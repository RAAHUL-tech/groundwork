"""
Supabase DB layer — typed CRUD functions for all tables.

Uses the service role key, so RLS is bypassed.
All public-facing auth checks happen at the Flask middleware layer.
"""
import logging
from typing import Optional
from typing_extensions import TypedDict, NotRequired

from supabase import create_client, Client
from config import Config

logger = logging.getLogger(__name__)

# ─── Singleton client ─────────────────────────────────────────────────────────

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        if not Config.SUPABASE_URL or not Config.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
            )
        _client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_KEY)
    return _client


# ─── Row type definitions ─────────────────────────────────────────────────────

class ProjectRow(TypedDict, total=False):
    id: str
    user_id: str
    name: str
    client_name: NotRequired[Optional[str]]
    client_address: NotRequired[Optional[str]]
    status: str                          # active | proposal_sent | in_progress | complete
    total_estimate: NotRequired[Optional[float]]
    created_at: str
    updated_at: str


class RoomScanRow(TypedDict, total=False):
    id: str
    project_id: NotRequired[Optional[str]]
    room_label: NotRequired[Optional[str]]
    room_type: NotRequired[Optional[str]]
    room_confidence: NotRequired[Optional[float]]
    condition: NotRequired[Optional[str]]  # poor | fair | good | excellent
    image_urls: list
    video_url: NotRequired[Optional[str]]
    voice_transcript: NotRequired[Optional[str]]
    celery_job_id: NotRequired[Optional[str]]
    status: str                            # pending | processing | complete | failed
    created_at: str


class EstimateRow(TypedDict, total=False):
    id: str
    room_scan_id: str
    project_id: str
    tier: str                             # economy | standard | premium
    subtotal_materials: NotRequired[Optional[float]]
    subtotal_labor: NotRequired[Optional[float]]
    permits: NotRequired[Optional[float]]
    contingency: NotRequired[Optional[float]]
    total_estimate: NotRequired[Optional[float]]
    estimate_low: NotRequired[Optional[float]]
    estimate_high: NotRequired[Optional[float]]
    confidence_score: NotRequired[Optional[float]]
    confidence_label: NotRequired[Optional[str]]
    regional_multiplier: NotRequired[Optional[float]]
    scope_narrative: NotRequired[Optional[str]]
    timeline_weeks: NotRequired[Optional[int]]
    raw_response: NotRequired[Optional[dict]]
    created_at: str


class EstimateLineItemRow(TypedDict, total=False):
    id: str
    estimate_id: str
    item_label: str
    scope_description: NotRequired[Optional[str]]
    quantity: NotRequired[Optional[float]]
    unit: NotRequired[Optional[str]]
    material_unit_cost: NotRequired[Optional[float]]
    labor_unit_cost: NotRequired[Optional[float]]
    total: NotRequired[Optional[float]]
    hd_price_reference: NotRequired[Optional[str]]
    source: NotRequired[Optional[str]]             # vision | voice | manual
    detection_confidence: NotRequired[Optional[float]]
    sort_order: int


class ProposalRow(TypedDict, total=False):
    id: str
    project_id: str
    estimate_id: str
    pdf_url: NotRequired[Optional[str]]
    contractor_snapshot: dict
    client_snapshot: dict
    payment_terms: NotRequired[Optional[str]]
    valid_until: NotRequired[Optional[str]]
    sent_at: NotRequired[Optional[str]]
    status: str                                    # draft | sent | approved | rejected
    created_at: str


# ─── PROJECTS ─────────────────────────────────────────────────────────────────

def create_project(user_id: str, name: str, **kwargs) -> ProjectRow:
    result = get_db().table('projects').insert({
        'user_id': user_id,
        'name': name,
        **kwargs,
    }).execute()
    return result.data[0]


def get_project(project_id: str) -> Optional[ProjectRow]:
    result = get_db().table('projects').select('*').eq('id', project_id).maybe_single().execute()
    return result.data


def list_projects(user_id: str) -> list[ProjectRow]:
    result = (
        get_db().table('projects')
        .select('*')
        .eq('user_id', user_id)
        .order('created_at', desc=True)
        .execute()
    )
    return result.data


def update_project(project_id: str, **kwargs) -> Optional[ProjectRow]:
    result = get_db().table('projects').update(kwargs).eq('id', project_id).execute()
    return result.data[0] if result.data else None


def delete_project(project_id: str) -> bool:
    get_db().table('projects').delete().eq('id', project_id).execute()
    return True


# ─── ROOM SCANS ───────────────────────────────────────────────────────────────

def create_room_scan(project_id: Optional[str] = None, **kwargs) -> RoomScanRow:
    row: dict = {**kwargs}
    if project_id:
        row['project_id'] = project_id
    logger.info("[db] INSERT room_scans  project_id=%s  status=%s", project_id, row.get('status'))
    result = get_db().table('room_scans').insert(row).execute()
    scan = result.data[0]
    logger.info("[db] ✓ room_scan created  id=%s", scan['id'])
    return scan


