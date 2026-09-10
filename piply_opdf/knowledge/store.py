"""
The layout knowledge store: one SQLite file, no ORM.

Why a plain file with a documented schema, when the text knowledge base uses
SQLAlchemy: the plan says each store is "its own file so other applications can
use them". A bare SQLite table can be read by anything — Python, a CLI, a
spreadsheet tool, another team's service — without agreeing on a mapping layer
first. It also keeps the package light, which is the standing rule here.

Two guarantees this module enforces rather than documents:

1. **Only human-verified regions become knowledge.** A detector's opinion is
   output, not truth. ``remember`` refuses any other source, so a bad
   classification cannot teach itself.
2. **Matching never crosses a feature version.** ``candidates`` filters on the
   current one. Reading stale records is possible, but you have to ask for it
   by name.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from piply_opdf.core.exceptions import KnowledgeBaseError
from piply_opdf.core.types import BBox
from piply_opdf.knowledge.actions import LayoutAction, LayoutFeedback
from piply_opdf.knowledge.layout import LayoutFeatures
from piply_opdf.knowledge.provenance import FEATURE_VERSION, Provenance, utc_now

__all__ = [
    "LayoutKnowledgeStore", "StoredLayout", "TRUSTED_SOURCES",
    "EXPORT_FORMAT_VERSION",
]

#: The shape of an exported file. Bumped when the layout of the JSON
#: changes — separate from ``FEATURE_VERSION``, which is about what the
#: numbers mean. A reader that cannot understand the file says so rather
#: than guessing at half of it.
EXPORT_FORMAT_VERSION = 1

#: Sources allowed into the store. ``human`` is a person's own judgement;
#: ``manual_import`` is verified knowledge carried in from another store. Both
#: trace back to a human decision, which is the whole entry requirement.
#:
#: The vocabulary matches the existing text knowledge base on purpose, so the
#: two stores can be reasoned about together.
TRUSTED_SOURCES = ("human", "manual_import")

_FEATURE_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(LayoutFeatures))

#: The versioning block, as columns. Declared once and shared by both tables so
#: they cannot drift apart.
_PROVENANCE_TYPES: tuple[tuple[str, str], ...] = (
    ("source_document", "TEXT"),
    ("source_page", "INTEGER"),
    ("detector_name", "TEXT"),
    ("detector_version", "TEXT"),
    ("model_version", "TEXT"),
    ("feature_version", "TEXT"),
    ("created_at", "TEXT"),
)
_PROVENANCE_DDL = ", ".join(f"{name} {kind}" for name, kind in _PROVENANCE_TYPES)

#: The same block without ``created_at``. The feedback table declares its own —
#: when the *action* happened, which is not when the region was detected. Two
#: columns of the same name is a schema error; two meanings under one name
#: would have been worse.
_PROVENANCE_DDL_NO_TIME = ", ".join(
    f"{name} {kind}" for name, kind in _PROVENANCE_TYPES if name != "created_at"
)

_KNOWLEDGE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS layout_knowledge (
    id                INTEGER PRIMARY KEY,
    source            TEXT NOT NULL,
    confidence        REAL NOT NULL,
    user_id           TEXT,
    {_PROVENANCE_DDL},
    component_type    TEXT NOT NULL,
    rel_x             REAL, rel_y REAL, rel_w REAL, rel_h REAL,
    page_band         TEXT,
    aspect_ratio      REAL,
    parent_type       TEXT, above_type TEXT, below_type TEXT,
    left_type         TEXT, right_type TEXT,
    aligns_left_with  INTEGER, aligns_right_with INTEGER,
    ink_ratio         REAL, stroke_width_cv REAL, component_density REAL,
    baseline_scatter  REAL, colour_clusters INTEGER,
    region_phash      TEXT, hog_features TEXT, hu_moments TEXT
);
CREATE INDEX IF NOT EXISTS ix_layout_type_version
    ON layout_knowledge (component_type, feature_version);
CREATE INDEX IF NOT EXISTS ix_layout_band
    ON layout_knowledge (page_band);

CREATE TABLE IF NOT EXISTS layout_feedback (
    id                  INTEGER PRIMARY KEY,
    layout_knowledge_id INTEGER,
    document_id         TEXT NOT NULL,
    page_no             INTEGER NOT NULL,
    action              TEXT NOT NULL,
    detected_type       TEXT,
    human_type          TEXT,
    bbox_before         TEXT,
    bbox_after          TEXT,
    user_id             TEXT,
    created_at          TEXT NOT NULL,
    {_PROVENANCE_DDL_NO_TIME}
);
CREATE INDEX IF NOT EXISTS ix_feedback_action ON layout_feedback (action);
CREATE INDEX IF NOT EXISTS ix_feedback_document ON layout_feedback (document_id);
"""


