"""Clique check-in CLI — domain, loaders, and CLI."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any


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
    raise NotImplementedError


def merge_contacts(
    members: list[Member],
    contacts: dict[str, tuple[datetime, str]],
) -> list[Member]:
    raise NotImplementedError


def get_due_checkins(
    members: list[Member],
    holidays: list[date],
    current_date: date,
    top_n: int,
) -> list[DueCheckin]:
    raise NotImplementedError


def parse_args(argv: list[str] | None = None) -> Any:
    raise NotImplementedError


def main(argv: list[str] | None = None) -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
