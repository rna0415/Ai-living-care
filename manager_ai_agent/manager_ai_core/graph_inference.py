"""Pure graph-inference orchestration for Manager AI Core.

The function consumes contexts already resolved through the caller's approved
boundary (IF-1 in production).  It intentionally performs no Neo4j/file access,
does not synthesize mock observations, and stops before L2 policy generation.
"""

from __future__ import annotations

from collections.abc import Mapping

from manager_ai_agent.manager_ai_core.kg_mapping.axis_routing import (
    AxisScorer,
    DEFAULT_THRESHOLD,
    route_axes,
)
from manager_ai_agent.manager_ai_core.policy_generation.rule_evaluator import evaluate


def infer_from_contexts(
    query: str,
    *,
    hour: int,
    contexts_by_axis: Mapping[str, Mapping],
    observations_by_axis: Mapping[str, Mapping],
    scorer: AxisScorer | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Route a query and evaluate every active, pre-resolved axis context.

    ``contexts_by_axis`` must be supplied by the caller; this module does not
    cross the KG boundary.  Missing contexts and observations remain missing in
    the result so an upstream policy layer can ask for data instead of treating
    invented defaults as evidence.  ``inference_status`` preserves any real
    escalation while ``complete`` reports missing or indeterminate evidence.
    """

    if not isinstance(contexts_by_axis, Mapping):
        raise TypeError("contexts_by_axis must be a mapping")
    if not isinstance(observations_by_axis, Mapping):
        raise TypeError("observations_by_axis must be a mapping")

    routing = route_axes(query, scorer=scorer, threshold=threshold)
    results: list[dict] = []
    missing_context_axis_ids: list[str] = []
    context_issues: list[dict] = []

    for axis_id in routing["active_axis_ids"]:
        context = contexts_by_axis.get(axis_id)
        if context is None:
            missing_context_axis_ids.append(axis_id)
            continue
        if not isinstance(context, Mapping):
            raise TypeError(f"context for {axis_id} must be a mapping")

        declared_axis_id = context.get("axis_id", axis_id)
        if declared_axis_id != axis_id:
            raise ValueError(
                f"context axis mismatch: routed {axis_id!r}, received {declared_axis_id!r}"
            )

        context_source = context.get("source")
        if not isinstance(context_source, str) or not context_source.strip():
            context_issues.append(
                {"axis_id": axis_id, "reason": "context source must be a non-empty string"}
            )

        rules = context.get("rules", [])
        if not isinstance(rules, (list, tuple)):
            raise TypeError(f"rules for {axis_id} must be a list or tuple")

        observations = observations_by_axis.get(axis_id, {})
        if not isinstance(observations, Mapping):
            raise TypeError(f"observations for {axis_id} must be a mapping")

        results.append(
            {
                "axis_id": axis_id,
                "label": context.get("label", axis_id),
                "context_source": context_source,
                "observations": dict(observations),
                "evaluation": evaluate(rules, observations, hour),
            }
        )

    evaluation_statuses = {
        result["evaluation"]["evaluation_status"] for result in results
    }
    complete = not (
        missing_context_axis_ids
        or context_issues
        or "indeterminate" in evaluation_statuses
    )
    if "escalate" in evaluation_statuses:
        inference_status = "escalate"
    elif not complete:
        inference_status = "indeterminate"
    else:
        inference_status = "no_escalation"

    return {
        "query": query,
        "routing": routing,
        "missing_context_axis_ids": missing_context_axis_ids,
        "context_issues": context_issues,
        "inference_status": inference_status,
        "complete": complete,
        "results": results,
    }
