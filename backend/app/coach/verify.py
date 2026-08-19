"""Numeric grounding check.

The coach may paraphrase, prioritise and explain. It may not produce a number
that is not in the context it was given. This module enforces that by
extracting every numeric token from the response and asserting membership in a
set derived from the context — a prompt instruction alone is not a control.

That is what makes a free-tier model acceptable here: capability determines how
fluent the answer reads, not whether the numbers in it are true.

The allowed set contains formattings of real context values, not arbitrary
numbers. A collision is possible — 4.16 rounds to "4", so a stray "4" passes —
but the guard exists to stop fabrication, not ambiguity, and every string in
the set traces back to a value that was actually computed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Dates first: they contain digits that would otherwise read as bare numbers.
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
CLOCK = re.compile(r"\b\d{1,3}:\d{2}(?::\d{2})?\b")
NUMBER = re.compile(r"\d+(?:\.\d+)?")

# Ordinals and small counts that are prose rather than claims. Kept tiny and
# explicit — this is the one place a loophole could hide.
PROSE_SAFE = {"0", "1", "2", "3"}


@dataclass
class Violation:
    token: str
    kind: str  # date | clock | number

    def __str__(self) -> str:
        return f"{self.token} ({self.kind})"


@dataclass
class Result:
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    allowed_sample: list[str] = field(default_factory=list)

    def message(self) -> str:
        listed = ", ".join(str(v) for v in self.violations)
        return f"Response contained values not present in the context: {listed}"


def _walk(node: object) -> list[float]:
    """Every scalar anywhere in the context, at any depth."""
    out: list[float] = []
    if isinstance(node, bool):
        return out
    if isinstance(node, (int, float)):
        out.append(float(node))
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_walk(value))
    elif isinstance(node, (list, tuple)):
        for value in node:
            out.extend(_walk(value))
    return out


def _collect_text_tokens(node: object) -> tuple[set[str], set[str]]:
    """Numbers and clock times embedded in the context's own strings and keys.

    `best_efforts_s: {"5K": 1518}` puts "5K" in the context, so a coach writing
    "your 5K" is quoting, not inventing. The same applies to plan warnings,
    which quote figures like "8%" and "20 km" in prose. Anything spelled out in
    the context is fair for the model to spell back.
    """
    numbers: set[str] = set()
    clocks: set[str] = set()

    def harvest(text: str) -> None:
        clocks.update(CLOCK.findall(text))
        # A date in the context legitimises its parts. The model may write
        # "22 August 2026" or "08/22" rather than the ISO form, and those
        # digits are a quotation, not an invention.
        for iso in ISO_DATE.findall(text):
            year, month, day = iso.split("-")
            numbers.update({year, month, day, str(int(month)), str(int(day))})
        stripped = CLOCK.sub(" ", ISO_DATE.sub(" ", text))
        numbers.update(NUMBER.findall(stripped))

    if isinstance(node, str):
        harvest(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                harvest(key)
            n, c = _collect_text_tokens(value)
            numbers |= n
            clocks |= c
    elif isinstance(node, (list, tuple)):
        for value in node:
            n, c = _collect_text_tokens(value)
            numbers |= n
            clocks |= c

    return numbers, clocks


def _collect_dates(node: object) -> set[str]:
    out: set[str] = set()
    if isinstance(node, str):
        out.update(ISO_DATE.findall(node))
    elif isinstance(node, dict):
        for value in node.values():
            out |= _collect_dates(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            out |= _collect_dates(value)
    return out


def _clock_forms(seconds: float) -> set[str]:
    """m:ss and h:mm:ss, the two formattings the API itself emits."""
    out: set[str] = set()
    if seconds <= 0 or seconds > 86400:
        return out

    total = int(round(seconds))
    for value in {total, int(seconds)}:
        m, s = divmod(value, 60)
        out.add(f"{m}:{s:02d}")
        h, rem = divmod(value, 3600)
        mm, ss = divmod(rem, 60)
        out.add(f"{h}:{mm:02d}:{ss:02d}")
        if h:
            out.add(f"{h}:{mm:02d}")
    return out


def _number_forms(value: float) -> set[str]:
    out: set[str] = set()
    for text in (
        f"{value:.0f}",
        f"{value:.1f}",
        f"{value:.2f}",
        f"{value:.3f}",
        repr(value),
        str(value),
    ):
        out.add(text)
        if "." in text:
            out.add(text.rstrip("0").rstrip("."))
    return out


def allowed_tokens(context: dict) -> tuple[set[str], set[str], set[str]]:
    """(numbers, clock times, dates) the response is permitted to contain."""
    scalars = _walk(context)

    numbers: set[str] = set(PROSE_SAFE)
    clocks: set[str] = set()

    for value in scalars:
        numbers |= _number_forms(value)
        # Seconds -> clock. Applied to every scalar rather than guessing which
        # fields are durations; a false extra form is harmless, a missing one
        # rejects a correct answer.
        clocks |= _clock_forms(value)
        # Metres -> kilometres, the one unit conversion the formatter may do.
        if abs(value) >= 100:
            numbers |= _number_forms(value / 1000)
        # Fractions -> percentages.
        if 0 < abs(value) <= 1:
            numbers |= _number_forms(value * 100)

    text_numbers, text_clocks = _collect_text_tokens(context)
    numbers |= text_numbers
    clocks |= text_clocks

    return numbers, clocks, _collect_dates(context)


def verify(response: str, context: dict) -> Result:
    numbers, clocks, dates = allowed_tokens(context)
    violations: list[Violation] = []
    remaining = response

    for token in ISO_DATE.findall(remaining):
        if token not in dates:
            violations.append(Violation(token, "date"))
    remaining = ISO_DATE.sub(" ", remaining)

    for token in CLOCK.findall(remaining):
        if token not in clocks:
            violations.append(Violation(token, "clock"))
    remaining = CLOCK.sub(" ", remaining)

    # Ordinals ("1st", "2nd") and week/day words are prose, not claims.
    remaining = re.sub(r"\b(\d+)(st|nd|rd|th)\b", " ", remaining)

    for token in NUMBER.findall(remaining):
        if token not in numbers:
            violations.append(Violation(token, "number"))

    # Deduplicate while preserving order, so the retry message stays readable.
    seen: set[str] = set()
    unique = [v for v in violations if not (v.token in seen or seen.add(v.token))]

    return Result(
        ok=not unique,
        violations=unique,
        allowed_sample=sorted(list(numbers))[:12],
    )
