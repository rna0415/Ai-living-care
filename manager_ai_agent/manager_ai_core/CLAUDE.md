# Manager AI Core (MAC)

> **역할** L0(자연어) → L1(Intent Query) → L2(High-level Policy)
> **상태** Phase 0 · 미착수(정본 파이프라인) · 작업 `0-3` · **`kg_mapping/`·`policy_generation/`에 실험·미승인 Neo4j 추론 코드 있음** (2026-08-18, 옛 `graph_inference/` 분배) · **`api_server.py`로 HTTP 게이트웨이 실험 추가**(2026-08-18, 상급자 승인 대기)
> **읽을 절** spec **§4.1**(계층 정의) · **§4.2**(L1) · **§4.3**(L2 ECA) — 그 외 절은 열지 않는다
> **정본** 구조 `SOT.md` · spec §4

**Intent Translator + Session Key Manager.** L0(자연어) → L1(Intent Query) → L2(High-level Policy) 변환의 주체.

논문 Fig.1과 slide 17의 표는 `Manager Controller`로 표기 — **별칭으로만 인정**한다 (spec §2.1).

## 구성

| 디렉터리 | 책임 |
|---|---|
| `intent_extraction/` | L0 자연어 → 어구 분해 |
| `kg_mapping/` | 어구 → KG element=value 바인딩 (IF-1) · **+ 축(axis) 라우팅·Neo4j 조회 실험 코드** |
| `query_composing/` | 바인딩 → L1 Intent Query JSON |
| `policy_generation/` | L1 → L2 High-level Policy (ECA) · **+ 규칙 판단·LLM intent 조립 실험 코드** |
| `session_key_manager/` | IF-4 세션 키 발급·갱신 (파이프라인과 직교) |

## 파이프라인 (정본 — 미착수)

```
"Check if Grandma is okay"
  → intent_extraction/     ["Grandma", "check", "is okay"]
  → kg_mapping/            IF-1로 KG 조회 → phrase별 element=value 바인딩
  → query_composing/       L1 Intent Query JSON
  → policy_generation/     LLM + Schema Prompt → L2 ECA XML
```

`session_key_manager/`는 직교하며 IF-4의 세션 키를 발급·갱신한다.
생성된 L2는 `../a2a_client/`가 IF-4로 실어 보낸다.

## 반드시 지킬 것

- **L2에 디바이스 이름을 넣지 않는다.** device-agnostic이어야 다중 Worker fan-out이 성립한다 (spec §4.3).
- **`bindings`를 반드시 남긴다.** 어느 어구가 어떤 값으로 해소됐는지 없으면 오역 디버깅이 불가능하다 (P-5).
- **LLM 실패 경로를 설계에 포함한다** (P-4). 정상 파싱 → 필드 정규화 → 규칙 기반 폴백 3단 구조 권장.

## 작업 (Phase 0)

- [ ] 0-3 L0→L2 파이프라인 전체
- [ ] LLM 선택 확정 (U-3)
- [ ] L2 직렬화 형식 확정 (U-2 — 내부 JSON / 표준 문서 XML 양방향 변환 권고)

---

## Neo4j 추론 파이프라인 (실험 · 미승인 — 위 정본 파이프라인과 별개)

준상님의 Neo4j 지식그래프 위에 얹는 **다른 모양의** 추론 계층. 자연어 → 축(axis) 라우팅 →
그래프 조회(C1) → 규칙 판단(C2) → 로봇 intent 생성(C3). 위 정본 파이프라인(어구 분해 →
IF-1 바인딩 → L1 JSON → L2 XML)과 **스키마·흐름이 다르다** — 병합 여부는 TODO(확인 필요),
`kg_mapping/CLAUDE.md`의 「기존 KG와의 관계」참조.

**판단(위험도·에스컬레이션)은 코드가 규칙으로 결정**하고 **LLM(Ollama/Claude)은 조립만** 한다.
그래프는 **읽기 전용(MATCH)** 으로만 접근한다.

