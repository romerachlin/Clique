"""Clique check-in CLI — domain, loaders, and CLI."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass
class DueCheckin:
    member_id: str
    full_name: str
    priority_score: float
    recommended_window: str


@dataclass
class Member:
    member_id: str
    full_name: str
    age: int
    preferred_channel: str
    risk_flags: list[str]
    last_contact_utc: datetime | None = None
    last_outcome: str | None = None

    def _last_contact_utc_date(self) -> date | None:
        """Return the UTC calendar date of the last contact, or None if unknown.

        Naive datetimes are interpreted as UTC to match ISO timestamps ending in Z.
        """
        if self.last_contact_utc is None:
            return None
        last_contact_instant = self.last_contact_utc
        if last_contact_instant.tzinfo is None:
            last_contact_instant = last_contact_instant.replace(tzinfo=timezone.utc)
        return last_contact_instant.astimezone(timezone.utc).date()

    def calculate_priority(self, current_date: date) -> float:
        """Compute priority score: integer risk/outcome bonuses plus days_since_last_contact / 7.

        With no contact record, the fractional term uses a 365-day default gap (see README).
        """
        risk_flags_set = set(self.risk_flags)
        integer_bonus_sum = 0.0
        if "recent_discharge" in risk_flags_set:
            integer_bonus_sum += 3.0
        if "lives_alone" in risk_flags_set:
            integer_bonus_sum += 2.0
        if self.age >= 80:
            integer_bonus_sum += 1.0
        if self.last_contact_utc is not None and self.last_outcome == "no_answer":
            integer_bonus_sum += 1.0

        last_contact_calendar_date = self._last_contact_utc_date()
        if last_contact_calendar_date is None:
            days_since_last_contact = 365
        else:
            days_since_last_contact = (current_date - last_contact_calendar_date).days

        fractional_term = days_since_last_contact / 7.0
        return integer_bonus_sum + fractional_term

    def get_recommended_window(self) -> str:
        """Return call window label: morning for age 80+, otherwise afternoon."""
        return "morning" if self.age >= 80 else "afternoon"


def load_members(path: str) -> list[Member]:
    """Read members.csv-style input: semicolon-separated risk_flags; empty flag cells allowed.

    Raises ValueError if a row has a missing column or a non-integer age.
    """
    members: list[Member] = []
    with open(path, encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            raw_risk_flags_cell = row.get("risk_flags") or ""
            risk_flag_tokens = [
                token.strip() for token in raw_risk_flags_cell.split(";")
            ]
            risk_flags = [token for token in risk_flag_tokens if token]
            try:
                age = int(str(row["age"]).strip())
            except (KeyError, ValueError) as error:
                raise ValueError(f"Invalid or missing age in row: {row!r}") from error
            members.append(
                Member(
                    member_id=str(row["member_id"]).strip(),
                    full_name=str(row["full_name"]).strip(),
                    age=age,
                    preferred_channel=str(row["preferred_channel"]).strip(),
                    risk_flags=risk_flags,
                )
            )
    return members


def _parse_utc_instant_from_iso_string(iso_timestamp: str) -> datetime:
    """Parse an ISO-8601 instant; trailing Z is treated as UTC (stdlib-friendly)."""
    normalized = iso_timestamp.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    contact_instant = datetime.fromisoformat(normalized)
    if contact_instant.tzinfo is None:
        contact_instant = contact_instant.replace(tzinfo=timezone.utc)
    return contact_instant.astimezone(timezone.utc)


def load_last_contacts(path: str) -> dict[str, tuple[datetime, str]]:
    """Map member_id to (last_contact_utc aware UTC, outcome).

    If a member_id appears more than once, the row with the latest last_contact_utc wins.
    """
    contacts_by_member_id: dict[str, tuple[datetime, str]] = {}
    with open(path, encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            member_id = str(row["member_id"]).strip()
            try:
                contact_instant = _parse_utc_instant_from_iso_string(
                    str(row["last_contact_utc"])
                )
            except (KeyError, ValueError) as error:
                raise ValueError(f"Invalid last_contact_utc in row: {row!r}") from error
            outcome = str(row["outcome"]).strip()
            existing_contact = contacts_by_member_id.get(member_id)
            if existing_contact is None or contact_instant > existing_contact[0]:
                contacts_by_member_id[member_id] = (contact_instant, outcome)
    return contacts_by_member_id


def load_holidays(path: str) -> list[date]:
    """Load a JSON file containing a list of ISO calendar dates (YYYY-MM-DD strings).

    Raises ValueError if the top-level JSON is not a list of date strings.
    """
    with open(path, encoding="utf-8") as json_file:
        raw_payload = json.load(json_file)
    if not isinstance(raw_payload, list):
        raise ValueError(
            f"Expected a JSON array of holiday date strings, got {type(raw_payload)!r}"
        )
    holiday_dates: list[date] = []
    for holiday_index, raw_date_string in enumerate(raw_payload):
        if not isinstance(raw_date_string, str):
            raise ValueError(
                f"Holiday at index {holiday_index} must be a string, "
                f"got {type(raw_date_string)!r}"
            )
        holiday_dates.append(date.fromisoformat(raw_date_string.strip()))
    return holiday_dates


def merge_contacts(
    members: list[Member],
    contacts: dict[str, tuple[datetime, str]],
) -> list[Member]:
    """Return members with last_contact_utc and last_outcome set when present in contacts.

    Members whose member_id is missing from contacts keep last_contact_utc and last_outcome
    as None.
    """
    merged_members: list[Member] = []
    for member in members:
        contact_record = contacts.get(member.member_id)
        if contact_record is None:
            merged_members.append(member)
            continue
        last_contact_instant, last_outcome = contact_record
        merged_members.append(
            replace(
                member,
                last_contact_utc=last_contact_instant,
                last_outcome=last_outcome,
            )
        )
    return merged_members


def get_due_checkins(
    members: list[Member],
    holidays: list[date],
    current_date: date,
    top_n: int,
) -> list[DueCheckin]:
    """Return up to top_n due check-ins: filters, then sort by priority desc, member_id asc.

    Skips everyone when current_date is a holiday. Otherwise keeps members with a non-blank
    preferred channel who have no contact record or last contact at least 7 days ago (UTC date).
    """
    holiday_calendar_dates = set(holidays)
    if current_date in holiday_calendar_dates:
        return []

    members_passing_filters: list[Member] = []
    for member in members:
        if member.preferred_channel.strip() == "":
            continue
        if member.last_contact_utc is None:
            members_passing_filters.append(member)
            continue
        last_contact_calendar_date = member._last_contact_utc_date()
        days_since_last_contact = (
            current_date - last_contact_calendar_date
        ).days
        if days_since_last_contact >= 7:
            members_passing_filters.append(member)

    members_with_scores: list[tuple[Member, float]] = []
    for member in members_passing_filters:
        priority_score = member.calculate_priority(current_date)
        members_with_scores.append((member, priority_score))

    members_with_scores.sort(
        key=lambda item: (-item[1], item[0].member_id),
    )

    due_checkins: list[DueCheckin] = []
    for member, priority_score in members_with_scores[:top_n]:
        due_checkins.append(
            DueCheckin(
                member_id=member.member_id,
                full_name=member.full_name,
                priority_score=priority_score,
                recommended_window=member.get_recommended_window(),
            )
        )
    return due_checkins


def _parse_iso_date_argument(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _parse_top_argument(value: str) -> int:
    parsed_top = int(value)
    if parsed_top < 1:
        raise argparse.ArgumentTypeError("top must be >= 1")
    return parsed_top


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI flags: --top (default 5), optional --mock-date, optional --data-dir."""
    parser = argparse.ArgumentParser(
        description="List members due for check-in (sorted by priority).",
    )
    parser.add_argument(
        "--top",
        type=_parse_top_argument,
        default=5,
        metavar="N",
        help="Maximum number of rows to print (default: 5).",
    )
    parser.add_argument(
        "--mock-date",
        dest="mock_date",
        type=_parse_iso_date_argument,
        default=None,
        metavar="YYYY-MM-DD",
        help="Use this calendar date instead of today's UTC date.",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Folder with members.csv, last_contacts.csv, holidays.json (default: data).",
    )
    return parser.parse_args(argv)


