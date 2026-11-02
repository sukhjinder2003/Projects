"""End-to-end API test with SYNTHETIC data (Flask test client). Output is stored in the
normal outputs/ folder, checked, then deleted.   Run:  python tests/api_test.py"""
import io, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tempfile
from smoke_test import SYNTHETIC_PROPERTY as P, synthetic_images
from app import app
from config import Config

def form(**over):
    d = {"property_name": P["name"], "location": P["location"], "price": P["price"], "property_type": "Apartment",
         "bedrooms": "3", "bathrooms": "2", "area": "1850", "features": "\n".join(P["features"]),
         "contact": P["contact"], "cta": P["cta"], "style": "social_media", "aspect": "9:16"}
    d.update(over); return d

def post(c, imgs, **over):
    data = form(**over)
    data["images"] = [(io.BytesIO(p.read_bytes()), p.name) for p in imgs]
    return c.post("/api/generate", data=data, content_type="multipart/form-data")

with tempfile.TemporaryDirectory() as tmp:
    imgs = synthetic_images(Path(tmp), 5)
    c = app.test_client()
    assert c.get("/").status_code == 200
    r = post(c, imgs[:3]);             assert r.status_code == 400 and "at least 4" in r.json["errors"][0], r.json
    r = post(c, imgs, aspect="4:3");   assert r.status_code == 400 and any("aspect" in e for e in r.json["errors"]), r.json
    r = post(c, imgs, property_name=""); assert r.status_code == 400
    bad = Path(tmp) / "x.gif"; bad.write_bytes(b"GIF89a")
    r = post(c, imgs[:4] + [bad]);     assert r.status_code == 400 and any("JPG" in e for e in r.json["errors"]), r.json
    fake = Path(tmp) / "fake.jpg"; fake.write_bytes(b"not an image")
    r = post(c, imgs[:4] + [fake]);    assert r.status_code == 400, r.json
    print("validation checks passed")
    r = post(c, imgs); assert r.status_code == 200 and r.json["ok"], r.json
    jid = r.json["job_id"]
    while True:
        s = c.get(f"/api/status/{jid}").json
        if s["status"] in ("done", "error"): break
        time.sleep(1)
    assert s["status"] == "done", s
    v = c.get(f"/api/video/{jid}"); assert v.status_code == 200 and v.mimetype == "video/mp4" and len(v.data) > 10000
    d = c.get(f"/download/{jid}"); assert "attachment" in d.headers["Content-Disposition"]
    print("render + preview + download passed;", s["script"]["source"], "script; video", len(v.data) // 1024, "KB")
    (Config.OUTPUT_DIR / f"{jid}.mp4").unlink()
