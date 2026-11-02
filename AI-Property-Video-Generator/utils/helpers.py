"""Small, dependency-free helper functions."""
import re
import shutil
import time
from pathlib import Path

from config import Config


def ensure_dirs() -> None:
    """Create the working folders if they do not exist yet."""
    for folder in (Config.UPLOAD_DIR, Config.OUTPUT_DIR, Config.MUSIC_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def cleanup_old_files(max_age_hours: float = Config.FILE_TTL_HOURS) -> None:
    """Delete generated videos and leftover upload folders older than the TTL."""
    cutoff = time.time() - max_age_hours * 3600
    for root in (Config.UPLOAD_DIR, Config.OUTPUT_DIR):
        if not root.exists():
            continue
        for item in root.iterdir():
            if item.name == ".gitkeep":
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    shutil.rmtree(item) if item.is_dir() else item.unlink()
            except OSError:
                pass  # file in use or already removed - ignore


def list_music_tracks() -> list[dict]:
    """Return the royalty-free tracks the user has placed in static/music."""
    if not Config.MUSIC_DIR.exists():
        return []
    tracks = []
    for f in sorted(Config.MUSIC_DIR.iterdir()):
        if f.suffix.lower() in Config.MUSIC_EXTENSIONS:
            tracks.append({"file": f.name, "label": f.stem.replace("_", " ").replace("-", " ").title()})
    return tracks


def slugify(text: str, fallback: str = "property-video") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:60] or fallback


def format_number(value: float) -> str:
    """1850 -> '1,850', 1850.5 -> '1,850.5'."""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def split_list(raw: str) -> list[str]:
    """Split a free-text list on newlines, commas, semicolons and bullets."""
    parts = re.split(r"[\n,;•]+", raw or "")
    return [" ".join(p.split()) for p in parts if p.strip()]
