import unittest
from unittest.mock import patch

import main


class ChatTaskWebInjectionTests(unittest.TestCase):
    def test_task_prefetch_context_contains_items_and_provider_errors(self) -> None:
        search_result = {
            "query": "ai chips",
            "items": [
                {
                    "title": "AI Chips Market Update",
                    "snippet": "Latest market update for AI chips.",
                    "url": "https://example.com/ai-chips",
                }
            ],
            "provider_errors": {"searxng": ["timeout", "retry exhausted"]},
        }
        context = main._build_task_prefetch_context_block(search_result, max_items=5)
        self.assertIn("【事前Web検索結果】query=ai chips", context)
        self.assertIn("provider_errors: searxng: timeout, retry exhausted", context)
        self.assertIn("AI Chips Market Update", context)

    def test_chat_search_context_contains_items_and_provider_errors(self) -> None:
        fake_search_output = {
            "provider": "searxng",
            "selected_provider": "searxng",
            "attempted_providers": ["searxng"],
            "fallback_used": False,
            "skipped_providers": {},
            "provider_errors": {"searxng": ["temporary upstream error"]},
            "configured": True,
            "non_fatal": False,
            "message": "ok",
            "items": [
                {
                    "provider": "searxng",
                    "query": "ai regulation",
                    "rank": 1,
                    "title": "AI Regulation Update",
                    "url": "https://example.com/regulation",
                    "snippet": "Regulatory changes summary",
                }
            ],
            "total_items": 1,
        }
        with patch.object(main, "_search_enabled", True):
            with patch.object(main, "plan_web_queries", return_value=["ai regulation"]):
                with patch.object(main, "run_web_search", return_value=fake_search_output):
                    context = main._run_nexus_search_for_context(
                        "ai regulation",
                        num_results=3,
                        mode="quick",
                        depth="quick",
                        max_queries=1,
                    )["context_text"]

        self.assertIn("meta: selected_provider=searxng", context)
        self.assertIn("provider_errors: searxng: temporary upstream error", context)
        self.assertIn("AI Regulation Update", context)


if __name__ == "__main__":
    unittest.main()
