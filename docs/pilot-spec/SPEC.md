# 파일럿 명세 v0.1 — A·B·C 공통 계약

> 이 문서는 세 사람이 서로의 산출물을 쓰기 위해 **먼저 맞춰 두는 약속**이다. 코드가 아니라 형식과 이름을 정한다.
> 바꾸려면 B(정경훈)와 상의한다. 모든 예시 값은 형식을 보이기 위한 것이다.

## 1. 목적과 범위

- 측정 대상: **분해된 발화 → Rule JSON** 번역이 정답에 맞는가. 범위는 검색 → 생성 → 검증 → 배정까지.
- 범위 밖: A2A 전송과 MCP 호출, Neo4j 적재, 발화 분해기(입력은 사람이 분해해 둔 어구).
- 평가 발화는 30개(정상 20 · 모호 5 · 무효 5). 먼저 **스모크 테스트**(발화 8개)로 파이프라인과 데이터를 점검한 뒤 30개를 동결해 돌린다.
- 모든 결과 수치에는 한정어를 붙인다: "파일럿, 합성 발화 30개, 모델명, 그래프 스냅샷. 설계 검증용이며 일반화의 근거가 아님."

## 2. 누가 무엇을 내는가

| 사람 | 산출물 | 위치 |
|---|---|---|
| **C** | LIMO TD, 공장 TD, 장소 파일, 스모크 발화 8개와 라벨, (이후) 파일럿 발화 30개와 라벨 | `data/limo-1.td.json` · `data/factory.td.json` · `data/places.json` · `data/gold_smoke.jsonl` · `data/gold_pilot.jsonl` |
| **A** | 그래프 로더(§7), 채점 스크립트 | `pilot/graph_loader.py` · `pilot/score.py` |
| **B** | Rule 스키마, 파이프라인(검색·생성·검증·배정), 실행 스크립트, LLM mock | `pilot/pipeline/` |

`data/`와 `pilot/` 경로는 레포의 새 브랜치 안에서 쓸 자리이고, 브랜치 이름은 팀이 정한다. 이 문서의 `templates/`가 각 파일의 형식 예시다.

## 3. 동결된 결정

| 항목 | 결정 |
|---|---|
| Rule JSON 범위 | event는 `user-request`만. 조건은 장소 지정(`geographic-location.destination`)만. 슬롯은 `motion-action` · `perception-action` · `control-action` · `report-action`. 조건부 발화(배터리·시간 등)는 이번 파일럿에서 제외하고 한정어에 적는다 |
| `control-action` | `{step, action-type, target[], args}`. `target`은 대상 **기기** ID이고 생략하면 "대상 미지정"이다 |
| identity 표기 | LLM 출력과 gold 모두 **접두사 없이** `navigate-to`. YANG의 `iot-intent-capability:` 접두사는 저장·변환 시 후처리로 붙인다 |
| 발화 범위 | 단일 요청 위주. 순차 2단계까지 허용 |
| 그래프 구조 | **Function 층 없음.** Device가 Action·Property·Event를 직접 가진다 |
| 고정값 | 모델명·임베딩 모델은 B가 정해 알린다. temperature 0, 재시도 1회(스모크). 파일럿은 재시도 횟수를 따로 정해 기록한다 |

## 4. Rule JSON (LLM이 만드는 것)

정식 정의는 `rule.schema.json`이다. 모양:

```json
{
  "name": "check-person-in-kitchen",
  "event": { "request-event": ["user-request"] },
  "condition": { "geographic-location": { "destination": ["kitchen"] } },
  "action": {
    "motion-action":     [{ "step": 1, "action-type": "navigate-to", "destination": ["kitchen"] }],
    "perception-action": [{ "step": 1, "action-type": "detect-objects", "object-class": ["person"] }],
    "report-action":     ["report-result"]
  }
}
```

- `action-type`, `object-class`는 **Identity ID**(`vocab.json`), `destination`은 **장소 ID**(`places.json`), `target`은 **기기 ID**(TD의 `title`)다.
- LLM은 이 안의 값을 **검색이 준 후보 안에서만** 고른다.
- **실행 순서 관례:** 슬롯 순서 motion → control → perception → report, 같은 슬롯 안에서는 `step` 순서. 채점은 이 관례를 따른다.
- 판정(`execute` / `ask-clarification` / `reject`)은 LLM이 내지 않고 파이프라인이 정한다(§9).

## 5. TD 작성 규칙 (C)

형식 예시: `templates/example-lamp.td.json`. 이 파일은 일반 예시이고 LIMO·공장 내용이 아니다. TD 1.1의 부분집합이며 `forms`와 `security`는 파일럿에서 생략한다(W3C TD 검증기로는 통과하지 않는다).

**기기 수준**
- `title`: 기기 ID. 파일 안에서 유일해야 하고 `target`에 쓰인다.
- `@type`: `id:`로 시작하는 기기 종류(`vocab.json`의 DeviceType 아래).
- `description`: **한국어**로 이 기기가 무엇이고 어디에 쓰이는지 한 문장 이상.
- `aliases`: 사람이 부를 만한 한국어 이름들(확장 필드).
- `location`: 기기가 있는 장소 ID(`places.json`의 `id`, 확장 필드).

