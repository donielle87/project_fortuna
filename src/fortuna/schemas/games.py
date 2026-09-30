"""Game schema."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class Game(BaseModel):
    """A lottery draw game tracked by Project Fortuna."""

    model_config = ConfigDict(extra="forbid")

    game_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", description="Stable snake_case id")
    name: str
    operator: str
    jurisdiction: str
    launch_date: date | None = None
    active: bool = True
    notes: str | None = None
