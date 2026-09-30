"""Integration test: source -> immutable artifact -> draw ingest -> regime
assignment -> validation -> pooling guard, using the real registries."""
import hashlib
from datetime import date

import pytest

from fortuna.provenance.store import ArtifactStore
from fortuna.rules.assign import IncompatibleMatrixError, assert_poolable, assign_regime
from fortuna.schemas.draws import Draw, DrawValidationStatus
from fortuna.validation.draw_validator import validate_draws


def test_full_phase0_chain(tmp_path, regimes):
    # 1. Provenance: store a fetched artifact, verify hash lands on disk
    store = ArtifactStore(raw_dir=tmp_path / "data" / "raw",
                          manifest_path=tmp_path / "metadata" / "raw_artifacts.csv")
    payload = b"official source bytes"
    art = store.store("SRC-TEST-E2E", payload, "text/plain",
                      filename_hint="rules.txt")
    artifact_path = tmp_path / art.immutable_path
    assert artifact_path.exists()
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == art.sha256

    # 2. A real draw record arrives; the regime is assigned, not assumed
    regime = assign_regime("powerball", date(2016, 1, 6), regimes)
    assert regime.regime_id == "PB-R009"

    draw = Draw(
        draw_id="PB-D-2016-01-06", game_id="powerball",
        regime_id=regime.regime_id, draw_date=date(2016, 1, 6),
        main_numbers=[2, 12, 22, 28, 50], special_ball=7,
        source_id="SRC-NY-PB-DATA", raw_artifact_sha256=art.sha256,
    )
    results = validate_draws([draw], regimes)
    assert results == {}
    assert draw.validation_status == DrawValidationStatus.VALID

    # 3. The pooling guard still blocks mixing eras even in a real pipeline
    other = Draw(draw_id="PB-D-2013-01-02", game_id="powerball",
                 regime_id="PB-R008", draw_date=date(2013, 1, 2),
                 main_numbers=[1, 2, 3, 4, 5], special_ball=6)
    with pytest.raises(IncompatibleMatrixError):
        assert_poolable([draw, other], regimes)

    # 4. Double Play stream cannot be conflated with FL Lotto main draws:
    #    a DP-era draw and a 6/49-era draw must never share a pool.
    fl_old = Draw(draw_id="FL-D-1990-01-06", game_id="florida_lotto",
                  regime_id="FL-R001", draw_date=date(1990, 1, 6),
                  main_numbers=[1, 2, 3, 4, 5, 6])
    fl_new = Draw(draw_id="FL-D-2021-01-02", game_id="florida_lotto",
                  regime_id="FL-R004", draw_date=date(2021, 1, 2),
                  main_numbers=[1, 2, 3, 4, 5, 6])
    with pytest.raises(IncompatibleMatrixError):
        assert_poolable([fl_old, fl_new], regimes)