**동작·속성·이벤트 수준** (`actions`, `properties`, `events`)
- 모든 항목에 `@type`(`id:` + `vocab.json`의 이름)과 **한국어 `description`**을 쓴다. 검색은 이 설명으로 노드를 찾는다.
- 모든 action에 `input` 스키마가 필요한 만큼 있어야 한다. 값이 있는 인자는 `type`, `minimum`/`maximum` 또는 `enum`, 필수 여부(`required`)를 적는다. 입력이 없는 동작은 `input`을 생략한다.
- `@type`에 쓸 새 Identity가 필요하면 `vocab.json`에 **기존 부모 아래로 먼저 추가**하고 B에게 알린다.

**도메인 구성 (공장 TD 권장)**
- 같은 `@type` 동작을 가진 기기가 **2개 이상**(모호 발화를 만들기 위함).
- 값 범위가 있는 인자 1개 이상.
- 로봇 쪽 기기 1대 이상. 어떤 TD에도 없는 능력도 알고 있어야 한다(무효 발화용).

## 6. 장소 파일 (C)

형식 예시: `templates/places.example.json`. 장소마다 `id`, **한국어 `aliases`**(주방 / 부엌처럼), `pose`(없으면 `null`). 발화의 장소 이름은 `aliases`로 `id`에 연결된다.

## 7. 그래프 인터페이스 (A와 B)

함수 이름과 입출력은 `graph_interface.md`. A가 구현하고 B는 같은 인터페이스를 따르는 mock 픽스처로 먼저 개발한다.

## 8. 라벨과 결과 형식

**`gold.jsonl`** (C): 한 줄에 발화 하나. 형식 예시 `templates/gold.example.jsonl`.

| 필드 | 설명 |
|---|---|
| `id`, `utterance` | 발화 ID와 원문 |
| `phrases` | 사람이 분해한 어구 목록(어간형으로 통일) |
| `label` | `normal` / `ambiguous` / `invalid` |
| `gold_verdict` | `execute` / `ask-clarification` / `reject` (label과 1:1) |
| `gold_rule` | normal만. 슬롯별 기대 Rule(§4의 `action` 부분) |
| `gold_candidates` | ambiguous만. 후보 기기 ID 목록 |
| `invalid_reason` | invalid만. `nonexistent-device` / `nonexistent-place` / `nonexistent-action` |

- 라벨은 **TD와 장소 파일을 확정한 뒤** 달고, TD를 고치면 라벨도 다시 확인한다.
- 정상은 하나로 정해지는 발화, 모호는 같은 동작을 가진 기기가 둘 이상이고 대상 지정이 없는 발화, 무효는 그래프에 없는 기기·장소·동작을 요구하는 발화다.
- 파일럿 30개는 두 사람이 독립 라벨링 후 합의한 다음 동결한다.

**`results.jsonl`** (B가 남김, A가 채점): 형식 예시 `templates/results.example.jsonl`. 검증 **전**의 `raw_llm_output`을 반드시 남긴다(환각률 계산용).

## 9. 검증과 배정 (B)

검증은 네 가지를 순서대로 확인하고 처음 실패한 검사를 `first_failed_check`에 적는다.

| 검사 | 값 | 확인하는 것 |
|---|---|---|
| 스키마 | `schema` | `rule.schema.json` 구조·타입·범위 (정적) |
| 참조 해소 | `reference` | `action-type`·`object-class`가 어휘에 있고 어떤 기기가 제공하는가, `destination`이 장소에 있는가, `target`이 기기인가 |
| 슬롯 종류 | `slot` | `action-type`의 조상 클래스가 들어 있는 슬롯과 맞는가 |
| 인자 | `args` | `args` 값이 TD의 `input` 스키마를 만족하는가 |

배정은 검증을 통과한 Rule에서 정한다.
- 필요한 동작을 가진 기기가 **1개** → `execute`
- **2개 이상**(그리고 `target`/`destination`으로 좁혀지지 않음) → `ask-clarification`
- **0개**, 또는 검증 실패 → `reject`(default-action)

## 10. 스모크 테스트 발화 8개 구성

정상 LIMO 2 · 정상 공장 2 · 모호 2 · 무효 2. **파일럿 30개와 겹치지 않게** 쓴다. 정답 라벨은 간단히 달아도 되지만 `gold_verdict`는 반드시 쓴다.

## 11. 체크리스트

**C**
- [ ] `limo-1.td.json`, `factory.td.json`이 JSON으로 파싱된다
- [ ] 모든 `@type`이 `vocab.json`에 있다(`python3 check_spec.py`로 확인)
- [ ] 모든 항목에 한국어 `description`이 있고, 값이 있는 action에 `input`이 있다
- [ ] `places.json`에 별칭이 있고 TD의 `location`이 모두 장소 ID다
- [ ] 같은 동작을 가진 기기가 2개 이상, 어디에도 없는 능력도 알고 있다
- [ ] `gold_smoke.jsonl` 8줄

**A**
- [ ] 로더가 위 파일을 읽어 `graph_interface.md`의 함수를 제공한다
- [ ] Function 노드를 만들지 않고 Device가 동작·속성·이벤트를 직접 가진다
- [ ] 채점 스크립트가 `templates/*.example.jsonl`로 손으로 계산한 값과 같은 결과를 낸다

**B**
- [ ] `rule.schema.json`과 회귀 테스트(`python3 check_spec.py`)
- [ ] mock 픽스처와 같은 인터페이스의 그래프
- [ ] LLM mock으로 8개가 끝까지 돈다, 그다음 실제 LLM
