# pilot_pipeline — KG 스키마 파일럿 파이프라인 (검색 → 생성 → 검증 → 배정)

> **역할** 분해된 발화 → Rule JSON 번역을 평가하는 파일럿의 파이프라인과 결과 기록 (명세는 `docs/pilot-spec/`)
> **상태** `REFERENCE-ONLY` · 2026-10-07 · 메모리 그래프 스텁 + 검증기 4종 + 어휘 검색 + LLM 백엔드(mock · Claude CLI · Anthropic API, Ollama 는 주석 보존) · `unittest` 33건 통과(mock LLM) · **실제 LLM·임베딩으로는 아직 실행 안 함** · A2A·MCP 전송은 범위 밖
> **읽을 절** 없음 — `docs/pilot-spec/SPEC.md` §3·§9 만 본다
> **정본** 아님 — 채택하면 `docs/decisions/` 에 결정 파일

| 파일 | 내용 |
|---|---|
| `graph_stub.py` | `docs/pilot-spec/graph_interface.md` 를 따르는 메모리 그래프. A 의 로더가 나오면 같은 인터페이스로 교체 |
| `retrieval.py` | 어구 → 노드 연결(이름·별칭 일치, bigram 유사도, 선택적 임베딩) + 이웃 확장 → 후보 집합 |
| `generation.py` | 프롬프트 구성, LLM 백엔드(`MockLLM` · `ClaudeCLILLM`(`claude -p`, 구독 로그인) · `AnthropicLLM`, `OllamaLLM` 은 주석 보존), JSON 파싱과 재시도. `{"unsupported": ...}` 거부 경로 |
| `validator.py` | 검증 4종: schema → reference → slot → args. 처음 실패한 검사를 돌려준다 |
| `assign.py` | execute / ask-clarification / reject 판정 |
| `pipeline.py` | `run_one` 과 CLI. 발화마다 `results.jsonl` 한 줄(검증 전 원본 출력 포함)을 남긴다 |
| `check_gold.py` | 정답 파일을 그래프와 대조(정답 검증 · 배정 · 검색 재현) — C 가 라벨을 달 때 쓴다. `python3 -m ...pilot_pipeline.check_gold --td ... --places ... --vocab ... --gold ...` |
| `test_pilot_pipeline.py` | 위 전부의 회귀. `python3 -m unittest manager_ai_agent.manager_ai_core.pilot_pipeline.test_pilot_pipeline` |
