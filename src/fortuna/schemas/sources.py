"""Source registry schemas (Tasks 6 and 8)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fortuna.schemas.common import SourceType, parse_list


class Source(BaseModel):
    """A provenance source.

    authority_tier:
      1 = official lottery operator / official rules / official government source
      2 = official archived publication, annual report, supporting official material
      3 = secondary source used only for reconciliation or gap identification
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^SRC-[A-Z0-9][A-Z0-9-]*$")
    game: str = Field(description="game_id, ';'-separated list, or 'multi'")
    publisher: str
    source_type: SourceType
    url: str
    authority_tier: int = Field(ge=1, le=3)
    retrieved_at: datetime | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    local_raw_path: str | None = None
    notes: str | None = None


class DrawSource(BaseModel):
    """Inventory record for an official historical winning-number source
    (Task 8). Documents capabilities and limitations for Phase 1 ingestion."""

    model_config = ConfigDict(extra="forbid")

    draw_source_id: str = Field(pattern=r"^DS-[A-Z0-9][A-Z0-9-]*$")
    game_id: str
    publisher: str
    source_id: str | None = Field(default=None, description="link to source_registry")
    url: str | None = Field(default=None, description="Empty for documented coverage gaps")
    authority_tier: int = Field(ge=1, le=3)
    available_start: str | None = Field(default=None, description="earliest draw covered")
    available_end: str | None = Field(default=None, description="latest draw covered or 'present'")
    format: str = Field(description="e.g. html, csv, json, pdf")
    pagination: str | None = None
    query_parameters: str | None = None
    has_draw_identifier: bool = False
    preserves_draw_order: bool = False
    has_jackpot: bool = False
    has_jackpot_winners: bool = False
    has_multiplier: bool = False
    has_machine_id: bool = False
    has_ball_set_id: bool = False
    has_drawing_location: bool = False
    known_limitations: str | None = None
    recommended_ingestion_strategy: str | None = None
    notes: str | None = None


class RuleChange(BaseModel):
    """Rule-change log record (Task 5): every legal/statistical event."""

    model_config = ConfigDict(extra="forbid")

    change_id: str = Field(pattern=r"^RC-[A-Z0-9][A-Z0-9-]*$")
    game_id: str
    legal_effective_date: str | None = Field(
        default=None, description="ISO date or 'unknown'"
    )
    first_affected_draw: str | None = Field(
        default=None, description="ISO date of first draw under new rules, or 'unknown'"
    )
    last_prior_draw: str | None = Field(
        default=None, description="ISO date of final draw under prior rules, or 'unknown'"
    )
    classification: str = Field(
        description="matrix|mechanism|schedule|economic|administrative|baseline|unresolved"
    )
    statistically_material: bool = Field(
        description="True iff the change plausibly alters the sampling process"
    )
    before_matrix: str | None = None
    after_matrix: str | None = None
    resulting_regime_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    verification_status: str = "unresolved"
    notes: str | None = None

    @field_validator("source_ids", mode="before")
    @classmethod
    def _split_sources(cls, v: object) -> object:
        if isinstance(v, str):
            return parse_list(v)
        return v
