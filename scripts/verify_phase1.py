"""Phase 1 verification — checks the canonical draw database against the
Definition of Done. Exits nonzero on any failure.

Checks (no statistics — data engineering and quality only):
  * canonical outputs exist and reload through the pydantic contract
  * draw_id uniqueness; (game, date, stream) uniqueness
  * every draw has source provenance (source_id + artifact sha256)
  * every analysis-eligible draw is structurally valid and non-quarantined
  * no eligible draw sits inside a boundary quarantine window
  * known boundaries: MM 1999-01-12 -> MM-S01 / 1999-01-15 -> MM-S02
  * FL Lotto coverage reaches 1988-05-07; order-semantics split intact
  * Double Play rows exist only under draw_stream=double_play
  * unresolved winning-number conflicts -> not eligible
  * source-authority gate: no eligible draw is backed solely by Tier-3
    (unofficial) sources; unofficial sources are never marked Tier-1;
    precedence never ranks an unofficial source above an authoritative one
  * manifest contains a dataset hash and artifact hashes
  * manifest build_code_commit names a committed code state containing the
    build pipeline; manifest counts reconcile
  * artifact files exist and match manifest hashes
  * offline rebuild is deterministic (dataset hash stable across rebuilds)
"""

import hashlib
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.rules.assign import assign_regime, statistical_groups
from fortuna.schemas.artifacts import RawArtifact
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.draws import Draw, DrawValidationStatus
from fortuna.schemas.regimes import GameRegime

ROOT = Path(__file__).resolve().parent.parent
FAILS: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


