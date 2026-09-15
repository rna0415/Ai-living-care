"""
make_eval_figures.py — eval_report.m과 같은 입력(eval_results.json)으로 같은 3장을 만든다.
MATLAB이 없는 환경에서의 대체 경로. 파일명도 eval_report.m과 동일하게 맞춰서
report.md/PPT가 어느 쪽으로 만든 그림이든 그대로 참조할 수 있게 했다.
"""

import json

import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"  # 한글 라벨
plt.rcParams["axes.unicode_minus"] = False

# dataviz 스킬 기본 팔레트(references/palette.md) — 카테고리 슬롯 순서 고정
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
RED = "#e34948"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e3e2dd"

with open("eval_results.json", encoding="utf-8") as f:
    data = json.load(f)

cases = data["cases"]
metrics = data["metrics"]


def _style_ax(ax):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _label_bars(ax, bars, fmt="{:.0f}%"):
    for b in bars:
        h = b.get_height()
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10, color=TEXT)


# ── 1. 핵심 지표 ──
fig, ax = plt.subplots(figsize=(5, 4))
labels = ["정책 적합률", "실제 작업 성공률"]
values = [metrics["policy_fit_rate"] * 100, metrics["task_success_rate"] * 100]
bars = ax.bar(labels, values, width=0.5, color=[BLUE, AQUA])
ax.set_ylim(0, 110)
ax.set_ylabel("%", color=MUTED)
ax.set_title("핵심 성능 지표", color=TEXT, fontsize=13, loc="left")
_style_ax(ax)
_label_bars(ax, bars)
fig.tight_layout()
fig.savefig("fig_core_metrics.png", dpi=150)
plt.close(fig)

# ── 2. 필드별 오류율 ──
fig, ax = plt.subplots(figsize=(7, 4))
fields = list(metrics["field_error_rate"].keys())
err = [metrics["field_error_rate"][f] * 100 for f in fields]
bars = ax.bar(fields, err, width=0.55, color=RED)
ax.set_ylim(0, max(10, max(err) + 5))
ax.set_ylabel("오류율 (%)", color=MUTED)
ax.set_title("필드별 오류율", color=TEXT, fontsize=13, loc="left")
plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
_style_ax(ax)
_label_bars(ax, bars, fmt="{:.1f}%")
fig.tight_layout()
fig.savefig("fig_field_error_rate.png", dpi=150)
plt.close(fig)

# ── 3. persona별 정책 적합률 + 개인화 신호(위험 복용약 flag 수) ──
subject_ids = sorted({c["subject_id"] for c in cases})
short_name = {
    "subj:kim_oksun_001": "김옥순(취약)",
    "subj:park_malsun_002": "박말순(비취약)",
    "subj:lee_gapsu_003": "이갑수(취약)",
}
fit_by_subject, medflag_by_subject = [], []
for sid in subject_ids:
    sub_cases = [c for c in cases if c["subject_id"] == sid]
    fit_by_subject.append(sum(c["all_pass"] for c in sub_cases) / len(sub_cases) * 100)
    medflag_by_subject.append(len(sub_cases[0]["result"]["medication_flags"]))

labels3 = [short_name.get(sid, sid) for sid in subject_ids]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

bars1 = ax1.bar(labels3, fit_by_subject, width=0.55, color=BLUE)
ax1.set_ylim(0, 110)
ax1.set_ylabel("%", color=MUTED)
ax1.set_title("persona별 정책 적합률", color=TEXT, fontsize=12, loc="left")
plt.setp(ax1.get_xticklabels(), rotation=20, ha="right")
_style_ax(ax1)
_label_bars(ax1, bars1)

bars2 = ax2.bar(labels3, medflag_by_subject, width=0.55, color=ORANGE)
ax2.set_ylim(0, max(medflag_by_subject) + 1)
ax2.set_ylabel("개수", color=MUTED)
ax2.set_title("persona별 개인화 신호(위험 복용약 flag 수)", color=TEXT, fontsize=12, loc="left")
plt.setp(ax2.get_xticklabels(), rotation=20, ha="right")
_style_ax(ax2)
_label_bars(ax2, bars2, fmt="{:.0f}")

fig.tight_layout()
fig.savefig("fig_persona_comparison.png", dpi=150)
plt.close(fig)

print("저장 완료: fig_core_metrics.png, fig_field_error_rate.png, fig_persona_comparison.png")
