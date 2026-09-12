"""Pull the full Jellycat catalogue from the Searchspring index behind jellycat.com.

jellycat.com is a BigCommerce storefront whose listing pages are powered by
Searchspring (siteId d3slzq).  Its public search endpoint returns the whole
shoppable catalogue as JSON, which saves us from parsing any HTML:

    https://api.searchspring.net/api/search/search.json
        ?siteId=d3slzq&resultsPerPage=100&page=N&resultsFormat=native

The fields we care about, per result:

    uid                 stable product id (primary key across runs)
    name, sku           display name and SKU
    custom_url          site-relative slug, e.g. "/ulrich-wolf/"
    price               GBP, as a string
    imageUrl            500x500 CDN thumbnail
    ss_in_stock         "1" / "0"
    ss_product_status   "Live" / "Coming Soon"
    ss_badge_title      "New In" / "Back in Stock" / "Available 16th September" / ...
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

SITE_ID = "d3slzq"
API = "https://api.searchspring.net/api/search/search.json"
BASE_URL = "https://jellycat.com"
PER_PAGE = 100

# Identify ourselves honestly rather than pretending to be a browser; this is a
# low-volume personal tracker (12 requests a day).
USER_AGENT = (
    "jellycat-release-tracker/1.0 "
    "(+https://github.com/Yoyo1112/jellycat-release-tracker; personal restock tracker)"
)

MAX_ATTEMPTS = 3
PAGE_DELAY = 0.3
MAX_PAGES = 30  # guard against a runaway pagination loop


class FetchError(RuntimeError):
    """Raised when the catalogue could not be retrieved in full."""


def _get_page(page: int, timeout: int = 30) -> dict:
    url = (
        f"{API}?siteId={SITE_ID}&resultsPerPage={PER_PAGE}"
        f"&page={page}&resultsFormat=native"
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/"}
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            last_error = error
            if attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt)  # 2s, then 4s

    raise FetchError(f"page {page} failed after {MAX_ATTEMPTS} attempts: {last_error}")


def _normalise(result: dict) -> tuple[str, dict] | None:
    """Reduce a Searchspring result to the handful of fields we track."""
    uid = str(result.get("uid") or "").strip()
    slug = (result.get("custom_url") or "").strip()
    if not uid or not slug:
        return None

    return uid, {
        "name": (result.get("name") or "").strip(),
        "sku": (result.get("sku") or "").strip(),
        "url": slug,
        "price": str(result.get("price") or "").strip(),
        "in_stock": str(result.get("ss_in_stock") or "") == "1",
        "status": (result.get("ss_product_status") or "").strip(),
        "badge": (result.get("ss_badge_title") or "").strip(),
        "image": (result.get("thumbnailImageUrl") or result.get("imageUrl") or "").strip(),
    }


def fetch_catalogue() -> dict[str, dict]:
    """Return every catalogue product keyed by Searchspring uid.

    Raises FetchError if any page cannot be retrieved, so that a partial
    catalogue never reaches the diff (which would look like mass delisting).
    """
    products: dict[str, dict] = {}
    page = 1
    total_pages = 1

    while page <= total_pages and page <= MAX_PAGES:
        payload = _get_page(page)
        pagination = payload.get("pagination") or {}
        total_pages = int(pagination.get("totalPages") or 1)

        results = payload.get("results") or []
        if not results:
            raise FetchError(f"page {page} of {total_pages} returned no results")

        for result in results:
            entry = _normalise(result)
            if entry:
                products[entry[0]] = entry[1]

        page += 1
        if page <= total_pages:
            time.sleep(PAGE_DELAY)

    if not products:
        raise FetchError("catalogue came back empty")

    return products


def product_url(product: dict) -> str:
    """Absolute URL for a tracked product."""
    slug = product.get("url") or ""
    if slug.startswith("http"):
        return slug
    return f"{BASE_URL}{slug}"
