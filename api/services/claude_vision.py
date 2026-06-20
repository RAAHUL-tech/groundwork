"""
Claude Vision room classification — B6.

Sends up to 5 images to claude-sonnet-4-6 with CLASSIFICATION_PROMPT.
Retries once on malformed JSON, then falls back to GPT-4o Vision.
"""
import json
import logging
import re

from config import Config

logger = logging.getLogger(__name__)

MAX_IMAGES = 5      # cap for cost and latency
MAX_TOKENS = 2048

CLASSIFICATION_PROMPT = """You are a licensed residential general contractor doing a site walkthrough to price a remodel. You have 20 years of experience estimating kitchens, bathrooms, and whole-home renovations.

Analyze the room image(s) exactly as you would on a real job walk:
- What do you see that clearly needs replacement vs. repair vs. cleaning?
- What surfaces, fixtures, and finishes are past their useful life?
- What would you proactively recommend replacing while the crew is already on site?
- Are there any code issues, moisture damage, or safety concerns visible?
- What's the realistic scope a homeowner should budget for?

Return ONLY valid JSON in this exact structure:
{
  "room_type": "kitchen|bathroom|bedroom|living_room|basement|exterior|laundry|garage",
  "confidence": 0.0-1.0,
  "condition": "poor|fair|good|excellent",
  "condition_notes": "what you'd tell the homeowner in plain language about the room's current state",
  "detected_features": [
    {
      "item": "EXACT_KEY_FROM_LIST_BELOW",
      "estimated_qty": number_or_null,
      "unit": "linear_ft|sq_ft|each|null",
      "condition": "poor|fair|good|excellent",
      "recommendation": "replace|repair|keep|inspect",
      "priority": "must|should|could",
      "notes": "contractor reasoning — why you'd replace/repair, what material you'd spec"
    }
  ],
  "scope_observations": "2-3 sentence contractor summary: what the job entails, what you'd watch out for, rough sequencing",
  "contractor_upsells": ["item a contractor would suggest adding while on site", "..."],
  "ar_measurement_recommended": true|false
}

ITEM KEYS — use EXACTLY these strings, no variations:
Kitchen:  cabinets, countertop, sink, range, dishwasher, refrigerator, microwave,
          flooring, backsplash, lighting_fixture, window, paint, drywall
Bathroom: vanity, toilet, tub, shower, tile_floor, tile_wall, mirror,
          lighting_fixture, faucet, flooring, paint, drywall
General:  flooring, drywall, window, door, lighting_fixture, paint

QUANTITY RULES:
- cabinets → linear_ft (measure upper + lower combined run)
- flooring, drywall, tile_floor, tile_wall, countertop, backsplash, paint → sq_ft
- everything else → each
- Return null for qty only when truly impossible to estimate. Give your best conservative estimate.

Do NOT list furniture (beds, sofas, chairs, tables) — construction/renovation items only.
Return ONLY the JSON object — no markdown fences, no explanation."""


SCOPE_EXTRACTION_PROMPT = """You are a construction estimating assistant. Extract scope items from this contractor's voice note.

Voice note: "{transcript}"
Room type detected: {room_type}

Return ONLY a valid JSON array. Each item must use an exact key from the approved list:
[
  {{
    "item": "EXACT_ITEM_KEY",
    "action": "replace|repair|install|remove|demo",
    "modifier": "eco|standard|premium|null",
    "qty": number_or_null,
    "unit": "each|linear_ft|sq_ft|null"
  }}
]

APPROVED ITEM KEYS:
Kitchen:  cabinets, countertop, sink, range, dishwasher, refrigerator, microwave, flooring, backsplash, lighting_fixture, window, paint, drywall
Bathroom: vanity, toilet, tub, shower, tile_floor, tile_wall, mirror, lighting_fixture, faucet, flooring, paint, drywall
General:  flooring, drywall, window, door, lighting_fixture, paint, ac_unit_removal, hvac_disconnect, ceiling_fan, closet

Language mapping:
- "remove AC" / "AC unit" / "window AC" / "take out the AC" → ac_unit_removal (action: remove, qty: 1, unit: each)
- "new cabinets" / "replace cabinets" → cabinets (action: replace)
- "quartz" / "granite" / "new countertops" → countertop (action: replace)
- "repaint" / "paint the room" / "fresh paint" → paint (action: paint)
- "new floors" / "replace flooring" → flooring (action: replace)
- "mid-range" / "standard" → standard modifier
- "high-end" / "luxury" → premium modifier
- "budget" / "basic" / "economy" → eco modifier

Return ONLY the JSON array. No markdown, no explanation."""


