"""Frequency analysis of camera settings, rendered with rich."""

import numpy as np
import pandas as pd
from rich import box
from rich.columns import Columns
from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

RECIPE_FIELDS = [
    "FilmSimulation", "DynamicRange", "HighlightTone", "ShadowTone", "Color",
    "Sharpness", "NoiseReduction", "Clarity", "GrainEffect", "GrainSize",
    "ColorChromeEffect", "ColorChromeFXBlue", "WhiteBalance", "WBShift",
]
LR_SLIDERS = [
    "Exposure", "Contrast", "Highlights", "Shadows", "Whites", "Blacks", "Texture", "Clarity",
    "Dehaze", "Vibrance", "Saturation", "IncrementalTemperature", "IncrementalTint",
    "GrainAmount", "PostCropVignetteAmount",
]

FULL_STOPS = np.array([30, 15, 8, 4, 2, 1, 1/2, 1/4, 1/8, 1/15, 1/30, 1/60, 1/125,
                       1/250, 1/500, 1/1000, 1/2000, 1/4000, 1/8000, 1/16000])
ISO_BINS = ([0, 200, 400, 800, 1600, 3200, np.inf],
            ["≤200", "250–400", "500–800", "1000–1600", "2000–3200", ">3200"])
APERTURE_BINS = ([0, 2, 2.8, 4, 5.6, 8, 11, 16, np.inf],
                 ["≤f/2", "f/2.2–2.8", "f/3.2–4", "f/4.5–5.6", "f/6.4–8", "f/9–11", "f/13–16", ">f/16"])
FOCAL_BINS = ([0, 24, 35, 50, 85, 135, np.inf],
              ["≤24mm wide", "25–35mm", "36–50mm normal", "51–85mm portrait", "86–135mm", ">135mm tele"])
HOUR_BINS = ([-1, 5, 11, 16, 23], ["Night 0–5h", "Morning 6–11h", "Afternoon 12–16h", "Evening 17–23h"])

BAR_WIDTH = 16
MAX_WIDTH = 112  # keep the report readable on very wide terminals
ACCENT = "cyan"
# one colour per section, used for its border and bars
THEME = {"Gear": "magenta", "Exposure": "cyan", "Exposure summary": "cyan", "Framing & timing": "green",
         "Fujifilm JPEG settings": "yellow", "Focus & drive": "blue", "Fujifilm recipes": "yellow",
         "Post-processing": "bright_magenta", "Takeaways": "bright_cyan"}
LABELS = {"FilmSimulation": "Film simulation", "DynamicRange": "Dynamic range", "HighlightTone": "Highlight tone",
          "ShadowTone": "Shadow tone", "NoiseReduction": "Noise reduction", "GrainEffect": "Grain",
          "GrainSize": "Grain size", "ColorChromeEffect": "Color chrome", "ColorChromeFXBlue": "Color chrome blue",
          "WhiteBalance": "White balance", "WBShift": "WB shift", "FocusMode": "Focus mode",
          "AFAreaMode": "AF area", "DriveMode": "Drive", "ShutterType": "Shutter type",
          "ImageStabilization": "Stabilization"}
# values that mean "left at the camera default", shown dimmed so your changes stand out
DEFAULTS = {"0", "Off", "–", "R+0 B+0"}


def shutter_label(seconds: float) -> str:
    return f'{seconds:g}"' if seconds >= 1 else f"1/{round(1 / seconds)}"


def nearest_stop(seconds: pd.Series) -> pd.Categorical:
    """Snap shutter speeds to the nearest full stop, as an ordered category (slow → fast)."""
    idx = np.abs(np.log2(seconds.to_numpy()[:, None]) - np.log2(FULL_STOPS)).argmin(axis=1)
    labels = [shutter_label(s) for s in FULL_STOPS]
    return pd.Categorical([labels[i] for i in idx], categories=labels, ordered=True)


def bucket(series: pd.Series, bins) -> pd.Series:
    edges, labels = bins
    return pd.cut(series, bins=edges, labels=labels)




# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def bar(frac: float, color: str, width: int = BAR_WIDTH) -> Text:
    """Thin horizontal bar with half-cell resolution on a faint track."""
    full, half = divmod(max(1, round(frac * width * 2)), 2)
    filled = "━" * full + ("╸" if half else "")
    return Text.assemble((filled, color), ("─" * (width - len(filled)), "grey30"))


def title(name: str, n: int | None = None) -> Text:
    t = Text(name, style="bold")
    if n is not None:
        t.append(f"  {n} shot{'s' * (n != 1)}", style="dim")
    return t


def freq_table(name: str, series: pd.Series, top: int, color: str = ACCENT) -> Table | None:
    series = series.dropna()
    if series.empty:
        return None
    ordered = isinstance(series.dtype, pd.CategoricalDtype)
    counts = series.value_counts(sort=not ordered)
    counts = counts[counts > 0]  # categoricals keep their natural order (e.g. ISO low → high)
    shown = counts if ordered else counts.head(top)
    n, peak = len(series), shown.max()

    t = Table(title=title(LABELS.get(name, name), n), title_justify="left",
              show_header=False, box=None, padding=(0, 1), pad_edge=False)
    t.add_column(no_wrap=True, max_width=28, overflow="ellipsis")
    t.add_column(no_wrap=True)
    t.add_column(justify="right")
    t.add_column(justify="right", style="dim")
    for value, cnt in shown.items():
        t.add_row(Text(str(value), style="bold" if cnt == peak else ""), bar(cnt / n, color), str(cnt), f"{cnt / n:.0%}")
    if (rest := len(counts) - len(shown)) > 0:
        other = counts.iloc[len(shown):].sum()
        t.add_row(Text(f"+{rest} more", style="dim italic"), bar(other / n, "grey50"), Text(str(other), style="dim"), f"{other / n:.0%}")
    return t


def constant_table(rows: list[tuple[str, str, int]], color: str) -> Table:
    """Settings that never changed, collapsed into one compact table instead of full-width 100% bars."""
    t = Table(title=title("Same in every shot"), title_justify="left", show_header=False,
              box=None, padding=(0, 1), pad_edge=False, min_width=20)
    t.add_column(style="dim", no_wrap=True)
    t.add_column(no_wrap=True, max_width=32, overflow="ellipsis")
    t.add_column(style="dim", justify="right")
    for name, value, n in rows:
        t.add_row(LABELS.get(name, name), Text(value, style=f"bold {color}"), f"all {n}")
    return t


Item = tuple[str, pd.Series] | RenderableType | None


def section(name: str, items: list[Item], top: int, width: int) -> Panel | None:
    """Panel of frequency tables; `items` are (column name, series) pairs or ready-made renderables."""
    color = THEME.get(name, ACCENT)
    tables, constant = [], []
    for item in items:
        if isinstance(item, tuple):
            col, s = item
            s = s.dropna()
            if s.empty:
                continue
            if s.nunique() == 1 and len(s) > 1:
                constant.append((col, str(s.iloc[0]), len(s)))
            else:
                tables.append(freq_table(col, s, top, color))
        elif item is not None:
            tables.append(item)
    if constant:
        tables.insert(0, constant_table(constant, color))
    if not tables:
        return None
    return panel(name, Columns(tables, padding=(1, 3)), width)


def panel(name: str, body: RenderableType, width: int) -> Panel:
    color = THEME.get(name, ACCENT)
    return Panel(body, title=f"[bold {color}] {name} ", title_align="left", border_style=color,
                 box=box.ROUNDED, padding=(1, 2), width=width)


