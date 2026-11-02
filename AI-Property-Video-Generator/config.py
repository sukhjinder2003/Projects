"""Central configuration. All tunables live here so other modules stay clean."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    BASE_DIR = BASE_DIR
    UPLOAD_DIR = BASE_DIR / "uploads"
    OUTPUT_DIR = BASE_DIR / "outputs"
    MUSIC_DIR = BASE_DIR / "static" / "music"
    MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}

    # ---- Image upload rules -------------------------------------------------
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
    MIN_IMAGES = 4
    MAX_IMAGES = 8
    MAX_IMAGE_MB = 10
    MIN_IMAGE_SIDE = 400  # pixels (shortest side)
    MAX_CONTENT_LENGTH = (MAX_IMAGES * MAX_IMAGE_MB + 2) * 1024 * 1024

    # ---- Video settings -----------------------------------------------------
    # aspect ratio -> (width, height). All dimensions are even (H.264 needs it).
    ASPECT_RATIOS = {
        "16:9": (1280, 720),   # YouTube
        "9:16": (720, 1280),   # Reels / Shorts
        "1:1": (960, 960),     # Feed posts
    }
    FPS = int(os.getenv("VIDEO_FPS", "24"))
    MAX_CONCURRENT_RENDERS = 1
    FILE_TTL_HOURS = 6  # generated videos older than this are deleted

    # ---- Optional LLM -------------------------------------------------------
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip()
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))

    # ---- Server -------------------------------------------------------------
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", "5000"))
