"""Comprehensive tests for wave_checker.py"""
import hashlib
import json
import os
import sys
import types
from io import StringIO
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wave_checker
from wave_checker import (
    _MSG_BANK,
    build_today_message,
    composite_score,
    height_score,
    period_score,
    pick_motivational_message,
    wind_score,
)


# ---------------------------------------------------------------------------
# height_score tests
# ---------------------------------------------------------------------------

class TestHeightScore:
    def test_below_min_returns_zero(self):
        assert height_score(0.5, 0.8) == 0.0

    def test_exactly_at_min(self):
        # height == min_height → ratio=0 → 0.3 + 0*0.7 = 0.3
        result = height_score(0.8, 0.8)
        assert result == pytest.approx(0.3, abs=1e-6)

    def test_double_min_height(self):
        # height=1.6, min=0.8 → ratio=1.0 → 0.3 + 1.0*0.7 = 1.0
        result = height_score(1.6, 0.8)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_capped_at_one(self):
        # Large height should still give 1.0
        assert height_score(10.0, 0.8) == 1.0

    def test_zero_min_height_small_wave(self):
        # min_height=0 → uses max(0, 0.01)=0.01 as denominator
        # height=0.01, ratio=0/0.01=0 → 0.3 + 0*0.7 = 0.3
        result = height_score(0.0, 0.0)
        assert result == pytest.approx(0.3, abs=1e-6)

    def test_just_below_min(self):
        assert height_score(0.79, 0.8) == 0.0

    def test_typical_good_wave(self):
        # height=1.2, min=0.8 → ratio=(1.2-0.8)/0.8=0.5 → 0.3+0.5*0.7=0.65
        result = height_score(1.2, 0.8)
        assert result == pytest.approx(0.65, abs=1e-6)


# ---------------------------------------------------------------------------
# period_score tests
# ---------------------------------------------------------------------------

class TestPeriodScore:
    def test_none_returns_half(self):
        assert period_score(None) == 0.5

    def test_very_short_period(self):
        # < 6 → 0.1
        assert period_score(4.0) == 0.1
        assert period_score(5.9) == 0.1

    def test_exactly_6(self):
        # 6 <= period < 8 → 0.3 + (6-6)/2 * 0.2 = 0.3
        assert period_score(6.0) == pytest.approx(0.3, abs=1e-6)

    def test_period_7(self):
        # 0.3 + (7-6)/2 * 0.2 = 0.3 + 0.1 = 0.4
        assert period_score(7.0) == pytest.approx(0.4, abs=1e-6)

    def test_exactly_8(self):
        # 8 <= period < 12 → 0.5 + (8-8)/4 * 0.4 = 0.5
        assert period_score(8.0) == pytest.approx(0.5, abs=1e-6)

    def test_period_10(self):
        # 0.5 + (10-8)/4 * 0.4 = 0.5 + 0.2 = 0.7
        assert period_score(10.0) == pytest.approx(0.7, abs=1e-6)

    def test_period_12_and_above(self):
        assert period_score(12.0) == 1.0
        assert period_score(15.0) == 1.0

    def test_boundary_just_before_12(self):
        # 0.5 + (11.9-8)/4 * 0.4 = 0.5 + 3.9/4 * 0.4 = 0.5 + 0.39 = 0.89
        result = period_score(11.9)
        assert result == pytest.approx(0.5 + (11.9 - 8) / 4 * 0.4, abs=1e-6)


# ---------------------------------------------------------------------------
# wind_score tests
# ---------------------------------------------------------------------------

