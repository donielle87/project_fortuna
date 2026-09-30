"""Build the canonical Phase 1 draw database from preserved raw artifacts.

Modes:
  --offline   build strictly from data/raw artifacts (no network; default)
  --fetch     re-fetch live sources first (scripts/fetch_draw_sources.py),
              then build (retrieval events are appended to the artifact log)

Outputs:
  data/processed/draws.csv                 all normalized canonical records
  data/processed/draw_numbers.csv          normalized ball-level rows
  data/processed/dataset_manifest.json     provenance + dataset hash
  data/processed/data_quality_report.csv   per-game/per-status metrics
  metadata/missing_draws.csv               schedule-completeness ledger
  metadata/reconciliation_registry.csv     cross-source reconciliation
"""

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.ingestion import parsers
from fortuna.ingestion.pipeline import (
    apply_eligibility,
    build_canonical,
    dataset_hash,
    reconcile_groups,
    schedule_audit,
    structural_validate,
    write_manifest,
)
from fortuna.ingestion.staging import StagedDraw
from fortuna.schemas.artifacts import RawArtifact
from fortuna.schemas.csv_io import dump_csv, load_csv
from fortuna.schemas.regimes import GameRegime

ROOT = Path(__file__).resolve().parent.parent
LOTTO_SORTED_AFTER = date(2005, 2, 2)  # Phase 0 finding: FL archive reports
# physical draw order through 2005-01-29, ascending-sorted from 2005-02-02.


def parse_artifacts(artifacts: list[RawArtifact]) -> list[StagedDraw]:
    """Dispatch each artifact to its parser. Deterministic: artifacts sorted
    by immutable_path."""
    staged: list[StagedDraw] = []
    for art in sorted(artifacts, key=lambda a: a.immutable_path):
        path = ROOT / art.immutable_path
        if not path.exists():
            raise FileNotFoundError(
                f"required artifact missing: {art.immutable_path}"
            )
        content = path.read_bytes()
        import hashlib

        digest = hashlib.sha256(content).hexdigest()
        if digest != art.sha256:
            raise ValueError(
                f"artifact hash mismatch: {art.immutable_path} "
                f"(manifest {art.sha256[:12]} != file {digest[:12]})"
            )
        sid = art.source_id
        if sid == "SRC-NY-PB-DATA":
            staged += parsers.parse_ny_socrata_powerball(content, art)
        elif sid == "SRC-NY-MM-DATA":
            staged += parsers.parse_ny_socrata_megamillions(content, art)
        elif sid == "SRC-NY-PB-ARCHIVE":
            staged += parsers.parse_ny_archive_html(
                content, art, slug="powerball", game_id="powerball",
                special_cls="powerball",
            )
        elif sid == "SRC-NY-MM-ARCHIVE":
            staged += parsers.parse_ny_archive_html(
                content, art, slug="mega-millions", game_id="mega_millions",
                special_cls="mega-ball",
            )
        elif sid == "SRC-MO-PB-XLSX":
            staged += parsers.parse_mo_powerball_xlsx(content, art)
        elif sid == "SRC-TX-PB-CSV":
            staged += parsers.parse_tx_csv(content, art, game_id="powerball")
        elif sid == "SRC-TX-MM-CSV":
            staged += parsers.parse_tx_csv(content, art, game_id="mega_millions")
        elif sid == "SRC-FL-PB-HIST-PDF":
            staged += parsers.parse_fl_pdf(content, art, game_id="powerball")
        elif sid == "SRC-FL-MM-HIST-PDF":
            staged += parsers.parse_fl_pdf(content, art, game_id="mega_millions")
        elif sid == "SRC-FL-LOTTO-HIST-PDF":
            staged += parsers.parse_fl_pdf(
                content,
                art,
                game_id="florida_lotto",
                lotto_sorted_after=LOTTO_SORTED_AFTER,
            )
        # non-draw sources (rules PDFs etc.) contribute no staged records
    return staged


