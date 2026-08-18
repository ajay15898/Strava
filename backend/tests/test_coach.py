"""The coach's numeric guard.

The prompt asks the model not to invent numbers. This tests the part that does
not depend on the model complying.
"""

from __future__ import annotations

import pytest

from app.coach.prompt import build_messages, templated_summary
from app.coach.verify import allowed_tokens, verify

# Shaped like the real thing, with this athlete's actual figures.
CONTEXT = {
    "generated_for_date": "2026-08-18",
    "athlete": {
        "goal_time_s": 7200,
        "goal_race_date": "2026-10-04",
        "goal_race_distance_m": 21097.5,
        "weeks_out": 6.7,
    },
    "fitness": {
        "weekly_km_2wk": 23.63,
        "weekly_km_4wk": 13.58,
        "longest_run_m": 15008.8,
        "best_efforts_s": {"5K": 1518, "10K": 3667},
        "tsb": -10.94,
        "has_recent_heartrate": False,
    },
    "prediction": {
        "predicted_time_s": 7268,
        "blended_s": 6977,
        "durability_penalty_pct": 4.16,
        "reference_date": "2026-08-15",
    },
    "feasibility": {"verdict": "tight", "limiting_factor": "long_run_durability"},
    "plan": {
        "current_week_no": 1,
        "weeks": 7,
        "peak_weekly_km": 40.6,
        "this_week": [
            {"date": "2026-08-22", "session_type": "long", "target_distance_m": 15000.0,
             "status": "planned", "target_pace_low": 379.5, "target_pace_high": 409.0},
        ],
    },
    "adaptations": [],
    "flags": ["no_heart_rate_data"],
}


# --- what must pass --------------------------------------------------------


def test_plain_context_numbers_pass():
    assert verify("Your last two weeks averaged 23.63 km per week.", CONTEXT).ok


def test_rounded_forms_pass():
    """A coach writing 23.6 rather than 23.63 is formatting, not inventing."""
    assert verify("You averaged 23.6 km last fortnight.", CONTEXT).ok


def test_seconds_rendered_as_a_clock_pass():
    """7268 s is 2:01:08, and 1518 s is 25:18."""
    result = verify("Projected 2:01:08, from a 25:18 5K.", CONTEXT)
    assert result.ok, result.violations


def test_metres_rendered_as_kilometres_pass():
    """15008.8 m is 15.01 km, or 15.0."""
    assert verify("Your longest run is 15.01 km.", CONTEXT).ok
    assert verify("Your longest run is 15.0 km.", CONTEXT).ok


def test_pace_seconds_rendered_as_pace_pass():
    """379.5 s/km is 6:19, 409.0 is 6:49."""
    assert verify("Run Saturday at 6:19 to 6:49 per km.", CONTEXT).ok


def test_dates_present_in_context_pass():
    assert verify("Your long run is on 2026-08-22.", CONTEXT).ok


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


def test_arithmetic_the_model_did_itself_is_caught():
    """7268 - 7200 = 68. Correct, and still rejected: the coach does not compute."""
    result = verify("You are 68 seconds off the goal.", CONTEXT)
    assert not result.ok
    assert any(v.token == "68" for v in result.violations)


def test_violations_are_deduplicated():
    result = verify("99.9 here, and 99.9 again, and 99.9 once more.", CONTEXT)
    assert [v.token for v in result.violations] == ["99.9"]


def test_the_failure_message_names_the_tokens():
    result = verify("You will run 1:45:00.", CONTEXT)
    assert "1:45:00" in result.message()


# --- the fallback ----------------------------------------------------------


def test_the_templated_summary_passes_its_own_verifier():
    """The fallback exists for when the model fails the guard twice.

    If the fallback itself could not pass, there would be no safe answer left,
    so this is the single most load-bearing test in the module.
    """
    summary = templated_summary(CONTEXT)
    result = verify(summary, CONTEXT)
    assert result.ok, f"fallback failed its own guard: {result.violations}"
    assert "tight" in summary
    assert len(summary) > 80


def test_the_templated_summary_survives_a_sparse_context():
    thin = {"athlete": {"goal_time_s": 7200}, "fitness": {}, "flags": []}
    summary = templated_summary(thin)
    assert verify(summary, thin).ok


# --- prompt assembly -------------------------------------------------------


def test_context_is_sent_and_the_rule_is_stated():
    messages = build_messages(CONTEXT, "How am I doing?")
    assert messages[0]["role"] == "system"
    assert "EVERY number in your response must appear in the CONTEXT" in messages[0]["content"]
    assert "7268" in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": "How am I doing?"}


def test_history_is_placed_between_context_and_question():
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
    messages = build_messages(CONTEXT, "now", history)
    assert messages[2:4] == history
    assert messages[-1]["content"] == "now"


# --- allowed set -----------------------------------------------------------


def test_allowed_set_covers_nested_values():
    numbers, clocks, dates = allowed_tokens(CONTEXT)
    assert "1518" in numbers          # nested two levels deep
    assert "25:18" in clocks
    assert "2026-08-22" in dates      # inside a list of dicts


def test_booleans_are_not_treated_as_numbers():
    numbers, _, _ = allowed_tokens({"flag": True, "other": False})
    assert "1" in numbers  # from the prose-safe set, not from True
    assert "0" in numbers
    assert len(numbers) == 4  # exactly the prose-safe set


@pytest.mark.parametrize("token", ["7200", "7268", "40.6", "4.16", "15008.8"])
def test_every_scalar_in_context_is_allowed(token):
    numbers, _, _ = allowed_tokens(CONTEXT)
    assert token in numbers
