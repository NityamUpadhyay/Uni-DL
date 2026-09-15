"""
UniDL — Universal Downloader
A web UI around yt-dlp for downloading videos, playlists, and educational resources.

Run with:  python app.py
Then open: http://127.0.0.1:5000
"""

import json
import re
import subprocess
import sys
import threading
import time
import uuid
import shutil
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# Tools directory (scribd_wrapper lives here)
TOOLS_DIR = Path(__file__).resolve().parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "downloads"
DEFAULT_DOWNLOAD_DIR.mkdir(exist_ok=True)

CATALOGUE_FILE = BASE_DIR / "catalogue.json"

# In-memory job store: job_id -> dict(status, percent, speed, eta, log, filename)
JOBS = {}
JOBS_LOCK = threading.Lock()

PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>[\d.]+)%(?:\s+of\s+~?(?P<size>[\d.]+\w+))?"
    r"(?:\s+at\s+(?P<speed>[\d.]+\w+/s|Unknown speed))?"
    r"(?:\s+ETA\s+(?P<eta>[\d:]+|Unknown))?"
)
DEST_RE = re.compile(r"\[download\] Destination:\s*(.+)")
ALREADY_RE = re.compile(r"\[download\]\s+(.+)\s+has already been downloaded")
MERGE_RE = re.compile(r"\[Merger\] Merging formats into \"(.+)\"")
EXTRACT_AUDIO_RE = re.compile(r"\[ExtractAudio\] Destination:\s*(.+)")


def find_ytdlp_cmd():
    """Locate yt-dlp on this machine.

    Preference order:
      1. A system install on PATH.
      2. The yt-dlp Python package (installed via requirements.txt / bootstrap.py).
    Returns a list to prefix onto every yt-dlp command.
    """
    exe = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return ["yt-dlp"]


def find_ffmpeg_location():
    """Locate ffmpeg. Prefer system install; fall back to imageio-ffmpeg bundle."""
    if shutil.which("ffmpeg"):
        return None
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


YTDLP_CMD = find_ytdlp_cmd()
FFMPEG_LOCATION = find_ffmpeg_location()


# ---------- catalogue ----------

def load_catalogue():
    """Load and return the curated catalogue JSON, or an empty structure on error."""
    try:
        with open(CATALOGUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"departments": [], "_error": str(e)}


@app.route("/api/catalogue")
def api_catalogue():
    return jsonify(load_catalogue())


# ---------- yt-dlp helpers ----------

