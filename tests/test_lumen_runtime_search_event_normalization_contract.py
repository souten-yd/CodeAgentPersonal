from app.services.lumen_runtime import normalize_lumen_runtime_event


def test_normalize_lumen_runtime_event_exists():
    assert callable(normalize_lumen_runtime_event)


def test_web_results_are_normalized_to_search_items():
    event = normalize_lumen_runtime_event(
        {
            "type": "web_search",
            "web_results": [
                {"title": "Nemotron 3 Super", "url": "https://example.com/nemotron", "snippet": "model"}
            ],
        }
    )

    assert event["type"] == "tool_result"
    assert event["tool"] == "search"
    assert event["action"] == "search"
    assert event["ok"] is True
    assert event["item_count"] == 1
    assert event["items"][0]["title"] == "Nemotron 3 Super"
    assert event["items"][0]["url"] == "https://example.com/nemotron"
    assert event["metadata"]["overall_status"] == "ok"
    assert event["metadata"]["provider"] == "web_assist"
    assert event["metadata"]["raw_event_type"] == "web_search"


def test_search_results_are_normalized_to_search_items():
    event = normalize_lumen_runtime_event(
        {"type": "search_result", "search_results": [{"name": "Result A", "link": "https://example.com/a"}]}
    )

    assert event["item_count"] == len(event["items"]) == 1
    assert event["items"][0]["title"] == "Result A"
    assert event["items"][0]["url"] == "https://example.com/a"
    assert event["metadata"]["overall_status"] == "ok"


def test_citations_are_normalized_to_search_items():
    event = normalize_lumen_runtime_event(
        {"type": "tool_result", "tool": "search", "citations": [{"source": "Docs", "summary": "Citation text"}]}
    )

    assert event["item_count"] == len(event["items"]) == 1
    assert event["items"][0]["source"] == "Docs"
    assert event["items"][0]["snippet"] == "Citation text"
    assert event["metadata"]["overall_status"] == "ok"


def test_zero_search_items_mark_event_failed_and_empty():
    event = normalize_lumen_runtime_event({"type": "web_context", "context_sources": []})

    assert event["type"] == "tool_result"
    assert event["tool"] == "search"
    assert event["ok"] is False
    assert event["item_count"] == 0
    assert event["items"] == []
    assert event["metadata"]["overall_status"] == "failed"
    assert event["metadata"]["empty"] is True
