"""Input validation for the property form and the uploaded images."""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from config import Config
from utils.helpers import format_number, split_list

PROPERTY_TYPES = ["Apartment", "Villa", "House", "Townhouse", "Penthouse",
                  "Studio", "Plot / Land", "Commercial", "Office", "Other"]
MAX_FEATURES = 8


def _one_line(value: str | None, max_len: int) -> str:
    return " ".join((value or "").split())[:max_len]


def _int_field(raw: str | None, label: str, errors: list[str], lo: int = 0, hi: int = 50) -> int:
    raw = (raw or "").strip()
    if raw == "":
        errors.append(f"{label} is required.")
        return 0
    if not re.fullmatch(r"\d+", raw) or not lo <= int(raw) <= hi:
        errors.append(f"{label} must be a whole number between {lo} and {hi}.")
        return 0
    return int(raw)


def validate_property_form(form) -> tuple[dict, list[str]]:
    """Validate and clean the text fields. Returns (clean_data, error_messages)."""
    errors: list[str] = []
    data = {
        "name": _one_line(form.get("property_name"), 80),
        "location": _one_line(form.get("location"), 100),
        "price": _one_line(form.get("price"), 40),
        "cta": _one_line(form.get("cta"), 60),
    }
    for key, label in (("name", "Property name"), ("location", "Property location"),
                       ("price", "Property price"), ("cta", "Call-to-action text")):
        if not data[key]:
            errors.append(f"{label} is required.")

    ptype = _one_line(form.get("property_type"), 30)
    if ptype not in PROPERTY_TYPES:
        errors.append("Choose a property type from the list.")
    data["property_type"] = ptype

    data["bedrooms"] = _int_field(form.get("bedrooms"), "Bedrooms", errors)
    data["bathrooms"] = _int_field(form.get("bathrooms"), "Bathrooms", errors)

    area_raw = (form.get("area") or "").replace(",", "").strip()
    try:
        area = float(area_raw)
        if not 0 < area <= 10_000_000:
            raise ValueError
        data["area"] = format_number(area)
    except ValueError:
        errors.append("Property area must be a positive number (sq. ft.).")
        data["area"] = ""

    features = [f[:50] for f in split_list(form.get("features"))][:MAX_FEATURES]
    if not features:
        errors.append("Add at least one key feature or amenity.")
    data["features"] = features

    contact_lines = [" ".join(l.split()) for l in (form.get("contact") or "").splitlines() if l.strip()]
    if not contact_lines:
        errors.append("Contact information is required.")
    elif len(contact_lines) > 4 or any(len(l) > 80 for l in contact_lines):
        errors.append("Contact information can have up to 4 lines of 80 characters each.")
    data["contact"] = "\n".join(l[:80] for l in contact_lines[:4])
    return data, errors


def process_uploaded_images(files, dest_dir: Path) -> tuple[list[Path], list[str]]:
    """Validate uploads, normalise them to RGB JPEGs in dest_dir.

    Returns (paths, errors). When errors is non-empty, paths is empty.
    """
    errors: list[str] = []
    files = [f for f in files if f and f.filename]
    if len(files) < Config.MIN_IMAGES:
        errors.append(f"Upload at least {Config.MIN_IMAGES} images (you added {len(files)}).")
    if len(files) > Config.MAX_IMAGES:
        errors.append(f"Upload at most {Config.MAX_IMAGES} images (you added {len(files)}).")
    if errors:
        return [], errors

    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for idx, f in enumerate(files, start=1):
        name = f.filename
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in Config.ALLOWED_IMAGE_EXTENSIONS:
            errors.append(f"'{name}': only JPG, JPEG and PNG files are supported.")
            continue
        raw = f.read()
        if not raw:
            errors.append(f"'{name}': the file is empty.")
            continue
        if len(raw) > Config.MAX_IMAGE_MB * 1024 * 1024:
            errors.append(f"'{name}': larger than {Config.MAX_IMAGE_MB} MB.")
            continue
        try:
            with Image.open(io.BytesIO(raw)) as probe:
                probe.verify()  # detects truncated/corrupt files
            img = Image.open(io.BytesIO(raw))
            if img.format not in ("JPEG", "PNG"):
                raise ValueError("wrong format")
            img = ImageOps.exif_transpose(img)
            if min(img.size) < Config.MIN_IMAGE_SIDE:
                errors.append(f"'{name}': too small ({img.width}x{img.height}). "
                              f"The shortest side must be at least {Config.MIN_IMAGE_SIDE}px.")
                continue
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.getchannel("A"))
                img = bg
            else:
                img = img.convert("RGB")
            img.thumbnail((2400, 2400), Image.LANCZOS)
            out = dest_dir / f"img_{idx:02d}.jpg"
            img.save(out, "JPEG", quality=92)
            saved.append(out)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, SyntaxError):
            errors.append(f"'{name}': not a valid or readable JPG/PNG image.")
    if errors:
        return [], errors
    return saved, []