def signed(v: float, fmt: str) -> Text:
    return Text(format(v, fmt), style="green" if v > 0 else "red" if v < 0 else "dim")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["File", "Model", "LensModel", "ExposureTime", "FNumber", "ISO", "FocalLength35mm",
                "ExposureProgram", "MeteringMode", "ExposureCompensation", "HasFujiSettings",
                "WBShiftRed", "WBShiftBlue", "EditedIn", "LR_Profile", "LR_Cropped", "DateTimeOriginal",
                *RECIPE_FIELDS]:
        if col not in df:
            df[col] = pd.NA
    df["HasFujiSettings"] = df["HasFujiSettings"].astype("boolean").fillna(False)
    df["HasExposure"] = df["ExposureTime"].notna()
    df["WBShift"] = df.apply(
        lambda r: f"R{int(r.WBShiftRed):+d} B{int(r.WBShiftBlue):+d}" if pd.notna(r.WBShiftRed) else None, axis=1
    )
    exp = df["ExposureTime"].astype(float)
    df["Shutter"] = pd.Series(pd.NA, index=df.index, dtype="object")
    if exp.notna().any():
        df.loc[exp.notna(), "Shutter"] = nearest_stop(exp.dropna())
        df["Shutter"] = pd.Categorical(df["Shutter"], categories=[shutter_label(s) for s in FULL_STOPS], ordered=True)
    df["ApertureBucket"] = bucket(df["FNumber"].astype(float), APERTURE_BINS)
    df["ISOBucket"] = bucket(df["ISO"].astype(float), ISO_BINS)
    df["FocalBucket"] = bucket(df["FocalLength35mm"].astype(float), FOCAL_BINS)
    dt = pd.to_datetime(df["DateTimeOriginal"], errors="coerce")
    df["TimeOfDay"] = bucket(dt.dt.hour, HOUR_BINS)
    months = dt.dt.strftime("%Y-%m")
    df["Month"] = pd.Categorical(months, categories=sorted(months.dropna().unique()), ordered=True)
    return df


def build(df: pd.DataFrame, top: int = 8, width: int = MAX_WIDTH) -> list[tuple[str, RenderableType]]:
    """All report blocks as (name, renderable), in display order. Empty sections are left out."""
    width = min(width, MAX_WIDTH)
    df = _add_derived(df)
    exp = df[df["HasExposure"]]
    fuji = df[df["HasFujiSettings"]]
    comp = exp["ExposureCompensation"].dropna().astype(float).map(lambda v: f"{v:+g} EV" if v else "0 EV")

    blocks = [
        ("Overview", _overview(df, exp, fuji, width)),
        ("Gear", section("Gear", [("Body", df["Model"]), ("Lens", df["LensModel"])], top, width)),
        ("Exposure", section("Exposure", [
            ("Mode", exp["ExposureProgram"]), ("Metering", exp["MeteringMode"]),
            ("Shutter (nearest stop)", exp["Shutter"]), ("Aperture", exp["ApertureBucket"]),
            ("ISO", exp["ISOBucket"]), ("Exp. compensation", comp),
        ], top, width)),
        ("Exposure summary", _exposure_summary(exp, top, width)),
        ("Framing & timing", section("Framing & timing", [
            ("Focal length (35mm eq.)", exp["FocalBucket"]), ("Time of day", df["TimeOfDay"]), ("Month", df["Month"]),
        ], top, width)),
    ]
    if not fuji.empty:
        blocks += [
            ("Fujifilm JPEG settings", section("Fujifilm JPEG settings",
                                               [(f, fuji[f]) for f in RECIPE_FIELDS if f in fuji], top, width)),
            ("Fujifilm recipes", _recipes(fuji, top, width)),
            ("Focus & drive", section("Focus & drive", [(f, fuji[f]) for f in
                                      ["FocusMode", "AFAreaMode", "DriveMode", "ShutterType", "ImageStabilization"]
                                      if f in fuji], top, width)),
        ]
    blocks += [("Post-processing", _post(df, top, width)), ("Takeaways", _takeaways_panel(df, exp, fuji, width))]
    return [(name, b) for name, b in blocks if b is not None]


def render(df: pd.DataFrame, top: int = 8, console: Console | None = None):
    console = console or Console()
    for _, block in build(df, top, console.width):
        console.print(block)


