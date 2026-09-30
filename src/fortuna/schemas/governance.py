"""Governance registry schemas (registry/*.csv).

These registries are append-only research-governance ledgers. In Phase 0 they
are created empty (header only); rows are added as the program progresses.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fortuna.schemas.common import parse_list


class Hypothesis(BaseModel):
    """A registered hypothesis — MUST be logged before the analysis it
    describes is run (discovery/confirmation separation)."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(pattern=r"^H-\d{3}$")
    registered_date: date
    registered_by: str
    game_id: str | None = None
    statistical_regime_id: str | None = None
    statement: str
    analysis_plan: str = Field(description="Pre-specified test procedure")
    significance_threshold: float = Field(default=0.05, gt=0, lt=1)
    correction_method: str | None = Field(
        default=None, description="Multiple-testing correction, if any"
    )
    data_slice: str = Field(description="Exact draw population to be tested")
    status: str = Field(default="registered")
    notes: str | None = None


class Experiment(BaseModel):
    """A registered analysis run against registered hypotheses."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^EXP-\d{3}$")
    hypothesis_ids: list[str]
    registered_date: date
    executed_date: date | None = None
    code_version: str | None = Field(default=None, description="git SHA")
    data_slice: str
    result_summary: str | None = None
    outcome: str | None = Field(
        default=None, description="rejected|inconclusive|supported|exploratory"
    )
    artifacts: str | None = None
    notes: str | None = None

    @field_validator("hypothesis_ids", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return parse_list(v)
        return v


class ModelRegistration(BaseModel):
    """Model registry — Phase 1+ only. Exists now so governance is in place
    before any modeling begins."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_id: str = Field(pattern=r"^M-\d{3}$")
    registered_date: date
    game_id: str
    statistical_regime_id: str
    description: str
    training_window: str | None = None
    code_version: str | None = None
    evaluation_protocol: str | None = None
    status: str = Field(default="registered")
    notes: str | None = None


class ProspectivePrediction(BaseModel):
    """Prospective prediction ledger — immutable once registered.

    Any predictive claim must be logged BEFORE the draw it covers. The ledger
    distinguishes research predictions from a system that claims an edge.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    prediction_id: str = Field(pattern=r"^P-\d{4}$")
    logged_at: datetime
    model_id: str | None = None
    game_id: str
    draw_date: date = Field(description="The future draw this prediction covers")
    predicted_numbers: str | None = None
    claimed_edge: str | None = None
    result: str | None = None
    outcome_recorded_at: datetime | None = None
    notes: str | None = None


class DecisionLogEntry(BaseModel):
    """Append-only decision log for material research decisions."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(pattern=r"^D-\d{3}$")
    date: date
    decided_by: str
    decision: str
    rationale: str
    alternatives_considered: str | None = None
    supersedes: str | None = None
    notes: str | None = None
