"""make_nl_e2e_figure.py -> fig_nl_routing.png, fig_nl_funnel.png"""

import json

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE, ORANGE, AQUA, RED, GREEN = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2dd"

with open("eval_nl_e2e_results.json", encoding="utf-8") as f:
    data = json.load(f)

items = data["items"]
summary = data["summary"]

# ---- 1. 라우팅 결과 — 16개 항목, 소스별로 그룹, 성공/실패 색 구분 ----
fig, ax = plt.subplots(figsize=(9, 5.5))
sources_order = ["Intent.raw_text", "Intent.raw_text(system)", "ObservationSelectionPolicy.goal_pattern",
                  "ResponseSelectionPolicy.problem_pattern", "KnowledgeQueryPolicy.goal_pattern"]
y = list(range(len(items)))
labels = [f"{it['id']}  ({it['text'][:22]}{'…' if len(it['text']) > 22 else ''})" for it in items]
colors = [GREEN if it["routing_correct"] else RED for it in items]

ax.barh(y, [1] * len(items), color=colors, height=0.6)
ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=9)
ax.invert_yaxis()
ax.set_xlim(0, 1.3)
ax.set_xticks([])
for i, it in enumerate(items):
    ax.text(1.03, i, f"{it['true_category']} → {it['predicted_category']}",
             va="center", fontsize=8.5, color=TEXT if it["routing_correct"] else RED)
ax.set_title(f"자연어 → axis 라우팅 (그래프에 있는 자연어 16개 전부) — "
             f"accuracy={summary['routing_accuracy']*100:.1f}%, macro-F1={summary['routing_macro_f1']*100:.1f}%",
             color=TEXT, fontsize=11, loc="left")
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig("fig_nl_routing.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---- 2. 퍼널 차트 — 파이프라인 실행 가능한 8개, 단계별 통과율 ----
stages = summary["stage_pass_rates"]
stage_names = list(stages.keys())
stage_values = [stages[k] * 100 for k in stage_names]

fig, ax = plt.subplots(figsize=(8, 4.5))
bar_colors = [BLUE, AQUA, ORANGE, "#4a3aa7", RED]
bars = ax.bar(stage_names, stage_values, color=bar_colors[: len(stage_names)], width=0.55)
for b in bars:
    h = b.get_height()
    ax.annotate(f"{h:.1f}%", (b.get_x() + b.get_width() / 2, h), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom", fontsize=11, color=TEXT, fontweight="bold")
ax.set_ylim(0, 112)
ax.set_ylabel("통과율 (%)", color=MUTED)
ax.set_title(f"자연어 → device 호출 전체 파이프라인 단계별 통과율 (N={summary['n_e2e_testable']}, "
             f"실행 가능한 것만)", color=TEXT, fontsize=11, loc="left")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.spines["left"].set_color(GRID)
ax.spines["bottom"].set_color(GRID)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
plt.setp(ax.get_xticklabels(), fontsize=10)
fig.tight_layout()
fig.savefig("fig_nl_funnel.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("저장 완료: fig_nl_routing.png, fig_nl_funnel.png")
