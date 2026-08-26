# Knowledge Graph (KG)

> **역할** 사용자·공간·디바이스의 관계와 능력을 보유한다 — 접근은 IF-1 경유
> **상태** Phase 0 · 구현 중 · `kg.py`(resolve_location/list_locations) + `entities.json` 룩업 2건 등록 · 미측정 장소(예: 에어컨 제어 위치)는 여전히 미해소 · 작업 `0-10`
> **읽을 절** spec **§3.1**(IF-1 계약) · **§2.3**(KG↔IAD 구분) — 그 외 절은 열지 않는다
> **정본** 구조 `SOT.md` §2.1 · 스키마 `contracts/`

사용자·공간·디바이스의 **관계와 능력**을 보유한다 — 누가 무엇을 할 수 있는가.
`intent_audit_database/`(감사 이력)와는 별개다 (spec §2.3). 접근은 **IF-1 경유**.

## Phase 0: JSON 룩업으로 간소 구현 (D-6)

인터페이스 계약을 **고정**해 후일 그래프DB로 무중단 교체한다.

```json
{
  "entities": {
    "grandma":     {"type":"person","role":"elder","usual_place":"living_room"},
    "living_room": {"type":"space","map_frame":"map","pose":{"x":…,"y":…,"yaw":…}},
    "LIMO_1":      {"type":"device","skills":["navigate","person-scan","state-check"],
                    "sensors":["camera","lidar"],"agent_uri":"stdio://limo_1"}
  },
  "phrase_bindings": { "grandma": [...], "check": [...], "is okay": [...] }
}
```

## 구현 현황

`kg.py`의 `KnowledgeGraph.resolve_location(name)`이 `entities.json`을 읽어 좌표를 돌려준다.
등록된 것은 **3건**이다: `dining_area`(식탁 구역)·`upper_left_room`(좌상단 방)은 이 문서
「주의」 절이 확인한 실측 좌표, `air_conditioner`는 `tools/limo-patrol-viz/WORLD.md` §2가
전수 추출한 `AirconditionerB` 가구의 **소속 구역 접근점**(가구 자체 좌표는 아님, 벽 여유
1.68m로 검증됨)이다. 그 외 이름을 조회하면 좌표를 지어내지 않고 `UnknownLocationError`를 던진다
— 예를 들어 침실의 `AirconditionerA`는 **그 구역이 맵에서 미탐색이라 아직 등록하지 않았다.**

> ⚠️ **소비처가 Manager AI Core가 아니다.** Manager AI Core에 graph-inference 순수 코어는 생겼지만
> IF-1 context adapter가 아직 없어, Worker의
> `ReasoningModule`이 이 모듈을 **IF-1 없이 직접 import**해서 `resolve_location` MCP tool로
> 노출하고 있다 (임시 조치, `docs/decisions/2026-08-10-worker-side-kg-lookup-phase0.md`).
> Manager AI Core/IF-1이 생기면 이 배선을 되돌려야 한다.

## G-6 — 채워야 할 공백

현재 코드에 `list_locations` / `locations.json`이 **없다.** `plan_and_navigate`는 좌표만 받는다.
L2의 `<location-label>living_room`을 좌표로 해소할 경로가 없다.
**좌표 ↔ 방 이름 매핑을 만드는 것이 곧 G-6 해소이자 `entities.<space>` 채우기다** (작업 0-10).

## 주의 (중요)

- 저장소에서 좌표에 **의미 있는 이름이 붙은 것은 두 개뿐**이다:
  `(8.10, 1.71)`="식탁 구역", `(-7.77, 0.56)`="좌상단 방" (`tools/limo-patrol-viz/`).
  **나머지 5개 순찰 좌표에는 방 이름이 부여된 바 없다. 임의로 붙이지 말 것.**
- docx의 `locations.json`(`living_room = (1.2, 0.4)`)은 **별개 출처이며 small_house 좌표계와 무관하다.**
- `phrase_bindings`는 데모용 지름길이다. Phase 1에서 그래프 순회 + 임베딩 유사도로 대체하고
  이 표는 회귀 테스트 정답셋으로 전환한다.
