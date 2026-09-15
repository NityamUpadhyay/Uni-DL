# UniDL — Universal Downloader

> **Download videos, playlists, books, PDFs and slides — all from one local web app.**

UniDL is a clean, browser-based interface around [yt-dlp](https://github.com/yt-dlp/yt-dlp) that runs entirely on your own machine. No accounts, no cloud, no data sent anywhere.

---

## ✨ Features

| Tab | What it does |
|---|---|
| 📚 **Catalogue** | Browse a curated library of educational playlists (NPTEL, MIT OCW, freeCodeCamp, CS50, Khan Academy) organised by department and subject — one click to download |
| 📖 **Resources** | Search for books and PDFs on Open Library & Internet Archive, download directly. Paste any SlideShare or Scribd URL to save it as a PDF |
| 🔗 **Paste URL** | Paste any video or playlist URL from YouTube, NPTEL, Vimeo, and [1000+ other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) — pick exact quality, codec and format |

**All downloads** get a live progress bar with **pause / resume / cancel** controls and auto-retry on failure.

---

## 🚀 Quick Start

### Requirements

- **Python 3.10+** — download from [python.org](https://www.python.org/downloads/)
  > ⚠️ On Windows, tick **"Add python.exe to PATH"** during install.
- **Google Chrome** — only needed for downloading Scribd documents. All other features work without it.

### One-click launch

**Windows** — double-click **`start.bat`**

**Mac / Linux** — open a terminal and run:
```bash
./start.sh
```

That's it. On first run, it automatically installs all Python dependencies, then opens the app in your browser at **http://127.0.0.1:5000**.

<details>
<summary>Manual setup (advanced)</summary>

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

</details>

---

## 📖 How to Use

### 📚 Browse Catalogue

1. The app opens on the **Browse Catalogue** tab.
2. Expand a **department** (e.g. Computer Science & Engineering).
3. Click a **subject chip** (e.g. Data Structures & Algorithms) — playlist cards appear.
4. Use the **search box** to filter across all playlists instantly.
5. On a playlist card, choose an action:
   - **▶ Load & Preview** — fetches the playlist so you can inspect or pick individual videos.
   - **⬇️ Video+Audio** — downloads the entire playlist at best quality immediately.
   - **🎵 Audio MP3** — downloads all lectures as MP3 (great for offline listening).

> Tick **"download subtitles (.srt)"** before downloading to save English subtitles alongside each file.

---

### 📖 Resources

**Search for books & PDFs:**

1. Go to the **Resources** tab.
2. Type a topic (e.g. `"operating systems"`, `"calculus"`, `"machine learning"`).
3. Filter by **All Sources**, **Open Library**, or **Internet Archive**.
4. Click **⬇️ Download** on any result — the file saves to `downloads/Resources/`.
5. Click **🎓 Scholar** to open a Google Scholar search for the same topic in your browser.
6. Click **🔗 Open** to view the book's page online.

**Download a document by URL:**

Paste any of the following into the URL box at the bottom of the Resources tab:

| URL type | How it's handled |
|---|---|
| `slideshare.net/…` | Scrapes slide images, merges into a PDF |
| `scribd.com/…` | Uses headless Chrome to render and save as PDF |
| Any `.pdf` / `.pptx` / `.epub` link | Downloaded directly via HTTP |

---

### 🔗 Paste URL

1. Click the **Paste URL** tab.
2. Paste any supported URL and click **Analyze**.
3. For a **playlist** — use the quick-download buttons or click an individual video to open the format picker.
4. For a **single video** — use quick-download presets, build a custom combo (video + audio stream), or click **get** on any row in the format table.

---

## 📁 Folder Structure

All files are saved inside `downloads/` next to `app.py`.

```
downloads/
│
├── Data Structures & Algorithms/          ← Catalogue download (subject)
│   └── DSA — NPTEL Playlist/             ← (playlist name)
│       ├── 01 - Introduction to DSA.mp4
│       ├── 02 - Arrays and Linked Lists.mp4
│       └── …
│
├── Resources/                             ← Resource tab downloads
│   ├── calculus/                          ← (search topic)
│   │   └── Calculus_Vol_1.pdf
│   ├── SlideShare/
│   │   └── intro-to-ml.pdf
│   └── Scribd/
│       └── design-patterns.pdf
│
└── My Playlist Title/                     ← URL tab (playlist)
    ├── 01 - First Video.mp4
    └── …
```

---

## 📚 Catalogue Contents

| Department | Subjects |
|---|---|
| 💻 Computer Science & Engineering | Data Structures & Algorithms, Operating Systems, DBMS, Computer Networks, Machine Learning, Python, Web Development, Compiler Design, Discrete Mathematics, Software Engineering |
| 📊 Commerce & Management | Financial Accounting, Corporate Finance, Marketing Management, Business Statistics, Organisational Behaviour, Supply Chain Management, Entrepreneurship |
| 🔬 Sciences | Engineering Mathematics, Physics, Chemistry, Biology |
| 📚 Humanities & Social Sciences | Communication Skills, Economics, Psychology, Indian History |

**Sources:** NPTEL (IIT lecture series), MIT OpenCourseWare, freeCodeCamp, CS50 Harvard, Khan Academy, Y Combinator Startup School, Yale Online.

---

## ⚙️ Dependencies

All installed automatically by `start.bat` / `start.sh`:

| Package | Purpose |
|---|---|
| `Flask` | Local web server |
| `yt-dlp` | Video/audio download engine |
| `imageio-ffmpeg` | Bundled ffmpeg fallback (used if ffmpeg is not on your PATH) |
| `requests` | Resource search + direct PDF download |
| `Pillow` | Merges SlideShare slide images into a single PDF |
| `selenium` | Drives headless Chrome for Scribd downloads |
| `pypdf` | PDF assembly used by the Scribd tool |

> **Google Chrome** must be separately installed for Scribd downloads. Get it at [google.com/chrome](https://www.google.com/chrome/).

---

## 🔒 Privacy & Security

- The server only listens on `127.0.0.1` (localhost) — **nothing is reachable from your network or the internet**.
- No usage data, analytics, or crash reports are sent anywhere.
- All downloads go to a local `downloads/` folder on your own machine.
- The Scribd downloader clones [themrsami/scribd-downloader](https://github.com/themrsami/scribd-downloader) from GitHub on first use — you can inspect its code before running.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `Python not found` | Install Python 3.10+ from [python.org](https://www.python.org/downloads/) and tick "Add to PATH" |
| App opens but catalogue is empty | Check your internet connection — the catalogue loads from `catalogue.json` which is bundled, but playlist info is fetched live |
| Download stuck at 0% | yt-dlp may need updating: `pip install -U yt-dlp` |
| SlideShare says "could not extract slide images" | The presentation may be private or login-gated. Open the URL in your browser to confirm it's public |
| Scribd download fails | Make sure Google Chrome is installed. On first run, the tool auto-clones from GitHub (needs internet + git) |
| `git clone failed: destination already exists` | Delete the `tools/scribd-downloader/` folder and try again — the app will re-clone it cleanly |

---

## 🤝 Contributing

Contributions are welcome! Here are some good first issues to start with:

- **Add playlists to the catalogue** — edit `catalogue.json` and submit a PR (make sure the URL is publicly accessible).
- **Add new site support** — yt-dlp already supports [1000+ sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md); test and document any edge cases.
- **UI improvements** — the frontend is plain HTML/CSS/JS in `static/` and `templates/` — no build step required.
- **Bug fixes** — open an issue describing the problem, then submit a fix.

### Development setup

```bash
git clone https://github.com/YOUR_USERNAME/Uni-DL.git
cd Uni-DL
pip install -r requirements.txt
python app.py
```

The app hot-reloads on save when Flask is in debug mode (set `DEBUG=True` at the bottom of `app.py` temporarily).

---

## 📄 License

Released under the **MIT License** — see [`LICENSE`](LICENSE) for the full text.

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) is licensed under The Unlicense.
- [themrsami/scribd-downloader](https://github.com/themrsami/scribd-downloader) is cloned at runtime — check its own license before use.

> Please respect each platform's Terms of Service. Only download content you have the legal right to access.

