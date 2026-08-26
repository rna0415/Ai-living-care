# AI-Care Edge System — 팀 공용 진입점
#
#   make hooks   최초 1회. 커밋할 때 앵커 검사가 자동으로 돈다
#   make check   커밋 전 검사 (수 초)
#   make test    로봇 없이 도는 회귀 (약 1분)
#
# ROS2 가 필요한 것은 여기 없다 — 시뮬·실기는 각 디렉터리 CLAUDE.md 참조.

# python3 이 없는 환경이 있다 (이 팀의 기본은 Windows + Git Bash — 거기엔 `python` 만 있다).
# 훅은 이미 폴백을 갖고 있었는데 Makefile 만 없어서 `make status` 가 안 돌았다.
PY ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)

.DEFAULT_GOAL := help
.PHONY: help hooks check test manager-test status spec anchor structure

help:
	@echo "  make hooks   pre-commit 훅 설치 (최초 1회)"
	@echo "  make check   앵커 + 구조 검사 — PR 기준(--strict). 커밋 훅은 더 완만하다"
	@echo "  make test    회귀 테스트 (로봇 불필요, 약 1분)"
	@echo "  make status  세션 시작에 한 번 — 전 영역 상태 + 최근 커밋·결정"
	@echo "  make spec    설계 정본 절 색인 — 시작 줄·크기를 읽는 시점에"

hooks:
	@git config core.hooksPath .githooks
	@chmod +x .githooks/* 2>/dev/null || true
	@echo "pre-commit 훅 설치됨 — 이제 커밋할 때 앵커 검사가 돈다"
	@echo "우회가 필요하면 (환경별):"
	@echo "  Git Bash     SKIP_ANCHOR=1 git commit ..."
	@echo "  CMD          set SKIP_ANCHOR=1 && git commit ... && set SKIP_ANCHOR="
	@echo '  PowerShell   $$env:SKIP_ANCHOR=1; git commit ...; Remove-Item Env:SKIP_ANCHOR'

status:
	@$(PY) anchor.py --status

spec:
	@$(PY) anchor.py --spec

check: anchor structure

anchor:
	@$(PY) anchor.py --strict

structure:
	@$(PY) sot_audit.py > /dev/null && echo "구조 OK" || ($(PY) sot_audit.py; exit 1)

test: manager-test
	@echo "── 순찰 커버리지 회귀 (ROS2 불필요) ─────────────────────"
	@cd tools/limo-patrol-viz && ./run_coverage.sh | tail -4

manager-test:
	@echo "── Manager graph-inference 회귀 (외부 의존성 없음) ───────"
	@$(PY) -m unittest manager_ai_agent.manager_ai_core.test_graph_inference