def get_room_scan(room_scan_id: str) -> Optional[RoomScanRow]:
    result = (
        get_db().table('room_scans')
        .select('*')
        .eq('id', room_scan_id)
        .maybe_single()
        .execute()
    )
    return result.data


def get_room_scan_by_job(celery_job_id: str) -> Optional[RoomScanRow]:
    result = (
        get_db().table('room_scans')
        .select('*')
        .eq('celery_job_id', celery_job_id)
        .maybe_single()
        .execute()
    )
    return result.data


def update_room_scan(room_scan_id: str, **kwargs) -> Optional[RoomScanRow]:
    logger.info("[db] UPDATE room_scans  id=%s  fields=%s", room_scan_id, list(kwargs.keys()))
    result = (
        get_db().table('room_scans')
        .update(kwargs)
        .eq('id', room_scan_id)
        .execute()
    )
    ok = bool(result.data)
    logger.info("[db] %s room_scan updated  id=%s", '✓' if ok else '✗ no rows', room_scan_id)
    return result.data[0] if result.data else None


def list_room_scans(project_id: str) -> list[RoomScanRow]:
    result = (
        get_db().table('room_scans')
        .select('*')
        .eq('project_id', project_id)
        .order('created_at', desc=True)
        .execute()
    )
    return result.data


# ─── ESTIMATES ────────────────────────────────────────────────────────────────

def create_estimate(room_scan_id: Optional[str] = None,
                    project_id: Optional[str] = None, **kwargs) -> EstimateRow:
    row: dict = {**kwargs}
    if room_scan_id:
        row['room_scan_id'] = room_scan_id
    if project_id:
        row['project_id'] = project_id
    logger.info("[db] INSERT estimates  room_scan_id=%s  project_id=%s  total=%s",
                room_scan_id, project_id, row.get('total_estimate'))
    result = get_db().table('estimates').insert(row).execute()
    est = result.data[0]
    logger.info("[db] ✓ estimate created  id=%s", est['id'])
    return est


def get_estimate(estimate_id: str) -> Optional[EstimateRow]:
    result = (
        get_db().table('estimates')
        .select('*')
        .eq('id', estimate_id)
        .maybe_single()
        .execute()
    )
    return result.data


def get_estimate_by_room_scan(room_scan_id: str) -> Optional[EstimateRow]:
    result = (
        get_db().table('estimates')
        .select('*')
        .eq('room_scan_id', room_scan_id)
        .order('created_at', desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_estimates_by_project(project_id: str) -> list[EstimateRow]:
    result = (
        get_db().table('estimates')
        .select('*')
        .eq('project_id', project_id)
        .order('created_at', desc=True)
        .execute()
    )
    return result.data


# ─── ESTIMATE LINE ITEMS ──────────────────────────────────────────────────────

def bulk_create_line_items(
    estimate_id: str, items: list[dict]
) -> list[EstimateLineItemRow]:
    rows = [
        {'estimate_id': estimate_id, 'sort_order': idx, **item}
        for idx, item in enumerate(items)
    ]
    logger.info("[db] INSERT estimate_line_items  estimate_id=%s  count=%d", estimate_id, len(rows))
    result = get_db().table('estimate_line_items').insert(rows).execute()
    logger.info("[db] ✓ %d line item(s) created", len(result.data))
    return result.data


def get_line_items(estimate_id: str) -> list[EstimateLineItemRow]:
    result = (
        get_db().table('estimate_line_items')
        .select('*')
        .eq('estimate_id', estimate_id)
        .order('sort_order')
        .execute()
    )
    return result.data


def delete_line_items(estimate_id: str) -> bool:
    get_db().table('estimate_line_items').delete().eq('estimate_id', estimate_id).execute()
    return True


# ─── PROPOSALS ────────────────────────────────────────────────────────────────

def create_proposal(project_id: str, estimate_id: str, **kwargs) -> ProposalRow:
    result = get_db().table('proposals').insert({
        'project_id': project_id,
        'estimate_id': estimate_id,
        **kwargs,
    }).execute()
    return result.data[0]


def get_proposal(proposal_id: str) -> Optional[ProposalRow]:
    result = (
        get_db().table('proposals')
        .select('*')
        .eq('id', proposal_id)
        .maybe_single()
        .execute()
    )
    return result.data


def update_proposal(proposal_id: str, **kwargs) -> Optional[ProposalRow]:
    result = (
        get_db().table('proposals')
        .update(kwargs)
        .eq('id', proposal_id)
        .execute()
    )
    return result.data[0] if result.data else None


def list_proposals_by_project(project_id: str) -> list[ProposalRow]:
    result = (
        get_db().table('proposals')
        .select('*')
        .eq('project_id', project_id)
        .order('created_at', desc=True)
        .execute()
    )
    return result.data