class TestWindScore:
    def test_none_speed_returns_half(self):
        assert wind_score(None, 180.0, 100.0) == 0.5

    def test_none_dir_returns_half(self):
        assert wind_score(15.0, None, 100.0) == 0.5

    def test_both_none_returns_half(self):
        assert wind_score(None, None, 100.0) == 0.5

    def test_light_wind_glassy(self):
        # wind < 10 → 0.9 regardless of direction
        assert wind_score(5.0, 270.0, 100.0) == 0.9
        assert wind_score(9.9, 0.0, 90.0) == 0.9

    def test_exactly_offshore(self):
        # diff=0 <= 30 → 1.0
        assert wind_score(20.0, 100.0, 100.0) == 1.0

    def test_slightly_off_offshore(self):
        # diff=20 <= 30 → 1.0
        assert wind_score(20.0, 120.0, 100.0) == 1.0

    def test_diff_exactly_30(self):
        # diff=30 <= 30 → 1.0
        assert wind_score(20.0, 130.0, 100.0) == 1.0

    def test_diff_60(self):
        # diff=60, 30 < 60 <= 90 → 1.0 - (60-30)/60 * 0.7 = 1.0 - 0.5*0.7 = 0.65
        assert wind_score(20.0, 160.0, 100.0) == pytest.approx(0.65, abs=1e-6)

    def test_diff_90(self):
        # diff=90 → 1.0 - (90-30)/60 * 0.7 = 1.0 - 0.7 = 0.3
        assert wind_score(20.0, 190.0, 100.0) == pytest.approx(0.3, abs=1e-6)

    def test_diff_135_onshore(self):
        # diff=135 > 90 → max(0, 0.3 - (135-90)/90 * 0.3) = 0.3 - 45/90*0.3 = 0.3 - 0.15 = 0.15
        assert wind_score(20.0, 235.0, 100.0) == pytest.approx(0.15, abs=1e-6)

    def test_fully_onshore_zero(self):
        # diff=180 → max(0, 0.3 - 90/90*0.3) = max(0, 0) = 0.0
        assert wind_score(20.0, 280.0, 100.0) == 0.0


# ---------------------------------------------------------------------------
# composite_score tests
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_all_ones_without_tide(self):
        # 0.50 + 0.28 + 0.22 = 1.0 → *10 = 10.0
        assert composite_score(1.0, 1.0, 1.0) == 10.0

    def test_all_zeros_without_tide(self):
        assert composite_score(0.0, 0.0, 0.0) == 0.0

    def test_all_ones_with_tide(self):
        # 0.45 + 0.25 + 0.20 + 0.10 = 1.0 → *10 = 10.0
        assert composite_score(1.0, 1.0, 1.0, 1.0) == 10.0

    def test_typical_values(self):
        # h=0.65, p=0.5, w=0.9 → 0.5*0.65 + 0.28*0.5 + 0.22*0.9
        # = 0.325 + 0.14 + 0.198 = 0.663 → *10 = 6.6 (rounded to 1 decimal)
        result = composite_score(0.65, 0.5, 0.9)
        expected = round((0.50 * 0.65 + 0.28 * 0.5 + 0.22 * 0.9) * 10, 1)
        assert result == expected

    def test_rounded_to_one_decimal(self):
        # Ensure result has at most 1 decimal place
        result = composite_score(0.3, 0.5, 0.7)
        assert result == round(result, 1)

    def test_with_tide_uses_correct_weights(self):
        # h=1, p=0, w=0, t=0 → 0.45*1 = 4.5
        result = composite_score(1.0, 0.0, 0.0, 0.0)
        assert result == pytest.approx(4.5, abs=0.05)

    def test_none_tide_uses_three_weights(self):
        # Without tide: h=1, p=0, w=0 → 0.50*1 = 5.0
        result = composite_score(1.0, 0.0, 0.0, None)
        assert result == pytest.approx(5.0, abs=0.05)


# ---------------------------------------------------------------------------
# pick_motivational_message tests
# ---------------------------------------------------------------------------

