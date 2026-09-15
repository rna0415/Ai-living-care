"""
sequence_generator.py  —  C3: 로봇 실행 계약(RobotTask) 생성

v3 스키마(2026-08-31, Axis 제거·AxisKnowledge 승격) 대응 — axis_id/axis_label 대신
slot 하나로 통일한다.

역할:
    C2가 내린 판단(should_escalate + 발화 규칙)과 C1이 가져온 기기 정보를 받아,
    Worker가 결정론으로 받아쓸 수 있는 '구조화된 계약(JSON)'을 만든다.
    (예전엔 prose 한 문장 = 블랙박스였음 → 이제 구조화된 계약 = 투명)

핵심 원칙 (tier<=2, 기본 경로):
    - functions(무엇을 할지)는 '규칙'이 이미 정한다 — LLM은 못 고른다(안전).
    - LLM은 그 functions를 자연스러운 한국어 `goal`로 '번역·연결'만 한다.
    - LLM 출력은 반드시 검증한다(functions가 바뀌면 폐기 → 결정론 fallback).

tier>=3 (현재 temperature slot만):
    - LangGraph ReAct 에이전트가 3단계로 계약을 조립한다 — generate_sequence_agentic().
        1) 맥락 검색: graph_tools.py의 읽기 전용 도구를 스스로 반복 호출해
           device/function/규칙(AxisKnowledge)을 조회한다.
        2) 스켈레톤 자연어 생성: 고른 functions를 한국어 문장으로 번역하되, 정책·
           보고조건 문구 자리는 `{{POLICY}}` placeholder로 비워둔 `goal_skeleton`만
           낸다 — LLM이 정책 문구를 직접 지어내지 않게 원천 차단.
        3) 검색된 정책 삽입: 코드가 발화한 rule_id의 rationale을 그래프 원문 그대로
           `{{POLICY}}` 자리에 결정론적으로 삽입해 최종 `goal`을 완성한다
           (_insert_retrieved_policy) — LLM이 아니라 조회 결과가 정책 문구의
           유일한 출처가 되도록 강제하는 추가 그라운딩.
    - 검증 기준이 완화된다: functions가 규칙과 '정확히 일치'가 아니라 device의
      reachable=true function '부분집합'이면 통과(_validate_agentic) — 설계도가
      tier=4에 허용한 "device_knowledge + function node 제약 안에서 LLM이 실제 추론".
    - 주의(2026-08-31 재확인): 이 검증은 "존재/reachable 여부"만 본다. functions의
      순서·조합이 실제로 원하는 시나리오를 만드는지는 검증하지 않는다 — end-to-end
      시나리오 검증은 여전히 없음(별도 과제).
    - 에이전트 실패/검증 실패는 여전히 결정론 템플릿(_fallback_contract)으로 폴백.

출력(C안 계약):
    {
      "device_id":  str | None,
      "functions":  [함수이름, ...],          # tier<=2: 규칙이 정함 / tier>=3: 에이전트가 reachable 범위 내에서 선택
      "goal":       str,                       # LLM(또는 템플릿)이 한국어로 렌더
      "params_hint":{...},
      "report_condition": str | None,
      "grounded_on":{"slot", "rule_id", "rationale"},
      # --- 파이프라인 호환 메타 ---
      "escalate":   bool,
      "source":     "ollama:..|claude:..|ollama:agentic|claude:agentic|rule|mock(..)",
      "intent":     goal 또는 None(구 코드 호환),
      "agent_trace": [{"tool":..,"args":..}, ...]  # tier>=3 에이전트 루프일 때만
    }

백엔드: Ollama(무료) → Claude(유료) → mock. functions가 비면 LLM 안 부르고 결정론 처리.
"""

import os
import json
import urllib.request
import urllib.error

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# 함수 실행 순서 (그래프가 뒤섞어 줘도 여기서 정규화 — Navigate 먼저)
_FUNCTION_ORDER = {"NavigateFunction": 0, "ObserveFunction": 1, "SensingFunction": 2, "TimingFunction": 3}

