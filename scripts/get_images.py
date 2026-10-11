"""
get_images.py - build the pizza vs. sushi dataset for OPIM 5509 Assignment 4 (Route B).

Steps:
  1. Collect ~230 candidate images per class from Wikimedia Commons (free, official API,
     real photos), using several varied search queries per class. Bing image search is
     used as a fallback only if Commons comes up short.
  2. Keep only results whose file name / page / title actually mentions the class word.
  3. Clean: drop files < 4 KB, files PIL cannot verify, and exact duplicates (MD5).
  4. Normalize: convert to RGB .jpg, longest side <= 400 px (keeps the zip small).
  5. Print per-class counts.

Why not icrawler?  icrawler 0.6.10 was tried first: its Google parser crashes, and Bing
returned off-topic images (fantasy dragons for "dragon roll sushi", TV shows, memes) once
it started throttling us. The keyword filter in step 2 is what keeps that junk out.

Run:   python scripts/get_images.py            (from the A04 folder)
Then eyeball images/pizza and images/sushi, delete wrong images, and run:
       python scripts/make_zip.py
"""
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the A04 folder
RAW_DIR = os.path.join(ROOT, "raw_images")   # untouched downloads
OUT_DIR = os.path.join(ROOT, "images")       # cleaned images that go into the zip

TARGET_PER_CLASS = 230   # collect extra: manual review will remove some
MIN_BYTES = 4096
MAX_SIDE = 400

