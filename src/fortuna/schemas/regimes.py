"""Game regime schema — the core "rules are data" contract.

Every row is a legal/rule era (`regime_id`). Each row also belongs to a
statistical regime / pool group (`statistical_regime_id`): rows sharing a pool
group are sampling-equivalent and may be pooled for analysis. Matrix or
mechanism changes create a new pool group; schedule/economic/administrative
changes create a new legal era but reuse the previous pool group.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fortuna.schemas.common import ChangeClassification, VerificationStatus, parse_list


class GameRegime(BaseModel):
    """One legal rule era of one game."""

    model_config = ConfigDict(extra="forbid")

    # Identity
    regime_id: str = Field(pattern=r"^[A-Z]{2,4}-R\d{3}$")
    game_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    statistical_regime_id: str = Field(
        pattern=r"^[A-Z]{2,4}-S\d{2}$",
        description="Pool group; draws may only be pooled within one group.",
    )
    change_classification: ChangeClassification = ChangeClassification.BASELINE

    # Legal era
    legal_effective_start: date | None = None
    legal_effective_end: date | None = None

    # Draw-level span actually conducted under these rules (the fields used for
    # draw->regime assignment). None on the right edge means "ongoing".
    first_affected_draw: date | None = None
    last_affected_draw: date | None = None

    # Sampling-process fields — these define statistical comparability.
    main_ball_count: int = Field(gt=0)
    main_ball_min: int
    main_ball_max: int
    special_ball_count: int = Field(ge=0, default=0)
    special_ball_min: int | None = None
    special_ball_max: int | None = None
    sampling_without_replacement: bool = True

    # Descriptive / economic fields — recorded but do not by themselves split
    # the statistical series.
    drawing_days: list[str] = Field(default_factory=list)
    scheduled_draw_time: str | None = Field(
        default=None, pattern=r"^\d{2}:\d{2}$", description="Local scheduled time HH:MM"
    )
    timezone: str | None = None
    ticket_price: Decimal | None = Field(default=None, ge=0)
    jackpot_odds: int | None = Field(
        default=None, gt=0, description="Jackpot odds denominator (1 in N)"
    )
    overall_odds: float | None = Field(
        default=None, gt=0, description="Overall odds denominator (1 in N)"
    )
    drawing_location: str | None = None
    drawing_method: str | None = None

    # Provenance
    material_change_reason: str | None = None
    rule_identifier: str | None = Field(
        default=None, description="Official rule/document identifier, e.g. 53ER15-xx"
    )
    source_id: str | None = None
    verification_date: date | None = None
    verification_status: VerificationStatus = VerificationStatus.UNRESOLVED
    notes: str | None = None

    @field_validator("drawing_days", mode="before")
    @classmethod
    def _split_days(cls, v: object) -> object:
        if isinstance(v, str):
            return parse_list(v)
        return v

    @field_validator("drawing_days")
    @classmethod
    def _check_days(cls, v: list[str]) -> list[str]:
        valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        lowered = [d.lower() for d in v]
        bad = set(lowered) - valid
        if bad:
            raise ValueError(f"unknown drawing days: {sorted(bad)}")
        return lowered

    @model_validator(mode="after")
    def _check_consistency(self) -> "GameRegime":
        if self.main_ball_min >= self.main_ball_max:
            raise ValueError("main_ball_min must be < main_ball_max")
        if self.special_ball_count == 0:
            if self.special_ball_min is not None or self.special_ball_max is not None:
                raise ValueError("special_ball_min/max must be empty when count is 0")
        else:
            if self.special_ball_min is None or self.special_ball_max is None:
                raise ValueError("special_ball_min/max required when count > 0")
            if self.special_ball_min >= self.special_ball_max:
                raise ValueError("special_ball_min must be < special_ball_max")
        lo, hi = self.legal_effective_start, self.legal_effective_end
        if lo and hi and lo > hi:
            raise ValueError("legal_effective_start must be <= legal_effective_end")
        lo, hi = self.first_affected_draw, self.last_affected_draw
        if lo and hi and lo > hi:
            raise ValueError("first_affected_draw must be <= last_affected_draw")
        return self

    @property
    def span_start(self) -> date | None:
        """First draw date governed by this regime (fallback: legal start)."""
        return self.first_affected_draw or self.legal_effective_start

    @property
    def span_end(self) -> date | None:
        """Last draw date governed by this regime; None = ongoing."""
        return self.last_affected_draw or self.legal_effective_end

    def matrix_key(self) -> tuple:
        """Fields that define the stochastic sampling process."""
        return (
            self.main_ball_count,
            self.main_ball_min,
            self.main_ball_max,
            self.special_ball_count,
            self.special_ball_min,
            self.special_ball_max,
            self.sampling_without_replacement,
        )
