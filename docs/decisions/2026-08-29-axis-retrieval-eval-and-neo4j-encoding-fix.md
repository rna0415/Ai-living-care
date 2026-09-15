# 2026-08-29 · axis retrieval 비교 실험(`kg_mapping/eval/`) 추가 + Neo4j 한글 인코딩 손상 수정

> **정본 반영** `manager_ai_agent/manager_ai_core/kg_mapping/CLAUDE.md`

## 배경

axis 라우팅(`axis_routing.py`, Method 1: 손으로 쓴 축 설명 + ko-sroberta 임베딩)과, Neo4j
그래프 내용(device/function/AxisKnowledge.rationale)을 그대로 축 표현으로 쓰는 방식(Method 2,
이번에 새로 만듦)을 검증 문장 20개로 비교했다. `kg_mapping/eval/`에 실험 코드로 추가한다 —
`kg_mapping/CLAUDE.md`가 이미 "실험·미승인"으로 표시한 `graph_retrieval.py`·`axis_routing.py`와
같은 층위, 정본 승격 아님.

## 작업 중 발견한 문제 — Neo4j 한글 데이터 손상

평가를 실제 그래프로 돌리기 전, `GraphRetriever.fetch_axis_context()`가 반환하는
`AxisKnowledge.rationale` 등 한글 텍스트에 U+FFFD(복구 불가 대체문자)가 섞여 있는 것을
발견했다. `livingcare_graph_v2.cypher` 원본 파일은 정상 UTF-8인데, DB 안 실제 값은 깨져
있었다 — 최초 적재 때 (아마 `cypher-shell` 등이 콘솔 코드페이지로 stdin을 잘못 디코딩해)
바이트가 이미 유실된 것으로 보인다.

박준상님 확인 하에 **DB를 `MATCH (n) DETACH DELETE n`으로 비우고, `.cypher` 파일을 Python
`neo4j` 드라이버로(파일을 UTF-8로 직접 읽어 문장 단위 실행) 재적재**해 고쳤다. 재적재 후
`rationale` 필드에 U+FFFD 없음을 확인(스팟체크 1건 + `eval/` 평가 전체 재실행으로 간접 확인).
86개 문장 전부 재실행 성공, 노드 수 41개로 재적재 전과 동일.

**교훈**: 이 그래프에 자연어 텍스트를 다시 적재/수정할 일이 있으면 반드시 UTF-8을 명시하는
경로(Python 드라이버 등)로 하고, `cypher-shell`처럼 콘솔 인코딩에 의존하는 경로는 피한다.

## eval/ 구성

| 파일 | 역할 |
|---|---|
| `graph_axis_doc.py` | axis 하나의 `fetch_axis_context()` 결과를 한국어 텍스트 한 덩어리로 직렬화 |
| `build_graph_axis_vectors.py` | 위 텍스트를 `jhgan/ko-sroberta-multitask`로 임베딩해 `graph_axis_vectors.json`에 캐싱(Neo4j 연결 필요, 1회성) |
| `graph_axis_vectors.json` | Method 2 축 중심 벡터 캐시 — 이후 평가는 Neo4j 없이 이 파일만으로 돈다 |
| `validation_sentences.json` | 검증 문장 20개(WellBeing/Safety/Comfort 각 5~7 + OOS 2). **`gold_axis` 라벨은 Claude 초안 — 박준상님 검수 전** |
| `evaluate_axis_retrieval.py` | Method 1(`../axis_centroids.json`) vs Method 2 top-1 정확도·confusion matrix·OOS 분리력 비교, `results.json` 출력 |
| `results.json` | 최근 실행 결과(실측치) |

## 결과 요약 (1회 실측, 라벨 미검수 상태)

Method 1(문장 임베딩) top-1 정확도 94.4%(17/18) vs Method 2(그래프 기반) 83.3%(15/18).
Method 2가 Safety→Comfort로 새는 오분류가 2건 — Comfort의 rationale 텍스트가 4개 규칙·749자로
가장 길고 구체적이라 일반 안전 문장과도 임베딩이 가까워지는 것으로 추정(후속 검증 필요).
OOS 2문장에 대한 최고 유사도는 Method 2가 둘 다 더 낮아(관련 없는 문장에 덜 반응) — 다만
Method 2용 라우팅 임계값은 아직 캘리브레이션 안 됨. 상세 수치·confusion matrix는 artifact
(`https://claude.ai/code/artifact/c20ee5fc-6d3e-4887-b76f-ae7096efa334`, 대화 세션에서 생성)
참조.

## 승격하지 않은 것

- **`axis_routing.py`의 정본 라우팅은 바꾸지 않았다.** 이 비교는 별도 실험 — Method 2를
  실제 파이프라인(`pipeline.py`)에 연결하지 않았다.
- **`validation_sentences.json`의 라벨은 확정이 아니다.** CLAUDE.md 태스크 세분화/검증 규칙대로
  박준상님이 직접 검사·수정해야 최종 수치로 쓸 수 있다.
- Neo4j 데이터 자체는 실서비스 데이터가 아니라(D-6 TODO 대상, 이 저장소 밖 데이터) 백업 없이
  바로 비우고 재적재했다 — 프로덕션이었다면 다른 절차가 필요했을 것.