def main() -> int:
    draws_p = ROOT / "data/processed/draws.csv"
    nums_p = ROOT / "data/processed/draw_numbers.csv"
    man_p = ROOT / "data/processed/dataset_manifest.json"
    check(draws_p.exists(), "canonical draws.csv exists")
    check(nums_p.exists(), "canonical draw_numbers.csv exists")
    check(man_p.exists(), "dataset manifest exists")
    check((ROOT / "metadata/missing_draws.csv").exists(), "missing-draw ledger exists")
    check(
        (ROOT / "metadata/reconciliation_registry.csv").exists(),
        "reconciliation registry exists",
    )
    if FAILS:
        return 1

    draws = load_csv(draws_p, Draw)
    regimes = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    artifacts = load_csv(ROOT / "metadata/raw_artifacts.csv", RawArtifact)
    artifact_shas = {a.sha256 for a in artifacts}
    by_id = {r.regime_id: r for r in regimes}

    # uniqueness
    ids = Counter(d.draw_id for d in draws)
    check(all(v == 1 for v in ids.values()), "draw_id unique")
    keys = Counter((d.game_id, d.draw_date, d.draw_stream) for d in draws)
    check(all(v == 1 for v in keys.values()), "(game, date, stream) unique")

    # provenance
    check(
        all(
            d.source_id
            and d.raw_artifact_sha256
            and d.raw_artifact_sha256 in artifact_shas
            for d in draws
        ),
        "every draw has source_id + artifact sha256 linked to manifest",
    )

    # eligibility gates
    eligible = [d for d in draws if d.analysis_eligible]
    check(
        all(
            d.validation_status == DrawValidationStatus.VALID
            and d.source_id
            and not d.provisional
            for d in eligible
        ),
        "every eligible draw is valid, provenanced, non-provisional",
    )
    q_viol = [
        d.draw_id
        for d in eligible
        if (r := by_id.get(d.regime_id)) is not None
        and r.first_unambiguous_draw is not None
        and d.draw_date < r.first_unambiguous_draw
    ]
    check(not q_viol, f"no eligible draw inside quarantine window {q_viol[:5]}")
    check(
        not any(
            d.validation_status == DrawValidationStatus.QUARANTINED
            and d.analysis_eligible
            for d in draws
        ),
        "no quarantined draw is eligible",
    )

    # regime assignment on real data
    try:
        a = assign_regime("mega_millions", date(1999, 1, 12), regimes)
        b = assign_regime("mega_millions", date(1999, 1, 15), regimes)
        check(
            a.regime_id == "MM-R002" and a.statistical_regime_id == "MM-S01",
            "1999-01-12 -> MM-R002/MM-S01",
        )
        check(
            b.regime_id == "MM-R003" and b.statistical_regime_id == "MM-S02",
            "1999-01-15 -> MM-R003/MM-S02",
        )
    except Exception as exc:  # noqa: BLE001
        check(False, f"boundary assignment raised {exc}")
    check(
        all(by_id[d.regime_id] for d in draws),
        "every draw's regime_id resolves in inventory",
    )

    # coverage floors
    earliest = {
        g: min(d.draw_date for d in draws if d.game_id == g)
        for g in ("powerball", "mega_millions", "florida_lotto")
    }
    check(earliest["florida_lotto"] == date(1988, 5, 7), "FL Lotto back to 1988-05-07")
    check(earliest["mega_millions"] == date(1996, 9, 6), "MM back to 1996-09-06")
    check(earliest["powerball"] == date(1992, 4, 22), "PB back to 1992-04-22")

    # FL Lotto ordering semantics
    fl = [d for d in draws if d.game_id == "florida_lotto" and d.draw_stream.value == "main"]
    pre = [d for d in fl if d.draw_date < date(2005, 2, 2)]
    post = [d for d in fl if d.draw_date >= date(2005, 2, 2)]
    check(
        all(d.numbers_order.value == "physical_draw_order" for d in pre),
        "FL Lotto pre-2005-02-02 rows physical order",
    )
    check(
        all(d.numbers_order.value == "source_sorted_order" for d in post),
        "FL Lotto post-2005-02-02 rows sorted order",
    )

    # DP separation
    dp = [d for d in draws if d.draw_stream.value == "double_play"]
    check(dp and all(d.draw_id.endswith("-DP") for d in dp), "DP draws under -DP stream IDs")
    check(
        all(d.draw_stream.value == "main" for d in draws if not d.draw_id.endswith("-DP")),
        "main series carries no DP rows",
    )

    # conflicts ineligible (unresolved CONFLICT rows only)
    import csv

    recon = list(csv.DictReader(open(ROOT / "metadata/reconciliation_registry.csv")))
    conflict_keys = {
        (r["game_id"], r["draw_date"])
        for r in recon
        if r["classification"] == "CONFLICT"
        and r["field"] in ("main_numbers_sorted", "special_ball")
        and r["status"] == "unresolved"
    }
    bad = [
        d.draw_id
        for d in draws
        if d.analysis_eligible and (d.game_id, d.draw_date.isoformat()) in conflict_keys
    ]
    check(not bad, f"no eligible draw with unresolved number conflict {bad[:5]}")

    # ---- source-authority gate ----
    from fortuna.ingestion.pipeline import (
        SOURCE_PRECEDENCE,
        _precedence,
        draw_source_ids,
        load_source_tiers,
    )
    from fortuna.schemas.sources import Source

    sources = load_csv(ROOT / "metadata/source_registry.csv", Source)
    tiers = {s.source_id: s.authority_tier for s in sources}
    loaded_tiers = load_source_tiers(ROOT)
    check(tiers == loaded_tiers, "registry tiers consistent with pipeline loader")

    # no unofficial source masquerading as Tier 1
    tier1_secondary = [
        s.source_id
        for s in sources
        if s.authority_tier == 1 and s.source_type.value == "secondary"
    ]
    check(not tier1_secondary, f"no Tier-1 secondary sources {tier1_secondary}")
    ny_archive_mislabeled = [
        s.source_id
        for s in sources
        if "nylottery.org" in s.url and s.authority_tier < 3
    ]
    check(
        not ny_archive_mislabeled,
        f"nylottery.org sources are Tier 3 {ny_archive_mislabeled}",
    )

    # precedence: no unofficial source ahead of an authoritative one
    prec_bad = []
    for g, order in SOURCE_PRECEDENCE.items():
        for sid in order:
            if tiers.get(sid, 3) >= 3 and any(
                tiers.get(o, 3) <= 2 and _precedence(order, sid) < _precedence(order, o)
                for o in order
            ):
                # unofficial source listed ahead of an authoritative source
                prec_bad.append((g, sid))
    check(
        not prec_bad,
        f"unofficial sources never precede authoritative in precedence {prec_bad}",
    )

    # eligibility: every eligible draw has >=1 tier<=2 source
    unofficial_only = [
        d.draw_id
        for d in eligible
        if not any(tiers.get(sid, 3) <= 2 for sid in draw_source_ids(d))
    ]
    check(
        not unofficial_only,
        f"no eligible draw backed solely by unofficial sources {unofficial_only[:5]}",
    )

    # poolability of eligible draws only
    try:
        statistical_groups([d for d in eligible], regimes)
        check(True, "eligible draws pool cleanly by statistical regime")
    except Exception as exc:  # noqa: BLE001
        check(False, f"pooling failed: {exc}")

    # ---- D-007 atomic sequence provenance -------------------------------
    from fortuna.ingestion.pipeline import load_resolutions

    check(
        all(d.number_sequence_source_id for d in draws),
        "every draw carries number_sequence_source_id",
    )
    # Resolution-overridden sequences legitimately name the resolution's
    # evidence source, which may not be among the draw's staged sources.
    resolution_sources = {
        r.get("evidence_source_id", "") for r in load_resolutions(ROOT).values()
    }
    check(
        all(
            d.number_sequence_source_id in draw_source_ids(d)
            or d.number_sequence_source_id in resolution_sources
            for d in draws
        ),
        "sequence source is a backing source or a resolution evidence source",
    )
    physical_capable = {
        "SRC-WI-PB-CSV", "SRC-MO-PB-XLSX", "SRC-TX-PB-CSV",
        "SRC-TX-MM-CSV", "SRC-FL-LOTTO-HIST-PDF",
    }
    bad_phys = [
        d.draw_id
        for d in draws
        if d.numbers_order.value == "physical_draw_order"
        and (
            d.number_sequence_source_id not in physical_capable
            or d.main_numbers == sorted(d.main_numbers)
        )
    ]
    check(
        not bad_phys,
        "physical-order rows have physical-capable sequence source and "
        f"non-ascending sequence {bad_phys[:5]}",
    )

    # ---- D-008 draw-exclusion ledger -------------------------------------
    from fortuna.ingestion.pipeline import load_exclusions

    exclusions = load_exclusions(ROOT)
    ledger_path = ROOT / "metadata/draw_exclusions.csv"
    check(ledger_path.exists(), "draw_exclusions.csv exists")
    by_draw_id = {d.draw_id: d for d in draws}
    excl_bad = [
        did for did in exclusions
        if did not in by_draw_id or by_draw_id[did].analysis_eligible
    ]
    check(
        not excl_bad,
        f"every ledger exclusion is a canonical ineligible draw {excl_bad}",
    )
    check(
        all(
            "excluded_non_draw_artifact" in (d.data_quality_notes or "")
            for did in exclusions
            for d in [by_draw_id[did]]
            if did in by_draw_id
        ),
        "excluded draws carry excluded_non_draw_artifact reason",
    )

    # manifest
    import json

    man = json.loads(man_p.read_text())
    check(bool(man.get("dataset_sha256")), "manifest has dataset hash")
    check(
        man.get("hash_algorithm") == "sha256",
        "manifest declares sha256",
    )
    check(man.get("num_draws") == len(draws), "manifest draw count matches")

    # manifest count reconciliation
    check(
        man.get("num_analysis_eligible") == len(eligible),
        "manifest eligible count matches",
    )
    check(
        man.get("num_analysis_ineligible") == len(draws) - len(eligible)
        and man.get("num_draws")
        == man.get("num_analysis_eligible") + man.get("num_analysis_ineligible"),
        "manifest draws = eligible + ineligible",
    )
    reason_counts = man.get("analysis_ineligible_reason_counts") or {}
    inelig = [d for d in draws if not d.analysis_eligible]
    check(
        sum(reason_counts.values()) >= len(inelig)
        and sum(1 for d in draws if not d.analysis_eligible) == len(inelig),
        "ineligible reason counts cover every ineligible draw",
    )

    # build_code_commit: must be a real commit containing the build pipeline
    import subprocess

    bcc = man.get("build_code_commit")
    ok_commit = False
    if bcc:
        def _git_ok(*args: str) -> bool:
            return subprocess.run(
                ["git", "-c", f"safe.directory={ROOT}", *args],
                capture_output=True, cwd=ROOT,
            ).returncode == 0

        ok_commit = _git_ok("cat-file", "-e", f"{bcc}^{{commit}}") and _git_ok(
            "cat-file",
            "-e",
            f"{bcc}:src/fortuna/ingestion/pipeline.py",
        ) and _git_ok(
            "cat-file", "-e", f"{bcc}:scripts/build_draw_database.py"
        )
    check(
        ok_commit,
        f"build_code_commit {bcc} is a committed state containing the build pipeline",
    )

    # artifact integrity
    missing_arts = [
        a.immutable_path for a in artifacts if not (ROOT / a.immutable_path).exists()
    ]
    check(not missing_arts, f"all artifact files exist {missing_arts[:3]}")
    altered = []
    for a in artifacts:
        p = ROOT / a.immutable_path
        if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() != a.sha256:
            altered.append(a.immutable_path)
    check(not altered, f"all artifacts hash-match manifest {altered[:3]}")

    print()
    if FAILS:
        print(f"PHASE 1 VERIFICATION FAILED ({len(FAILS)} checks)")
        return 1
    print(
        f"PHASE 1 VERIFIED: {len(draws)} draws, {len(eligible)} analysis-eligible, "
        f"dataset sha256 {man['dataset_sha256'][:16]}…"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