def _print_due_checkins_table(due_checkins: list[DueCheckin]) -> None:
    """Print due check-ins as aligned columns on stdout."""
    column_headers = (
        f"{'member_id':<10}"
        f"{'full_name':<24}"
        f"{'priority_score':>16}  "
        f"{'recommended_window':<18}"
    )
    print(column_headers)
    print("-" * min(len(column_headers), 88))
    for due_row in due_checkins:
        print(
            f"{due_row.member_id:<10}"
            f"{due_row.full_name:<24}"
            f"{due_row.priority_score:>16.2f}  "
            f"{due_row.recommended_window:<18}"
        )


def main(argv: list[str] | None = None) -> None:
    """Load data files, compute due check-ins for the chosen date, print a table."""
    parsed_arguments = parse_args(argv)
    data_directory = Path(parsed_arguments.data_dir)
    members = load_members(str(data_directory / "members.csv"))
    contacts = load_last_contacts(str(data_directory / "last_contacts.csv"))
    holidays = load_holidays(str(data_directory / "holidays.json"))
    merged_members = merge_contacts(members, contacts)
    if parsed_arguments.mock_date is not None:
        current_calendar_date = parsed_arguments.mock_date
    else:
        current_calendar_date = datetime.now(timezone.utc).date()
    due_checkins = get_due_checkins(
        merged_members,
        holidays,
        current_calendar_date,
        parsed_arguments.top,
    )
    _print_due_checkins_table(due_checkins)


if __name__ == "__main__":
    main()