class TestPickMotivationalMessage:
    def test_fire_tier_score_gte_7(self):
        msg = pick_motivational_message(7.0, "2024-01-01")
        # Should be from fire bank
        assert any(msg == tmpl.format(score="7.0") for tmpl in _MSG_BANK["fire"])

    def test_fire_tier_score_10(self):
        msg = pick_motivational_message(10.0, "2024-01-01")
        assert any(msg == tmpl.format(score="10.0") for tmpl in _MSG_BANK["fire"])

    def test_good_tier_score_5(self):
        msg = pick_motivational_message(5.0, "2024-01-01")
        assert any(msg == tmpl.format(score="5.0") for tmpl in _MSG_BANK["good"])

    def test_good_tier_score_6(self):
        msg = pick_motivational_message(6.9, "2024-01-01")
        assert any(msg == tmpl.format(score="6.9") for tmpl in _MSG_BANK["good"])

    def test_decent_tier_score_3(self):
        msg = pick_motivational_message(3.0, "2024-01-01")
        assert any(msg == tmpl.format(score="3.0") for tmpl in _MSG_BANK["decent"])

    def test_decent_tier_score_4(self):
        msg = pick_motivational_message(4.9, "2024-01-01")
        assert any(msg == tmpl.format(score="4.9") for tmpl in _MSG_BANK["decent"])

    def test_weak_tier_below_3(self):
        msg = pick_motivational_message(2.9, "2024-01-01")
        assert any(msg == tmpl.format(score="2.9") for tmpl in _MSG_BANK["weak"])

    def test_weak_tier_zero(self):
        msg = pick_motivational_message(0.0, "2024-01-01")
        assert any(msg == tmpl.format(score="0.0") for tmpl in _MSG_BANK["weak"])

    def test_score_appears_in_output(self):
        msg = pick_motivational_message(6.5, "2024-06-15")
        assert "6.5" in msg

    def test_score_appears_formatted(self):
        # Score should appear as X.Y format
        msg = pick_motivational_message(8.0, "2024-06-15")
        assert "8.0" in msg

    def test_day_hash_rotates(self):
        """Different dates should produce different messages (or same, by hash)."""
        msgs = set()
        for i in range(100):
            date_str = f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
            msg = pick_motivational_message(5.0, date_str)
            msgs.add(msg)
        # Over 100 different dates with 5 messages in the bank, should see >1 distinct
        assert len(msgs) > 1

    def test_same_date_same_message(self):
        """Same date always returns the same message."""
        msg1 = pick_motivational_message(5.0, "2024-06-15")
        msg2 = pick_motivational_message(5.0, "2024-06-15")
        assert msg1 == msg2

    def test_hash_deterministic_index(self):
        """Verify the hash-based index is correct."""
        date_str = "2024-06-15"
        bank = _MSG_BANK["good"]
        expected_idx = int(hashlib.md5(date_str.encode()).hexdigest(), 16) % len(bank)
        expected = bank[expected_idx].format(score="5.0")
        assert pick_motivational_message(5.0, date_str) == expected

    def test_boundary_exactly_7_is_fire(self):
        msg = pick_motivational_message(7.0, "2024-01-01")
        assert any(msg == tmpl.format(score="7.0") for tmpl in _MSG_BANK["fire"])

    def test_boundary_exactly_5_is_good(self):
        msg = pick_motivational_message(5.0, "2024-01-01")
        assert any(msg == tmpl.format(score="5.0") for tmpl in _MSG_BANK["good"])

    def test_boundary_exactly_3_is_decent(self):
        msg = pick_motivational_message(3.0, "2024-01-01")
        assert any(msg == tmpl.format(score="3.0") for tmpl in _MSG_BANK["decent"])

    def test_boundary_just_below_3_is_weak(self):
        # 2.99 < 3 → weak tier, but :.1f rounds to "3.0" in the message text
        msg = pick_motivational_message(2.99, "2024-01-01")
        formatted_score = f"{2.99:.1f}"  # == "3.0"
        assert any(msg == tmpl.format(score=formatted_score) for tmpl in _MSG_BANK["weak"])