def run_ytdlp_json(url):
    """Run yt-dlp with --flat-playlist -j and return list of parsed JSON objects (one per line)."""
    cmd = YTDLP_CMD + ["-j", "--flat-playlist", "--no-warnings", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed to fetch info")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def fetch_full_info(url):
    """Run yt-dlp -j (no flatten) for a single video to get full format list."""
    cmd = YTDLP_CMD + ["-j", "--no-warnings", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed to fetch info")
    return json.loads(result.stdout.strip().splitlines()[-1])


def human_size(n):
    if not n:
        return None
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def simplify_formats(info):
    """Split raw yt-dlp formats into combined / video-only / audio-only buckets."""
    combined, video_only, audio_only = [], [], []
    for f in info.get("formats", []):
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        if vcodec == "images":
            continue
        raw_bytes = f.get("filesize") or f.get("filesize_approx")
        row = {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "resolution": f.get("resolution") or (f"{f.get('width')}x{f.get('height')}" if f.get("width") else None),
            "fps": f.get("fps"),
            "vcodec": None if vcodec == "none" else vcodec,
            "acodec": None if acodec == "none" else acodec,
            "abr": f.get("abr"),
            "tbr": f.get("tbr"),
            "filesize": human_size(raw_bytes),
            "filesize_bytes": raw_bytes,
            "note": f.get("format_note"),
            "ext_label": f.get("ext"),
        }
        has_v = vcodec != "none"
        has_a = acodec != "none"
        if has_v and has_a:
            combined.append(row)
        elif has_v:
            video_only.append(row)
        elif has_a:
            audio_only.append(row)

    def sort_key_video(r):
        try:
            h = int((r["resolution"] or "0x0").split("x")[1])
        except Exception:
            h = 0
        return (h, r["tbr"] or 0)

    def sort_key_audio(r):
        return r["abr"] or r["tbr"] or 0

    combined.sort(key=sort_key_video, reverse=True)
    video_only.sort(key=sort_key_video, reverse=True)
    audio_only.sort(key=sort_key_audio, reverse=True)

    if not combined:
        combined = build_virtual_combos(video_only, audio_only)

    return combined, video_only, audio_only


def build_virtual_combos(video_only, audio_only):
    """Synthesize 'combined' rows by pairing each video-only resolution with matching audio."""
    if not video_only or not audio_only:
        return []

    def height_of(row):
        try:
            return int((row["resolution"] or "0x0").split("x")[1])
        except Exception:
            return 0

    best_by_key = {}
    for v in video_only:
        h = height_of(v)
        if h <= 0 or not v.get("ext"):
            continue
        key = (h, v["ext"])
        if key not in best_by_key or (v["tbr"] or 0) > (best_by_key[key]["tbr"] or 0):
            best_by_key[key] = v

    def best_audio(pred):
        candidates = [a for a in audio_only if pred(a)]
        return max(candidates, key=lambda a: a["abr"] or a["tbr"] or 0, default=None)

    best_audio_overall = best_audio(lambda a: True)
    m4a_audio = best_audio(lambda a: a["ext"] == "m4a")
    webm_audio = best_audio(lambda a: a["ext"] == "webm")

    combos = []
    for (h, ext), v in best_by_key.items():
        if ext == "mp4":
            audio = m4a_audio or best_audio_overall
        elif ext == "webm":
            audio = webm_audio or best_audio_overall
        else:
            audio = best_audio_overall
        if not audio:
            continue
        v_bytes, a_bytes = v.get("filesize_bytes"), audio.get("filesize_bytes")
        combos.append({
            "format_id": f"{v['format_id']}+{audio['format_id']}",
            "ext": ext,
            "resolution": f"{h}p",
            "fps": v.get("fps"),
            "vcodec": v.get("vcodec"),
            "acodec": audio.get("acodec"),
            "abr": audio.get("abr"),
            "tbr": v.get("tbr"),
            "filesize": human_size(v_bytes + a_bytes) if v_bytes and a_bytes else None,
            "note": "video+audio, merged automatically",
            "ext_label": ext,
            "_height": h,
        })

    combos.sort(key=lambda r: (r["_height"], r["ext"]))
    for c in combos:
        del c["_height"]
    return combos


# ---------- routes ----------

@app.route("/")
def index():
    return render_template("index.html", default_dir=str(DEFAULT_DOWNLOAD_DIR))


@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "Please paste a URL."}), 400
    try:
        entries = run_ytdlp_json(url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if len(entries) > 1:
        # It's a playlist
        playlist_title = entries[0].get("playlist_title") or entries[0].get("playlist") or "Playlist"
        items = [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={e.get('id')}",
                "duration": e.get("duration_string") or e.get("duration"),
                "thumbnail": e.get("thumbnails", [{}])[-1].get("url") if e.get("thumbnails") else None,
            }
            for e in entries
        ]
        return jsonify({
            "type": "playlist",
            "playlist_title": playlist_title,
            "playlist_url": url,
            "count": len(items),
            "items": items,
        })

    # Single video
    single = entries[0]
    if "formats" not in single or not single.get("formats"):
        single = fetch_full_info(single.get("webpage_url") or url)

    combined, video_only, audio_only = simplify_formats(single)
    return jsonify({
        "type": "video",
        "id": single.get("id"),
        "title": single.get("title"),
        "uploader": single.get("uploader") or single.get("channel"),
        "duration": single.get("duration_string"),
        "thumbnail": single.get("thumbnail"),
        "webpage_url": single.get("webpage_url") or url,
        "combined": combined,
        "video_only": video_only,
        "audio_only": audio_only,
    })


