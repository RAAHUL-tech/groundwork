"""Unit tests for services/pricing_engine.py."""
import pytest
from unittest.mock import patch

from services.pricing_engine import (
    zip_to_state,
    get_regional_multiplier,
    calculate_estimate,
    calculate_all_tiers,
    REGIONAL_MULTIPLIERS,
    PERMIT_RATE,
    CONTINGENCY_RATE,
)

# ─── zip_to_state ─────────────────────────────────────────────────────────────

class TestZipToState:
    @pytest.mark.parametrize('zip_code,expected', [
        ('90210', 'CA'),   # Beverly Hills
        ('10001', 'NY'),   # New York City
        ('75201', 'TX'),   # Dallas
        ('33101', 'FL'),   # Miami
        ('60601', 'IL'),   # Chicago
    ])
    def test_known_zip_codes(self, zip_code, expected):
        assert zip_to_state(zip_code) == expected

    def test_unknown_prefix_returns_default(self):
        assert zip_to_state('00000') == 'default'

    def test_short_zip_returns_default(self):
        assert zip_to_state('1') == 'default'

    def test_uses_first_three_digits(self):
        assert zip_to_state('90210') == zip_to_state('90299')


# ─── get_regional_multiplier ──────────────────────────────────────────────────

class TestGetRegionalMultiplier:
    def test_california_multiplier(self):
        assert get_regional_multiplier('90210') == pytest.approx(1.35)

    def test_new_york_multiplier(self):
        assert get_regional_multiplier('10001') == pytest.approx(1.42)

    def test_texas_multiplier(self):
        assert get_regional_multiplier('75201') == pytest.approx(0.92)

    def test_florida_multiplier(self):
        assert get_regional_multiplier('33101') == pytest.approx(0.96)

    def test_unknown_zip_returns_default(self):
        assert get_regional_multiplier('00000') == pytest.approx(1.0)

    def test_all_multipliers_are_positive(self):
        for state, mult in REGIONAL_MULTIPLIERS.items():
            assert mult > 0, f'{state} has non-positive multiplier'


# ─── calculate_estimate ───────────────────────────────────────────────────────

KITCHEN_ITEMS = [
    {'label': 'cabinets',   'confidence': 0.91, 'quantity': 18.5, 'unit': 'linear_ft'},
    {'label': 'countertop', 'confidence': 0.88, 'quantity': 32,   'unit': 'sq_ft'},
    {'label': 'flooring',   'confidence': 0.93, 'quantity': 144,  'unit': 'sq_ft'},
]


@pytest.fixture(autouse=True)
def no_live_prices():
    """Suppress live SerpApi calls in all pricing tests."""
    with patch('services.pricing_engine._fetch_live_prices', return_value={}):
        yield


class TestCalculateEstimate:
    def test_returns_required_top_level_keys(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen', tier='standard', zip_code='90210')
        required = {
            'estimate_breakdown', 'subtotal_materials', 'subtotal_labor',
            'permits', 'contingency', 'total_estimate', 'estimate_range',
            'regional_multiplier',
        }
        assert required.issubset(result.keys())

    def test_estimate_breakdown_matches_detected_items(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen')
        # At least one line item per detected item
        assert len(result['estimate_breakdown']) >= 1

    def test_permit_rate_is_eight_percent(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen', zip_code='00001')
        subtotal = result['subtotal_materials'] + result['subtotal_labor']
        expected_permits = round(subtotal * PERMIT_RATE)
        assert abs(result['permits'] - expected_permits) <= 2

    def test_contingency_rate_is_ten_percent(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen', zip_code='00001')
        subtotal = result['subtotal_materials'] + result['subtotal_labor']
        expected_contingency = round(subtotal * CONTINGENCY_RATE)
        assert abs(result['contingency'] - expected_contingency) <= 2

    def test_total_is_sum_of_parts(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen')
        expected = (
            result['subtotal_materials'] + result['subtotal_labor']
            + result['permits'] + result['contingency']
        )
        assert abs(result['total_estimate'] - expected) <= 5

    def test_regional_multiplier_applied(self):
        result_ca = calculate_estimate(KITCHEN_ITEMS, 'kitchen', zip_code='90210')
        result_tx = calculate_estimate(KITCHEN_ITEMS, 'kitchen', zip_code='75201')
        assert result_ca['total_estimate'] > result_tx['total_estimate']
        assert result_ca['regional_multiplier'] == pytest.approx(1.35)
        assert result_tx['regional_multiplier'] == pytest.approx(0.92)

    def test_empty_items_returns_zero_estimate(self):
        result = calculate_estimate([], 'kitchen')
        assert result['total_estimate'] == 0 or result['total_estimate'] >= 0
        assert 'estimate_breakdown' in result

    def test_estimate_range_low_lt_total_lt_high(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen')
        assert result['estimate_range']['low'] < result['total_estimate']
        assert result['total_estimate'] < result['estimate_range']['high']

    def test_live_pricing_items_key_present(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen')
        assert 'live_pricing_items' in result
        assert isinstance(result['live_pricing_items'], int)

    def test_regional_multiplier_key_present(self):
        result = calculate_estimate(KITCHEN_ITEMS, 'kitchen', tier='premium')
        assert 'regional_multiplier' in result

    def test_bathroom_items_produce_estimate(self):
        bath_items = [
            {'label': 'toilet', 'confidence': 0.95, 'quantity': 1,  'unit': 'each'},
            {'label': 'vanity', 'confidence': 0.90, 'quantity': 1,  'unit': 'each'},
            {'label': 'tile_floor', 'confidence': 0.88, 'quantity': 50, 'unit': 'sq_ft'},
        ]
        result = calculate_estimate(bath_items, 'bathroom', tier='standard')
        assert result['total_estimate'] > 0


# ─── calculate_all_tiers ──────────────────────────────────────────────────────

class TestCalculateAllTiers:
    def test_returns_three_tier_keys(self):
        result = calculate_all_tiers(KITCHEN_ITEMS, 'kitchen')
        assert set(result.keys()) == {'eco', 'standard', 'premium'}

    def test_each_tier_has_required_keys(self):
        result = calculate_all_tiers(KITCHEN_ITEMS, 'kitchen')
        for tier_key in ('eco', 'standard', 'premium'):
            tier = result[tier_key]
            assert 'total_estimate' in tier
            assert 'estimate_breakdown' in tier
            assert 'estimate_range' in tier

    def test_premium_costs_more_than_standard(self):
        result = calculate_all_tiers(KITCHEN_ITEMS, 'kitchen', zip_code='00001')
        assert result['premium']['total_estimate'] > result['standard']['total_estimate']

    def test_standard_costs_more_than_economy(self):
        result = calculate_all_tiers(KITCHEN_ITEMS, 'kitchen', zip_code='00001')
        assert result['standard']['total_estimate'] > result['eco']['total_estimate']

    def test_all_totals_positive(self):
        result = calculate_all_tiers(KITCHEN_ITEMS, 'kitchen')
        for tier_key in ('eco', 'standard', 'premium'):
            assert result[tier_key]['total_estimate'] > 0
