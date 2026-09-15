"""make_advanced_figures.py -> fig_response_curve.png, fig_noise_sensitivity.png"""

import json

import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e3e2dd"


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


# ---- 1. 반응 곡선 (100%가 의심스럽다는 지적에 대한 직접 증거) ----
with open("eval_roc_curve_results.json", encoding="utf-8") as f:
    roc = json.load(f)

fig, ax = plt.subplots(figsize=(8, 5))
colors = [BLUE, ORANGE, AQUA]
for (name, data), color in zip(roc.items(), colors):
    xs = [r["ratio"] for r in data["curve"]]
    ys = [r["escalate_rate"] * 100 for r in data["curve"]]
    ax.plot(xs, ys, marker="o", markersize=4, linewidth=2, color=color, label=name)

ax.axvline(1.0, color=MUTED, linestyle="--", linewidth=1)
ax.axhline(50, color=MUTED, linestyle=":", linewidth=1)
ax.text(1.02, 5, "threshold", color=MUTED, fontsize=9)
ax.set_xlabel("참값 / threshold 비율", color=MUTED)
ax.set_ylabel("escalate율 (%)", color=MUTED)
ax.set_title("경계값 반응 곡선 — 3개 구간이 아니라 18단계 연속 스윕 (N=300/점)",
              color=TEXT, fontsize=12, loc="left")
_style(ax)
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig("fig_response_curve.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---- 2. 잡음 크기 vs 특이도, CDS 문헌 범위와 비교 ----
with open("eval_noise_sensitivity_results.json", encoding="utf-8") as f:
    ns = json.load(f)

sweep = ns["noise_sweep"]
xs = [r["noise_frac"] * 100 for r in sweep]
ys = [r["specificity"] * 100 for r in sweep]
lo, hi = [v * 100 for v in ns["cds_spec_range"]]

fig, ax = plt.subplots(figsize=(8, 5))
ax.axhspan(lo, hi, color=RED, alpha=0.12, label=f"CDS 문헌 특이도 범위 ({lo:.0f}~{hi:.0f}%)")
ax.plot(xs, ys, marker="o", markersize=4, linewidth=2, color=BLUE, label="우리 시스템(해석적 정확값)")
ax.axvline(15, color=MUTED, linestyle="--", linewidth=1)
ax.text(16, 100.5, "실제 사용한 잡음(15%)", color=MUTED, fontsize=9, va="top")

ax.set_xlabel("센서 잡음 크기 (threshold 대비 표준편차 %)", color=MUTED)
ax.set_ylabel("특이도 (%)", color=MUTED)
ax.set_title("잡음 크기별 특이도 — 문헌 수준까지 떨어지려면 잡음이 얼마나 커야 하나",
              color=TEXT, fontsize=12, loc="left")
ax.set_ylim(65, 102)
_style(ax)
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=9)
fig.tight_layout()
fig.savefig("fig_noise_sensitivity.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("저장 완료: fig_response_curve.png, fig_noise_sensitivity.png")