@app.route("/api/video_formats", methods=["POST"])
def api_video_formats():
    """Fetch full format list for a single playlist entry the user clicked into."""
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "Missing url"}), 400
    try:
        single = fetch_full_info(url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    combined, video_only, audio_only = simplify_formats(single)
    return jsonify({
        "type": "video",
        "id": single.get("id"),
        "title": single.get("title"),
        "uploader": single.get("uploader") or single.get("channel"),
        "duration": single.get("duration_string"),
        "thumbnail": single.get("thumbnail"),
        "webpage_url": single.get("webpage_url") or url,
        "combined": combined,
        "video_only": video_only,
        "audio_only": audio_only,
    })


# ---------- download engine ----------

STOPPING_STATES = ("paused", "cancelled")
MAX_AUTO_RETRIES = 8


def _process_line(job_id, line):
    line = line.rstrip()
    if not line:
        return
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["log"].append(line)
        job["log"] = job["log"][-200:]
        m = PROGRESS_RE.search(line)
        if m:
            job["percent"] = float(m.group("percent"))
            if m.group("speed"):
                job["speed"] = m.group("speed")
            if m.group("eta"):
                job["eta"] = m.group("eta")
        d = DEST_RE.search(line)
        if d:
            job["filepath"] = d.group(1)
            job["filename"] = os.path.basename(d.group(1))
        a = ALREADY_RE.search(line)
        if a:
            job["filepath"] = a.group(1)
            job["filename"] = os.path.basename(a.group(1))
            job["percent"] = 100
        mg = MERGE_RE.search(line)
        if mg:
            job["filepath"] = mg.group(1)
            job["filename"] = os.path.basename(mg.group(1))
            job["status"] = "merging"
        ea = EXTRACT_AUDIO_RE.search(line)
        if ea:
            job["filepath"] = ea.group(1)
            job["filename"] = os.path.basename(ea.group(1))


def _spawn_attempt(job_id):
    """Run a single yt-dlp attempt. Returns return code, or None if killed on purpose."""
    with JOBS_LOCK:
        job = JOBS[job_id]
        cmd, cwd = job["cmd"], job["out_dir"]
        if job["status"] not in STOPPING_STATES:
            job["status"] = "downloading"

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True,
        )
    except FileNotFoundError:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["log"].append(
                "Could not run yt-dlp. Make sure dependencies are installed "
                "(run start.bat again, or `pip install -r requirements.txt`)."
            )
        return 1

    with JOBS_LOCK:
        JOBS[job_id]["proc"] = proc

    for line in proc.stdout:
        _process_line(job_id, line)
    proc.wait()

    with JOBS_LOCK:
        JOBS[job_id]["proc"] = None
        if JOBS[job_id]["status"] in STOPPING_STATES:
            return None

    return proc.returncode


def _download_worker(job_id):
    """Outer controller: runs attempts with auto-retry on transient failures."""
    attempt = 0
    while True:
        rc = _spawn_attempt(job_id)

        with JOBS_LOCK:
            status = JOBS[job_id]["status"]
        if status in STOPPING_STATES:
            return

        if rc == 0:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "finished"
                JOBS[job_id]["percent"] = 100
            return

        attempt += 1
        if attempt > MAX_AUTO_RETRIES:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["log"].append(
                    f"Gave up after {MAX_AUTO_RETRIES} automatic retries. "
                    "Click Resume to try again, or Cancel to stop."
                )
            return

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "retrying"
            JOBS[job_id]["log"].append(
                f"--- attempt {attempt} failed, retrying in a few seconds "
                "(resuming from where it stopped) ---"
            )

        for _ in range(6):
            time.sleep(0.5)
            with JOBS_LOCK:
                if JOBS[job_id]["status"] in STOPPING_STATES:
                    return


