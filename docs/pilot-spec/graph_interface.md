# 그래프 인터페이스 (A 구현 · B 사용)

파일럿의 그래프는 TD 파일과 `places.json`, `vocab.json`을 읽어 **메모리에 만든다**(Neo4j 아님). 아래 함수만 제공하면 되고, 내부 저장 방식은 자유다. B는 이 시그니처를 따르는 mock 픽스처로 먼저 개발한다.

## ID 규칙
| 종류 | ID | 예 |
|---|---|---|
| 기기(Device) | TD의 `title` | `lamp-a` |
| 동작·속성·이벤트 노드 | `기기ID/키` | `lamp-a/turnOn` |
| Identity | `@type`의 `id:` 뒤 이름 | `turn-on` |
| 장소(Space) | `places.json`의 `id` | `room_a` |

Rule JSON이 참조하는 값은 **Identity ID**(`action-type`, `object-class`), **장소 ID**(`destination`), **기기 ID**(`target`)다. 기기별 노드 ID(`lamp-a/turnOn`)는 Rule에 나오지 않는다.

## 구조
Device가 `actions`·`properties`·`events`의 각 항목을 **직접** 가진다(중간 Function 층 없음). 각 항목은 `@type`으로 Identity 하나를 가리킨다. 기기는 `location`으로 장소 하나를 가리킨다.

## 함수

```python
class Graph:
    @classmethod
    def load(cls, td_paths: list[str], places_path: str, vocab_path: str) -> "Graph": ...

    # 존재 확인
    def has_identity(self, identity_id: str) -> bool: ...
    def has_place(self, place_id: str) -> bool: ...
    def has_device(self, device_id: str) -> bool: ...

    # 별칭 해소 (한국어 이름 → ID). 없으면 None
    def resolve_place(self, name: str) -> str | None: ...

    # Identity 계층
    def ancestors(self, identity_id: str) -> list[str]: ...   # 부모부터 루트까지
    def slot_of(self, action_identity_id: str) -> str | None: ...
        # "motion-action" | "perception-action" | "control-action" | None

    # 어떤 기기가 무엇을 제공하는가
    def devices_with(self, action_identity_id: str) -> list[str]: ...
    def input_schema(self, device_id: str, action_identity_id: str) -> dict | None: ...
    def device_location(self, device_id: str) -> str | None: ...

    # 검색용: 노드와 설명 텍스트
    def searchable_nodes(self) -> list[dict]: ...
        # kind는 "device" | "action" | "property" | "event" | "place" | "object-class"
        # {"node_id": "lamp-a/turnOn", "kind": "action", "identity": "turn-on",
        #  "device": "lamp-a", "names": ["turnOn", "켜다", "점등"], "text": "조명을 켠다. ..."}
        # names: 정확히 일치를 볼 이름과 별칭(TD의 aliases 포함), text: 설명 전체
        # place는 node_id=장소 ID, device는 node_id=기기 ID, object-class는 node_id=identity ID
    def neighbors(self, node_id: str, hops: int = 1) -> list[str]: ...
```

## 규칙
- `has_identity`는 `vocab.json`에 있는지를 본다. 어떤 기기가 실제로 제공하는지는 `devices_with`가 알려 준다.
- `slot_of`는 Identity의 조상 중 `MotionAction` / `PerceptionAction` / `ControlAction`을 보고 정한다.
- `input_schema`는 TD의 `input`을 그대로 돌려준다(없으면 `None`).
- 로드 중 TD의 `@type`이 `vocab.json`에 없으면 **오류를 낸다**(조용히 넘기지 않는다).
