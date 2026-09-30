"""Future historical-draw data contract (Task 9).

Defined now so Phase 1 ingestion lands on a stable, validated contract.
``ball_position`` in DrawNumber records the SOURCE-DEFINED ordering — physical
draw order if and only if the source preserves it. If order is unavailable,
``ball_position`` is null; it is never invented. For games where the official
source reports numbers in sorted order, positions 1..N mean "sorted ascending",
documented in docs/data_dictionary.md.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BallType(str, Enum):
    MAIN = "main"
    SPECIAL = "special"


class DrawValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    REJECTED = "rejected"


class Draw(BaseModel):
    """Header record for one official drawing."""

    model_config = ConfigDict(extra="forbid")

    draw_id: str = Field(pattern=r"^[A-Z]{2,4}-D-\d{4}-\d{2}-\d{2}(-\d+)?$")
    game_id: str
    regime_id: str = Field(
        description="REQUIRED — no draw may exist without a regime assignment"
    )
    draw_date: date
    scheduled_datetime: datetime | None = None
    drawing_identifier: str | None = Field(
        default=None, description="Official draw/serial identifier if the source provides one"
    )

    main_numbers: list[int] = Field(
        min_length=1, description="Main-ball numbers in source-reported order"
    )
    special_ball: int | None = None
    multiplier: float | None = Field(
        default=None, description="Drawn multiplier (Power Play / Megaplier / built-in)"
    )

    jackpot: Decimal | None = Field(default=None, ge=0)
    jackpot_cash_value: Decimal | None = Field(default=None, ge=0)
    jackpot_winners: int | None = Field(default=None, ge=0)

    drawing_location: str | None = None
    machine_id: str | None = None
    ball_set_id: str | None = None

    source_id: str | None = None
    retrieved_at: datetime | None = None
    raw_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    ingestion_version: str | None = None
    validation_status: DrawValidationStatus = DrawValidationStatus.PENDING

    def to_draw_numbers(self) -> list["DrawNumber"]:
        """Normalized representation. Positions are source-reported order
        (physical draw order only if the source preserves it — see module
        docstring)."""
        rows = [
            DrawNumber(
                draw_id=self.draw_id,
                ball_position=i + 1,
                ball_type=BallType.MAIN,
                number=n,
            )
            for i, n in enumerate(self.main_numbers)
        ]
        if self.special_ball is not None:
            rows.append(
                DrawNumber(
                    draw_id=self.draw_id,
                    ball_position=len(self.main_numbers) + 1,
                    ball_type=BallType.SPECIAL,
                    number=self.special_ball,
                )
            )
        return rows


class DrawNumber(BaseModel):
    """One ball in one draw — normalized form (draw_id, position, number)."""

    model_config = ConfigDict(extra="forbid")

    draw_id: str
    ball_position: int | None = Field(
        default=None,
        description="Source-defined ordering; None iff order is not preserved",
    )
    ball_type: BallType = BallType.MAIN
    number: int

    @model_validator(mode="after")
    def _check_position(self) -> "DrawNumber":
        if self.ball_position is not None and self.ball_position < 1:
            raise ValueError("ball_position must be >= 1 or None")
        return self