# device의 reachable function을 전부 넣으면(device가 여러 목적을 겸하는 경우, 예: 로봇이
# 일반 관찰용 Navigate/Observe와 locomotion 전용 TimingFunction을 동시에 가짐) 관련 없는
# slot에도 그 기능이 새어 들어간다(2026-09-01 실증된 버그 — motion 체크에 TimingFunction이
# 끼어듦). 특정 slot에서만 의미 있는 function은 여기 화이트리스트로 제한한다.
# 화이트리스트에 없는 function(Navigate/Observe/Sensing 등 범용)은 모든 slot에서 그대로 허용.
_SLOT_SPECIFIC_FUNCTIONS = {
    "TimingFunction": {"locomotion"},
    "AskQuestionFunction": {"cognition", "psychological", "vision", "hearing"},
}


def _relevant_functions(device: dict, slot: str) -> list[str]:
    names = (f["name"] for f in device.get("functions", []) if f.get("reachable"))
    return [n for n in names
            if n not in _SLOT_SPECIFIC_FUNCTIONS or slot in _SLOT_SPECIFIC_FUNCTIONS[n]]


# ---------------------------------------------------------------------
# few-shot 프롬프트 (LLM에게: functions → 한국어 goal + JSON 조립)
# ---------------------------------------------------------------------
_FEWSHOT_SYSTEM = """너는 로봇 실행 계약(RobotTask)을 조립하는 '포매터'다.
입력으로 '이미 규칙이 결정한' 정보(기기 · 선택된 함수 목록 · 파라미터 힌트 · 판단 근거 · 보고조건)를 받는다.
네 임무는 두 가지뿐이다:
  1. 주어진 함수들을 순서대로 자연스러운 한국어 `goal` 한 문장으로 번역·연결한다.
  2. 아래 JSON 스키마로만 출력한다.

엄수 규칙:
  - functions를 추가·삭제·재정렬하지 마라. 입력 그대로 옮긴다.
  - params_hint·report_condition·grounded_on은 입력 값을 그대로 옮긴다. 지어내지 마라.
  - JSON만 출력한다. 설명·인사·코드펜스 금지.

함수 → 한국어 번역 가이드 (예시에 없는 함수도 이 원칙으로 일반화):
  NavigateFunction → "맵을 켜서 <target>(으)로 이동해 찾고"
  ObserveFunction  → "찾으면 <observe_minutes>분 관찰하고"
  SensingFunction  → "<target> 값을 측정하고"
  그 외 함수 → 함수명의 동사 의미를 살려 간결한 한국어 동작으로.
  report_condition이 있으면 문장 끝을 "<report_condition>"으로 맺는다.

출력 스키마:
{"device_id":<string|null>,"functions":[...],"goal":<string>,"params_hint":<object>,"report_condition":<string|null>,"grounded_on":{"slot":<string>,"rule_id":<string|null>}}

[예시 1 — motion · 로봇 출동]
입력:
{"device_id":"cap:limo_robot_agent","functions":["NavigateFunction","ObserveFunction"],"params_hint":{"target":"할머니","observe_minutes":240},"report_condition":"240분 무동작 시 보고","grounded_on":{"slot":"motion","rule_id":"wb_r1_no_motion_day"}}
출력:
{"device_id":"cap:limo_robot_agent","functions":["NavigateFunction","ObserveFunction"],"goal":"맵을 켜서 할머니를 찾고, 찾으면 240분 관찰하고, 240분 무동작이면 보고","params_hint":{"target":"할머니","observe_minutes":240},"report_condition":"240분 무동작 시 보고","grounded_on":{"slot":"motion","rule_id":"wb_r1_no_motion_day"}}

[예시 2 — temperature · 센서만]
입력:
{"device_id":"cap:temperaturesensor","functions":["SensingFunction"],"params_hint":{"target":"방 온도","threshold_celsius":18},"report_condition":"18도 미만 시 보고","grounded_on":{"slot":"temperature","rule_id":"cf_r1_temp_too_low"}}
출력:
{"device_id":"cap:temperaturesensor","functions":["SensingFunction"],"goal":"방 온도 값을 측정하고, 18도 미만이면 보고","params_hint":{"target":"방 온도","threshold_celsius":18},"report_condition":"18도 미만 시 보고","grounded_on":{"slot":"temperature","rule_id":"cf_r1_temp_too_low"}}

[예시 3 — doorswitch · 로봇 출동, 다른 대상]
입력:
{"device_id":"cap:limo_robot_agent","functions":["NavigateFunction","ObserveFunction"],"params_hint":{"target":"현관","observe_minutes":5},"report_condition":"침입 의심 시 보고","grounded_on":{"slot":"doorswitch","rule_id":"sf_r3_door_open_night"}}
출력:
{"device_id":"cap:limo_robot_agent","functions":["NavigateFunction","ObserveFunction"],"goal":"맵을 켜서 현관으로 이동해 확인하고, 찾으면 5분 관찰하고, 침입 의심 시 보고","params_hint":{"target":"현관","observe_minutes":5},"report_condition":"침입 의심 시 보고","grounded_on":{"slot":"doorswitch","rule_id":"sf_r3_door_open_night"}}

이제 아래 실제 입력을 같은 방식으로 처리해 JSON만 출력하라."""


