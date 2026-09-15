# Knowledge Graph (KG)

> **역할** 사용자·공간·디바이스의 관계와 능력을 보유한다 — 접근은 IF-1 경유
> **상태** Phase 0 · 미착수(정본 JSON 룩업) · 갭 `G-6` · 작업 `0-10` · **Neo4j 그래프 파일 있음(실험·미승인, 2026-08-18)** · **`graph_cot_agent/` 평가 프로토타입 있음(실험·미승인, 2026-09-15)**
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

## Neo4j 그래프 파일 (실험 · 미승인 — 위 정본 JSON 룩업과 별개)

`manager_ai_core/kg_mapping/graph_retrieval.py`(실험 파이프라인, `docs/decisions/
2026-08-18-graph-inference-distribution.md`)가 읽는 그래프의 **원본**을 2026-08-18에 이
폴더로 들여왔다. **스키마가 위 D-6 JSON과 다르다** — 여기는 `Axis/Device/Function/State/
AxisKnowledge`, D-6 JSON은 `person/space/device`(grandma·living_room·LIMO_1). 하나를
다른 하나로 대체할지 공존시킬지는 여전히 TODO(확인 필요) — `kg_mapping/CLAUDE.md`
「기존 KG와의 관계」참조.

| 파일 | 역할 |
|---|---|
| `livingcare_graph_v2.cypher` | 그래프를 **처음부터 다시 만드는** Cypher 스크립트(준상님 작성, 저장소 밖 개인 작업 폴더에서 복사). Neo4j Browser에 그대로 붙여넣으면 재현된다 |
| `export_neo4j_snapshot.py` | 지금 **실제로 떠 있는** 그래프를 JSON으로 통째로 내보내는 스크립트. `.cypher`를 돌린 뒤 수동으로 고친 값이 있어도 그 변경분까지 잡힌다 |
| `neo4j_snapshot.json` | 위 스크립트로 2026-08-18에 뜬 스냅샷 — 노드 362개·관계 666개(1회 실측). **tier 추가 후 재실행 필요(아래)** |
| `load_v5.py` | v5 스키마+seed(제약→seed→additions→runtime_examples 등 최대 6개 `.cypher` 파일)를 순서대로 새 Neo4j 인스턴스에 적재. `cypher-shell` 대신 파이썬 드라이버로 문장 단위 실행해 한글 인코딩 손상을 피한다(2026-08-29 결정) |
| `reload_from_cypher.py` | `.cypher` 파일 하나를 받아 그래프를 `DETACH DELETE` 후 통째로 재적재. 역시 UTF-8 직접 읽기로 인코딩 손상을 피함 |
| `apply_additions.py` | `reload_from_cypher.py`의 비파괴 버전 — 기존 데이터는 건드리지 않고 새 노드/관계만 얹는다 |

**tier 시스템(2026-08-24 추가)**: `Axis.tier`(1~4, `manager_orchestrator_design.md`의
불변 재량 상한) 추가 — WellBeing/Safety=1(로봇 출동 축이라 결정론만), Comfort=4(로봇
없는 센서 전용 축이라 에이전트 루프 파일럿). tier×axis_knowledge-없음 OOS 매트릭스
실증용 데모 축 2개(`onto:demo/TierFixedNoKnowledge` tier=1, `onto:demo/
TierResilientNoKnowledge` tier=4, 둘 다 axis_knowledge 없음, 실서비스 축 아님)와,
Comfort의 device fallback 데모용 backup 온도센서(`cap:temperaturesensor_backup`,
기존 `cap:temperaturesensor`의 SensingFunction은 데모로 `reachable=false`) 추가.
반영하려면 그래프를 `MATCH (n) DETACH DELETE n;` 후 `.cypher` 재실행 → 
`export_neo4j_snapshot.py`로 스냅샷 갱신할 것.

