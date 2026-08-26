"""Deterministic evaluation of graph-provided care rules.

The evaluator is the safe, dependency-free C2 subset selected from
``mac/graph-inference``.  Missing observations and unsupported rule shapes are
reported explicitly; neither is silently interpreted as a normal condition.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from numbers import Real
from typing import Literal


DEFAULT_ESCALATION_POLICY = {
    "min_concern_rules_triggered": 1,
    "min_mild_concern_rules_triggered": 2,
}

_SEVERITY_RANK = {"concern": 2, "mild_concern": 1, "info_only": 0}
_TIME_CONTEXTS = {"day", "night"}
_PREDICATE_FIELDS = (
    "immediate",
    "condition",
    "threshold_hours",
    "threshold_minutes",
    "threshold_celsius",
)
_RuleStatus = Literal["triggered", "not_triggered", "indeterminate", "unsupported"]


@dataclass(frozen=True)
class _RuleOutcome:
    status: _RuleStatus
    reason: str | None = None


def classify_time_context(hour: int) -> str:
    """Classify 22:00 through 05:59 as night."""

    if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError("hour must be an integer from 0 through 23")
    return "night" if hour >= 22 or hour < 6 else "day"


def _is_finite_number(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _validate_rule(rule: Mapping) -> str | None:
    rule_id = rule.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        return "rule_id must be a non-empty string"

    severity = rule.get("severity")
    if severity not in _SEVERITY_RANK:
        return f"unsupported severity: {severity!r}"

    if "time_context" in rule and rule["time_context"] not in _TIME_CONTEXTS:
        return f"unsupported time_context: {rule['time_context']!r}"

    predicates = [field for field in _PREDICATE_FIELDS if field in rule]
    if len(predicates) != 1:
        return "rule must define exactly one supported predicate"

    predicate = predicates[0]
    if predicate == "immediate":
        if rule[predicate] is not True:
            return "immediate predicate must be true"
        if not isinstance(rule.get("slot"), str) or not rule["slot"].strip():
            return "immediate predicate requires a non-empty slot"
        return None

    if predicate == "condition":
        if not isinstance(rule[predicate], str) or not rule[predicate].strip():
            return "condition must name a non-empty observation key"
        if "location" in rule and (
            not isinstance(rule["location"], str) or not rule["location"].strip()
        ):
            return "location must be a non-empty string"
        return None

    if not isinstance(rule.get("slot"), str) or not rule["slot"].strip():
        return "threshold predicate requires a non-empty slot"
    if not _is_finite_number(rule[predicate]):
        return f"{predicate} must be a finite number"
    if predicate == "threshold_celsius" and rule.get("direction") not in {
        "at_least",
        "below",
        "above",
    }:
        return f"unsupported direction: {rule.get('direction')!r}"
    return None


def _compare_numeric(value: object, threshold: object, *, direction: str) -> _RuleOutcome:
    if not _is_finite_number(value):
        return _RuleOutcome("indeterminate", "observation must be a finite number")
    if not _is_finite_number(threshold):
        return _RuleOutcome("unsupported", "threshold must be a finite number")
    if direction == "at_least":
        return _RuleOutcome("triggered" if value >= threshold else "not_triggered")
    if direction == "below":
        return _RuleOutcome("triggered" if value < threshold else "not_triggered")
    if direction == "above":
        return _RuleOutcome("triggered" if value > threshold else "not_triggered")
    return _RuleOutcome("unsupported", f"unsupported direction: {direction!r}")


def _evaluate_rule(rule: Mapping, observations: Mapping, time_context: str) -> _RuleOutcome:
    expected_time = rule.get("time_context")
    if expected_time and expected_time != time_context:
        return _RuleOutcome("not_triggered")

    slot = rule.get("slot")

    if "immediate" in rule:
        if slot not in observations or observations.get(slot) is None:
            return _RuleOutcome("indeterminate", f"missing observation: {slot!r}")
        if not isinstance(observations[slot], bool):
            return _RuleOutcome("indeterminate", "immediate observation must be boolean")
        return _RuleOutcome("triggered" if observations[slot] else "not_triggered")

    if "condition" in rule:
        condition_key = rule.get("condition")
        if condition_key not in observations:
            return _RuleOutcome("indeterminate", f"missing observation: {condition_key!r}")
        if not isinstance(observations[condition_key], bool):
            return _RuleOutcome("indeterminate", "condition observation must be boolean")
        if not observations[condition_key]:
            return _RuleOutcome("not_triggered")
        if rule.get("location"):
            if "location" not in observations:
                return _RuleOutcome("indeterminate", "missing observation: 'location'")
            if observations.get("location") != rule["location"]:
                return _RuleOutcome("not_triggered")
        return _RuleOutcome("triggered")

    threshold_fields = (
        ("threshold_hours", "at_least"),
        ("threshold_minutes", "at_least"),
        ("threshold_celsius", rule.get("direction", "")),
    )
    for field, direction in threshold_fields:
        if field not in rule:
            continue
        if slot not in observations or observations.get(slot) is None:
            return _RuleOutcome("indeterminate", f"missing observation: {slot!r}")
        return _compare_numeric(observations[slot], rule[field], direction=direction)

    return _RuleOutcome("unsupported", "rule has no supported condition or threshold")


def _diagnostic(rule: Mapping, reason: str | None) -> dict:
    return {"rule_id": rule.get("rule_id"), "reason": reason}


def _validated_policy(policy: Mapping | None) -> dict:
    if policy is not None and not isinstance(policy, Mapping):
        raise TypeError("policy must be a mapping")

    active_policy = dict(DEFAULT_ESCALATION_POLICY if policy is None else policy)
    required_policy_keys = set(DEFAULT_ESCALATION_POLICY)
    missing_policy_keys = required_policy_keys - active_policy.keys()
    if missing_policy_keys:
        raise ValueError(f"missing escalation policy keys: {sorted(missing_policy_keys)}")

    for key in required_policy_keys:
        value = active_policy[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{key} must be a positive integer")
    return active_policy


def evaluate(
    rules: Sequence[Mapping],
    observations: Mapping,
    hour: int,
    policy: Mapping | None = None,
) -> dict:
    """Evaluate rules and return triggered plus non-decidable evidence."""

    if isinstance(rules, (str, bytes)) or not isinstance(rules, Sequence):
        raise TypeError("rules must be a sequence of mappings")
    if not isinstance(observations, Mapping):
        raise TypeError("observations must be a mapping")

    time_context = classify_time_context(hour)
    active_policy = _validated_policy(policy)

    triggered: list[Mapping] = []
    indeterminate: list[dict] = []
    unsupported: list[dict] = []
    seen_rule_ids: set[str] = set()

    if not rules:
        indeterminate.append(_diagnostic({}, "no rules provided"))

    for rule in rules:
        if not isinstance(rule, Mapping):
            raise TypeError("each rule must be a mapping")
        validation_error = _validate_rule(rule)
        if validation_error:
            unsupported.append(_diagnostic(rule, validation_error))
            continue
        normalized_rule_id = rule["rule_id"].strip()
        if normalized_rule_id in seen_rule_ids:
            unsupported.append(_diagnostic(rule, "duplicate rule_id"))
            continue
        seen_rule_ids.add(normalized_rule_id)
        outcome = _evaluate_rule(rule, observations, time_context)
        if outcome.status == "triggered":
            triggered.append(rule)
        elif outcome.status == "indeterminate":
            indeterminate.append(_diagnostic(rule, outcome.reason))
        elif outcome.status == "unsupported":
            unsupported.append(_diagnostic(rule, outcome.reason))

    triggered.sort(key=lambda rule: _SEVERITY_RANK[rule["severity"]], reverse=True)
    concern_count = sum(rule.get("severity") == "concern" for rule in triggered)
    mild_count = sum(rule.get("severity") == "mild_concern" for rule in triggered)
    should_escalate = (
        concern_count >= active_policy["min_concern_rules_triggered"]
        or mild_count >= active_policy["min_mild_concern_rules_triggered"]
    )
    if should_escalate:
        evaluation_status = "escalate"
    elif indeterminate or unsupported:
        evaluation_status = "indeterminate"
    else:
        evaluation_status = "no_escalation"

    return {
        "time_context": time_context,
        "evaluation_status": evaluation_status,
        "triggered_rules": [
            {
                "rule_id": rule.get("rule_id"),
                "severity": rule.get("severity"),
                "rationale": rule.get("rationale"),
            }
            for rule in triggered
        ],
        "indeterminate_rules": indeterminate,
        "unsupported_rules": unsupported,
        "should_escalate": should_escalate,
        "highest_severity": triggered[0].get("severity") if triggered else None,
    }
