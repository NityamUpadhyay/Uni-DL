"""
tools/slideshare_dl.py
Custom SlideShare downloader — no browser needed.

Extracts slide image URLs from the page's embedded JSON (__NEXT_DATA__
or legacy CDN patterns), downloads all slides, and merges them into
a single PDF using Pillow.
"""

from __future__ import annotations
import json
import re
from io import BytesIO
from pathlib import Path

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from PIL import Image
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_slide_urls(html: str) -> list[str]:
    """Try multiple strategies to extract slide image URLs."""
    urls: list[str] = []

    # Strategy 1 — Next.js __NEXT_DATA__ JSON blob (current SlideShare)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            page_props = data.get("props", {}).get("pageProps", {})
            # Try several known key names
            ss = (
                page_props.get("slideshow") or
                page_props.get("presentation") or
                page_props.get("ssProps", {}).get("slideshow") or
                {}
            )
            slides = ss.get("slides") or ss.get("slideImages") or []
            for slide in slides:
                if isinstance(slide, dict):
                    img = (
                        slide.get("imageURL") or
                        slide.get("image") or
                        slide.get("url") or
                        slide.get("src")
                    )
                    if img:
                        urls.append(img)
                elif isinstance(slide, str) and slide.startswith("http"):
                    urls.append(slide)
        except Exception:
            pass

    if urls:
        return urls

    # Strategy 2 — Inline JSON patterns in any <script> tag
    for pattern in [
        r'"slideImages"\s*:\s*(\[.*?\])',
        r'"slides"\s*:\s*(\[.*?\])',
        r'"slide_images"\s*:\s*(\[.*?\])',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                items = json.loads(m.group(1))
                for item in items:
                    if isinstance(item, dict):
                        img = (
                            item.get("imageURL") or
                            item.get("image") or
                            item.get("url") or
                            item.get("src")
                        )
                        if img:
                            urls.append(img)
                    elif isinstance(item, str) and item.startswith("http"):
                        urls.append(item)
                if urls:
                    return urls
            except Exception:
                pass

    # Strategy 3 — Legacy CDN URLs embedded as attributes / data-src
    cdn_pattern = re.compile(
        r'https://(?:image|cdn)\.slidesharecdn\.com/'
        r'[A-Za-z0-9_\-]+/[0-9]+/[A-Za-z0-9_\-/]+\.jpg',
    )
    seen: set[str] = set()
    for raw_url in cdn_pattern.findall(html):
        base = raw_url.split("?")[0]
        if base not in seen:
            seen.add(base)
            urls.append(base)

    return urls


def download(url: str, out_pdf: str, progress_cb=None) -> None:
    """
    Download a SlideShare URL and save all slides as a single PDF.

    Args:
        url        : Full SlideShare presentation URL.
        out_pdf    : Absolute path for the output .pdf file.
        progress_cb: Optional callable(current_slide, total_slides).

    Raises:
        RuntimeError on any unrecoverable error.
    """
    if not REQUESTS_OK:
        raise RuntimeError("'requests' is not installed. Run: pip install requests")
    if not PILLOW_OK:
        raise RuntimeError("'Pillow' is not installed. Run: pip install Pillow")

    # Fetch the presentation page
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch SlideShare page: {e}") from e

    slide_urls = _extract_slide_urls(resp.text)

    if not slide_urls:
        raise RuntimeError(
            "Could not find slide images in this SlideShare page.\n"
            "The presentation may be private, login-gated, or SlideShare may "
            "have changed its page structure.\n"
            "Try opening the URL in your browser first to confirm it is public."
        )

    # Download each slide
    images: list[Image.Image] = []
    total = len(slide_urls)
    for i, img_url in enumerate(slide_urls, 1):
        if progress_cb:
            try:
                progress_cb(i, total)
            except Exception:
                pass
        try:
            img_resp = requests.get(img_url, headers=HEADERS, timeout=20)
            img_resp.raise_for_status()
            img = Image.open(BytesIO(img_resp.content)).convert("RGB")
            images.append(img)
        except Exception as e:
            # Skip bad slides rather than aborting entirely
            print(f"  Warning: could not download slide {i}: {e}", flush=True)

    if not images:
        raise RuntimeError("No slide images were successfully downloaded.")

    # Merge into a single PDF
    Path(out_pdf).parent.mkdir(parents=True, exist_ok=True)
    first, rest = images[0], images[1:]
    first.save(out_pdf, format="PDF", save_all=True, append_images=rest)
