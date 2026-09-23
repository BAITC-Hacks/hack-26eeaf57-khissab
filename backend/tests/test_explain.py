import asyncio
import copy
import json
import os
import time
import unittest
from unittest.mock import patch

import httpx

from backend.engine import RecommendationEngine
from backend.explain import LLMSettings, explain, explain_recommendations, slim_factors
from backend.loader import ROOT, read_dataset
from backend.tests.test_engine import SYSTEM, dataset, event, record


def tool_response(body, phrasing="supportive"):
    fact_ids = body["tools"][0]["function"]["parameters"]["properties"]["clauses"]["items"]["properties"]["fact_id"]["enum"]
    return {"choices": [{"message": {"content": None, "tool_calls": [{
        "type": "function", "id": "test_call",
        "function": {"name": "submit_explanation", "arguments": json.dumps({
            "clauses": [{"fact_id": fact_id, "phrasing": phrasing} for fact_id in fact_ids]
        })},
    }]}}]}


class ExplainTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        data = dataset([
            event("START", develops_skills=[{"skill_id": SYSTEM, "gain": 1, "max_level": 3}]),
            event("ADVANCED", prerequisites={SYSTEM: 3}),
            event("OTHER_TYPE", type="workshop", develops_skills=[]),
        ], [record("SKIP", "OTHER_TYPE", "declined")])
        self.recommendation = RecommendationEngine(data).recommend("TEST_EMPLOYEE")[0]
        self.settings = LLMSettings(model="test-model", base_url="http://127.0.0.1:11434/v1", api_key="test-key")

    def test_slim_factors_only_include_the_relevant_type_and_do_not_mutate_debug_factors(self):
        before = copy.deepcopy(self.recommendation)
        slim = slim_factors(self.recommendation)
        self.assertEqual(slim["engagement"]["type"], "course")
        self.assertNotIn("engagement_by_type", slim)
        self.assertNotIn("workshop", json.dumps(slim))
        self.assertNotIn("records", slim["engagement"])
        self.assertEqual(slim["gateway_to"][0]["event_id"], "ADVANCED")
        slim["gaps"][0]["current"] = 999
        slim["gateway_to"].clear()
        self.assertEqual(self.recommendation, before)

    async def test_no_key_fallback_is_offline_and_contains_grade_gap_history_and_gateway(self):
        def forbidden(request):
            self.fail("No-key fallback attempted a model request")
        result = await explain(self.recommendation, LLMSettings(), transport=httpx.MockTransport(forbidden))
        self.assertEqual(result["source"], "template")
        self.assertEqual(result["fallback_reason"], "no_api_key")
        self.assertIn("Senior", result["text"])
        self.assertIn("2 against 4 required", result["text"])
        self.assertIn("critical", result["text"])
        self.assertIn("course history", result["text"])
        self.assertIn("would unlock ADVANCED", result["text"])
        self.assertIn("2 to 3 against prerequisite 3", result["text"])

    async def test_tool_call_path_validates_and_renders_the_model_phrasing_plan(self):
        before = copy.deepcopy(self.recommendation)
        requests = []

        def model(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(json.loads(body["messages"][1]["content"]), slim_factors(self.recommendation))
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(body["model"], "test-model")
            self.assertTrue(body["tools"][0]["function"]["strict"])
            self.assertEqual(body["tool_choice"]["function"]["name"], "submit_explanation")
            self.assertFalse(body["parallel_tool_calls"])
            return httpx.Response(200, json=tool_response(body))

        result = await explain(self.recommendation, self.settings, transport=httpx.MockTransport(model))
        self.assertEqual(len(requests), 1)
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["model"], "test-model")
        self.assertIsNone(result["fallback_reason"])
        self.assertIn("current 2, required 4", result["text"])
        self.assertIn("opens a path to ADVANCED", result["text"])
        self.assertEqual(set(result["validated_fact_ids"]), {"grade", f"skill:{SYSTEM}", "engagement", "score", "gateway:ADVANCED"})
        self.assertEqual(self.recommendation, before)

    async def test_invented_numbers_missing_evidence_and_wrong_tool_fall_back(self):
        for fault in ("extra_number", "missing", "duplicate", "unknown_fact", "free_text", "wrong_tool", "bad_json", "refusal"):
            with self.subTest(fault=fault):
                def bad_model(request):
                    response = tool_response(json.loads(request.content))
                    message = response["choices"][0]["message"]
                    function = message["tool_calls"][0]["function"]
                    plan = json.loads(function["arguments"])
                    if fault == "extra_number":
                        plan["clauses"][0]["score"] = 999
                    elif fault == "missing":
                        plan["clauses"] = plan["clauses"][:-1]
                    elif fault == "duplicate":
                        plan["clauses"].append(plan["clauses"][0])
                    elif fault == "unknown_fact":
                        plan["clauses"][0]["fact_id"] = "salary:999"
                    elif fault == "free_text":
                        message["content"] = "Your score is 999 and promotion is guaranteed."
                    elif fault == "wrong_tool":
                        function["name"] = "select_event"
                    elif fault == "refusal":
                        message["refusal"] = "Refused"
                    function["arguments"] = "{" if fault == "bad_json" else json.dumps(plan)
                    return httpx.Response(200, json=response)

                result = await explain(self.recommendation, self.settings, transport=httpx.MockTransport(bad_model))
                self.assertEqual(result["source"], "template")
                self.assertEqual(result["fallback_reason"], "invalid_model_response")
                self.assertNotIn("999", result["text"])

    async def test_provider_errors_and_redirects_fall_back_without_exposing_secrets(self):
        for status in (401, 429, 500, 302):
            with self.subTest(status=status):
                requests = []

                def failing(request):
                    requests.append(request)
                    return httpx.Response(status, text="test-key", headers={"Location": "https://example.com"})

                result = await explain(self.recommendation, self.settings, transport=httpx.MockTransport(failing))
                self.assertEqual(result["fallback_reason"], "provider_error")
                self.assertEqual(len(requests), 1)
                self.assertNotIn("test-key", json.dumps(result))
        self.assertNotIn("test-key", repr(self.settings))

    async def test_connection_failure_and_oversized_response_fall_back(self):
        def disconnected(request):
            raise httpx.ConnectError("Unavailable", request=request)
        result = await explain(self.recommendation, self.settings, transport=httpx.MockTransport(disconnected))
        self.assertEqual(result["fallback_reason"], "provider_error")
        oversized = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 65537))
        result = await explain(self.recommendation, self.settings, transport=oversized)
        self.assertEqual(result["fallback_reason"], "invalid_model_response")

    async def test_batch_deadline_is_bounded_and_cancels_pending_requests(self):
        started, cancelled = [], []

        async def slow(request):
            started.append(request)
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled.append(request)
                raise

        settings = LLMSettings(model="test", base_url=self.settings.base_url, api_key="test", timeout_seconds=0.03)
        start = time.monotonic()
        results = await explain_recommendations([self.recommendation] * 3, settings, transport=httpx.MockTransport(slow))
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(len(started), 3)
        self.assertEqual(len(cancelled), 3)
        self.assertTrue(all(row["explanation"]["fallback_reason"] == "timeout" for row in results))

    async def test_missing_configuration_and_nonlocal_endpoint_never_make_requests(self):
        def forbidden(request):
            self.fail("Invalid configuration attempted a request")
        for url, reason in (("", "missing_configuration"), ("https://api.openai.com/v1", "nonlocal_endpoint")):
            with self.subTest(url=url):
                settings = LLMSettings(base_url=url, api_key="test")
                result = await explain(self.recommendation, settings, transport=httpx.MockTransport(forbidden))
                self.assertEqual(result["fallback_reason"], reason)

    async def test_gateway_with_unmet_remaining_prerequisite_never_says_unlocked(self):
        recommendation = copy.deepcopy(self.recommendation)
        gateway = recommendation["factors"]["gateway_to"][0]
        gateway["unlocked_after_completion"] = False
        gateway["blocking_prerequisites"][0].update(required=4, met_after_completion=False)
        result = await explain(recommendation, LLMSettings())
        self.assertIn("prerequisites would remain unmet", result["text"])
        self.assertNotIn("would unlock", result["text"])

    def test_environment_settings_have_a_capped_timeout(self):
        with patch.dict(os.environ, {"LLM_MODEL": "local-model", "LLM_BASE_URL": "http://localhost:11434/v1",
                                     "LLM_API_KEY": "local", "LLM_TIMEOUT_SECONDS": "100"}, clear=True):
            settings = LLMSettings.from_env()
            self.assertEqual(settings.model, "local-model")
            self.assertEqual(settings.timeout_seconds, 8)
        with patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "invalid"}, clear=True):
            self.assertEqual(LLMSettings.from_env().timeout_seconds, 8)

    @unittest.skipUnless((ROOT / "data" / "employees.json").is_file(), "Starter kit is not installed in data/")
    async def test_real_e0002_gateway_and_rationale_are_grounded(self):
        recommendations = RecommendationEngine(read_dataset(ROOT / "data")).recommend("E0002")
        first = recommendations[0]
        self.assertAlmostEqual(first["factors"]["engagement_multiplier"], 0.468)
        self.assertEqual(first["factors"]["engagement_by_type"]["course"]["self_factor"], 1.3)
        self.assertEqual([g["event_id"] for g in first["factors"]["gateway_to"]], ["EV_006", "EV_007"])
        for gateway in first["factors"]["gateway_to"]:
            blocker = gateway["blocking_prerequisites"][0]
            self.assertEqual((blocker["current"], blocker["required"], blocker["after_completion"]), (1, 2, 2))
        result = await explain(first, LLMSettings())
        self.assertIn("1 against 4 required", result["text"])
        self.assertIn("capped self-factor 1.3", result["text"])
        self.assertIn("engagement multiplier 0.468", result["text"])
        self.assertIn("score 2.808", result["text"])
        self.assertIn("1 to 2 against prerequisite 2", result["text"])


if __name__ == "__main__":
    unittest.main()
