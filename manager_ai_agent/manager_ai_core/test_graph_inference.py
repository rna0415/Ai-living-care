"""ROS2·DB·LLM 없이 실행되는 Manager graph-inference 회귀 테스트."""

import unittest

from manager_ai_agent.manager_ai_core.graph_inference import infer_from_contexts
from manager_ai_agent.manager_ai_core.kg_mapping.axis_routing import route_axes
from manager_ai_agent.manager_ai_core.policy_generation.rule_evaluator import evaluate


WELLBEING = "onto:saref/WellBeing"
SAFETY = "onto:saref/Safety"
COMFORT = "onto:saref/Comfort"


class AxisRoutingTests(unittest.TestCase):
    def test_korean_queries_route_to_expected_axis(self):
        cases = {
            "할머니 괜찮은지 확인해줘": WELLBEING,
            "가스레인지 안 껐는지 확인해줘": SAFETY,
            "방 온도 너무 낮은 거 아니야?": COMFORT,
        }

        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(route_axes(query)["active_axis_ids"], [expected])

    def test_out_of_scope_query_activates_no_axis(self):
        self.assertEqual(route_axes("파스타 맛있게 만드는 법 알려줘")["active_axis_ids"], [])

    def test_multi_axis_query_keeps_every_matching_axis(self):
        self.assertEqual(
            route_axes("할머니 안전 상태를 확인해줘")["active_axis_ids"],
            [WELLBEING, SAFETY],
        )

    def test_injected_scorer_is_used_without_model_dependency(self):
        result = route_axes(
            "arbitrary",
            scorer=lambda _text: {WELLBEING: 0.2, SAFETY: 0.8, COMFORT: 0.1},
            threshold=0.7,
        )

        self.assertEqual(result["active_axis_ids"], [SAFETY])
        self.assertEqual(result["mode"], "injected")

    def test_invalid_routing_threshold_is_rejected(self):
        for threshold in (0, -0.1, 1.1, float("nan"), True):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                route_axes("파스타 레시피", threshold=threshold)

        for invalid_score in (float("nan"), float("inf"), True, 10**10000):
            with self.subTest(invalid_score=invalid_score), self.assertRaises(ValueError):
                route_axes(
                    "arbitrary",
                    scorer=lambda _text, score=invalid_score: {SAFETY: score},
                )


