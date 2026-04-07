"""Tests for main — core logic (~10) plus a few edge cases (~3)."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import main


DATA_DIR = Path(__file__).resolve().parent / "data"


def _golden_due(top_n: int = 10):
    """Load sample CSVs, merge, return get_due_checkins for 2025-11-06 with given top_n."""
    members = main.load_members(str(DATA_DIR / "members.csv"))
    contacts = main.load_last_contacts(str(DATA_DIR / "last_contacts.csv"))
    merged = main.merge_contacts(members, contacts)
    holidays = main.load_holidays(str(DATA_DIR / "holidays.json"))
    return main.get_due_checkins(merged, holidays, date(2025, 11, 6), top_n=top_n)


class TestCoreLogic(unittest.TestCase):
    """About ten tests: Member helpers, loaders, pipeline, CLI args."""

    def test_calculate_priority_ruth_like_golden(self) -> None:
        """Tests Member.calculate_priority for a fixed member and date.

        Input: age 82, lives_alone, last contact 2025-10-30 UTC, current date 2025-11-06.
        Expected output: 4.0 (integer bonuses 2+1 plus days_since/7 = 7/7).
        """
        m = main.Member(
            member_id="1",
            full_name="Ruth Cohen",
            age=82,
            preferred_channel="call",
            risk_flags=["lives_alone"],
            last_contact_utc=datetime(2025, 10, 30, 8, 0, tzinfo=timezone.utc),
            last_outcome="ok",
        )
        self.assertAlmostEqual(
            m.calculate_priority(date(2025, 11, 6)), 4.0, places=10
        )

    def test_get_recommended_window_age_80_morning(self) -> None:
        """Tests Member.get_recommended_window at the age threshold.

        Input: age exactly 80.
        Expected output: "morning".
        """
        m = main.Member(
            member_id="a",
            full_name="A",
            age=80,
            preferred_channel="call",
            risk_flags=[],
        )
        self.assertEqual(m.get_recommended_window(), "morning")

    def test_get_recommended_window_age_79_afternoon(self) -> None:
        """Tests Member.get_recommended_window below the senior threshold.

        Input: age 79.
        Expected output: "afternoon".
        """
        m = main.Member(
            member_id="b",
            full_name="B",
            age=79,
            preferred_channel="call",
            risk_flags=[],
        )
        self.assertEqual(m.get_recommended_window(), "afternoon")

    def test_load_members_row_count(self) -> None:
        """Tests load_members on sample members.csv.

        Expected output: four Member rows (one per data row after the header).
        """
        members = main.load_members(str(DATA_DIR / "members.csv"))
        self.assertEqual(len(members), 4)

    def test_load_holidays_iso_dates(self) -> None:
        """Tests load_holidays on sample holidays.json.

        Expected output: the set {2025-11-07, 2025-12-25} as date objects.
        """
        h = main.load_holidays(str(DATA_DIR / "holidays.json"))
        self.assertEqual(set(h), {date(2025, 11, 7), date(2025, 12, 25)})

    def test_pipeline_sort_order_2025_11_06(self) -> None:
        """Tests end-to-end load, merge, and get_due_checkins sort order.

        Input: sample data/, current date 2025-11-06, top_n large enough for all.
        Expected output: member_id list in descending priority order: ["3", "1", "4", "2"].
        """
        due = _golden_due(10)
        self.assertEqual(
            [d.member_id for d in due],
            ["3", "1", "4", "2"],
        )

    def test_pipeline_priority_member_1(self) -> None:
        """Tests computed priority_score for member "1" in the golden pipeline.

        Input: same as test_pipeline_sort_order_2025_11_06.
        Expected output: DueCheckin for member "1" has priority_score 4.0.
        """
        due = _golden_due(10)
        one = next(d for d in due if d.member_id == "1")
        self.assertAlmostEqual(one.priority_score, 4.0, places=7)

    def test_top_n_truncates(self) -> None:
        """Tests that get_due_checkins returns only the first top_n rows.

        Input: same golden pipeline, top_n=3, date 2025-11-06.
        Expected output: three rows, member_ids ["3", "1", "4"] (highest priorities).
        """
        due = _golden_due(3)
        self.assertEqual([d.member_id for d in due], ["3", "1", "4"])

    def test_parse_args_mock_date(self) -> None:
        """Tests CLI parsing of --mock-date.

        Input: argv with --mock-date 2025-11-06 and --top 3.
        Expected output: namespace attribute mock_date equals date(2025, 11, 6).
        """
        ns = main.parse_args(["--mock-date", "2025-11-06", "--top", "3"])
        self.assertEqual(ns.mock_date, date(2025, 11, 6))

    def test_parse_args_top(self) -> None:
        """Tests CLI parsing of --top.

        Input: argv with --mock-date 2025-11-06 and --top 3.
        Expected output: namespace attribute top equals 3.
        """
        ns = main.parse_args(["--mock-date", "2025-11-06", "--top", "3"])
        self.assertEqual(ns.top, 3)


class TestEdgeCases(unittest.TestCase):
    """Edge cases: holiday blackout, missing last contact."""

    def test_holiday_returns_no_due_checkins(self) -> None:
        """Tests get_due_checkins when current_date is a listed holiday.

        Input: one qualifying member, holidays containing 2025-11-07, current_date 2025-11-07.
        Expected output: empty list (no check-ins on a holiday).
        """
        m = main.Member(
            member_id="1",
            full_name="Anyone",
            age=70,
            preferred_channel="call",
            risk_flags=[],
            last_contact_utc=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            last_outcome="ok",
        )
        due = main.get_due_checkins(
            [m], [date(2025, 11, 7)], date(2025, 11, 7), top_n=5
        )
        self.assertEqual(due, [])

    def test_no_last_contact_priority_uses_365_day_fraction(self) -> None:
        """Tests calculate_priority when there is no last_contact_utc.

        Input: Member with last_contact_utc None, no risk flags, age 70, date 2025-11-06.
        Expected output: score 365/7 (documented default gap for the fractional term only).
        """
        m = main.Member(
            member_id="99",
            full_name="No History",
            age=70,
            preferred_channel="sms",
            risk_flags=[],
            last_contact_utc=None,
            last_outcome=None,
        )
        self.assertAlmostEqual(
            m.calculate_priority(date(2025, 11, 6)),
            365.0 / 7.0,
            places=10,
        )

    def test_no_last_contact_still_surfaces_in_get_due_checkins(self) -> None:
        """Tests get_due_checkins includes members with no contact history when rules allow.

        Input: one Member with no last contact, non-empty channel, no holidays on that date.
        Expected output: one DueCheckin whose priority_score equals 365/7.
        """
        m = main.Member(
            member_id="99",
            full_name="No History",
            age=70,
            preferred_channel="sms",
            risk_flags=[],
            last_contact_utc=None,
            last_outcome=None,
        )
        due = main.get_due_checkins([m], [], date(2025, 11, 6), top_n=5)
        self.assertAlmostEqual(due[0].priority_score, 365.0 / 7.0, places=7)


if __name__ == "__main__":
    unittest.main()
