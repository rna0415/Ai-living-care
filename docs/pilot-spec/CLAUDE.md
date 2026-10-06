# pilot-spec — KG 스키마 파일럿 명세 (A·B·C 공통 계약)

> **역할** 파일럿(분해된 발화 → Rule JSON 번역 평가)에서 세 사람이 서로의 산출물을 쓰기 위해 맞춰 두는 형식과 이름
> **상태** `REFERENCE-ONLY` · 2026-10-06 초안 v0.1 · `check_spec.py` 통과(유효 1 · 무효 6 · 어휘·템플릿 정합성) · 아직 팀 합의 전
> **정본** 아님 — 채택하면 `docs/decisions/`에 결정 파일, 스키마는 `contracts/`로 옮긴다

| 파일 | 내용 |
|---|---|
| `SPEC.md` | 범위, 담당별 산출물, 동결된 결정, TD·장소·라벨 작성 규칙, 검증·배정 정의, 체크리스트 |
| `rule.schema.json` | LLM이 만드는 Rule의 정적 JSON Schema (구조·타입·범위만 검사) |
| `vocab.json` | Identity 어휘 시드. TD의 `@type` 값은 모두 여기에 있어야 한다 |
| `graph_interface.md` | 그래프 로더가 제공할 함수 시그니처 (A 구현 · B 사용) |
| `check_spec.py` | 스키마 회귀, 어휘 부모 참조, TD·라벨 형식 점검. `python3 check_spec.py [TD 또는 gold.jsonl ...]` |
| `templates/` | TD·장소·라벨·결과 형식 예시 (`templates/CLAUDE.md`) |
