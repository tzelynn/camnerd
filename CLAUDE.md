# CLAUDE.md

camnerd is a small Python CLI (Typer + rich) that extracts camera metadata from JPEGs and reports frequently used settings. See README.md for user-facing usage.

## Commands

```sh
uv sync                                   # install deps
uv run camnerd analyze sample_pics/       # main smoke test: full report
uv run camnerd extract sample_pics/ -o /tmp/m.csv && uv run camnerd analyze /tmp/m.csv   # CSV round-trip
```

There is no test suite yet. Check changes by running both commands above against `sample_pics/`, and also try the JSON path (`-o x.json`) when touching I/O or column types. For report layout changes, also check a narrow terminal (`COLUMNS=80`); the recipe table switches to a card layout when it won't fit.

## Layout

- `camnerd/cli.py`: Typer app with the `extract` and `analyze` commands. Keep it thin.
- `camnerd/metadata.py`: `read_metadata(path) -> dict` builds one flat row per image from EXIF (exifread), with XMP (Pillow) as fallback. Also handles Fujifilm maker notes, Lightroom `crs:` develop settings (`LR_*` columns) and `EditedIn` detection. `scan()` builds the DataFrame; `load()` also reloads extract's CSV/JSON output.
- `camnerd/fuji.py`: decodes Fujifilm maker-note tag IDs into the camera-menu labels. The lookup tables come from ExifTool's `FujiFilm.pm`.
- `camnerd/report.py`: `_add_derived()` adds bucketed and derived columns (shutter stop, ISO/aperture/focal bins, time of day, WB shift). `build()` returns the report as named rich panels (overview, sections, recipes + crosstab, post-processing, takeaways); `render()` prints them. `section()` collapses settings with a single value into a "Same in every shot" table. Each section's colour comes from `THEME`, friendly column titles from `LABELS`.
- `docs/screenshots.py`: regenerates the README SVGs from `sample_pics/`. Re-run it after visible report changes.

## Conventions and gotchas

- Rows are flat dicts with CamelCase column names. Missing values are `None`/NA, never a placeholder string. Report code must tolerate any column being absent (`_add_derived` back-fills the expected ones).
- Fujifilm tone/color settings are **text labels** (`"+2"`, `"-1"`, `"0"`), not numbers. Columns that need this are listed in `fuji.TEXT_COLUMNS` so `load()` doesn't coerce them when reading CSV. Add new label-style columns there.
- Any new `RECIPE_FIELDS` entry in `report.py` also needs a short header in `RECIPE_SHORT` and a friendly name in `LABELS`.
- `metadata.LR_SLIDERS` (XMP names, some with a `2012` suffix) and `report.LR_SLIDERS` (column names without it) must stay in sync.
- `scan()` logs and skips files it cannot read; it should never abort the whole run.
- Ordered categoricals (shutter, buckets, month) keep their natural order in `freq_table`. Other series are sorted by count and truncated to `--top`.
- Code style: compact, type-hinted, comments only where the reason isn't obvious. Requires Python 3.13+.