def _overview(df, exp, fuji, width: int) -> Panel:
    def tile(value, label: str) -> Text:
        return Text.assemble((str(value), f"bold {ACCENT}"), "\n", (label, "dim"), justify="center")

    dt = pd.to_datetime(df["DateTimeOriginal"], errors="coerce").dropna()
    tiles = [tile(len(df), "images"), tile(len(exp), "exposure data"), tile(len(fuji), "Fujifilm JPEGs"),
             tile(df["Model"].nunique(), "bodies"), tile(df["LensModel"].nunique(), "lenses")]
    if not dt.empty:
        span = f"{dt.min():%b %Y}" if dt.min().to_period("M") == dt.max().to_period("M") \
            else f"{dt.min():%b %Y} → {dt.max():%b %Y}"
        tiles.append(tile(span, "shot between"))
    grid = Table.grid(expand=True, padding=(0, 1))
    for i, _ in enumerate(tiles):
        grid.add_column(justify="center", ratio=2 if i == 5 else 1)  # the date span needs more room
    grid.add_row(*tiles)

    body: list[RenderableType] = [grid]
    stripped = df.loc[~df["HasExposure"], "File"].dropna().tolist()
    if stripped:
        body.append(Padding(Text.assemble(("⚠ ", "yellow"), (f"{len(stripped)} with camera EXIF stripped by an editor: ", "yellow"),
                                          (", ".join(stripped), "dim")), (1, 0, 0, 0)))
    return Panel(Group(*body), title=f"[bold {ACCENT}]◉ camnerd[/]", subtitle="[dim]camera settings report",
                 subtitle_align="right", title_align="left", border_style=ACCENT, box=box.HEAVY,
                 padding=(1, 2), width=width)


def _exposure_summary(exp: pd.DataFrame, top: int, width: int) -> Panel | None:
    if exp.empty:
        return None
    stats = exp[["ISO", "FNumber", "FocalLength35mm", "ExposureTime"]].astype(float).describe(
        percentiles=[0.25, 0.5, 0.75]).T
    t = Table(title=title("Summary stats"), title_justify="left", box=box.SIMPLE_HEAD, show_edge=False, header_style="dim",
              padding=(0, 1), pad_edge=False)
    for c in ["", "median", "middle 50%", "range"]:
        t.add_column(c, justify="right" if c else "left", no_wrap=True)
    fmt = {"ISO": "{:.0f}", "FNumber": "f/{:g}", "FocalLength35mm": "{:.0f}mm"}
    names = {"FNumber": "Aperture", "FocalLength35mm": "Focal (35mm)", "ExposureTime": "Shutter"}
    for name, row in stats.dropna(subset=["50%"]).iterrows():
        f = shutter_label if name == "ExposureTime" else fmt[name].format
        t.add_row(names.get(name, name), Text(f(row["50%"]), style=f"bold {ACCENT}"),
                  f"{f(row['25%'])} – {f(row['75%'])}", Text(f"{f(row['min'])} – {f(row['max'])}", style="dim"))
    combos = (exp.dropna(subset=["FNumber", "ISO"])
              .apply(lambda r: f"{shutter_label(r.ExposureTime)} · f/{r.FNumber:g} · ISO {r.ISO:.0f}", axis=1))
    return section("Exposure summary", [t, ("Exposure triangle", pd.Series(combos, dtype="object"))], top, width)


def _tone_cell(value: str) -> Text:
    return Text(value, style="dim" if value in DEFAULTS else "bold")


RECIPE_SHORT = {"FilmSimulation": "Film sim", "DynamicRange": "DR", "HighlightTone": "H", "ShadowTone": "S",
                "Color": "Color", "Sharpness": "Sharp", "NoiseReduction": "NR", "WhiteBalance": "WB",
                "WBShift": "WB shift", "GrainEffect": "Grain", "GrainSize": "Grain size",
                "ColorChromeEffect": "CC", "ColorChromeFXBlue": "CC Blue", "Clarity": "Clarity"}