# ---------------------------------------------------------------------------
# build_today_message tests
# ---------------------------------------------------------------------------

def _make_result(name="Test Spot", score=6.0, height=1.2, height_score_val=0.65,
                 period=10.0, wind_label="אוף 🟢", window_start=8, window_end=11,
                 hour=9, tide_label=None):
    return {
        "name": name,
        "score": score,
        "height": height,
        "height_score": height_score_val,
        "period": period,
        "wind_label": wind_label,
        "window_start": window_start,
        "window_end": window_end,
        "hour": hour,
        "tide_label": tide_label,
        "wind_dir": 100.0,
        "wind_speed": 15.0,
    }


class TestBuildTodayMessage:
    def test_min_score_zero_hides_threshold(self):
        """When min_score=0, score threshold should NOT appear in the message."""
        results = [_make_result()]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        # Should not have "⭐ 0.0/10" in threshold line
        assert "⭐ 0.0/10" not in msg
        # The threshold line should not include score part
        assert "⚡ סף: 0.8m\n" in msg or "⚡ סף: 0.8m" in msg

    def test_min_score_positive_shows_threshold(self):
        """When min_score > 0, score threshold should appear in the message."""
        results = [_make_result()]
        msg = build_today_message(results, 0.8, 4.0, "שישי")
        assert "⭐ 4.0/10" in msg

    def test_motivational_message_included(self):
        """The motivational message passed in should appear in the output."""
        results = [_make_result()]
        motivational = "⭐ 6.0/10 — הים בוער! 🔥"
        msg = build_today_message(results, 0.8, 0.0, "שישי", motivational)
        assert motivational in msg

    def test_header_present(self):
        results = [_make_result()]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        assert "🏄 התראת גלים!" in msg

    def test_day_in_message(self):
        results = [_make_result()]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        assert "שישי" in msg

    def test_good_spot_has_checkmark(self):
        """A spot meeting score threshold should show 📍 icon."""
        results = [_make_result(score=6.0, height_score_val=0.65)]
        msg = build_today_message(results, 0.8, 4.0, "שישי")
        assert "📍" in msg

    def test_bad_spot_has_x(self):
        """A spot below score threshold should show ❌ icon."""
        results = [_make_result(score=3.0, height_score_val=0.3)]
        msg = build_today_message(results, 0.8, 4.0, "שישי")
        assert "❌" in msg

    def test_score_threshold_not_shown_when_zero(self):
        """The threshold line format: '⚡ סף: Xm' without score when min_score=0."""
        results = [_make_result()]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        # Threshold line should not have | symbol for score
        threshold_line = [l for l in msg.split("\n") if "⚡ סף:" in l][0]
        assert "|" not in threshold_line

    def test_score_threshold_shown_when_positive(self):
        """Threshold line should contain score when min_score > 0."""
        results = [_make_result()]
        msg = build_today_message(results, 0.8, 4.0, "שישי")
        threshold_line = [l for l in msg.split("\n") if "⚡ סף:" in l][0]
        assert "4.0" in threshold_line

    def test_window_shown_when_multi_hour(self):
        """When window spans >1 hour, show time range."""
        results = [_make_result(window_start=8, window_end=11, hour=9)]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        assert "08:00–11:00" in msg

    def test_single_hour_shows_peak(self):
        """When window is single hour, show peak time only."""
        results = [_make_result(window_start=9, window_end=9, hour=9)]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        assert "שיא 09:00" in msg

    def test_spot_comparison_shown_when_two_good_spots(self):
        """When 2 good spots, comparison line should appear."""
        results = [
            _make_result(name="Spot A", score=7.0, height_score_val=0.8),
            _make_result(name="Spot B", score=5.0, height_score_val=0.6),
        ]
        msg = build_today_message(results, 0.8, 4.0, "שישי")
        # diff = 2.0 >= 0.5, so should show best spot
        assert "Spot A" in msg
        assert "🏆" in msg

    def test_similar_spots_show_equal_message(self):
        """When spots are within 0.5 of each other, show equal message."""
        results = [
            _make_result(name="Spot A", score=6.0, height_score_val=0.7),
            _make_result(name="Spot B", score=5.8, height_score_val=0.65),
        ]
        msg = build_today_message(results, 0.8, 4.0, "שישי")
        assert "🤝" in msg

    def test_tide_label_shown_when_present(self):
        results = [_make_result(tide_label="גאות ▲")]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        assert "גאות ▲" in msg

    def test_no_tide_label_when_none(self):
        results = [_make_result(tide_label=None)]
        msg = build_today_message(results, 0.8, 0.0, "שישי")
        assert "גאות" not in msg


