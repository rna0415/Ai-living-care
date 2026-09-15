"""make_robustness_figure.py — eval_robustness_results.json -> fig_sensitivity_specificity.png"""

import json

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE = "#2a78d6"
AQUA = "#1baf7a"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e3e2dd"

with open("eval_robustness_results.json", encoding="utf-8") as f:
    data = json.load(f)

rows = data["boundary_montecarlo"]
scenarios = sorted({r["scenario"] for r in rows}, key=lambda s: [r["scenario"] for r in rows].index(s))

sens = [next(r["sensitivity"] for r in rows if r["scenario"] == s and "sensitivity" in r) * 100 for s in scenarios]
spec = [next(r["specificity"] for r in rows if r["scenario"] == s and "specificity" in r) * 100 for s in scenarios]

x = np.arange(len(scenarios))
w = 0.32

fig, ax = plt.subplots(figsize=(8.5, 4.5))
b1 = ax.bar(x - w / 2, sens, width=w, color=BLUE, label="민감도(안전도) — 위험을 놓치지 않는 비율")
b2 = ax.bar(x + w / 2, spec, width=w, color=AQUA, label="특이도(편의성) — 오탐 없이 넘어가는 비율")

for bars in (b1, b2):
    for b in bars:
        h = b.get_height()
        ax.annotate(f"{h:.1f}%", (b.get_x() + b.get_width() / 2, h), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10, color=TEXT)

ax.set_xticks(x)
ax.set_xticklabels(scenarios, fontsize=10)
ax.set_ylim(0, 115)
ax.set_ylabel("%", color=MUTED)
ax.set_title("경계값 몬테카를로 — 안전도 vs 편의성 (N=200/조건, 잡음=threshold의 15%)",
              color=TEXT, fontsize=12, loc="left")
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
ax.spines["left"].set_color(GRID)
ax.spines["bottom"].set_color(GRID)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=2, frameon=False, fontsize=9)

fig.tight_layout()
fig.savefig("fig_sensitivity_specificity.png", dpi=150, bbox_inches="tight")
print("저장 완료: fig_sensitivity_specificity.png")