def _write_dict_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    import csv as csv_mod

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv_mod.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, cwd=ROOT,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def build(repo_root: Path = ROOT) -> dict:
    artifacts = load_csv(repo_root / "metadata/raw_artifacts.csv", RawArtifact)
    regimes = load_csv(repo_root / "metadata/game_regimes.csv", GameRegime)

    staged = parse_artifacts(artifacts)
    groups, recon_rows = reconcile_groups(staged)
    draws, errors, conflict_keys = build_canonical(groups, regimes)
    violations = structural_validate(draws, regimes)
    apply_eligibility(draws, conflict_keys, regimes)

    # schedule completeness over main-stream canonical draws
    observed: dict[str, set[date]] = {}
    for d in draws:
        if d.draw_stream.value == "main":
            observed.setdefault(d.game_id, set()).add(d.draw_date)
    asof = max(d.draw_date for d in draws)
    missing_rows = [
        r for r in schedule_audit(regimes, observed, asof)
        if r["missing_from_all_sources"] == "true"
    ]

    out_dir = repo_root / "data/processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    draws_path = out_dir / "draws.csv"
    nums_path = out_dir / "draw_numbers.csv"
    dump_csv(draws_path, draws)
    dump_csv(nums_path, [n for d in draws for n in d.to_draw_numbers()])

    recon_fields = [
        "game_id", "draw_date", "draw_stream", "field", "source_a", "value_a",
        "source_b", "value_b", "classification", "resolution",
        "resolution_evidence", "status", "notes",
    ]
    _write_dict_csv(
        repo_root / "metadata/reconciliation_registry.csv", recon_rows, recon_fields
    )
    miss_fields = [
        "game_id", "expected_draw_date", "regime_id", "statistical_regime_id",
        "missing_from_all_sources", "known_exception", "source_coverage",
        "resolution_status", "notes",
    ]
    _write_dict_csv(repo_root / "metadata/missing_draws.csv", missing_rows, miss_fields)

    # data-quality report: counts only (no pattern statistics)
    dq_rows: list[dict] = []
    for g in sorted({d.game_id for d in draws}):
        gd = [d for d in draws if d.game_id == g]
        dq_rows.append(
            {
                "game_id": g,
                "metric": "total_normalized_draws",
                "value": len(gd),
            }
        )
        for metric, pred in [
            ("analysis_eligible", lambda d: d.analysis_eligible),
            ("rejected", lambda d: d.validation_status.value == "rejected"),
            ("quarantined", lambda d: d.validation_status.value == "quarantined"),
            ("double_play_stream", lambda d: d.draw_stream.value == "double_play"),
            ("physical_order", lambda d: d.numbers_order.value == "physical_draw_order"),
            ("sorted_order", lambda d: d.numbers_order.value == "source_sorted_order"),
            ("with_machine_id", lambda d: d.machine_id is not None),
        ]:
            dq_rows.append(
                {"game_id": g, "metric": metric, "value": sum(1 for d in gd if pred(d))}
            )
    _write_dict_csv(
        out_dir / "data_quality_report.csv", dq_rows, ["game_id", "metric", "value"]
    )

    dsha = dataset_hash([draws_path, nums_path])
    artifact_shas = {
        sid: sorted({a.sha256 for a in artifacts if a.source_id == sid})
        for sid in sorted({a.source_id for a in artifacts})
    }
    write_manifest(
        out_dir / "dataset_manifest.json",
        draws=draws,
        artifact_shas=artifact_shas,
        dataset_sha=dsha,
        git_commit=_git_commit(),
    )
    return {
        "staged": len(staged),
        "draws": len(draws),
        "eligible": sum(1 for d in draws if d.analysis_eligible),
        "violations": len(violations),
        "conflicts": len(conflict_keys),
        "missing": len(missing_rows),
        "recon_rows": len(recon_rows),
        "errors": errors,
        "dataset_sha256": dsha,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--offline", action="store_true",
        help="build from preserved artifacts only (default)",
    )
    ap.add_argument(
        "--fetch", action="store_true", help="re-fetch live sources first"
    )
    args = ap.parse_args()
    if args.fetch:
        print("fetching live sources...")
        rc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/fetch_draw_sources.py")],
            cwd=ROOT,
        ).returncode
        if rc != 0:
            print("fetch failures — see output above")
            return rc
    res = build()
    print(
        f"staged={res['staged']} draws={res['draws']} eligible={res['eligible']} "
        f"violations={res['violations']} conflicts={res['conflicts']} "
        f"missing={res['missing']} recon={res['recon_rows']}"
    )
    for e in res["errors"]:
        print("ERROR:", e)
    print("dataset sha256:", res["dataset_sha256"])
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