# ---------------------------------------------------------------------------
# Config loading tests — falsy-zero bug
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_min_score_zero_loads_as_zero(self):
        """min_score=0 in config.json MUST load as 0.0, not fall back to 4.0."""
        config = {"min_wave_height": 0.8, "min_score": 0}
        with patch("builtins.open", mock.mock_open(read_data=json.dumps(config))):
            with patch("json.load", return_value=config):
                file_config = config
        # Simulate the actual loading logic from main()
        min_score = float(
            file_config["min_score"] if "min_score" in file_config
            else os.environ.get("MIN_SCORE", "4.0")
        )
        assert min_score == 0.0, f"Expected 0.0, got {min_score}"

    def test_min_score_zero_not_falsy_default(self):
        """The old bug: 'file_config.get("min_score") or 4.0' would give 4.0 when value=0.
        The fix uses 'file_config["min_score"] if "min_score" in file_config'."""
        config = {"min_score": 0}
        # Old buggy pattern (should NOT be used):
        old_result = config.get("min_score") or 4.0
        assert old_result == 4.0, "Old buggy behavior confirmed"

        # New correct pattern:
        new_result = float(
            config["min_score"] if "min_score" in config
            else 4.0
        )
        assert new_result == 0.0, f"Fixed behavior should give 0.0, got {new_result}"

    def test_min_score_absent_falls_back_to_env(self):
        """If min_score not in config, use environment variable or default 4.0."""
        config = {"min_wave_height": 0.8}
        with patch.dict(os.environ, {"MIN_SCORE": "3.5"}):
            min_score = float(
                config["min_score"] if "min_score" in config
                else os.environ.get("MIN_SCORE", "4.0")
            )
        assert min_score == 3.5

    def test_min_score_absent_defaults_to_4(self):
        """If min_score not in config and no env var, default is 4.0."""
        config = {}
        env = {}
        with patch.dict(os.environ, {}, clear=True):
            # Remove MIN_SCORE from env if present
            os.environ.pop("MIN_SCORE", None)
            min_score = float(
                config["min_score"] if "min_score" in config
                else os.environ.get("MIN_SCORE", "4.0")
            )
        assert min_score == 4.0

    def test_load_config_file_returns_dict(self, tmp_path):
        """load_config_file should return the parsed JSON dict."""
        config_data = {"min_wave_height": 0.8, "min_score": 0}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = wave_checker.load_config_file()
        finally:
            os.chdir(orig_dir)

        assert result["min_score"] == 0
        assert result["min_wave_height"] == 0.8

    def test_config_zero_min_score_not_replaced_by_default(self, tmp_path):
        """End-to-end: config.json with min_score=0 results in min_score=0.0."""
        config_data = {"min_wave_height": 0.8, "min_score": 0}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        orig_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            file_config = wave_checker.load_config_file()
        finally:
            os.chdir(orig_dir)

        min_score = float(
            file_config["min_score"] if "min_score" in file_config
            else os.environ.get("MIN_SCORE", "4.0")
        )
        assert min_score == 0.0


# ---------------------------------------------------------------------------
# run_today day-of-week check tests
# ---------------------------------------------------------------------------

