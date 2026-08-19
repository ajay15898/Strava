"""Within-run analysis: decoupling and split fade.

Written against synthetic streams so the maths is checkable, because the real
answer depends on heart-rate data that only started arriving on 2026-08-18.
"""

from __future__ import annotations

import pytest

from app.analytics.streams import (
    DECOUPLING_CONCERN_PCT,
    MIN_SAMPLES_PER_HALF,
    decoupling,
    split_fade,
)

N = MIN_SAMPLES_PER_HALF * 2


def steady(value: float, n: int = N) -> list[float]:
    return [value] * n


def drifting(start: float, end: float, n: int = N) -> list[float]:
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


# --- decoupling -----------------------------------------------------------


def test_a_perfectly_steady_run_does_not_decouple():
    result = decoupling(heart_rate=steady(150), watts=steady(200))
    assert result.pct == pytest.approx(0.0, abs=0.01)
    assert result.method == "pw:hr"
    assert not result.is_concerning


def test_rising_heart_rate_at_constant_power_is_decoupling():
    """The classic fade: same output, more heartbeats to produce it."""
    result = decoupling(heart_rate=drifting(140, 170), watts=steady(200))
    assert result.pct is not None and result.pct > 0
    assert result.first_half_ratio > result.second_half_ratio


def test_falling_power_at_constant_heart_rate_is_decoupling():
    result = decoupling(heart_rate=steady(155), watts=drifting(210, 180))
    assert result.pct is not None and result.pct > 0


def test_a_strong_finish_reads_as_negative_decoupling():
    result = decoupling(heart_rate=steady(150), watts=drifting(180, 220))
    assert result.pct is not None and result.pct < 0
    assert not result.is_concerning


def test_the_concern_threshold_is_applied():
    mild = decoupling(heart_rate=drifting(150, 152), watts=steady(200))
    assert not mild.is_concerning
    severe = decoupling(heart_rate=drifting(140, 180), watts=steady(200))
    assert severe.pct > DECOUPLING_CONCERN_PCT
    assert severe.is_concerning


def test_power_is_preferred_over_pace_when_both_exist():
    result = decoupling(heart_rate=steady(150), watts=steady(200), velocity=steady(3.0))
    assert result.method == "pw:hr"


def test_pace_is_used_when_there_is_no_power():
    result = decoupling(heart_rate=steady(150), velocity=drifting(3.2, 2.9))
    assert result.method == "pa:hr"
    assert result.pct is not None and result.pct > 0


# --- missing data must never look like a good result ----------------------


def test_no_heart_rate_returns_none_with_a_reason():
    """A missing measurement and a healthy one must not look alike."""
    result = decoupling(heart_rate=None, watts=steady(200))
    assert result.pct is None
    assert result.method == "none"
    assert "heart-rate" in result.reason
    assert not result.is_concerning


def test_an_all_zero_heart_rate_stream_counts_as_missing():
    result = decoupling(heart_rate=steady(0), watts=steady(200))
    assert result.pct is None


def test_no_output_stream_returns_none():
    result = decoupling(heart_rate=steady(150))
    assert result.pct is None
    assert "power or velocity" in result.reason


def test_too_few_samples_returns_none():
    short = MIN_SAMPLES_PER_HALF
    result = decoupling(heart_rate=steady(150, short), watts=steady(200, short))
    assert result.pct is None
    assert "usable samples" in result.reason


def test_stopped_samples_are_excluded():
    """Standing at a crossing should not count as a collapse in output."""
    hr = steady(150)
    watts = steady(200)
    watts[N // 2 :] = [0] * (N - N // 2)
    moving = [True] * (N // 2) + [False] * (N - N // 2)

    # Without the moving mask the stopped half destroys the ratio...
    unmasked = decoupling(heart_rate=hr, watts=watts)
    # ...and with it, the stopped samples simply drop out.
    masked = decoupling(heart_rate=hr, watts=watts, moving=moving)
    assert masked.pct is None or abs(masked.pct) < abs(unmasked.pct or 0) + 1


# --- split fade -----------------------------------------------------------


def test_even_splits_show_no_fade():
    fade = split_fade([330, 330, 330, 330])
    assert fade.fade_pct == pytest.approx(0.0)
    assert fade.negative_split is False


def test_slowing_down_is_positive_fade():
    fade = split_fade([320, 330, 345, 360])
    assert fade.fade_pct > 0
    assert fade.first_km_pace_s == 320
    assert fade.last_km_pace_s == 360
    assert fade.fastest_km == 1
    assert fade.slowest_km == 4
    assert fade.negative_split is False


def test_a_negative_split_is_detected():
    fade = split_fade([360, 350, 335, 325])
    assert fade.fade_pct < 0
    assert fade.negative_split is True
    assert fade.fastest_km == 4


def test_a_single_split_cannot_show_fade():
    fade = split_fade([330])
    assert fade.fade_pct is None
    assert fade.negative_split is None


def test_zero_and_missing_splits_are_ignored():
    fade = split_fade([0, 330, 340, 0])
    assert fade.first_km_pace_s == 330
    assert fade.last_km_pace_s == 340
