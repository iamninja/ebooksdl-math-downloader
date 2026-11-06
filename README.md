# ebooksdl-math-downloader

Downloads the math textbooks (Μαθηματικά) for Γυμνάσιο and Λύκειο from the
[«Μελίσπη» digital library](https://ebooksdl.cti.gr/) as PDFs.

```bash
pip install -r requirements.txt
python download_math_books.py
```

PDFs are saved to `math_books/<τάξη>/`. Files already downloaded are skipped,
so running it again only fetches new books.

Note: the site blocks requests from cloud servers, so run this from a home or
office connection.