**tier 시스템(2026-08-24 추가, `manager_orchestrator_design.md` 반영)**: Axis마다
불변 tier(1~4)가 있어 LLM에게 허용된 재량 상한을 정한다. tier=1(WellBeing·Safety)에서
axis_knowledge가 없으면 그래프 설계 오류로 보고 `no_relation` + 관리자 escalation
로그(`logs/admin_escalations.log`, JSON-lines, git-ignored)를 남기고, tier<=2는
`sequence_generator.py`도 지금처럼 결정론 경로만 쓴다. tier=4(현재 Comfort만)는
axis_knowledge가 없으면 정상 HITL로 `need_more_knowledge`를 반환하고, 있으면
LangGraph 기반 에이전트가 도구 호출을 스스로 반복하는 루프로 명령을 조립한다(아래
`graph_tools.py`). tier 2~3의 실제 차등 동작은 미정 — 지금은 tier=4와 동일 취급
(`pipeline.py`/`policy_generation/CLAUDE.md` 참조). **의도적 설계 편차**: 이 에이전트
루프도 Cypher는 LLM이 생성하지 않는다 — `graph_tools.py`가 감싸는 건 이미 고정된
`graph_retrieval.py` 쿼리뿐이고, 에이전트는 "어떤 도구를 언제 부를지"만 결정한다
(`GraphCypherQAChain`류의 LLM Cypher 생성 패턴은 read-only/Cypher-격리 원칙과
충돌해서 의도적으로 안 씀).

### 파일

| 파일 | 역할 |
|---|---|
| `pipeline.py` | 라우팅 → tier×OOS 스코프 판별 → C1 → C2 → 안전 게이트 → device fallback → C3 통합. 7개 시나리오 데모 포함 |
| `trace_demo.py` | 한 시나리오가 단계마다 어떤 데이터로 변하는지 펼쳐 보는 학습용 |
| `call_trace_demo.py` | 어떤 함수가 어떤 순서로 호출되는지 추적 |
| `kg_mapping/graph_retrieval.py` | C1 — Neo4j 조회 (읽기 전용 Cypher). axis의 tier도 함께 반환 |
| `kg_mapping/graph_tools.py` | tier>=3 에이전트 루프용 LangChain Tool 래퍼(읽기 전용, 새 Cypher 없음) |
| `kg_mapping/axis_routing.py` | 자연어 → 축 라우팅 (ko-sroberta 임베딩, 폴백 포함) |
| `kg_mapping/axis_centroids.json` | 축별 임베딩 중심값 (진짜 임베딩 모드에 필요) |
| `policy_generation/rule_evaluator.py` | C2 — 규칙 평가(판단, 코드, 결정론적) |
| `policy_generation/sequence_generator.py` | C3 — 로봇 intent 생성. tier<=2 결정론/단발 LLM, tier>=3 LangGraph 에이전트 루프. 백엔드: Ollama(무료) → Claude(유료) → mock |
| `logs/admin_escalations.log` | tier=1 축의 axis_knowledge 누락 시 관리자 escalation 기록(JSON-lines, git-ignored) |
| `api_server.py` | **HTTP 게이트웨이(2026-08-18 추가, 별도 실험·미승인)** — `../../frontend/`가 POST하는 자연어를 받아 `pipeline.run()`으로 처리하고 결과를 반환하는 동시에 `../a2a_client/a2a_client.py`(표준 A2A, HTTP+JSON-RPC 2.0)로 Worker에 전달. root `CLAUDE.md`의 "HTTP API 없음"과 충돌 — `../../frontend/CLAUDE.md` 참조 |
| `end_to_end.py` | **별도 조립 파이프라인(2026-09-01 설계, 실험·미승인)** — `pipeline.py`(slot 하나씩 threshold 라우팅)를 대체하지 않고 병존. "포괄적 질의 → 관련 지식 top-k 동시 추출"(`kg_mapping/knowledge_retriever.py`) → `worker_agent.py` 관측값 → C2 판단 → InterventionPolicy 분기 → C3 조립 순서로 동작 |
| `worker_agent.py` | Manager가 확인이 필요하다고 판단한 slot의 실제(또는 mock) 관측값을 가져오는 Worker(실험·미승인). 함수 시그니처를 나중에 실제 MCP tool-call로 그대로 옮길 수 있게 설계 |

