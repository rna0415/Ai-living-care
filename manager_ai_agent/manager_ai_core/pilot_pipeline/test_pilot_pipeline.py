"""파일럿 파이프라인 회귀 — ROS2·DB·LLM 없이 표준 라이브러리 unittest 로 돈다.

실행: python3 -m unittest manager_ai_agent.manager_ai_core.pilot_pipeline.test_pilot_pipeline
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from manager_ai_agent.manager_ai_core.pilot_pipeline import assign, generation, pipeline, retrieval, validator
from manager_ai_agent.manager_ai_core.pilot_pipeline.graph_stub import StubGraph

ROOT = Path(__file__).resolve().parents[3]
VOCAB = json.loads((ROOT / "docs/pilot-spec/vocab.json").read_text(encoding="utf-8"))
LAMP = json.loads((ROOT / "docs/pilot-spec/templates/example-lamp.td.json").read_text(encoding="utf-8"))

PLACES = {"places": [
    {"id": "room_a", "aliases": ["A실", "에이실"], "pose": None},
    {"id": "room_b", "aliases": ["B실", "비실"], "pose": None},
]}


def lamp(title, room, label):
    td = copy.deepcopy(LAMP)
    td["title"], td["location"] = title, room
    td["aliases"] = [f"{label} 조명", f"{label} 불"]
    return td


ROBOT = {
    "title": "robot-1", "@type": "id:mobile-robot", "description": "이동 로봇", "location": "room_a",
    "aliases": ["로봇"],
    "properties": {},
    "actions": {
        "navigateTo": {"@type": "id:navigate-to", "description": "목적지 장소로 이동한다.",
                       "aliases": ["가다", "이동하다"],
                       "input": {"type": "object", "required": ["destination"],
                                 "properties": {"destination": {"type": "string"}}}},
        "detectObjects": {"@type": "id:detect-objects", "description": "물체를 검출한다.",
                          "aliases": ["확인하다", "찾다", "보다"]},
    },
    "events": {},
}


def make_graph():
    return StubGraph([lamp("lamp-a", "room_a", "A실"), lamp("lamp-b", "room_b", "B실"), ROBOT],
                     PLACES, VOCAB)


def rule(**action):
    return {"name": "t", "event": {"request-event": ["user-request"]}, "action": action}


class GraphStubTest(unittest.TestCase):
    def setUp(self):
        self.g = make_graph()

    def test_slot_and_providers(self):
        self.assertEqual(self.g.slot_of("turn-on"), "control-action")
        self.assertEqual(self.g.slot_of("detect-objects"), "perception-action")
        self.assertIsNone(self.g.slot_of("person"))
        self.assertEqual(sorted(self.g.devices_with("turn-on")), ["lamp-a", "lamp-b"])
        self.assertEqual(self.g.devices_with("navigate-to"), ["robot-1"])

    def test_place_aliases_and_ancestors(self):
        self.assertEqual(self.g.resolve_place("A실"), "room_a")
        self.assertIsNone(self.g.resolve_place("주방"))
        self.assertEqual(self.g.ancestors("turn-on"), ["ControlAction", "Action"])

    def test_unknown_type_is_an_error(self):
        bad = copy.deepcopy(ROBOT)
        bad["actions"]["x"] = {"@type": "id:fly-to", "description": "x"}
        with self.assertRaises(ValueError):
            StubGraph([bad], PLACES, VOCAB)


class ValidatorTest(unittest.TestCase):
    def setUp(self):
        self.g = make_graph()

    def check(self, r):
        return validator.validate_rule(r, self.g)

    def test_valid_rules_pass(self):
        ok = self.check(rule(**{"control-action": [{"step": 1, "action-type": "turn-on", "target": ["lamp-a"]}]}))
        self.assertTrue(ok["passed"], ok)
        ok = self.check(rule(**{
            "motion-action": [{"step": 1, "action-type": "navigate-to", "destination": ["room_a"]}],
            "perception-action": [{"step": 1, "action-type": "detect-objects", "object-class": ["person"]}],
            "report-action": ["report-result"]}))
        self.assertTrue(ok["passed"], ok)

    def test_schema(self):
        r = self.check(rule(**{"control-action": [{"step": 0, "action-type": "turn-on"}]}))
        self.assertEqual(r["first_failed_check"], "schema")

    def test_hallucinated_action_is_reference(self):
        r = self.check(rule(**{"control-action": [{"step": 1, "action-type": "cool-down"}]}))
        self.assertEqual(r["first_failed_check"], "reference")

    def test_unknown_place_and_device_are_reference(self):
        r = self.check(rule(**{"motion-action": [{"step": 1, "action-type": "navigate-to", "destination": ["kitchen"]}]}))
        self.assertEqual(r["first_failed_check"], "reference")
        r = self.check(rule(**{"control-action": [{"step": 1, "action-type": "turn-on", "target": ["lamp-z"]}]}))
        self.assertEqual(r["first_failed_check"], "reference")

    def test_target_must_offer_the_action(self):
        r = self.check(rule(**{"control-action": [{"step": 1, "action-type": "turn-on", "target": ["robot-1"]}]}))
        self.assertEqual(r["first_failed_check"], "reference")

    def test_wrong_slot(self):
        r = self.check(rule(**{"motion-action": [{"step": 1, "action-type": "detect-objects", "destination": ["room_a"]}]}))
        self.assertEqual(r["first_failed_check"], "slot")

    def test_args_range_and_unknown_key(self):
        r = self.check(rule(**{"control-action": [
            {"step": 1, "action-type": "set-value", "target": ["lamp-a"], "args": {"value": 150}}]}))
        self.assertEqual(r["first_failed_check"], "args")
        r = self.check(rule(**{"control-action": [
            {"step": 1, "action-type": "set-value", "target": ["lamp-a"], "args": {"value": 50, "color": "red"}}]}))
        self.assertEqual(r["first_failed_check"], "args")
        r = self.check(rule(**{"control-action": [{"step": 1, "action-type": "set-value", "target": ["lamp-a"]}]}))
        self.assertEqual(r["first_failed_check"], "args")  # value 필수
        r = self.check(rule(**{"control-action": [
            {"step": 1, "action-type": "set-value", "target": ["lamp-a"], "args": {"value": 70}}]}))
        self.assertTrue(r["passed"], r)

    def test_args_without_target_pass_if_any_device_accepts(self):
        r = self.check(rule(**{"control-action": [{"step": 1, "action-type": "set-value", "args": {"value": 30}}]}))
        self.assertTrue(r["passed"], r)

    def test_non_object_is_schema_failure(self):
        self.assertEqual(self.check(["not", "a", "rule"])["first_failed_check"], "schema")


class AssignTest(unittest.TestCase):
    def setUp(self):
        self.g = make_graph()

    def test_target_gives_execute(self):
        d = assign.decide(rule(**{"control-action": [{"step": 1, "action-type": "turn-on", "target": ["lamp-a"]}]}), self.g)
        self.assertEqual((d["verdict"], d["assigned_devices"]), ("execute", ["lamp-a"]))

    def test_two_candidates_ask(self):
        d = assign.decide(rule(**{"control-action": [{"step": 1, "action-type": "turn-on"}]}), self.g)
        self.assertEqual(d["verdict"], "ask-clarification")
        self.assertIn("lamp-a", d["clarification"])

    def test_place_condition_narrows_control_candidates(self):
        r = rule(**{"control-action": [{"step": 1, "action-type": "turn-on"}]})
        r["condition"] = {"geographic-location": {"destination": ["room_b"]}}
        d = assign.decide(r, self.g)
        self.assertEqual((d["verdict"], d["assigned_devices"]), ("execute", ["lamp-b"]))

    def test_no_single_device_rejects(self):
        d = assign.decide(rule(**{"control-action": [{"step": 1, "action-type": "turn-on"}],
                                  "motion-action": [{"step": 1, "action-type": "navigate-to"}]}), self.g)
        self.assertEqual(d["verdict"], "reject")


class RetrievalTest(unittest.TestCase):
    def setUp(self):
        self.g = make_graph()

    def test_alias_match(self):
        c = retrieval.retrieve(["A실", "조명", "켜다"], self.g)
        self.assertIn("turn-on", c["actions"])
        self.assertIn("lamp-a", c["devices"])
        self.assertIn("room_a", c["places"])

    def test_verb_only_finds_both_lamps(self):
        c = retrieval.retrieve(["불", "켜다"], self.g)
        self.assertTrue({"lamp-a", "lamp-b"} <= set(c["devices"]))

    def test_unknown_phrases_give_no_candidates(self):
        c = retrieval.retrieve(["냉장고"], self.g, threshold=0.5)
        self.assertEqual(c["actions"], [])

    def test_object_class_alias(self):
        c = retrieval.retrieve(["사람", "확인하다"], self.g)
        self.assertIn("person", c["classes"])
        self.assertIn("detect-objects", c["actions"])


class GenerationTest(unittest.TestCase):
    def test_parse_variants(self):
        self.assertEqual(generation.parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(generation.parse_json_object('설명입니다 {"a": {"b": 2}} 끝'), {"a": {"b": 2}})
        with self.assertRaises(ValueError):
            generation.parse_json_object("JSON 없음")

    def test_retry_then_success_and_failure(self):
        class Flaky:
            name = "flaky"

            def __init__(self, outputs):
                self.outputs = list(outputs)

            def complete(self, messages, temperature=0.0):
                return self.outputs.pop(0)

        ok = generation.generate(Flaky(["garbage", '{"x": 1}']), [], retries=1)
        self.assertEqual((ok["output"], ok["attempts"]), ({"x": 1}, 2))
        bad = generation.generate(Flaky(["garbage", "still garbage"]), [], retries=1)
        self.assertIsNone(bad["output"])
        self.assertIn("unparseable", bad["error"])
        none = generation.generate(Flaky(["garbage"]), [], retries=0)
        self.assertEqual(none["attempts"], 1)

    def test_prompt_lists_only_candidates(self):
        g = make_graph()
        c = retrieval.retrieve(["A실", "조명", "켜다"], g)
        text = "\n".join(m["content"] for m in generation.build_messages("A실 조명 켜 줘", ["A실", "조명", "켜다"], c, g))
        self.assertIn("lamp-a", text)
        self.assertIn("후보에 없는", text)


GOLD = [
    {"id": "n1", "utterance": "A실 조명 켜 줘", "phrases": ["A실", "조명", "켜다"], "label": "normal",
     "gold_verdict": "execute",
     "gold_rule": {"control-action": [{"step": 1, "action-type": "turn-on", "target": ["lamp-a"]}]}},
    {"id": "m1", "utterance": "불 켜 줘", "phrases": ["불", "켜다"], "label": "ambiguous",
     "gold_verdict": "ask-clarification", "gold_candidates": ["lamp-a", "lamp-b"]},
    {"id": "i1", "utterance": "냉장고 문 열어 줘", "phrases": ["냉장고", "문", "열다"], "label": "invalid",
     "gold_verdict": "reject", "invalid_reason": "nonexistent-action"},
]


class EndToEndTest(unittest.TestCase):
    def test_mock_llm_walks_every_path(self):
        g = make_graph()
        llm = generation.MockLLM(GOLD, g)
        got = {r["id"]: pipeline.run_one(r, g, llm) for r in GOLD}
        self.assertEqual(got["n1"]["verdict"], "execute")
        self.assertEqual(got["n1"]["assigned_devices"], ["lamp-a"])
        self.assertEqual(got["n1"]["final_rule"]["action"], GOLD[0]["gold_rule"])
        self.assertEqual(got["m1"]["verdict"], "ask-clarification")
        self.assertIsNone(got["m1"]["final_rule"])
        self.assertEqual(got["i1"]["verdict"], "reject")
        self.assertEqual(got["i1"]["validation"]["first_failed_check"], "declined")
        for r in got.values():  # results 형식: 검증 전 원본 출력과 후보를 항상 남긴다
            self.assertIn("raw_llm_output", r)
            self.assertIn("candidates", r)

    def test_hallucination_is_rejected_and_logged_before_validation(self):
        class Hallucinator:
            name = "hallucinator"

            def complete(self, messages, temperature=0.0):
                return json.dumps(rule(**{"control-action": [{"step": 1, "action-type": "cool-down"}]}))

        g = make_graph()
        r = pipeline.run_one(GOLD[0], g, Hallucinator())
        self.assertEqual(r["verdict"], "reject")
        self.assertEqual(r["validation"]["first_failed_check"], "reference")
        self.assertIsNotNone(r["raw_llm_output"])  # 환각률 계산용 원본
        self.assertIsNone(r["final_rule"])

    def test_unparseable_output_is_rejected(self):
        class Garbage:
            name = "garbage"

            def complete(self, messages, temperature=0.0):
                return "I cannot do that"

        r = pipeline.run_one(GOLD[0], make_graph(), Garbage())
        self.assertEqual((r["verdict"], r["validation"]["first_failed_check"]), ("reject", "schema"))
        self.assertEqual(r["attempts"], 2)

    def test_cli_writes_results(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tds = []
            for i, td in enumerate([lamp("lamp-a", "room_a", "A실"), lamp("lamp-b", "room_b", "B실"), ROBOT]):
                p = d / f"td{i}.json"
                p.write_text(json.dumps(td, ensure_ascii=False), encoding="utf-8")
                tds += ["--td", str(p)]
            (d / "places.json").write_text(json.dumps(PLACES, ensure_ascii=False), encoding="utf-8")
            (d / "gold.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in GOLD), encoding="utf-8")
            code = pipeline.main(tds + ["--places", str(d / "places.json"),
                                       "--vocab", str(ROOT / "docs/pilot-spec/vocab.json"),
                                       "--gold", str(d / "gold.jsonl"), "--out", str(d / "out.jsonl"),
                                       "--llm", "mock", "--runs", "2"])
            self.assertEqual(code, 0)
            lines = [json.loads(l) for l in (d / "out.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(lines), 6)
            self.assertEqual({l["run"] for l in lines}, {1, 2})


if __name__ == "__main__":
    unittest.main()
