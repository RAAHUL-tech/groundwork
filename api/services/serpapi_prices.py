"""
Live Home Depot material pricing via SerpApi (Home Depot engine).

Public API (drop-in replacement for apify_prices):
    fetch_hd_price(label, zip_code)           → HDPrice | None
    fetch_hd_prices(labels, zip_code)         → dict[label, HDPrice | None]

Each call:
  1. Checks Redis cache (6-hr TTL)
  2. On miss: calls SerpApi engine=home_depot (one HTTP request per item)
  3. Parses product list → picks median-priced product
  4. Normalises price to our unit (sq_ft / linear_ft / each)
  5. Caches result; returns None on any failure (caller uses hardcoded table)

Requires SERPAPI_KEY in environment; skips gracefully if absent.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from dataclasses import dataclass

import requests

from config import Config

logger = logging.getLogger(__name__)

SERPAPI_SEARCH_URL = "https://serpapi.com/search"
REQUEST_TIMEOUT    = 15   # seconds per SerpApi call (much faster than Apify actor spin-up)
PARALLEL_WORKERS   = 8


@dataclass
class HDPrice:
    unit_price:    float
    unit:          str
    product_title: str
    product_url:   str
    hd_raw_price:  float
    hd_raw_unit:   str
    source:        str   # "serpapi" | "cache"


# ── Per-item search configuration ─────────────────────────────────────────────
# query:    search string sent to Home Depot
# hd_unit:  how HD sells this item
# our_unit: pricing engine unit
# factor:   multiply HD raw price by this → our unit price
# min/max:  sanity-check bounds on our_unit price (catches bad scrapes)

_ITEM_CFG: dict[str, dict] = {
    # Kitchen
    "cabinets": {
        "query":    "kitchen wall cabinet wood 30 inch ready assemble",
        "hd_unit":  "each",
        "our_unit": "linear_ft",
        "factor":   1 / 2.5,    # 30-in box ≈ 2.5 linear ft
        "min": 40,   "max": 600,
    },
    "countertop": {
        "query":    "quartz countertop kitchen",
        "hd_unit":  "sq_ft",
        "our_unit": "sq_ft",
        "factor":   1.0,
        "min": 5,   "max": 250,
    },
    "sink": {
        "query":    "kitchen sink undermount stainless steel",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 80,   "max": 2500,
    },
    "range": {
        "query":    "electric range freestanding 30 inch stainless",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 400,   "max": 6000,
    },
    "dishwasher": {
        "query":    "dishwasher built-in stainless 24 inch",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 300,   "max": 3000,
    },
    "refrigerator": {
        "query":    "refrigerator french door stainless counter depth",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 600,   "max": 8000,
    },
    "microwave": {
        "query":    "over-the-range microwave stainless 30 inch",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 100,   "max": 1500,
    },
    "backsplash": {
        "query":    "subway tile backsplash ceramic white",
        "hd_unit":  "sq_ft",
        "our_unit": "sq_ft",
        "factor":   1.0,
        "min": 2,    "max": 60,
    },
    "flooring": {
        "query":    "luxury vinyl plank flooring waterproof",
        "hd_unit":  "sq_ft",
        "our_unit": "sq_ft",
        "factor":   1.0,
        "min": 0.5,  "max": 20,
    },
    # Bathroom
    "vanity": {
        "query":    "bathroom vanity with sink 36 inch white",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 150,   "max": 4000,
    },
    "toilet": {
        "query":    "toilet elongated two piece comfort height",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 100,   "max": 1500,
    },
    "tub": {
        "query":    "bathtub alcove soaking white 60 inch",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 200,   "max": 5000,
    },
    "shower": {
        "query":    "shower kit complete base walls glass door",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 200,   "max": 4000,
    },
    "tile_floor": {
        "query":    "floor tile porcelain 12x12",
        "hd_unit":  "sq_ft",
        "our_unit": "sq_ft",
        "factor":   1.0,
        "min": 1,    "max": 40,
    },
    "tile_wall": {
        "query":    "wall tile ceramic subway 3x6",
        "hd_unit":  "sq_ft",
        "our_unit": "sq_ft",
        "factor":   1.0,
        "min": 1,    "max": 40,
    },
    "faucet": {
        "query":    "bathroom faucet single hole chrome",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 30,   "max": 1000,
    },
    "mirror": {
        "query":    "bathroom mirror frameless rectangle",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 30,   "max": 800,
    },
    # General
    "window": {
        "query":    "double hung window replacement vinyl",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 100,   "max": 3000,
    },
    "door": {
        "query":    "interior door prehung hollow core 80 inch",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 80,   "max": 1500,
    },
    "lighting_fixture": {
        "query":    "ceiling light fixture LED flush mount",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 20,   "max": 800,
    },
    "drywall": {
        "query":    "drywall sheet 4x8 half inch",
        "hd_unit":  "each",
        "our_unit": "sq_ft",
        "factor":   1 / 32,    # 4×8 sheet = 32 sq ft
        "min": 0.3,  "max": 5,
    },
    "paint": {
        "query":    "interior paint gallon eggshell",
        "hd_unit":  "each",
        "our_unit": "sq_ft",
        "factor":   1 / 300,   # 1 gal ÷ 300 sq ft (2 coats, ~10% waste)
        "min": 0.05, "max": 1.5,
    },
    "ceiling_fan": {
        "query":    "ceiling fan with light remote control 52 inch",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 40,   "max": 800,
    },
    "closet": {
        "query":    "closet organizer system wood",
        "hd_unit":  "each",
        "our_unit": "each",
        "factor":   1.0,
        "min": 100,   "max": 3000,
    },
}

_LABOR_ONLY = {"ac_unit_removal", "hvac_disconnect"}


# ── Redis cache ────────────────────────────────────────────────────────────────

def _redis():
    try:
        import redis as redis_lib
        r = redis_lib.from_url(
            Config.REDIS_URL,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        r.ping()
        return r
    except Exception:
        return None


def _cache_key(label: str) -> str:
    return f"hd_price:serpapi:v1:{label}"


# ── SerpApi fetch ──────────────────────────────────────────────────────────────

def _extract_price(product: dict) -> float | None:
    """Pull numeric price from a SerpApi Home Depot product dict."""
    # SerpApi home_depot engine returns 'price' as a float directly
    val = product.get("price")
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    # Some responses embed price inside 'primary_price' or as a string
    for field in ("primary_price", "sale_price", "regular_price"):
        val = product.get(field)
        if val is None:
            continue
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
        if isinstance(val, str):
            try:
                cleaned = val.replace("$", "").replace(",", "").strip()
                parsed = float(cleaned)
                if parsed > 0:
                    return parsed
            except ValueError:
                pass
    return None


def _median_product(products: list[dict]) -> dict | None:
    """Return the product whose price is closest to the median."""
    priced = [(p, _extract_price(p)) for p in products]
    priced = [(p, px) for p, px in priced if px]
    if not priced:
        return None
    priced.sort(key=lambda x: x[1])
    return priced[len(priced) // 2][0]


def _serpapi_search(label: str, cfg: dict, zip_code: str = "90210") -> HDPrice | None:
    """
    Query SerpApi's Home Depot engine for one item. Returns HDPrice or None.
    Falls back gracefully if the API key is missing or the request fails.
    """
    if not Config.SERPAPI_KEY:
        return None

    params = {
        "engine":       "home_depot",
        "q":            cfg["query"],
        "delivery_zip": zip_code,
        "api_key":      Config.SERPAPI_KEY,
        "ps":           12,   # number of products (max results per page)
    }

    try:
        t0 = time.monotonic()
        resp = requests.get(SERPAPI_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info("[serpapi] %s — HTTP %d  %.0fms  zip=%s", label, resp.status_code, elapsed_ms, zip_code)

        if resp.status_code == 401:
            logger.error("[serpapi] Invalid API key — check SERPAPI_KEY in .env")
            return None

        if resp.status_code != 200:
            logger.warning("[serpapi] %s non-200 (%d): %s", label, resp.status_code, resp.text[:200])
            return None

        data = resp.json()

        # SerpApi home_depot engine puts results in "products"
        products: list[dict] = data.get("products") or []

        if not products:
            logger.warning("[serpapi] %s — empty result set (zip=%s)", label, zip_code)
            return None

        best = _median_product(products)
        if not best:
            return None

        raw_price = _extract_price(best)
        if not raw_price:
            return None

        our_price = round(raw_price * cfg["factor"], 4)
        lo, hi = cfg.get("min", 0), cfg.get("max", 99999)
        if not (lo <= our_price <= hi):
            logger.warning("[serpapi] %s out-of-range $%.2f/%s (raw=$%.2f) — discarding",
                           label, our_price, cfg["our_unit"], raw_price)
            return None

        title = (
            best.get("title") or best.get("description") or "Home Depot product"
        )[:80]
        product_url = best.get("link") or "https://www.homedepot.com"

        logger.info("[serpapi] ✓ %s → $%.2f/%s  (%s)", label, our_price, cfg["our_unit"], title[:40])
        return HDPrice(
            unit_price=our_price,
            unit=cfg["our_unit"],
            product_title=title,
            product_url=product_url,
            hd_raw_price=raw_price,
            hd_raw_unit=cfg["hd_unit"],
            source="serpapi",
        )

    except Exception as exc:
        logger.warning("[serpapi] %s — request failed: %s", label, exc)
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_hd_price(label: str, zip_code: str = "90210") -> HDPrice | None:
    """
    Fetch live HD price for one item label (zip-code-aware delivery lookup).
    Checks Redis cache first; calls SerpApi on miss; caches success.
    Returns None if the item is labor-only, unconfigured, or any fetch fails.
    """
    if label in _LABOR_ONLY or label not in _ITEM_CFG:
        return None

    cfg = _ITEM_CFG[label]
    key = _cache_key(label)
    r   = _redis()

    if r:
        try:
            raw = r.get(key)
            if raw:
                d = json.loads(raw)
                logger.info("[serpapi] cache ✓ %s → $%.2f/%s", label, d["unit_price"], d["unit"])
                return HDPrice(**{**d, "source": "cache"})
        except Exception as exc:
            logger.warning("[serpapi] cache read error: %s", exc)

    result = _serpapi_search(label, cfg, zip_code=zip_code)

    if result and r:
        try:
            payload = {
                "unit_price":    result.unit_price,
                "unit":          result.unit,
                "product_title": result.product_title,
                "product_url":   result.product_url,
                "hd_raw_price":  result.hd_raw_price,
                "hd_raw_unit":   result.hd_raw_unit,
            }
            r.set(key, json.dumps(payload), ex=Config.HD_PRICE_CACHE_TTL)
        except Exception as exc:
            logger.warning("[serpapi] cache write error: %s", exc)

    return result


def fetch_hd_prices(labels: list[str], zip_code: str = "90210") -> dict[str, HDPrice | None]:
    """
    Fetch HD prices for multiple item labels in parallel.
    Returns dict mapping each label → HDPrice (or None on failure).
    """
    if not labels:
        return {}

    results: dict[str, HDPrice | None] = {}
    to_fetch = [l for l in labels if l in _ITEM_CFG and l not in _LABOR_ONLY]

    for l in labels:
        if l not in to_fetch:
            results[l] = None

    if not to_fetch:
        return results

    # Check all caches first
    r = _redis()
    cache_misses: list[str] = []
    if r:
        for label in to_fetch:
            try:
                raw = r.get(_cache_key(label))
                if raw:
                    d = json.loads(raw)
                    results[label] = HDPrice(**{**d, "source": "cache"})
                    logger.info("[serpapi] cache ✓ %s → $%.2f/%s", label, d["unit_price"], d["unit"])
                else:
                    cache_misses.append(label)
            except Exception:
                cache_misses.append(label)
    else:
        cache_misses = list(to_fetch)

    if not cache_misses:
        return results

    logger.info("[serpapi] fetching %d item(s) in parallel: %s", len(cache_misses), cache_misses)

    with ThreadPoolExecutor(max_workers=min(PARALLEL_WORKERS, len(cache_misses))) as ex:
        futures = {ex.submit(fetch_hd_price, label, zip_code): label for label in cache_misses}
        try:
            for future in as_completed(futures, timeout=REQUEST_TIMEOUT + 5):
                label = futures[future]
                try:
                    results[label] = future.result()
                except Exception as exc:
                    logger.warning("[serpapi] %s future error: %s", label, exc)
                    results[label] = None
        except FuturesTimeout:
            logger.warning("[serpapi] batch timeout — partial results returned")
            for label in cache_misses:
                if label not in results:
                    results[label] = None

    live_count  = sum(1 for v in results.values() if v and v.source == "serpapi")
    cache_count = sum(1 for v in results.values() if v and v.source == "cache")
    logger.info("[serpapi] batch done — %d live, %d cached, %d fallback",
                live_count, cache_count, sum(1 for v in results.values() if not v))
    return results
