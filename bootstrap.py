"""
bootstrap.py — auto-install dependencies then launch UniDL.

Called by start.bat / start.sh so users get a one-click start experience
without needing to run pip manually.
"""

import os
import subprocess
import sys

HERE         = os.path.dirname(os.path.abspath(__file__))
REQ_FILE     = os.path.join(HERE, "requirements.txt")
APP_FILE     = os.path.join(HERE, "app.py")

BANNER = "=" * 62

def pip_install(args, label=""):
    if label:
        print(f"  Installing {label}…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", *args],
        check=False,
    )
    return result.returncode


def check_package(pkg_name):
    """Return True if a package is importable (already installed)."""
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.metadata; importlib.metadata.version('{pkg_name}')"],
        capture_output=True,
    )
    return result.returncode == 0


def main():
    print(BANNER)
    print("  UniDL — Universal Downloader")
    print(BANNER)
    print()
    print("  Step 1/2 — Checking Python dependencies…")
    print()

    rc = pip_install(["-r", REQ_FILE])
    if rc != 0:
        print()
        print("  [!] Auto-install failed.")
        print("  Run this manually, then try again:")
        print()
        print(f"      {sys.executable} -m pip install -r requirements.txt")
        print()
        input("  Press Enter to exit…")
        sys.exit(rc)

    print()
    print("  All Python dependencies are ready.")
    print()

    # ── Chrome reminder for Scribd ────────────────────────────────────────────
    print("  Step 2/2 — Checking optional system tools…")
    print()
    import shutil
    if shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chromium"):
        print("  [OK] Google Chrome detected — Scribd downloader will work.")
    else:
        # On Windows Chrome is not on PATH by default; check the install dir
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        chrome_found = any(os.path.isfile(p) for p in chrome_paths)
        if chrome_found:
            print("  [OK] Google Chrome found — Scribd downloader will work.")
        else:
            print("  [!] Google Chrome NOT found.")
            print("      Scribd document downloads require Chrome.")
            print("      Install it from: https://www.google.com/chrome/")
            print("      (All other features — playlists, PDFs, SlideShare — work without it.)")

    print()
    print(BANNER)
    print("  Starting UniDL…  Browser will open automatically.")
    print("  Press Ctrl+C in this window to stop the server.")
    print(BANNER)
    print()

    # Replace current process with the app (no extra subprocess / wrapper layer)
    os.execv(sys.executable, [sys.executable, APP_FILE] + sys.argv[1:])


if __name__ == "__main__":
    main()
