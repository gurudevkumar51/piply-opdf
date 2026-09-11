"""
Copying a knowledge base somewhere safe, and checking the copy is real.

The knowledge bases are the only things here that cannot be rebuilt. Delete the
working database and you reprocess; delete `piply_opdf_knowledge-001.db` and
1,656 human decisions are gone, along with every hour that went into making
them. This project has already lost data from the working database once, which
is the cheap version of the lesson.

Two things this does that copying the file does not:

**It uses SQLite's own backup, not a file copy.** A database being written to
has pages in flight; `shutil.copy` can catch a page half-written and produce a
file that opens fine and is subtly wrong. The backup API copies under a read
lock and is safe against a live writer.

**It reads the copy back.** A backup nobody has opened is a belief, not a
backup — and the failure it guards against is exactly the one where you find
out at restore time. Every copy here is opened, integrity-checked and counted
before the function returns, and the counts are reported so a copy that came
back empty cannot pass quietly.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from piply_opdf.core.exceptions import KnowledgeBaseError
from piply_opdf.knowledge.provenance import utc_now

__all__ = ["BackupResult", "backup_database", "backup_all", "KNOWLEDGE_GLOBS"]

#: What counts as a knowledge base worth keeping. Both stores, not just the
#: text one: layout knowledge is equally unrepeatable and equally a person's
#: time.
KNOWLEDGE_GLOBS = ("piply_opdf_knowledge-*.db", "piply_opdf_layout-*.db")

#: How many copies of one database to keep. Older ones are removed as newer
#: ones succeed — but only *after* the new copy has been verified, so a failed
#: backup can never be the thing that deletes the last good one.
DEFAULT_KEEP = 7


@dataclass(frozen=True, slots=True)
class BackupResult:
    """One database copied, and what was found in the copy."""

    source: Path
    target: Path
    tables: dict[str, int]
    removed: tuple[Path, ...] = ()

    @property
    def rows(self) -> int:
        return sum(self.tables.values())

    def summary(self) -> str:
        counts = ", ".join(f"{name} {n}" for name, n in sorted(self.tables.items()))
        return f"{self.source.name} -> {self.target.name} ({counts or 'empty'})"


def backup_database(
    source: str | Path,
    target_dir: str | Path,
    *,
    keep: int = DEFAULT_KEEP,
    stamp: datetime | None = None,
) -> BackupResult:
    """Copy one database, verify the copy, then prune older ones.

    The order matters and is the whole point: verify before pruning, so a
    backup that failed cannot be what removes the last good one.
    """
    source_path = Path(source)
    if not source_path.exists():
        raise KnowledgeBaseError(f"nothing to back up at {source_path}")

    target_root = Path(target_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    when = (stamp or utc_now()).strftime("%Y%m%d-%H%M%S")
    target = target_root / f"{source_path.stem}.{when}.db"

    # `with sqlite3.connect(...)` commits the transaction; it does **not**
    # close the connection. On Windows that leaves the file locked, and the
    # prune below then fails with "used by another process" — found by the
    # test that prunes. `closing` is what actually releases the handle.
    with closing(sqlite3.connect(str(source_path))) as origin:
        with closing(sqlite3.connect(str(target))) as copy:
            origin.backup(copy)                  # safe against a live writer

    tables = _verify(target)
    removed = _prune(target_root, source_path.stem, keep)
    return BackupResult(source_path, target, tables, removed)


def backup_all(
    knowledge_dir: str | Path = "knowledge",
    target_dir: str | Path = "knowledge/backups",
    *,
    keep: int = DEFAULT_KEEP,
) -> list[BackupResult]:
    """Back up every knowledge base found in *knowledge_dir*.

    Returns one result per database. An empty list means nothing was found,
    which is worth saying out loud rather than reporting as success.
    """
    root = Path(knowledge_dir)
    found: list[Path] = []
    for pattern in KNOWLEDGE_GLOBS:
        found.extend(sorted(root.glob(pattern)))

    return [backup_database(path, target_dir, keep=keep) for path in found]


def _verify(path: Path) -> dict[str, int]:
    """Open the copy, check it, and count what is in it.

    Raises rather than returning a flag: a backup that cannot be read is not a
    backup, and a caller that has to remember to check a boolean will one day
    forget on the run that mattered.
    """
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
            verdict = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if verdict != "ok":
                raise KnowledgeBaseError(f"backup {path.name} is corrupt: {verdict}")

            names = [
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            ]
            return {
                name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for name in names
            }
    except sqlite3.Error as error:
        raise KnowledgeBaseError(f"backup {path.name} could not be read: {error}") from error


def _prune(target_dir: Path, stem: str, keep: int) -> tuple[Path, ...]:
    """Remove all but the newest *keep* copies of one database.

    Names sort chronologically because the timestamp is fixed-width and in
    year-month-day order, so this needs no file metadata — which would be wrong
    anyway after the backups are themselves copied somewhere else.
    """
    if keep <= 0:
        return ()

    existing = sorted(target_dir.glob(f"{stem}.*.db"))
    doomed = existing[:-keep]
    for path in doomed:
        path.unlink()
    return tuple(doomed)


def restore(backup_path: str | Path, target: str | Path) -> Path:
    """Put a verified backup back.

    Deliberately not clever: it checks the backup first, refuses to write over
    a file that is currently a working database without you having moved it
    aside, and copies. Restoring is the moment to be boring.
    """
    source = Path(backup_path)
    destination = Path(target)

    _verify(source)                          # never restore something unread

    if destination.exists():
        raise KnowledgeBaseError(
            f"{destination} already exists. Move it aside first — overwriting a "
            f"live knowledge base is not something this should decide for you."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination
