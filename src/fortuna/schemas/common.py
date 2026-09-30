"""Shared enumerations used across Fortuna schemas."""

from enum import Enum


class VerificationStatus(str, Enum):
    """How firmly a record is backed by authoritative evidence."""

    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNRESOLVED = "unresolved"


class ChangeClassification(str, Enum):
    """What kind of rule event a regime/change-log row represents.

    Only ``MATRIX`` and ``MECHANISM`` changes create a new statistical regime
    (pool group). ``BASELINE`` marks a game's initial regime. ``SCHEDULE``,
    ``ECONOMIC`` and ``ADMINISTRATIVE`` changes are recorded as distinct legal
    eras but share the previous pool group when the sampling process is
    unchanged. ``UNRESOLVED`` means the materiality is not yet determined.
    """

    BASELINE = "baseline"
    MATRIX = "matrix"
    MECHANISM = "mechanism"
    SCHEDULE = "schedule"
    ECONOMIC = "economic"
    ADMINISTRATIVE = "administrative"
    UNRESOLVED = "unresolved"


class SourceType(str, Enum):
    """Nature of a provenance source."""

    OFFICIAL_RULES = "official_rules"
    OFFICIAL_ARCHIVE = "official_archive"
    OFFICIAL_PRESS_RELEASE = "official_press_release"
    OFFICIAL_DATA_PORTAL = "official_data_portal"
    GOVERNMENT_REGISTER = "government_register"
    ANNUAL_REPORT = "annual_report"
    SECONDARY = "secondary"


def parse_list(raw: str | list[str] | None) -> list[str]:
    """Parse a semicolon-separated CSV cell into a list of strings."""
    if raw is None or isinstance(raw, list):
        return raw or []
    return [part.strip() for part in raw.split(";") if part.strip()]
