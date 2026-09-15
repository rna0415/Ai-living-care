"""
graph_cot_agent.py — v5 스키마 기반 Intent 상태머신 에이전트 (2세대 아키텍처).

**2026-09 재설계**: 1세대는 axis를 받아 고정 5단계(action/judgement/timing) plan을 도는
구조였다. 이건 이 파일이 지어낸 분류였다 — 그런데 실제로는 seed 저장소에
`livingcare_graph_v5_seed_runtime_examples.cypher`라는, **한 번도 로드하지 않은 파일**에
Intent/IntentCycle/Action/Assessment/ConditionRegistration/IntentKnowledgeLookup이라는
진짜 실행 상태머신 스키마와 그 위에 짠 worked example 3개(시나리오 A/B/C)가 이미 있었다.
2세대는 그 스키마를 그대로 구현한다:

    Intent{needs_action, execution_timing, needs_judgment} — A/T/J 세 값으로 분기
    needs_action=false            -> 지식조회(MedicationKnowledge 대조), 끝
    needs_action=true, immediate  -> 바로 실행 루프
    needs_action=true, conditional-> ConditionRegistration 등록 후 대기, 트리거되면
                                      새 즉시형 Intent를 만들어 같은 루프로 합류
    실행 루프: check_item 하나 꺼내 Action 실행(OBSERVE/ACTUATE는 CheckItem.default_action_type
    이 이미 갖고 있음) -> OBSERVE면 Assessment로 severity 판정 -> CONCERN이 아니면 계속
    스캔(큐 남으면 반복, 없으면 종료) -> CONCERN이면 재시도 한도(LoopTerminationPolicy.
    max_cycles) 확인 -> 한도 도달이면 사람에게 알림하고 종료, 아니면 ResponseSelectionPolicy가
    고른 다음 check_item을 큐에 넣고 반복.

runtime_examples.cypher는 여전히 SeedGraph 파서로 로드하지 않는다(WHERE절 cross-join
패턴이라 파서가 못 다룸) — 대신 그 안의 worked example 3개를 이 엔진의 **검증용 기대값**으로
쓴다(__main__ 참조). 정책/규칙 seed(observation/response/termination policy, MonitoringRule)는
1세대와 동일하게 그대로 조회한다 — 바뀐 건 "그 지식을 어떤 상태머신으로 소비하는가"다.

Ai-living-care 저장소의 기존 pipeline.py / graph_retrieval.py / sequence_generator.py는
전혀 import하지 않는다. 라이브 Neo4j 연결도 없다 — .cypher 텍스트 자체가 데이터 소스다.

실행:
    python graph_cot_agent.py
    python graph_cot_agent.py WellBeing 15
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_KG_DIR = r"C:\Users\A\Desktop\산학협력\Ai-living-care\manager_ai_agent\knowledge_graph"

# runtime_examples.cypher는 여전히 여기서 로드하지 않는다 — WHERE절 cross-join 패턴이라
# 이 파서가 못 다룬다. 대신 그 파일의 worked example 3개를 __main__에서 기대값으로 직접 쓴다.
SEED_FILES = [
    "livingcare_graph_v5_seed.cypher",
    "livingcare_graph_v5_seed_additions.cypher",
    "livingcare_graph_v5_seed_comfort_setpoints.cypher",
    "livingcare_graph_v5_seed_response_protocols.cypher",
]

# resp_comfort_mild(Comfort)·resp_wellbeing_concern(WellBeing) rationale 원문에 그대로 있는
# 재량 구분 — "WellBeing/Safety는 결정론", "Comfort는 에이전트 루프 파일럿". 숫자 tier는
# v5에 없으므로 만들지 않고, 이 axis 이름 자체를 근거로 쓴다.
AGENT_LOOP_AXES = {"Comfort"}

_SEVERITY_RANK = {"INFO": 0, "MILD": 1, "CONCERN": 2}
_NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
# uses_baseline 규칙(예: mr_wb6 체중감소)이 필요로 하는 VitalBaseline.vital_type 매핑 —
# 지금 seed엔 weight baseline만 있다(HAS_BASELINE 관계 2건, 둘 다 vital_type="weight").
_VITAL_TYPE_BY_CHECK_ITEM = {"ci:weight": "weight"}


def _evaluate_single_rule(rule: dict, obs, personalizer: Optional[Callable] = None,
                           baseline: Optional[float] = None) -> tuple[bool, bool]:
    """규칙 하나 vs 관측값 하나 -> (발화 여부, 개인화 threshold를 썼는지).

    모듈 최상위 함수로 뺀 이유: GraphCoTAgent 없이도(에이전트 인스턴스화 없이) 몬테카를로
    강건성 테스트에서 그대로 재사용하려고 — eval_robustness.py 참조. personalizer는
    (rule) -> (vulnerable_threshold|None, is_personalized) 형태의 콜백(GraphCoTAgent.
    _personalized_threshold와 동일 시그니처); 안 넘기면 개인화 없이 일반 threshold만 쓴다.
    baseline은 uses_baseline=true인 규칙(threshold_kg/threshold_percent, 예: mr_wb6
    체중감소)에만 쓰인다 — 없으면(None) 이런 규칙은 그냥 미발화로 처리한다(기존 동작 유지,
    baseline 없이 kg/percent 변화량을 계산할 방법이 없으므로).
    """
    if rule.get("condition_qualifier", "").endswith("_immediate"):
        return bool(obs) is True, False
    if rule.get("uses_baseline") and ("threshold_kg" in rule or "threshold_percent" in rule):
        if baseline is None or not isinstance(obs, (int, float)) or baseline == 0:
            return False, False
        delta = obs - baseline
        direction = rule.get("direction")
        direction_ok = (direction == "loss" and delta < 0) or (direction == "gain" and delta > 0)
        if not direction_ok:
            return False, False
        kg_hit = "threshold_kg" in rule and abs(delta) >= rule["threshold_kg"]
        pct_hit = "threshold_percent" in rule and abs(delta) / baseline * 100 >= rule["threshold_percent"]
        return bool(kg_hit or pct_hit), False
    if "threshold_hours" in rule and isinstance(obs, (int, float)):
        return obs >= rule["threshold_hours"], False
    if "threshold_minutes" in rule and isinstance(obs, (int, float)):
        return obs >= rule["threshold_minutes"], False
    if "threshold_lux" in rule and isinstance(obs, (int, float)):
        return obs < rule["threshold_lux"], False
    if "threshold_celsius" in rule and isinstance(obs, (int, float)):
        threshold = rule["threshold_celsius"]
        personalized = False
        if personalizer is not None:
            vuln_threshold, personalized = personalizer(rule)
            if vuln_threshold is not None:
                threshold = vuln_threshold
        hit = obs < threshold if rule.get("direction") == "below" else obs > threshold
        return hit, hit and personalized
    return False, False


# --------------------------------------------------------------------------- #
# 0. Cypher-lite 파서 — CREATE 노드/관계, SET 노드/관계 속성만 다룬다(seed 파일 실측 범위).
#    load_v5.py와 같은 방식으로 라인 단위 주석 제거 후 세미콜론으로 문장을 자른다.
# --------------------------------------------------------------------------- #
def _split_top_level(s: str, sep: str = ",") -> list[str]:
    parts, depth, in_str, buf = [], 0, False, []
    for i, ch in enumerate(s):
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            in_str = not in_str
            buf.append(ch)
        elif ch in "[{" and not in_str:
            depth += 1
            buf.append(ch)
        elif ch in "]}" and not in_str:
            depth -= 1
            buf.append(ch)
        elif ch == sep and not in_str and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _parse_value(v: str):
    v = v.strip()
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v == "true":
        return True
    if v == "false":
        return False
    if v == "null":
        return None
    if v.startswith("[") and v.endswith("]"):
        return [_parse_value(x) for x in _split_top_level(v[1:-1], ",")]
    try:
        return float(v) if "." in v else int(v)
    except ValueError:
        return v


def _parse_props(s: str) -> dict:
    props = {}
    for part in _split_top_level(s, ","):
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        props[key.strip()] = _parse_value(val)
    return props


_NODE_RE = re.compile(r"^CREATE\s*\(:(\w+)\s*\{(.*)\}\)$")
_REL_RE = re.compile(
    r"^MATCH\s*\((\w+):(\w+)\s*\{(.*?)\}\)\s*,\s*\((\w+):(\w+)\s*\{(.*?)\}\)\s*"
    r"CREATE\s*\(\w+\)-\[:(\w+)\s*(?:\{(.*?)\})?\]->\(\w+\)$"
)
_SET_NODE_RE = re.compile(r"^MATCH\s*\((\w+):(\w+)\s*\{(.*?)\}\)\s*SET\s+(.*)$")
_SET_REL_RE = re.compile(
    r"^MATCH\s*\((\w+):(\w+)\s*\{(.*?)\}\)-\[(\w+):(\w+)\]->\((\w+):(\w+)\s*\{(.*?)\}\)\s*SET\s+(.*)$"
)


class SeedGraph:
    """v5 seed cypher를 그대로 읽어 만든 인메모리 그래프. Neo4j 없음."""

    def __init__(self, files: list[str] = SEED_FILES, base_dir: str = _KG_DIR):
        self.nodes_by_label: dict[str, list[dict]] = {}
        self.rels: list[dict] = []  # {"start":node, "type":str, "end":node, "props":dict}
        for fname in files:
            self._load(os.path.join(base_dir, fname))
        self._apply_property_joins()

    # ---- 로딩 ----
    def _load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip() and not l.strip().startswith("//")]
        text = "".join(lines)
        for stmt in (s.strip() for s in text.split(";") if s.strip()):
            self._exec(stmt)

    def _exec(self, stmt: str) -> None:
        if m := _NODE_RE.match(stmt):
            label, props_txt = m.groups()
            self.nodes_by_label.setdefault(label, []).append(_parse_props(props_txt))
            return
        if m := _REL_RE.match(stmt):
            _, l1, p1, _, l2, p2, rel_type, relprops_txt = m.groups()
            start = self.find_one(l1, _parse_props(p1))
            end = self.find_one(l2, _parse_props(p2))
            if start is not None and end is not None:
                self.rels.append({
                    "start": start, "type": rel_type, "end": end,
                    "props": _parse_props(relprops_txt) if relprops_txt else {},
                })
            return
        if m := _SET_REL_RE.match(stmt):
            _, l1, p1, _, rel_type, _, l2, p2, set_clause = m.groups()
            start = self.find_one(l1, _parse_props(p1))
            end = self.find_one(l2, _parse_props(p2))
            rel = next((r for r in self.rels if r["start"] is start and r["end"] is end and r["type"] == rel_type), None)
            if rel is not None:
                rel["props"].update(self._parse_set_clause(set_clause))
            return
        if m := _SET_NODE_RE.match(stmt):
            _, label, props_txt, set_clause = m.groups()
            node = self.find_one(label, _parse_props(props_txt))
            if node is not None:
                node.update(self._parse_set_clause(set_clause))
            return
        # 그 외(검증용 MATCH...RETURN, WHERE 기반 blanket join 2건)는 의도적으로 건너뛴다 —
        # blanket join(EVALUATES/ESCALATES_VIA)은 아래 _apply_property_joins()가 대신한다.

    @staticmethod
    def _parse_set_clause(clause: str) -> dict:
        out = {}
        for part in _split_top_level(clause, ","):
            if "=" not in part:
                continue
            lhs, rhs = part.split("=", 1)
            prop = lhs.strip().split(".", 1)[-1]
            out[prop] = _parse_value(rhs)
        return out

    def _apply_property_joins(self) -> None:
        """seed 파일의 두 blanket-join 문(WHERE 기반 속성 매칭)을 코드로 재현한다:
        (MonitoringRule)-[:EVALUATES]->(CheckItem)  — rule.check_item_id로
        (LoopTerminationPolicy)-[:ESCALATES_VIA]->(CheckItem) — policy.escalation_check_item_id로
        """
        for rule in self.nodes_by_label.get("MonitoringRule", []):
            ci = self.find_one("CheckItem", {"check_item_id": rule.get("check_item_id")})
            if ci is not None:
                self.rels.append({"start": rule, "type": "EVALUATES", "end": ci, "props": {}})
        for policy in self.nodes_by_label.get("LoopTerminationPolicy", []):
            ci = self.find_one("CheckItem", {"check_item_id": policy.get("escalation_check_item_id")})
            if ci is not None:
                self.rels.append({"start": policy, "type": "ESCALATES_VIA", "end": ci, "props": {}})

    # ---- 조회 ----
    def find_one(self, label: str, match_props: dict) -> Optional[dict]:
        for n in self.nodes_by_label.get(label, []):
            if all(n.get(k) == v for k, v in match_props.items()):
                return n
        return None

    def find_all(self, label: str, match_props: Optional[dict] = None) -> list[dict]:
        nodes = self.nodes_by_label.get(label, [])
        if not match_props:
            return list(nodes)
        return [n for n in nodes if all(n.get(k) == v for k, v in match_props.items())]

    def related(self, node: dict, rel_type: str, reverse: bool = False) -> list[dict]:
        if reverse:
            return [r["start"] for r in self.rels if r["end"] is node and r["type"] == rel_type]
        return [r["end"] for r in self.rels if r["start"] is node and r["type"] == rel_type]

    def rel_props(self, start: dict, rel_type: str, end: dict) -> dict:
        rel = next((r for r in self.rels if r["start"] is start and r["type"] == rel_type and r["end"] is end), {})
        return rel.get("props", {}) if rel else {}


# --------------------------------------------------------------------------- #
# 1. Retriever — 도구 하나. query_type이 v5의 5개 관계 유형과 1:1.
# --------------------------------------------------------------------------- #
RETRIEVER_TOOL_SCHEMA = {
    "name": "retrieve_graph_knowledge",
    "description": (
        "LivingCare v5 지식그래프(CheckItem/Device/MonitoringRule/ObservationSelectionPolicy/"
        "ResponseSelectionPolicy/LoopTerminationPolicy, 읽기 전용)를 조회한다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["observation_policy", "monitoring_rules", "response_policy", "termination_policy", "device", "subject_context"],
                "description": (
                    "observation_policy: target(axis)의 ObservationSelectionPolicy + 관측 대상 CheckItem(우선순위순). "
                    "monitoring_rules: target(check_item_id)에 적용되는 MonitoringRule 전체. "
                    "response_policy: target(axis)의 ResponseSelectionPolicy들 + 대응 CheckItem(우선순위순), "
                    "min_severity를 함께 반환하니 호출측이 현재 severity와 비교해 고른다. "
                    "termination_policy: target(axis)의 LoopTerminationPolicy(max_cycles, 에스컬레이션 대상). "
                    "device: target(check_item_id)를 MONITORS하는 Device 목록. "
                    "subject_context: target(subject_id)의 개인 맥락 — is_vulnerable, 진단명, 복용 중인 약, "
                    "그 약이 MedicationKnowledge에 걸리는지(medication_flags)까지 함께 반환."
                ),
            },
            "target": {"type": "string", "description": "axis(WellBeing/Safety/Comfort), check_item_id(ci:...), 또는 subject_id(subj:...)"},
        },
        "required": ["query_type", "target"],
    },
}


class GraphRetrieverTool:
    name = RETRIEVER_TOOL_SCHEMA["name"]
    schema = RETRIEVER_TOOL_SCHEMA

    def __init__(self, graph: SeedGraph):
        self.graph = graph
        self.call_log: list[dict] = []

    def __call__(self, query_type: str, target: str) -> dict:
        result = self._dispatch(query_type, target)
        self.call_log.append({"query_type": query_type, "target": target, "found": result.get("found")})
        return result

    def _selects(self, policies: list[dict]) -> list[dict]:
        out = []
        for p in policies:
            for ci in self.graph.related(p, "SELECTS"):
                out.append({**ci, "priority": self.graph.rel_props(p, "SELECTS", ci).get("priority")})
        return sorted(out, key=lambda c: (c.get("priority") is None, c.get("priority")))

    def _dispatch(self, query_type: str, target: str) -> dict:
        if query_type == "observation_policy":
            policies = self.graph.find_all("ObservationSelectionPolicy", {"axis": target})
            if not policies:
                return {"found": False, "reason": f"axis '{target}'의 ObservationSelectionPolicy 없음"}
            return {"found": True, "policies": policies, "check_items": self._selects(policies)}

        if query_type == "monitoring_rules":
            rules = self.graph.find_all("MonitoringRule", {"check_item_id": target})
            if not rules:
                return {"found": False, "reason": f"check_item '{target}'에 적용되는 MonitoringRule 없음"}
            return {"found": True, "rules": rules}

        if query_type == "response_policy":
            policies = self.graph.find_all("ResponseSelectionPolicy", {"axis": target})
            if not policies:
                return {"found": False, "reason": f"axis '{target}'의 ResponseSelectionPolicy 없음"}
            by_policy = [{**p, "check_items": self._selects([p])} for p in policies]
            return {"found": True, "policies": by_policy}

        if query_type == "termination_policy":
            policy = self.graph.find_one("LoopTerminationPolicy", {"axis": target})
            if policy is None:
                return {"found": False, "reason": f"axis '{target}'의 LoopTerminationPolicy 없음"}
            escalates_to = self.graph.related(policy, "ESCALATES_VIA")
            return {"found": True, "policy": policy, "escalates_to": escalates_to}

        if query_type == "device":
            ci = self.graph.find_one("CheckItem", {"check_item_id": target})
            if ci is None:
                return {"found": False, "reason": f"check_item '{target}' 없음"}
            devices = self.graph.related(ci, "MONITORS", reverse=True)
            # robot_dispatch·call_caregiver는 MONITORS로 안 묶여 있다(seed 주석에 명시된 설계) —
            # robot_dispatch는 limo_robot_agent가 겸임, call_caregiver는 알림 채널이라 물리 기기가 없다.
            if not devices and target == "ci:robot_dispatch":
                robot = self.graph.find_one("Device", {"name": "LimoRobot"})
                devices = [robot] if robot else []
            return {"found": True, "devices": devices}

        if query_type == "subject_context":
            subj = self.graph.find_one("Subject", {"subject_id": target})
            if subj is None:
                return {"found": False, "reason": f"subject '{target}' 없음"}
            active_drugs = [
                d for d in self.graph.related(subj, "TAKES")
                if self.graph.rel_props(subj, "TAKES", d).get("is_active")
            ]
            med_flags = []
            for d in active_drugs:
                for mk in self.graph.related(d, "CONCERNS", reverse=True):
                    med_flags.append({
                        "rule_id": mk["rule_id"], "drug": d["name"],
                        "drug_class": mk.get("drug_class"), "recommendation": mk.get("recommendation"),
                    })
            return {
                "found": True,
                "subject": subj,
                "diagnoses": [d.get("condition_name") for d in self.graph.related(subj, "HAS_DIAGNOSIS")],
                "active_drugs": [d["name"] for d in active_drugs],
                "fall_history": self.graph.related(subj, "HAS_FALL_EVENT"),
                "medication_flags": med_flags,
                "baselines": self.graph.related(subj, "HAS_BASELINE"),
            }

        return {"found": False, "reason": f"알 수 없는 query_type '{query_type}'"}


# --------------------------------------------------------------------------- #
# 2. Intent 상태머신 — runtime_examples.cypher의 실제 실행 스키마를 그대로 구현.
# --------------------------------------------------------------------------- #
class GraphCoTAgent:
    """
    Intent{needs_action, execution_timing, needs_judgment}를 받아 분기한다.
    WellBeing/Safety — 결정론 루프(코드가 threshold 비교). Comfort(AGENT_LOOP_AXES) — LLM이
    retrieve_graph_knowledge를 스스로 호출하며 판단(진짜 tool-use 루프, LangChain 없음).
    """

    def __init__(self, retriever: GraphRetrieverTool, llm_client=None, model: str = "claude-opus-4-8"):
        self.retriever = retriever
        self.graph = retriever.graph
        self.memory: dict = {}
        self._llm_client = llm_client
        self._model = model
        self._counters = {"intent": 0, "action": 0, "assessment": 0, "cycle": 0, "registration": 0}

    def _next_id(self, kind: str) -> int:
        self._counters[kind] += 1
        return self._counters[kind]

    def _personalized_threshold(self, rule: dict, subj_ctx: dict) -> tuple[Optional[float], bool]:
        """규칙에 vulnerable_condition_value(예: "20°C 미만")가 있고 subject.is_vulnerable이면
        일반 threshold 대신 그 값을 쓴다. 타입 있는 vulnerable_threshold_celsius 필드가 seed에
        없어서(실제 데이터 한계) 문자열에서 숫자만 정규식으로 뽑는다 — 있는 그대로 밝혀둔다."""
        is_vulnerable = bool(subj_ctx.get("found") and subj_ctx.get("subject", {}).get("is_vulnerable"))
        if is_vulnerable and rule.get("vulnerable_condition_value"):
            m = _NUM_RE.search(rule["vulnerable_condition_value"])
            if m:
                return float(m.group(1)), True
        return None, False

    # ---- 진입점: Intent 하나를 A(needs_action)/T(execution_timing)로 분기 ----
    def dispatch_intent(self, raw_text: str, target_domain: str, needs_action: bool,
                         execution_timing: Optional[str] = None, needs_judgment: bool = True,
                         subject_id: Optional[str] = None, hour: int = 12,
                         observation_override=None,
                         condition_rule_id: Optional[str] = None,
                         condition_fixed_check_item_id: Optional[str] = None) -> dict:
        intent = {
            "intent_id": self._next_id("intent"), "raw_text": raw_text, "subject_id": subject_id,
            "target_domain": target_domain, "needs_action": needs_action,
            "execution_timing": execution_timing, "needs_judgment": needs_judgment,
        }
        if not needs_action:
            return self._knowledge_lookup(intent)
        if execution_timing == "conditional":
            return self._register_condition(intent, condition_rule_id, condition_fixed_check_item_id)
        if execution_timing == "immediate":
            return self._run_loop(intent, hour, observation_override)
        raise ValueError(f"needs_action=true인데 execution_timing이 'immediate'/'conditional'이 아님: {execution_timing!r}")

    # ---- A=false: 지식조회 (IntentKnowledgeLookup 대응) ----
    def _knowledge_lookup(self, intent: dict) -> dict:
        subject_id = intent.get("subject_id")
        ctx = self.retriever(query_type="subject_context", target=subject_id) if subject_id else {"found": False}
        med_flags = ctx.get("medication_flags", []) if ctx.get("found") else []
        return {
            "intent": intent, "source": "knowledge_lookup",
            "found": bool(med_flags),
            "answer_summary": med_flags[0]["recommendation"] if med_flags else "관련 MedicationKnowledge 없음 — 이 약/진단 조합은 seed에 주의사항이 등록돼 있지 않음",
            "medication_flags": med_flags,
            "grounded_on": [m["rule_id"] for m in med_flags],
            "retriever_calls": len(self.retriever.call_log),
        }

    # ---- A=true, T=conditional: 조건 등록 (ConditionRegistration 대응) ----
    def _register_condition(self, intent: dict, rule_id: Optional[str],
                             fixed_check_item_id: Optional[str]) -> dict:
        if not rule_id:
            raise ValueError("execution_timing='conditional'에는 condition_rule_id가 필요하다 — "
                              "무엇을 지켜보다가 트리거할지가 없으면 등록만 하고 끝낼 수 없다.")
        registration = {
            "registration_id": self._next_id("registration"), "intent_id": intent["intent_id"],
            "rule_id": rule_id, "fixed_check_item_id": fixed_check_item_id, "is_active": True,
        }
        return {"intent": intent, "source": "condition_registered", "registration": registration}

    # ---- 조건 트리거: 새 즉시형 Intent를 만들어 같은 루프로 합류 (ConditionTriggerLog 대응) ----
    def trigger_condition(self, registration: dict, subject_id: str, target_domain: str, hour: int,
                           observation_override=None) -> dict:
        triggered_intent = {
            "intent_id": self._next_id("intent"),
            "raw_text": f"[system] {registration['rule_id']} triggered for {subject_id}",
            "subject_id": subject_id, "target_domain": target_domain,
            "needs_action": True, "execution_timing": "immediate", "needs_judgment": False,
        }
        result = self._run_loop(triggered_intent, hour, observation_override,
                                 forced_check_item_id=registration.get("fixed_check_item_id"))
        result["triggered_from_registration"] = registration["registration_id"]
        return result

    # ---- 실행 루프: check_item 하나씩 꺼내 Action -> (OBSERVE면) Assessment -> 다음 결정 ----
    def _run_loop(self, intent: dict, hour: int, observation_override=None,
                  forced_check_item_id: Optional[str] = None) -> dict:
        axis = intent["target_domain"]
        if axis in AGENT_LOOP_AXES:
            return self._run_loop_agentic(intent, hour)

        subject_id = intent.get("subject_id")
        period = "night" if (hour < 6 or hour >= 22) else "day"
        subj_ctx = self.retriever(query_type="subject_context", target=subject_id) if subject_id else {"found": False}

        term_policy = self.retriever(query_type="termination_policy", target=axis)
        max_cycles = term_policy["policy"]["max_cycles"] if term_policy.get("found") else 1
        escalation_items = term_policy.get("escalates_to", []) if term_policy.get("found") else []
        escalation_ci = escalation_items[0] if escalation_items else None

        if forced_check_item_id:
            ci0 = self.graph.find_one("CheckItem", {"check_item_id": forced_check_item_id})
            queue: list[dict] = [ci0] if ci0 else []
        else:
            obs_policy = self.retriever(query_type="observation_policy", target=axis)
            queue = list(obs_policy.get("check_items", [])) if obs_policy.get("found") else []

        cycles: list[dict] = []
        concern_retries = 0
        final_severity = "NORMAL"
        grounded_on: list[str] = []
        personalized_used = False
        first_observation_done = False
        pending_reobserve: Optional[dict] = None  # CONCERN 대응(로봇 등) 후 다시 관측할 CheckItem

        def _is_escalation_target(check_item_id: str) -> bool:
            if escalation_ci is not None:
                return check_item_id == escalation_ci["check_item_id"]
            return check_item_id == "ci:call_caregiver"

        while queue:
            ci = queue.pop(0)
            seq_no = len(cycles) + 1
            action_type = ci.get("default_action_type", "OBSERVE")

            # ---- ACTUATE: 실행 -> 에스컬레이션 대상이면 종료, 응답 대기 중이던 재관측이
            #      남아 있으면 그걸로 돌아가고, 그것도 아니면 큐가 빌 때 종료 ----
            if action_type == "ACTUATE":
                devices = self.retriever(query_type="device", target=ci["check_item_id"])
                device_id = devices["devices"][0]["device_id"] if devices.get("found") and devices["devices"] else None
                if device_id is None and ci["check_item_id"] == "ci:call_caregiver":
                    device_id = "svc:call_caregiver"  # 물리 기기 없는 알림 채널
                action = {"action_id": self._next_id("action"), "check_item_id": ci["check_item_id"],
                          "action_type": "ACTUATE", "axis": axis, "device_id": device_id, "result_value": "dispatched"}

                if _is_escalation_target(ci["check_item_id"]):
                    is_terminal, reason = True, "escalated_to_human"
                elif pending_reobserve is not None:
                    queue = [pending_reobserve] + queue
                    pending_reobserve = None
                    is_terminal, reason = False, None
                else:
                    is_terminal = not queue
                    reason = "resolved_by_response" if is_terminal else None
                cycles.append({"cycle_id": self._next_id("cycle"), "sequence_no": seq_no, "action": action,
                                "assessment": None, "is_terminal": is_terminal, "termination_reason": reason})
                continue

            # ---- OBSERVE: 값 읽고 규칙과 비교 ----
            mr = self.retriever(query_type="monitoring_rules", target=ci["check_item_id"])
            ci_id = ci["check_item_id"]
            if isinstance(observation_override, dict):
                obs_value = observation_override.get(ci_id, MOCK_OBSERVATIONS.get(ci_id))
            elif not first_observation_done and observation_override is not None:
                obs_value = observation_override
            else:
                obs_value = MOCK_OBSERVATIONS.get(ci_id)
            first_observation_done = True

            baseline = None
            vital_type = _VITAL_TYPE_BY_CHECK_ITEM.get(ci_id)
            if vital_type and subj_ctx.get("found"):
                bl = next((b for b in subj_ctx.get("baselines", []) if b.get("vital_type") == vital_type), None)
                baseline = bl["baseline_value"] if bl else None

            action = {"action_id": self._next_id("action"), "check_item_id": ci["check_item_id"],
                      "action_type": "OBSERVE", "axis": axis, "device_id": None, "result_value": obs_value}

            applicable = [r for r in mr.get("rules", []) if r.get("axis") == axis
                          and r.get("time_context") in (None, period)] if mr.get("found") else []
            hit_rule = None
            for r in applicable:
                hit, pz = _evaluate_single_rule(
                    r, obs_value, personalizer=lambda rule: self._personalized_threshold(rule, subj_ctx),
                    baseline=baseline)
                if hit and (hit_rule is None or _SEVERITY_RANK.get(r["severity"], 0) > _SEVERITY_RANK.get(hit_rule["severity"], 0)):
                    hit_rule, personalized_used = r, personalized_used or pz

            severity = hit_rule["severity"] if hit_rule else "NORMAL"
            assessment = {"assessment_id": self._next_id("assessment"),
                          "rule_id": hit_rule["rule_id"] if hit_rule else None, "severity": severity}
            if hit_rule:
                grounded_on.append(hit_rule["rule_id"])
                if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(final_severity, 0):
                    final_severity = severity

            # "정상"(NORMAL/INFO/MILD) — CONCERN만 대응을 유발한다(설계 그대로).
            if severity != "CONCERN":
                is_terminal = not queue
                cycles.append({"cycle_id": self._next_id("cycle"), "sequence_no": seq_no, "action": action,
                                "assessment": assessment, "is_terminal": is_terminal,
                                "termination_reason": "no_concern_detected" if is_terminal else None})
                continue

            # ---- CONCERN: 재시도 한도 확인. max_cycles는 "몇 번째 CONCERN 관측에서
            # 재시도 없이 바로 escalate하는가"다 — Safety(max_cycles=1)는 1번째부터 바로
            # 에스컬레이션(재시도 없음), WellBeing(max_cycles=2)은 1번째는 응답(로봇 등)을
            # 한 번 시도하고 재관측, 2번째에서도 여전히 CONCERN이면 그때 에스컬레이션한다
            # (term_wellbeing.rationale: "1번 더 재확인할 여유를 둔다" — seed 원문 그대로). ----
            final_severity = "CONCERN"
            concern_retries += 1
            cycles.append({"cycle_id": self._next_id("cycle"), "sequence_no": seq_no, "action": action,
                            "assessment": assessment, "is_terminal": False, "termination_reason": None})

            if concern_retries >= max_cycles:
                queue = [escalation_ci] if escalation_ci else []
                if not queue:
                    cycles[-1]["is_terminal"] = True
                    cycles[-1]["termination_reason"] = "retry_limit_no_escalation_target"
                continue

            resp = self.retriever(query_type="response_policy", target=axis)
            candidates = sorted(
                [p for p in resp.get("policies", []) if _SEVERITY_RANK.get(p.get("min_severity"), 99) <= _SEVERITY_RANK["CONCERN"]],
                key=lambda p: _SEVERITY_RANK.get(p.get("min_severity"), -1), reverse=True)
            response_ci = next((p["check_items"][0] for p in candidates if p["check_items"]), None)
            queue = [response_ci] if response_ci else ([escalation_ci] if escalation_ci else [])
            if not queue:
                cycles[-1]["is_terminal"] = True
                cycles[-1]["termination_reason"] = "no_response_policy_matched"
            elif not _is_escalation_target(response_ci["check_item_id"]):
                pending_reobserve = ci  # 응답이 에스컬레이션이 아니면(예: 로봇 출동) 대응 후 원래 항목을 다시 본다

        return {
            "intent": intent, "source": "deterministic_loop", "axis": axis, "hour": hour,
            "cycles": cycles, "final_severity": final_severity, "escalate": final_severity == "CONCERN",
            "grounded_on": grounded_on, "personalized": personalized_used,
            "medication_flags": subj_ctx.get("medication_flags", []) if subj_ctx.get("found") else [],
            "termination_reason": cycles[-1]["termination_reason"] if cycles else "no_check_items_in_observation_policy",
            "n_cycles": len(cycles), "retriever_calls": len(self.retriever.call_log),
        }

    # ---- Comfort(AGENT_LOOP_AXES): LLM이 직접 도구를 호출하며 판단, 결과를 cycle 1개로 표현 ----
    def _run_loop_agentic(self, intent: dict, hour: int) -> dict:
        axis = intent["target_domain"]
        self._run_agentic(axis, hour)  # self.memory에 escalate/severity/response_check_item 등을 채움
        action = {"action_id": self._next_id("action"), "check_item_id": None,
                  "action_type": "LLM_AGENT_LOOP", "axis": axis, "device_id": None, "result_value": None}
        assessment = {"assessment_id": self._next_id("assessment"),
                      "rule_id": [r["rule_id"] for r in self.memory.get("triggered_rules", [])],
                      "severity": self.memory.get("severity", "unknown")}
        cycle = {"cycle_id": self._next_id("cycle"), "sequence_no": 1, "action": action, "assessment": assessment,
                  "is_terminal": True, "termination_reason": "llm_agent_decision"}
        return {
            "intent": intent, "source": "llm_agent", "axis": axis, "hour": hour,
            "cycles": [cycle], "final_severity": self.memory.get("severity", "unknown"),
            "escalate": self.memory.get("escalate", False),
            "grounded_on": [r["rule_id"] for r in self.memory.get("triggered_rules", [])],
            "personalized": False, "medication_flags": [],
            "termination_reason": "llm_agent_decision", "n_cycles": 1,
            "retriever_calls": len(self.retriever.call_log),
            "agent_reasoning": self.memory.get("agent_reasoning", ""),
            "response_check_item": (self.memory.get("response_check_item") or {}).get("check_item_id"),
        }

    # ---- tier(=Comfort) 축: LLM이 직접 도구를 호출하며 판단 ----
    def _run_agentic(self, axis: str, hour: int) -> list[dict]:
        if self._llm_client is None:
            raise RuntimeError(
                f"'{axis}' 축은 AGENT_LOOP_AXES에 있어 LLM 에이전트가 필요하다. "
                "GraphCoTAgent(llm_client=anthropic.Anthropic())로 클라이언트를 넘겨라."
            )
        system = (
            f"너는 LivingCare 판단 에이전트다. 지금 판단할 축은 '{axis}', 현재 시각은 {hour}시다.\n"
            "이 축은 관측 전용(로봇 출동 없음)이라 재량이 넓다 — retrieve_graph_knowledge 도구로 "
            "observation_policy·monitoring_rules·response_policy·termination_policy·device를 "
            "필요할 때마다 조회해서 근거를 모아라. 관측 센서값은 제공되지 않으니 그래프의 규칙과 "
            "정책만으로 상식적으로 판단하고 reasoning에 근거를 남겨라.\n"
            "충분히 조사했으면 다음 JSON만 출력해라(그 외 텍스트 금지):\n"
            '{"escalate": bool, "severity": "INFO"|"MILD"|"CONCERN"|"NORMAL", '
            '"response_check_item_id": str|null, "grounded_on": [rule_id...], "reasoning": str}'
        )
        messages = [{"role": "user", "content": f"'{axis}' 축을 판단해줘."}]
        agent_calls: list[dict] = []
        for _ in range(6):
            response = self._llm_client.messages.create(
                model=self._model, max_tokens=2048, system=system,
                tools=[RETRIEVER_TOOL_SCHEMA], messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break
            tool_use = next(b for b in response.content if b.type == "tool_use")
            result = self.retriever(**tool_use.input)
            agent_calls.append({"query_type": tool_use.input["query_type"], "target": tool_use.input["target"], "result": result})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result, ensure_ascii=False)}
            ]})
        else:
            raise RuntimeError(f"'{axis}' 판단이 tool-call 6회 안에 끝나지 않았다")

        final_text = next((b.text for b in response.content if b.type == "text"), "")
        decision = json.loads(final_text)
        self.memory["escalate"] = decision.get("escalate", False)
        self.memory["severity"] = decision.get("severity", "unknown")
        self.memory["triggered_rules"] = [{"rule_id": r} for r in decision.get("grounded_on", [])]
        self.memory["agent_reasoning"] = decision.get("reasoning", "")
        rci = decision.get("response_check_item_id")
        self.memory["response_check_item"] = {"check_item_id": rci} if rci else None
        return agent_calls

# 관측값은 mock — 실제 센서가 없다. check_item_id 기준(v5는 axis가 아니라 check_item에 값이 붙는다).
MOCK_OBSERVATIONS = {
    "ci:motion": 5.0,          # 마지막 움직임 이후 경과 시간(h)
    "ci:smoke": False,
    "ci:door_status": 2,       # 문이 열려 있던 시간(min) — 주간(30min)·야간(5min) 둘 다 안전한 기본값
    "ci:temperature": 16,      # 실내 온도(°C)
    "ci:ambient_light": 30,    # 조도(lux)
    "ci:fall_event": False,
    "ci:heartrate": 1.0,       # 마지막 동기화 이후 경과 시간(h) — mr_wb4 threshold(6h) 대비 안전
    "ci:medication_dispensing": 0.5,  # 복약 예정시각 이후 경과(h) — mr_wb8 threshold(2h) 대비 안전
    "ci:bathroom_occupancy": 5,       # 욕실 체류시간(min) — mr_sf4 threshold(20min) 대비 안전
}


# --------------------------------------------------------------------------- #
# demo + 검증 — runtime_examples.cypher의 worked example 3개를 기대값으로 재생한다.
# --------------------------------------------------------------------------- #
def _print_result(label: str, result: dict) -> None:
    print("=" * 78)
    print(f"[{label}] intent_id={result['intent']['intent_id']} raw_text={result['intent']['raw_text']!r}")
    print(f"  source={result.get('source')}")
    if "cycles" in result:
        for c in result["cycles"]:
            a = c["action"]
            line = f"  cycle {c['cycle_id']}(seq={c['sequence_no']}): {a['action_type']} {a['check_item_id']}"
            if c["assessment"]:
                line += f" -> severity={c['assessment']['severity']} (rule={c['assessment']['rule_id']})"
            if c["is_terminal"]:
                line += f"  [TERMINAL: {c['termination_reason']}]"
            print(line)
        print(f"  final_severity={result['final_severity']} escalate={result['escalate']} "
              f"grounded_on={result['grounded_on']} personalized={result['personalized']}")
    elif result.get("source") == "condition_registered":
        print(f"  registration={result['registration']}")
    elif result.get("source") == "knowledge_lookup":
        print(f"  found={result['found']} answer_summary={result['answer_summary']!r} grounded_on={result['grounded_on']}")
    print()


if __name__ == "__main__":
    graph = SeedGraph()
    print(f"[로딩] label별 노드 수: { {k: len(v) for k, v in graph.nodes_by_label.items()} }")
    print(f"[로딩] 관계 총 {len(graph.rels)}개\n")

    tool = GraphRetrieverTool(graph)

    if len(sys.argv) >= 2:
        axis_arg = sys.argv[1]
        hour_arg = int(sys.argv[2]) if len(sys.argv) >= 3 else 15
        agent = GraphCoTAgent(tool)
        res = agent.dispatch_intent(f"[cli] {axis_arg} 확인해줘", target_domain=axis_arg,
                                     needs_action=True, execution_timing="immediate", hour=hour_arg)
        _print_result(f"CLI axis={axis_arg} hour={hour_arg}", res)
        sys.exit(0)

    # ---- 시나리오 A: WellBeing 즉시조치 — 김옥순, 체중 급감(49.2kg, baseline 52.0kg=-5.4%) ----
    # 기대값(runtime_examples.cypher 시나리오 A): mr_wb6_weight_loss_frailty CONCERN ->
    # resp_wellbeing_concern -> ci:call_caregiver -> escalated_to_human, cycle 2개.
    agent_a = GraphCoTAgent(tool)
    res_a = agent_a.dispatch_intent(
        "오늘 옥순님 괜찮은지 확인해줘", target_domain="WellBeing", needs_action=True,
        execution_timing="immediate", subject_id="subj:kim_oksun_001", hour=9,
        observation_override={"ci:weight": 49.2},  # ci:weight가 몇 순위든 정확히 이 값이 꽂힌다
    )
    _print_result("시나리오 A (WellBeing·즉시·체중급감 기대)", res_a)

    # ---- 시나리오 B: Safety 조건등록 -> 실제 낙상 트리거 -> 즉시 대응 ----
    # 기대값(시나리오 B): ConditionRegistration(mr_sf5_fall_detected) 등록 -> 트리거 시
    # mr_sf5_fall_detected CONCERN -> resp_safety_concern -> ci:call_caregiver -> escalated_to_human.
    agent_b = GraphCoTAgent(tool)
    reg_result = agent_b.dispatch_intent(
        "갑수님 낙상 나면 바로 알려줘", target_domain="Safety", needs_action=True,
        execution_timing="conditional", subject_id="subj:lee_gapsu_003",
        condition_rule_id="mr_sf5_fall_detected", condition_fixed_check_item_id="ci:fall_event",
    )
    _print_result("시나리오 B-1 (Safety·조건등록)", reg_result)
    trig_result = agent_b.trigger_condition(
        reg_result["registration"], subject_id="subj:lee_gapsu_003", target_domain="Safety",
        hour=3, observation_override=True,  # fall_event 감지됨
    )
    _print_result("시나리오 B-2 (조건 트리거 -> 즉시 루프 합류, 기대: escalated_to_human)", trig_result)

    # ---- 시나리오 C: 지식조회 — 박말순, 글리부리드(설포닐우레아) ----
    # 기대값(시나리오 C): IntentKnowledgeLookup, mk_sulfonylurea_avoid에 걸림.
    agent_c = GraphCoTAgent(tool)
    res_c = agent_c.dispatch_intent(
        "글리부리드 계속 먹어도 되나요?", target_domain="WellBeing", needs_action=False,
        subject_id="subj:park_malsun_002",
    )
    _print_result("시나리오 C (지식조회·박말순·글리부리드 기대: mk_sulfonylurea_avoid 매칭)", res_c)

    print("[Comfort는 AGENT_LOOP_AXES라 LLM 클라이언트 없이는 못 돌린다 — 아래는 스킵]")
    print("  agent = GraphCoTAgent(tool, llm_client=anthropic.Anthropic())")
    print("  agent.dispatch_intent('실내 온도 괜찮은지 봐줘', target_domain='Comfort', needs_action=True, execution_timing='immediate', hour=15)")
