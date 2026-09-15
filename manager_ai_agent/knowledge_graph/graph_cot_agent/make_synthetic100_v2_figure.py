"""make_synthetic100_v2_figure.py -> fig_english_strip_comparison.png"""

import json

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE, ORANGE, AQUA, RED, GREEN = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2dd"

with open("eval_synthetic_nl_100_v2_results.json", encoding="utf-8") as f:
    data = json.load(f)

base = data["baseline"]
strip = data["stripped"]
labels = base["labels"]

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# ---- 왼쪽: macro-F1 / accuracy 전체 비교 ----
ax = axes[0]
names = ["accuracy", "macro-F1"]
base_vals = [base["accuracy"] * 100, base["macro_f1"] * 100]
strip_vals = [strip["accuracy"] * 100, strip["macro_f1"] * 100]
x = np.arange(len(names))
w = 0.32
ax.bar(x - w / 2, base_vals, w, label="baseline(영어 그대로)", color=BLUE)
ax.bar(x + w / 2, strip_vals, w, label="stripped(영어 제거)", color=RED)
for xi, (b, s) in enumerate(zip(base_vals, strip_vals)):
    ax.annotate(f"{b:.1f}%", (xi - w / 2, b), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=10)
    ax.annotate(f"{s:.1f}%", (xi + w / 2, s), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=10)
ax.set_xticks(x)
ax.set_xticklabels(names)
ax.set_ylim(0, 65)
ax.set_title("① 전체 지표 — 영어 제거해도 거의 그대로(오히려 미세 하락)", fontsize=10.5, loc="left", color=TEXT)
ax.legend(frameon=False, fontsize=9)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)

# ---- 오른쪽: 클래스별 recall 변화 ----
ax = axes[1]
base_recall = [base["per_class_recall"][c] * 100 for c in labels]
strip_recall = [strip["per_class_recall"][c] * 100 for c in labels]
x = np.arange(len(labels))
ax.bar(x - w / 2, base_recall, w, label="baseline", color=BLUE)
ax.bar(x + w / 2, strip_recall, w, label="stripped", color=RED)
for xi, (b, s) in enumerate(zip(base_recall, strip_recall)):
    d = s - b
    color = GREEN if d > 0 else (RED if d < 0 else MUTED)
    ax.annotate(f"{d:+.0f}%p", (xi, max(b, s)), xytext=(0, 5), textcoords="offset points",
                ha="center", fontsize=9, color=color, fontweight="bold")
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
ax.set_ylim(0, 108)
ax.set_ylabel("recall (%)", color=MUTED)
ax.set_title("② 클래스별 recall — WellBeing +4%p, Safety -8%p (상쇄됨)", fontsize=10.5, loc="left", color=TEXT)
ax.legend(frameon=False, fontsize=9)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)

fig.suptitle("9.2절 제안(영어 전문용어 제거)을 실제로 적용한 결과 — 순효과는 거의 0(-1.0%p)",
             fontsize=12, y=1.02)
fig.tight_layout()
fig.savefig("fig_english_strip_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("저장 완료: fig_english_strip_comparison.png")
