"""The coach's numeric guard.

The prompt asks the model not to invent numbers. This tests the part that does
not depend on the model complying.
"""

from __future__ import annotations

import pytest

from app.coach.prompt import build_messages, templated_summary
from app.coach.verify import allowed_tokens, verify

# The display-first shape the context actually has: times as clocks, distances
# in kilometres, paces as bands. Raw seconds and metres are deliberately absent
# — a model cannot print units it was never given.
CONTEXT = {
    "generated_for_date": "2026-08-19",
    "athlete": {
        "goal_time": "2:00:00",
        "goal_pace_per_km": "5:41",
        "goal_race_date": "2026-10-04",
        "goal_race_distance_km": 21.1,
        "weeks_out": 6.6,
        "runs_per_week": 4,
    },
    "fitness": {
        "avg_km_per_week_last_2_weeks": 26.13,
        "avg_km_per_week_last_4_weeks": 14.83,
        "longest_run_ever_km": 15.01,
        "best_efforts": {"5K": "25:18", "10K": "1:01:07"},
        "tsb": -10.94,
        "has_recent_heartrate": False,
    },
    "prediction": {
        "predicted_finish_time": "2:01:08",
        "predicted_pace_per_km": "5:44",
        "blended_before_penalty": "1:56:17",
        "durability_penalty_pct": 4.16,
        "based_on_effort": "5K",
        "based_on_time": "25:18",
        "based_on_date": "2026-08-15",
    },
    "feasibility": {
        "verdict": "tight",
        "limiting_factor": "long run durability",
        "current_weekly_km": 14.83,
        "predicted_finish_time": "2:01:08",
    },
    "plan": {
        "current_week_no": 1,
        "weeks": 7,
        "peak_weekly_km": 40.6,
        "this_week": [
            {
                "date": "2026-08-22",
                "session_type": "long",
                "target_distance_km": 15.0,
                "target_pace_per_km": "6:20-6:50",
                "status": "planned",
            }
        ],
    },
    "adaptations": [],
    "flags": ["no_heart_rate_data"],
}


# --- what must pass --------------------------------------------------------


def test_plain_context_numbers_pass():
    assert verify("Your last two weeks averaged 26.13 km per week.", CONTEXT).ok


def test_rounded_forms_pass():
    """A coach writing 26.1 rather than 26.13 is formatting, not inventing."""
    assert verify("You averaged 26.1 km last fortnight.", CONTEXT).ok


def test_clock_values_from_the_context_pass():
    assert verify("Projected 2:01:08, from a 25:18 5K.", CONTEXT).ok


def test_pace_bands_pass():
    assert verify("Run Saturday at 6:20 to 6:50 per km.", CONTEXT).ok


def test_dates_present_in_context_pass():
    assert verify("Your long run is on 2026-08-22.", CONTEXT).ok


def test_date_components_are_quotable():
    """"22 August 2026" quotes a context date rather than inventing numbers."""
    assert verify("Your long run is on 22 August 2026.", CONTEXT).ok
    assert verify("Race day is 04/10/2026.", CONTEXT).ok


def test_ordinals_are_prose_not_claims():
    assert verify("This is your 1st week of the block.", CONTEXT).ok


def test_a_response_with_no_numbers_passes():
    assert verify("Keep the easy runs genuinely easy.", CONTEXT).ok


# --- what must fail --------------------------------------------------------


def test_an_invented_number_is_caught():
    result = verify("You averaged 31.4 km per week.", CONTEXT)
    assert not result.ok
    assert any(v.token == "31.4" for v in result.violations)


def test_an_invented_finish_time_is_caught():
    result = verify("You are on track for 1:52:30.", CONTEXT)
    assert not result.ok
    assert any(v.token == "1:52:30" for v in result.violations)


def test_an_invented_date_is_caught():
    result = verify("Your race is on 2026-11-29.", CONTEXT)
    assert not result.ok
    assert any(v.token == "2026-11-29" for v in result.violations)


def test_a_date_not_in_context_fails_in_any_format():
    result = verify("Your race is on 29 November 2026.", CONTEXT)
    assert not result.ok
    assert any(v.token == "29" for v in result.violations)


def test_arithmetic_the_model_did_itself_is_caught():
    """The coach does not compute, even when the arithmetic is right."""
    result = verify("That is 68 seconds off the goal.", CONTEXT)
    assert not result.ok
    assert any(v.token == "68" for v in result.violations)


def test_violations_are_deduplicated():
    result = verify("99.9 here, and 99.9 again, and 99.9 once more.", CONTEXT)
    assert [v.token for v in result.violations] == ["99.9"]


def test_the_failure_message_names_the_tokens():
    assert "1:45:00" in verify("You will run 1:45:00.", CONTEXT).message()


# --- the fallback ----------------------------------------------------------


def test_the_templated_summary_passes_its_own_verifier():
    """If the fallback could not pass, there would be no safe answer left."""
    summary = templated_summary(CONTEXT)
    result = verify(summary, CONTEXT)
    assert result.ok, f"fallback failed its own guard: {result.violations}"


def test_the_fallback_actually_says_something():
    """The guard cannot tell a useful answer from an empty one.

    When the context shape changed underneath it, the fallback degraded to
    "Projected unknown ... None km/week" and the verifier passed it happily,
    because absent text has no numbers to object to. Emptiness needs its own
    check.
    """
    summary = templated_summary(CONTEXT)
    assert "unknown" not in summary.lower()
    assert "None" not in summary
    assert "2:01:08" in summary          # the projection
    assert "2:00:00" in summary          # the goal
    assert "26.13" in summary            # recent volume
    assert "15.01" in summary            # longest run
    assert "tight" in summary            # the verdict


def test_the_fallback_names_what_is_missing_rather_than_inventing():
    thin = {"athlete": {}, "fitness": {}, "flags": []}
    summary = templated_summary(thin)
    assert verify(summary, thin).ok
    assert "No data available for" in summary
    assert "prediction" in summary


# --- prompt assembly -------------------------------------------------------


def test_context_is_sent_and_the_rule_is_stated():
    messages = build_messages(CONTEXT, "How am I doing?")
    assert messages[0]["role"] == "system"
    assert "EVERY number in your response must appear in the CONTEXT" in messages[0]["content"]
    assert "2:01:08" in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": "How am I doing?"}


def test_context_is_serialised_without_indentation():
    """Whitespace is pure token cost against an 8000/minute ceiling."""
    payload = build_messages(CONTEXT, "hi")[1]["content"]
    assert '":' in payload or '":' in payload
    assert "\n " not in payload.split("CONTEXT:\n", 1)[1]


def test_history_is_placed_between_context_and_question():
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
    messages = build_messages(CONTEXT, "now", history)
    assert messages[2:4] == history
    assert messages[-1]["content"] == "now"


# --- allowed set -----------------------------------------------------------


def test_allowed_set_covers_nested_values_and_strings():
    numbers, clocks, dates = allowed_tokens(CONTEXT)
    assert "25:18" in clocks          # a string, nested two levels deep
    assert "40.6" in numbers          # a scalar inside plan
    assert "2026-08-22" in dates      # inside a list of dicts


def test_booleans_are_not_treated_as_numbers():
    numbers, _, _ = allowed_tokens({"flag": True, "other": False})
    assert len(numbers) == 4  # exactly the prose-safe set


@pytest.mark.parametrize("token", ["26.13", "14.83", "15.01", "40.6", "4.16", "21.1"])
def test_every_scalar_in_context_is_allowed(token):
    numbers, _, _ = allowed_tokens(CONTEXT)
    assert token in numbers
