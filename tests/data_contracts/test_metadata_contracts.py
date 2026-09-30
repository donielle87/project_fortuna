"""Data-contract tests: every registry CSV must satisfy its schema and
all cross-references must resolve."""
import hashlib
from pathlib import Path

import pytest

from fortuna.config import load_all_game_configs
from fortuna.rules import check_regime_integrity, load_regimes
from fortuna.rules.registry import load_games
from fortuna.rules.rule_log import load_rule_change_log
from fortuna.schemas.artifacts import RawArtifact
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.governance import (
    DecisionLogEntry,
    Experiment,
    Hypothesis,
    ModelRegistration,
    ProspectivePrediction,
)
from fortuna.schemas.sources import DrawSource, Source

META = Path(__file__).resolve().parents[2] / "metadata"
REG = Path(__file__).resolve().parents[2] / "registry"
ROOT = META.parent


def test_games_contract():
    games = load_games(META / "games.csv")
    assert {g.game_id for g in games} == {"powerball", "mega_millions", "florida_lotto"}


def test_source_registry_contract():
    sources = load_csv(META / "source_registry.csv", Source)
    assert len(sources) >= 20
    assert all(s.authority_tier in (1, 2, 3) for s in sources)


def test_regime_inventory_integrity():
    regimes = load_regimes(META / "game_regimes.csv")
    warnings = check_regime_integrity(regimes)
    assert warnings == [], f"unexpected integrity warnings: {warnings}"


def test_every_game_has_verified_regime():
    regimes = load_regimes(META / "game_regimes.csv")
    for g in {"powerball", "mega_millions", "florida_lotto"}:
        rows = [r for r in regimes if r.game_id == g]
        assert rows, g
        assert any(r.verification_status.value == "verified" for r in rows), g


def test_unverified_material_boundaries_are_quarantined():
    """A baseline/matrix/mechanism regime that is not verified MUST carry a
    quarantine window so uncertain draws cannot be silently assigned."""
    regimes = load_regimes(META / "game_regimes.csv")
    material = {"baseline", "matrix", "mechanism"}
    for r in regimes:
        if (r.change_classification.value in material
                and r.verification_status.value != "verified"):
            assert r.first_unambiguous_draw is not None, (
                f"{r.regime_id}: unverified {r.change_classification.value} "
                "boundary treated as definitive")
            assert r.first_unambiguous_draw > r.first_affected_draw


def test_regime_sources_registered():
    regimes = load_regimes(META / "game_regimes.csv")
    src_ids = {s.source_id for s in load_csv(META / "source_registry.csv", Source)}
    for r in regimes:
        assert r.source_id in src_ids, f"{r.regime_id} cites {r.source_id}"


def test_rule_change_log_contract():
    log = load_rule_change_log(META / "rule_change_log.csv")
    reg_ids = {r.regime_id for r in load_regimes(META / "game_regimes.csv")}
    src_ids = {s.source_id for s in load_csv(META / "source_registry.csv", Source)}
    for c in log:
        if c.resulting_regime_id:
            assert c.resulting_regime_id in reg_ids, c.change_id
        for sid in c.source_ids:
            assert sid in src_ids, f"{c.change_id} cites unregistered {sid}"


def test_draw_sources_contract():
    rows = load_csv(META / "draw_sources.csv", DrawSource)
    src_ids = {s.source_id for s in load_csv(META / "source_registry.csv", Source)}
    for d in rows:
        if d.source_id:
            assert d.source_id in src_ids


def test_artifact_manifest_matches_disk():
    artifacts = load_csv(META / "raw_artifacts.csv", RawArtifact)
    assert artifacts
    for a in artifacts:
        p = ROOT / a.immutable_path
        assert p.exists(), f"missing {a.immutable_path}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == a.sha256


def test_source_registry_links_to_artifacts():
    sources = load_csv(META / "source_registry.csv", Source)
    art_hashes = {a.sha256 for a in load_csv(META / "raw_artifacts.csv", RawArtifact)}
    linked = [s for s in sources if s.content_sha256 in art_hashes]
    assert len(linked) == len([s for s in sources if s.content_sha256])


def test_game_configs_resolve():
    configs = load_all_game_configs(ROOT / "config" / "games")
    regimes = load_regimes(META / "game_regimes.csv")
    reg_ids = {r.regime_id for r in regimes}
    pool_ids = {r.statistical_regime_id for r in regimes}
    for cfg in configs.values():
        assert cfg.current_regime_id in reg_ids
        assert cfg.current_statistical_regime_id in pool_ids


@pytest.mark.parametrize("name,model", [
    ("hypothesis_registry.csv", Hypothesis),
    ("experiment_registry.csv", Experiment),
    ("model_registry.csv", ModelRegistration),
    ("prediction_ledger.csv", ProspectivePrediction),
    ("decision_log.csv", DecisionLogEntry),
])
def test_governance_registries_parse(name, model):
    load_csv(REG / name, model)  # must not raise
