"""
Cost calculation from detected items — derives estimate_breakdown from vision output.

Uses hardcoded RSMeans-calibrated tables from the spec. SerpApi live pricing
is a Phase 4 enhancement; this module provides consistent pricing tied to
detected quantities rather than static mock data.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

REGIONAL_MULTIPLIERS = {
    'CA': 1.35, 'NY': 1.42, 'MA': 1.38, 'WA': 1.28,
    'IL': 1.18, 'CO': 1.15, 'TX': 0.92, 'FL': 0.96,
    'GA': 0.88, 'AZ': 0.95, 'OH': 0.87, 'MI': 0.89,
    'default': 1.00,
}

# ZIP prefix → state (simplified; first 3 digits for common areas)
_ZIP_STATE: dict[str, str] = {
    '900': 'CA', '901': 'CA', '902': 'CA', '903': 'CA', '904': 'CA',
    '100': 'NY', '101': 'NY', '102': 'NY', '103': 'NY', '104': 'NY',
    '750': 'TX', '751': 'TX', '752': 'TX', '770': 'TX',
    '331': 'FL', '332': 'FL', '333': 'FL',
    '606': 'IL', '607': 'IL',
    '981': 'WA', '980': 'WA',
}

MATERIAL_COSTS: dict[str, dict[str, dict]] = {
    'kitchen': {
        'cabinets':          {'unit': 'linear_ft', 'eco': 90,  'standard': 180, 'premium': 380},
        'countertop':        {'unit': 'sq_ft',     'eco': 55,  'standard': 80,  'premium': 130},
        'flooring':          {'unit': 'sq_ft',     'eco': 2,   'standard': 4.5, 'premium': 8},
        'sink':              {'unit': 'each',      'eco': 200, 'standard': 450, 'premium': 1200},
        'dishwasher':        {'unit': 'each',      'eco': 400, 'standard': 800, 'premium': 1800},
        'refrigerator':      {'unit': 'each',      'eco': 900, 'standard': 1800,'premium': 5000},
        'range':             {'unit': 'each',      'eco': 600, 'standard': 1400,'premium': 4000},
        'microwave':         {'unit': 'each',      'eco': 150, 'standard': 350, 'premium': 800},
        'backsplash':        {'unit': 'sq_ft',     'eco': 8,   'standard': 15,  'premium': 30},
        'lighting_fixture':  {'unit': 'each',      'eco': 80,  'standard': 200, 'premium': 600},
        'paint':             {'unit': 'sq_ft',     'eco': 0.60,'standard': 0.90,'premium': 1.40},
    },
    'bathroom': {
        'vanity':            {'unit': 'each',      'eco': 300, 'standard': 800, 'premium': 2500},
        'toilet':            {'unit': 'each',      'eco': 200, 'standard': 450, 'premium': 900},
        'tub':               {'unit': 'each',      'eco': 400, 'standard': 900, 'premium': 3000},
        'shower':            {'unit': 'each',      'eco': 300, 'standard': 700, 'premium': 2000},
        'tile_floor':        {'unit': 'sq_ft',     'eco': 5,   'standard': 10,  'premium': 22},
        'tile_wall':         {'unit': 'sq_ft',     'eco': 4,   'standard': 9,   'premium': 20},
        'faucet':            {'unit': 'each',      'eco': 80,  'standard': 200, 'premium': 600},
        'mirror':            {'unit': 'each',      'eco': 80,  'standard': 200, 'premium': 600},
        'lighting_fixture':  {'unit': 'each',      'eco': 60,  'standard': 150, 'premium': 450},
        'paint':             {'unit': 'sq_ft',     'eco': 0.60,'standard': 0.90,'premium': 1.40},
    },
    'general': {
        'flooring':          {'unit': 'sq_ft',     'eco': 2,   'standard': 4.5, 'premium': 8},
        'window':            {'unit': 'each',      'eco': 300, 'standard': 700, 'premium': 1800},
        'door':              {'unit': 'each',      'eco': 150, 'standard': 350, 'premium': 900},
        'drywall':           {'unit': 'sq_ft',     'eco': 1.5, 'standard': 2.5, 'premium': 4},
        'paint':             {'unit': 'sq_ft',     'eco': 0.60,'standard': 0.90,'premium': 1.40},
        'lighting_fixture':  {'unit': 'each',      'eco': 60,  'standard': 150, 'premium': 450},
        'microwave':         {'unit': 'each',      'eco': 150, 'standard': 350, 'premium': 800},
        'ac_unit_removal':   {'unit': 'each',      'eco': 350, 'standard': 700, 'premium': 1400},
        'hvac_disconnect':   {'unit': 'each',      'eco': 180, 'standard': 320, 'premium': 600},
        'ceiling_fan':       {'unit': 'each',      'eco': 80,  'standard': 200, 'premium': 500},
        'closet':            {'unit': 'each',      'eco': 500, 'standard': 1200,'premium': 3000},
    },
}

# Labor $/unit at standard productivity (material + labor = total per line)
LABOR_UNIT_COSTS: dict[str, dict[str, float]] = {
    'cabinets':         {'linear_ft': 65},
    'countertop':       {'sq_ft': 35},
    'flooring':         {'sq_ft': 4.0},
    'tile_floor':       {'sq_ft': 8},
    'tile_wall':        {'sq_ft': 10},
    'backsplash':       {'sq_ft': 12},
    'sink':             {'each': 220},
    'vanity':           {'each': 350},
    'toilet':           {'each': 250},
    'tub':              {'each': 600},
    'shower':           {'each': 800},
    'dishwasher':       {'each': 150},
    'refrigerator':     {'each': 100},
    'range':            {'each': 200},
    'microwave':        {'each': 80},
    'ac_unit_removal':  {'each': 150},
    'hvac_disconnect':  {'each': 100},
    'ceiling_fan':      {'each': 120},
    'closet':           {'each': 400},
    'paint':            {'sq_ft': 2.20},
    'drywall':          {'sq_ft': 3.0},
    'window':           {'each': 200},
    'door':             {'each': 150},
    'lighting_fixture': {'each': 80},
}

_LABEL_DISPLAY = {
    'cabinets': 'Cabinet replacement',
    'countertop': 'Countertop replacement',
    'flooring': 'Flooring replacement',
    'sink': 'Sink + faucet replacement',
    'dishwasher': 'Dishwasher replacement',
    'refrigerator': 'Refrigerator replacement',
    'range': 'Range replacement',
    'vanity': 'Vanity replacement',
    'toilet': 'Toilet replacement',
    'tub': 'Tub replacement',
    'shower': 'Shower replacement',
    'tile_floor': 'Floor tile',
    'tile_wall': 'Wall tile',
    'paint': 'Interior painting',
    'backsplash': 'Backsplash tile',
    'lighting_fixture': 'Lighting fixture',
    'window': 'Window replacement',
    'door': 'Door replacement',
    'drywall': 'Drywall repair / patch',
    'microwave': 'Microwave replacement',
    'ac_unit_removal': 'AC unit removal',
    'hvac_disconnect': 'HVAC disconnect',
    'ceiling_fan': 'Ceiling fan installation',
    'closet': 'Closet system installation',
}

PERMIT_RATE = 0.08
CONTINGENCY_RATE = 0.10


def zip_to_state(zip_code: str) -> str:
    prefix = (zip_code or '')[:3]
    return _ZIP_STATE.get(prefix, 'default')


def get_regional_multiplier(zip_code: str) -> float:
    state = zip_to_state(zip_code)
    if state == 'default':
        return REGIONAL_MULTIPLIERS['default']
    return REGIONAL_MULTIPLIERS.get(state, REGIONAL_MULTIPLIERS['default'])


def _lookup_costs(label: str, room_type: str, tier: str) -> Optional[dict]:
    tier_key = tier if tier in ('eco', 'standard', 'premium') else 'standard'
    room_table = MATERIAL_COSTS.get(room_type, {})
    if label in room_table:
        return room_table[label]
    general = MATERIAL_COSTS.get('general', {})
    return general.get(label)


def _labor_cost(label: str, unit: str) -> float:
    rates = LABOR_UNIT_COSTS.get(label, {})
    return rates.get(unit, rates.get('each', 50.0))


def calculate_estimate(
    detected_items: list[dict],
    room_type: str,
    tier: str = 'standard',
    zip_code: str = '90210',
    scope_narrative: str = '',
) -> dict:
    """
    Build estimate_breakdown and totals from detected_items quantities.
    """
    state = zip_to_state(zip_code)
    multiplier = get_regional_multiplier(zip_code)
    logger.info("[pricing] starting — room=%s  tier=%s  zip=%s  state=%s  multiplier=%.2f",
                room_type, tier, zip_code, state, multiplier)
    logger.info("[pricing] %d detected item(s) to price", len(detected_items))

    breakdown: list[dict] = []
    subtotal_materials = 0.0
    subtotal_labor = 0.0
    skipped_labels: list[str] = []

    for det in detected_items:
        label = det.get('label', '')
        qty = det.get('quantity')

        if qty is None or qty <= 0:
            logger.info("[pricing]   skip %-20s — qty=%s (no quantity)", label, qty)
            skipped_labels.append(label)
            continue

        costs = _lookup_costs(label, room_type, tier)
        if not costs:
            logger.info("[pricing]   skip %-20s — no cost table for room=%s", label, room_type)
            skipped_labels.append(label)
            continue

        unit = det.get('unit') or costs['unit']
        mat_cost = float(costs.get(tier, costs.get('standard', 0)))
        lab_cost = _labor_cost(label, unit)
        mat_cost *= multiplier
        lab_cost *= multiplier
        line_total = round((mat_cost + lab_cost) * qty)

        breakdown.append({
            'item': _LABEL_DISPLAY.get(label, label.replace('_', ' ').title()),
            'scope': f'{tier.title()} tier, like-for-like',
            'qty': round(float(qty), 1),
            'unit': unit,
            'material_unit_cost': round(mat_cost, 2),
            'labor_unit_cost': round(lab_cost, 2),
            'total': line_total,
            'hd_price_reference': None,
            '_source_label': label,
            '_detection_confidence': det.get('confidence'),
        })
        subtotal_materials += mat_cost * qty
        subtotal_labor += lab_cost * qty
        logger.info("[pricing]   ✓ %-20s  qty=%-6s %s  mat=$%.0f  lab=$%.0f  line=$%d",
                    label, qty, unit, mat_cost, lab_cost, line_total)

    # Default paint line for kitchens/bathrooms if not detected
    if room_type in ('kitchen', 'bathroom') and not any(b.get('_source_label') == 'paint' for b in breakdown):
        paint_sq_ft = 480 if room_type == 'kitchen' else 200
        costs = _lookup_costs('paint', room_type, tier)
        if costs:
            mat = float(costs.get(tier, costs['standard'])) * multiplier
            lab = _labor_cost('paint', 'sq_ft') * multiplier
            line_total = round((mat + lab) * paint_sq_ft)
            breakdown.append({
                'item': 'Interior painting',
                'scope': 'Walls + ceiling, 2 coats',
                'qty': paint_sq_ft,
                'unit': 'sq_ft',
                'material_unit_cost': round(mat, 2),
                'labor_unit_cost': round(lab, 2),
                'total': line_total,
                'hd_price_reference': None,
                '_source_label': 'paint',
                '_detection_confidence': None,
            })
            subtotal_materials += mat * paint_sq_ft
            subtotal_labor += lab * paint_sq_ft
            logger.info("[pricing]   + paint (auto-added)  %d sq_ft  line=$%d", paint_sq_ft, line_total)

    subtotal_materials = round(subtotal_materials)
    subtotal_labor = round(subtotal_labor)
    subtotal = subtotal_materials + subtotal_labor
    permits = round(subtotal * PERMIT_RATE)
    contingency = round(subtotal * CONTINGENCY_RATE)
    total = subtotal + permits + contingency
    range_pct = 0.15

    logger.info("[pricing] ── summary ──────────────────────────────")
    logger.info("[pricing]   line items   : %d priced, %d skipped", len(breakdown), len(skipped_labels))
    if skipped_labels:
        logger.info("[pricing]   skipped      : %s", skipped_labels)
    logger.info("[pricing]   materials    : $%d", subtotal_materials)
    logger.info("[pricing]   labor        : $%d", subtotal_labor)
    logger.info("[pricing]   permits (8%%) : $%d", permits)
    logger.info("[pricing]   contingency  : $%d", contingency)
    logger.info("[pricing]   TOTAL        : $%d  (range $%d–$%d)",
                total, round(total * (1 - range_pct)), round(total * (1 + range_pct)))

    return {
        'estimate_breakdown': [
            {k: v for k, v in item.items() if not k.startswith('_')}
            for item in breakdown
        ],
        '_breakdown_meta': breakdown,
        'subtotal_materials': subtotal_materials,
        'subtotal_labor': subtotal_labor,
        'permits': permits,
        'contingency': contingency,
        'total_estimate': total,
        'estimate_range': {
            'low': round(total * (1 - range_pct)),
            'high': round(total * (1 + range_pct)),
        },
        'regional_multiplier': multiplier,
        'scope_narrative': scope_narrative,
        'timeline_estimate_weeks': 4 if room_type == 'kitchen' else 3,
    }