def _recipes(fuji: pd.DataFrame, top: int, width: int) -> Panel:
    color = THEME["Fujifilm recipes"]
    cols = [c for c in RECIPE_FIELDS if c in fuji and fuji[c].notna().any()]
    recipes = fuji[cols].fillna("–").astype(str).value_counts().head(top).reset_index(name="Shots")
    # settings identical across every listed recipe say nothing about the differences; note them once instead
    shared = [c for c in cols if len(recipes) > 1 and recipes[c].nunique() == 1 and c != "FilmSimulation"]
    cols = [c for c in cols if c not in shared]
    share = lambda n: Text.assemble((str(n), "bold"), (f" {n / len(fuji):>4.0%}", "dim"))
    cell = lambda c, v: Text(v, style=f"bold {color}") if c == "FilmSimulation" else _tone_cell(v)

    # table needs: every column's widest cell plus padding; fall back to cards when it won't fit
    need = 12 + sum(max(len(RECIPE_SHORT.get(c, c)), recipes[c].str.len().max()) + 2 for c in cols)
    if need <= width - 6:
        t = Table(box=box.SIMPLE_HEAD, show_edge=False, header_style=f"bold {color}", padding=(0, 1), pad_edge=False)
        t.add_column("#", justify="right", style="dim")
        t.add_column("Shots", justify="right", no_wrap=True)
        for c in cols:
            t.add_column(RECIPE_SHORT.get(c, c), no_wrap=True,
                         justify="left" if c in ("FilmSimulation", "WBShift") else "center")
        for i, row in recipes.iterrows():
            t.add_row(str(i + 1), share(row.Shots), *[cell(c, row[c]) for c in cols])
    else:
        t = Table.grid(padding=(0, 1))
        t.add_column(style="dim", justify="right")
        t.add_column()
        for i, row in recipes.iterrows():
            head = Text.assemble(cell("FilmSimulation", row.get("FilmSimulation", "–")), "  ", share(row.Shots))
            rest = Text("  ").join(Text.assemble((RECIPE_SHORT.get(c, c) + " ", "dim"), cell(c, row[c]))
                                   for c in cols if c != "FilmSimulation")
            t.add_row(f"{i + 1}", Group(head, rest))

    body: list[RenderableType] = [title("Favourite recipes"), t]
    if shared:
        body.append(Text.assemble(("All of these use ", "dim"), Text(", ").join(
            Text.assemble((RECIPE_SHORT.get(c, c) + " ", "dim"), (recipes[c].iloc[0], "bold")) for c in shared)))
    body.append(Text("A recipe is one identical combination of every JPEG look setting. Defaults are dimmed.",
                     style="dim italic"))
    if (ct := _crosstab(fuji, color)) is not None:
        body += [Text(""), ct]
    return panel("Fujifilm recipes", Group(*body), width)


def _crosstab(fuji: pd.DataFrame, color: str) -> Table | None:
    """How the film sim choice relates to dynamic range — handy to spot habits per look."""
    if fuji["FilmSimulation"].nunique() < 2:
        return None
    ct = pd.crosstab(fuji["FilmSimulation"], fuji["DynamicRange"].fillna("–"))
    t = Table(title=title("Film sim × Dynamic range"), title_justify="left", box=box.SIMPLE, show_edge=False,
              header_style="dim", padding=(0, 2), pad_edge=False, show_footer=True, footer_style="dim")
    t.add_column("", footer="Total")
    for c in ct.columns:
        t.add_column(str(c), justify="center", footer=str(ct[c].sum()))
    t.add_column("Total", justify="right", style="dim", footer=str(ct.values.sum()))
    peak = ct.values.max()
    for idx, row in ct.iterrows():
        cells = [Text("·", style="grey30") if not v else Text(str(v), style=f"bold {color}" if v == peak else "")
                 for v in row]
        t.add_row(str(idx), *cells, str(row.sum()))
    return t


