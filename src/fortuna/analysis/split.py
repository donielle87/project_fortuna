"""Phase 3 exploration/holdout split — METADATA ONLY.

The split is chronological and deterministic: within each statistical
regime, the LAST ceil(0.20 * n) eligible main draws form the Phase 4
holdout; the earlier 80% form the Phase 3 exploration set. The split is
built exclusively from whitelisted metadata columns (draw_id, game_id,
regime_id, draw_date, draw_stream, analysis_eligible, numbers_order) —
winning-number fields are never read here.

The holdout seal hashes the raw CSV bytes of the canonical holdout rows
in file order so later phases can prove the holdout population was not
altered. Row bytes are hashed verbatim; outcome fields are never parsed.
"""

import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path

from fortuna.simulation.observation import (
    _expected_dates,
    contiguous_segments,
    load_draw_metadata,
)

# Columns exposed in the split manifests — metadata only, by construction.
SPLIT_MANIFEST_FIELDS = (
    "draw_id", "game_id", "statistical_regime_id", "draw_date",
    "draw_stream", "split",
)


def split_policy_sha256(split_cfg: dict) -> str:
    """Deterministic hash of the frozen split-policy block."""
    payload = json.dumps(split_cfg, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def assign_splits(
    meta: list[dict], stat_of: dict[str, str], holdout_fraction: float = 0.20
) -> list[dict]:
    """One split row per eligible main draw, sorted by regime then date.

    ``meta`` rows must carry only the whitelisted metadata fields.
    Returns rows with SPLIT_MANIFEST_FIELDS keys.
    """
    by_stat: dict[str, list[dict]] = {}
    for r in meta:
        if r["draw_stream"] != "main" or r["analysis_eligible"] != "true":
            continue
        stat_id = stat_of.get(r["regime_id"])
        if stat_id is None:
            continue
        by_stat.setdefault(stat_id, []).append(r)

    rows: list[dict] = []
    for stat_id in sorted(by_stat):
        draws = sorted(
            by_stat[stat_id], key=lambda r: (r["draw_date"], r["draw_id"])
        )
        n = len(draws)
        n_hold = math.ceil(holdout_fraction * n)
        for i, r in enumerate(draws):
            rows.append(
                {
                    "draw_id": r["draw_id"],
                    "game_id": r["game_id"],
                    "statistical_regime_id": stat_id,
                    "draw_date": r["draw_date"],
                    "draw_stream": r["draw_stream"],
                    "split": "holdout" if i >= n - n_hold else "exploration",
                }
            )
    return rows


def holdout_seal_sha256(draws_csv: Path, holdout_ids: set[str]) -> str:
    """SHA-256 over the raw bytes of canonical holdout rows, file order.

    Only the first CSV field (draw_id, unquoted by construction) is read
    to decide membership; the remainder of each selected line is hashed
    verbatim without interpretation.
    """
    h = hashlib.sha256()
    with draws_csv.open("rb") as f:
        header = f.readline()  # skipped: column names, not draw records
        assert header.startswith(b"draw_id,"), "unexpected draws.csv schema"
        for line in f:
            did = line.split(b",", 1)[0].decode()
            if did in holdout_ids:
                h.update(line)
    return h.hexdigest()


def exploration_segments(
    meta: list[dict],
    regimes: list,
    stat_of: dict[str, str],
    exploration_ids: set[str],
    order_only: bool = False,
) -> dict[str, list[list[date]]]:
    """Contiguous exploration segments per statistical regime.

    Same scientific rule as Phase 2: the timeline is every scheduled
    position plus every actual draw position (eligible or not) within the
    exploration window; any position that is not an exploration-eligible
    draw breaks a segment — including missing scheduled draws, ineligible
    draws, unresolved-conflict draws, Tier-3-only draws, and the
    exploration/holdout boundary itself (no position past the last
    exploration draw can extend a segment). With ``order_only`` only
    physical-draw-order exploration positions count as eligible.
    """
    id_set = exploration_ids
    expl_dates: dict[str, set[date]] = {}
    all_dates: dict[str, set[date]] = {}
    for r in meta:
        if r["draw_stream"] != "main":
            continue
        stat_id = stat_of.get(r["regime_id"])
        if stat_id is None:
            continue
        d = date.fromisoformat(r["draw_date"])
        all_dates.setdefault(stat_id, set()).add(d)
        if r["draw_id"] in id_set:
            if order_only and r.get("numbers_order") != "physical_draw_order":
                continue
            expl_dates.setdefault(stat_id, set()).add(d)

    asof = max(d for ds in all_dates.values() for d in ds)
    stat_regs: dict[str, list] = {}
    for reg in regimes:
        stat_regs.setdefault(reg.statistical_regime_id, []).append(reg)

    out: dict[str, list[list[date]]] = {}
    for stat_id in sorted(stat_regs):
        regs = sorted(stat_regs[stat_id], key=lambda r: r.first_affected_draw)
        last_expl = max(expl_dates.get(stat_id, set()), default=None)
        if last_expl is None:
            out[stat_id] = []
            continue
        expected = {
            d
            for reg in regs
            for d in _expected_dates(reg, asof)
            if d <= last_expl
        }
        timeline = sorted(
            expected | {d for d in all_dates.get(stat_id, set())
                        if d <= last_expl}
        )
        out[stat_id] = contiguous_segments(
            timeline, expl_dates.get(stat_id, set())
        )
    return out


def write_split_manifest(path: Path, rows: list[dict], split: str) -> str:
    """Write one split's manifest; returns its sha256."""
    sel = [r for r in rows if r["split"] == split]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(SPLIT_MANIFEST_FIELDS))
        w.writeheader()
        w.writerows(sel)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_summary_rows(
    split_rows: list[dict],
    segments: dict[str, list[list[date]]],
    order_segments: dict[str, list[list[date]]],
) -> list[dict]:
    """Per-regime split summary — metadata only."""
    by_stat: dict[str, list[dict]] = {}
    for r in split_rows:
        by_stat.setdefault(r["statistical_regime_id"], []).append(r)
    out = []
    for stat_id in sorted(by_stat):
        rs = by_stat[stat_id]
        expl = [r for r in rs if r["split"] == "exploration"]
        hold = [r for r in rs if r["split"] == "holdout"]
        segs = segments.get(stat_id, [])
        osegs = order_segments.get(stat_id, [])
        out.append(
            {
                "statistical_regime_id": stat_id,
                "game_id": rs[0]["game_id"],
                "eligible_main_draw_count": len(rs),
                "exploration_count": len(expl),
                "holdout_count": len(hold),
                "exploration_end_date": expl[-1]["draw_date"] if expl else "",
                "holdout_start_date": hold[0]["draw_date"] if hold else "",
                "exploration_segments": len(segs),
                "exploration_segment_lengths": ";".join(
                    str(len(s)) for s in segs
                ),
                "order_eligible_exploration_count": sum(
                    len(s) for s in osegs
                ),
                "order_eligible_segment_lengths": ";".join(
                    str(len(s)) for s in osegs
                ),
            }
        )
    return out


