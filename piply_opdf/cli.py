"""
piply-opdf CLI
===============

Command-line interface powered by Typer.

Available commands
------------------
    piply-opdf assess <file>
    piply-opdf enhance <file>
    piply-opdf detect-tables <file>
    piply-opdf extract-grid <file>
    piply-opdf run <file>          # full pipeline
    piply-opdf version
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from piply_opdf import __version__
from piply_opdf.config import load_config
from piply_opdf.document import Document

app = typer.Typer(
    name="piply-opdf",
    help="OCR + PDF Document Understanding Framework",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True, style="bold red")

# ── Common options ────────────────────────────────────────────────────────────

ConfigOption = Annotated[
    Optional[Path],
    typer.Option("--config", "-c", help="Path to custom YAML config file", show_default=False),
]
WorkDirOption = Annotated[
    Optional[Path],
    typer.Option("--work-dir", "-w", help="Output directory for artefacts", show_default=False),
]
OutputOption = Annotated[
    Optional[Path],
    typer.Option("--output", "-o", help="Override output file path", show_default=False),
]


def _make_document(
    file: Path,
    config: Optional[Path],
    work_dir: Optional[Path],
) -> Document:
    if not file.exists():
        err_console.print(f"File not found: {file}")
        raise typer.Exit(1)
    cfg = load_config(config) if config else None
    return Document(file, config=cfg, work_dir=work_dir)


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command("version")
def cmd_version() -> None:
    """Show the piply-opdf version and exit."""
    console.print(f"piply-opdf [bold cyan]v{__version__}[/bold cyan]")


@app.command("assess")
def cmd_assess(
    file: Annotated[Path, typer.Argument(help="PDF or image file to assess")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
    output: OutputOption = None,
    json_only: Annotated[bool, typer.Option("--json", help="Print raw JSON output")] = False,
) -> None:
    """
    [Phase 1] Assess document quality — blur, noise, contrast, skew.

    Writes [bold]assessment.json[/bold] to the work directory.
    """
    doc = _make_document(file, config, work_dir)

    with console.status("[bold green]Assessing document…"):
        result = doc.assess(output_path=output)

    if json_only:
        console.print_json(result.model_dump_json(indent=2))
        return

    summary = result.summary()
    table = Table(title=f"Assessment — {file.name}", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    issues = summary["issues"]
    table.add_row("Pages", str(result.page_count))
    table.add_row("Blurry pages", str(issues["blurry_pages"]))
    table.add_row("Noisy pages", str(issues["noisy_pages"]))
    table.add_row("Low-contrast pages", str(issues["low_contrast_pages"]))
    table.add_row("Skewed pages", str(issues["skewed_pages"]))
    table.add_row(
        "Enhancement needed",
        "[red]YES[/red]" if result.any_enhancement_needed else "[green]NO[/green]",
    )
    table.add_row(
        "Recommended enhancements",
        ", ".join(result.recommended_enhancements) or "none",
    )

    console.print(table)
    out_path = output or (doc.work_dir / "assessment.json")
    console.print(f"\n[dim]Saved → {out_path}[/dim]")


@app.command("enhance")
def cmd_enhance(
    file: Annotated[Path, typer.Argument(help="PDF or image file to enhance")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
    output: OutputOption = None,
    no_assess: Annotated[bool, typer.Option("--no-assess", help="Skip assessment step")] = False,
) -> None:
    """
    [Phase 2] Enhance document — deskew, denoise, contrast, sharpen.

    Writes [bold]<name>_enhanced.pdf[/bold] to the work directory.
    """
    doc = _make_document(file, config, work_dir)

    if not no_assess:
        with console.status("[bold green]Assessing first…"):
            doc.assess()

    with console.status("[bold green]Enhancing document…"):
        enhanced_path = doc.enhance(output_path=output)

    console.print(Panel(
        f"[green]✓[/green] Enhanced PDF written to:\n[bold]{enhanced_path}[/bold]",
        title="Phase 2 — Enhancement",
        border_style="green",
    ))


@app.command("detect-tables")
def cmd_detect_tables(
    file: Annotated[Path, typer.Argument(help="PDF or image file")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
) -> None:
    """Detect structured bordered tables using OpenCV."""
    doc = _make_document(file, config, work_dir)
    with console.status("[bold green]Detecting structured tables…"):
        # We run the full process_layout which handles the priority pipeline,
        # but report only the bordered tables.
        tables = doc.process_layout()

    console.print(Panel(
        f"[green]✓[/green] Detected [bold]{len(tables)}[/bold] structured tables\n"
        f"Output directory: [bold]{doc.work_dir}/layouts[/bold]",
        title="Structured Table Detection (P1)",
        border_style="green",
    ))


@app.command("detect-borderless-tables")
def cmd_detect_borderless_tables(
    file: Annotated[Path, typer.Argument(help="PDF or image file")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
) -> None:
    """Detect borderless tables using PyMuPDF and OpenCV."""
    doc = _make_document(file, config, work_dir)
    with console.status("[bold green]Detecting borderless tables…"):
        doc.process_layout()

    console.print(Panel(
        f"[green]✓[/green] Detected [bold]{len(doc.borderless_tables)}[/bold] borderless tables\n"
        f"Output directory: [bold]{doc.work_dir}/layouts[/bold]",
        title="Borderless Table Detection (P2)",
        border_style="green",
    ))


@app.command("detect-headers")
def cmd_detect_headers(
    file: Annotated[Path, typer.Argument(help="PDF or image file")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
) -> None:
    """Detect page headers using PyMuPDF."""
    doc = _make_document(file, config, work_dir)
    with console.status("[bold green]Detecting headers…"):
        doc.process_layout()

    console.print(Panel(
        f"[green]✓[/green] Detected [bold]{len(doc.headers)}[/bold] headers",
        title="Header Detection (P3)",
        border_style="green",
    ))


@app.command("detect-footers")
def cmd_detect_footers(
    file: Annotated[Path, typer.Argument(help="PDF or image file")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
) -> None:
    """Detect page footers using PyMuPDF."""
    doc = _make_document(file, config, work_dir)
    with console.status("[bold green]Detecting footers…"):
        doc.process_layout()

    console.print(Panel(
        f"[green]✓[/green] Detected [bold]{len(doc.footers)}[/bold] footers",
        title="Footer Detection (P4)",
        border_style="green",
    ))



@app.command("run")
def cmd_run(
    file: Annotated[Path, typer.Argument(help="PDF or image file to process")],
    config: ConfigOption = None,
    work_dir: WorkDirOption = None,
) -> None:
    """
    Run the complete Phase 1–5 pipeline in sequence.

    Equivalent to running: assess → enhance → detect-layout → extract-layouts → ocr
    """
    doc = _make_document(file, config, work_dir)

    steps = [
        ("Phase 1 — Assessment", "assess"),
        ("Phase 2 — Enhancement", "enhance"),
        ("Phase 3 — Table & Grid Extraction", "process_layout"),
    ]

    for label, method in steps:
        with console.status(f"[bold green]{label}…"):
            getattr(doc, method)()
        console.print(f"[green][DONE][/green] {label}")

    console.print(Panel(
        f"[green]Pipeline complete![/green]\n"
        f"All artefacts written to: [bold]{doc.work_dir}[/bold]\n\n"
        f"  assessment.json\n"
        f"  {file.stem}_enhanced.pdf\n"
        f"  layouts/\n"
        f"  debug/",
        title="piply-opdf — Done",
        border_style="green",
    ))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