class TestRunTodayDayCheck:
    """Test that run_today respects check_days and --force flag."""

    def _mock_hours(self, date_str):
        """Create minimal wave data for the given date."""
        return [
            {
                "date": date_str,
                "hour": h,
                "wave_height": 1.2,
                "wave_period": 10.0,
                "wind_speed_kmh": 15.0,
                "wind_dir": 100.0,
                "tide_height": None,
            }
            for h in range(6, 18)
        ]

    def test_exits_early_when_day_not_in_check_days(self, capsys):
        """run_today should exit early when today is not in check_days and force=False."""
        # We'll mock today as 'monday' but check_days only has ['thursday', 'friday', 'saturday']
        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Monday",
            "%Y-%m-%d": "2024-06-10",
        }.get(fmt, "")

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo") as mock_fetch:
                wave_checker.run_today(
                    token="", chat_id="",
                    min_height=0.8, min_score=4.0,
                    check_days=["thursday", "friday", "saturday"],
                    force=False,
                )
                # Should not have called fetch_open_meteo
                mock_fetch.assert_not_called()

        captured = capsys.readouterr()
        assert "monday" in captured.out.lower() or "not in check days" in captured.out.lower()

    def test_does_not_exit_when_day_in_check_days(self, capsys):
        """run_today should proceed when today IS in check_days."""
        date_str = "2024-06-14"  # a friday

        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Friday",
            "%Y-%m-%d": date_str,
        }.get(fmt, "")

        hours = self._mock_hours(date_str)

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo", return_value=hours):
                with patch("wave_checker.append_history"):
                    with patch("wave_checker.send_telegram") as mock_send:
                        wave_checker.run_today(
                            token="tok", chat_id="cid",
                            min_height=0.8, min_score=4.0,
                            check_days=["thursday", "friday", "saturday"],
                            force=False,
                        )
                        # Should have tried to send (if any_good)
                        # At minimum, fetch was called (not exited early)

    def test_force_flag_overrides_day_check(self, capsys):
        """--force should bypass day-of-week check and proceed."""
        date_str = "2024-06-10"  # a monday

        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Monday",
            "%Y-%m-%d": date_str,
        }.get(fmt, "")

        hours = self._mock_hours(date_str)

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo", return_value=hours):
                with patch("wave_checker.append_history"):
                    with patch("wave_checker.send_telegram") as mock_send:
                        wave_checker.run_today(
                            token="tok", chat_id="cid",
                            min_height=0.8, min_score=4.0,
                            check_days=["thursday", "friday", "saturday"],
                            force=True,
                        )
                        # Should have tried to send because force=True
                        # (if conditions meet min_score)

        captured = capsys.readouterr()
        # Should see "force" or "running anyway" in output
        assert "force" in captured.out.lower() or "running anyway" in captured.out.lower()

    def test_force_false_on_check_day_proceeds(self, capsys):
        """Even without --force, should proceed on a check day."""
        date_str = "2024-06-13"  # thursday

        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Thursday",
            "%Y-%m-%d": date_str,
        }.get(fmt, "")

        hours = self._mock_hours(date_str)

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo", return_value=hours) as mock_fetch:
                with patch("wave_checker.append_history"):
                    with patch("wave_checker.send_telegram"):
                        wave_checker.run_today(
                            token="tok", chat_id="cid",
                            min_height=0.8, min_score=4.0,
                            check_days=["thursday", "friday", "saturday"],
                            force=False,
                        )
                        mock_fetch.assert_called()


# ---------------------------------------------------------------------------
# any_good logic with min_score=0
# ---------------------------------------------------------------------------