def build_phase3_split(
    draws_csv: Path,
    regimes: list,
    split_cfg: dict,
    out_dir: Path,
) -> dict:
    """Generate all split artifacts; returns seal + hashes provenance."""
    meta = load_draw_metadata(draws_csv)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    rows = assign_splits(meta, stat_of, split_cfg["holdout_fraction"])

    exploration_ids = {r["draw_id"] for r in rows if r["split"] == "exploration"}
    holdout_ids = {r["draw_id"] for r in rows if r["split"] == "holdout"}
    assert not (exploration_ids & holdout_ids)

    expl_hash = write_split_manifest(
        out_dir / "phase3_exploration_ids.csv", rows, "exploration"
    )
    hold_hash = write_split_manifest(
        out_dir / "phase3_holdout_ids.csv", rows, "holdout"
    )
    seal = holdout_seal_sha256(draws_csv, holdout_ids)

    segments = exploration_segments(meta, regimes, stat_of, exploration_ids)
    order_segments = exploration_segments(
        meta, regimes, stat_of, exploration_ids, order_only=True
    )
    summary = split_summary_rows(rows, segments, order_segments)
    with (out_dir / "phase3_split_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    seal_doc = {
        "phase": 3,
        "experiment_id": "F-E002",
        "dataset_sha256": None,  # filled by caller
        "split_policy_sha256": split_policy_sha256(split_cfg),
        "exploration_manifest_sha256": expl_hash,
        "holdout_manifest_sha256": hold_hash,
        "holdout_seal_sha256": seal,
        "holdout_counts": {
            s["statistical_regime_id"]: s["holdout_count"] for s in summary
        },
        "exploration_counts": {
            s["statistical_regime_id"]: s["exploration_count"]
            for s in summary
        },
        "note": (
            "Seal covers raw bytes of canonical holdout rows; Phase 3 "
            "code never parses holdout outcome fields."
        ),
    }
    return {
        "seal_doc": seal_doc,
        "summary": summary,
        "segments": segments,
        "order_segments": order_segments,
        "exploration_ids": exploration_ids,
        "holdout_ids": holdout_ids,
    }
