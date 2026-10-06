# pilot-spec/templates — 파일럿 데이터 형식 예시

> **역할** C가 TD·장소·라벨을, B가 결과를 쓸 때 따를 형식 예시. 내용은 일반 예시이며 LIMO·공장 데이터가 아니다
> **상태** `REFERENCE-ONLY` · 2026-10-06

| 파일 | 내용 |
|---|---|
| `example-lamp.td.json` | TD 형식 예시 (조명 1대, 한국어 설명·별칭·input 스키마) |
| `places.example.json` | 장소 파일 형식 예시 (별칭, 좌표 없음 허용) |
| `gold.example.jsonl` | 라벨 형식 예시 — 정상·모호·무효 각 1줄 |
| `results.example.jsonl` | 결과 기록 형식 예시 — 검증 전 LLM 원본 출력 포함 |
