# AI Property Video Generator

Create promotional real-estate videos (MP4) from property details and 4-8 photos, without any video-editing software.

## 1. Project overview

Sales teams enter a property's facts, upload photos, pick a style and format, and the app renders a finished video with an opening title, a price/details scene, one scene per photo with captions, a highlights scene and a final enquiry screen.

**Truthfulness rule:** the script, captions and highlights are built **only from the facts you type in**. The template generator can only repeat your input. The optional AI generator is prompted with the same rule *and* its output is rejected (falling back to templates) if it contains any number that is not in your input.

## 2. Features

- Property form: name, location, price, type, bedrooms, bathrooms, area, features, contact info, call-to-action.
- Image upload (JPG/JPEG/PNG, 4-8 images, 10 MB each) with previews, **Remove** and **Replace** buttons, drag and drop, and clear error messages.
- Script generation: template-based by default; optional Claude (Anthropic API) mode.
- Four video styles: Modern Luxury, Minimal Professional, Premium Real Estate, Social Media Promotional.
- Three aspect ratios: 16:9 (YouTube, 1280x720), 9:16 (Reels/Shorts, 720x1280), 1:1 (posts, 960x960).
- Ken Burns pan/zoom on photos, animated cards, fade / slide / zoom transitions, fade in/out.
- Optional background music from files you provide.
- Progress bar while rendering, in-page video preview, MP4 download, and a view of the script used.
- Validation and friendly errors for missing fields, bad images, wrong image counts, bad aspect ratios, render failures and missing FFmpeg. The app does not crash on invalid input.

## 3. Technology stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, vanilla JavaScript (no framework, no build step) |
| Backend | Python 3.9-3.13, Flask 3 |
| Video | Pillow (frame drawing) + FFmpeg (H.264 encoding, bundled via `imageio-ffmpeg`) |
| AI (optional) | Anthropic Messages API via `requests` |

> MoviePy is intentionally not used. Drawing frames with Pillow and piping them to FFmpeg avoids MoviePy's version incompatibilities and is faster and more predictable on Windows.

## 4. Folder structure

```
ai-property-video-generator/
├── app.py                    Flask routes, background render jobs, JSON API
├── config.py                 All settings (limits, aspect ratios, env vars)
├── requirements.txt
├── .env.example              Optional API-key configuration
├── README.md
├── services/
│   ├── validators.py         Form + image validation / normalisation
│   ├── script_generator.py   Template script + optional Claude script
│   └── video_generator.py    Scenes, styles, transitions, FFmpeg encoding
├── utils/helpers.py          Small helpers (cleanup, slugify, music list)
├── templates/index.html      Landing page + dashboard
├── static/
│   ├── css/style.css
│   ├── js/app.js             Previews, validation, polling
│   └── music/                Put your royalty-free tracks here (optional)
├── tests/
│   ├── smoke_test.py         Renders synthetic videos to a temp folder
│   └── api_test.py           End-to-end API test (synthetic data)
├── uploads/                  Temporary uploads (auto-deleted)
└── outputs/                  Generated MP4s (auto-deleted after 6 hours)
```

## 5. Prerequisites

- Windows 10/11 (also works on macOS/Linux)
- Python 3.9 or newer from https://www.python.org/downloads/ (tick **Add python.exe to PATH** in the installer)
- Internet access for the first `pip install`. No separate FFmpeg install is needed.

Check Python:

```bat
python --version
```

## 6. Installation (Windows)

Open **Command Prompt** in the project folder (`cd path\to\ai-property-video-generator`) and run:

```bat
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**PowerShell** users activate with `.\venv\Scripts\Activate.ps1`. If PowerShell blocks it, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

macOS/Linux: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`

## 7. Environment variables and API key (optional)

The app works fully without any key. To enable AI-written scripts:

```bat
copy .env.example .env
notepad .env
```

Set `ANTHROPIC_API_KEY=your-key` (create one at https://console.anthropic.com/). Other options in `.env.example`: `ANTHROPIC_MODEL`, `LLM_TIMEOUT`, `VIDEO_FPS`, `FLASK_HOST`, `FLASK_PORT`. Never commit `.env`; it is git-ignored. If the API fails or returns unusable text, the app silently falls back to the template script and says so in the "See the script used" panel.

## 8. Run the application

```bat
venv\Scripts\activate
python app.py
```

Open http://127.0.0.1:5000 in your browser. Stop the server with `Ctrl+C`.

Optional self-checks (use synthetic data, leave no videos behind):

```bat
python tests\smoke_test.py
python tests\smoke_test.py --all
python tests\api_test.py
```

## 9. How to use

1. Click **Fill with sample data** to try it with fictional details, or type your own.
2. Add 4-8 photos (drag and drop or click). Use **Replace** / **Remove** under any preview.
3. Choose a style and a format (16:9, 9:16 or 1:1). Optionally choose music and AI scripting.
4. Click **Generate video**. A progress bar shows rendering (roughly 20-90 seconds depending on your PC, format and number of photos).
5. Watch the preview, click **Download MP4**, and expand **See the script used** to review the text.

**Adding music:** copy royalty-free `.mp3`/`.wav`/`.m4a` files into `static\music\`, then restart the app. Check each track's licence permits commercial and social-media use. No music is bundled.

## 10. AI models, APIs and libraries

| Item | Purpose |
|---|---|
| Anthropic Messages API (default model `claude-sonnet-5-5`, configurable) | Optional script, caption, headline and highlight writing |
| Flask | Web server and API |
| Pillow | Image validation, Ken Burns frames, text and card drawing |
| imageio-ffmpeg (bundled FFmpeg) | H.264 MP4 encoding and music mixing |
| python-dotenv, requests, numpy | Configuration, HTTP calls, Pillow dependency |

No machine-learning model runs locally and no other external service is contacted. Google Fonts are loaded by the web page only for typography and fall back to system fonts when offline. Video text uses fonts already installed on your system (Segoe UI, Georgia, Arial on Windows).

## 11. How video generation works

1. **Validate** the form and images; each image is checked, rotated per EXIF, converted to RGB and saved as a JPEG in a job folder.
2. **Script**: build the headline, tagline, one caption per photo, highlights and closing line (template or AI with the numbers guard).
3. **Scenes**: title -> price and details -> one scene per photo -> highlights -> contact/CTA. Each scene is a backdrop (Ken Burns motion over a photo, blurred and dimmed for text-heavy scenes) plus timed, animated cards. Photos whose shape differs a lot from the chosen format are shown whole over a blurred copy of themselves instead of being cropped hard.
4. **Timeline**: scenes overlap by 0.6-0.8 s for the style's transition (fade, slide or zoom); the video fades in from and out to black.
5. **Encode**: frames are streamed to FFmpeg (`libx264`, `yuv420p`, `faststart`). If music is selected it is looped, faded in/out and mixed in.
6. **Serve**: the browser polls job status, then streams the MP4 for preview and download. Files are cleaned up automatically.

## 12. Known limitations and ideas

- Rendering runs on CPU; long videos at 1080-class sizes take longer. One render runs at a time.
- Captions are derived from your facts, not from what is visible in the photos (no image recognition, by design, to avoid invented details).
- Jobs and status are kept in memory, so restarting the server forgets past jobs.
- Fonts depend on those installed on the machine.
- No user accounts, history or multi-user queue management; it is built for local/team use. For production use a WSGI server such as `waitress` behind authentication.
- Ideas: per-image caption editing, logo and agent photo upload, 1080p / 1080x1920 export, voice-over via text-to-speech, vision-based room labelling with human approval, multi-language scripts, saved templates.
