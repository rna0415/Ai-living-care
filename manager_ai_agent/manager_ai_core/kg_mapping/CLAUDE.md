# KG Mapping

> **역할** 어구 → KG element=value 바인딩. IF-1 경유만
> **상태** Phase 0 · 부분 구현 — `axis_routing.py` keyword fallback+scorer 주입 · IF-1 phrase binding 미구현 · 갭 `G-6`
> **읽을 절** spec **§3.1**(IF-1 계약) · **§4.2** — 그 외 절은 열지 않는다
> **정본** 구조 `SOT.md` · spec §3.1

추출된 어구를 KG에 조회해 `element = value` 바인딩으로 해소한다. **IF-1 경유** (`interfaces/if01_database/`).

```
resolve(phrase: str, context: dict) -> list[Binding]
Binding = {"element": str, "value": any, "confidence": float, "source": str}
```

slide 21의 KG mapping 표:

| PHRASE | ELEMENT → RETRIEVED VALUE |
|---|---|
| "Grandma" | `target = elder`, `place = living_room` |
| "check" | `task = safety_check`, `mobile = [LIMO_1, LIMO_2]` |
| "is okay" | `condition = realtime`, `sensor = camera` |

## 구현된 부분

`axis_routing.py`는 WellBeing/Safety/Comfort 축의 보수적 keyword 라우팅과 외부 scorer 주입점을 제공한다.
모듈 import 시 임베딩 모델을 읽지 않으며 KG 파일에도 접근하지 않는다. 이 결과는 IF-1 조회 전 후보 축을
줄이는 pre-filter일 뿐, 위 `Binding` 계약이나 `query_composing/`을 대신하지 않는다. 라우팅 임계값은
`0 < threshold <= 1`이어야 하며, 범위를 벗어나거나 scorer가 유한하지 않은 값을 반환하면 판정을 중단한다.

## 주의

- **KG를 직접 파일로 읽지 말 것.** IF-1 계약으로만 접근해야 후일 그래프DB로 무중단 교체할 수 있다 (D-6).
- `confidence`를 반드시 채운다. 낮은 신뢰도 바인딩은 사용자 확인(MRTR)으로 승격될 수 있다.
