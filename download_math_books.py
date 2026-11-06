#!/usr/bin/env python3
"""
Download all Math (Μαθηματικά) books for Γυμνάσιο and Λύκειο
from ebooksdl.cti.gr

Requirements:
    pip install requests beautifulsoup4 lxml

Usage:
    python download_math_books.py

Books are saved to ./math_books/<τάξη>/<τίτλος>.pdf
Already-downloaded files are skipped, so re-running only fetches new books.
"""

import html
import math
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://ebooksdl.cti.gr"
LISTING = f"{BASE}/didaktika_paketa"
PAGE_SIZE = 9
DOWNLOAD_DIR = Path("math_books")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
})

# At Λύκειο level maths is published under its branch names, not "Μαθηματικά".
MATH_NAME_RE = re.compile(r"μαθηματ|άλγεβρ|γεωμετρ", re.I)

# eduContext codes used by the listing API: 2=Δημοτικό, 3=Γυμνάσιο, 4=Λύκειο.
EDU_CONTEXTS = ("3", "4")

# Collection names mix Latin lookalikes into Greek text ("A΄ Λυκείου"), which
# breaks any exact-string comparison; fold them before matching or labelling.
LATIN_TO_GREEK = str.maketrans({
    "A": "Α", "B": "Β", "E": "Ε", "H": "Η", "I": "Ι", "K": "Κ", "M": "Μ",
    "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "X": "Χ", "Y": "Υ", "Z": "Ζ",
})