WORK_ITEMS_PROMPT = """You are a licensed residential general contractor finalizing the materials list for a renovation quote.

Your earlier room walkthrough produced this analysis:
Room type: {room_type}
Condition: {condition}
What you observed: {features_json}
Scope assessment: {scope_observations}

Homeowner's voice note: "{voice_transcript}"

Based on what you SAW in the room and what the homeowner ASKED FOR, produce the definitive list of items to purchase at Home Depot for this job. Do not add items that are not visible or not mentioned — only include things clearly needed based on evidence.

Return ONLY a valid JSON array:
[
  {{
    "item": "EXACT_ITEM_KEY",
    "action": "replace|repair|install|remove",
    "qty": number_or_null,
    "unit": "linear_ft|sq_ft|each|null",
    "reason": "one sentence: why this item is needed",
    "priority": "must|should|could"
  }}
]

APPROVED ITEM KEYS — use exactly these strings:
Kitchen:  cabinets, countertop, sink, range, dishwasher, refrigerator, microwave, flooring, backsplash, lighting_fixture, window, paint, drywall
Bathroom: vanity, toilet, tub, shower, tile_floor, tile_wall, mirror, lighting_fixture, faucet, flooring, paint, drywall
General:  flooring, drywall, window, door, lighting_fixture, paint, ceiling_fan, closet, ac_unit_removal, hvac_disconnect

RULES:
- Use the qty from your visual estimate when you have a reliable estimate; null otherwise
- Voice note overrides visual when the homeowner explicitly mentions an item
- Include paint ONLY if there is visible damage/discoloration or the homeowner requested it
- Do NOT add generic items (flooring, paint) just to pad the list
- Items the homeowner explicitly named take priority=must
- Items you observed as poor/fair condition with replace recommendation = must or should
- Items in good condition not mentioned = do not include

Return ONLY the JSON array — no markdown, no explanation."""