# ---------------------------------------------------------------------
# 규칙 조회 유틸
# ---------------------------------------------------------------------
def _find_rule(rules: list[dict], rule_id: str) -> dict:
    for r in rules:
        if r.get("rule_id") == rule_id:
            return r
    return {}


def _threshold_phrase(rule: dict) -> str:
    if "threshold_hours" in rule:
        return f"{rule['threshold_hours']}시간"
    if "threshold_minutes" in rule:
        return f"{rule['threshold_minutes']}분"
    if "threshold_celsius" in rule:
        return f"{rule['threshold_celsius']}도"
    return "지정 기준"


def _report_condition(rule: dict, params_hint: dict) -> str | None:
    """규칙에서 보고 조건 문구를 결정론적으로 만든다."""
    if not rule:
        return None
    if "threshold_hours" in rule:
        mins = params_hint.get("observe_minutes")
        return f"{mins}분 무동작 시 보고" if mins else f"{_threshold_phrase(rule)} 무동작 시 보고"
    if "threshold_minutes" in rule:
        return f"{rule['threshold_minutes']}분 초과 시 보고"
    if "threshold_celsius" in rule:
        direction = "미만" if rule.get("direction") == "below" else "초과"
        return f"{rule['threshold_celsius']}도 {direction} 시 보고"
    return "이상 감지 시 보고"


# ---------------------------------------------------------------------
# ① decision 조립 — 규칙 결과에서 계약 입력을 만든다 (결정론, LLM 아님)
# ---------------------------------------------------------------------
def _build_decision(slot: str, evaluation: dict, device: dict | None,
                    rules: list[dict], target: str) -> dict:
    top = evaluation["triggered_rules"][0] if evaluation.get("triggered_rules") else {}
    rule = _find_rule(rules, top.get("rule_id", "")) if top else {}

    # 에스컬레이션 불필요 or 대응 기기 없음 → 함수 없는(빈) 계약
    if not evaluation.get("should_escalate") or device is None:
        return {
            "device_id": None,
            "functions": [],
            "params_hint": {},
            "report_condition": None,
            "grounded_on": {"slot": slot, "rule_id": top.get("rule_id"),
                            "rationale": top.get("rationale")},
        }

    # 기기의 함수를 규칙 순서로 정규화 (Navigate → Observe → Sensing).
    # reachable=false인 function은 애초에 후보에서 뺀다 — device fallback(select_goal_
    # device)이 이미 "reachable한 function이 있는 device"만 골라 넘기지만, 그 device가
    # reachable=true/false function을 섞어 갖고 있을 수도 있어 여기서도 한 번 더 거른다.
    functions = sorted(_relevant_functions(device, slot), key=lambda n: _FUNCTION_ORDER.get(n, 9))
    params_hint = {"target": target}
    if "threshold_hours" in rule:
        params_hint["observe_minutes"] = rule["threshold_hours"] * 60
    if "threshold_celsius" in rule:
        params_hint["threshold_celsius"] = rule["threshold_celsius"]

    return {
        "device_id": device["device_id"],
        "functions": functions,
        "params_hint": params_hint,
        "report_condition": _report_condition(rule, params_hint),
        "grounded_on": {"slot": slot, "rule_id": top.get("rule_id"),
                        "rationale": top.get("rationale")},
    }


