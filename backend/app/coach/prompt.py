"""The prompt contract, and the deterministic fallback when it is not honoured.

The fallback is not an edge case. Free-tier models trip the verifier more often
than frontier ones, so `templated_summary` is a normal code path and is written
to be genuinely useful on its own rather than as an apology.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You are the coaching layer of a running app called Pace. You are talking to one \
athlete about their own training data.

You will be given a CONTEXT object containing everything known about this \
athlete: their fitness, their plan, what they have actually run, and the \
verdicts a deterministic engine has already computed.

Rules, in order of importance:

1. EVERY number in your response must appear in the CONTEXT. Do not compute, \
convert, estimate, average, or extrapolate. If you want to say a number, find \
it in the CONTEXT first. This is checked automatically after you answer, and a \
response containing an invented number is discarded.
2. If the CONTEXT cannot answer the question, say plainly which data is \
missing. Do not guess.
3. Never advise training through pain, and never suggest exceeding the volume \
or intensity in the plan.
4. Cite the session or activity you are referring to by its date.
5. Quote the engine's verdicts rather than reinterpreting them. If feasibility \
says "tight", the answer is tight — do not soften it to "on track" or harden \
it to "impossible".

Style: direct and specific. Short paragraphs. No emoji, no bullet-point walls, \
no cheerleading. Write like a coach who respects the athlete's time and has \
read their data properly. If something in the data is concerning, say so \
plainly rather than burying it."""


def build_messages(context: dict, question: str, history: list[dict] | None = None) -> list[dict]:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "CONTEXT:\n" + json.dumps(context, separators=(",", ":"), default=str),
        },
    ]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})
    return messages


def retry_instruction(violations: str) -> dict:
    """Named-violation retry. One attempt, then the template takes over."""
    return {
        "role": "system",
        "content": (
            f"Your previous answer was rejected. {violations}. "
            f"Rewrite it using only values that appear in the CONTEXT object. "
            f"If you cannot support a claim with a number from the CONTEXT, "
            f"omit the number and say what is missing instead."
        ),
    }


def templated_summary(context: dict) -> str:
    """Deterministic answer, assembled from the context with no model call.

    Used when the model twice fails the numeric check. Every value comes
    straight from the context, so it passes verification by construction.

    Reads the display-formatted fields, which is also why `missing` is tracked:
    when the context shape changed underneath this function it degraded to
    "unknown" and "None" — and the verifier passed it, because absent text has
    no numbers to object to. A guard against fabrication is not a guard against
    emptiness, so that has to be checked separately.
    """
    lines: list[str] = []
    missing: list[str] = []

    fitness = context.get("fitness") or {}
    prediction = context.get("prediction") or {}
    feasibility = context.get("feasibility") or {}
    plan = context.get("plan") or {}
    athlete = context.get("athlete") or {}

    predicted = prediction.get("predicted_finish_time")
    goal = athlete.get("goal_time")
    if predicted and goal:
        lines.append(
            f"Projected {predicted} for the half marathon against a goal of {goal}. "
            f"The engine calls this {feasibility.get('verdict', 'unrated')}, limited by "
            f"{feasibility.get('limiting_factor', 'nothing in particular')}."
        )
    else:
        missing.append("prediction")

    two_wk = fitness.get("avg_km_per_week_last_2_weeks")
    four_wk = fitness.get("avg_km_per_week_last_4_weeks")
    longest = fitness.get("longest_run_ever_km")
    if two_wk is not None and four_wk is not None:
        lines.append(
            f"Recent volume is {two_wk} km/week over the last two weeks and "
            f"{four_wk} km/week over four."
            + (f" Longest run on record is {longest} km." if longest else "")
        )
    else:
        missing.append("volume")

    if plan.get("this_week"):
        done = sum(1 for s in plan["this_week"] if s.get("status") == "done")
        lines.append(
            f"Week {plan.get('current_week_no')} of {plan.get('weeks')}: "
            f"{done} of {len(plan['this_week'])} sessions completed."
        )

    actionable = [
        a for a in (context.get("adaptations") or [])
        if a.get("severity") in {"action", "warning"}
    ]
    if actionable:
        lines.append("Open flags: " + " ".join(a["message"] for a in actionable))

    if missing:
        lines.append(f"No data available for: {', '.join(missing)}.")

    lines.append(
        "This is a generated summary — the coaching model could not answer within "
        "the data it was given, so these figures come straight from the training "
        "engine."
    )
    return "\n\n".join(lines)
