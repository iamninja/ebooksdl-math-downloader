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

import re
import time
import urllib.parse
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://ebooksdl.cti.gr"
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

MATH_SUBJECTS = [
    ("Α' Γυμνασίου", "Μαθηματικά (Α' Γυμνασίου)"),
    ("Β' Γυμνασίου", "Μαθηματικά (Β' Γυμνασίου)"),
    ("Γ' Γυμνασίου", "Μαθηματικά (Γ' Γυμνασίου)"),
    ("Α' Λυκείου", "Μαθηματικά (Α' Λυκείου - Γενικής Παιδείας)"),
    ("Β' Λυκείου", "Μαθηματικά (Β' Λυκείου - Γενικής Παιδείας)"),
    ("Γ' Λυκείου", "Μαθηματικά (Γ' Λυκείου - Γενικής Παιδείας)"),
]


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


def view_links(soup):
    return [urljoin(BASE, a["href"]) for a in soup.find_all("a", href=re.compile(r"/view\?item="))]


def scrape_view_urls_for_subject(subject: str) -> list:
    params = urllib.parse.urlencode({
        "filtername": "subject",
        "filterquery": subject,
        "filtertype": "equals",
    })
    url = f"{BASE}/didaktika_paketa?{params}"
    print(f"\n  Fetching: {subject}")
    soup = get_soup(url)
    if soup is None:
        return []

    results = view_links(soup)
    page = 2
    next_link = soup.find("a", string=re.compile(r"επόμενη", re.I))
    while next_link and next_link.get("href") and next_link["href"] != "#":
        soup = get_soup(urljoin(BASE, next_link["href"]))
        if soup is None:
            break
        new = view_links(soup)
        if not new or set(new) <= set(results):
            break
        results.extend(new)
        next_link = soup.find("a", string=re.compile(r"επόμενη", re.I))
        page += 1
        time.sleep(1.0)

    print(f"  -> {len(results)} PDF links")
    return results


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
    items, seen = [], set()
    for class_label, subject in MATH_SUBJECTS:
        for v in scrape_view_urls_for_subject(subject):
            if v not in seen:
                seen.add(v)
                items.append((class_label, v))
        time.sleep(1.0)

    print(f"\n  Total unique PDF items: {len(items)}")
    if not items:
        print("\n[!] Nothing found. The site may be blocking requests; try again later.")
        return

    print("\n[2/3] Resolving direct PDF links...")
    queue = []
    for i, (class_label, view_url) in enumerate(items, 1):
        title, pdf_url = resolve_pdf_url(view_url)
        print(f"  [{i}/{len(items)}] {title[:60]}" + ("" if pdf_url else "  (no PDF, skipped)"))
        if pdf_url:
            queue.append((class_label, title, pdf_url, view_url))
        time.sleep(0.6)

    print(f"\n[3/3] Downloading {len(queue)} PDFs...\n")
    ok, failed = 0, []
    for i, (class_label, title, pdf_url, view_url) in enumerate(queue, 1):
        name = sanitize(title) or Path(pdf_url).stem
        dest = DOWNLOAD_DIR / sanitize(class_label) / f"{name}.pdf"
        print(f"[{i}/{len(queue)}] {class_label} — {title[:55]}")
        if download_pdf(pdf_url, dest, referer=view_url):
            ok += 1
        else:
            failed.append((class_label, title, pdf_url))
        time.sleep(1.0)

    print(f"\n{'=' * 65}")
    print(f"  Done: {ok}/{len(queue)} downloaded to {DOWNLOAD_DIR.resolve()}")
    for cls, t, u in failed:
        print(f"  FAILED [{cls}] {t}\n         {u}")
    print("=" * 65)


if __name__ == "__main__":
    main()
