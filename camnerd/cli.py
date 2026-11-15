"""camnerd: extract camera metadata from photos and analyse your shooting habits."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from camnerd.metadata import load, scan
from camnerd.report import render

app = typer.Typer(help=__doc__, no_args_is_help=True, add_completion=False)
console = Console()

PathsArg = Annotated[list[Path], typer.Argument(exists=True, help="Image files/folders (analyze also accepts a .csv/.json from extract)")]
SAVERS = {
    ".svg": lambda c, p: c.save_svg(str(p), title="camnerd"),
    ".html": lambda c, p: c.save_html(str(p)),
    ".txt": lambda c, p: c.save_text(str(p)),
}
NoRecursive = Annotated[bool, typer.Option("--no-recursive", help="Don't descend into subfolders")]


@app.command()
def extract(
    paths: PathsArg,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output .csv or .json")] = Path("metadata.csv"),
    show: Annotated[bool, typer.Option("--show", help="Print each file's metadata")] = False,
    no_recursive: NoRecursive = False,
):
    """Extract EXIF + Fujifilm settings from every JPEG into a CSV/JSON file."""
    with console.status("Reading metadata…"):
        df = scan(paths, recursive=not no_recursive)
    if df.empty:
        raise typer.Exit("No JPEGs found.")

    if show:
        for _, row in df.iterrows():
            t = Table(title=f"[bold]{row['File']}", title_justify="left", show_header=False, box=None)
            for k, v in row.dropna().items():
                if k not in ("File", "Path"):
                    t.add_row(f"[dim]{k}", str(v))
            console.print(t)

    if out.suffix.lower() == ".json":
        df.to_json(out, orient="records", indent=2, date_format="iso")
    else:
        df.to_csv(out, index=False)
    console.print(f"[green]✓[/] Extracted {len(df)} images → {out}")


@app.command()
def analyze(
    paths: PathsArg,
    top: Annotated[int, typer.Option(help="Rows per frequency table")] = 8,
    save: Annotated[Path | None, typer.Option("--save", help="Also save the report as .svg, .html or .txt")] = None,
    no_recursive: NoRecursive = False,
):
    """Report your most frequent camera settings."""
    with console.status("Reading metadata…"):
        df = load(paths, recursive=not no_recursive)
    if df.empty:
        raise typer.Exit("No JPEGs found.")
    if save and save.suffix.lower() not in SAVERS:
        raise typer.BadParameter("use a .svg, .html or .txt file", param_hint="--save")
    out = Console(record=True) if save else console
    render(df, top=top, console=out)
    if save:
        SAVERS[save.suffix.lower()](out, save)
        console.print(f"[green]✓[/] Saved report → {save}")


if __name__ == "__main__":
    app()