@dataclass(frozen=True, slots=True)
class StoredLayout:
    """A knowledge record as it came back out."""

    id: int
    source: str
    confidence: float
    features: LayoutFeatures
    provenance: Provenance
    user_id: str | None = None


class LayoutKnowledgeStore:
    """Answers "what kind of region is this?" from what people have confirmed.

    Usable as a context manager::

        with LayoutKnowledgeStore("knowledge/layout-001.db") as store:
            store.remember(features, provenance, source="human")
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.executescript(_KNOWLEDGE_SCHEMA)

    # ── writing ─────────────────────────────────────────────────────────────

    def remember(
        self,
        features: LayoutFeatures,
        provenance: Provenance,
        *,
        source: str,
        confidence: float = 1.0,
        user_id: str | None = None,
    ) -> int:
        """Store one verified region. Returns its id.

        Raises :class:`KnowledgeBaseError` for any source outside
        :data:`TRUSTED_SOURCES` — a detector's own output is not knowledge, and
        letting it in is how one unchecked mistake becomes a learned rule.
        """
        if source not in TRUSTED_SOURCES:
            raise KnowledgeBaseError(
                f"refusing source {source!r}: only human-verified content becomes "
                f"knowledge. Expected one of {', '.join(TRUSTED_SOURCES)}."
            )

        row: dict[str, Any] = {
            "source": source,
            "confidence": float(confidence),
            "user_id": user_id,
            **provenance.as_row(),
            **features.as_row(),
        }
        columns = list(row)
        statement = (
            f"INSERT INTO layout_knowledge ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})"
        )
        with self._connection:
            cursor = self._connection.execute(statement, [row[c] for c in columns])
        return int(cursor.lastrowid)

    def record(self, feedback: LayoutFeedback) -> int:
        """Log one human action. Returns its id."""
        row: dict[str, Any] = {
            "layout_knowledge_id": feedback.layout_knowledge_id,
            "document_id": feedback.document_id,
            "page_no": feedback.page_no,
            "action": feedback.action,
            "detected_type": feedback.detected_type,
            "human_type": feedback.human_type,
            "bbox_before": _box_to_json(feedback.bbox_before),
            "bbox_after": _box_to_json(feedback.bbox_after),
            "user_id": feedback.user_id,
            "created_at": feedback.created_at.isoformat(),
            **{
                k: v for k, v in feedback.provenance.as_row().items()
                if k != "created_at"        # the action's own time, not the record's
            },
        }
        columns = list(row)
        statement = (
            f"INSERT INTO layout_feedback ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})"
        )
        with self._connection:
            cursor = self._connection.execute(statement, [row[c] for c in columns])
        return int(cursor.lastrowid)

    # ── reading ─────────────────────────────────────────────────────────────

    def candidates(
        self,
        component_type: str | None = None,
        *,
        page_band: str | None = None,
        include_stale: bool = False,
        limit: int | None = None,
    ) -> list[StoredLayout]:
        """Records worth comparing against a page being processed now.

        Stale-version records are excluded unless ``include_stale`` is set,
        because features built by a different extractor are not comparable —
        see :mod:`piply_opdf.knowledge.provenance`. Ask for them by name when
        exporting or migrating, never when matching.
        """
        where: list[str] = []
        values: list[Any] = []

        if not include_stale:
            where.append("feature_version = ?")
            values.append(FEATURE_VERSION)
        if component_type is not None:
            where.append("component_type = ?")
            values.append(component_type)
        if page_band is not None:
            where.append("page_band = ?")
            values.append(page_band)

        query = "SELECT * FROM layout_knowledge"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id"
        if limit is not None:
            query += " LIMIT ?"
            values.append(int(limit))

        with closing(self._connection.execute(query, values)) as cursor:
            return [_to_stored(row) for row in cursor.fetchall()]

    def feedback(
        self, *, document_id: str | None = None, action: str | None = None
    ) -> list[LayoutFeedback]:
        """The action log, optionally narrowed."""
        if action is not None and action not in LayoutAction.ALL:
            raise ValueError(f"unknown action {action!r}")

        where: list[str] = []
        values: list[Any] = []
        if document_id is not None:
            where.append("document_id = ?")
            values.append(document_id)
        if action is not None:
            where.append("action = ?")
            values.append(action)

        query = "SELECT * FROM layout_feedback"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id"

        with closing(self._connection.execute(query, values)) as cursor:
            return [_to_feedback(row) for row in cursor.fetchall()]

    def stats(self) -> dict[str, Any]:
        """What is in here, including how much of it is no longer comparable.

        ``stale`` is reported separately rather than folded into the total: a
        store that looks full but answers nothing is the confusing failure this
        exists to prevent.
        """
        by_type = self._group("SELECT component_type, COUNT(*) FROM layout_knowledge "
                              "GROUP BY component_type")
        by_version = self._group("SELECT feature_version, COUNT(*) FROM layout_knowledge "
                                 "GROUP BY feature_version")
        by_action = self._group("SELECT action, COUNT(*) FROM layout_feedback "
                                "GROUP BY action")
        total = sum(by_type.values())
        current = by_version.get(FEATURE_VERSION, 0)

        return {
            "path": str(self.path),
            "total": total,
            "current_feature_version": FEATURE_VERSION,
            "usable": current,
            "stale": total - current,
            "by_type": by_type,
            "by_feature_version": by_version,
            "feedback": by_action,
        }

    def _group(self, query: str) -> dict[str, int]:
        with closing(self._connection.execute(query)) as cursor:
            return {str(key): int(count) for key, count in cursor.fetchall()}

    # ── moving a store between machines ─────────────────────────────────────

    def export_to(self, path: str | Path) -> dict[str, int]:
        """Write everything to one JSON file, including stale records.

        Stale records are exported rather than dropped: an export is a copy of
        what is there, not a filtered view. They arrive at the other end still
        marked stale and still ignored by matching, which is the correct
        outcome — silently deleting somebody's older knowledge during a move is
        not this function's decision to make.

        The action log travels with the knowledge. Separated, the counts that
        make a detector measurable are lost.
        """
        knowledge = self.candidates(include_stale=True)
        actions = self.feedback()

        payload = {
            "format_version": EXPORT_FORMAT_VERSION,
            "exported_at": utc_now().isoformat(),
            "current_feature_version": FEATURE_VERSION,
            "knowledge": [
                {
                    "source": record.source,
                    "confidence": record.confidence,
                    "user_id": record.user_id,
                    "provenance": record.provenance.as_row(),
                    "features": record.features.as_row(),
                }
                for record in knowledge
            ],
            "feedback": [
                {
                    "action": row.action,
                    "document_id": row.document_id,
                    "page_no": row.page_no,
                    "layout_knowledge_id": row.layout_knowledge_id,
                    "detected_type": row.detected_type,
                    "human_type": row.human_type,
                    "bbox_before": _box_to_json(row.bbox_before),
                    "bbox_after": _box_to_json(row.bbox_after),
                    "user_id": row.user_id,
                    "created_at": row.created_at.isoformat(),
                    "provenance": row.provenance.as_row(),
                }
                for row in actions
            ],
        }

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {"knowledge": len(knowledge), "feedback": len(actions)}

    def import_from(self, path: str | Path) -> dict[str, int]:
        """Read a file written by :meth:`export_to`.

        Everything arrives as ``manual_import``: it reached this store through
        a person moving a file, not through a detector, and the source column
        should say which. Records whose feature version does not match are
        stored and counted as ``stale`` — kept, but not matched against.
        """
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

        found = payload.get("format_version")
        if found != EXPORT_FORMAT_VERSION:
            raise KnowledgeBaseError(
                f"export format {found!r} cannot be read by this version "
                f"(expected {EXPORT_FORMAT_VERSION})"
            )

        stale = 0
        for record in payload.get("knowledge", []):
            provenance = _provenance_from(record["provenance"])
            if not provenance.is_current:
                stale += 1
            self.remember(
                LayoutFeatures(**record["features"]),
                provenance,
                source="manual_import",
                confidence=float(record.get("confidence", 1.0)),
                user_id=record.get("user_id"),
            )

        for row in payload.get("feedback", []):
            self.record(LayoutFeedback(
                action=row["action"],
                document_id=row["document_id"],
                page_no=int(row["page_no"]),
                provenance=_provenance_from(row["provenance"]),
                layout_knowledge_id=row.get("layout_knowledge_id"),
                detected_type=row.get("detected_type"),
                human_type=row.get("human_type"),
                bbox_before=_box_from_json(row.get("bbox_before")),
                bbox_after=_box_from_json(row.get("bbox_after")),
                user_id=row.get("user_id"),
                created_at=_parse_time(row.get("created_at")),
            ))

        return {
            "knowledge": len(payload.get("knowledge", [])),
            "feedback": len(payload.get("feedback", [])),
            "stale": stale,
        }

    # ── lifecycle ───────────────────────────────────────────────────────────

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> LayoutKnowledgeStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


# ── row conversion ───────────────────────────────────────────────────────────

def _provenance_from(data: dict[str, Any]) -> Provenance:
    """Rebuild a versioning block from a database row or an exported dict."""
    return Provenance(
        source_document=data.get("source_document") or "",
        source_page=int(data.get("source_page") or 0),
        detector_name=data.get("detector_name") or "unknown",
        detector_version=data.get("detector_version") or "0",
        model_version=data.get("model_version"),
        feature_version=data.get("feature_version") or "",
        created_at=_parse_time(data.get("created_at")),
    )


def _to_stored(row: sqlite3.Row) -> StoredLayout:
    data = dict(row)
    features = LayoutFeatures(**{c: data[c] for c in _FEATURE_COLUMNS})
    provenance = _provenance_from(data)
    return StoredLayout(
        id=int(data["id"]),
        source=data["source"],
        confidence=float(data["confidence"]),
        features=features,
        provenance=provenance,
        user_id=data["user_id"],
    )


def _to_feedback(row: sqlite3.Row) -> LayoutFeedback:
    data = dict(row)
    # The feedback row has no provenance ``created_at`` — the action has its
    # own, read separately below.
    provenance = _provenance_from({**data, "created_at": None})
    return LayoutFeedback(
        action=data["action"],
        document_id=data["document_id"],
        page_no=int(data["page_no"]),
        provenance=provenance,
        layout_knowledge_id=data["layout_knowledge_id"],
        detected_type=data["detected_type"],
        human_type=data["human_type"],
        bbox_before=_box_from_json(data["bbox_before"]),
        bbox_after=_box_from_json(data["bbox_after"]),
        user_id=data["user_id"],
        created_at=_parse_time(data["created_at"]),
    )


def _box_to_json(box: BBox | None) -> str | None:
    return None if box is None else json.dumps(list(box.to_tuple()))


def _box_from_json(value: str | None) -> BBox | None:
    if not value:
        return None
    return BBox.from_any(json.loads(value))


def _parse_time(value: str | None) -> datetime:
    if not value:
        return utc_now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return utc_now()
