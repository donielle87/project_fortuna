"""Phase 0 verification runner.

Loads every registry through its pydantic contract, checks regime integrity,
provenance linkage (source registry <-> raw artifact manifest <-> files on
disk), and prints a PASS/FAIL summary. Read-only: never mutates data.
"""
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from fortuna.config import load_all_game_configs  # noqa: E402
from fortuna.rules import check_regime_integrity, load_regimes  # noqa: E402
from fortuna.rules.registry import load_games  # noqa: E402
from fortuna.rules.rule_log import load_rule_change_log  # noqa: E402
from fortuna.schemas.artifacts import RawArtifact  # noqa: E402
from fortuna.schemas.csv_io import load_csv  # noqa: E402
from fortuna.schemas.governance import (  # noqa: E402
    DecisionLogEntry,
    Experiment,
    Hypothesis,
    ModelRegistration,
    ProspectivePrediction,
)
from fortuna.schemas.sources import DrawSource, Source  # noqa: E402

META = REPO_ROOT / "metadata"
REG = REPO_ROOT / "registry"

failures: list[str] = []
warnings: list[str] = []


def check(label, fn):
    try:
        result = fn()
        print(f"  OK   {label}")
        return result
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{label}: {exc}")
        print(f"  FAIL {label}: {exc}")
        return None


