"""Decode Fujifilm maker-note values into the names shown in the camera menus.

exifread parses the maker-note IFD for us but only names a handful of the older
tags; these tables (from ExifTool's FujiFilm.pm) cover the modern JPEG settings.
"""

FILM_MODE = {
    0x000: "Provia/Standard", 0x100: "Studio Portrait", 0x110: "Studio Portrait Enh. Saturation",
    0x120: "Astia/Soft", 0x130: "Studio Portrait Inc. Sharpness", 0x200: "Velvia/Vivid",
    0x300: "Studio Portrait Ex", 0x400: "Velvia/Vivid", 0x500: "Pro Neg. Std",
    0x501: "Pro Neg. Hi", 0x600: "Classic Chrome", 0x700: "Eterna",
    0x800: "Classic Negative", 0x900: "Eterna Bleach Bypass", 0xA00: "Nostalgic Neg",
    0xB00: "Reala Ace",
}
# Tag 0x1003 doubles as the Color setting and the monochrome film sims
COLOR = {
    0x000: "0", 0x080: "+1", 0x100: "+2", 0x0C0: "+3", 0x0E0: "+4",
    0x180: "-1", 0x400: "-2", 0x4C0: "-3", 0x4E0: "-4", 0x200: "Low", 0x8000: "Film Simulation",
}
MONOCHROME = {
    0x300: "Monochrome", 0x301: "Monochrome+R", 0x302: "Monochrome+Ye", 0x303: "Monochrome+G",
    0x310: "Sepia", 0x500: "Acros", 0x501: "Acros+R", 0x502: "Acros+Ye", 0x503: "Acros+G",
}
SHARPNESS = {
    0x00: "-4", 0x01: "-3", 0x02: "-2", 0x82: "-1", 0x03: "0", 0x84: "+1",
    0x04: "+2", 0x05: "+3", 0x06: "+4", 0x8000: "Film Simulation", 0xFFFF: "n/a",
}
NOISE_REDUCTION = {
    0x000: "0", 0x180: "+1", 0x100: "+2", 0x1C0: "+3", 0x1E0: "+4",
    0x280: "-1", 0x200: "-2", 0x2C0: "-3", 0x2E0: "-4",
}
WHITE_BALANCE = {
    0x000: "Auto", 0x001: "Auto (white priority)", 0x002: "Auto (ambience priority)",
    0x100: "Daylight", 0x200: "Cloudy", 0x300: "Fluorescent (daylight)",
    0x301: "Fluorescent (warm white)", 0x302: "Fluorescent (cool white)",
    0x303: "Fluorescent", 0x304: "Fluorescent", 0x400: "Incandescent", 0x500: "Flash",
    0x600: "Underwater", 0xF00: "Custom", 0xF01: "Custom 2", 0xF02: "Custom 3",
    0xF03: "Custom 4", 0xF04: "Custom 5", 0xFF0: "Kelvin",
}
STRENGTH = {0: "Off", 16: "Weak", 32: "Weak", 48: "Strong", 64: "Strong"}
GRAIN_SIZE = {0: "Off", 16: "Small", 32: "Large"}
DR_SETTING = {0x0000: "Auto", 0x0001: "Manual", 0x0100: "DR100", 0x0200: "DR200",
              0x0201: "DR400", 0x8000: "Film Simulation"}
SHUTTER_TYPE = {0: "Mechanical", 1: "Electronic", 2: "Electronic (long)", 3: "Electronic front curtain"}
FOCUS_MODE = {0: "Manual", 1: "AF-S", 2: "AF-C"}
AF_AREA = {0: "Single point", 1: "Zone", 2: "Wide/Tracking"}
DRIVE = {0: "Single", 1: "Continuous Low", 2: "Continuous High"}

# Decoded settings that are labels ("+2", "-1", "0"), not numbers
TEXT_COLUMNS = {"Color", "HighlightTone", "ShadowTone", "Sharpness", "NoiseReduction", "Clarity"}