# ---------------------------------------------------------------------
# ② goal 렌더링 — 결정론 템플릿 (LLM fallback / 검증 실패 시)
# ---------------------------------------------------------------------
def _render_goal_template(decision: dict) -> str:
    functions = decision["functions"]
    if not functions:
        return "특별한 조치가 필요하지 않습니다"
    ph = decision["params_hint"]
    target = ph.get("target", "대상")
    mins = ph.get("observe_minutes")
    parts = []
    if "NavigateFunction" in functions:
        parts.append(f"맵을 켜서 {target}을(를) 찾고")
    if "ObserveFunction" in functions:
        parts.append(f"찾으면 {mins}분 관찰하고" if mins else "찾으면 관찰하고")
    if "SensingFunction" in functions:
        parts.append(f"{target} 값을 측정하고")
    # 위 셋에 없는 함수는 이름 그대로라도 넣어준다 (일반화)
    for fn in functions:
        if fn not in ("NavigateFunction", "ObserveFunction", "SensingFunction"):
            parts.append(f"{fn} 수행하고")
    if decision.get("report_condition"):
        parts.append(decision["report_condition"])
    return ", ".join(parts)


def _fallback_contract(decision: dict) -> dict:
    """LLM 없이 계약을 완성 (goal은 템플릿)."""
    return {**decision, "goal": _render_goal_template(decision)}


# ---------------------------------------------------------------------
# ③ LLM 호출 (Ollama / Claude) — few-shot으로 goal + JSON 조립
# ---------------------------------------------------------------------
def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1] if "```" in t[3:] else t.lstrip("`")
        t = t.replace("json", "", 1).strip()
    # 첫 { 부터 마지막 } 까지만
    if "{" in t and "}" in t:
        t = t[t.index("{"): t.rindex("}") + 1]
    return t


def _call_ollama(decision: dict, system: str = _FEWSHOT_SYSTEM) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": json.dumps(decision, ensure_ascii=False)}],
        "stream": False,
        "options": {"temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["message"]["content"]


def _call_claude(decision: dict, system: str = _FEWSHOT_SYSTEM) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL, max_tokens=1024, system=system,
        messages=[{"role": "user", "content": json.dumps(decision, ensure_ascii=False)}],
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


def _ollama_available() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1.5)
        return True
    except Exception:
        return False


def _choose_backend() -> str:
    forced = os.environ.get("LLM_BACKEND")
    if forced:
        return forced
    if _ollama_available():
        return "ollama"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return "mock"


# ---------------------------------------------------------------------
# ④ 검증 — LLM이 함수를 바꿨는지 확인 (블랙박스 방지)
# ---------------------------------------------------------------------
def _validate(contract: dict, decision: dict):
    if contract.get("functions") != decision["functions"]:
        raise ValueError(f"LLM이 functions를 변경함: {contract.get('functions')} != {decision['functions']}")
    if not contract.get("goal"):
        raise ValueError("goal 비어있음")