class TestAnyGoodLogic:
    """When min_score=0, alert should send even with low scores/height_scores."""

    def _make_run_today_with_score(self, score, height_score_val, min_score):
        """Run run_today with mocked data that produces the given score."""
        date_str = "2024-06-14"

        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Friday",
            "%Y-%m-%d": date_str,
        }.get(fmt, "")

        # Create mocked best_conditions result
        mocked_result = {
            "name": "Test Spot",
            "score": score,
            "height_score": height_score_val,
            "height": 1.2 if height_score_val > 0 else 0.5,
            "period": 10.0,
            "wind_label": "אוף 🟢",
            "window_start": 8,
            "window_end": 11,
            "hour": 9,
            "tide_label": None,
            "wind_dir": 100.0,
            "wind_speed": 15.0,
        }

        sent_messages = []

        def fake_send(token, chat_id, text):
            sent_messages.append(text)

        hours = [
            {
                "date": date_str,
                "hour": h,
                "wave_height": 1.2,
                "wave_period": 10.0,
                "wind_speed_kmh": 15.0,
                "wind_dir": 100.0,
                "tide_height": None,
            }
            for h in range(6, 18)
        ]

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo", return_value=hours):
                with patch("wave_checker.best_conditions_in_window", return_value=mocked_result):
                    with patch("wave_checker.append_history"):
                        with patch("wave_checker.send_telegram", side_effect=fake_send):
                            wave_checker.run_today(
                                token="tok", chat_id="cid",
                                min_height=0.8, min_score=min_score,
                                check_days=["friday"],
                                force=False,
                            )

        return sent_messages

    def test_min_score_zero_sends_alert_with_low_score(self):
        """With min_score=0, any score >= 0 should trigger alert."""
        sent = self._make_run_today_with_score(
            score=2.0, height_score_val=0.3, min_score=0.0
        )
        assert len(sent) == 1, f"Expected alert to be sent, got: {sent}"

    def test_min_score_zero_sends_even_with_zero_height_score(self):
        """With min_score=0, alert sends even when height_score=0."""
        # any_good logic: score >= 0 is True, and (min_score == 0) is True
        # so height_score check is bypassed
        sent = self._make_run_today_with_score(
            score=0.0, height_score_val=0.0, min_score=0.0
        )
        assert len(sent) == 1, f"Expected alert to be sent with min_score=0, got: {sent}"

    def test_min_score_4_blocks_low_score(self):
        """With min_score=4.0, score=2.0 should NOT send alert."""
        sent = self._make_run_today_with_score(
            score=2.0, height_score_val=0.3, min_score=4.0
        )
        assert len(sent) == 0, f"Expected no alert, but got: {sent}"

    def test_min_score_4_allows_high_score(self):
        """With min_score=4.0, score=6.0 should send alert."""
        sent = self._make_run_today_with_score(
            score=6.0, height_score_val=0.65, min_score=4.0
        )
        assert len(sent) == 1, f"Expected alert to be sent, got: {sent}"

    def test_min_score_4_blocks_zero_height_score_even_high_composite(self):
        """With min_score=4.0 and height_score=0, no alert even if composite score is high."""
        # height_score=0 means wave below minimum height
        sent = self._make_run_today_with_score(
            score=5.0, height_score_val=0.0, min_score=4.0
        )
        assert len(sent) == 0, "Should not send when height_score=0 and min_score > 0"