def _lookup(table, val):
    return table.get(val, f"0x{val:x}")


def _step(x: float) -> str:
    x = int(x) if x == int(x) else x
    return f"{x:+g}" if x else "0"


def decode(raw: dict[int, list]) -> dict:
    """`raw` maps maker-note tag id -> list of values (as exifread gives them)."""
    t = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in raw.items()}
    out = {}

    sat, film = t.get(0x1003), t.get(0x1401)
    if sat in MONOCHROME:
        out["FilmSimulation"] = MONOCHROME[sat]
    elif film is not None:
        out["FilmSimulation"] = _lookup(FILM_MODE, film)
    if sat is not None and sat not in MONOCHROME:
        out["Color"] = _lookup(COLOR, sat)

    # Highlight/Shadow tone are stored as -16 per step (so -32 == +2)
    if 0x1041 in t:
        out["HighlightTone"] = _step(-t[0x1041] / 16)
    if 0x1040 in t:
        out["ShadowTone"] = _step(-t[0x1040] / 16)
    if 0x1001 in t:
        out["Sharpness"] = _lookup(SHARPNESS, t[0x1001])
    if 0x100E in t:
        out["NoiseReduction"] = _lookup(NOISE_REDUCTION, t[0x100E])
    if 0x100F in t:
        out["Clarity"] = _step(t[0x100F] / 1000)

    if 0x1047 in t:
        out["GrainEffect"] = STRENGTH.get(t[0x1047], str(t[0x1047]))
    if 0x104C in t:
        out["GrainSize"] = GRAIN_SIZE.get(t[0x104C], str(t[0x104C]))
    if 0x1048 in t:
        out["ColorChromeEffect"] = STRENGTH.get(t[0x1048], str(t[0x1048]))
    if 0x104E in t:
        out["ColorChromeFXBlue"] = STRENGTH.get(t[0x104E], str(t[0x104E]))

    if 0x1002 in t:
        out["WhiteBalance"] = _lookup(WHITE_BALANCE, t[0x1002])
        if out["WhiteBalance"] == "Kelvin" and 0x1005 in t:
            out["ColorTemperatureK"] = t[0x1005]
    shift = t.get(0x100A)
    if isinstance(shift, list) and len(shift) == 2:
        r, b = shift
        # Newer bodies store the shift multiplied by 20
        if all(v % 20 == 0 for v in (r, b)) and any(abs(v) >= 10 for v in (r, b)):
            r, b = r // 20, b // 20
        out["WBShiftRed"], out["WBShiftBlue"] = r, b

    if 0x1402 in t:
        dr = _lookup(DR_SETTING, t[0x1402])
        if dr == "Manual" and t.get(0x1403):
            dr = f"DR{t[0x1403]}"
        out["DynamicRange"] = dr

    if 0x1050 in t:
        out["ShutterType"] = SHUTTER_TYPE.get(t[0x1050], str(t[0x1050]))
    if 0x102D in t:
        fs = t[0x102D]
        out["FocusMode"] = FOCUS_MODE.get(fs & 0xF, str(fs & 0xF))
        if fs & 0xF:  # AF area is meaningless in manual focus
            out["AFAreaMode"] = AF_AREA.get((fs >> 12) & 0xF, str((fs >> 12) & 0xF))
    elif 0x1021 in t:
        out["FocusMode"] = {0: "Auto", 1: "Manual"}.get(t[0x1021], str(t[0x1021]))
    if 0x1103 in t:
        out["DriveMode"] = DRIVE.get(t[0x1103] & 0xFF, str(t[0x1103] & 0xFF))
    if isinstance(t.get(0x1422), list):
        out["ImageStabilization"] = "On" if t[0x1422][0] else "Off"
    if 0x1446 in t:
        out["FlickerReduction"] = "On" if t[0x1446] & 1 else "Off"
    return out
