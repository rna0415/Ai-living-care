# data — KG 스키마 파일럿 데이터 (스모크)

> **역할** 파일럿의 기기 TD, 장소, 정답 라벨과 실행 결과 (형식은 `docs/pilot-spec/SPEC.md`)
> **상태** `REFERENCE-ONLY` · 2026-10-07 · 스모크 발화 8개 · 정답 점검 8/8 통과(`check_gold`) · 실제 LLM(`claude-sonnet-5-5`, Claude CLI)으로 1회 실행 · 채점은 아직
> **정본** 아님

| 파일 | 내용 |
|---|---|
| `limo-1.td.json` · `cobot.td.json` · `amr.td.json` | 기기 TD (LIMO · 협동로봇 · 물류 이송 로봇) — C 작성 |
| `places.json` | 장소 27개 (집 + 공장 구역), 한국어 별칭과 좌표 |
| `gold_smoke.jsonl` | 스모크 발화 8개와 정답 (정상 4 · 모호 2 · 무효 2) |
| `results_smoke.jsonl` | 위 8개를 파이프라인에 통과시킨 결과 1회분. 검증 전 LLM 원본 출력·후보·검증·판정·토큰 수 포함 |
