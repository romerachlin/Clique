"""Clique check-in CLI — domain, loaders, and CLI (TDD stub: raises until implemented)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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

    def calculate_priority(self, current_date: date) -> float:
        raise NotImplementedError

    def get_recommended_window(self) -> str:
        raise NotImplementedError


def load_members(path: str) -> list[Member]:
    raise NotImplementedError


def load_last_contacts(path: str) -> dict[str, tuple[datetime, str]]:
    raise NotImplementedError


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
