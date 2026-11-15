"""Frequency analysis of camera settings, rendered with rich."""

import numpy as np
import pandas as pd
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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

BAR_WIDTH = 20
ACCENT = "cyan"


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


def freq_table(title: str, series: pd.Series, top: int) -> Table | None:
    series = series.dropna()
    if series.empty:
        return None
    counts = series.value_counts(sort=not isinstance(series.dtype, pd.CategoricalDtype))
    if isinstance(series.dtype, pd.CategoricalDtype):
        counts = counts[counts > 0]  # keep natural order (e.g. ISO low → high)
    else:
        counts = counts.head(top)
    n, peak = len(series), counts.max()

    t = Table(title=f"[bold]{title}[/] [dim](n={n})[/]", title_justify="left",
              show_header=False, box=None, padding=(0, 1))
    t.add_column(no_wrap=True)
    t.add_column(no_wrap=True)
    t.add_column(justify="right")
    t.add_column(justify="right", style="dim")
    for value, cnt in counts.items():
        bar = "█" * max(1, round(BAR_WIDTH * cnt / peak))
        t.add_row(str(value), f"[{ACCENT}]{bar}[/]", str(cnt), f"{cnt / n:.0%}")
    return t


def section(console: Console, title: str, tables: list[Table | None]):
    tables = [t for t in tables if t is not None]
    if tables:
        console.print(Panel(Columns(tables, padding=(1, 4)), title=f"[bold]{title}", title_align="left"))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["ExposureTime", "FNumber", "ISO", "FocalLength35mm", "HasFujiSettings", "WBShiftRed",
                "EditedIn", "LR_Profile", "DateTimeOriginal", *RECIPE_FIELDS]:
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


def render(df: pd.DataFrame, top: int = 8, console: Console | None = None):
    console = console or Console()
    df = _add_derived(df)
    exp = df[df["HasExposure"]]
    fuji = df[df["HasFujiSettings"]]

    console.rule(f"[bold]camnerd · {len(df)} images")
    console.print(f"{len(exp)} with exposure data · {len(fuji)} with Fujifilm JPEG settings")
    stripped = df.loc[~df["HasExposure"], "File"].tolist()
    if stripped:
        console.print(f"[yellow]⚠ camera EXIF stripped by an editor:[/] {', '.join(stripped)}")

    section(console, "Gear", [freq_table("Body", df["Model"], top), freq_table("Lens", df["LensModel"], top)])

    section(console, "Exposure", [
        freq_table("Mode", exp["ExposureProgram"], top),
        freq_table("Metering", exp["MeteringMode"], top),
        freq_table("Shutter (nearest stop)", exp["Shutter"], top),
        freq_table("Aperture", exp["ApertureBucket"], top),
        freq_table("ISO", exp["ISOBucket"], top),
        freq_table("Exp. compensation", exp["ExposureCompensation"].map(lambda v: f"{v:+g} EV" if v else "0 EV"), top),
    ])

    if not exp.empty:
        stats = exp[["ISO", "FNumber", "FocalLength35mm", "ExposureTime"]].astype(float).describe(
            percentiles=[0.25, 0.5, 0.75]).T
        t = Table(title="[bold]Summary stats", title_justify="left", box=None)
        for c in ["", "median", "25%–75%", "min – max"]:
            t.add_column(c, justify="right" if c else "left")
        fmt = {"ISO": "{:.0f}", "FNumber": "f/{:g}", "FocalLength35mm": "{:.0f}mm"}
        for name, row in stats.iterrows():
            f = (lambda v: shutter_label(v)) if name == "ExposureTime" else fmt[name].format
            label = {"FNumber": "Aperture", "FocalLength35mm": "Focal (35mm eq.)", "ExposureTime": "Shutter"}.get(name, name)
            t.add_row(label, f(row["50%"]), f"{f(row['25%'])} – {f(row['75%'])}", f"{f(row['min'])} – {f(row['max'])}")
        combos = (exp.dropna(subset=["FNumber", "ISO"])
                  .assign(Combo=lambda d: d.apply(lambda r: f"{shutter_label(r.ExposureTime)} · f/{r.FNumber:g} · ISO {r.ISO:.0f}", axis=1)))
        section(console, "Exposure summary", [t, freq_table("Exposure triangle", combos["Combo"], top)])

    section(console, "Framing & timing", [
        freq_table("Focal length (35mm eq.)", exp["FocalBucket"], top),
        freq_table("Time of day", df["TimeOfDay"], top),
        freq_table("Month", df["Month"], top),
    ])

    if not fuji.empty:
        section(console, "Fujifilm JPEG settings",
                [freq_table(f, fuji[f], top) for f in RECIPE_FIELDS if f in fuji])
        section(console, "Focus & drive",
                [freq_table(f, fuji[f], top) for f in
                 ["FocusMode", "AFAreaMode", "DriveMode", "ShutterType", "ImageStabilization"] if f in fuji])
        _render_recipes(console, fuji, top)
        _render_crosstab(console, fuji)

    _render_post(console, df, top)

    console.print(Panel("\n".join(f"• {line}" for line in takeaways(df, exp, fuji)),
                        title="[bold]Takeaways", title_align="left", border_style=ACCENT))