# ---------------------------------------------------------------------
# ⑤ tier>=3 에이전트 루프 — LangGraph ReAct 에이전트가 도구 호출을 스스로 반복한다
#    tier<=2는 위 _validate()처럼 "규칙이 정한 functions와 정확히 일치"해야 통과하지만,
#    여기서는 "device의 reachable=true function 집합의 부분집합"이면 통과한다 — 설계도가
#    tier=4에 허용한 "device_knowledge + function node 제약 안에서 LLM이 실제 추론"을
#    그대로 구현한 것. (이 검증이 시나리오 정확성까지 보장하진 않음 — 파일 상단 참조)
# ---------------------------------------------------------------------

_POLICY_PLACEHOLDER = "{{POLICY}}"

_AGENTIC_SYSTEM = """너는 tier=4(resilient) slot을 위한 로봇 실행 계약(RobotTask) 조립 에이전트다.
규칙 판단(rule_evaluator)이 이미 "에스컬레이션이 필요한가"를 결정해 evaluation으로
넘겨줬다 — 그 판단 자체를 네가 다시 내리지 마라. 네 일은 세 단계다:

  1. 맥락 검색: 도구(search_devices_for_slot, check_function_reachable,
     get_device_knowledge, search_axis_knowledge)로 이 slot의 device·function·
     판단규칙(AxisKnowledge)을 확인한다. 실제로 reachable=true인 function만 골라
     functions 목록을 만든다 — reachable=false이거나 존재하지 않는 function은 절대
     넣지 마라. evaluation에서 이미 발화한 규칙의 rule_id를 search_axis_knowledge
     결과에서 찾아 확인한다.

  2. 스켈레톤 자연어 생성: 고른 functions를 자연스러운 한국어 문장으로 번역·연결한
     `goal_skeleton`을 만든다. 문장에서 정책·보고조건이 들어갈 자리는 네가 문구를
     쓰지 말고 `{{POLICY}}`라는 자리표시자 하나로 정확히 한 번만 남겨라 — 실제 정책
     문구(rationale)는 네가 지어내면 안 되고, 다음 단계에서 그래프 조회 원문이
     그대로 그 자리에 삽입된다.

  3. 아래 JSON 스키마로만 최종 답을 낸다 — 설명·인사·코드펜스 금지, 도구 호출이 다
     끝난 마지막 턴에서 이 JSON 하나만 출력한다:
{"device_id":<string|null>,"functions":[...],"goal_skeleton":<string, "{{POLICY}}" 정확히 1번 포함>,"params_hint":<object>,"grounded_on":{"slot":<string>,"rule_id":<string, search_axis_knowledge로 확인한 실제 rule_id>}}

[예시 — motion, 로봇 출동]
functions=["NavigateFunction","ObserveFunction"], target="할머니", observe_minutes=240
goal_skeleton 예: "맵을 켜서 할머니를 찾고, 찾으면 240분 관찰하고, {{POLICY}}"
(정책 문구 "240분 무동작 시 보고"는 네가 쓰지 않는다 — 3단계에서 삽입됨)
"""


def _get_chat_model(backend: str):
    if backend == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_URL, temperature=0.2)
    if backend == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=MODEL, temperature=0.2)
    raise RuntimeError(f"'{backend}' 백엔드는 에이전트 루프를 지원하지 않음(mock)")


def _validate_agentic(contract: dict, retriever, slot: str):
    """functions가 '규칙과 정확히 일치'가 아니라 '선택한 device의 reachable function
    부분집합'인지만 검증한다 — tier>=3의 완화된 그라운딩 기준. (순서/시나리오
    정확성은 검증 범위 밖 — 파일 상단 주의 참조)
    goal_skeleton은 {{POLICY}} placeholder를 정확히 1번 담아야 한다 — LLM이 정책
    문구를 직접 쓰지 않았다는 걸 구조적으로 확인하는 절차(3단계 삽입의 전제)."""
    skeleton = contract.get("goal_skeleton")
    if not skeleton:
        raise ValueError("goal_skeleton 비어있음")
    if skeleton.count(_POLICY_PLACEHOLDER) != 1:
        raise ValueError(
            f"goal_skeleton에 {_POLICY_PLACEHOLDER}가 정확히 1번 있어야 함: {skeleton!r}"
        )
    devices = retriever.fetch_knowledge_context(slot)["devices"]
    reachable = {
        d["device_id"]: {f["name"] for f in d.get("functions", []) if f.get("reachable")}
        for d in devices
    }
    functions = contract.get("functions") or []
    allowed = reachable.get(contract.get("device_id"), set())
    if not set(functions) <= allowed:
        raise ValueError(
            f"에이전트가 reachable=false/존재하지 않는 function을 선택함: "
            f"{functions} not subset of {sorted(allowed)}"
        )


