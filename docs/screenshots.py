"""Regenerate the README screenshots: uv run python docs/screenshots.py"""

import io
from pathlib import Path

from rich.console import Console

from camnerd.metadata import load
from camnerd.report import build

ROOT = Path(__file__).parent
SHOTS = {
    "overview": ["Overview", "Gear", "Exposure"],
    "fujifilm": ["Fujifilm JPEG settings", "Fujifilm recipes"],
    "takeaways": ["Post-processing", "Takeaways"],
}

blocks = dict(build(load([ROOT.parent / "sample_pics"]), width=112))
for name, keys in SHOTS.items():
    console = Console(record=True, width=112, force_terminal=True, file=io.StringIO())
    for k in keys:
        console.print(blocks[k])
    console.save_svg(str(ROOT / f"{name}.svg"), title="camnerd analyze sample_pics/")
    print(f"wrote docs/{name}.svg")
