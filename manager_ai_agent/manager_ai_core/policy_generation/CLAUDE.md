# High-level Policy Generation

> **역할** L1 → L2 ECA 정책. **device-agnostic 이어야 fan-out 이 성립한다**
> **상태** Phase 0 · 부분 구현 — 시나리오 2 `bring_water_policy.py` + 결정론 `rule_evaluator.py` · 범용 L1→L2 생성 미구현 · 미결정 `U-2` `U-3`
> **읽을 절** spec **§4.3**(L2 ECA XML) — 그 외 절은 열지 않는다
> **정본** 구조 `SOT.md` · spec §4.3

L1 + Schema Prompt를 LLM에 넣어 **L2 High-level Policy (ECA XML)** 를 생성한다.

Phase 0 데모 구현 `bring_water_policy.py`는 "물 갖다줘" 요청을 실제 물체 조작으로
과장하지 않고 `navigation-rehearsal` L2 내부 JSON 정책으로 생성한다.

`rule_evaluator.py`는 graph context의 임계값 규칙과 관측값을 결정론적으로 비교한다. 누락 관측은
정상으로 간주하지 않고 `evaluation_status=indeterminate`와 `indeterminate_rules`로 반환한다. 빈 규칙
집합도 정상 근거가 아니므로 `indeterminate`다. 각 규칙은 비어 있지 않은 `rule_id`, 알려진 severity와
day/night 문맥, 정확히 한 개의 predicate를 가져야 하며, 임계값·관측 수치는 유한한 실수여야 한다.
`immediate`·`condition` predicate의 관측값은 boolean이어야 한다.
위반 규칙은 발화 여부를 보기 전에 `unsupported_rules`로 분리한다. escalation policy의 두 임계값은
양의 정수만 허용하며, 이는 graph data가 아니라 호출자 설정 오류이므로 예외로 거부한다.
이 결과는 정책 생성의 근거이며 자체가 L2 정책은 아니다.

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