def _find_rule_rationale(rules: list[dict], rule_id: str | None) -> str | None:
    for r in rules:
        if r.get("rule_id") == rule_id:
            return r.get("rationale")
    return None


def _insert_retrieved_policy(skeleton: str, rules: list[dict], rule_id: str | None) -> str:
    """3단계: 검색된 정책(rationale) 삽입 — rule_id로 찾은 rationale을 그래프 원문
    그대로 {{POLICY}} 자리에 끼워 최종 goal을 만든다. 결정론(LLM 아님) — 정책 문구의
    유일한 출처가 그래프 조회 결과가 되도록 강제한다. rationale을 못 찾으면 자리표시자만
    지우고 문장을 이어 붙인다(안 터짐)."""
    rationale = _find_rule_rationale(rules, rule_id)
    if _POLICY_PLACEHOLDER not in skeleton:
        return skeleton
    if not rationale:
        return skeleton.replace(_POLICY_PLACEHOLDER, "").rstrip(", ").rstrip("、").strip()
    return skeleton.replace(_POLICY_PLACEHOLDER, rationale)


def generate_sequence_agentic(slot: str, evaluation: dict, rules: list[dict],
                              hour: int | None, target: str, retriever, decision: dict,
                              backend: str, max_iterations: int = 6) -> dict:
    """tier>=3 전용. LangGraph의 prebuilt ReAct 에이전트에 graph_tools.py의 읽기 전용
    도구를 묶어 실행한다 — 에이전트가 "어떤 도구를 몇 번 부를지"를 스스로 정하는
    '루프'가 여기서 돈다. 실패하면(백엔드 에러/검증 실패) 결정론 템플릿으로 폴백한다."""
    from langgraph.prebuilt import create_react_agent
    from graph_tools import build_graph_tools  # kg_mapping/ — pipeline.py가 sys.path에 이미 추가

    try:
        tools = build_graph_tools(retriever)
        model = _get_chat_model(backend)
        agent = create_react_agent(model, tools)

        user_payload = {
            "slot": slot, "hour": hour, "target": target,
            "evaluation": evaluation, "device_hint": decision,
        }
        result = agent.invoke(
            {"messages": [("system", _AGENTIC_SYSTEM),
                          ("user", json.dumps(user_payload, ensure_ascii=False))]},
            {"recursion_limit": max_iterations * 2},
        )
        messages = result["messages"]
        agent_trace = [
            {"tool": call["name"], "args": call["args"]}
            for m in messages if getattr(m, "tool_calls", None)
            for call in m.tool_calls
        ]
        contract = json.loads(_strip_fences(messages[-1].content))
        _validate_agentic(contract, retriever, slot)

        # 3단계: 검색된 정책 삽입 — goal_skeleton의 {{POLICY}} 자리에 grounded_on.rule_id
        # 로 찾은 rationale을 결정론적으로 끼워 최종 goal을 만든다(LLM이 아니라 그래프
        # 조회 원문이 정책 문구의 유일한 출처).
        skeleton = contract.pop("goal_skeleton")
        grounded_rule_id = (contract.get("grounded_on") or {}).get("rule_id")
        contract["goal"] = _insert_retrieved_policy(skeleton, rules, grounded_rule_id)
        contract.setdefault("grounded_on", {})
        contract["grounded_on"].setdefault("slot", slot)
        contract["grounded_on"]["rationale"] = _find_rule_rationale(rules, grounded_rule_id)

        contract["agent_trace"] = agent_trace
        return _finalize(contract, decision, evaluation, f"{backend}:agentic")
    except Exception as e:
        fallback = _fallback_contract(decision)
        fallback["agent_trace"] = []
        return _finalize(fallback, decision, evaluation,
                         f"mock({backend} agentic 실패: {str(e)[:40]})")


