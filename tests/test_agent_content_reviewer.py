from types import SimpleNamespace

import pytest

import agent_content_reviewer as reviewer


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def get_final_message(self):
        return self.response


class FakeMessages:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(next(self.responses))


def response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )


def test_claims_by_path_indexes_schema_output():
    result = {
        "claims": [
            {"path": "en.summary", "status": "verified"},
            {"path": "ja.summary", "status": "verified"},
        ]
    }

    assert set(reviewer._claims_by_path(result)) == {"en.summary", "ja.summary"}


def test_claims_by_path_rejects_duplicates():
    result = {"claims": [{"path": "en.summary"}, {"path": "en.summary"}]}

    with pytest.raises(ValueError, match="duplicate claim path"):
        reviewer._claims_by_path(result)


def test_set_claim_text_updates_nested_list_value():
    content = {
        "en": {
            "seasonal_produce": {
                "fruits": ["old fruit"],
            }
        }
    }

    reviewer._set_claim_text(
        content, "en.seasonal_produce.fruits[0]", "supported fruit"
    )

    assert content["en"]["seasonal_produce"]["fruits"][0] == "supported fruit"


def test_repair_candidate_requires_exact_failed_path_set(monkeypatch):
    content = {"en": {"summary": "unsupported"}}
    failed = [{"path": "en.summary", "text": "unsupported"}]
    monkeypatch.setattr(
        reviewer,
        "_call_with_search",
        lambda *_: {
            "replacements": [{"path": "en.summary", "value": "supported"}]
        },
    )

    count = reviewer._repair_candidate(object(), {}, content, failed)

    assert count == 1
    assert content["en"]["summary"] == "supported"


def test_call_with_search_streams_structured_output_with_larger_budget():
    messages = FakeMessages([response('{"claims": []}')])
    client = SimpleNamespace(messages=messages)

    result = reviewer._call_with_search(
        client, "review this", reviewer.RESEARCH_OUTPUT_SCHEMA
    )

    assert result == {"claims": []}
    call = messages.calls[0]
    assert call["max_tokens"] == reviewer.MAX_OUTPUT_TOKENS
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert (
        call["output_config"]["format"]["schema"]
        is reviewer.RESEARCH_OUTPUT_SCHEMA
    )
    confidence_schema = reviewer.RESEARCH_CLAIM_SCHEMA["properties"]["confidence"]
    assert confidence_schema == {"type": "number"}


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_call_with_search_fails_closed_on_incomplete_output(stop_reason):
    messages = FakeMessages([response('{"claims": []}', stop_reason)])
    client = SimpleNamespace(messages=messages)

    with pytest.raises(RuntimeError, match=stop_reason):
        reviewer._call_with_search(
            client, "review this", reviewer.RESEARCH_OUTPUT_SCHEMA
        )
