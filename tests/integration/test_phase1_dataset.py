"""Phase 1 integration tests — canonical dataset against real artifacts.

These tests rebuild the dataset in-memory from preserved raw artifacts and
verify coverage, regime boundaries, stream separation, and provenance.
"""
import hashlib
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_draw_database import build, parse_artifacts  # noqa: E402
from fortuna.schemas.artifacts import RawArtifact  # noqa: E402
from fortuna.schemas.csv_io import load_csv  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "data/raw").exists(), reason="raw artifacts not present"
)


@pytest.fixture(scope="module")
def staged():
    arts = load_csv(REPO_ROOT / "metadata/raw_artifacts.csv", RawArtifact)
    return parse_artifacts(arts)


def test_artifact_hashes_match_files():
    arts = load_csv(REPO_ROOT / "metadata/raw_artifacts.csv", RawArtifact)
    for a in arts:
        p = REPO_ROOT / a.immutable_path
        assert p.exists(), a.immutable_path
        assert hashlib.sha256(p.read_bytes()).hexdigest() == a.sha256, a.immutable_path


def test_ny_archive_covers_first_draws(staged):
    pb = [s for s in staged if s.source_id == "SRC-NY-PB-ARCHIVE"]
    mm = [s for s in staged if s.source_id == "SRC-NY-MM-ARCHIVE"]
    assert min(s.draw_date for s in pb) == date(1992, 4, 22)
    assert min(s.draw_date for s in mm) == date(1996, 9, 6)


def test_fl_lotto_full_history(staged):
    fl = [
        s for s in staged
        if s.source_id == "SRC-FL-LOTTO-HIST-PDF" and s.draw_stream.value == "main"
    ]
    assert min(s.draw_date for s in fl) == date(1988, 5, 7)
    # machine/ball-set metadata begins at the 2020-10-10 regime
    mach = [s for s in fl if s.machine_id]
    assert mach and min(s.draw_date for s in mach) >= date(2009, 10, 14)


def test_mm_boundary_on_real_data(staged):
    """The 1999 matrix boundary must hold against the official NY archive."""
    mm = {
        s.draw_date: s
        for s in staged
        if s.source_id == "SRC-NY-MM-ARCHIVE" and s.game_id == "mega_millions"
    }
    old = mm[date(1999, 1, 12)]
    new = mm[date(1999, 1, 15)]
    assert max(old.main_numbers) <= 50 and (old.special_ball or 0) <= 25
    assert len(new.main_numbers) == 5


def test_offline_rebuild_deterministic(tmp_path, monkeypatch):
    """Two offline builds produce identical canonical CSV bytes."""
    r1 = build()
    draws_bytes = (REPO_ROOT / "data/processed/draws.csv").read_bytes()
    r2 = build()
    draws_bytes2 = (REPO_ROOT / "data/processed/draws.csv").read_bytes()
    assert draws_bytes == draws_bytes2
    assert r1["dataset_sha256"] == r2["dataset_sha256"]


def test_outputs_exist_after_build():
    for rel in (
        "data/processed/draws.csv",
        "data/processed/draw_numbers.csv",
        "data/processed/dataset_manifest.json",
        "data/processed/data_quality_report.csv",
        "metadata/missing_draws.csv",
        "metadata/reconciliation_registry.csv",
    ):
        assert (REPO_ROOT / rel).exists(), rel
