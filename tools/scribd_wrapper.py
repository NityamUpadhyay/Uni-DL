"""
tools/scribd_wrapper.py
Wrapper around themrsami/scribd-downloader from GitHub.

The upstream script (scribd-downloader.py) is INTERACTIVE — it calls
input("Input link Scribd: ") and writes the PDF to the current directory
using a filename derived from the URL.

This wrapper:
  1. Clones + installs the tool on first use (safely handles partial clones)
  2. Runs the script with the URL fed via stdin
  3. Renames the output PDF to the caller-specified path
  4. Yields progress lines back to the job worker
"""

from __future__ import annotations
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

TOOLS_DIR    = Path(__file__).resolve().parent
REPO_DIR     = TOOLS_DIR / "scribd-downloader"
REPO_URL     = "https://github.com/themrsami/scribd-downloader.git"
ENTRY_SCRIPT = REPO_DIR / "scribd-downloader.py"   # hyphen, not underscore


# ── helpers ───────────────────────────────────────────────────────────────────

def _git_available() -> bool:
    return shutil.which("git") is not None


def _force_remove(path: Path) -> None:
    """Remove a directory tree, handling Windows read-only files inside .git."""
    def _on_error(func, p, _exc_info):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=_on_error)


def _pip_install_requirements() -> str | None:
    req_file = REPO_DIR / "requirements.txt"
    if not req_file.exists():
        return None
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"],
        capture_output=True, text=True, timeout=300,
    )
    return None if result.returncode == 0 else f"pip install failed:\n{result.stderr.strip()}"


# ── installation ──────────────────────────────────────────────────────────────

def ensure_installed() -> str | None:
    """
    Ensure the scribd-downloader tool is present and ready.
    Returns None on success, or an error string on failure.
    """
    if ENTRY_SCRIPT.exists():
        return None     # already installed

    if not _git_available():
        return (
            "git is not installed or not on PATH. "
            "Install Git from https://git-scm.com/ and restart the app."
        )

    # Remove any partial / broken clone so git-clone can start fresh
    if REPO_DIR.exists():
        try:
            _force_remove(REPO_DIR)
        except Exception as e:
            return f"Could not remove broken clone at {REPO_DIR}: {e}"

    # Clone fresh
    result = subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return f"git clone failed:\n{result.stderr.strip()}"

    if not ENTRY_SCRIPT.exists():
        return (
            f"Cloned the repo but {ENTRY_SCRIPT.name} was not found. "
            "The repository structure may have changed — check "
            "https://github.com/themrsami/scribd-downloader"
        )

    return _pip_install_requirements()


# ── URL helpers ───────────────────────────────────────────────────────────────

def _expected_pdf_name(url: str) -> str:
    """
    Replicate get_filename_from_url() from the upstream script so we know
    what filename it will create in the working directory.
    """
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    last_segment = path.split("/")[-1] if path else "scribd_document"
    return f"{unquote(last_segment)}.pdf"


# ── runner ────────────────────────────────────────────────────────────────────

def run_scribd(url: str, out_path: str):
    """
    Generator: drives the scribd-downloader script non-interactively.

    The upstream script uses input() for its URL prompt, so we feed the URL
    via stdin.  It saves the PDF to its CWD (REPO_DIR) with a filename derived
    from the URL; we then move it to out_path.

    Yields:
        str  — a line of stdout/stderr output
        dict — final item: {"returncode": int}

    Raises:
        RuntimeError — if the tool couldn't be set up.
    """
    err = ensure_installed()
    if err:
        raise RuntimeError(err)

    expected_pdf = REPO_DIR / _expected_pdf_name(url)

    proc = subprocess.Popen(
        [sys.executable, str(ENTRY_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        cwd=str(REPO_DIR),
    )

    # Send the URL as the answer to input("Input link Scribd: ")
    try:
        proc.stdin.write(url + "\n")
        proc.stdin.flush()
        proc.stdin.close()
    except Exception:
        pass

    for line in proc.stdout:
        yield line.rstrip()

    proc.wait()
    rc = proc.returncode

    # Move the output PDF to the caller's requested path
    if rc == 0 and expected_pdf.exists():
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(expected_pdf), out_path)
        yield f"Saved → {out_path}"
    elif rc == 0 and not expected_pdf.exists():
        # Script succeeded but file is somewhere else — search CWD
        candidates = list(REPO_DIR.glob("*.pdf"))
        if candidates:
            # Use the most recently modified
            newest = max(candidates, key=lambda p: p.stat().st_mtime)
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(newest), out_path)
            yield f"Saved → {out_path}"
        else:
            rc = 1
            yield "Warning: script exited 0 but no PDF was found in the output directory."

    yield {"returncode": rc}
