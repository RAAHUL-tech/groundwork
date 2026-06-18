"""
Quantity estimation from bounding boxes + Claude features — B8.

Converts normalized bounding box geometry to real-world measurements using
room-type scale factors. Priority order:
  1. AR measurements (Phase 6 — placeholder)
  2. Roboflow bounding boxes
  3. Claude estimated_qty from detected_features
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Typical room footprints used as scale reference (ft)
ROOM_DIMENSIONS: dict[str, dict] = {
    'kitchen':      {'width': 12.0, 'depth': 12.0, 'sq_ft': 144},
    'bathroom':     {'width':  8.0, 'depth':  8.0, 'sq_ft':  64},
    'bedroom':      {'width': 12.0, 'depth': 14.0, 'sq_ft': 168},
    'living_room':  {'width': 15.0, 'depth': 20.0, 'sq_ft': 300},
    'basement':     {'width': 20.0, 'depth': 25.0, 'sq_ft': 500},
    'garage':       {'width': 20.0, 'depth': 22.0, 'sq_ft': 440},
    'laundry':      {'width':  8.0, 'depth':  8.0, 'sq_ft':  64},
    'exterior':     {'width': 30.0, 'depth':  1.0, 'sq_ft':  30},
}
_DEFAULT_DIMS = {'width': 12.0, 'depth': 12.0, 'sq_ft': 144}

# Camera at typical shooting distance captures ~65% of room width
_VIEW_W = 0.65
_VIEW_D = 0.55

UNIT_ITEMS = {
    'sink', 'toilet', 'tub', 'shower', 'dishwasher', 'refrigerator',
    'range', 'microwave', 'window', 'door', 'lighting_fixture', 'vanity', 'mirror',
    'ac_unit_removal', 'hvac_disconnect', 'ceiling_fan', 'closet',
}
LINEAR_ITEMS = {'cabinets'}
SQFT_ITEMS = {
    'countertop', 'flooring', 'backsplash', 'tile_wall',
    'tile_floor', 'drywall', 'paint',
}

# Labels that are furniture / non-construction — skip entirely
_SKIP_LABELS = {
    'bed_frame', 'bed', 'chair', 'gaming_chair', 'desk', 'table', 'sofa',
    'couch', 'dresser', 'nightstand', 'bookshelf', 'shelf',
    'ac_unit', 'ac_unit_-_window_mounted', 'air_conditioner', 'hvac',
    'ceiling_fan', 'tv', 'television', 'computer', 'monitor',
    'lamp', 'decoration', 'curtain', 'blinds',
}

# Map Claude's verbose labels to the standard pricing keys.
# Claude often returns descriptive strings like "drywall_-_walls" or
# "flooring_-_carpet" — these must be normalised before reaching the
# pricing engine.  Build the map from both underscore and hyphen variants.
_LABEL_NORM: dict[str, str] = {
    # Drywall / walls
    'drywall': 'drywall',
    'drywall_walls': 'drywall',
    'drywall_-_walls': 'drywall',
    'walls_drywall': 'drywall',
    'wall': 'drywall',
    'walls': 'drywall',
    # Flooring (all materials map to generic 'flooring' for pricing)
    'flooring': 'flooring',
    'flooring_carpet': 'flooring',
    'flooring_-_carpet': 'flooring',
    'flooring_hardwood': 'flooring',
    'flooring_-_hardwood': 'flooring',
    'flooring_vinyl': 'flooring',
    'flooring_-_vinyl': 'flooring',
    'flooring_lvp': 'flooring',
    'flooring_-_lvp': 'flooring',
    'flooring_laminate': 'flooring',
    'carpet': 'flooring',
    'hardwood': 'flooring',
    'lvp': 'flooring',
    'laminate': 'flooring',
    # Ceiling (treat as drywall for pricing)
    'ceiling': 'drywall',
    'ceiling_popcorn': 'drywall',
    'ceiling_-_popcorn': 'drywall',
    'ceiling_-_popcorn/textured': 'drywall',
    'ceiling_texture': 'drywall',
    'popcorn_ceiling': 'drywall',
    # Paint
    'paint': 'paint',
    'painting': 'paint',
    'paint_walls': 'paint',
    # Windows
    'window': 'window',
    'window_standard': 'window',
    'window_single_pane': 'window',
    'window_-_single_pane': 'window',
    'window_double_pane': 'window',
    'window_-_double_pane': 'window',
    'windows': 'window',
    # Doors
    'door': 'door',
    'door_interior': 'door',
    'interior_door': 'door',
    'door_exterior': 'door',
    'exterior_door': 'door',
    # Lighting
    'lighting': 'lighting_fixture',
    'lighting_fixture': 'lighting_fixture',
    'light_fixture': 'lighting_fixture',
    'ceiling_light': 'lighting_fixture',
    'recessed_lighting': 'lighting_fixture',
    # Kitchen
    'cabinets': 'cabinets',
    'cabinet': 'cabinets',
    'kitchen_cabinet': 'cabinets',
    'countertop': 'countertop',
    'countertops': 'countertop',
    'counter': 'countertop',
    'sink': 'sink',
    'kitchen_sink': 'sink',
    'faucet': 'sink',
    'backsplash': 'backsplash',
    'tile_backsplash': 'backsplash',
    'dishwasher': 'dishwasher',
    'refrigerator': 'refrigerator',
    'fridge': 'refrigerator',
    'range': 'range',
    'stove': 'range',
    'oven': 'range',
    'microwave': 'microwave',
    # Bathroom
    'vanity': 'vanity',
    'bathroom_vanity': 'vanity',
    'toilet': 'toilet',
    'tub': 'tub',
    'bathtub': 'tub',
    'shower': 'shower',
    'tile_floor': 'tile_floor',
    'tile_wall': 'tile_wall',
    'mirror': 'mirror',
}


def estimate_quantities(
    detections: list[dict],
    room_type: str,
    claude_features: list[dict],
    ar_measurements: Optional[dict] = None,
    depth_measurements: Optional[dict] = None,
    condition: str = 'fair',
) -> list[dict]:
    """
    Merge YOLO detections + Claude features + depth measurements into
    detected_items with real-world quantities.

    Priority order for sq ft items:
      1. AR measurements (Phase 6)
      2. Depth estimation (floor_area_sqft from depth model)
      3. YOLO bounding box heuristic
      4. Claude estimated_qty
      5. Room-type default

    Returns list of {label, confidence, quantity, unit, bounding_box?}.
    """
    dims = ROOM_DIMENSIONS.get(room_type, _DEFAULT_DIMS)

    # Depth-derived floor area overrides the room-dimension default
    depth_floor_sqft: float | None = None
    depth_wall_sqft: float | None = None
    if depth_measurements and depth_measurements.get('depth_map_available'):
        raw_floor = depth_measurements.get('floor_area_sqft', 0)
        if raw_floor and raw_floor > 20:
            depth_floor_sqft = raw_floor
            depth_wall_sqft  = depth_measurements.get('wall_area_sqft')
            logger.info("[quantity] depth floor=%.0f sqft  wall=%.0f sqft",
                        depth_floor_sqft, depth_wall_sqft or 0)

    # AR measurements override everything (Phase 6)
    ar_floor_sqft: float | None = None
    if ar_measurements:
        ar_floor_sqft = ar_measurements.get('floor_area_sqft')

    # Index Claude features by normalised label for O(1) fallback lookup
    claude_qty: dict[str, dict] = {}
    for feat in (claude_features or []):
        key = _norm(feat.get('item', ''))
        if key:
            claude_qty[key] = {
                'quantity': feat.get('estimated_qty'),
                'unit':     feat.get('unit'),
            }

    # Filter to construction-only detections (skip room-hint labels)
    construction_detections = [
        d for d in detections
        if not d.get('is_room_hint', False)
    ]

    if not construction_detections:
        logger.info("[quantity] no YOLO construction detections — using Claude features")
        return _from_claude_features(
            claude_features,
            depth_floor_sqft=depth_floor_sqft,
            depth_wall_sqft=depth_wall_sqft,
            ar_floor_sqft=ar_floor_sqft,
            condition=condition,
        )

    results: list[dict] = []
    for det in construction_detections:
        label = det['label']
        bbox  = det.get('bounding_box', {})

        # Voice-derived detections that already carry a quantity skip geometry estimation
        if det.get('quantity') is not None:
            qty  = det['quantity']
            unit = det.get('unit') or _unit_for(label)
        else:
            unit, qty = _estimate(
                label, bbox, dims,
                depth_floor_sqft=depth_floor_sqft,
                depth_wall_sqft=depth_wall_sqft,
                ar_floor_sqft=ar_floor_sqft,
                condition=condition,
            )

        # Fall back to Claude qty if geometry estimate is unavailable
        if qty is None:
            fb = claude_qty.get(label) or claude_qty.get(_norm(label))
            if fb and fb['quantity'] is not None:
                qty  = fb['quantity']
                unit = fb['unit'] or unit

        item: dict = {
            'label':      label,
            'confidence': det['confidence'],
            'quantity':   round(qty, 1) if qty is not None else None,
            'unit':       unit,
        }
        if bbox:
            item['bounding_box'] = bbox

        results.append(item)
        logger.debug("[quantity] %s → %.1f %s", label, qty or 0, unit)

    # Append Claude-only items not detected by YOLO
    detected_labels = {d['label'] for d in results}
    for feat in (claude_features or []):
        raw = feat.get('item', '')
        key = _canonical(raw)
        if key is None or key in detected_labels:
            continue
        if feat.get('estimated_qty') is not None:
            results.append({
                'label':      key,
                'confidence': 0.65,
                'quantity':   feat['estimated_qty'],
                'unit':       feat.get('unit') or _unit_for(key),
            })

    logger.info("[quantity] %d item(s) with quantities estimated", len(results))
    return results


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _estimate(
    label: str,
    bbox: dict,
    dims: dict,
    depth_floor_sqft: float | None = None,
    depth_wall_sqft: float | None = None,
    ar_floor_sqft: float | None = None,
    condition: str = 'fair',
) -> tuple[str, Optional[float]]:
    """Return (unit, quantity) with depth/AR measurements taking priority."""
    bw = bbox.get('w', 0)
    bh = bbox.get('h', 0)
    area = bw * bh

    # AR measurements are most accurate (Phase 6)
    effective_floor = ar_floor_sqft or depth_floor_sqft

    if label in UNIT_ITEMS:
        return 'each', 1.0

    if label in LINEAR_ITEMS:
        # Cabinets: visible width × 2 for upper+lower runs
        visible_w = dims['width'] * _VIEW_W
        lin_ft = bw * visible_w * 2.0
        return 'linear_ft', max(4.0, lin_ft) if bw > 0 else None

    if label in SQFT_ITEMS:
        if label == 'flooring':
            # Best estimate: AR > depth > room-type default
            return 'sq_ft', float(effective_floor or dims['sq_ft'])

        if label == 'paint':
            # Wall area ≈ floor area × 2.5 (8-ft ceiling, 4 sides, rough)
            if effective_floor:
                return 'sq_ft', round(effective_floor * 2.5, 1)
            return 'sq_ft', float(dims['sq_ft'] * 2.5)

        if label == 'drywall':
            # Scale drywall scope to condition: poor=full walls, fair=20% patch, good+=skip
            _cond_factor = {'poor': 1.0, 'fair': 0.20, 'good': 0.0, 'excellent': 0.0}
            factor = _cond_factor.get(condition, 0.20)
            if factor <= 0:
                return 'sq_ft', None
            base = effective_floor * 2.5 if effective_floor else dims['sq_ft'] * 2.5
            return 'sq_ft', round(base * factor, 1)

        # Countertop, backsplash, tile — scale bbox to visible room area
        visible_area = (effective_floor or dims['sq_ft']) * _VIEW_W * _VIEW_D
        item_sq_ft = (area / 0.30) * visible_area if area > 0 else None
        return 'sq_ft', max(4.0, item_sq_ft) if item_sq_ft else None

    # Unknown label — infer from name
    unit = _unit_for(label)
    if unit == 'each':
        return 'each', 1.0
    if unit == 'sq_ft' and area > 0:
        return 'sq_ft', round(area * (effective_floor or dims['sq_ft']), 1)
    return unit, None


def _from_claude_features(
    features: list[dict],
    depth_floor_sqft: float | None = None,
    depth_wall_sqft: float | None = None,
    ar_floor_sqft: float | None = None,
    condition: str = 'fair',
) -> list[dict]:
    effective_floor = ar_floor_sqft or depth_floor_sqft
    _cond_factor = {'poor': 1.0, 'fair': 0.20, 'good': 0.0, 'excellent': 0.0}
    results = []
    for f in features:
        raw = f.get('item', '')
        key = _canonical(raw)
        if key is None:
            logger.info("[quantity] skip claude feature '%s' (furniture/unmapped)", raw)
            continue
        qty  = f.get('estimated_qty')
        unit = f.get('unit') or _unit_for(key)
        # Override Claude's sq ft estimates with depth-measured values
        if effective_floor and unit == 'sq_ft':
            if key == 'flooring':
                qty = effective_floor
            elif key == 'paint':
                qty = round(effective_floor * 2.5, 1)
            elif key == 'drywall':
                # Apply condition-based scope reduction
                factor = _cond_factor.get(condition, 0.20)
                qty = round(effective_floor * 2.5 * factor, 1) if factor > 0 else None
        results.append({
            'label':      key,
            'confidence': 0.65,
            'quantity':   qty,
            'unit':       unit,
        })
    return results


def _norm(label: str) -> str:
    return label.lower().strip().replace(' ', '_')


def _canonical(raw: str) -> str | None:
    """
    Normalise a Claude item label to a standard pricing key.
    Returns None if the label is furniture or otherwise non-construction.
    Returns the normalised string (may not be in pricing table) as a fallback.
    """
    key = _norm(raw)

    # Exact skip match
    if key in _SKIP_LABELS:
        return None
    # Substring skip match — catches "desk_-_basic", "ac_unit_-_window_mounted", etc.
    for skip in _SKIP_LABELS:
        if skip in key:
            return None

    # Exact label map match
    if key in _LABEL_NORM:
        return _LABEL_NORM[key]
    # Prefix/substring match — e.g. "flooring_-_engineered_hardwood"
    for pattern, standard in _LABEL_NORM.items():
        if key.startswith(pattern) or pattern in key:
            return standard

    # Keep as-is — pricing engine will log "no cost table" and skip it
    return key


def _unit_for(label: str) -> str:
    l = label.lower()
    if any(k in l for k in ('cabinet', 'baseboard', 'trim', 'rail', 'molding')):
        return 'linear_ft'
    if any(k in l for k in ('floor', 'tile', 'counter', 'drywall', 'paint', 'backsplash', 'wall')):
        return 'sq_ft'
    return 'each'
