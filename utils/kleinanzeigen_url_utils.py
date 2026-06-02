"""
Shared Kleinanzeigen URL utilities — used by both scrapers without circular imports.
"""

import re
from urllib.parse import urlparse, urlunparse, unquote


def inject_page(url: str, page_num: int) -> str:
    """
    Strip any existing seite/s-seite segment and inject the requested page number.

    Category URLs: seite:N is inserted immediately before the filter segment
    (the segment matching k?\\d*c\\d+), preserving any extra path components
    (e.g. anzeige:angebote, preis::N) that appear before it:
      /s-autos/anzeige:angebote/preis::15000/seite:2/c216+...
    Generic search URLs (no filter segment): s-seite:N appended before the query string.
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)

    # Strip any existing page segment
    segments = [
        s
        for s in path.strip("/").split("/")
        if s and not re.match(r"^s-seite:\d+$", s) and not re.match(r"^seite:\d+$", s)
    ]

    if page_num > 1:
        filter_idx = next(
            (i for i, s in enumerate(segments) if re.match(r"^k?\d*c\d+", s)),
            None,
        )
        if filter_idx is not None:
            # Insert seite:N directly before the filter segment
            segments.insert(filter_idx, f"seite:{page_num}")
        else:
            # Generic search: append s-seite:N before query string
            segments.append(f"s-seite:{page_num}")

    new_path = "/" + "/".join(segments)
    return urlunparse(parsed._replace(path=new_path))
