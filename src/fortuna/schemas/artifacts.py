"""Raw artifact schema (Task 7) — immutable retrieved-source storage."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RawArtifact(BaseModel):
    """One immutable retrieved copy of a source's content.

    Raw artifacts are never overwritten. Re-retrieval of changed content
    produces a new artifact with a new sha256 and retrieval timestamp.
    """

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(pattern=r"^RA-\d{6}$")
    source_id: str = Field(pattern=r"^SRC-[A-Z0-9][A-Z0-9-]*$")
    filename: str
    mime_type: str
    retrieved_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    immutable_path: str = Field(description="Repo-relative path under data/raw/")
    parser_version: str | None = None
