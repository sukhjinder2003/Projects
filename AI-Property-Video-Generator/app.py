"""Flask application: routes, background render jobs and JSON API."""
from __future__ import annotations

import logging
import re
import shutil
import threading
import time
import uuid

from flask import Flask, abort, jsonify, render_template, request, send_file

from config import Config
from services.script_generator import generate_script, llm_available
from services.validators import PROPERTY_TYPES, process_uploaded_images, validate_property_form
from services.video_generator import STYLES, VideoGenerationError, ffmpeg_available, generate_video
from utils.helpers import cleanup_old_files, ensure_dirs, list_music_tracks, slugify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
ensure_dirs()

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
RENDER_SLOTS = threading.Semaphore(Config.MAX_CONCURRENT_RENDERS)
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _update(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def _get_job(job_id: str) -> dict:
    if not JOB_ID_RE.match(job_id):
        abort(404)
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        abort(404)
    return job


# --------------------------------------------------------------------------- #
# Background worker
# --------------------------------------------------------------------------- #
def run_job(job_id, image_paths, prop, style, aspect, music_path, use_ai) -> None:
    upload_dir = Config.UPLOAD_DIR / job_id
    try:
        _update(job_id, status="queued", message="Waiting for a free render slot…", progress=0.01)
        with RENDER_SLOTS:
            _update(job_id, status="running", message="Writing the script…", progress=0.02)
            script = generate_script(prop, len(image_paths), use_ai=use_ai)
            _update(job_id, script=script)
            out = Config.OUTPUT_DIR / f"{job_id}.mp4"
            generate_video(
                image_paths, prop, script, style, aspect, out, music_path=music_path,
                progress=lambda p, m: _update(job_id, progress=round(p, 3), message=m),
            )
        _update(job_id, status="done", progress=1.0, message="Your video is ready.",
                filename=f"{slugify(prop['name'])}-{aspect.replace(':', 'x')}.mp4")
    except VideoGenerationError as exc:
        log.warning("Render failed for %s: %s", job_id, exc)
        _update(job_id, status="error", message=str(exc))
    except Exception:  # never let a worker thread die silently
        log.exception("Unexpected render error for %s", job_id)
        _update(job_id, status="error",
                message="Something went wrong while rendering. Check the server console for details.")
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template(
        "index.html",
        styles={k: {"label": v["label"], "description": v["description"], "swatch": v["swatch"]} for k, v in STYLES.items()},
        aspects=[("16:9", "YouTube", "Landscape"), ("9:16", "Reels & Shorts", "Portrait"), ("1:1", "Feed posts", "Square")],
        property_types=PROPERTY_TYPES,
        music_tracks=list_music_tracks(),
        ai_enabled=llm_available(),
        cfg={"min": Config.MIN_IMAGES, "max": Config.MAX_IMAGES, "maxMB": Config.MAX_IMAGE_MB,
             "exts": sorted(Config.ALLOWED_IMAGE_EXTENSIONS)},
    )


@app.post("/api/generate")
def api_generate():
    if not ffmpeg_available():
        return jsonify(ok=False, errors=["FFmpeg is not available. Run 'pip install -r requirements.txt' and restart the app."]), 503

    errors: list[str] = []
    prop, form_errors = validate_property_form(request.form)
    errors += form_errors

    style = request.form.get("style", "")
    if style not in STYLES:
        errors.append("Choose a video style.")
    aspect = request.form.get("aspect", "")
    if aspect not in Config.ASPECT_RATIOS:
        errors.append("Unsupported aspect ratio. Choose 16:9, 9:16 or 1:1.")

    music_file = request.form.get("music", "").strip()
    music_path = None
    if music_file:
        if music_file not in {t["file"] for t in list_music_tracks()}:
            errors.append("The selected music track was not found.")
        else:
            music_path = Config.MUSIC_DIR / music_file

    job_id = uuid.uuid4().hex
    upload_dir = Config.UPLOAD_DIR / job_id
    image_paths, image_errors = process_uploaded_images(request.files.getlist("images"), upload_dir)
    errors += image_errors
    if errors:
        shutil.rmtree(upload_dir, ignore_errors=True)
        return jsonify(ok=False, errors=errors), 400

    cleanup_old_files()
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "progress": 0.0, "message": "Starting…", "script": None, "filename": None}
    use_ai = request.form.get("use_ai") == "on"
    threading.Thread(target=run_job, daemon=True,
                     args=(job_id, image_paths, prop, style, aspect, music_path, use_ai)).start()
    return jsonify(ok=True, job_id=job_id)


@app.get("/api/status/<job_id>")
def api_status(job_id):
    job = _get_job(job_id)
    return jsonify({k: job[k] for k in ("status", "progress", "message", "script")})


def _video_file(job_id):
    job = _get_job(job_id)
    path = Config.OUTPUT_DIR / f"{job_id}.mp4"
    if job["status"] != "done" or not path.exists():
        abort(404)
    return job, path


@app.get("/api/video/<job_id>")
def api_video(job_id):
    _, path = _video_file(job_id)
    return send_file(path, mimetype="video/mp4", conditional=True)


@app.get("/download/<job_id>")
def download(job_id):
    job, path = _video_file(job_id)
    return send_file(path, mimetype="video/mp4", as_attachment=True, download_name=job["filename"])


# --------------------------------------------------------------------------- #
# Error handlers (always JSON for the API)
# --------------------------------------------------------------------------- #
@app.errorhandler(413)
def too_large(_):
    return jsonify(ok=False, errors=[f"Upload too large. Keep each image under {Config.MAX_IMAGE_MB} MB "
                                     f"and use at most {Config.MAX_IMAGES} images."]), 413


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith(("/api/", "/download/")):
        return jsonify(ok=False, errors=["Not found. The video may have expired - generate it again."]), 404
    return "Page not found", 404


@app.errorhandler(500)
def server_error(_):
    return jsonify(ok=False, errors=["Unexpected server error. Check the server console."]), 500


if __name__ == "__main__":
    print(f"\n  AI Property Video Generator -> http://{Config.HOST}:{Config.PORT}\n")
    app.run(host=Config.HOST, port=Config.PORT, debug=False, threaded=True)
