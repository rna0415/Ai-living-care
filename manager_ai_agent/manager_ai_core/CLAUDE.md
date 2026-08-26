# Manager AI Core (MAC)

> **역할** L0(자연어) → L1(Intent Query) → L2(High-level Policy)
> **상태** Phase 0 · 부분 구현 — 축 라우팅+결정론 규칙 평가 graph-inference 코어 · 시나리오 2 규칙 정책 · L0→L2 전체는 미구현 · 작업 `0-3`
> **읽을 절** spec **§4.1**(계층 정의) · **§4.2**(L1) · **§4.3**(L2 ECA) — 그 외 절은 열지 않는다
> **정본** 구조 `SOT.md` · spec §4

**Intent Translator + Session Key Manager.** L0(자연어) → L1(Intent Query) → L2(High-level Policy) 변환의 주체.

논문 Fig.1과 slide 17의 표는 `Manager Controller`로 표기 — **별칭으로만 인정**한다 (spec §2.1).

## 구성

| 디렉터리 | 책임 |
|---|---|
| `intent_extraction/` | L0 자연어 → 어구 분해 |
| `kg_mapping/` | 어구 → KG element=value 바인딩 (IF-1) |
| `query_composing/` | 바인딩 → L1 Intent Query JSON |
| `policy_generation/` | L1 → L2 High-level Policy (ECA) |
| `session_key_manager/` | IF-4 세션 키 발급·갱신 (파이프라인과 직교) |

## 파이프라인

```
"Check if Grandma is okay"
  → intent_extraction/     ["Grandma", "check", "is okay"]
  → kg_mapping/            IF-1로 KG 조회 → phrase별 element=value 바인딩
  → query_composing/       L1 Intent Query JSON
  → policy_generation/     LLM + Schema Prompt → L2 ECA XML
```

`session_key_manager/`는 직교하며 IF-4의 세션 키를 발급·갱신한다.
생성된 L2는 `../mcp_client/`가 IF-4로 실어 보낸다.

## 구현된 부분 — graph inference 지원 코어

- `graph_inference.py`: 이미 IF-1 경계에서 해소된 axis context와 실제 관측값을 받아 라우팅→규칙 평가를 조립한다. DB·파일을 직접 읽지 않고, 누락 context/관측값을 mock으로 만들지 않으며, L2 정책 생성 전에 멈춘다. 최상위 `inference_status`와 `complete`로 context·provenance·규칙 판단의 완결성을 드러낸다. 누락이 있어도 실제 escalation 근거는 억제하지 않고 `escalate + complete=false`로 보존한다.
- `test_graph_inference.py`: ROS2·DB·LLM 없이 단일/다중 축 라우팅, 규칙 발화/판단 불가, context·source 누락, 잘못된 규칙·정책·수치 입력을 검증하는 표준 라이브러리 `unittest` 17건.
- 시나리오 2의 `policy_generation/bring_water_policy.py`는 기존 규칙 기반 데모다. 위 graph inference 결과와 아직 연결되지 않았다.

이 코어는 `contracts/intent_query/`와 `contracts/high_level_policy/`가 미작성인 상태에서 내부 추론 근거만 만든다. 출력은 L1 또는 L2 계약이 아니며 Worker로 직접 보내지 않는다.

## 반드시 지킬 것

- **L2에 디바이스 이름을 넣지 않는다.** device-agnostic이어야 다중 Worker fan-out이 성립한다 (spec §4.3).
- **`bindings`를 반드시 남긴다.** 어느 어구가 어떤 값으로 해소됐는지 없으면 오역 디버깅이 불가능하다 (P-5).
- **LLM 실패 경로를 설계에 포함한다** (P-4). 정상 파싱 → 필드 정규화 → 규칙 기반 폴백 3단 구조 권장.

## 작업 (Phase 0)

- [ ] 0-3 L0→L2 파이프라인 전체
- [x] graph inference 지원 코어 — keyword/injected 축 라우팅 + 결정론 규칙 평가 + 사전 해소 context 오케스트레이션
- [ ] LLM 선택 확정 (U-3)
- [ ] L2 직렬화 형식 확정 (U-2 — 내부 JSON / 표준 문서 XML 양방향 변환 권고)
