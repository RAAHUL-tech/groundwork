"""
Shared test configuration and fixtures.

Environment variables must be set before any app-module imports so that
Config and module-level singletons (Celery, limiter) pick up test values.
"""
import os
import sys

# ── Must be set before any application imports ────────────────────────────────
os.environ.update({
    'FLASK_ENV':             'testing',
    'REDIS_URL':             'memory://',          # Flask-Limiter in-process storage
    'SUPABASE_URL':          'https://test.supabase.co',
    'SUPABASE_SERVICE_KEY':  'eyJtest',
    'SUPABASE_JWT_SECRET':   'test-secret-at-least-32-chars-long-xx',
    'AWS_ACCESS_KEY_ID':     'AKIATEST',
    'AWS_SECRET_ACCESS_KEY': 'test/secret',
    'S3_BUCKET':             'test-bucket',
    'S3_REGION':             'us-east-1',
    'ANTHROPIC_API_KEY':     'sk-ant-test',
    'OPENAI_API_KEY':        'sk-test',
    'SERPAPI_KEY':           'test-serpapi-key',
    'DEV_PROJECT_ID':        'dev-project-uuid',
})

# Put api/ directory on sys.path so imports work from any working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import MagicMock, patch


# ─── App / client ─────────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def app():
    """Create the Flask test application once for the entire test session."""
    # Prevent supabase.create_client from trying to reach the network
    with patch('supabase.create_client', return_value=MagicMock()):
        from app import create_app
        application = create_app()
        application.config['TESTING'] = True
        application.config['RATELIMIT_ENABLED'] = False
        yield application


@pytest.fixture
def client(app):
    """Fresh test client per test function."""
    return app.test_client()


# ─── Sample data ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_estimate():
    """Realistic estimate result dict matching the pipeline output schema."""
    return {
        'room_type':          'kitchen',
        'room_confidence':    0.92,
        'condition':          'fair',
        'condition_notes':    'Cabinets show wear, countertops are dated.',
        'scope_narrative':    'Kitchen remodel including cabinet replacement and LVP flooring.',
        'timeline_estimate_weeks': 3,
        'zip_code':           '90210',
        'tier':               'standard',
        'regional_multiplier': 1.0,
        'vision_detected_features': [
            {'item': 'cabinets',   'estimated_qty': 18.5, 'unit': 'linear_ft',
             'condition': 'fair', 'notes': 'Upper and lower cabinet run'},
            {'item': 'countertop', 'estimated_qty': 32,   'unit': 'sq_ft',
             'condition': 'poor', 'notes': 'Laminate, heavily worn'},
            {'item': 'flooring',   'estimated_qty': 144,  'unit': 'sq_ft',
             'condition': 'fair', 'notes': 'Linoleum, dated'},
        ],
        'detected_items': [
            {'label': 'cabinets',   'confidence': 0.91, 'quantity': 18.5, 'unit': 'linear_ft'},
            {'label': 'countertop', 'confidence': 0.88, 'quantity': 32,   'unit': 'sq_ft'},
            {'label': 'flooring',   'confidence': 0.93, 'quantity': 144,  'unit': 'sq_ft'},
        ],
        'work_items': [
            {'item': 'cabinets',   'action': 'replace', 'qty': 18.5, 'unit': 'linear_ft',
             'reason': 'Visible wear', 'priority': 'must'},
            {'item': 'countertop', 'action': 'replace', 'qty': 32,   'unit': 'sq_ft',
             'reason': 'Laminate beyond useful life', 'priority': 'must'},
        ],
        'estimate_breakdown': [
            {'item': 'Cabinet replacement', 'scope': 'Semi-custom cabinets', 'qty': 18.5,
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
        'confidence': {
            'score': 0.84, 'label': 'High', 'range_pct': 15,
            'factors': {'vision_confidence': 0.91, 'voice_scope_provided': False},
        },
        '_estimate_db_id': 'est-uuid-1234',
        '_project_id':     'proj-uuid-1234',
        '_room_scan_id':   'scan-uuid-1234',
    }


@pytest.fixture
def sample_contractor():
    return {
        'name':    'Jane Smith',
        'company': 'Smith Construction LLC',
        'license': 'CA-GC-000001',
        'phone':   '555-0100',
        'email':   'jane@smithconstruction.com',
    }


@pytest.fixture
def sample_client_info():
    return {
        'name':    'Bob Homeowner',
        'address': '123 Oak St, Fullerton CA 92831',
        'phone':   '555-0200',
        'email':   'bob@example.com',
    }


@pytest.fixture
def sample_project():
    return {
        'id':             'proj-uuid-1234',
        'name':           'Oak Street Kitchen Remodel',
        'client_name':    'Bob Homeowner',
        'client_address': '123 Oak St, Fullerton CA 92831',
        'status':         'active',
        'total_estimate': 10442.0,
        'created_at':     '2026-06-01T10:00:00Z',
    }


@pytest.fixture
def sample_project_aggregate(sample_project):
    return {
        **sample_project,
        'rooms': [
            {'id': 'pr-1', 'room_label': 'Kitchen', 'total_estimate': 10442.0,
             'room_scan_id': 'scan-uuid-1234', 'estimate_id': 'est-uuid-1234',
             'added_at': '2026-06-01T10:05:00Z'},
        ],
        'aggregate': {
            'room_count': 1,
            'subtotal':   10442,
            'mobilization': 0,
            'grand_total':  10442,
        },
    }
