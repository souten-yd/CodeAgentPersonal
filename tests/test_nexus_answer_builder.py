import os
import json
import tempfile
import unittest
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

from app.nexus.answer_builder import _probe_llm_endpoint_detail, build_answer_payload
from app.nexus.config import NexusPaths


class NexusAnswerBuilderTests(unittest.TestCase):
    def test_search_model_from_orchestrator_is_preferred(self) -> None:
        references = [{"citation_label": "s1", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "s1"}]
        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._load_search_role_assignment",
            return_value={"role": "SEARCH", "model": "search-role-model", "enabled": True, "endpoint": ""},
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={"endpoint": "http://127.0.0.1:8080/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value="ok [S1]",
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=references, evidence_chunks=chunks)
        self.assertEqual(payload["llm_model"], "search-role-model")
        self.assertEqual(payload["generation"]["model_role"], "SEARCH")
        self.assertEqual(payload["generation"]["model_source"], "model_orchestrator")
        self.assertEqual(payload["generation"]["selected_reason"], "search_role_model")

    def test_deep_research_model_env_takes_priority_over_search_role(self) -> None:
        with patch.dict(os.environ, {"DEEP_RESEARCH_LLM_MODEL": "deep-model"}, clear=True), patch(
            "app.nexus.answer_builder._load_search_role_assignment",
            return_value={"role": "SEARCH", "model": "search-role-model", "enabled": True, "endpoint": ""},
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={"endpoint": "http://127.0.0.1:8080/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=[], evidence_chunks=[])
        self.assertEqual(payload["llm_model"], "deep-model")

    def test_search_model_empty_falls_back_to_models_api(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "app.nexus.answer_builder._load_search_role_assignment",
            return_value={"role": "SEARCH", "model": "", "enabled": True, "error": "search_role_model_missing"},
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={"endpoint": "http://127.0.0.1:8080/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
        ), patch(
            "app.nexus.answer_builder._discover_model_from_models_api",
            return_value="remote-model-1",
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=[], evidence_chunks=[])
        self.assertEqual(payload["llm_model"], "remote-model-1")
        self.assertIn("fallback_to_models_api", payload["selected_reason"])

    def test_search_endpoint_is_in_endpoint_candidates(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "app.nexus.answer_builder._load_search_role_assignment",
            return_value={"role": "SEARCH", "model": "search-role-model", "enabled": True, "endpoint": "http://127.0.0.1:19090/v1"},
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            side_effect=[
                {"endpoint": "http://127.0.0.1:19090/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
            ],
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=[], evidence_chunks=[])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:19090/v1/chat/completions")

    def test_http_400_error_body_is_in_llm_error(self) -> None:
        references = [{"citation_label": "s1", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "s1"}]
        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={"endpoint": "http://127.0.0.1:8080/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=RuntimeError("answer llm http_error: status=400 body={\"error\":\"bad request\"}"),
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=references, evidence_chunks=chunks)
        self.assertIn("status=400", payload["llm_error"])
        self.assertIn("body=", payload["llm_error"])
        self.assertIn("request failed", payload["generation"]["notice"])

    def test_generate_answer_payload_contains_max_tokens_and_stream_false(self) -> None:
        from app.nexus import answer_builder as target

        captured: dict = {}

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "ok [S1]"}}]}).encode("utf-8")

        def _fake_urlopen(req, timeout=0):  # noqa: ANN001, ARG001
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _Resp()

        with patch.dict(os.environ, {"NEXUS_ANSWER_LLM_MAX_TOKENS": "1024"}, clear=True), patch(
            "app.nexus.answer_builder.request.urlopen",
            side_effect=_fake_urlopen,
        ):
            text = target._generate_answer_with_llm(
                question="質問",
                references=[{"citation_label": "[S1]", "title": "src"}],
                evidence_chunks=[{"citation_label": "[S1]", "source_id": "src", "quote": "fact"}],
                llm_settings={"enabled": True, "endpoint": "http://127.0.0.1:8080/v1/chat/completions", "model": "m"},
            )
        self.assertEqual(text, "ok [S1]")
        self.assertEqual(captured["payload"]["max_tokens"], 1024)
        self.assertFalse(captured["payload"]["stream"])

    def test_resolve_settings_selects_8080_when_8000_probe_fails(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]

        def _fake_probe(endpoint: str, timeout_sec: float = 1.5) -> dict:
            if "8000" in endpoint:
                return {"endpoint": endpoint, "reachable": False, "checks": [], "error": "connection refused"}
            if "8080" in endpoint:
                return {"endpoint": endpoint, "reachable": True, "checks": [], "error": ""}
            return {"endpoint": endpoint, "reachable": False, "checks": [], "error": "unreachable"}

        with patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "http://127.0.0.1:8000/v1", "CODEAGENT_LLM_CHAT": "http://127.0.0.1:8080/v1/chat/completions"},
            clear=True,
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            side_effect=_fake_probe,
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value="shared endpoint works [S1]",
        ):
            payload = build_answer_payload(
                question="質問",
                summary="fallback summary legacy-label",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertTrue(payload["llm_enabled"])
        self.assertTrue(payload["llm_reachable"])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")

    def test_probe_llm_endpoint_detail_treats_404_as_failure(self) -> None:
        with patch(
            "app.nexus.answer_builder.request.urlopen",
            side_effect=HTTPError(
                url="http://127.0.0.1:8080/v1/models",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=None,
            ),
        ):
            detail = _probe_llm_endpoint_detail("http://127.0.0.1:8080/v1/chat/completions", timeout_sec=0.1)

        self.assertFalse(detail["reachable"])
        self.assertTrue(detail["checks"])
        self.assertIn(detail["checks"][0]["status"], [404])

    def test_build_answer_payload_uses_llm_with_evidence_chunks_and_preserves_s_label(self) -> None:
        references = [{"citation_label": "article#1", "title": "Source 1", "url": "https://example.com/1", "source_id": "src-1"}]
        chunks = [{"quote": "fact", "source_id": "src-1", "citation_label": "article#1"}]
        llm_text = "結論です article#1\n\n## 追加確認が必要な点\n- なし"

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value=llm_text,
        ) as mocked:
            payload = build_answer_payload(
                question="質問",
                summary="fallback summary",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertIn("[S1]", payload["answer"])
        self.assertNotIn("article#1", payload["answer"])
        self.assertIn(payload["answer"], payload["answer_markdown"])
        mocked.assert_called_once()
        self.assertEqual(payload["references"][0]["citation_label"], "[S1]")
        self.assertIn("- [S1] Source 1 (https://example.com/1)", payload["answer_markdown"])
        self.assertEqual(payload["generation_mode"], "llm_answer")
        self.assertTrue(payload["llm_enabled"])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(payload["llm_model"], "local-llm")
        self.assertIsNone(payload["llm_error"])
        self.assertEqual(payload["generation"]["mode"], "llm_answer")
        self.assertTrue(payload["generation"]["llm_enabled"])
        self.assertEqual(payload["generation"]["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(payload["generation"]["llm_model"], "local-llm")
        self.assertIsNone(payload["generation"]["error"])

    def test_build_answer_payload_falls_back_to_template_summary_when_llm_fails(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]
        fallback_summary = "fallback summary legacy-label"

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=TimeoutError("timeout"),
        ):
            payload = build_answer_payload(
                question="質問",
                summary=fallback_summary,
                references=references,
                evidence_chunks=chunks,
            )

        self.assertIn("fallback summary", payload["answer"])
        self.assertIn("[S1]", payload["answer"])
        self.assertNotIn("legacy-label", payload["answer"])
        self.assertIn("## References", payload["answer_markdown"])
        self.assertEqual(payload["generation_mode"], "template_fallback")
        self.assertTrue(payload["llm_enabled"])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(payload["llm_model"], "local-llm")
        self.assertEqual(payload["llm_error"], "timeout")
        self.assertEqual(payload["generation"]["mode"], "template_fallback")
        self.assertTrue(payload["generation"]["llm_enabled"])
        self.assertEqual(payload["generation"]["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(payload["generation"]["llm_model"], "local-llm")
        self.assertEqual(payload["generation"]["error"], "timeout")
        self.assertIn("template fallback answer", payload["generation"]["notice"])

    def test_build_answer_payload_explicit_enabled_true_with_unreachable_endpoint_keeps_probe_state(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]

        with patch.dict(
            os.environ,
            {
                "DEEP_RESEARCH_LLM_ENABLED": "true",
                "DEEP_RESEARCH_LLM_ENDPOINT": "http://127.0.0.1:9999/v1/chat/completions",
            },
            clear=True,
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={
                "endpoint": "http://127.0.0.1:9999/v1/chat/completions",
                "reachable": False,
                "checks": [{"url": "http://127.0.0.1:9999/v1/models", "status": 0, "ok": False, "error": "refused"}],
                "error": "connection refused",
            },
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=RuntimeError("answer llm unavailable: refused"),
        ):
            payload = build_answer_payload(
                question="質問",
                summary="fallback summary legacy-label",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertEqual(payload["generation_mode"], "template_fallback")
        self.assertTrue(payload["llm_enabled"])
        self.assertFalse(payload["llm_reachable"])
        self.assertEqual(payload["probe_error"], "all endpoint probes failed")
        self.assertIn("unavailable", payload["llm_error"])

    def test_build_answer_payload_resolves_llm_endpoint_from_shared_chat_setting(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]

        with patch.dict(
            os.environ,
            {"CODEAGENT_LLM_CHAT": "http://127.0.0.1:18080/v1/chat/completions"},
            clear=True,
        ), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={
                "endpoint": "http://127.0.0.1:18080/v1/chat/completions",
                "reachable": True,
                "checks": [],
                "error": "",
            },
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value="shared endpoint works [S1]",
        ):
            payload = build_answer_payload(
                question="質問",
                summary="fallback summary legacy-label",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertTrue(payload["llm_enabled"])
        self.assertEqual(payload["llm_endpoint"], "http://127.0.0.1:18080/v1/chat/completions")
        self.assertEqual(payload["generation_mode"], "llm_answer")

    def test_build_answer_payload_persists_llm_metadata_in_answer_json(self) -> None:
        references = [{"citation_label": "legacy-label", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "legacy-label"}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            ca_data_dir = Path(tmp_dir) / "ca_data"
            nexus_dir = ca_data_dir / "nexus"
            paths = NexusPaths(
                ca_data_dir=ca_data_dir,
                nexus_dir=nexus_dir,
                db_path=nexus_dir / "nexus.db",
                uploads_dir=nexus_dir / "uploads",
                extracted_dir=nexus_dir / "extracted",
                reports_dir=nexus_dir / "reports",
                exports_dir=nexus_dir / "exports",
            )
            with patch(
                "app.nexus.answer_builder.NEXUS_PATHS",
                paths,
            ), patch(
                "app.nexus.answer_builder._save_answer_row",
                return_value="answer-id-123",
            ), patch.dict(
                os.environ,
                {"NEXUS_ENABLE_ANSWER_LLM": "true"},
                clear=True,
            ), patch(
                "app.nexus.answer_builder._generate_answer_with_llm",
                side_effect=RuntimeError("llm unavailable"),
            ):
                payload = build_answer_payload(
                    question="質問",
                    summary="fallback summary legacy-label",
                    references=references,
                    evidence_chunks=chunks,
                    job_id="job_1",
                )

            answer_json_path = Path(payload["answer_json_path"])
            self.assertTrue(answer_json_path.exists())
            saved_payload = json.loads(answer_json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["generation_mode"], "template_fallback")
            self.assertTrue(saved_payload["llm_enabled"])
            self.assertEqual(saved_payload["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")
            self.assertEqual(saved_payload["llm_model"], "local-llm")
            self.assertEqual(saved_payload["llm_error"], "llm unavailable")
            self.assertEqual(saved_payload["generation"]["mode"], "template_fallback")
            self.assertTrue(saved_payload["generation"]["llm_enabled"])
            self.assertEqual(saved_payload["generation"]["llm_endpoint"], "http://127.0.0.1:8080/v1/chat/completions")
            self.assertEqual(saved_payload["generation"]["llm_model"], "local-llm")
            self.assertEqual(saved_payload["generation"]["error"], "llm unavailable")

    def test_build_answer_payload_keeps_references_consistent_between_json_and_markdown(self) -> None:
        references = [
            {"citation_label": "r1", "title": "Source 1", "url": "https://example.com/1", "source_id": "src-1"},
            {"citation_label": "r2", "title": "Source 2", "url": "https://example.com/2", "source_id": "src-2"},
        ]
        evidence = [
            {"citation_label": "r1", "source_id": "src-1", "quote": "q1"},
            {"citation_label": "r2", "source_id": "src-2", "quote": "q2"},
        ]
        chunks = [
            {"citation_label": "r1", "source_id": "src-1", "text": "q1"},
            {"citation_label": "r2", "source_id": "src-2", "text": "q2"},
        ]

        payload = build_answer_payload(
            question="質問",
            summary="summary r1 r2",
            references=references,
            evidence=evidence,
            evidence_chunks=chunks,
        )

        self.assertEqual([ref["citation_label"] for ref in payload["references"]], ["[S1]", "[S2]"])
        self.assertEqual([row["citation_label"] for row in payload["evidence_json"]], ["[S1]", "[S2]"])
        self.assertIn("- [S1] Source 1 (https://example.com/1)", payload["answer_markdown"])
        self.assertIn("- [S2] Source 2 (https://example.com/2)", payload["answer_markdown"])

    def test_build_answer_payload_normalizes_non_standard_labels(self) -> None:
        references = [{"citation_label": "article#1", "title": "Source 1", "source_id": "src-1"}]
        evidence = [{"citation_label": "article#1", "title": "Source 1", "source_id": "src-1"}]
        chunks = [{"text": "fact", "source_id": "src-1", "citation_label": "article#1"}]

        payload = build_answer_payload(
            question="質問",
            summary="article#1 の根拠です",
            references=references,
            evidence=evidence,
            evidence_chunks=chunks,
        )

        self.assertEqual(payload["references"][0]["citation_label"], "[S1]")
        self.assertEqual(payload["evidence_json"][0]["citation_label"], "[S1]")
        self.assertIn("[S1]", payload["answer_markdown"])
        self.assertNotIn("article#1", payload["answer_markdown"])

    def test_citation_verification_ok_when_all_labels_match(self) -> None:
        references = [{"citation_label": "src-a", "title": "Source A", "source_id": "src-a"}]

        payload = build_answer_payload(
            question="質問",
            summary="これは結論です src-a",
            references=references,
        )

        self.assertFalse(payload["citation_verification"]["ok"])
        self.assertEqual(payload["citation_verification"]["missing_in_references"], [])
        self.assertEqual(payload["citation_verification"]["unused_references"], [])
        self.assertEqual(payload["citation_verification"]["invalid_labels"], [])
        self.assertEqual(payload["citation_verification"]["warnings"][0]["reason"], "evidence_missing")

    def test_citation_verification_detects_unknown_label_in_answer(self) -> None:
        references = [{"citation_label": "src-a", "title": "Source A", "source_id": "src-a"}]

        payload = build_answer_payload(
            question="質問",
            summary="結論 [S1] [S9]",
            references=references,
        )

        self.assertFalse(payload["citation_verification"]["ok"])
        self.assertEqual(payload["citation_verification"]["missing_in_references"], ["[S9]"])
        self.assertEqual(payload["citation_verification"]["unused_references"], [])

    def test_citation_verification_sentence_status_regression(self) -> None:
        references = [
            {"citation_label": "r1", "title": "Source 1", "source_id": "src-1"},
            {"citation_label": "r2", "title": "Source 2", "source_id": "src-2"},
            {"citation_label": "r3", "title": "Source 3", "source_id": "src-3"},
        ]
        chunks = [
            {"citation_label": "r1", "source_id": "src-1", "chunk_id": "c1", "quote": "東京の人口は約1400万人です。"},
            {"citation_label": "r2", "source_id": "src-2", "chunk_id": "c2", "quote": "電気自動車の販売は前年比で増加した。"},
            {"citation_label": "r3", "source_id": "src-3", "chunk_id": "c3", "quote": "全く関係のない証拠文です。"},
        ]

        payload = build_answer_payload(
            question="質問",
            summary=(
                "東京の人口は約1400万人です。[S1] "
                "電気自動車市場については増加傾向です。[S2] "
                "火星に海があると断定できます。[S3]"
            ),
            references=references,
            evidence_chunks=chunks,
        )

        sentence_results = payload["citation_verification"]["sentence_results"]
        self.assertEqual([row["status"] for row in sentence_results], ["supported", "weak", "unsupported"])
        self.assertEqual(payload["citation_verification"]["warnings"][0]["sentence_index"], 2)
        self.assertEqual(payload["citation_verification"]["warnings"][1]["sentence_index"], 3)
        self.assertEqual(payload["citation_verification"]["warnings"][1]["reason"], "low_semantic_overlap")

    def test_citation_verification_detects_unused_reference_label(self) -> None:
        references = [
            {"citation_label": "r1", "title": "Source 1", "source_id": "src-1"},
            {"citation_label": "r2", "title": "Source 2", "source_id": "src-2"},
        ]
        chunks = [
            {"text": "fact1", "source_id": "src-1", "citation_label": "r1"},
            {"text": "fact2", "source_id": "src-2", "citation_label": "r2"},
        ]

        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value="結論 [S1]",
        ):
            payload = build_answer_payload(
                question="質問",
                summary="fallback",
                references=references,
                evidence_chunks=chunks,
            )

        self.assertFalse(payload["citation_verification"]["ok"])
        self.assertEqual(payload["citation_verification"]["missing_in_references"], [])
        self.assertEqual(payload["citation_verification"]["unused_references"], ["[S2]"])
        self.assertEqual(payload["citation_verification"]["invalid_labels"], [])

    def test_payload_includes_compression_stats_when_many_chunks(self) -> None:
        references = [
            {"citation_label": f"r{i}", "title": f"Source {i}", "source_id": f"src-{i}", "source_type": "web"}
            for i in range(1, 6)
        ]
        chunks = [
            {
                "source_id": f"src-{(i % 5) + 1}",
                "chunk_id": f"c{i}",
                "citation_label": f"r{(i % 5) + 1}",
                "quote": "fact " * 400,
                "source_type": "web",
            }
            for i in range(60)
        ]
        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            return_value="ok [S1]",
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=references, evidence_chunks=chunks)
        compression = payload["generation"]["compression"]
        self.assertIn("chunks_input", compression)
        self.assertIn("chunks_used", compression)
        self.assertLessEqual(compression["chunks_used"], compression["chunks_input"])

    def test_context_overflow_retries_once_with_stronger_compression(self) -> None:
        references = [{"citation_label": "r1", "title": "Source 1", "source_id": "src-1", "source_type": "web"}]
        chunks = [{"quote": "fact " * 200, "source_id": "src-1", "chunk_id": f"c{i}", "citation_label": "r1"} for i in range(50)]
        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={"endpoint": "http://127.0.0.1:8080/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=[
                RuntimeError("answer llm http_error: status=400 body={\"error\":\"exceed_context_size_error n_prompt_tokens=11111 n_ctx=8192\"}"),
                "retry ok [S1]",
            ],
        ) as mocked:
            payload = build_answer_payload(question="質問", summary="fallback", references=references, evidence_chunks=chunks)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(payload["generation"]["retry_count"], 1)
        self.assertEqual(payload["generation"]["mode"], "llm_answer")

    def test_context_overflow_retry_failure_sets_notice(self) -> None:
        references = [{"citation_label": "r1", "title": "Source 1", "source_id": "src-1", "source_type": "web"}]
        chunks = [{"quote": "fact " * 200, "source_id": "src-1", "chunk_id": "c1", "citation_label": "r1"}]
        with patch.dict(os.environ, {"NEXUS_ENABLE_ANSWER_LLM": "true"}, clear=True), patch(
            "app.nexus.answer_builder._probe_llm_endpoint_detail",
            return_value={"endpoint": "http://127.0.0.1:8080/v1/chat/completions", "reachable": True, "checks": [], "error": ""},
        ), patch(
            "app.nexus.answer_builder._generate_answer_with_llm",
            side_effect=[
                RuntimeError("answer llm http_error: status=400 body={\"error\":\"exceed_context_size_error n_prompt_tokens=11111 n_ctx=8192\"}"),
                RuntimeError("answer llm http_error: status=400 body={\"error\":\"exceed_context_size_error n_prompt_tokens=9999 n_ctx=8192\"}"),
            ],
        ):
            payload = build_answer_payload(question="質問", summary="fallback", references=references, evidence_chunks=chunks)
        self.assertEqual(payload["generation"]["mode"], "template_fallback")
        self.assertIn("exceeded context size", payload["generation"]["notice"])


if __name__ == "__main__":
    unittest.main()