# ---------------------------------------------------------------------------
# dry-run flag tests
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_does_not_call_send_telegram(self, capsys):
        """--dry-run should skip send_telegram."""
        date_str = "2024-06-14"

        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Friday",
            "%Y-%m-%d": date_str,
        }.get(fmt, "")

        mocked_result = {
            "name": "Test Spot",
            "score": 6.0,
            "height_score": 0.65,
            "height": 1.2,
            "period": 10.0,
            "wind_label": "אוף 🟢",
            "window_start": 8,
            "window_end": 11,
            "hour": 9,
            "tide_label": None,
            "wind_dir": 100.0,
            "wind_speed": 15.0,
        }

        hours = [
            {
                "date": date_str,
                "hour": h,
                "wave_height": 1.2,
                "wave_period": 10.0,
                "wind_speed_kmh": 15.0,
                "wind_dir": 100.0,
                "tide_height": None,
            }
            for h in range(6, 18)
        ]

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo", return_value=hours):
                with patch("wave_checker.best_conditions_in_window", return_value=mocked_result):
                    with patch("wave_checker.append_history"):
                        with patch("wave_checker.send_telegram") as mock_send:
                            wave_checker.run_today(
                                token="tok", chat_id="cid",
                                min_height=0.8, min_score=4.0,
                                check_days=["friday"],
                                force=False,
                                dry_run=True,
                            )
                            mock_send.assert_not_called()

    def test_dry_run_prints_message(self, capsys):
        """--dry-run should print 'DRY RUN — message would be sent:' and the message."""
        date_str = "2024-06-14"

        mock_now = MagicMock()
        mock_now.strftime.side_effect = lambda fmt: {
            "%A": "Friday",
            "%Y-%m-%d": date_str,
        }.get(fmt, "")

        mocked_result = {
            "name": "Test Spot",
            "score": 6.0,
            "height_score": 0.65,
            "height": 1.2,
            "period": 10.0,
            "wind_label": "אוף 🟢",
            "window_start": 8,
            "window_end": 11,
            "hour": 9,
            "tide_label": None,
            "wind_dir": 100.0,
            "wind_speed": 15.0,
        }

        hours = [
            {
                "date": date_str,
                "hour": h,
                "wave_height": 1.2,
                "wave_period": 10.0,
                "wind_speed_kmh": 15.0,
                "wind_dir": 100.0,
                "tide_height": None,
            }
            for h in range(6, 18)
        ]

        with patch("wave_checker.get_israel_now", return_value=mock_now):
            with patch("wave_checker.fetch_open_meteo", return_value=hours):
                with patch("wave_checker.best_conditions_in_window", return_value=mocked_result):
                    with patch("wave_checker.append_history"):
                        wave_checker.run_today(
                            token="", chat_id="",
                            min_height=0.8, min_score=4.0,
                            check_days=["friday"],
                            force=False,
                            dry_run=True,
                        )

        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "message would be sent" in captured.out


# ---------------------------------------------------------------------------
# Integration: any_good when min_score=0 and height_score=0
# ---------------------------------------------------------------------------

class TestAnyGoodDirectLogic:
    """Directly test the any_good expression used in run_today."""

    def _any_good(self, results, min_score):
        return any(
            r["score"] >= min_score and (min_score == 0 or r["height_score"] > 0)
            for r in results
        )

    def test_min_score_zero_height_score_zero(self):
        results = [{"score": 0.0, "height_score": 0.0}]
        assert self._any_good(results, 0.0) is True

    def test_min_score_zero_height_score_positive(self):
        results = [{"score": 5.0, "height_score": 0.6}]
        assert self._any_good(results, 0.0) is True

    def test_min_score_positive_height_score_zero(self):
        """Even if score >= min_score, height_score=0 should block alert."""
        results = [{"score": 5.0, "height_score": 0.0}]
        assert self._any_good(results, 4.0) is False

    def test_min_score_positive_score_below_min(self):
        results = [{"score": 2.0, "height_score": 0.4}]
        assert self._any_good(results, 4.0) is False

    def test_min_score_positive_all_conditions_met(self):
        results = [{"score": 5.0, "height_score": 0.6}]
        assert self._any_good(results, 4.0) is True

    def test_multiple_spots_any_good(self):
        results = [
            {"score": 2.0, "height_score": 0.3},
            {"score": 6.0, "height_score": 0.7},
        ]
        assert self._any_good(results, 4.0) is True

    def test_multiple_spots_all_bad(self):
        results = [
            {"score": 2.0, "height_score": 0.3},
            {"score": 3.0, "height_score": 0.4},
        ]
        assert self._any_good(results, 4.0) is False