def _post(df: pd.DataFrame, top: int, width: int) -> Panel | None:
    edited = df["EditedIn"].dropna()
    if edited.empty:
        return None
    items: list[Item] = [("Edited in", edited)]
    lr = df[df["LR_Profile"].notna()]
    if not lr.empty:
        items += [("Lightroom profile", lr["LR_Profile"]),
                  ("Cropped", lr["LR_Cropped"].map({True: "Yes", False: "No"}))]
        sliders = pd.DataFrame({s: lr[f"LR_{s}"].astype(float) for s in LR_SLIDERS if f"LR_{s}" in lr})
        moved = sliders.where(sliders != 0)
        summary = pd.DataFrame({"edits": moved.count(), "mean": moved.mean(),
                                "min": moved.min(), "max": moved.max()}).query("edits > 0")
        t = Table(title=Text.assemble(("Sliders you move", "bold"), (f"  of {len(lr)} Lightroom edits", "dim")), title_justify="left", box=box.SIMPLE_HEAD, show_edge=False,
                  header_style="dim", padding=(0, 1), pad_edge=False)
        for c in ["", "edits", "avg", "range"]:
            t.add_column(c, justify="right" if c else "left", no_wrap=True)
        for name, r in summary.sort_values("edits", ascending=False).iterrows():
            t.add_row(name, str(int(r.edits)), signed(r["mean"], "+.2f"),
                      Text(f"{r['min']:+g} … {r['max']:+g}", style="dim"))
        if summary.empty:
            t.add_row("[dim](none — only crops/profile)", "", "", "")
        items.append(t)
    return section("Post-processing", items, top, width)


def _takeaways_panel(df, exp, fuji, width: int) -> Panel | None:
    lines = takeaways(df, exp, fuji)
    if not lines:
        return None
    color = THEME["Takeaways"]
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style=color, no_wrap=True)
    grid.add_column()  # wraps with a hanging indent under the bullet
    for line in lines:
        grid.add_row("›", line)
    return panel("Takeaways", grid, width)


def _mode(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return None, 0, 0
    counts = s.value_counts()
    return counts.index[0], counts.iloc[0], len(s)


def takeaways(df, exp, fuji) -> list[str]:
    out = []
    if (m := _mode(exp["ExposureProgram"]))[0]:
        out.append(f"You shoot [bold cyan]{m[0]}[/] {m[1] / m[2]:.0%} of the time.")
    if (m := _mode(exp["MeteringMode"]))[0]:
        out.append(f"Favourite metering: [bold cyan]{m[0]}[/] ({m[1]}/{m[2]}).")
    if (iso := exp["ISO"].dropna().astype(float)).any():
        out.append(f"Typical ISO [bold cyan]{iso.median():g}[/]; {(iso <= 400).sum()}/{len(iso)} shots at ISO ≤400.")
    if (f := exp["FNumber"].dropna().astype(float)).any():
        line = f"Median aperture [bold cyan]f/{f.median():g}[/]; {(f >= 8).sum()}/{len(f)} shots at f/8 or smaller"
        if (f > 11).any():
            line += f" — {(f > 11).sum()} past f/11, where diffraction softens APS-C images"
        out.append(line + ".")
    if (fl := exp["FocalLength35mm"].dropna().astype(float)).any():
        out.append(f"Median focal length [bold cyan]{fl.median():g}mm[/] equiv. (range {fl.min():g}–{fl.max():g}mm).")
    slow = exp[exp["ExposureTime"].astype(float) > 1 / exp["FocalLength35mm"].astype(float).fillna(50)]
    if len(slow):
        out.append(f"{len(slow)}/{len(exp)} shots slower than 1/focal-length (handheld-shake risk).")
    if (m := _mode(fuji["FilmSimulation"]))[0]:
        out.append(f"Go-to film simulation: [bold cyan]{m[0]}[/] ({m[1]}/{m[2]}).")
    shifted = fuji[(fuji["WBShiftRed"].fillna(0) != 0) | (fuji.get("WBShiftBlue", 0) != 0)]
    if len(shifted):
        warmth = (shifted["WBShiftRed"] - shifted["WBShiftBlue"]).astype(float).sum()
        out.append(f"{len(shifted)}/{len(fuji)} shots use a WB shift — you lean [bold cyan]{'warm' if warmth > 0 else 'cool'}[/].")
    if (n := (~df["HasExposure"]).sum()):
        out.append(f"{n} files had camera metadata stripped by an editor — "
                   "point camnerd at the original out-of-camera JPEGs for complete stats.")
    return out
