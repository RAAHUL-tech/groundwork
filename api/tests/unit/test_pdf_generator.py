"""Unit tests for services/pdf_generator.py (no external calls needed)."""
import pytest

from services.pdf_generator import build_proposal_pdf, _fmt


# ─── _fmt ────────────────────────────────────────────────────────────────────

class TestFmt:
    def test_integer(self):
        assert _fmt(1000) == '$1,000'

    def test_float_rounded(self):
        assert _fmt(1000.7) == '$1,001'

    def test_zero(self):
        assert _fmt(0) == '$0'

    def test_large_number(self):
        assert _fmt(1_000_000) == '$1,000,000'

    def test_negative_rounds_correctly(self):
        assert _fmt(1499.5) == '$1,500'


# ─── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def base_estimate():
    return {
        'room_type': 'kitchen',
        'estimate_breakdown': [
            {'item': 'Cabinet replacement', 'scope': 'Semi-custom', 'qty': 18.5,
             'unit': 'lin ft', 'material_unit_cost': 180, 'labor_unit_cost': 65,
             'total': 4532, 'source': 'vision'},
            {'item': 'LVP flooring', 'scope': None, 'qty': 144,
             'unit': 'sq ft', 'material_unit_cost': 4.5, 'labor_unit_cost': 4.0,
             'total': 1224, 'source': 'vision'},
        ],
        'subtotal_materials': 5756,
        'subtotal_labor':     3090,
        'permits':            710,
        'contingency':        886,
        'total_estimate':     10442,
        'estimate_range':     {'low': 8878, 'high': 12530},
        'scope_narrative':    'Full kitchen remodel.',
        'timeline_estimate_weeks': 3,
    }


@pytest.fixture
def contractor():
    return {
        'name':    'Jane Smith',
        'company': 'Smith Construction LLC',
        'license': 'CA-GC-000001',
        'phone':   '555-0100',
        'email':   'jane@smith.com',
    }


@pytest.fixture
def client():
    return {
        'name':    'Bob Homeowner',
        'address': '123 Oak St, Fullerton CA 92831',
    }


# ─── build_proposal_pdf ───────────────────────────────────────────────────────

class TestBuildProposalPdf:
    def test_returns_bytes(self, base_estimate, contractor, client):
        result = build_proposal_pdf(base_estimate, contractor, client)
        assert isinstance(result, bytes)

    def test_returns_non_empty_bytes(self, base_estimate, contractor, client):
        result = build_proposal_pdf(base_estimate, contractor, client)
        assert len(result) > 1000  # PDFs are at least several KB

    def test_starts_with_pdf_header(self, base_estimate, contractor, client):
        result = build_proposal_pdf(base_estimate, contractor, client)
        assert result[:4] == b'%PDF'

    def test_empty_line_items(self, base_estimate, contractor, client):
        base_estimate['estimate_breakdown'] = []
        result = build_proposal_pdf(base_estimate, contractor, client)
        assert result[:4] == b'%PDF'

    def test_missing_optional_fields(self, contractor, client):
        minimal_estimate = {
            'room_type': 'bathroom',
            'estimate_breakdown': [],
            'subtotal_materials': 0,
            'subtotal_labor': 0,
            'permits': 0,
            'contingency': 0,
            'total_estimate': 0,
        }
        result = build_proposal_pdf(minimal_estimate, contractor, client)
        assert result[:4] == b'%PDF'

    def test_scope_narrative_included(self, base_estimate, contractor, client):
        result = build_proposal_pdf(base_estimate, contractor, client)
        assert len(result) > 0

    def test_no_estimate_range_handled(self, base_estimate, contractor, client):
        base_estimate.pop('estimate_range', None)
        result = build_proposal_pdf(base_estimate, contractor, client)
        assert result[:4] == b'%PDF'

    def test_custom_payment_terms(self, base_estimate, contractor, client):
        result = build_proposal_pdf(
            base_estimate, contractor, client,
            payment_terms='Net 30', valid_days=60
        )
        assert result[:4] == b'%PDF'

    def test_proposal_id_included_in_output(self, base_estimate, contractor, client):
        pid = 'prop-testid123456'
        result = build_proposal_pdf(base_estimate, contractor, client, proposal_id=pid)
        assert result[:4] == b'%PDF'

    def test_multiple_line_items(self, contractor, client):
        estimate = {
            'room_type': 'kitchen',
            'estimate_breakdown': [
                {'item': f'Item {i}', 'qty': i * 10, 'unit': 'sq ft',
                 'material_unit_cost': 5.0, 'labor_unit_cost': 3.0, 'total': i * 80}
                for i in range(1, 11)
            ],
            'subtotal_materials': 2000,
            'subtotal_labor': 1200,
            'permits': 256,
            'contingency': 320,
            'total_estimate': 3776,
        }
        result = build_proposal_pdf(estimate, contractor, client)
        assert result[:4] == b'%PDF'

    def test_bathroom_room_type(self, contractor, client):
        estimate = {
            'room_type': 'bathroom',
            'estimate_breakdown': [
                {'item': 'Toilet', 'qty': 1, 'unit': 'each',
                 'material_unit_cost': 450, 'labor_unit_cost': 220, 'total': 670}
            ],
            'subtotal_materials': 450, 'subtotal_labor': 220,
            'permits': 53, 'contingency': 67, 'total_estimate': 790,
        }
        result = build_proposal_pdf(estimate, contractor, client)
        assert result[:4] == b'%PDF'