class RuleEvaluatorTests(unittest.TestCase):
    def test_daytime_threshold_rule_escalates_deterministically(self):
        rules = [
            {
                "rule_id": "wb-no-motion-day",
                "slot": "motion",
                "time_context": "day",
                "threshold_hours": 4,
                "severity": "concern",
                "rationale": "주간 4시간 무동작",
            }
        ]

        result = evaluate(rules, {"motion": 5.0}, hour=10)

        self.assertTrue(result["should_escalate"])
        self.assertEqual(result["triggered_rules"][0]["rule_id"], "wb-no-motion-day")
        self.assertEqual(result["indeterminate_rules"], [])

    def test_missing_observation_is_indeterminate_not_normal(self):
        rules = [
            {
                "rule_id": "temperature-low",
                "slot": "temperature",
                "threshold_celsius": 18,
                "direction": "below",
                "severity": "concern",
            }
        ]

        result = evaluate(rules, {}, hour=10)

        self.assertFalse(result["should_escalate"])
        self.assertEqual(result["evaluation_status"], "indeterminate")
        self.assertEqual(result["triggered_rules"], [])
        self.assertEqual(result["indeterminate_rules"][0]["rule_id"], "temperature-low")

    def test_unknown_rule_shape_is_reported(self):
        result = evaluate(
            [{"rule_id": "future-rule", "severity": "concern", "custom": 1}],
            {},
            hour=10,
        )

        self.assertEqual(result["unsupported_rules"][0]["rule_id"], "future-rule")
        self.assertEqual(result["evaluation_status"], "indeterminate")

    def test_invalid_hour_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([], {}, hour=24)

    def test_empty_rule_set_is_indeterminate(self):
        result = evaluate([], {}, hour=10)

        self.assertEqual(result["evaluation_status"], "indeterminate")
        self.assertFalse(result["should_escalate"])
        self.assertIn("no rules", result["indeterminate_rules"][0]["reason"])

    def test_invalid_time_context_is_reported(self):
        result = evaluate(
            [
                {
                    "rule_id": "invalid-time",
                    "slot": "motion",
                    "time_context": "dawn",
                    "threshold_hours": 4,
                    "severity": "concern",
                }
            ],
            {"motion": 10},
            hour=10,
        )

        self.assertEqual(result["evaluation_status"], "indeterminate")
        self.assertEqual(result["unsupported_rules"][0]["rule_id"], "invalid-time")

    def test_invalid_escalation_policy_is_rejected(self):
        for invalid in (0, -1, 1.5, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evaluate(
                    [],
                    {},
                    hour=10,
                    policy={
                        "min_concern_rules_triggered": invalid,
                        "min_mild_concern_rules_triggered": 2,
                    },
                )

    def test_non_numeric_observation_is_indeterminate(self):
        rules = [
            {
                "rule_id": "motion-threshold",
                "slot": "motion",
                "threshold_hours": 4,
                "severity": "concern",
            }
        ]

        for value in ("10", float("nan"), float("inf"), True, 10**10000):
            with self.subTest(value=value):
                result = evaluate(rules, {"motion": value}, hour=10)
                self.assertEqual(result["evaluation_status"], "indeterminate")
                self.assertEqual(
                    result["indeterminate_rules"][0]["rule_id"],
                    "motion-threshold",
                )

    def test_malformed_rule_metadata_is_reported_before_matching(self):
        malformed = (
            {
                "slot": "motion",
                "threshold_hours": 4,
                "severity": "concern",
            },
            {
                "rule_id": "bad-severity",
                "slot": "motion",
                "threshold_hours": 4,
                "severity": "critical",
            },
            {
                "rule_id": "ambiguous",
                "slot": "motion",
                "condition": "door_open",
                "threshold_hours": 4,
                "severity": "concern",
            },
        )

        for rule in malformed:
            with self.subTest(rule=rule):
                result = evaluate([rule], {"motion": 1, "door_open": False}, hour=10)
                self.assertEqual(result["evaluation_status"], "indeterminate")
                self.assertEqual(len(result["unsupported_rules"]), 1)

        duplicate = {
            "rule_id": "duplicate",
            "slot": "motion",
            "threshold_hours": 4,
            "severity": "concern",
        }
        result = evaluate([duplicate, duplicate], {"motion": 1}, hour=10)
        self.assertEqual(result["evaluation_status"], "indeterminate")
        self.assertIn("duplicate", result["unsupported_rules"][0]["reason"])


class GraphInferenceTests(unittest.TestCase):
    def test_pipeline_routes_and_evaluates_pre_resolved_context(self):
        contexts = {
            WELLBEING: {
                "axis_id": WELLBEING,
                "label": "WellBeing",
                "source": "if01:test-double",
                "rules": [
                    {
                        "rule_id": "wb-no-motion-day",
                        "slot": "motion",
                        "time_context": "day",
                        "threshold_hours": 4,
                        "severity": "concern",
                        "rationale": "주간 4시간 무동작",
                    }
                ],
            }
        }

        result = infer_from_contexts(
            "할머니 괜찮은지 확인해줘",
            hour=10,
            contexts_by_axis=contexts,
            observations_by_axis={WELLBEING: {"motion": 5.0}},
        )

        self.assertEqual(result["routing"]["active_axis_ids"], [WELLBEING])
        self.assertEqual(result["missing_context_axis_ids"], [])
        self.assertEqual(result["context_issues"], [])
        self.assertEqual(result["inference_status"], "escalate")
        self.assertTrue(result["complete"])
        self.assertTrue(result["results"][0]["evaluation"]["should_escalate"])
        self.assertEqual(result["results"][0]["context_source"], "if01:test-double")

    def test_pipeline_does_not_invent_missing_context_or_observation(self):
        no_context = infer_from_contexts(
            "할머니 괜찮은지 확인해줘",
            hour=10,
            contexts_by_axis={},
            observations_by_axis={},
        )
        self.assertEqual(no_context["missing_context_axis_ids"], [WELLBEING])
        self.assertEqual(no_context["results"], [])
        self.assertEqual(no_context["inference_status"], "indeterminate")
        self.assertFalse(no_context["complete"])

        context_without_observation = infer_from_contexts(
            "할머니 괜찮은지 확인해줘",
            hour=10,
            contexts_by_axis={
                WELLBEING: {
                    "axis_id": WELLBEING,
                    "label": "WellBeing",
                    "rules": [
                        {
                            "rule_id": "wb-no-motion-day",
                            "slot": "motion",
                            "threshold_hours": 4,
                            "severity": "concern",
                        }
                    ],
                }
            },
            observations_by_axis={},
        )
        evaluation = context_without_observation["results"][0]["evaluation"]
        self.assertFalse(evaluation["should_escalate"])
        self.assertEqual(evaluation["evaluation_status"], "indeterminate")
        self.assertEqual(evaluation["indeterminate_rules"][0]["rule_id"], "wb-no-motion-day")
        self.assertEqual(context_without_observation["inference_status"], "indeterminate")
        self.assertFalse(context_without_observation["complete"])

    def test_missing_context_source_preserves_escalation_but_marks_incomplete(self):
        result = infer_from_contexts(
            "할머니 괜찮은지 확인해줘",
            hour=10,
            contexts_by_axis={
                WELLBEING: {
                    "axis_id": WELLBEING,
                    "rules": [
                        {
                            "rule_id": "wb-no-motion-day",
                            "slot": "motion",
                            "threshold_hours": 4,
                            "severity": "concern",
                        }
                    ],
                }
            },
            observations_by_axis={WELLBEING: {"motion": 10}},
        )

        self.assertEqual(result["inference_status"], "escalate")
        self.assertFalse(result["complete"])
        self.assertEqual(result["context_issues"][0]["axis_id"], WELLBEING)


if __name__ == "__main__":
    unittest.main()