def _finalize(contract: dict, decision: dict, evaluation: dict, source: str) -> dict:
    """계약에 파이프라인 호환 메타(escalate/source/intent)를 붙여 마무리."""
    contract.setdefault("grounded_on", decision["grounded_on"])
    contract["escalate"] = bool(evaluation.get("should_escalate"))
    contract["source"] = source
    # 실제 로봇 동작(함수)이 있을 때만 intent 채움 — 없으면 파이프라인이 딴 분기 타게
    contract["intent"] = contract.get("goal") if contract.get("functions") else None
    return contract


# ---------------------------------------------------------------------
# 응급/보호자 메시지 조립 — call_emergency_services·notify_caregiver 전용.
# C3(로봇 goal)와 같은 원칙(skeleton 생성 + {{POLICY}} 결정론 삽입)을 "문장을 만드는"
# 컴포넌트에만 적용한 것 — 검색·판단·검증 단계엔 애초에 채울 빈칸이 없어 이 패턴이
# 안 붙는다(대화 결론). LLM은 어조/구조만 만들고, 사실관계(rule_id·rationale)는
# 여전히 그래프 조회 결과가 유일한 출처.
# ---------------------------------------------------------------------
_EMERGENCY_MESSAGE_SYSTEM = """너는 노인돌봄 시스템이 119 또는 보호자에게 보낼 알림
메시지를 조립하는 '포매터'다. 상황 판단(rule_evaluator)은 이미 끝났다 — 다시 판단하지
마라. 네 일은 두 가지뿐이다:
  1. 침착하고 명확한 한국어 문장으로 상황을 요약하되, 구체적 근거 문구(수치·임계값·
     rationale)가 들어갈 자리는 네가 쓰지 말고 {{POLICY}} 자리표시자 정확히 1번으로
     남겨라 — 그 문구는 다음 단계에서 그래프 조회 원문 그대로 삽입된다.
  2. 아래 JSON 스키마로만 출력한다. 설명·인사·코드펜스 금지.

출력 스키마: {"message_skeleton": "...{{POLICY}}..."}

[예시] 입력: {"slot":"heartrate","target":"할머니","severity":"concern","action_type":"call_emergency_services"}
출력: {"message_skeleton": "할머니 심박수에 이상이 감지되어 신고합니다. {{POLICY}} 빠른 확인 부탁드립니다."}
"""


def generate_emergency_message(slot: str, evaluation: dict, target: str = "할머니",
                               action_type: str = "call_emergency_services") -> dict:
    """call_emergency_services/notify_caregiver 메시지를 skeleton+정책삽입으로 조립.
    LLM이 없거나(mock) 실패하면 grounded rationale을 그대로 문장에 붙이는 결정론
    템플릿으로 안전하게 대체한다 — goal 생성과 동일한 폴백 원칙."""
    top = evaluation["triggered_rules"][0] if evaluation.get("triggered_rules") else {}
    fallback_message = top.get("rationale") or "이상이 감지되었습니다."

    backend = _choose_backend()
    if backend == "mock" or not top.get("rule_id"):
        return {"message": fallback_message, "source": "template"}

    payload = {"slot": slot, "target": target, "severity": top.get("severity"),
              "action_type": action_type}
    try:
        if backend == "ollama":
            raw = _call_ollama(payload, system=_EMERGENCY_MESSAGE_SYSTEM)
        else:
            raw = _call_claude(payload, system=_EMERGENCY_MESSAGE_SYSTEM)
        parsed = json.loads(_strip_fences(raw))
        skeleton = parsed["message_skeleton"]
        if skeleton.count(_POLICY_PLACEHOLDER) != 1:
            raise ValueError(f"{_POLICY_PLACEHOLDER}가 정확히 1번 있어야 함: {skeleton!r}")
        message = _insert_retrieved_policy(skeleton, [top], top["rule_id"])
        return {"message": message, "source": f"{backend}:message"}
    except Exception as e:
        return {"message": fallback_message, "source": f"mock({backend} 실패: {str(e)[:40]})"}


