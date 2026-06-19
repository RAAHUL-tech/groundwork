"""Unit tests for services/serpapi_prices.py."""
import json
import pytest
from unittest.mock import MagicMock, patch

from services.serpapi_prices import (
    HDPrice,
    _extract_price,
    _median_product,
    _cache_key,
    fetch_hd_price,
    fetch_hd_prices,
    _ITEM_CFG,
    _LABOR_ONLY,
)


# ─── _extract_price ───────────────────────────────────────────────────────────

class TestExtractPrice:
    def test_float_price_field(self):
        assert _extract_price({'price': 49.99}) == pytest.approx(49.99)

    def test_int_price_field(self):
        assert _extract_price({'price': 50}) == pytest.approx(50.0)

    def test_ignores_zero_price(self):
        assert _extract_price({'price': 0}) is None

    def test_ignores_negative_price(self):
        assert _extract_price({'price': -5}) is None

    def test_no_price_returns_none(self):
        assert _extract_price({'title': 'Cabinet'}) is None

    def test_string_primary_price_parsed(self):
        assert _extract_price({'primary_price': '$29.99'}) == pytest.approx(29.99)

    def test_comma_in_string_price(self):
        assert _extract_price({'primary_price': '$1,299.00'}) == pytest.approx(1299.0)

    def test_sale_price_fallback(self):
        assert _extract_price({'sale_price': 39.0}) == pytest.approx(39.0)

    def test_price_takes_priority_over_fallbacks(self):
        assert _extract_price({'price': 10.0, 'sale_price': 20.0}) == pytest.approx(10.0)

    def test_unparseable_string_returns_none(self):
        assert _extract_price({'primary_price': 'call for price'}) is None


# ─── _median_product ──────────────────────────────────────────────────────────

class TestMedianProduct:
    def test_single_product_returned(self):
        p = {'price': 100.0}
        assert _median_product([p]) == p

    def test_three_products_returns_middle(self):
        low  = {'price': 10.0}
        mid  = {'price': 50.0}
        high = {'price': 100.0}
        result = _median_product([high, low, mid])
        assert result == mid

    def test_even_count_returns_upper_middle(self):
        products = [{'price': float(i * 10)} for i in range(1, 5)]
        result = _median_product(products)
        # 4 products, index len//2 = 2, price = 30.0
        assert _extract_price(result) == pytest.approx(30.0)

    def test_all_no_price_returns_none(self):
        assert _median_product([{'title': 'x'}, {'title': 'y'}]) is None

    def test_empty_list_returns_none(self):
        assert _median_product([]) is None

    def test_mixed_priced_and_unpriced(self):
        products = [{'title': 'no price'}, {'price': 50.0}, {'price': 25.0}]
        result = _median_product(products)
        assert result is not None
        assert _extract_price(result) in (25.0, 50.0)


# ─── _cache_key ───────────────────────────────────────────────────────────────

def test_cache_key_format():
    assert _cache_key('cabinets') == 'hd_price:serpapi:v1:cabinets'


# ─── fetch_hd_price ───────────────────────────────────────────────────────────

@pytest.fixture
def no_redis():
    with patch('services.serpapi_prices._redis', return_value=None):
        yield


