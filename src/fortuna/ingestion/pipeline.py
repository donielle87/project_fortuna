"""Phase 1 draw-database pipeline.

Staged records (per-source parse results) -> reconciled canonical Draws ->
structural validation -> eligibility -> canonical outputs + audit ledgers.

Canonical key: (game_id, draw_date, draw_stream). The primary record for each
key comes from the highest-precedence authoritative source; other sources are
recorded as corroborating and reconciled field-by-field.

Precedence (authority-first, then coverage):
  Within each authority tier, the order below applies. An unofficial
  (Tier-3) source can never outrank an official (Tier 1/2) source — the
  effective sort key is (authority_tier, position in this list).

  powerball:      WI csv (Tier-1, full history, physical draw order)
                  > MO xlsx > TX csv > FL PDF > MD archive (Tier-1s)
                  > NY Socrata open-data (Tier-2)
                  > nylottery.org archive (Tier-3, reconciliation only)
  mega_millions:  megamillions.com operator API (Tier-1)
                  > MD archive (Tier-1, full history incl. Big Game)
                  > TX csv > FL PDF (Tier-1s)
                  > NY Socrata open-data (Tier-2)
                  > nylottery.org archive (Tier-3, reconciliation only)
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

# Within-tier ordering only. The effective precedence key is
# (authority_tier, index in this list); Tier-3 sources therefore can never
# outrank an authoritative source regardless of list position.
SOURCE_PRECEDENCE: dict[str, list[str]] = {
    "powerball": [
        "SRC-WI-PB-CSV",
        "SRC-MO-PB-XLSX",
        "SRC-TX-PB-CSV",
        "SRC-FL-PB-HIST-PDF",
        "SRC-MD-PB-ARCHIVE",
        "SRC-NY-PB-DATA",
        "SRC-NY-PB-ARCHIVE",
    ],
    "mega_millions": [
        "SRC-MM-COM-API",
        "SRC-MD-MM-ARCHIVE",
        "SRC-TX-MM-CSV",
        "SRC-FL-MM-HIST-PDF",
        "SRC-NY-MM-DATA",
        "SRC-NY-MM-ARCHIVE",
    ],
    "florida_lotto": ["SRC-FL-LOTTO-HIST-PDF"],
}

# Authority tier for sources absent from the registry (defensive: unknown
# sources are treated as unofficial).
_UNKNOWN_SOURCE_TIER = 3


def load_source_tiers(repo_root: Path) -> dict[str, int]:
    """source_id -> authority_tier from metadata/source_registry.csv."""
    import csv as _csv

    tiers: dict[str, int] = {}
    reg = repo_root / "metadata/source_registry.csv"
    if reg.exists():
        for row in _csv.DictReader(reg.open()):
            try:
                tiers[row["source_id"]] = int(row["authority_tier"])
            except (KeyError, ValueError):
                continue
    return tiers


def load_resolutions(repo_root: Path) -> dict[tuple[str, date, str], dict]:
    """Authoritative conflict resolutions from metadata/draw_resolutions.csv.

    Key: (game_id, draw_date, field) where field is the canonical name
    ('main_numbers' | 'special_ball' | 'multiplier'). A resolution exists
    only when an official source has definitively settled the value.
    """
    import csv as _csv

    path = repo_root / "metadata/draw_resolutions.csv"
    out: dict[tuple[str, date, str], dict] = {}
    if not path.exists():
        return out
    for row in _csv.DictReader(path.open()):
        if row.get("status", "").strip() != "resolved":
            continue
        key = (row["game_id"], date.fromisoformat(row["draw_date"]), row["field"])
        out[key] = row
    return out


def draw_source_ids(draw: "Draw") -> list[str]:
    """All sources backing a canonical draw (primary + corroborating)."""
    return [draw.source_id, *draw.corroborating_source_ids]

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


def _tier_key(
    tiers: dict[str, int], order: list[str], source_id: str
) -> tuple[int, int]:
    """(authority_tier, within-tier precedence). An unofficial source can
    never sort ahead of an authoritative one, regardless of list order."""
    return (tiers.get(source_id, _UNKNOWN_SOURCE_TIER), _precedence(order, source_id))


def _fmt_val(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ";".join(map(str, v))
    return str(v)


def reconcile_groups(
    staged: list[StagedDraw],
    tiers: dict[str, int] | None = None,
) -> tuple[
    dict[tuple[str, date, DrawStream], list[StagedDraw]],
    list[dict],
]:
    """Group staged records by canonical key and reconcile across sources.

    Returns (groups, reconciliation_rows). A reconciliation row is produced
    per (key, source-pair-field-difference) and per missing-source overlap.
    """
    tiers = tiers or {}
    groups: dict[tuple[str, date, DrawStream], list[StagedDraw]] = defaultdict(list)
    seen_sig: dict[tuple[str, date, DrawStream], set[tuple]] = defaultdict(set)
    for s in staged:
        key = (s.game_id, s.draw_date, s.draw_stream)
        # Identical re-retrievals of the same source (e.g. a second fetch
        # produced a byte-different artifact with identical parsed content)
        # carry no information — dedupe on the parsed signature. Records
        # from the same source that differ in content are kept so the
        # divergence is surfaced in reconciliation.
        sig = (
            s.source_id,
            tuple(sorted(s.main_numbers)),
            s.special_ball,
            s.multiplier,
            s.jackpot,
            s.jackpot_winners,
            s.machine_id,
            s.ball_set_id,
            s.drawing_identifier,
            s.numbers_order,
        )
        if sig in seen_sig[key]:
            continue
        seen_sig[key].add(sig)
        groups[key].append(s)

    rows: list[dict] = []
    for (game_id, d, stream), recs in sorted(groups.items()):
        order = SOURCE_PRECEDENCE.get(game_id, [])
        recs.sort(key=lambda r: _tier_key(tiers, order, r.source_id))
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
                # A divergence between an authoritative primary and a Tier-3
                # (unofficial) source is a secondary-source error, not an
                # unresolved conflict: the authoritative value controls by
                # documented precedence. Authoritative-vs-authoritative
                # divergences stay unresolved.
                secondary_divergence = (
                    cls == "CONFLICT"
                    and tiers.get(primary.source_id, _UNKNOWN_SOURCE_TIER) <= 2
                    and tiers.get(other.source_id, _UNKNOWN_SOURCE_TIER) >= 3
                )
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
                            "resolution": (
                                "authoritative precedence"
                                if secondary_divergence
                                else ("" if cls == "CONFLICT" else "n/a")
                            ),
                            "resolution_evidence": "",
                            "status": (
                                "resolved"
                                if cls != "CONFLICT" or secondary_divergence
                                else "unresolved"
                            ),
                            "notes": (
                                "unofficial source diverges from authoritative "
                                "primary; recorded for audit, does not affect "
                                "canonical value"
                                if secondary_divergence
                                else ""
                            ),
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
    tiers: dict[str, int] | None = None,
    resolutions: dict[tuple[str, date, str], dict] | None = None,
) -> tuple[list[Draw], list[str], set[tuple[str, date, str]]]:
    """Produce canonical Draws + conflict keys.

    Returns (draws, fatal_errors, conflict_keys). Conflict keys are
    (game_id, draw_date, field) tuples with an unresolved winning-number or
    special-ball conflict — those draws can never be analysis-eligible.
    Conflicts with an authoritative resolution in draw_resolutions.csv are
    applied (canonical value set to the resolved value) and not flagged.
    """
    tiers = tiers or {}
    resolutions = resolutions or {}
    draws: list[Draw] = []
    errors: list[str] = []
    conflict_keys: set[tuple[str, date, str]] = set()

    for (game_id, d, stream), recs in sorted(groups.items()):
        order = SOURCE_PRECEDENCE.get(game_id, [])
        recs.sort(key=lambda r: _tier_key(tiers, order, r.source_id))
        primary = recs[0]
        merged = _merge(primary, recs[1:])
        main_numbers = primary.main_numbers
        special_ball = merged["special_ball"]

        primary_tier = tiers.get(primary.source_id, _UNKNOWN_SOURCE_TIER)
        for other in recs[1:]:
            # A Tier-3 (unofficial) divergence from an authoritative primary
            # is a secondary-source error: it is logged in the reconciliation
            # registry but does not create an unresolved conflict.
            authoritative_dispute = (
                primary_tier > 2
                or tiers.get(other.source_id, _UNKNOWN_SOURCE_TIER) <= 2
            )
            if sorted(other.main_numbers) != sorted(primary.main_numbers):
                key = (game_id, d, "main_numbers")
                if key in resolutions:
                    main_numbers = [
                        int(x) for x in resolutions[key]["resolved_value"].split(";")
                    ]
                    merged["numbers_order"] = OrderSemantics.SOURCE_SORTED_ORDER
                elif authoritative_dispute:
                    conflict_keys.add(key)
            if other.special_ball != primary.special_ball:
                key = (game_id, d, "special_ball")
                if key in resolutions:
                    special_ball = int(resolutions[key]["resolved_value"])
                elif authoritative_dispute:
                    conflict_keys.add(key)

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
            main_numbers=main_numbers,
            numbers_order=merged["numbers_order"],
            special_ball=special_ball,
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
    tiers: dict[str, int] | None = None,
) -> dict[str, list[str]]:
    """Final eligibility gate; mutates analysis_eligible in place.

    Returns draw_id -> list of ineligibility reason codes (empty for
    eligible draws). A draw is eligible only if at least one Tier-1/Tier-2
    (official) source backs it; a draw whose only sources are Tier-3
    unofficial can never be analysis-eligible.
    """
    tiers = tiers or {}
    regime_by_id = {r.regime_id: r for r in regimes}
    reasons: dict[str, list[str]] = {}
    for d in draws:
        codes: list[str] = []
        notes: list[str] = list(
            filter(None, [d.data_quality_notes])
        )
        if not (d.source_id and d.raw_artifact_sha256):
            codes.append("missing_provenance")
            notes.append("missing provenance")
        if d.validation_status == DrawValidationStatus.REJECTED:
            codes.append("structural_rejection")
            notes.append(f"validation_status={d.validation_status.value}")
        elif d.validation_status == DrawValidationStatus.QUARANTINED:
            codes.append("boundary_quarantine")
            notes.append(f"validation_status={d.validation_status.value}")
        elif d.validation_status != DrawValidationStatus.VALID:
            codes.append("invalid_status")
            notes.append(f"validation_status={d.validation_status.value}")
        if d.provisional:
            codes.append("provisional_source")
            notes.append("provisional source")
        source_tiers = [
            tiers.get(sid, _UNKNOWN_SOURCE_TIER) for sid in draw_source_ids(d)
        ]
        if not any(t <= 2 for t in source_tiers):
            codes.append("unofficial_source_only")
            notes.append("no authoritative (tier<=2) source")
        regime = regime_by_id.get(d.regime_id)
        if regime is None:
            codes.append("no_regime")
            notes.append("no regime")
        elif (
            regime.first_unambiguous_draw is not None
            and d.draw_date < regime.first_unambiguous_draw
        ):
            codes.append("boundary_quarantine")
            notes.append("quarantine window")
        if any(
            (d.game_id, d.draw_date, fld) in conflict_keys
            for fld in ("main_numbers", "special_ball")
        ):
            codes.append("unresolved_conflict")
            notes.append("unresolved winning-number conflict")
        d.analysis_eligible = not codes
        if codes:
            reasons[d.draw_id] = codes
        if notes:
            d.data_quality_notes = "; ".join(notes)
    return reasons


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
    build_code_commit: str | None,
    ineligible_reasons: dict[str, list[str]] | None = None,
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

    num_eligible = sum(1 for d in draws if d.analysis_eligible)
    reason_counts: dict[str, int] = {}
    for codes in (ineligible_reasons or {}).values():
        for c in codes:
            reason_counts[c] = reason_counts.get(c, 0) + 1

    manifest = {
        "dataset_version": INGESTION_VERSION,
        "build_timestamp": datetime.now(UTC).isoformat(),
        # The committed code state that produced this dataset. Must name a
        # commit that actually contains the build pipeline (verified by
        # scripts/verify_phase1.py against the git object store).
        "build_code_commit": build_code_commit,
        "hash_algorithm": "sha256",
        "dataset_sha256": dataset_sha,
        "source_artifact_sha256": artifact_shas,
        "num_draws": len(draws),
        "num_analysis_eligible": num_eligible,
        "num_analysis_ineligible": len(draws) - num_eligible,
        "num_quarantined_or_rejected": sum(
            1
            for d in draws
            if d.validation_status
            in (DrawValidationStatus.QUARANTINED, DrawValidationStatus.REJECTED)
        ),
        "analysis_ineligible_reason_counts": reason_counts,
        "coverage_by_game": by_game,
        "parser_version": "1.0.0",
        "ingestion_version": INGESTION_VERSION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