`livingcare_graph_v2.cypher`로 새로 만든 그래프와 `neo4j_snapshot.json`이 정확히 같다는
보장은 없다 — 스크립트 실행 이후 수동 수정이 있었는지는 확인 못 했다(TODO 확인 필요).
**`neo4j_snapshot.json`이 "지금 실제로 쓰이는" 값의 정본이고, `.cypher`는 "어떻게 만들어졌는가"의 기록이다.**

### 실행

```bash
cd manager_ai_agent/knowledge_graph
python export_neo4j_snapshot.py                 # .env가 있으면 그대로 인증됨 (kg_mapping/.env와 같은 관례)
python export_neo4j_snapshot.py 다른경로.json     # 출력 경로 지정
```

비밀번호는 `NEO4J_PASSWORD` 환경변수 또는 이 폴더의 `.env`(git에 안 올라감)로 준다.

## `graph_cot_agent/` — action/judgement/timing 평가 프로토타입 (실험·미승인, 2026-09-15)

위 Neo4j 파이프라인·`manager_ai_core/`와 **코드를 공유하지 않는 독립 프로토타입**이다.
`graph_cot_agent.py`는 Neo4j에 연결하지 않고 v5 seed `.cypher` 파일을 직접 텍스트로 파싱해서
쓴다. v5 스키마가 이미 갖고 있는 action(관측)/judgement(판단)/timing(에스컬레이션)/action(대응)
4단 분리를 그대로 따라, WellBeing·Safety는 코드가 규칙을 결정론으로 평가하고 Comfort는
LLM 에이전트 tool-use 루프로 분기한다. 상세 설계·평가 방법론·전체 결과는
`docs/decisions/2026-09-15-graph-cot-agent-eval.md`와 이 폴더의 `report.md` 참조.

**핵심 결과 요약**(전체 수치·그림은 `report.md`):
- 기본 회귀 15개 케이스(persona 3명 × WellBeing/Safety × 관측 시나리오) **전부 pass** —
  검증 과정에서 실제 버그 2건 발견·수정(`severity=INFO`인데 `escalate`가 새던 것, `ci:motion`이
  두 axis 관측 목록에 겹쳐 있어 axis 필터 없이 규칙이 섞이던 것).
- 개인화(취약군 threshold)가 **부가 정보가 아니라 실제 escalate 판정 자체를 가른다**는 것을
  19°C 경계 관측값으로 화이트박스 검증함(`mr_cf1_temp_too_low`).
- **판정 커널(`_evaluate_single_rule`)이 그래프 23개 규칙 중 61%(14개)만 구현** — 나머지
  9개는 `threshold_kg`/`threshold_percent`/`threshold_seconds`/`threshold_count`/
  `threshold_mgdl*` 등 미지원 필드를 써서 항상 NORMAL로 판정된다(`eval_macro_f1.py`,
  전체 규칙 기준 macro-F1 94.1% vs 지원 규칙만 100%).
- **자연어 axis 라우터(char n-gram TF-IDF)가 그래프 원문 16개에선 93.8%지만, 직접 지어낸
  자연스러운 구어체 합성 100문장에선 macro-F1 47.2%로 붕괴**(`eval_synthetic_nl_100.py`) —
  참조 문서(정책 문서체)와 실제 발화(구어체) 간 분포 불일치가 원인. 영어 전문용어 제거로
  저비용 완화를 시도했으나 효과 없음(오히려 -1.0%p, `eval_synthetic_nl_100_v2.py`). 이
  라우터를 임베딩/LLM 기반으로 교체하기 전엔 "자연어를 이해한다"고 말할 수 없다는 게
  이번에 정량적으로 확인된 가장 실사용 영향이 큰 한계.
- Comfort축(LLM 에이전트 경로)은 이 환경에 API 키가 없어 자동채점에서 계속 제외됨 — 여전히
  미검증.

**정본으로 승격하지 않음**: 위 Neo4j 파이프라인(`kg_mapping/graph_retrieval.py` 등)이나
`manager_ai_core/pipeline.py`에 연결되지 않았다 — 독립 평가 실험으로만 존재한다.
