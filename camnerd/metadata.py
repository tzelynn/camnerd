"""Read camera settings from JPEGs into a flat dict / pandas DataFrame."""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

import exifread
import pandas as pd
from PIL import Image

from camnerd import fuji

JPEG_EXTS = {".jpg", ".jpeg"}

NS = {
    "crs": "http://ns.adobe.com/camera-raw-settings/1.0/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "tiff": "http://ns.adobe.com/tiff/1.0/",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "exifEX": "http://cipa.jp/exif/1.0/",
    "aux": "http://ns.adobe.com/exif/1.0/aux/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}
_PREFIX = {uri: prefix for prefix, uri in NS.items()}

# Lightroom / Camera Raw develop sliders worth tracking
LR_SLIDERS = [
    "Exposure2012", "Contrast2012", "Highlights2012", "Shadows2012", "Whites2012",
    "Blacks2012", "Texture", "Clarity2012", "Dehaze", "Vibrance", "Saturation",
    "IncrementalTemperature", "IncrementalTint", "GrainAmount", "PostCropVignetteAmount",
]

METERING_NAMES = {"Pattern": "Multi-segment", "CenterWeightedAverage": "Center-weighted"}

# exifread is chatty about tags it can't decode
logging.getLogger("exifread").setLevel(logging.ERROR)


def _num(tag) -> float | None:
    if tag is None or not tag.values:
        return None
    v = tag.values[0]
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _str(tag) -> str | None:
    if tag is None:
        return None
    s = str(tag.printable).strip()
    return s or None


def read_xmp(path: Path) -> dict[str, str]:
    """Flatten XMP into {"prefix:Name": value}, covering both attribute and element forms."""
    with Image.open(path) as im:
        raw = im.info.get("xmp")
    if not raw:
        return {}
    try:
        root = ET.fromstring(raw.strip(b"\x00").decode("utf-8", "replace").strip())
    except ET.ParseError:
        return {}

    def qname(clark: str) -> str | None:
        uri, _, local = clark[1:].partition("}")
        return f"{_PREFIX[uri]}:{local}" if uri in _PREFIX else None

    out = {}
    for el in root.iter():
        for k, v in el.attrib.items():
            if (q := qname(k)) and q not in out:
                out[q] = v
        if (q := qname(el.tag)) and q not in out:
            # <exif:ISOSpeedRatings><rdf:Seq><rdf:li>400</rdf:li>... -> first li
            text = (el.text or "").strip() or next(
                ((li.text or "").strip() for li in el.iter(f"{{{NS['rdf']}}}li")), ""
            )
            if text:
                out[q] = text
    return out


def _xmp_float(xmp: dict, key: str) -> float | None:
    v = xmp.get(key)
    if v is None:
        return None
    try:
        if "/" in v:
            n, d = v.split("/")
            return float(n) / float(d)
        return float(v)
    except (ValueError, ZeroDivisionError):
        return None


def _parse_date(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    # EXIF uses "2025:10:21 12:34:19"; XMP uses ISO 8601 (local time, drop any offset)
    ts = pd.to_datetime(s[:19], format="%Y:%m:%d %H:%M:%S", errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(s[:19], format="ISO8601", errors="coerce")
    return None if pd.isna(ts) else ts


def read_metadata(path: str | Path) -> dict:
    path = Path(path)
    with path.open("rb") as fh:
        tags = exifread.process_file(fh, details=True)
    xmp = read_xmp(path)
    g = tags.get

    software = _str(g("Image Software")) or xmp.get("xmp:CreatorTool")
    row = {
        "File": path.name,
        "Path": str(path),
        "Make": _str(g("Image Make")) or xmp.get("tiff:Make"),
        "Model": _str(g("Image Model")) or xmp.get("tiff:Model"),
        "LensModel": _str(g("EXIF LensModel")) or xmp.get("exifEX:LensModel") or xmp.get("aux:Lens"),
        "Software": software,
        "DateTimeOriginal": _parse_date(
            _str(g("EXIF DateTimeOriginal")) or xmp.get("exif:DateTimeOriginal") or xmp.get("photoshop:DateCreated")
        ),
        "ExposureTime": _num(g("EXIF ExposureTime")) or _xmp_float(xmp, "exif:ExposureTime"),
        "FNumber": _num(g("EXIF FNumber")) or _xmp_float(xmp, "exif:FNumber"),
        "ISO": _num(g("EXIF ISOSpeedRatings")) or _xmp_float(xmp, "exif:ISOSpeedRatings"),
        "FocalLength": _num(g("EXIF FocalLength")) or _xmp_float(xmp, "exif:FocalLength"),
        "FocalLength35mm": _num(g("EXIF FocalLengthIn35mmFilm")) or _xmp_float(xmp, "exif:FocalLengthIn35mmFilm"),
        "ExposureCompensation": _num(g("EXIF ExposureBiasValue")),
        "ExposureProgram": _str(g("EXIF ExposureProgram")),
        "MeteringMode": METERING_NAMES.get(m := _str(g("EXIF MeteringMode")), m),
    }

    maker = {t.tag: t.values for k, t in tags.items() if k.startswith("MakerNote ")}
    if (row["Make"] or "").upper().startswith("FUJIFILM") and maker:
        row.update(fuji.decode(maker))
    row["HasFujiSettings"] = "FilmSimulation" in row

    if any(k.startswith("crs:") for k in xmp):
        row["EditedIn"] = "Lightroom"
        row["LR_Profile"] = xmp.get("crs:CameraProfile")
        row["LR_Cropped"] = xmp.get("crs:HasCrop") == "True"
        for s in LR_SLIDERS:
            row["LR_" + s.removesuffix("2012")] = _xmp_float(xmp, f"crs:{s}")
    elif software and not software.lower().startswith("digital camera"):
        row["EditedIn"] = software
    return row


def find_images(paths: list[Path], recursive: bool = True):
    for p in paths:
        if p.is_file():
            yield p
        elif p.is_dir():
            files = p.rglob("*") if recursive else p.iterdir()
            yield from sorted(f for f in files if f.suffix.lower() in JPEG_EXTS and not f.name.startswith("."))


def scan(paths: list[Path], recursive: bool = True) -> pd.DataFrame:
    rows = []
    for f in find_images(paths, recursive):
        try:
            rows.append(read_metadata(f))
        except Exception as e:  # keep going on corrupt/odd files
            logging.warning("skipping %s: %s", f, e)
    return pd.DataFrame(rows)


def load(paths: list[Path], recursive: bool = True) -> pd.DataFrame:
    """Scan image folders, or reload a CSV/JSON previously written by `camnerd extract`."""
    if len(paths) == 1 and paths[0].suffix.lower() in (".csv", ".json"):
        p = paths[0]
        if p.suffix.lower() == ".json":
            df = pd.read_json(p, dtype=False)  # values are already typed in JSON
        else:
            # keep signed labels like "+2" / "-1" as text, as written
            df = pd.read_csv(p, dtype=str)
            for col in df.columns:
                if set(df[col].dropna()) <= {"True", "False"}:
                    df[col] = df[col].map({"True": True, "False": False})
                    continue
                conv = pd.to_numeric(df[col], errors="coerce")
                if col not in fuji.TEXT_COLUMNS and conv.notna().sum() == df[col].notna().sum():
                    df[col] = conv
        df["DateTimeOriginal"] = pd.to_datetime(df["DateTimeOriginal"], errors="coerce")
        return df
    return scan(paths, recursive)