def sanitize(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()[:100]


def get_soup(url: str, retries: int = 3, delay: float = 2.0):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except requests.HTTPError as e:
            print(f"    [HTTP {e.response.status_code}] attempt {attempt + 1}/{retries}: {url}")
        except Exception as e:
            print(f"    [Error] attempt {attempt + 1}/{retries}: {e}")
        time.sleep(delay * (attempt + 1))
    return None


def clean_text(s: str) -> str:
    s = unicodedata.normalize("NFC", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def fold(s: str) -> str:
    return clean_text(s).translate(LATIN_TO_GREEK)


def api_collections(offset: int, page_total: int) -> dict:
    payload = {
        "action": "navigateCollections",
        "data": {
            "offset": {"offset": offset},
            "pageTotal": {"pageTotal": page_total},
            "filters": {},
        },
    }
    for attempt in range(3):
        try:
            r = SESSION.post(LISTING, json=payload, headers={"Referer": LISTING}, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"    [Error] offset {offset} attempt {attempt + 1}/3: {e}")
            time.sleep(2.0 * (attempt + 1))
    return {}


def grade_label(name: str) -> str:
    m = re.search(r"\(([^)]*)\)", fold(name))
    if not m:
        return "Χωρίς τάξη"
    return m.group(1).split(" - ")[0].strip() or "Χωρίς τάξη"


def discover_collections() -> list:
    # The POST API only answers once the session holds the cookie the page sets.
    SESSION.get(LISTING, timeout=30)

    first = api_collections(0, 1)
    total = int(first.get("totalCollections") or 0)
    if not total:
        return []
    pages = max(1, math.ceil(total / PAGE_SIZE))
    print(f"  {total} collections across {pages} pages")

    collections, seen = [], set()
    batch = first.get("collections", [])
    for page in range(1, pages + 1):
        if page > 1:
            batch = api_collections(PAGE_SIZE * (page - 1), pages).get("collections", [])
            time.sleep(0.4)
        if not batch:
            continue
        for c in batch:
            uuid = c.get("collectionUUID")
            if uuid and uuid not in seen:
                seen.add(uuid)
                collections.append(c)
        print(f"\r  page {page}/{pages} — {len(collections)} collections", end="", flush=True)
    print()
    return collections


def math_view_items(collections: list) -> list:
    items = []
    for c in collections:
        name = clean_text(c.get("name"))
        if str(c.get("eduContext")) not in EDU_CONTEXTS:
            continue
        if not MATH_NAME_RE.search(fold(name)):
            continue
        for book in c.get("books", []):
            for expr in book.get("expressions", []):
                url = (expr or {}).get("url", "")
                if "/view?item=" in url:
                    items.append({
                        "label": grade_label(name),
                        "subject": fold(name),
                        "publisher": clean_text(c.get("publisher")),
                        "view_url": urljoin(BASE, url),
                    })
    return items


def resolve_pdf_url(view_url: str):
    soup = get_soup(view_url)
    if soup is None:
        return None, None
    title_el = soup.find("title")
    raw = title_el.get_text(strip=True) if title_el else ""
    title = raw.replace(" - Προβολή", "").replace(" - PDF", "").strip() or "unknown"
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/bitstream/" in href and href.lower().endswith(".pdf"):
            return title, urljoin(BASE, href)
    return title, None


def download_pdf(pdf_url: str, dest: Path, referer: str = None) -> bool:
    if dest.exists():
        print(f"  [SKIP] {dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    headers = {"Accept": "application/pdf,application/octet-stream,*/*"}
    if referer:
        headers["Referer"] = referer
    try:
        with SESSION.get(pdf_url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r    {done / total * 100:5.1f}%  "
                              f"{done / 1048576:.1f}/{total / 1048576:.1f} MB", end="", flush=True)
        with open(tmp, "rb") as f:
            if f.read(5) != b"%PDF-":
                raise ValueError("response is not a PDF")
        tmp.rename(dest)
        print(f"\r  [OK]  {dest.name}  ({dest.stat().st_size / 1048576:.1f} MB)              ")
        return True
    except Exception as e:
        print(f"\r  [FAIL] {e}")
        tmp.unlink(missing_ok=True)
        return False


def main():
    print("=" * 65)
    print("  Math Books Downloader — ebooksdl.cti.gr")
    print("  Γυμνάσιο & Λύκειο — Βιβλία Μαθηματικών (PDF)")
    print("=" * 65)

    print("\n[1/3] Discovering books...")
    collections = discover_collections()
    if not collections:
        print("\n[!] Could not read the collection listing; try again later.")
        return

    items = math_view_items(collections)
    by_label = Counter(i["label"] for i in items)
    print(f"\n  Maths PDF items for Γυμνάσιο & Λύκειο: {len(items)}")
    for label in sorted(by_label):
        print(f"    {label}: {by_label[label]}")
    if not items:
        print("\n[!] Nothing matched the maths filter.")
        return

    print("\n[2/3] Resolving direct PDF links...")
    queue = []
    for i, item in enumerate(items, 1):
        title, pdf_url = resolve_pdf_url(item["view_url"])
        print(f"  [{i}/{len(items)}] {title[:60]}" + ("" if pdf_url else "  (no PDF, skipped)"))
        if pdf_url:
            queue.append({**item, "title": title, "pdf_url": pdf_url})
        time.sleep(0.6)

    print(f"\n[3/3] Downloading {len(queue)} PDFs...\n")
    ok, failed = 0, []
    for i, item in enumerate(queue, 1):
        # Several distinct collections share a title, so key the file on the handle id.
        handle_id = item["view_url"].rstrip("/").split("/")[-1]
        name = sanitize(item["title"]) or Path(item["pdf_url"]).stem
        dest = DOWNLOAD_DIR / sanitize(item["label"]) / f"{name} [{handle_id}].pdf"
        print(f"[{i}/{len(queue)}] {item['label']} — {item['title'][:55]}")
        if download_pdf(item["pdf_url"], dest, referer=item["view_url"]):
            ok += 1
        else:
            failed.append(item)
        time.sleep(1.0)

    print(f"\n{'=' * 65}")
    print(f"  Done: {ok}/{len(queue)} downloaded to {DOWNLOAD_DIR.resolve()}")
    for item in failed:
        print(f"  FAILED [{item['label']}] {item['title']}\n         {item['pdf_url']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