# ---------------------------------------------------------------------
# 공개 API — slot 하나로 통일(axis_id/axis_label 제거). target/tier/hour/retriever는 선택 인자.
# ---------------------------------------------------------------------
def generate_sequence(slot: str, evaluation: dict, device: dict | None,
                      rules: list[dict], target: str = "할머니", tier: int = 4,
                      hour: int | None = None, retriever=None) -> dict:
    """
    판단 결과 → 로봇 실행 계약(C안).
    target: 대상(예: "할머니"). 지금은 기본값/mock — 나중에 의도추출·KG로 교체(TODO 확인 필요).

    tier(1~4, 기본 4): 호출부(pipeline.py)가 slot의 tier를 넘긴다.
      - tier<=2: 아래 결정론 단발 LLM 경로(기존 동작 그대로) — functions는 규칙과
        정확히 일치해야 통과(_validate). LLM 호출/검증 실패 시 템플릿 폴백.
      - tier>=3: LLM 백엔드가 있고 retriever가 넘어왔으면
        generate_sequence_agentic()으로 위임 — 에이전트가 도구 호출을 스스로 반복하는
        루프. functions는 device의 reachable function 부분집합이면 통과(_validate_
        agentic, 완화된 그라운딩). mock 백엔드이거나 retriever가 없으면 tier와
        무관하게 안전하게 결정론 경로로 떨어진다.
    """
    decision = _build_decision(slot, evaluation, device, rules, target)

    # 함수가 없으면(조치 불필요/로봇 없음) LLM 안 부르고 결정론 처리 — 모든 tier 공통
    if not decision["functions"]:
        return _finalize(_fallback_contract(decision), decision, evaluation, "rule")

    backend = _choose_backend()

    if tier >= 3 and backend != "mock" and retriever is not None:
        return generate_sequence_agentic(slot, evaluation, rules, hour,
                                          target, retriever, decision, backend)

    try:
        if backend == "ollama":
            raw, source = _call_ollama(decision), f"ollama:{OLLAMA_MODEL}"
        elif backend == "claude":
            raw, source = _call_claude(decision), f"claude:{MODEL}"
        else:
            raise RuntimeError("mock")
        contract = json.loads(_strip_fences(raw))
        _validate(contract, decision)             # 함수 안 바꿨는지 검증
    except Exception as e:
        # LLM 실패/검증 실패 → 결정론 템플릿으로 안전하게 대체
        contract = _fallback_contract(decision)
        source = f"mock({backend} 실패: {str(e)[:40]})"

    return _finalize(contract, decision, evaluation, source)


# ---------------------------------------------------------------------
# 단독 실행 데모
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지
    except Exception:
        pass
    demo_device = {
        "device_id": "cap:limo_robot_agent",
        "functions": [{"name": "ObserveFunction"}, {"name": "NavigateFunction"}],
    }
    demo_eval = {
        "should_escalate": True,
        "triggered_rules": [{"rule_id": "wb_r1_no_motion_day", "severity": "concern",
                             "rationale": "주간 4시간 무동작이면 우려"}],
    }
    demo_rules = [{"rule_id": "wb_r1_no_motion_day", "slot": "motion",
                   "time_context": "day", "threshold_hours": 4, "severity": "concern"}]

    print("=== 백엔드:", _choose_backend(), "===")
    result = generate_sequence("motion", demo_eval, demo_device, demo_rules, target="할머니")
    print(json.dumps(result, ensure_ascii=False, indent=2))