### 실행 준비물

1. **Neo4j** — `bolt://localhost:7687`, 계정 `neo4j`, 비밀번호는 `NEO4J_PASSWORD` 환경변수 또는
   `kg_mapping/.env`(git에 안 올라감, `kg_mapping/CLAUDE.md` 참조)로 주입한다 (코드 기본값
   `livingcare123`은 예시일 뿐 실제 접속 비밀번호가 아니다 — 절대 커밋하지 않는다).
   그래프는 `livingcare_graph_v2.cypher`(준상님 소유, 이 저장소 밖)로 구축.
2. `pip install neo4j` (필수) · `pip install sentence-transformers`(선택 — 없으면 라우팅이
   단어겹침 폴백으로 내려간다) · `pip install anthropic`(선택 — Claude 백엔드 쓸 때만)
3. **Ollama**(선택, C3 무료 로컬 LLM) — `ollama pull qwen2.5:7b`. 안 떠 있으면 C3는 자동 mock 폴백.
4. tier>=3(현재 Comfort) 에이전트 루프를 실제로 태우려면 `pip install langgraph
   langchain-core langchain-ollama langchain-anthropic`도 필요(선택 — 없거나 백엔드가
   mock이면 tier와 무관하게 결정론 경로로 안전하게 떨어진다).

```bash
cd manager_ai_agent/manager_ai_core
python pipeline.py                                    # kg_mapping/.env가 있으면 그대로 인증됨
python trace_demo.py "할머니 괜찮은지 확인해줘" 15
python call_trace_demo.py

# HTTP 게이트웨이(실험) — 프론트엔드와 함께 쓸 때
pip install fastapi "uvicorn[standard]" requests
python -m uvicorn api_server:app --reload --port 8000
# 별도 터미널: cd ../../frontend && npm install && npm run dev  (http://localhost:5173)
```

환경변수: `LLM_BACKEND=mock|ollama|claude` · `OLLAMA_MODEL` · `ANTHROPIC_API_KEY` ·
`NEO4J_URI` · `NEO4J_USER` · `NEO4J_PASSWORD`.

### 지금 "진짜"인 것 vs "mock/스텁"인 것

| 구성요소 | 현재 |
|---|---|
| Neo4j 그래프 조회 | ✅ 진짜 (준상님 데이터, 이 저장소 밖에 있음) |
| 규칙 판단(C2) / 안전 게이트 | ✅ 진짜 코드 |
| 센서 관측값 | ⚠️ mock (그래프 State가 비어서) |
| C3 생성 | ✅ Ollama 무료 로컬 또는 Claude — 둘 다 없으면 mock |
| 라우팅 임베딩 | ✅ sentence-transformers 설치 시 진짜(ko-sroberta) · 없으면 폴백(단어겹침) |
| 로봇 실제 실행 | ❌ 없음 (intent까지만) |

### `versions/` — 프레임워크 4종 비교 실험 (2026-09-01, 실험·미승인)

같은 시나리오("할머니 괜찮은지 확인해줘", motion 5시간 무동작 + 심박 38bpm 서맥)를 서로 코드도
프레임워크도 겹치지 않는 4가지 방식(v1 기존 그래프RAG+결정론, v2 BDI, v3 형식검증(Z3),
v4 효율성 라우팅)으로 구현해 비교한 기록. `README.md`만 있고 실행 코드는 각 `v*_*/`
서브디렉터리 참조. 정본 파이프라인에 반영되지 않은 비교 실험.

### 팀과 정할 것

- **State**: 누가 쓰나 / 원본값 vs 가공값 / key 규약 / 읽기 권한 / 센서별 유무·신선도
- **에스컬레이션**: `requires_escalation_from` 그래프化 여부 / phase 전환 기준 / 배터리 등 물리조건
- **아키텍처**: Neo4j vs 기존 JSON KG(D-6) — `kg_mapping/CLAUDE.md` 참조
- 이 파이프라인의 산출물(intent 자연어 문장)을 정본 L2 ECA XML로 어떻게 승격/변환할지
