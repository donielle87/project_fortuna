"""Immutable raw-artifact store (Task 7).

Layout::

    data/raw/<source_id>/<YYYYMMDDTHHMMSSZ>_<sha256[:12]>.<ext>

Rules:
- artifacts are NEVER overwritten;
- re-retrieved content with a NEW sha256 produces a new artifact file;
- re-retrieved content with an IDENTICAL sha256 registers a retrieval event in
  the artifact log but reuses the existing file (dedupe-by-hash);
- every store call appends a row to metadata/raw_artifacts.csv.
"""

import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path

from fortuna.provenance.hashing import sha256_bytes
from fortuna.schemas.artifacts import RawArtifact
from fortuna.schemas.csv_io import dump_csv, load_csv

_EXT_BY_MIME = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "application/xml": ".xml",
    "text/xml": ".xml",
}


def _ext_for(mime_type: str, filename_hint: str | None) -> str:
    base = mime_type.split(";")[0].strip().lower()
    if base in _EXT_BY_MIME:
        return _EXT_BY_MIME[base]
    if filename_hint:
        suffix = Path(filename_hint).suffix
        if suffix:
            return suffix
    return mimetypes.guess_extension(base) or ".bin"


class ArtifactStore:
    """Immutable store rooted at data/raw with a CSV artifact manifest."""

    def __init__(
        self,
        raw_dir: str | Path = "data/raw",
        manifest_path: str | Path = "metadata/raw_artifacts.csv",
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.manifest_path = Path(manifest_path)
        # Repo root is inferred from the manifest location (metadata/ lives
        # directly under the repo root); immutable_path is repo-relative.
        self.repo_root = self.manifest_path.resolve().parent.parent
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> list[RawArtifact]:
        if self.manifest_path.exists():
            return load_csv(self.manifest_path, RawArtifact)
        return []

    def _save_manifest(self, rows: list[RawArtifact]) -> None:
        dump_csv(self.manifest_path, rows)

    def store(
        self,
        source_id: str,
        content: bytes,
        mime_type: str,
        retrieved_at: datetime | None = None,
        filename_hint: str | None = None,
        parser_version: str | None = None,
    ) -> RawArtifact:
        retrieved_at = retrieved_at or datetime.now(UTC)
        digest = sha256_bytes(content)
        manifest = self._load_manifest()

        existing = next(
            (a for a in manifest if a.source_id == source_id and a.sha256 == digest),
            None,
        )
        seq = max((int(a.artifact_id.split("-")[1]) for a in manifest), default=0) + 1
        artifact_id = f"RA-{seq:06d}"

        if existing is not None:
            # Content unchanged: reuse the immutable file, but still record the
            # retrieval event so provenance reflects the check.
            path = self.repo_root / existing.immutable_path
            if not path.exists():
                raise FileNotFoundError(
                    f"manifest references missing artifact {existing.immutable_path}"
                )
            filename = path.name
            immutable_path = existing.immutable_path
        else:
            ext = _ext_for(mime_type, filename_hint)
            stamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
            filename = f"{stamp}_{digest[:12]}{ext}"
            dest_dir = self.raw_dir / source_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename
            if dest.exists():
                raise FileExistsError(f"refusing to overwrite {dest}")
            dest.write_bytes(content)
            immutable_path = os.path.relpath(dest, self.repo_root).replace("\\", "/")

        artifact = RawArtifact(
            artifact_id=artifact_id,
            source_id=source_id,
            filename=filename,
            mime_type=mime_type.split(";")[0].strip().lower(),
            retrieved_at=retrieved_at,
            sha256=digest,
            immutable_path=immutable_path,
            parser_version=parser_version,
        )
        manifest.append(artifact)
        self._save_manifest(manifest)
        return artifact