class TestFetchHdPrice:
    def test_labor_only_item_returns_none(self, no_redis):
        for label in _LABOR_ONLY:
            assert fetch_hd_price(label) is None

    def test_unconfigured_label_returns_none(self, no_redis):
        assert fetch_hd_price('nonexistent_item_xyz') is None

    def test_no_serpapi_key_returns_none(self, no_redis):
        with patch('services.serpapi_prices.Config') as mock_cfg:
            mock_cfg.SERPAPI_KEY = ''
            mock_cfg.HD_PRICE_CACHE_TTL = 21600
            assert fetch_hd_price('cabinets') is None

    def test_cache_hit_returns_cached_value(self):
        cached_data = {
            'unit_price': 150.0, 'unit': 'linear_ft',
            'product_title': 'Test Cabinet', 'product_url': 'http://hd.com/cab',
            'hd_raw_price': 375.0, 'hd_raw_unit': 'each',
        }
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(cached_data)

        with patch('services.serpapi_prices._redis', return_value=mock_redis):
            result = fetch_hd_price('cabinets', '90210')

        assert result is not None
        assert result.unit_price == 150.0
        assert result.source == 'cache'
        mock_redis.get.assert_called_once()

    def test_cache_miss_calls_serpapi(self, no_redis):
        serpapi_response = {
            'products': [
                {'price': 399.0, 'title': 'Cabinet Box', 'link': 'http://hd.com/1'},
                {'price': 499.0, 'title': 'Cabinet Box Premium', 'link': 'http://hd.com/2'},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = serpapi_response

        with patch('requests.get', return_value=mock_resp):
            result = fetch_hd_price('cabinets', '90210')

        # Cabinets: factor = 1/2.5, raw price median = 399, unit_price = 399/2.5 = 159.6
        assert result is not None
        assert result.source == 'serpapi'
        assert result.unit == 'linear_ft'

    def test_serpapi_non_200_returns_none(self, no_redis):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = 'Rate limited'

        with patch('requests.get', return_value=mock_resp):
            result = fetch_hd_price('flooring', '90210')

        assert result is None

    def test_out_of_range_price_returns_none(self, no_redis):
        # Paint min=0.05, max=1.5 per sq_ft. Raw price for a gallon = $999 → way out of range
        serpapi_response = {
            'products': [{'price': 999.0, 'title': 'Expensive Paint', 'link': 'http://hd.com/p'}]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = serpapi_response

        with patch('requests.get', return_value=mock_resp):
            result = fetch_hd_price('paint', '90210')

        assert result is None

    def test_empty_products_returns_none(self, no_redis):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'products': []}

        with patch('requests.get', return_value=mock_resp):
            assert fetch_hd_price('flooring', '90210') is None

    def test_request_exception_returns_none(self, no_redis):
        with patch('requests.get', side_effect=Exception('network error')):
            assert fetch_hd_price('cabinets', '90210') is None

    def test_serpapi_401_returns_none(self, no_redis):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch('requests.get', return_value=mock_resp):
            assert fetch_hd_price('sink', '90210') is None

    def test_successful_result_is_cached(self):
        cached_entry = None
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # cache miss

        def capture_set(key, value, ex=None):
            nonlocal cached_entry
            cached_entry = value

        mock_redis.set.side_effect = capture_set

        serpapi_response = {
            'products': [{'price': 4.5, 'title': 'LVP Floor', 'link': 'http://hd.com/f'}]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = serpapi_response

        with patch('services.serpapi_prices._redis', return_value=mock_redis):
            with patch('requests.get', return_value=mock_resp):
                fetch_hd_price('flooring', '90210')

        assert cached_entry is not None
        cached = json.loads(cached_entry)
        assert 'unit_price' in cached


# ─── fetch_hd_prices ──────────────────────────────────────────────────────────

class TestFetchHdPrices:
    def test_empty_labels_returns_empty_dict(self):
        with patch('services.serpapi_prices._redis', return_value=None):
            assert fetch_hd_prices([]) == {}

    def test_labor_only_labels_map_to_none(self):
        with patch('services.serpapi_prices._redis', return_value=None):
            result = fetch_hd_prices(list(_LABOR_ONLY))
        for label in _LABOR_ONLY:
            assert result[label] is None

    def test_all_labels_present_in_result(self):
        labels = ['cabinets', 'flooring', 'sink']
        with patch('services.serpapi_prices._redis', return_value=None):
            with patch('services.serpapi_prices._serpapi_search', return_value=None):
                result = fetch_hd_prices(labels)
        assert set(result.keys()) == set(labels)

    def test_all_cache_hits_no_http_calls(self):
        cached_data = json.dumps({
            'unit_price': 4.5, 'unit': 'sq_ft',
            'product_title': 'LVP', 'product_url': 'http://hd.com',
            'hd_raw_price': 4.5, 'hd_raw_unit': 'sq_ft',
        })
        mock_redis = MagicMock()
        mock_redis.get.return_value = cached_data

        with patch('services.serpapi_prices._redis', return_value=mock_redis):
            with patch('requests.get') as mock_get:
                result = fetch_hd_prices(['flooring'], '90210')
                mock_get.assert_not_called()

        assert result['flooring'] is not None
        assert result['flooring'].source == 'cache'
