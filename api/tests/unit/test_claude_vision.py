"""Unit tests for services/claude_vision.py."""
import pytest
from unittest.mock import MagicMock, patch, call

from services.claude_vision import (
    _parse_json,
    _parse_json_array,
    _sample,
    _default,
    _JsonParseError,
    classify_room,
    extract_voice_scope,
    generate_work_items,
    MAX_IMAGES,
)


# ─── _parse_json ──────────────────────────────────────────────────────────────

class TestParseJson:
    def test_clean_json_object(self):
        raw = '{"room_type": "kitchen", "confidence": 0.9}'
        result = _parse_json(raw)
        assert result == {'room_type': 'kitchen', 'confidence': 0.9}

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"room_type": "bathroom"}\n```'
        result = _parse_json(raw)
        assert result['room_type'] == 'bathroom'

    def test_json_in_plain_code_fence(self):
        raw = '```\n{"room_type": "bedroom"}\n```'
        result = _parse_json(raw)
        assert result['room_type'] == 'bedroom'

    def test_json_embedded_in_prose(self):
        raw = 'Here is the analysis: {"room_type": "living_room", "confidence": 0.85} Hope that helps!'
        result = _parse_json(raw)
        assert result['room_type'] == 'living_room'

    def test_whitespace_around_json(self):
        raw = '   \n{"room_type": "garage"}\n   '
        result = _parse_json(raw)
        assert result['room_type'] == 'garage'

    def test_invalid_json_raises(self):
        with pytest.raises(_JsonParseError):
            _parse_json('not json at all')

    def test_empty_string_raises(self):
        with pytest.raises(_JsonParseError):
            _parse_json('')

    def test_json_array_at_root_raises(self):
        with pytest.raises(_JsonParseError):
            _parse_json('[1, 2, 3]')


# ─── _parse_json_array ────────────────────────────────────────────────────────

class TestParseJsonArray:
    def test_clean_json_array(self):
        raw = '[{"item": "cabinets"}, {"item": "sink"}]'
        result = _parse_json_array(raw)
        assert len(result) == 2
        assert result[0]['item'] == 'cabinets'

    def test_empty_array(self):
        assert _parse_json_array('[]') == []

    def test_array_embedded_in_prose(self):
        raw = 'Here are items: [{"item": "toilet"}] end.'
        result = _parse_json_array(raw)
        assert result[0]['item'] == 'toilet'

    def test_invalid_json_returns_empty(self):
        assert _parse_json_array('not an array') == []

    def test_object_at_root_returns_empty(self):
        assert _parse_json_array('{"key": "value"}') == []


# ─── _sample ─────────────────────────────────────────────────────────────────

class TestSample:
    def test_fewer_than_n_returns_all(self):
        images = ['a', 'b', 'c']
        assert _sample(images, 5) == images

    def test_exactly_n_returns_all(self):
        images = ['a', 'b', 'c', 'd', 'e']
        assert _sample(images, 5) == images

    def test_more_than_n_returns_n_items(self):
        images = list(range(20))
        result = _sample(images, MAX_IMAGES)
        assert len(result) == MAX_IMAGES

    def test_evenly_distributed(self):
        images = list(range(10))
        result = _sample(images, 5)
        # Should pick indices 0, 2, 4, 6, 8
        assert result == [0, 2, 4, 6, 8]

    def test_single_image_with_large_n(self):
        assert _sample(['only_one'], 10) == ['only_one']


# ─── _default ────────────────────────────────────────────────────────────────

class TestDefault:
    def test_default_has_required_keys(self):
        result = _default()
        assert 'room_type' in result
        assert 'confidence' in result
        assert 'condition' in result
        assert 'detected_features' in result

    def test_default_room_type_is_unknown(self):
        assert _default()['room_type'] == 'unknown'

    def test_default_confidence_is_zero(self):
        assert _default()['confidence'] == 0.0

    def test_default_has_fallback_marker(self):
        assert _default().get('_fallback') == 'default'


# ─── classify_room ───────────────────────────────────────────────────────────

VALID_CLAUDE_RESPONSE = {
    'room_type': 'kitchen',
    'confidence': 0.92,
    'condition': 'fair',
    'condition_notes': 'Cabinets worn',
    'detected_features': [
        {'item': 'cabinets', 'estimated_qty': 18.5, 'unit': 'linear_ft',
         'condition': 'fair', 'recommendation': 'replace', 'priority': 'must', 'notes': ''}
    ],
    'scope_observations': 'Full kitchen remodel needed.',
    'contractor_upsells': [],
    'ar_measurement_recommended': False,
}


@pytest.fixture
def mock_anthropic_response():
    import json
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(VALID_CLAUDE_RESPONSE))]
    mock_msg.usage = MagicMock(input_tokens=100, output_tokens=200)
    return mock_msg


class TestClassifyRoom:
    def test_no_images_returns_default(self):
        result = classify_room([])
        assert result['room_type'] == 'unknown'
        assert result.get('_fallback') == 'default'

    def test_successful_classification(self, mock_anthropic_response):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = classify_room(['base64data'])

        assert result['room_type'] == 'kitchen'
        assert result['confidence'] == 0.92

    def test_samples_images_up_to_max(self, mock_anthropic_response):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response

        images = ['img' + str(i) for i in range(20)]
        with patch('anthropic.Anthropic', return_value=mock_client):
            classify_room(images)

        call_args = mock_client.messages.create.call_args
        sent_content = call_args[1]['messages'][0]['content']
        image_blocks = [b for b in sent_content if b.get('type') == 'image']
        assert len(image_blocks) <= MAX_IMAGES

    def test_room_hints_prepended_to_prompt(self, mock_anthropic_response):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response

        with patch('anthropic.Anthropic', return_value=mock_client):
            classify_room(['base64data'], room_hints=['bathroom'])

        call_args = mock_client.messages.create.call_args
        text_block = next(
            b for b in call_args[1]['messages'][0]['content'] if b.get('type') == 'text'
        )
        assert 'bathroom' in text_block['text'].lower()

    def test_json_parse_failure_retries_once(self):
        import json
        bad_response = MagicMock()
        bad_response.content = [MagicMock(text='not json at all')]
        bad_response.usage = MagicMock(input_tokens=0, output_tokens=0)

        good_response = MagicMock()
        good_response.content = [MagicMock(text=json.dumps(VALID_CLAUDE_RESPONSE))]
        good_response.usage = MagicMock(input_tokens=100, output_tokens=200)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [bad_response, good_response]

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = classify_room(['base64data'])

        assert result['room_type'] == 'kitchen'
        assert mock_client.messages.create.call_count == 2

    def test_claude_failure_falls_back_to_gpt4o(self):
        import json
        mock_claude_client = MagicMock()
        mock_claude_client.messages.create.side_effect = Exception('API error')

        gpt_response = MagicMock()
        gpt_response.choices = [MagicMock(message=MagicMock(content=json.dumps(VALID_CLAUDE_RESPONSE)))]

        mock_oai_client = MagicMock()
        mock_oai_client.chat.completions.create.return_value = gpt_response

        with patch('anthropic.Anthropic', return_value=mock_claude_client):
            with patch('openai.OpenAI', return_value=mock_oai_client):
                result = classify_room(['base64data'])

        assert result['room_type'] == 'kitchen'
        assert result.get('_fallback') == 'gpt4o'

    def test_all_providers_fail_returns_default(self):
        mock_claude_client = MagicMock()
        mock_claude_client.messages.create.side_effect = Exception('Claude down')

        mock_oai_client = MagicMock()
        mock_oai_client.chat.completions.create.side_effect = Exception('OpenAI down')

        with patch('anthropic.Anthropic', return_value=mock_claude_client):
            with patch('openai.OpenAI', return_value=mock_oai_client):
                result = classify_room(['base64data'])

        assert result['room_type'] == 'unknown'
        assert result.get('_fallback') == 'default'


# ─── extract_voice_scope ─────────────────────────────────────────────────────

class TestExtractVoiceScope:
    def test_empty_transcript_returns_empty(self):
        assert extract_voice_scope('') == []
        assert extract_voice_scope('   ') == []

    def test_successful_extraction(self):
        scope_items = [
            {'item': 'cabinets', 'action': 'replace', 'modifier': 'standard', 'qty': None, 'unit': None}
        ]
        import json
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(scope_items))]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = extract_voice_scope('Replace the kitchen cabinets', 'kitchen')

        assert len(result) == 1
        assert result[0]['item'] == 'cabinets'

    def test_api_error_returns_empty(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception('timeout')

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = extract_voice_scope('Replace the sink', 'kitchen')

        assert result == []

    def test_invalid_json_response_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text='I cannot help with that.')]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = extract_voice_scope('Replace everything', 'kitchen')

        assert result == []

    def test_items_without_item_key_filtered(self):
        import json
        items = [{'action': 'replace'}, {'item': 'sink', 'action': 'replace'}]
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(items))]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = extract_voice_scope('Replace sink', 'kitchen')

        assert len(result) == 1
        assert result[0]['item'] == 'sink'


# ─── generate_work_items ─────────────────────────────────────────────────────

class TestGenerateWorkItems:
    def test_successful_generation(self):
        import json
        classification = {
            'condition': 'fair',
            'detected_features': [
                {'item': 'cabinets', 'estimated_qty': 18.5, 'condition': 'fair',
                 'recommendation': 'replace', 'priority': 'must', 'notes': ''}
            ],
            'scope_observations': 'Kitchen remodel needed.',
        }
        work_items = [
            {'item': 'cabinets', 'action': 'replace', 'qty': 18.5,
             'unit': 'linear_ft', 'reason': 'Worn cabinets', 'priority': 'must'}
        ]
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(work_items))]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = generate_work_items(classification, 'Replace cabinets', 'kitchen')

        assert len(result) == 1
        assert result[0]['item'] == 'cabinets'

    def test_api_error_returns_empty(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception('timeout')

        with patch('anthropic.Anthropic', return_value=mock_client):
            result = generate_work_items({'detected_features': []}, None, 'kitchen')

        assert result == []