@app.route("/api/download", methods=["POST"])
def api_download():
    try:
        data = request.get_json(force=True)
        url = (data or {}).get("url", "").strip()
        fmt = (data or {}).get("format", "").strip()
        mp3 = bool((data or {}).get("mp3"))
        playlist = bool((data or {}).get("playlist"))
        out_dir = (data or {}).get("out_dir") or str(DEFAULT_DOWNLOAD_DIR)
        merge_format = (data or {}).get("merge_format") or "mp4"
        subtitles = bool((data or {}).get("subtitles"))

        # University-specific: subject + playlist_name for hierarchical folder layout
        subject = ((data or {}).get("subject") or "").strip()
        playlist_name = ((data or {}).get("playlist_name") or "").strip()

        if merge_format not in ("mp4", "webm", "mkv"):
            merge_format = "mp4"

        if not url or not fmt:
            return jsonify({"error": "Missing url or format"}), 400

        Path(out_dir).mkdir(parents=True, exist_ok=True)

        # Build output template
        if playlist and subject and playlist_name:
            safe_subject = subject.replace("/", "-").replace("\\", "-")
            safe_playlist = playlist_name.replace("/", "-").replace("\\", "-")
            out_template = os.path.join(
                safe_subject, safe_playlist,
                "%(playlist_index)02d - %(title).150B.%(ext)s"
            )
        elif playlist:
            out_template = os.path.join(
                "%(playlist_title)s",
                "%(playlist_index)02d - %(title).150B.%(ext)s"
            )
        else:
            out_template = "%(title).150B [%(id)s].%(ext)s"

        cmd = YTDLP_CMD + [
            url, "-f", fmt, "-o", out_template, "--newline", "--no-warnings", "--no-mtime",
            "--continue",
            "--retries", "50",
            "--fragment-retries", "50",
            "--retry-sleep", "3",
            "--socket-timeout", "30",
            "--concurrent-fragments", "4",
        ]

        if FFMPEG_LOCATION:
            cmd += ["--ffmpeg-location", FFMPEG_LOCATION]

        if playlist:
            cmd.append("--yes-playlist")
        else:
            cmd.append("--no-playlist")

        if "+" in fmt or fmt in ("bv*+ba/b", "bestvideo+bestaudio"):
            cmd += ["--merge-output-format", merge_format]

        if mp3:
            cmd += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]

        if subtitles:
            cmd += [
                "--write-sub", "--write-auto-sub",
                "--sub-lang", "en,en-IN",
                "--convert-subs", "srt",
            ]

        job_id = str(uuid.uuid4())[:8]
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "queued", "percent": 0, "speed": None, "eta": None,
                "log": [], "filename": None, "filepath": None, "out_dir": out_dir,
                "cmd": cmd, "proc": None,
            }
        t = threading.Thread(target=_download_worker, args=(job_id,), daemon=True)
        t.start()
        return jsonify({"job_id": job_id})

    except Exception as exc:
        import traceback
        return jsonify({"error": str(exc), "trace": traceback.format_exc()}), 500


def _job_public(job):
    return {k: v for k, v in job.items() if k not in ("proc", "cmd")}


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        return jsonify(_job_public(job))