def generate_work_items(
    classification: dict,
    voice_transcript: str | None = None,
    room_type: str = 'unknown',
) -> list[dict]:
    """
    2nd Claude call: synthesize visual classification + voice intent → definitive
    list of materials to buy for the renovation.

    Returns list of {item, action, qty, unit, reason, priority}.
    Falls back to [] on any error so the pipeline continues.
    """
    if not Config.ANTHROPIC_API_KEY:
        logger.warning("[claude_vision] generate_work_items: ANTHROPIC_API_KEY not set")
        return []

    features = classification.get('detected_features', [])
    features_text = json.dumps(features, indent=2) if features else 'No specific features identified'

    prompt = WORK_ITEMS_PROMPT.format(
        room_type=room_type,
        condition=classification.get('condition', 'unknown'),
        features_json=features_text[:1200],
        scope_observations=(classification.get('scope_observations') or '')[:400],
        voice_transcript=(voice_transcript or 'No voice note provided').strip()[:600],
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        logger.info("[claude_vision] work_items raw: %s", raw[:300])
        items = _parse_json_array(raw)
        items = [i for i in items if isinstance(i, dict) and i.get('item')]
        logger.info("[claude_vision] ✓ work_items: %d — %s",
                    len(items), [i['item'] for i in items])
        return items
    except Exception as exc:
        logger.warning("[claude_vision] generate_work_items failed: %s", exc)
        return []


def extract_voice_scope(transcript: str, room_type: str = 'unknown') -> list[dict]:
    """
    Extract structured scope items from a Whisper transcript via Claude.
    Returns list of {item, action, modifier, qty, unit}. Falls back to [] on error.
    """
    if not transcript or not transcript.strip():
        return []

    import anthropic
    if not Config.ANTHROPIC_API_KEY:
        logger.warning("[claude_vision] extract_voice_scope: ANTHROPIC_API_KEY not set")
        return []

    prompt = SCOPE_EXTRACTION_PROMPT.format(
        transcript=transcript.strip()[:800],
        room_type=room_type,
    )

    try:
        client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        logger.info("[claude_vision] voice scope raw: %s", raw[:300])
        items = _parse_json_array(raw)
        # Validate: each item must have an 'item' key
        items = [i for i in items if isinstance(i, dict) and i.get('item')]
        logger.info("[claude_vision] ✓ voice scope: %d item(s) extracted", len(items))
        return items
    except Exception as exc:
        logger.warning("[claude_vision] extract_voice_scope failed: %s", exc)
        return []


class _JsonParseError(Exception):
    pass


def classify_room(
    base64_images: list[str],
    room_hints: list[str] | None = None,
    voice_transcript: str | None = None,
) -> dict:
    """
    Classify room type, condition, and features from base64 JPEG images.
    If voice_transcript is provided, Claude receives it alongside the images
    so both visual and spoken context inform the classification and item list.
    Returns parsed classification dict matching CLASSIFICATION_PROMPT schema.
    """
    import time

    if not base64_images:
        logger.warning("[claude_vision] ✗ no images provided — returning default")
        return _default()

    images = _sample(base64_images, MAX_IMAGES)
    logger.info("[claude_vision] starting — %d image(s) sampled from %d total (cap=%d)",
                len(images), len(base64_images), MAX_IMAGES)

    prompt = CLASSIFICATION_PROMPT

    # Prepend voice transcript so Claude can cross-reference spoken scope
    # with what it sees in the image(s).
    if voice_transcript:
        excerpt = voice_transcript.strip()[:600]
        voice_prefix = (
            f'HOMEOWNER SCOPE NOTE (spoken before the walkthrough):\n'
            f'"{excerpt}"\n\n'
            f'As the contractor, treat this as your primary directive for what the '
            f'homeowner wants done. Use the image(s) to confirm what you see, identify '
            f'items they mentioned, catch anything they missed, and add items you\'d '
            f'recommend doing while the crew is already there.\n'
            f'Voice scope takes priority — if they said "replace countertops", include '
            f'countertops even if the image quality makes them hard to assess.\n\n'
        )
        prompt = voice_prefix + prompt
        logger.info("[claude_vision] voice_transcript prepended (%d chars)", len(excerpt))

    if room_hints:
        hints = ', '.join(room_hints)
        prompt = f"The contractor believes this is a: {hints}.\n\n{prompt}"
        logger.info("[claude_vision] room_hints applied: %s", hints)

    # Try Claude with one JSON-parse retry
    for attempt in range(2):
        try:
            logger.info("[claude_vision] attempt %d — calling claude-haiku-4-5-20251001...", attempt + 1)
            t0 = time.monotonic()
            raw = _call_claude(images, prompt)
            elapsed = (time.monotonic() - t0) * 1000
            logger.info("[claude_vision] ✓ Claude responded in %.0fms — raw=%d chars",
                        elapsed, len(raw))
            logger.debug("[claude_vision] raw response: %s", raw[:500])

            result = _parse_json(raw)
            logger.info(
                "[claude_vision] ✓ parsed — room_type=%s  confidence=%.0f%%  "
                "condition=%s  features=%d  scope=%r",
                result.get('room_type'),
                float(result.get('confidence', 0)) * 100,
                result.get('condition'),
                len(result.get('detected_features', [])),
                (result.get('scope_observations') or '')[:80],
            )
            return result
        except _JsonParseError as exc:
            logger.warning("[claude_vision] attempt %d ✗ JSON parse failed: %s", attempt + 1, exc)
        except Exception as exc:
            logger.warning("[claude_vision] attempt %d ✗ Claude API error: %s", attempt + 1, exc)
            break  # Non-parse error — skip retry

    # GPT-4o Vision fallback
    logger.warning("[claude_vision] Claude failed — falling back to GPT-4o Vision")
    try:
        t0 = time.monotonic()
        raw = _call_gpt4o(images, prompt)
        elapsed = (time.monotonic() - t0) * 1000
        logger.info("[claude_vision] GPT-4o responded in %.0fms", elapsed)
        result = _parse_json(raw)
        result['_fallback'] = 'gpt4o'
        logger.info("[claude_vision] ✓ GPT-4o fallback succeeded — room=%s", result.get('room_type'))
        return result
    except Exception as exc:
        logger.error("[claude_vision] ✗ GPT-4o fallback also failed: %s", exc)
        logger.error("[claude_vision] returning default classification — all vision calls failed")
        return _default()


# ─── Model calls ──────────────────────────────────────────────────────────────

def _call_claude(images: list[str], prompt: str = CLASSIFICATION_PROMPT) -> str:
    import anthropic
    if not Config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    content: list[dict] = []
    for b64 in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    content.append({"type": "text", "text": prompt})

    logger.debug("[claude_vision] sending %d image(s) + prompt to API", len(images))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    usage = response.usage
    logger.info("[claude_vision] token usage — input=%d  output=%d",
                usage.input_tokens, usage.output_tokens)
    return response.content[0].text


def _call_gpt4o(images: list[str], prompt: str = CLASSIFICATION_PROMPT) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    content: list[dict] = []
    for b64 in images[:5]:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
                "detail": "high",
            },
        })
    content.append({"type": "text", "text": prompt})

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    return response.choices[0].message.content or ""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_json_array(raw: str) -> list:
    """Extract JSON array from model response. Returns [] if nothing parses."""
    raw = raw.strip()
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        pass
    match = re.search(r'\[[\s\S]*\]', raw)
    if match:
        try:
            result = json.loads(match.group(0))
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            pass
    return []


def _parse_json(raw: str) -> dict:
    """Extract JSON from model response. Raises _JsonParseError if nothing parses."""
    raw = raw.strip()

    # Direct parse
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise _JsonParseError(f"Expected JSON object, got {type(parsed).__name__}")
        return parsed
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Find outermost { ... } block
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise _JsonParseError(f"No valid JSON in response: {raw[:300]!r}")


def _sample(images: list[str], n: int) -> list[str]:
    """Return up to n evenly-distributed images."""
    if len(images) <= n:
        return images
    step = len(images) / n
    return [images[int(i * step)] for i in range(n)]


def _default() -> dict:
    """Safe fallback when all vision calls fail."""
    return {
        "room_type": "unknown",
        "confidence": 0.0,
        "condition": "fair",
        "condition_notes": "Vision analysis unavailable — add a voice note describing scope.",
        "detected_features": [],
        "scope_observations": "Unable to analyze image. Please describe the scope verbally.",
        "ar_measurement_recommended": True,
        "_fallback": "default",
    }
