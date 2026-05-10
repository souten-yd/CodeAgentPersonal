from app.lumen.tools import LumenToolResult, compress_lumen_tool_results_for_llm


def test_news_zero_count_context_forbids_invented_answers():
    context = compress_lumen_tool_results_for_llm(
        [
            LumenToolResult(
                tool="news",
                ok=True,
                content="item_count=0",
                metadata={"overall_status": "ok", "item_count": 0},
            )
        ]
    )

    assert "[news:error]" in context
    assert "News tool returned item_count=0." in context
    assert "Do not invent headlines, facts, or summaries." in context
    assert "Tell the user that no valid news articles were retrieved." in context
    assert "Do not answer from memory." in context


def test_news_success_context_requires_japanese_bullets_and_provided_context_only():
    context = compress_lumen_tool_results_for_llm(
        [
            LumenToolResult(
                tool="news",
                ok=True,
                content="1. 見出しA",
                metadata={"overall_status": "ok", "item_count": 1},
            )
        ]
    )

    assert "[news:ok]" in context
    assert "Do not answer in JSON." in context
    assert "Answer in natural Japanese prose." in context
    assert "Use concise bullet points." in context
    assert "Use only the provided news context." in context
