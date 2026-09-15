# High-level Policy Generation

> **역할** L1 → L2 ECA 정책. **device-agnostic 이어야 fan-out 이 성립한다**
> **상태** Phase 0 · 미착수(정본 L1→L2) · 미결정 `U-2` `U-3` · **실험 코드 있음(아래, 미승인)**
> **읽을 절** spec **§4.3**(L2 ECA XML) — 그 외 절은 열지 않는다
> **정본** 구조 `SOT.md` · spec §4.3

L1 + Schema Prompt를 LLM에 넣어 **L2 High-level Policy (ECA XML)** 를 생성한다.

스키마: `contracts/high_level_policy/`

```xml
<living-care-policy>
  <policy-id/> <intent-id/> <policy-name/> <issued-by/> <issued-at/>
  <rule>
    <rule-name/>
    <event><event-type/><trigger/></event>
    <condition><target-role/><place/><modality/></condition>
    <action><action-type/><required-skill/>…<dispatch-mode/></action>
  </rule>
  <assurance><deadline-sec/><report-mode/><escalation-on/></assurance>
</living-care-policy>
```

## 반드시 지킬 것

- **디바이스 이름 금지** (P-2). `<required-skill>`이 Worker 선택의 유일한 기준이다.
- **`<assurance>`를 비우지 않는다.** `not_found`·`timeout` 후속 액션이 여기서 선언적으로 정해진다.
- **스키마 검증 실패 출력은 정책으로 승격하지 않는다** (P-4). 재생성 → 폴백 → 사용자 확인 순.

## 주의

Ollama를 쓸 경우 `format: "json"`으로 출력 형식을 강제할 수 있다.
LLM 실패 폴백 설계는 `docs/audit/IETF승계issue.md` §4.1 참조 (참고 자료, 미채택).

## 실험 코드 — `rule_evaluator.py` · `sequence_generator.py` (실험 · 미승인)

2026-08-18에 옛 `manager_ai_agent/graph_inference/`를 폐기하고 여기로 옮겼다
(`docs/decisions/2026-08-18-graph-inference-distribution.md`). 위 정본 스키마(L1 JSON →
L2 ECA XML)를 아직 안 쓴다 — **자체 내부 dict 모양**으로 판단·생성한다.

- `rule_evaluator.py` — C2. `../kg_mapping/graph_retrieval.py`가 가져온 규칙(threshold 등)과
  관측값을 비교해 `should_escalate`를 결정한다. **100% 결정론적 코드**이며 LLM을 쓰지 않는다.
  이 결과가 정본 `<condition>`·`<assurance><escalation-on>`에 대응될 후보다.
- `sequence_generator.py` — C3. 2026-08-19에 "자연어 한 문장 조립"에서 **구조화된 실행
  계약(RobotTask) 생성**으로 바뀌었다. 출력:
  `{device_id, functions, goal, params_hint, report_condition, grounded_on, escalate, source, intent}` —
  `functions`(무엇을 할지)는 규칙이 이미 정하고(`_build_decision`, 100% 결정론), **LLM은 그
  functions를 한국어 `goal` 한 문장으로 번역·연결만 한다**(few-shot 프롬프트). `_validate`가
  LLM 출력의 `functions`가 입력과 다르면 통째로 버리고 결정론 템플릿(`_render_goal_template`)
  으로 폴백한다 — LLM이 새 판단·기능을 지어낼 수 없게 하는 검증 게이트. 백엔드 우선순위는
  그대로: `LLM_BACKEND` 강제 지정 → 로컬 Ollama → `ANTHROPIC_API_KEY` 있으면 Claude → 없으면
  mock(이 경우 LLM 자체를 안 부르고 템플릿만 씀). `target`(대상, 기본값 "할머니") 인자가
  추가됐다 — 아직 mock이고 의도추출·KG로 교체 예정(TODO 확인 필요). 이 RobotTask 산출물을
  정본 L2 ECA XML `<action>`으로 어떻게 승격할지는 여전히 TODO(확인 필요) — 다만 이제
  `functions`가 `<required-skill>` 후보에, `params_hint`가 `<condition>` 후보에 더 가깝다.

**tier 분기·에이전트 루프(2026-08-24 추가)**: `generate_sequence()`에 `tier: int = 4`,
`axis_id`·`hour`·`retriever`(선택) 인자가 추가됐다. tier<=2는 기존 결정론 단발 LLM
경로 그대로(`_validate`가 functions 정확 일치를 요구). tier>=3(현재 Comfort만)은 LLM
백엔드가 있고 axis_id·retriever가 넘어오면 `generate_sequence_agentic()`으로 위임 —
`langgraph.prebuilt.create_react_agent`가 `kg_mapping/graph_tools.py`의 읽기 전용
도구(+ 이 규칙 판단을 감싼 `evaluate_axis_rules`)를 스스로 반복 호출하는 루프다.
검증 기준도 갈린다: tier>=3은 `_validate_agentic`이 "functions가 규칙과 정확히
일치"가 아니라 "선택한 device의 reachable=true function 부분집합"인지만 확인한다 —
설계도가 tier=4에 허용한 "device_knowledge + function node 제약 안에서 LLM이 실제
추론"의 구현. 에이전트/검증 실패는 여전히 `_fallback_contract()`로 안전하게 폴백.
`_build_decision()`은 이제 `device['functions']`에서 `reachable=true`인 것만
골라 쓴다(전엔 무조건 전부 사용 — 버그 수정).

실행법·의존성은 `../CLAUDE.md`의 「Neo4j 추론 파이프라인」참조.

## `checkin_agent.py` (실험·미승인)

ICOPE Step1 자가보고 도메인(cognition/psychological/vision/hearing — 센서로 못 재고 물어봐야
아는 값이라 실행 로직이 없던 부분)을 자연스러운 대화 질문으로 건네는 컴포넌트.
`sequence_generator.py`의 `goal_skeleton`+`{{POLICY}}` 패턴을 재사용한다: LLM은 그래프의
`ScreeningKnowledge`(WHO ICOPE 표준 문항) 원문을 의역하지 않고 `{{QUESTION}}` 자리표시자에
그대로 삽입한다 — 검증된 스크리닝 도구 문구를 LLM이 바꾸면 그 도구의 민감도/특이도가
깨지기 때문.
