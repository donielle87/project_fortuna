# F-E003 — Corrected Phase 3 Historical Deviation Reanalysis

- **Experiment:** F-E003 (exploratory; candidate-hypothesis generation
  only — nothing here is confirmatory or predictive)
- **Preregistration:** `research/preregistrations/F-E003-phase3-corrected-reanalysis.md`
  (committed before any corrected outcome was read)
- **Config:** `config/experiments/F-E003.yaml`
- **Corrects:** F-E002 (immutable history; D-006/D-007/D-008)
- **Inputs:** corrected Phase 1 dataset `20017442…8ff`;
  F-E001 v4 observation plan `8309e1dd…c10a`; frozen 2,072-draw holdout
  (v2 seal `6dc9a023…ffe18`), corrected exploration 8,248 draws.

## 1. Population changes vs F-E002

The corrected exploration set is the original 8,260 exploration IDs
intersected with corrected analysis-eligible draws — 8,248 draws; the
12 evidence-excluded `SRC-MD-*-ARCHIVE` non-draw records (D-008) are
absent upstream. Segment structure changed in MM-S01/S03/S05/S06 and
PB-S06/S07; order-eligible (physical) coverage changed substantially
after the D-007 audit.

## 2. Results summary

| family | tests | raw p <= .05 | BH flags | Holm flags |
|---|---|---|---|---|
| primary (F-S001..S013) | 202 | 8 | 0 | 0 |
| secondary (P3-S001..S012) | 172 | 8 | 0 | 0 |

- Every F-E002 flag is gone on corrected data. The MM-S05 F-S006 /
  P3-S002 overlap anomalies and all seven P3-S011 order anomalies were
  entirely explained by the MD-archive phantom records and the
  position-semantics mislabeling — exactly as D-007/D-008 diagnosed.
- P3-S011 on genuinely physical, provenance-verified sequences shows
  no anomaly anywhere (|z| <= 1.65 across all 10 evaluable regimes).
- Two primary baselines reported NOT CONVERGED (FL-S01 F-S004,
  PB-S02 F-S002 — discrete near-degenerate statistics on the fresh
  F-E003 replicate stream); neither is flagged; statuses are reported
  honestly, never relabeled.
- 0 candidate hypotheses promoted. `phase3_candidate_hypotheses.csv`
  is empty.

## 3. Artifact adjudication standard

No statistic-level adjustment was performed: exclusions happened
upstream in canonical data, every one backed by independent
schedule/source evidence in `metadata/draw_exclusions.csv`. The
descriptive scans in `phase3_artifact_diagnostics.csv` confirm no
residual consecutive-duplicate events and no ascending-"physical"
populations remain in exploration.

## 4. Interpretation

On honest data, the fair-random null stands across all 202 primary and
172 secondary tests. No candidate hypotheses exist for confirmatory
testing. The F-E002 "anomalies" were a successful demonstration that
the exploratory machinery detects data defects — but they were never
drawing-process signals.

Phase 4 is NOT begun. The holdout remains sealed and unused.
