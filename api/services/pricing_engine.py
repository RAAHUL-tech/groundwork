"""
Cost engine — B9/B10.

calculate_estimate(detected_items, room_type, tier, zip_code, scope_narrative)
  1. Fetch live Home Depot prices via SerpApi (parallel, Redis-cached 6hr)
  2. Fall back to RSMeans-calibrated hardcoded table on any failure
  3. Apply ZIP → state → regional multiplier
  4. Add labor (RSMeans productivity rates)
  5. Compute permits (8%) + contingency (10%)
  6. Return full estimate dict matching GET /estimate/status spec
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Regional cost multipliers ─────────────────────────────────────────────────
# Source: BLS area cost data + RSMeans location factors

REGIONAL_MULTIPLIERS: dict[str, float] = {
    "CA": 1.35, "NY": 1.42, "MA": 1.38, "WA": 1.28,
    "IL": 1.18, "CO": 1.15, "TX": 0.92, "FL": 0.96,
    "GA": 0.88, "AZ": 0.95, "OH": 0.87, "MI": 0.89,
    "NJ": 1.36, "CT": 1.32, "MD": 1.18, "VA": 1.05,
    "NC": 0.90, "TN": 0.86, "MO": 0.90, "MN": 1.05,
    "WI": 0.95, "IN": 0.88, "PA": 1.08, "OR": 1.18,
    "NV": 1.02, "UT": 0.96, "default": 1.00,
}

# ZIP prefix (first 3 digits) → state code
_ZIP_STATE: dict[str, str] = {
    # California
    "900": "CA", "901": "CA", "902": "CA", "903": "CA", "904": "CA",
    "905": "CA", "906": "CA", "907": "CA", "908": "CA",
    "910": "CA", "911": "CA", "912": "CA", "913": "CA", "914": "CA",
    "915": "CA", "916": "CA", "917": "CA", "918": "CA", "919": "CA",
    "920": "CA", "921": "CA", "922": "CA", "923": "CA", "924": "CA",
    "925": "CA", "926": "CA", "927": "CA", "928": "CA",
    "930": "CA", "931": "CA", "932": "CA", "933": "CA", "934": "CA",
    "935": "CA", "936": "CA", "937": "CA", "938": "CA", "939": "CA",
    "940": "CA", "941": "CA", "942": "CA", "943": "CA", "944": "CA",
    "945": "CA", "946": "CA", "947": "CA", "948": "CA", "949": "CA",
    "950": "CA", "951": "CA", "952": "CA", "953": "CA", "954": "CA",
    "955": "CA", "956": "CA", "957": "CA", "958": "CA",
    "960": "CA", "961": "CA",
    # New York
    "100": "NY", "101": "NY", "102": "NY", "103": "NY", "104": "NY",
    "110": "NY", "111": "NY", "112": "NY", "113": "NY", "114": "NY",
    "115": "NY", "116": "NY", "117": "NY", "118": "NY", "119": "NY",
    "120": "NY", "121": "NY", "122": "NY", "123": "NY", "124": "NY",
    "125": "NY", "126": "NY", "127": "NY", "128": "NY", "129": "NY",
    "130": "NY", "131": "NY", "132": "NY", "133": "NY", "134": "NY",
    "135": "NY", "136": "NY", "137": "NY", "138": "NY", "139": "NY",
    "140": "NY", "141": "NY", "142": "NY", "143": "NY", "144": "NY",
    "145": "NY", "146": "NY", "147": "NY", "148": "NY", "149": "NY",
    # Texas
    "750": "TX", "751": "TX", "752": "TX", "753": "TX", "754": "TX",
    "755": "TX", "756": "TX", "757": "TX", "758": "TX", "759": "TX",
    "760": "TX", "761": "TX", "762": "TX", "763": "TX", "764": "TX",
    "765": "TX", "766": "TX", "767": "TX", "768": "TX", "769": "TX",
    "770": "TX", "771": "TX", "772": "TX", "773": "TX", "774": "TX",
    "775": "TX", "776": "TX", "777": "TX", "778": "TX", "779": "TX",
    "780": "TX", "781": "TX", "782": "TX", "783": "TX", "784": "TX",
    "785": "TX", "786": "TX", "787": "TX", "788": "TX", "789": "TX",
    "790": "TX", "791": "TX", "792": "TX", "793": "TX", "794": "TX",
    "795": "TX", "796": "TX", "797": "TX", "798": "TX", "799": "TX",
    # Florida
    "320": "FL", "321": "FL", "322": "FL", "323": "FL", "324": "FL",
    "325": "FL", "326": "FL", "327": "FL", "328": "FL", "329": "FL",
    "330": "FL", "331": "FL", "332": "FL", "333": "FL", "334": "FL",
    "335": "FL", "336": "FL", "337": "FL", "338": "FL", "339": "FL",
    "340": "FL", "341": "FL", "342": "FL", "344": "FL",
    "346": "FL", "347": "FL", "349": "FL",
    # Illinois
    "600": "IL", "601": "IL", "602": "IL", "603": "IL", "604": "IL",
    "605": "IL", "606": "IL", "607": "IL", "608": "IL", "609": "IL",
    "610": "IL", "611": "IL", "612": "IL", "613": "IL", "614": "IL",
    "615": "IL", "616": "IL", "617": "IL", "618": "IL", "619": "IL",
    "620": "IL", "622": "IL", "623": "IL", "624": "IL", "625": "IL",
    "626": "IL", "627": "IL", "628": "IL", "629": "IL",
    # Washington
    "980": "WA", "981": "WA", "982": "WA", "983": "WA", "984": "WA",
    "985": "WA", "986": "WA", "988": "WA", "989": "WA", "990": "WA",
    "991": "WA", "992": "WA", "993": "WA", "994": "WA",
    # Colorado
    "800": "CO", "801": "CO", "802": "CO", "803": "CO", "804": "CO",
    "805": "CO", "806": "CO", "807": "CO", "808": "CO", "809": "CO",
    "810": "CO", "811": "CO", "812": "CO", "813": "CO", "814": "CO",
    "815": "CO", "816": "CO",
    # Massachusetts
    "010": "MA", "011": "MA", "012": "MA", "013": "MA", "014": "MA",
    "015": "MA", "016": "MA", "017": "MA", "018": "MA", "019": "MA",
    "020": "MA", "021": "MA", "022": "MA", "023": "MA", "024": "MA",
    "025": "MA", "026": "MA", "027": "MA",
    # Georgia
    "300": "GA", "301": "GA", "302": "GA", "303": "GA", "304": "GA",
    "305": "GA", "306": "GA", "307": "GA", "308": "GA", "309": "GA",
    "310": "GA", "311": "GA", "312": "GA", "313": "GA", "314": "GA",
    "315": "GA", "316": "GA", "317": "GA", "318": "GA", "319": "GA",
    # Arizona
    "850": "AZ", "851": "AZ", "852": "AZ", "853": "AZ", "854": "AZ",
    "855": "AZ", "856": "AZ", "857": "AZ", "859": "AZ", "860": "AZ",
    "863": "AZ", "864": "AZ", "865": "AZ",
}

# ── Hardcoded material costs (fallback when Apify unavailable) ────────────────
# Source: RSMeans Residential Cost Data 2025, cross-checked with HD/Lowe's
# Unit: $/unit for the given tier (eco | standard | premium)

MATERIAL_COSTS: dict[str, dict[str, dict]] = {
    "kitchen": {
        "cabinets":     {"unit": "linear_ft", "eco": 90,   "standard": 180,  "premium": 380},
        "countertop":   {"unit": "sq_ft",     "eco": 55,   "standard": 80,   "premium": 130},
        "sink":         {"unit": "each",      "eco": 200,  "standard": 450,  "premium": 1200},
        "dishwasher":   {"unit": "each",      "eco": 400,  "standard": 800,  "premium": 1800},
        "refrigerator": {"unit": "each",      "eco": 900,  "standard": 1800, "premium": 5000},
        "range":        {"unit": "each",      "eco": 600,  "standard": 1400, "premium": 4000},
        "microwave":    {"unit": "each",      "eco": 150,  "standard": 350,  "premium": 800},
        "backsplash":   {"unit": "sq_ft",     "eco": 8,    "standard": 15,   "premium": 30},
        "flooring":     {"unit": "sq_ft",     "eco": 2,    "standard": 4.5,  "premium": 8},
        "lighting_fixture": {"unit": "each",  "eco": 80,   "standard": 200,  "premium": 600},
        "window":       {"unit": "each",      "eco": 300,  "standard": 700,  "premium": 1800},
        "paint":        {"unit": "sq_ft",     "eco": 0.60, "standard": 0.90, "premium": 1.40},
        "drywall":      {"unit": "sq_ft",     "eco": 1.5,  "standard": 2.5,  "premium": 4},
    },
    "bathroom": {
        "vanity":       {"unit": "each",      "eco": 300,  "standard": 800,  "premium": 2500},
        "toilet":       {"unit": "each",      "eco": 200,  "standard": 450,  "premium": 900},
        "tub":          {"unit": "each",      "eco": 400,  "standard": 900,  "premium": 3000},
        "shower":       {"unit": "each",      "eco": 300,  "standard": 700,  "premium": 2000},
        "tile_floor":   {"unit": "sq_ft",     "eco": 5,    "standard": 10,   "premium": 22},
        "tile_wall":    {"unit": "sq_ft",     "eco": 4,    "standard": 9,    "premium": 20},
        "faucet":       {"unit": "each",      "eco": 80,   "standard": 200,  "premium": 600},
        "mirror":       {"unit": "each",      "eco": 80,   "standard": 200,  "premium": 600},
        "lighting_fixture": {"unit": "each",  "eco": 60,   "standard": 150,  "premium": 450},
        "flooring":     {"unit": "sq_ft",     "eco": 2,    "standard": 4.5,  "premium": 8},
        "paint":        {"unit": "sq_ft",     "eco": 0.60, "standard": 0.90, "premium": 1.40},
        "drywall":      {"unit": "sq_ft",     "eco": 1.5,  "standard": 2.5,  "premium": 4},
    },
    "bedroom": {
        "flooring":     {"unit": "sq_ft",     "eco": 2,    "standard": 4.5,  "premium": 9},
        "paint":        {"unit": "sq_ft",     "eco": 0.60, "standard": 0.90, "premium": 1.40},
        "drywall":      {"unit": "sq_ft",     "eco": 1.5,  "standard": 2.5,  "premium": 4},
        "window":       {"unit": "each",      "eco": 300,  "standard": 700,  "premium": 1800},
        "door":         {"unit": "each",      "eco": 150,  "standard": 350,  "premium": 900},
        "lighting_fixture": {"unit": "each",  "eco": 60,   "standard": 150,  "premium": 450},
        "ceiling_fan":  {"unit": "each",      "eco": 80,   "standard": 200,  "premium": 500},
        "closet":       {"unit": "each",      "eco": 500,  "standard": 1200, "premium": 3000},
    },
    "living_room": {
        "flooring":     {"unit": "sq_ft",     "eco": 2,    "standard": 4.5,  "premium": 9},
        "paint":        {"unit": "sq_ft",     "eco": 0.60, "standard": 0.90, "premium": 1.40},
        "drywall":      {"unit": "sq_ft",     "eco": 1.5,  "standard": 2.5,  "premium": 4},
        "window":       {"unit": "each",      "eco": 300,  "standard": 700,  "premium": 1800},
        "door":         {"unit": "each",      "eco": 150,  "standard": 350,  "premium": 900},
        "lighting_fixture": {"unit": "each",  "eco": 60,   "standard": 150,  "premium": 450},
        "ceiling_fan":  {"unit": "each",      "eco": 80,   "standard": 200,  "premium": 500},
    },
    "general": {
        "flooring":         {"unit": "sq_ft", "eco": 2,    "standard": 4.5,  "premium": 8},
        "window":           {"unit": "each",  "eco": 300,  "standard": 700,  "premium": 1800},
        "door":             {"unit": "each",  "eco": 150,  "standard": 350,  "premium": 900},
        "drywall":          {"unit": "sq_ft", "eco": 1.5,  "standard": 2.5,  "premium": 4},
        "paint":            {"unit": "sq_ft", "eco": 0.60, "standard": 0.90, "premium": 1.40},
        "lighting_fixture": {"unit": "each",  "eco": 60,   "standard": 150,  "premium": 450},
        "microwave":        {"unit": "each",  "eco": 150,  "standard": 350,  "premium": 800},
        "ceiling_fan":      {"unit": "each",  "eco": 80,   "standard": 200,  "premium": 500},
        "ac_unit_removal":  {"unit": "each",  "eco": 350,  "standard": 700,  "premium": 1400},
        "hvac_disconnect":  {"unit": "each",  "eco": 180,  "standard": 320,  "premium": 600},
        "closet":           {"unit": "each",  "eco": 500,  "standard": 1200, "premium": 3000},
    },
}

# ── Labor rates (RSMeans 2025, per our unit) ──────────────────────────────────
# Includes trade labor + productivity factor. NOT adjusted by regional multiplier
# here — multiplier is applied in calculate_estimate to both mat and labor.

LABOR_UNIT_COSTS: dict[str, float] = {
    "cabinets":         65,   # $/linear_ft — carpenter
    "countertop":       35,   # $/sq_ft — stone setter
    "backsplash":       12,   # $/sq_ft — tile setter
    "sink":             220,  # each — plumber (1.5-2 hr)
    "faucet":           160,  # each — plumber (1 hr)
    "dishwasher":       150,  # each — plumber + electrician
    "refrigerator":     100,  # each — general labor (delivery + install)
    "range":            200,  # each — electrician + plumber (gas)
    "microwave":        80,   # each — electrician
    "vanity":           350,  # each — carpenter + plumber
    "toilet":           250,  # each — plumber
    "tub":              600,  # each — plumber + tile setter
    "shower":           800,  # each — plumber + tile setter
    "tile_floor":       8,    # $/sq_ft — tile setter
    "tile_wall":        10,   # $/sq_ft — tile setter
    "mirror":           60,   # each — general labor
    "flooring":         4,    # $/sq_ft — flooring installer
    "paint":            2.20, # $/sq_ft — painter (2 coats)
    "drywall":          3,    # $/sq_ft — drywall installer + finish
    "window":           200,  # each — carpenter (2-3 hr)
    "door":             150,  # each — carpenter (2 hr)
    "lighting_fixture": 80,   # each — electrician (1 hr)
    "ceiling_fan":      120,  # each — electrician (1.5 hr)
    "closet":           400,  # each — carpenter (4-5 hr)
    "ac_unit_removal":  150,  # each — HVAC tech + general labor
    "hvac_disconnect":  100,  # each — HVAC tech
}

# ── Display labels ────────────────────────────────────────────────────────────

_LABEL_DISPLAY: dict[str, str] = {
    "cabinets":         "Cabinet replacement",
    "countertop":       "Countertop replacement",
    "backsplash":       "Backsplash tile",
    "sink":             "Sink + faucet replacement",
    "faucet":           "Faucet replacement",
    "dishwasher":       "Dishwasher replacement",
    "refrigerator":     "Refrigerator replacement",
    "range":            "Range / stove replacement",
    "microwave":        "Microwave replacement",
    "vanity":           "Bathroom vanity replacement",
    "toilet":           "Toilet replacement",
    "tub":              "Bathtub replacement",
    "shower":           "Shower replacement",
    "tile_floor":       "Floor tile",
    "tile_wall":        "Wall tile",
    "mirror":           "Mirror replacement",
    "flooring":         "Flooring replacement",
    "paint":            "Interior painting",
    "drywall":          "Drywall repair / patch",
    "window":           "Window replacement",
    "door":             "Door replacement",
    "lighting_fixture": "Lighting fixture",
    "ceiling_fan":      "Ceiling fan installation",
    "closet":           "Closet system installation",
    "ac_unit_removal":  "AC unit removal",
    "hvac_disconnect":  "HVAC disconnect",
}

PERMIT_RATE      = 0.08
CONTINGENCY_RATE = 0.10


# ── Helpers ───────────────────────────────────────────────────────────────────

def zip_to_state(zip_code: str) -> str:
    prefix = (zip_code or "").zfill(5)[:3]
    return _ZIP_STATE.get(prefix, "default")


def get_regional_multiplier(zip_code: str) -> float:
    state = zip_to_state(zip_code)
    return REGIONAL_MULTIPLIERS.get(state, REGIONAL_MULTIPLIERS["default"])


def _hardcoded_mat(label: str, room_type: str, tier: str) -> Optional[float]:
    """Look up the hardcoded material unit cost for label + room + tier."""
    tier_k = tier if tier in ("eco", "standard", "premium") else "standard"
    row = (
        MATERIAL_COSTS.get(room_type, {}).get(label)
        or MATERIAL_COSTS["general"].get(label)
    )
    if row is None:
        return None
    return float(row.get(tier_k) or row.get("standard") or 0)


def _labor(label: str) -> float:
    return LABOR_UNIT_COSTS.get(label, 50.0)


def _display(label: str) -> str:
    return _LABEL_DISPLAY.get(label, label.replace("_", " ").title())


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_live_prices(detected_items: list[dict], zip_code: str) -> dict:
    """Batch-fetch HD prices for all detected item labels. Returns {} on any failure."""
    from config import Config
    all_labels = [d.get("label", "") for d in detected_items if d.get("label")]
    if not Config.SERPAPI_KEY or not all_labels:
        if not Config.SERPAPI_KEY:
            logger.info("[pricing] SERPAPI_KEY not set — using hardcoded tables")
        return {}
    try:
        from services.serpapi_prices import fetch_hd_prices
        live_prices = fetch_hd_prices(all_labels, zip_code=zip_code)
        hit = sum(1 for v in live_prices.values() if v)
        logger.info("[pricing] live prices: %d/%d items found on HD", hit, len(all_labels))
        return live_prices
    except Exception as exc:
        logger.warning("[pricing] SerpApi price fetch failed (using hardcoded): %s", exc)
        return {}


def _calc_tier(
    detected_items: list[dict],
    room_type: str,
    tier: str,
    multiplier: float,
    scope_narrative: str,
    live_prices: dict,
) -> dict:
    """
    Inner calculation for one tier using pre-fetched live prices.
    Returns the full estimate dict for that tier.
    """
    breakdown:          list[dict] = []
    subtotal_materials: float      = 0.0
    subtotal_labor:     float      = 0.0
    skipped:            list[str]  = []

    for det in detected_items:
        label = det.get("label", "")
        qty   = det.get("quantity")

        if qty is None or qty <= 0:
            skipped.append(f"{label}(no qty)")
            continue

        hd_info    = live_prices.get(label)
        hd_ref_str = None

        if hd_info:
            mat_cost = hd_info.unit_price
            hd_ref_str = (
                f"{hd_info.product_title} — "
                f"${hd_info.hd_raw_price:.2f}/{hd_info.hd_raw_unit} "
                f"(Home Depot)"
            )
        else:
            mat_cost = _hardcoded_mat(label, room_type, tier)
            if mat_cost is None:
                skipped.append(f"{label}(no table)")
                continue

        unit = det.get("unit")
        if not unit:
            row = MATERIAL_COSTS.get(room_type, {}).get(label) or MATERIAL_COSTS["general"].get(label)
            unit = row["unit"] if row else "each"

        mat_cost  *= multiplier
        lab_cost   = _labor(label) * multiplier
        line_total = round((mat_cost + lab_cost) * qty)
        scope_desc = _build_scope(label, tier, hd_info)

        breakdown.append({
            "item":               _display(label),
            "scope":              scope_desc,
            "qty":                round(float(qty), 1),
            "unit":               unit,
            "material_unit_cost": round(mat_cost, 2),
            "labor_unit_cost":    round(lab_cost, 2),
            "total":              line_total,
            "hd_price_reference": hd_ref_str,
            "_source_label":      label,
            "_detection_confidence": det.get("confidence"),
        })
        subtotal_materials += mat_cost * qty
        subtotal_labor     += lab_cost * qty

    # Auto-add paint for kitchen/bathroom
    if room_type in ("kitchen", "bathroom") and not any(b["_source_label"] == "paint" for b in breakdown):
        paint_sqft = 480 if room_type == "kitchen" else 240
        mat = (_hardcoded_mat("paint", room_type, tier) or 0.90) * multiplier
        lab = _labor("paint") * multiplier
        breakdown.append({
            "item": "Interior painting", "scope": "Walls + ceiling, 2 coats",
            "qty": paint_sqft, "unit": "sq_ft",
            "material_unit_cost": round(mat, 2), "labor_unit_cost": round(lab, 2),
            "total": round((mat + lab) * paint_sqft),
            "hd_price_reference": None,
            "_source_label": "paint", "_detection_confidence": None,
        })
        subtotal_materials += mat * paint_sqft
        subtotal_labor     += lab * paint_sqft

    subtotal_materials = round(subtotal_materials)
    subtotal_labor     = round(subtotal_labor)
    subtotal           = subtotal_materials + subtotal_labor
    permits            = round(subtotal * PERMIT_RATE)
    contingency        = round(subtotal * CONTINGENCY_RATE)
    total              = subtotal + permits + contingency
    live_count         = sum(1 for b in breakdown if b.get("hd_price_reference"))
    range_pct          = 0.12 if live_count >= max(len(breakdown) // 2, 1) else 0.18

    timeline = (
        5 if room_type == "kitchen" and len(breakdown) > 5
        else 4 if room_type in ("kitchen", "bathroom")
        else 3 if room_type in ("living_room", "bedroom")
        else 2
    )

    logger.info("[pricing] %-8s  mat=$%d  lab=$%d  total=$%d  (%d lines, %d HD-live)",
                tier, subtotal_materials, subtotal_labor, total, len(breakdown), live_count)

    public_breakdown = [{k: v for k, v in i.items() if not k.startswith("_")} for i in breakdown]

    return {
        "estimate_breakdown":  public_breakdown,
        "_breakdown_meta":     breakdown,
        "subtotal_materials":  subtotal_materials,
        "subtotal_labor":      subtotal_labor,
        "permits":             permits,
        "contingency":         contingency,
        "total_estimate":      total,
        "estimate_range": {
            "low":  round(total * (1 - range_pct)),
            "high": round(total * (1 + range_pct)),
        },
        "scope_narrative":        scope_narrative,
        "timeline_estimate_weeks": timeline,
        "live_pricing_items":     live_count,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_all_tiers(
    detected_items: list[dict],
    room_type: str,
    zip_code: str = "92831",
    scope_narrative: str = "",
) -> dict[str, dict]:
    """
    Calculate Economy / Standard / Premium estimates in one call.
    Fetches live HD prices once (parallel, cached), then applies 3 tier tables.
    Returns {'eco': {...}, 'standard': {...}, 'premium': {...}} each matching
    the /estimate/status result spec for that tier.
    """
    multiplier = get_regional_multiplier(zip_code)
    state      = zip_to_state(zip_code)
    logger.info("[pricing] all-tiers  room=%s  zip=%s→%s  multiplier=%.2f  items=%d",
                room_type, zip_code, state, multiplier, len(detected_items))

    live_prices = _fetch_live_prices(detected_items, zip_code)

    return {
        t: _calc_tier(detected_items, room_type, t, multiplier, scope_narrative, live_prices)
        for t in ("eco", "standard", "premium")
    }


def calculate_estimate(
    detected_items: list[dict],
    room_type: str,
    tier: str = "standard",
    zip_code: str = "92831",
    scope_narrative: str = "",
) -> dict:
    """
    Single-tier estimate (backward compat wrapper around calculate_all_tiers).
    Prefer calculate_all_tiers when you need all 3 tiers.
    """
    multiplier = get_regional_multiplier(zip_code)
    state      = zip_to_state(zip_code)
    logger.info("[pricing] room=%s  tier=%s  zip=%s→%s  multiplier=%.2f  items=%d",
                room_type, tier, zip_code, state, multiplier, len(detected_items))

    live_prices = _fetch_live_prices(detected_items, zip_code)
    result      = _calc_tier(detected_items, room_type, tier, multiplier, scope_narrative, live_prices)
    result["regional_multiplier"] = multiplier
    return result


def _build_scope(label: str, tier: str, hd_info) -> str:
    """Build the scope description string for a line item."""
    tier_label = {"eco": "Economy", "standard": "Standard", "premium": "Premium"}.get(tier, tier.title())

    if hd_info:
        # Trim product title to a clean short form
        title = hd_info.product_title.split(",")[0].split("(")[0].strip()
        return f"{title} · {tier_label} tier"

    _SCOPE_DEFAULTS = {
        "cabinets":         f"Semi-custom cabinets, {tier_label.lower()} finish",
        "countertop":       f"{tier_label} countertop, like-for-like",
        "backsplash":       "Tile backsplash, like-for-like",
        "sink":             "Undermount sink + faucet, like-for-like",
        "flooring":         f"{tier_label} LVP / hardwood, like-for-like",
        "paint":            "Walls + ceiling, 2 coats",
        "drywall":          "Drywall patch / repair",
        "ac_unit_removal":  "Remove window or wall AC unit, patch wall",
        "hvac_disconnect":  "Disconnect HVAC supply, cap and patch",
    }
    return _SCOPE_DEFAULTS.get(label, f"{tier_label} tier, like-for-like")