# Wikimedia asks API clients to identify themselves
HEADERS = {"User-Agent": "OPIM5509-A4-dataset/1.0 (https://github.com/UdayAnalyst/OPIM5509-A4)"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# varied queries per class -> more visual diversity (styles, angles, settings)
QUERIES = {
    "pizza": ["pizza", "pizza margherita", "pepperoni pizza", "neapolitan pizza",
              "pizza slice", "homemade pizza", "deep dish pizza", "vegetable pizza"],
    "sushi": ["sushi", "nigiri sushi", "maki sushi", "sushi platter",
              "sushi roll", "salmon sushi", "conveyor belt sushi", "sushi set"],
}


def polite_get(url, **kw):
    """GET with retries: back off when a server says 429 (too many requests)."""
    for attempt in range(6):
        r = requests.get(url, timeout=20, **kw)
        if r.status_code != 429:
            return r
        wait = int(r.headers.get("Retry-After", 0) or 0) or 5 * 2 ** attempt   # 5,10,20,40s...
        time.sleep(min(wait, 60))
    return r


def relevant(cls, *texts):
    """True if the class word appears in any of the given strings (file name, title, URL)."""
    return cls in " ".join(texts).lower()


def commons_urls(cls, query, limit=150):
    """Search Wikimedia Commons files; return {title: 400px-thumbnail URL}."""
    found = {}
    cont = {}
    while len(found) < limit:
        params = {"action": "query", "format": "json", "generator": "search",
                  "gsrnamespace": 6,                         # namespace 6 = files
                  "gsrsearch": f"{query} filetype:bitmap",   # photos only, no SVG/PDF
                  "gsrlimit": 50, "prop": "imageinfo", "iiprop": "url|mime",
                  "iiurlwidth": MAX_SIDE, **cont}            # server-side resized thumbnail
        r = polite_get("https://commons.wikimedia.org/w/api.php",
                       params=params, headers=HEADERS).json()
        time.sleep(1)   # be gentle with the API
        for page in r.get("query", {}).get("pages", {}).values():
            info = page.get("imageinfo", [{}])[0]
            if info.get("mime") in ("image/jpeg", "image/png") and relevant(cls, page["title"]):
                found[page["title"]] = info.get("thumburl") or info["url"]
        cont = r.get("continue", {})
        if not cont:
            break
    return found


def bing_urls(cls, query, n=35):
    """Fallback: first page of Bing image results, filtered by the class keyword."""
    r = requests.get("https://www.bing.com/images/async",
                     params={"q": query, "first": 0, "count": n},
                     headers=BROWSER_UA, timeout=15)
    found = {}
    for m in re.findall(r' m="(\{.*?\})"', r.text):          # one JSON blob per result
        meta = json.loads(html.unescape(m))
        if relevant(cls, meta.get("murl", ""), meta.get("purl", ""), meta.get("t", "")):
            found[meta["murl"]] = meta["murl"]
    return found


def download(url, path):
    try:
        r = polite_get(url, headers=HEADERS)
        if r.ok and r.headers.get("Content-Type", "").startswith("image"):
            with open(path, "wb") as fh:
                fh.write(r.content)
    except Exception:
        pass  # dead links are common; cleaning handles whatever is missing


def crawl(cls, queries):
    folder = os.path.join(RAW_DIR, cls)
    os.makedirs(folder, exist_ok=True)
    urls = {}   # title/url -> download url (dict = de-duplicated across queries)
    for q in queries:
        new = commons_urls(cls, q)
        urls.update(new)
        print(f"[{cls}] Commons '{q}': {len(new)} results ({len(urls)} unique so far)")
        if len(urls) >= TARGET_PER_CLASS:
            break
    if len(urls) < TARGET_PER_CLASS:   # top up from Bing if Commons came up short
        for q in queries:
            try:
                urls.update(bing_urls(cls, q))
            except Exception as e:
                print(f"[{cls}] Bing failed for '{q}': {e}")
        print(f"[{cls}] after Bing fallback: {len(urls)} unique")
    with ThreadPoolExecutor(max_workers=3) as pool:   # parallel downloads
        for k, u in enumerate(list(urls.values())[:TARGET_PER_CLASS + 20]):
            pool.submit(download, u, os.path.join(folder, f"{k:04d}.img"))


def clean_and_convert(cls):
    """Filter raw images and write normalized RGB jpgs to images/<cls>/."""
    out = os.path.join(OUT_DIR, cls)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    seen = set()  # MD5 hashes of raw bytes, for exact-duplicate removal
    stats = {"small": 0, "corrupt": 0, "dup": 0, "kept": 0}

    for f in sorted(os.listdir(os.path.join(RAW_DIR, cls))):
        path = os.path.join(RAW_DIR, cls, f)
        if os.path.getsize(path) < MIN_BYTES:  # thumbnails / error pages
            stats["small"] += 1
            continue
        with open(path, "rb") as fh:
            digest = hashlib.md5(fh.read()).hexdigest()
        if digest in seen:
            stats["dup"] += 1
            continue
        try:
            with Image.open(path) as img:
                img.verify()  # cheap integrity check
            with Image.open(path) as img:  # re-open: verify() invalidates the object
                img = img.convert("RGB")
                img.thumbnail((MAX_SIDE, MAX_SIDE))  # longest side <= 400, keeps aspect
                if min(img.size) < 64:  # tiny icons are useless for training
                    stats["small"] += 1
                    continue
                seen.add(digest)
                stats["kept"] += 1
                img.save(os.path.join(out, f"{cls}_{stats['kept']:04d}.jpg"), "JPEG", quality=85)
        except Exception:
            stats["corrupt"] += 1
    return stats


def main():
    skip_crawl = "--clean-only" in sys.argv  # re-run cleaning without re-downloading
    for cls, queries in QUERIES.items():
        if not skip_crawl:
            shutil.rmtree(os.path.join(RAW_DIR, cls), ignore_errors=True)
            crawl(cls, queries)
    print("\n=== Cleaning ===")
    for cls in QUERIES:
        s = clean_and_convert(cls)
        print(f"{cls:8s} kept={s['kept']:4d}  too_small={s['small']:3d}  "
              f"corrupt={s['corrupt']:3d}  duplicates={s['dup']:3d}")
        if s["kept"] < 150:
            print(f"  WARNING: {cls} has fewer than 150 images - add another query and re-run")


if __name__ == "__main__":
    main()
