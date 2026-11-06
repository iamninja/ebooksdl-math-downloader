# ebooksdl-math-downloader

Downloads the math textbooks (Μαθηματικά) for Γυμνάσιο and Λύκειο from the
[«Μελίσπη» digital library](https://ebooksdl.cti.gr/) as PDFs.

```bash
pip install -r requirements.txt
python download_math_books.py
```

PDFs are saved to `math_books/<τάξη>/`. Files already downloaded are skipped,
so running it again only fetches new books.

Expect ~1 GB for the current 19 books.

## What it finds

| Τάξη | Books |
| --- | --- |
| Α΄ Γυμνασίου | 3 |
| Β΄ Γυμνασίου | 3 |
| Γ΄ Γυμνασίου | 3 |
| Α΄ Λυκείου | 10 |

Β΄ and Γ΄ Λυκείου are absent on purpose: the library has no maths collections
for those years. There are also 9 Μαθηματικά collections for Δημοτικό
(`eduContext` 2) that this script deliberately skips.

## How discovery works

Notes from reverse-engineering the site, so the next person does not have to.

**The listing is a JSON API, not HTML.** Filtering by query string
(`/didaktika_paketa?filtername=subject&filterquery=...`) does nothing — the page
is rendered client-side by `/static/js/collection-in-mitroo.js`. Collections come
from `POST /didaktika_paketa` with a JSON body:

```json
{"action": "navigateCollections",
 "data": {"offset": {"offset": 0}, "pageTotal": {"pageTotal": 26}, "filters": {}}}
```

Quirks worth knowing:

- **A plain `GET` must come first.** The POST returns an empty `200` until the
  session holds the `_sn` cookie that the HTML page sets.
- **`action: searchCollections` returns an empty body.** Only
  `navigateCollections` answers, so paging over everything with `filters: {}` is
  the reliable route. 9 collections per page; page count is
  `ceil(totalCollections / 9)`.
- **A silent empty result looks exactly like a block.** Bad filters return
  `200` with a well-formed but empty page, so "found nothing" usually means the
  query shape is wrong, not that you are being throttled.

**Subject names cannot be matched as literal strings.** Two separate traps:

- They mix Latin lookalikes into Greek text — `A΄ Λυκείου` uses a Latin `A`,
  and the accent is a Greek tonos (`΄`, U+0384), not an ASCII apostrophe. Titles
  also arrive HTML-escaped (`&#x2F;`). Hence the `clean_text`/`fold` helpers.
- At Λύκειο level there is no `Μαθηματικά` collection at all. Maths is published
  as **Άλγεβρα**, **Γεωμετρία** and **Στοχαστικά Μαθηματικά**, which is why the
  filter is a regex over those names plus an `eduContext` check
  (2=Δημοτικό, 3=Γυμνάσιο, 4=Λύκειο).

**Getting from a collection to a PDF.** Each collection carries
`books[].expressions[]`; the entry with `type: "4"` holds a `/view?item=<handle>`
URL. That page links the real file as
`/bitstream/<handle>/<n>/<file>.pdf` (also mirrored at `/retrieve/<uuid>/...`).
Downloads are verified by checking for the `%PDF-` magic bytes, since an error
page would otherwise be saved as a valid-looking file.

**Filenames include the handle id.** Four distinct collections are all titled
"Άλγεβρα Α΄ Λυκείου" (different publishers), so the id is what keeps them from
overwriting each other.

Note: the site may block requests from cloud servers, so prefer a home or
office connection.
