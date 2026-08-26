"""Natural-language routing to the graph inference axes.

This is the dependency-free subset of ``mac/graph-inference``'s embedding
router.  The default scorer is deliberately deterministic and conservative;
an embedding scorer can be injected later without importing a model at module
load time.

Routing is only a pre-filter.  It does not replace IF-1 entity/binding
resolution and never reads the Knowledge Graph directly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AxisDefinition:
    """One routable ontology axis and its deterministic fallback keywords."""

    axis_id: str
    label: str
    keywords: tuple[str, ...]


ONTO_AXES = (
    AxisDefinition(
        axis_id="onto:saref/WellBeing",
        label="WellBeing",
        keywords=(
            "할머니",
            "할아버지",
            "안부",
            "괜찮",
            "웰빙",
            "무동작",
            "활동 여부",
            "건강",
        ),
    ),
    AxisDefinition(
        axis_id="onto:saref/Safety",
        label="Safety",
        keywords=(
            "가스",
            "연기",
            "화재",
            "낙상",
            "쓰러",
            "침입",
            "문 열",
            "위험",
            "안전",
            "비상",
        ),
    ),
    AxisDefinition(
        axis_id="onto:saref/Comfort",
        label="Comfort",
        keywords=(
            "온도",
            "습도",
            "조명",
            "쾌적",
            "추워",
            "추운",
            "더워",
            "더운",
            "난방",
            "냉방",
        ),
    ),
)

DEFAULT_THRESHOLD = 0.5
AxisScorer = Callable[[str], Mapping[str, float]]


def _keyword_scores(text: str) -> dict[str, float]:
    normalized = " ".join(text.casefold().split())
    scores: dict[str, float] = {}

    for axis in ONTO_AXES:
        matches = sum(keyword in normalized for keyword in axis.keywords)
        scores[axis.axis_id] = 0.0 if matches == 0 else min(1.0, 0.5 + 0.15 * (matches - 1))

    return scores


def get_axis_scores(text: str, scorer: AxisScorer | None = None) -> dict[str, float]:
    """Return one finite score per known axis.

    Unknown axes returned by an injected scorer are ignored.  Missing known
    axes receive ``0.0`` so routing output remains stable across backends.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    raw_scores = scorer(text) if scorer is not None else _keyword_scores(text)
    if not isinstance(raw_scores, Mapping):
        raise TypeError("axis scorer must return a mapping")

    scores: dict[str, float] = {}
    for axis in ONTO_AXES:
        raw_score = raw_scores.get(axis.axis_id, 0.0)
        if isinstance(raw_score, bool):
            raise ValueError(f"invalid score for {axis.axis_id}")
        try:
            score = float(raw_score)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid score for {axis.axis_id}") from exc
        if not math.isfinite(score):
            raise ValueError(f"non-finite score for {axis.axis_id}")
        scores[axis.axis_id] = score

    return scores


def determine_active_axes(
    scores: Mapping[str, float],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[str]:
    """Return known axes at or above ``threshold``, highest score first."""

    if isinstance(threshold, bool):
        raise ValueError("threshold must be numeric, not boolean")
    threshold = float(threshold)
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be greater than 0 and at most 1")

    order = {axis.axis_id: index for index, axis in enumerate(ONTO_AXES)}
    active = [
        axis.axis_id
        for axis in ONTO_AXES
        if float(scores.get(axis.axis_id, 0.0)) >= threshold
    ]
    return sorted(active, key=lambda axis_id: (-float(scores[axis_id]), order[axis_id]))


def route_axes(
    text: str,
    *,
    scorer: AxisScorer | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Score and select graph axes without performing KG retrieval."""

    scores = get_axis_scores(text, scorer=scorer)
    return {
        "mode": "injected" if scorer is not None else "keyword",
        "threshold": float(threshold),
        "scores": scores,
        "active_axis_ids": determine_active_axes(scores, threshold),
    }
