# Data Dictionary

## metadata/games.csv — `Game`

| field | type | meaning |
|---|---|---|
| game_id | str | stable snake_case key (`powerball`, `mega_millions`, `florida_lotto`) |
| name | str | display name |
| operator | str | governing body |
| jurisdiction | str | where sold |
| launch_date | date | first drawing |
| active | bool | currently offered |
| notes | str | free text |

## metadata/game_regimes.csv — `GameRegime`

The core table: one row per legal rule era. `matrix_key()` = the seven
sampling fields below; identical keys = same statistical pool group.

| field | type | meaning |
|---|---|---|
| regime_id | str | `XX-Rnnn`; unique legal era |
| game_id | str | owning game |
| statistical_regime_id | str | `XX-Snn`; pool group — pooling is legal only within one group |
| change_classification | enum | baseline / matrix / mechanism / schedule / economic / administrative / unresolved |
| legal_effective_start/end | date | rule's legal window (may differ from draw span) |
| first_affected_draw | date | first drawing conducted under this era — used for assignment |
| last_affected_draw | date | last drawing under this era; empty = ongoing |
| main_ball_count/min/max | int | main-pool sampling spec |
| special_ball_count/min/max | int | bonus-pool spec; 0 = no bonus ball |
| sampling_without_replacement | bool | always true for these games |
| drawing_days | list | semicolon-joined weekdays |
| scheduled_draw_time / timezone | str | local scheduled time + IANA zone |
| ticket_price | decimal | base play cost |
| jackpot_odds / overall_odds | number | published odds denominators (1 in N) |
| drawing_location / drawing_method | str | where/how the draw is conducted |
| material_change_reason | str | why this era exists |
| rule_identifier | str | official rule doc id (e.g. `53ER99-36`) |
| source_id | str | provenance link to source_registry |
| verification_date / verification_status | — | verified / partially_verified / unresolved |
| notes | str | evidence summary incl. corroboration |

## metadata/source_registry.csv — `Source`

`source_id` `SRC-…`; `authority_tier` 1–3 (see source_policy.md);
`retrieved_at`, `content_sha256`, `local_raw_path` filled by the fetcher.

## metadata/raw_artifacts.csv — `RawArtifact`

`artifact_id` `RA-nnnnnn`; links `source_id` → immutable file
(`immutable_path`), `sha256`, `retrieved_at`, `mime_type`.

## metadata/rule_change_log.csv — `RuleChange`

Append-only log of every rule event: `change_id` `RC-…`, legal and
draw-effective dates, `classification`, `statistically_material` (true iff the
sampling process changed), `before_matrix`/`after_matrix` shorthand,
`resulting_regime_id`, `source_ids`, `verification_status`.

## metadata/draw_sources.csv — `DrawSource`

Inventory of official winning-number sources for Phase 1 ingestion: coverage
window, format, which metadata fields are present (`has_machine_id`,
`has_ball_set_id`, `preserves_draw_order`, …), known limitations, and the
recommended ingestion strategy. Rows may document *gaps* (no URL) — e.g.
`DS-PB-EARLY-GAP`, `DS-MM-BIGGAME-GAP`.

## Future draw tables (schemas/draws.py)

`Draw`: `draw_id` `XX-D-YYYY-MM-DD`, `regime_id` (required — a draw without a
regime cannot exist), `draw_date`, `main_numbers` in **source-reported**
order, `special_ball`, `multiplier`, jackpot fields, `machine_id`,
`ball_set_id`, provenance fields, `validation_status`.

`DrawNumber`: normalized (draw_id, ball_position, ball_type, number).
`ball_position` is the source-defined ordering — physical draw order only if
the source preserves it (FL Lotto archive: draw order through 2005-01-29,
sorted ascending from 2005-02-02; NY Open Data: always sorted).

## registry/*.csv — governance ledgers

Schemas in `src/fortuna/schemas/governance.py`: `Hypothesis` (`H-nnn`),
`Experiment` (`EXP-nnn`), `ModelRegistration` (`M-nnn`),
`ProspectivePrediction` (`P-nnnn`), `DecisionLogEntry` (`D-nnn`).