def _render_recipes(console, fuji: pd.DataFrame, top: int):
    cols = [c for c in RECIPE_FIELDS if c in fuji and fuji[c].notna().any()]
    recipes = (fuji[cols].fillna("–").astype(str).value_counts().head(top).reset_index(name="Shots"))
    t = Table(title="[bold]Favourite recipes[/] [dim](identical combo of all JPEG look settings)",
              title_justify="left", header_style="bold")
    t.add_column("#", justify="right")
    t.add_column("Shots", justify="right")
    short = {"FilmSimulation": "Film sim", "DynamicRange": "DR", "HighlightTone": "H", "ShadowTone": "S",
             "Color": "Color", "Sharpness": "Sharp", "NoiseReduction": "NR", "WhiteBalance": "WB",
             "WBShift": "WB shift", "GrainEffect": "Grain", "GrainSize": "Grain size",
             "ColorChromeEffect": "CC", "ColorChromeFXBlue": "CC Blue", "Clarity": "Clarity"}
    for c in cols:
        t.add_column(short.get(c, c), no_wrap=True)
    for i, row in recipes.iterrows():
        t.add_row(str(i + 1), f"{row.Shots} ({row.Shots / len(fuji):.0%})", *[row[c] for c in cols])
    console.print(t)


def _render_crosstab(console, fuji: pd.DataFrame):
    """How the film sim choice relates to dynamic range — handy to spot habits per look."""
    if fuji["FilmSimulation"].nunique() < 2:
        return
    ct = pd.crosstab(fuji["FilmSimulation"], fuji["DynamicRange"].fillna("–"), margins=True, margins_name="Total")
    t = Table(title="[bold]Film sim × Dynamic range", title_justify="left", header_style="bold")
    t.add_column("")
    for c in ct.columns:
        t.add_column(str(c), justify="right")
    for idx, row in ct.iterrows():
        t.add_row(str(idx), *[str(v) if v else "[dim]·" for v in row])
    console.print(t)


def _render_post(console, df: pd.DataFrame, top: int):
    edited = df["EditedIn"].dropna()
    if edited.empty:
        return
    tables = [freq_table("Edited in", edited, top)]
    lr = df[df["LR_Profile"].notna()]
    if not lr.empty:
        tables.append(freq_table("Lightroom profile", lr["LR_Profile"], top))
        tables.append(freq_table("Cropped", lr["LR_Cropped"].map({True: "Yes", False: "No"}), top))
        sliders = pd.DataFrame({s: lr[f"LR_{s}"].astype(float) for s in LR_SLIDERS if f"LR_{s}" in lr})
        moved = sliders.where(sliders != 0)
        summary = pd.DataFrame({"edits": moved.count(), "mean": moved.mean(),
                                "min": moved.min(), "max": moved.max()}).query("edits > 0")
        t = Table(title=f"[bold]Sliders you move[/] [dim](of {len(lr)} LR edits)", title_justify="left", box=None)
        for c in ["", "edits", "avg", "range"]:
            t.add_column(c, justify="right" if c else "left")
        for name, r in summary.sort_values("edits", ascending=False).iterrows():
            t.add_row(name, str(int(r.edits)), f"{r['mean']:+.2f}", f"{r['min']:+g} … {r['max']:+g}")
        if summary.empty:
            t.add_row("[dim](none — only crops/profile)", "", "", "")
        tables.append(t)
    section(console, "Post-processing", tables)


def _mode(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return None, 0, 0
    counts = s.value_counts()
    return counts.index[0], counts.iloc[0], len(s)


def takeaways(df, exp, fuji) -> list[str]:
    out = []
    if (m := _mode(exp["ExposureProgram"]))[0]:
        out.append(f"You shoot [bold]{m[0]}[/] {m[1] / m[2]:.0%} of the time.")
    if (m := _mode(exp["MeteringMode"]))[0]:
        out.append(f"Favourite metering: [bold]{m[0]}[/] ({m[1]}/{m[2]}).")
    if (iso := exp["ISO"].dropna().astype(float)).any():
        out.append(f"Typical ISO [bold]{iso.median():g}[/]; {(iso <= 400).sum()}/{len(iso)} shots at ISO ≤400.")
    if (f := exp["FNumber"].dropna().astype(float)).any():
        line = f"Median aperture [bold]f/{f.median():g}[/]; {(f >= 8).sum()}/{len(f)} shots at f/8 or smaller"
        if (f > 11).any():
            line += f" — {(f > 11).sum()} past f/11, where diffraction softens APS-C images"
        out.append(line + ".")
    if (fl := exp["FocalLength35mm"].dropna().astype(float)).any():
        out.append(f"Median focal length [bold]{fl.median():g}mm[/] equiv. (range {fl.min():g}–{fl.max():g}mm).")
    slow = exp[exp["ExposureTime"].astype(float) > 1 / exp["FocalLength35mm"].astype(float).fillna(50)]
    if len(slow):
        out.append(f"{len(slow)}/{len(exp)} shots slower than 1/focal-length (handheld-shake risk).")
    if (m := _mode(fuji["FilmSimulation"]))[0]:
        out.append(f"Go-to film simulation: [bold]{m[0]}[/] ({m[1]}/{m[2]}).")
    shifted = fuji[(fuji["WBShiftRed"].fillna(0) != 0) | (fuji.get("WBShiftBlue", 0) != 0)]
    if len(shifted):
        warmth = (shifted["WBShiftRed"] - shifted["WBShiftBlue"]).astype(float).sum()
        out.append(f"{len(shifted)}/{len(fuji)} shots use a WB shift — you lean [bold]{'warm' if warmth > 0 else 'cool'}[/].")
    if (n := (~df["HasExposure"]).sum()):
        out.append(f"{n} files had camera metadata stripped by an editor — "
                   "point camnerd at the original out-of-camera JPEGs for complete stats.")
    return out