@app.route("/api/job/<job_id>/pause", methods=["POST"])
def api_job_pause(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        if job["status"] not in ("downloading", "merging", "retrying", "queued"):
            return jsonify({"error": f"can't pause a job that is {job['status']}"}), 400
        job["status"] = "paused"
        proc = job.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/job/<job_id>/resume", methods=["POST"])
def api_job_resume(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        if job["status"] != "paused":
            return jsonify({"error": f"can't resume a job that is {job['status']}"}), 400
        job["status"] = "queued"
        job["log"].append("--- resuming (yt-dlp will pick up from the partial file) ---")
    t = threading.Thread(target=_download_worker, args=(job_id,), daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/api/job/<job_id>/cancel", methods=["POST"])
def api_job_cancel(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        if job["status"] in ("finished", "cancelled", "error"):
            return jsonify({"error": f"job is already {job['status']}"}), 400
        job["status"] = "cancelled"
        proc = job.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/job/<job_id>", methods=["DELETE"])
def api_job_delete(job_id):
    """Remove a job from the list (server-side bookkeeping only)."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"ok": True})
        if job["status"] in ("downloading", "merging", "retrying", "queued"):
            return jsonify({"error": "job is still running — pause or cancel it first"}), 400
        JOBS.pop(job_id, None)
    return jsonify({"ok": True})


# ---------- resource search & document download ----------

OPEN_LIBRARY_SEARCH  = "https://openlibrary.org/search.json"
ARCHIVE_SEARCH       = "https://archive.org/advancedsearch.php"
ARCHIVE_DOWNLOAD_BASE = "https://archive.org/download"

RESOURCE_HEADERS = {
    "User-Agent": "UniDL/2.0 (+https://github.com/yt-dlp/yt-dlp)",
}


def _search_open_library(q: str, limit: int = 8) -> list:
    try:
        resp = _requests.get(
            OPEN_LIBRARY_SEARCH,
            params={"q": q, "limit": limit, "fields": "title,author_name,first_publish_year,cover_i,key,ia"},
            headers=RESOURCE_HEADERS,
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        return []

    results = []
    for doc in data.get("docs", []):
        ia_ids = doc.get("ia") or []
        cover_id = doc.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None
        # Build a direct download link if an Internet Archive copy exists
        dl_url = f"{ARCHIVE_DOWNLOAD_BASE}/{ia_ids[0]}" if ia_ids else None
        results.append({
            "source": "Open Library",
            "type": "book",
            "title": doc.get("title", "(untitled)"),
            "author": ", ".join(doc.get("author_name", [])[:3]),
            "year": doc.get("first_publish_year"),
            "cover_url": cover_url,
            "open_url": f"https://openlibrary.org{doc['key']}" if doc.get("key") else None,
            "download_url": dl_url,
            "ia_id": ia_ids[0] if ia_ids else None,
        })
    return results


def _search_archive(q: str, limit: int = 8) -> list:
    try:
        resp = _requests.get(
            ARCHIVE_SEARCH,
            params={
                "q": f"{q} AND mediatype:(texts)",
                "fl[]": ["identifier", "title", "creator", "year", "format", "description"],
                "rows": limit,
                "page": 1,
                "output": "json",
            },
            headers=RESOURCE_HEADERS,
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        return []

    results = []
    for doc in data.get("response", {}).get("docs", []):
        ident = doc.get("identifier", "")
        formats = doc.get("format") or []
        if isinstance(formats, str):
            formats = [formats]
        # Prefer PDF, then PPT/PPTX, then EPUB
        fmt_priority = ["PDF", "PPT", "PPTX", "EPUB"]
        chosen_ext = None
        for pref in fmt_priority:
            if pref in formats:
                chosen_ext = pref.lower()
                break
        dl_url = f"{ARCHIVE_DOWNLOAD_BASE}/{ident}/{ident}.{chosen_ext}" if chosen_ext else None
        results.append({
            "source": "Internet Archive",
            "type": chosen_ext or "text",
            "title": doc.get("title", "(untitled)"),
            "author": (doc.get("creator") or [""])[0] if isinstance(doc.get("creator"), list) else doc.get("creator", ""),
            "year": doc.get("year"),
            "cover_url": f"https://archive.org/services/img/{ident}",
            "open_url": f"https://archive.org/details/{ident}",
            "download_url": dl_url,
            "ia_id": ident,
            "formats": formats[:6],
        })
    return results


@app.route("/api/search_resources")
def api_search_resources():
    q = request.args.get("q", "").strip()
    src = request.args.get("source", "all")  # "all" | "openlibrary" | "archive"
    if not q:
        return jsonify({"error": "Missing query parameter q"}), 400
    if not _REQUESTS_OK:
        return jsonify({"error": "requests library not installed. Run: pip install requests"}), 500

    results = []
    if src in ("all", "openlibrary"):
        results += _search_open_library(q, limit=6)
    if src in ("all", "archive"):
        results += _search_archive(q, limit=6)

    return jsonify({"query": q, "results": results, "count": len(results)})


def _direct_download_worker(job_id: str, url: str, out_path: str, label: str):
    """Download a direct URL (PDF/PPTX/etc.) with requests, streaming."""
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "downloading"
        JOBS[job_id]["log"].append(f"Downloading: {label}")

    try:
        resp = _requests.get(url, headers=RESOURCE_HEADERS, stream=True, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0)) or None
        downloaded = 0
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = round(downloaded / total * 100, 1)
                        with JOBS_LOCK:
                            JOBS[job_id]["percent"] = pct
                            JOBS[job_id]["speed"] = None
                    with JOBS_LOCK:
                        if JOBS[job_id]["status"] == "cancelled":
                            return
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "finished"
            JOBS[job_id]["percent"] = 100
            JOBS[job_id]["filename"] = os.path.basename(out_path)
            JOBS[job_id]["filepath"] = out_path
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["log"].append(str(e))


@app.route("/api/download_resource", methods=["POST"])
def api_download_resource():
    """Download a direct PDF/PPTX/etc. URL (from Archive.org or any direct link)."""
    if not _REQUESTS_OK:
        return jsonify({"error": "requests library not installed. Run: pip install requests"}), 500

    data = request.get_json(force=True) or {}
    url   = data.get("url", "").strip()
    label = data.get("label", "document").strip()
    topic = data.get("topic", "Resources").strip()

    if not url:
        return jsonify({"error": "Missing url"}), 400

    # Derive a safe filename from the URL
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path) or "document.pdf"
    if not os.path.splitext(filename)[1]:
        filename += ".pdf"
    safe_topic = topic.replace("/", "-").replace("\\", "-")
    out_path = str(DEFAULT_DOWNLOAD_DIR / "Resources" / safe_topic / filename)

    job_id = str(uuid.uuid4())[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued", "percent": 0, "speed": None, "eta": None,
            "log": [], "filename": None, "filepath": None,
            "out_dir": str(DEFAULT_DOWNLOAD_DIR / "Resources"),
            "cmd": [], "proc": None,
        }

    t = threading.Thread(
        target=_direct_download_worker,
        args=(job_id, url, out_path, label),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id})


def _scribd_worker(job_id: str, url: str, out_path: str):
    """Run the scribd downloader and report progress back via JOBS."""
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "downloading"
        JOBS[job_id]["log"].append("Setting up Scribd downloader (first-run: may take a minute)…")

    try:
        from scribd_wrapper import run_scribd, ensure_installed
        err = ensure_installed()
        if err:
            raise RuntimeError(err)

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        for item in run_scribd(url, out_path):
            if isinstance(item, dict):
                rc = item.get("returncode", 1)
                with JOBS_LOCK:
                    if rc == 0:
                        JOBS[job_id]["status"] = "finished"
                        JOBS[job_id]["percent"] = 100
                        JOBS[job_id]["filename"] = os.path.basename(out_path)
                        JOBS[job_id]["filepath"] = out_path
                    else:
                        JOBS[job_id]["status"] = "error"
            else:
                with JOBS_LOCK:
                    job = JOBS[job_id]
                    job["log"].append(str(item))
                    job["log"] = job["log"][-200:]
                    if JOBS[job_id]["status"] == "cancelled":
                        return
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["log"].append(str(e))


@app.route("/api/scribd_download", methods=["POST"])
def api_scribd_download():
    """Download a Scribd document using the headless Chrome tool from GitHub."""
    data = request.get_json(force=True) or {}
    url   = data.get("url", "").strip()
    label = data.get("label", "scribd-doc").strip()

    if not url:
        return jsonify({"error": "Missing url"}), 400

    safe_label = re.sub(r'[^\w\-. ]', '_', label)[:80]
    out_path = str(DEFAULT_DOWNLOAD_DIR / "Resources" / "Scribd" / f"{safe_label}.pdf")

    job_id = str(uuid.uuid4())[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued", "percent": 0, "speed": None, "eta": None,
            "log": [], "filename": None, "filepath": None,
            "out_dir": str(DEFAULT_DOWNLOAD_DIR / "Resources" / "Scribd"),
            "cmd": [], "proc": None,
        }

    t = threading.Thread(target=_scribd_worker, args=(job_id, url, out_path), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


def _slideshare_worker(job_id: str, url: str, out_path: str):
    """Download a SlideShare presentation to PDF using our custom scraper."""
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "downloading"
        JOBS[job_id]["log"].append("Fetching SlideShare page…")

    try:
        from slideshare_dl import download as ss_download

        def _progress(cur, total):
            with JOBS_LOCK:
                JOBS[job_id]["percent"] = round(cur / total * 100, 1)
                JOBS[job_id]["log"].append(f"  Slide {cur}/{total}")
                JOBS[job_id]["log"] = JOBS[job_id]["log"][-200:]
                if JOBS[job_id]["status"] == "cancelled":
                    raise RuntimeError("cancelled")

        ss_download(url, out_path, progress_cb=_progress)

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "finished"
            JOBS[job_id]["percent"] = 100
            JOBS[job_id]["filename"] = os.path.basename(out_path)
            JOBS[job_id]["filepath"] = out_path
            JOBS[job_id]["log"].append(f"Saved → {out_path}")

    except Exception as e:
        with JOBS_LOCK:
            if JOBS[job_id]["status"] != "cancelled":
                JOBS[job_id]["status"] = "error"
            JOBS[job_id]["log"].append(str(e))


@app.route("/api/slideshare_download", methods=["POST"])
def api_slideshare_download():
    """Download a SlideShare presentation as a PDF (custom scraper, no browser)."""
    data = request.get_json(force=True) or {}
    url   = data.get("url", "").strip()
    label = data.get("label", "slides").strip()

    if not url:
        return jsonify({"error": "Missing url"}), 400

    safe_label = re.sub(r'[^\w\-. ]', '_', label)[:100]
    out_path = str(DEFAULT_DOWNLOAD_DIR / "Resources" / "SlideShare" / f"{safe_label}.pdf")

    job_id = str(uuid.uuid4())[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued", "percent": 0, "speed": None, "eta": None,
            "log": [], "filename": None, "filepath": None,
            "out_dir": str(DEFAULT_DOWNLOAD_DIR / "Resources" / "SlideShare"),
            "cmd": [], "proc": None,
        }

    t = threading.Thread(target=_slideshare_worker, args=(job_id, url, out_path), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/open_folder", methods=["POST"])
def api_open_folder():
    data = request.get_json(force=True)
    path = (data or {}).get("path") or str(DEFAULT_DOWNLOAD_DIR)
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore
        elif shutil.which("open"):
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def get_port():
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except ValueError:
            pass
    env_port = os.environ.get("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    return 5000


def open_browser_when_ready(port, delay=1.2):
    def _go():
        time.sleep(delay)
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


if __name__ == "__main__":
    PORT = get_port()
    print("=" * 60)
    print("  UniDL — Universal Downloader")
    print("=" * 60)
    print(f"  yt-dlp: {' '.join(YTDLP_CMD)}")
    print(f"  ffmpeg: {'system PATH' if not FFMPEG_LOCATION else FFMPEG_LOCATION}")
    print(f"  Downloads: {DEFAULT_DOWNLOAD_DIR}")
    print(f"\n  Starting at http://127.0.0.1:{PORT} ...")
    print("  Your browser will open automatically. Press Ctrl+C to stop.\n")
    open_browser_when_ready(PORT)
    app.run(debug=False, port=PORT)
