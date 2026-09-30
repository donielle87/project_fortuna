"""Phase 1 draw-database pipeline.

Staged records (per-source parse results) -> reconciled canonical Draws ->
structural validation -> eligibility -> canonical outputs + audit ledgers.

Canonical key: (game_id, draw_date, draw_stream). The primary record for each
key comes from the highest-precedence authoritative source; other sources are
recorded as corroborating and reconciled field-by-field.

Precedence (authoritative-first):
  powerball:      NY archive (official operator archive, full history) >
                  NY Socrata open-data > MO xlsx > TX csv > FL PDF
  mega_millions:  NY archive > NY Socrata > TX csv > FL PDF
  florida_lotto:  FL official history PDF (sole authoritative archive)

Double Play rows are a separate stream (draw_stream=double_play) and are
never merged into the main series.
"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from fortuna.ingestion.staging import StagedDraw
from fortuna.rules.assign import (
    AmbiguousRegimeError,
    NoRegimeError,
    UnverifiedBoundaryError,
    assign_regime,
)
from fortuna.schemas.draws import (
    Draw,
    DrawStream,
    DrawValidationStatus,
    OrderSemantics,
)
from fortuna.schemas.regimes import GameRegime
from fortuna.validation.draw_validator import validate_draw

INGESTION_VERSION = "1.0.0"

GAME_PREFIX = {"powerball": "PB", "mega_millions": "MM", "florida_lotto": "FL"}

SOURCE_PRECEDENCE: dict[str, list[str]] = {
    "powerball": [
        "SRC-NY-PB-ARCHIVE",
        "SRC-NY-PB-DATA",
        "SRC-MO-PB-XLSX",
        "SRC-TX-PB-CSV",
        "SRC-FL-PB-HIST-PDF",
    ],
    "mega_millions": [
        "SRC-NY-MM-ARCHIVE",
        "SRC-NY-MM-DATA",
        "SRC-TX-MM-CSV",
        "SRC-FL-MM-HIST-PDF",
    ],
    "florida_lotto": ["SRC-FL-LOTTO-HIST-PDF"],
}

# Fields compared during cross-source reconciliation.
_COMPARE_FIELDS = ("main_numbers_sorted", "special_ball", "multiplier")


def canonical_draw_id(game_id: str, draw_date: date, stream: DrawStream) -> str:
    fallback = "".join(c for c in game_id.upper() if c.isalpha())[:4] or "XX"
    prefix = GAME_PREFIX.get(game_id, fallback)
    base = f"{prefix}-D-{draw_date.isoformat()}"
    return f"{base}-DP" if stream is DrawStream.DOUBLE_PLAY else base

def _precedence(order: list[str], source_id: str) -> int:
    """Sources not in the precedence list sort last (provisional/future)."""
    return order.index(source_id) if source_id in order else len(order)


def _fmt_val(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ";".join(map(str, v))
    return str(v)


def reconcile_groups(
    staged: list[StagedDraw],
) -> tuple[
    dict[tuple[str, date, DrawStream], list[StagedDraw]],
    list[dict],
]:
    """Group staged records by canonical key and reconcile across sources.

    Returns (groups, reconciliation_rows). A reconciliation row is produced
    per (key, source-pair-field-difference) and per missing-source overlap.
    """
    groups: dict[tuple[str, date, DrawStream], list[StagedDraw]] = defaultdict(list)
    for s in staged:
        groups[(s.game_id, s.draw_date, s.draw_stream)].append(s)

    rows: list[dict] = []
    for (game_id, d, stream), recs in sorted(groups.items()):
        order = SOURCE_PRECEDENCE.get(game_id, [])
        recs.sort(key=lambda r: _precedence(order, r.source_id))
        primary = recs[0]
        for other in recs[1:]:
            for fld in _COMPARE_FIELDS:
                if fld == "main_numbers_sorted":
                    va = sorted(primary.main_numbers)
                    vb = sorted(other.main_numbers)
                else:
                    va = getattr(primary, fld)
                    vb = getattr(other, fld)
                if va is None and vb is None:
                    cls = "MATCH"
                elif va is None or vb is None:
                    cls = "FIELD_COMPLEMENT"
                elif va == vb:
                    cls = "MATCH"
                else:
                    cls = "CONFLICT"
                if cls != "MATCH" or fld == "main_numbers_sorted":
                    rows.append(
                        {
                            "game_id": game_id,
                            "draw_date": d.isoformat(),
                            "draw_stream": stream.value,
                            "field": fld,
                            "source_a": primary.source_id,
                            "value_a": _fmt_val(va),
                            "source_b": other.source_id,
                            "value_b": _fmt_val(vb),
                            "classification": cls,
                            "resolution": "" if cls == "CONFLICT" else "n/a",
                            "resolution_evidence": "",
                            "status": "unresolved" if cls == "CONFLICT" else "resolved",
                            "notes": "",
                        }
                    )
    return groups, rows


def _merge(primary: StagedDraw, others: list[StagedDraw]) -> dict:
    """Merge corroborating fields into the primary (documented precedence).

    Field-level precedence: a field missing from the primary is filled from
    the highest-precedence corroborating source that supplies it
    (FIELD_COMPLEMENT is reconciliation, not conflict).
    """
    merged = {
        "special_ball": primary.special_ball,
        "multiplier": primary.multiplier,
        "jackpot": primary.jackpot,
        "jackpot_winners": primary.jackpot_winners,
        "machine_id": primary.machine_id,
        "ball_set_id": primary.ball_set_id,
        "drawing_identifier": primary.drawing_identifier,
        "numbers_order": primary.numbers_order,
    }
    order_pref = {
        OrderSemantics.PHYSICAL_DRAW_ORDER: 0,
        OrderSemantics.SOURCE_SORTED_ORDER: 1,
        OrderSemantics.UNKNOWN_ORDER: 2,
    }
    for o in others:
        for k in merged:
            if k == "numbers_order":
                if order_pref[o.numbers_order] < order_pref[merged[k]]:
                    merged[k] = o.numbers_order
            elif merged[k] is None:
                v = getattr(o, k)
                if v is not None:
                    merged[k] = v
    return merged


def build_canonical(
    groups: dict[tuple[str, date, DrawStream], list[StagedDraw]],
    regimes: list[GameRegime],
) -> tuple[list[Draw], list[str], set[tuple[str, date, str]]]:
    """Produce canonical Draws + conflict keys.

    Returns (draws, fatal_errors, conflict_keys). Conflict keys are
    (game_id, draw_date, field) tuples with an unresolved winning-number or
    special-ball conflict — those draws can never be analysis-eligible.
    """
    draws: list[Draw] = []
    errors: list[str] = []
    conflict_keys: set[tuple[str, date, str]] = set()

    for (game_id, d, stream), recs in sorted(groups.items()):
        order = SOURCE_PRECEDENCE.get(game_id, [])
        recs.sort(key=lambda r: _precedence(order, r.source_id))
        primary = recs[0]
        merged = _merge(primary, recs[1:])

        for other in recs[1:]:
            if sorted(other.main_numbers) != sorted(primary.main_numbers):
                conflict_keys.add((game_id, d, "main_numbers"))
            if other.special_ball != primary.special_ball:
                conflict_keys.add((game_id, d, "special_ball"))

        try:
            regime = assign_regime(game_id, d, regimes)
            regime_id = regime.regime_id
            quarantined = False
        except UnverifiedBoundaryError:
            # Assign the containing regime record for bookkeeping but flag.
            candidates = [
                r
                for r in regimes
                if r.game_id == game_id
                and r.span_start is not None
                and r.span_start <= d
                and (r.span_end is None or d <= r.span_end)
            ]
            regime_id = candidates[0].regime_id if candidates else "UNASSIGNED"
            quarantined = True
        except (NoRegimeError, AmbiguousRegimeError) as exc:
            errors.append(f"{game_id} {d} {stream.value}: {exc}")
            continue

        draw = Draw(
            draw_id=canonical_draw_id(game_id, d, stream),
            game_id=game_id,
            regime_id=regime_id,
            draw_date=d,
            draw_stream=stream,
            main_numbers=primary.main_numbers,
            numbers_order=merged["numbers_order"],
            special_ball=merged["special_ball"],
            multiplier=merged["multiplier"],
            jackpot=merged["jackpot"],
            jackpot_winners=merged["jackpot_winners"],
            drawing_identifier=merged["drawing_identifier"],
            machine_id=merged["machine_id"],
            ball_set_id=merged["ball_set_id"],
            source_id=primary.source_id,
            retrieved_at=primary.retrieved_at,
            raw_artifact_sha256=primary.artifact_sha256,
            parser_version=primary.parser_version,
            ingestion_version=INGESTION_VERSION,
            corroborating_source_ids=[r.source_id for r in recs[1:]],
            data_quality_notes=primary.notes,
        )
        if quarantined:
            draw.validation_status = DrawValidationStatus.QUARANTINED
        draws.append(draw)
    return draws, errors, conflict_keys


def structural_validate(
    draws: list[Draw], regimes: list[GameRegime]
) -> dict[str, list[str]]:
    """Run structural validation; return draw_id -> violation reasons."""
    by_id = {r.regime_id: r for r in regimes}
    out: dict[str, list[str]] = {}
    for d in draws:
        reasons = validate_draw(d, by_id.get(d.regime_id), set(by_id))
        # Non-main streams must still satisfy the game's matrix; Double Play
        # uses the same ball pools as the main game, so regime bounds hold.
        if reasons:
            out[d.draw_id] = reasons
            d.validation_status = DrawValidationStatus.REJECTED
        elif d.validation_status != DrawValidationStatus.QUARANTINED:
            d.validation_status = DrawValidationStatus.VALID
    return out


def apply_eligibility(
    draws: list[Draw],
    conflict_keys: set[tuple[str, date, str]],
    regimes: list[GameRegime],
) -> None:
    """Final eligibility gate; mutates analysis_eligible in place."""
    regime_by_id = {r.regime_id: r for r in regimes}
    for d in draws:
        notes: list[str] = list(
            filter(None, [d.data_quality_notes])
        )
        eligible = True
        if not (d.source_id and d.raw_artifact_sha256):
            eligible = False
            notes.append("missing provenance")
        if d.validation_status != DrawValidationStatus.VALID:
            eligible = False
            notes.append(f"validation_status={d.validation_status.value}")
        if d.provisional:
            eligible = False
            notes.append("provisional source")
        regime = regime_by_id.get(d.regime_id)
        if regime is None:
            eligible = False
            notes.append("no regime")
        elif (
            regime.first_unambiguous_draw is not None
            and d.draw_date < regime.first_unambiguous_draw
        ):
            eligible = False
            notes.append("quarantine window")
        if any(
            (d.game_id, d.draw_date, fld) in conflict_keys
            for fld in ("main_numbers", "special_ball")
        ):
            eligible = False
            notes.append("unresolved winning-number conflict")
        d.analysis_eligible = eligible
        if notes:
            d.data_quality_notes = "; ".join(notes)


_WD = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def schedule_audit(
    regimes: list[GameRegime],
    observed: dict[str, set[date]],
    asof: date,
) -> list[dict]:
    """Expected scheduled draw dates (main stream) vs observed.

    Only regime periods with known drawing days are audited. The effective
    horizon is min(last_affected_draw, asof); ongoing regimes use asof.
    """
    rows: list[dict] = []
    for r in regimes:
        if not r.drawing_days or r.first_affected_draw is None:
            continue
        start = r.first_affected_draw
        end = r.last_affected_draw or asof
        end = min(end, asof)
        days = {_WD[x] for x in r.drawing_days}
        cur = start
        while cur <= end:
            if cur.weekday() in days:
                present = cur in observed.get(r.game_id, set())
                rows.append(
                    {
                        "game_id": r.game_id,
                        "expected_draw_date": cur.isoformat(),
                        "regime_id": r.regime_id,
                        "statistical_regime_id": r.statistical_regime_id,
                        "missing_from_all_sources": "false" if present else "true",
                        "known_exception": "false",
                        "source_coverage": "",
                        "resolution_status": "observed" if present else "unresolved",
                        "notes": "",
                    }
                )
            cur = date.fromordinal(cur.toordinal() + 1)
    return rows


def dataset_hash(paths: list[Path]) -> str:
    """Deterministic SHA-256 over sorted canonical outputs."""
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: x.name):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def write_manifest(
    path: Path,
    *,
    draws: list[Draw],
    artifact_shas: dict[str, list[str]],
    dataset_sha: str,
    git_commit: str | None,
) -> None:
    by_game: dict[str, dict] = {}
    for d in draws:
        g = by_game.setdefault(
            d.game_id, {"total": 0, "eligible": 0, "earliest": None, "latest": None}
        )
        g["total"] += 1
        g["eligible"] += int(d.analysis_eligible)
        s = d.draw_date.isoformat()
        g["earliest"] = s if g["earliest"] is None else min(g["earliest"], s)
        g["latest"] = s if g["latest"] is None else max(g["latest"], s)
    manifest = {
        "dataset_version": INGESTION_VERSION,
        "build_timestamp": datetime.now(UTC).isoformat(),
        "code_commit": git_commit,
        "hash_algorithm": "sha256",
        "dataset_sha256": dataset_sha,
        "source_artifact_sha256": artifact_shas,
        "num_draws": len(draws),
        "num_analysis_eligible": sum(1 for d in draws if d.analysis_eligible),
        "num_quarantined_or_rejected": sum(
            1
            for d in draws
            if d.validation_status
            in (DrawValidationStatus.QUARANTINED, DrawValidationStatus.REJECTED)
        ),
        "coverage_by_game": by_game,
        "parser_version": "1.0.0",
        "ingestion_version": INGESTION_VERSION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