def main() -> int:
    print("Phase 0 verification — data contracts & provenance\n")

    print("[1] Schemas / registries")
    games = check("metadata/games.csv", lambda: load_games(META / "games.csv"))
    sources = check(
        "metadata/source_registry.csv",
        lambda: load_csv(META / "source_registry.csv", Source),
    )
    artifacts = check(
        "metadata/raw_artifacts.csv",
        lambda: load_csv(META / "raw_artifacts.csv", RawArtifact),
    )
    draw_sources = check(
        "metadata/draw_sources.csv",
        lambda: load_csv(META / "draw_sources.csv", DrawSource),
    )
    log = check(
        "metadata/rule_change_log.csv",
        lambda: load_rule_change_log(META / "rule_change_log.csv"),
    )
    for name, model in [
        ("hypothesis_registry.csv", Hypothesis),
        ("experiment_registry.csv", Experiment),
        ("model_registry.csv", ModelRegistration),
        ("prediction_ledger.csv", ProspectivePrediction),
        ("decision_log.csv", DecisionLogEntry),
    ]:
        check(f"registry/{name}", lambda n=name, m=model: load_csv(REG / n, m))

    print("\n[2] Game configs")
    configs = check(
        "config/games/*.yaml",
        lambda: load_all_game_configs(REPO_ROOT / "config/games"),
    )

    print("\n[3] Regime inventory integrity")
    regimes = check("metadata/game_regimes.csv", lambda: load_regimes(META / "game_regimes.csv"))
    if regimes:
        for w in check_regime_integrity(regimes):
            warnings.append(w)
            print(f"  WARN {w}")
        unresolved = [r.regime_id for r in regimes
                      if r.verification_status.value == "unresolved"]
        partial = [r.regime_id for r in regimes
                   if r.verification_status.value == "partially_verified"]
        if unresolved:
            warnings.append(f"unresolved regimes: {unresolved}")
            print(f"  WARN unresolved regimes: {unresolved}")
        if partial:
            print(f"  INFO partially_verified regimes: {partial}")
        # Material-boundary quarantine enforcement:
        # a baseline/matrix/mechanism regime that is not 'verified' MUST carry
        # a quarantine window (first_unambiguous_draw > first_affected_draw)
        # so no uncertain draw can be auto-assigned or pooled. Schedule/
        # economic/administrative partials are pool-neutral and exempt.
        material = {"baseline", "matrix", "mechanism"}
        for r in regimes:
            if (r.change_classification.value in material
                    and r.verification_status.value != "verified"):
                if r.first_unambiguous_draw is None:
                    failures.append(
                        f"{r.regime_id}: {r.change_classification.value} boundary is "
                        f"{r.verification_status.value} but has no quarantine window "
                        "(first_unambiguous_draw) — treated as definitive")
                else:
                    print(f"  INFO {r.regime_id}: unresolved material boundary — "
                          f"quarantine {r.first_affected_draw}.."
                          f"{r.first_unambiguous_draw}")
        # Runtime probe: quarantined windows must actually raise on assignment
        from fortuna.rules.assign import UnverifiedBoundaryError, assign_regime
        for r in regimes:
            if r.first_unambiguous_draw is not None:
                try:
                    assign_regime(r.game_id, r.first_affected_draw, regimes)
                    failures.append(
                        f"{r.regime_id}: assign_regime succeeded inside the "
                        "quarantine window — boundary can silently assign")
                except UnverifiedBoundaryError:
                    print(f"  OK   {r.regime_id}: quarantined draw raises "
                          "UnverifiedBoundaryError")
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        f"{r.regime_id}: quarantine window raised wrong error: {exc}")
                try:
                    assign_regime(r.game_id, r.first_unambiguous_draw, regimes)
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        f"{r.regime_id}: first unambiguous draw "
                        f"{r.first_unambiguous_draw} fails assignment: {exc}")
        # every game must have >=1 regime and >=1 verified regime
        for g in {r.game_id for r in regimes}:
            rows = [r for r in regimes if r.game_id == g]
            if not any(r.verification_status.value == "verified" for r in rows):
                failures.append(f"{g}: no verified regime")
                print(f"  FAIL {g}: no verified regime")
        # pool-group count sanity
        for g in {r.game_id for r in regimes}:
            groups = {r.statistical_regime_id for r in regimes if r.game_id == g}
            print(f"  INFO {g}: {len([r for r in regimes if r.game_id == g])} regimes, "
                  f"{len(groups)} pool group(s): {sorted(groups)}")

    print("\n[4] Cross-reference checks")
    if regimes and games:
        game_ids = {g.game_id for g in games}
        bad = {r.game_id for r in regimes} - game_ids
        if bad:
            failures.append(f"regimes reference unknown game_ids {bad}")
            print(f"  FAIL regimes reference unknown game_ids {bad}")
        else:
            print("  OK   all regime game_ids resolve")
    if regimes and configs:
        reg_ids = {r.regime_id for r in regimes}
        pool_ids = {r.statistical_regime_id for r in regimes}
        for gid, cfg in configs.items():
            if cfg.current_regime_id not in reg_ids:
                failures.append(f"{gid}: config current_regime_id {cfg.current_regime_id} unknown")
            if cfg.current_statistical_regime_id not in pool_ids:
                failures.append(
                    f"{gid}: config pool group {cfg.current_statistical_regime_id} unknown")
        print("  OK   game configs resolve to regime inventory")
    if draw_sources and sources:
        src_ids = {s.source_id for s in sources}
        bad_ds = [d.draw_source_id for d in draw_sources
                  if d.source_id and d.source_id not in src_ids]
        if bad_ds:
            failures.append(f"draw_sources cite unregistered sources: {bad_ds}")
            print(f"  FAIL draw_sources cite unregistered sources: {bad_ds}")
        else:
            print("  OK   draw_source source references resolve")
    if regimes and log:
        reg_ids = {r.regime_id for r in regimes}
        badrc = [c.change_id for c in log
                 if c.resulting_regime_id and c.resulting_regime_id not in reg_ids]
        if badrc:
            failures.append(f"rule_change_log rows reference unknown regimes: {badrc}")
            print(f"  FAIL rule_change_log -> unknown regimes: {badrc}")
        else:
            print("  OK   rule_change_log regime references resolve")
        if sources:
            src_ids = {s.source_id for s in sources}
            badsrc = {sid for c in log for sid in c.source_ids} - src_ids
            if badsrc:
                failures.append(f"rule_change_log cites unregistered sources: {sorted(badsrc)}")
                print(f"  FAIL unregistered source ids in log: {sorted(badsrc)}")
            else:
                print("  OK   rule_change_log source citations resolve")

    print("\n[5] Provenance: artifacts <-> registry <-> disk")
    if artifacts and sources:
        src_ids = {s.source_id for s in sources}
        bad = [a.artifact_id for a in artifacts if a.source_id not in src_ids]
        if bad:
            failures.append(f"artifacts with unknown source_id: {bad}")
        art_hashes = {a.sha256: a for a in artifacts}
        dupes = len(artifacts) - len({a.sha256 for a in artifacts})
        if dupes:
            warnings.append(f"{dupes} duplicate-content artifacts (allowed but noted)")
        for a in artifacts:
            p = REPO_ROOT / a.immutable_path
            if not p.exists():
                failures.append(f"{a.artifact_id}: file missing {a.immutable_path}")
                continue
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            if digest != a.sha256:
                failures.append(f"{a.artifact_id}: sha256 mismatch on disk")
        # registry rows that fetched content should match manifest
        matched = sum(1 for s in sources if s.content_sha256 in art_hashes)
        print(f"  OK   {len(artifacts)} artifacts checked; "
              f"{matched}/{len(sources)} registry rows linked to manifest")

    print("\n[6] Coverage statement")
    if regimes:
        for g in sorted({r.game_id for r in regimes}):
            rows = sorted([r for r in regimes if r.game_id == g],
                          key=lambda r: r.span_start)
            print(f"  {g}: {rows[0].span_start} .. "
                  f"{rows[-1].span_end or 'present'} "
                  f"({len(rows)} regimes)")

    print("\n" + "=" * 60)
    if failures:
        print(f"RESULT: FAIL — {len(failures)} failure(s), {len(warnings)} warning(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"RESULT: PASS — 0 failures, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
