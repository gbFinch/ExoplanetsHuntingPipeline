---
agent: summary
sequence: 2
references: [research]
summary: "The BLS Pipeline Quality Audit identified 28 issues (7 P0, 12 P1, 9 P2) across the Exohunt transit-search pipeline, rating it 4.7/10 overall. The research passed the critic with an average score of 9.2/10. The most critical next step is implementing BLS SNR computation to give the pipeline a principled detection threshold."
---

## 1. Executive Summary

The Exohunt project is a Python-based exoplanet transit-search pipeline that ingests TESS light curves, preprocesses them, runs Box Least Squares (BLS) transit detection, vets candidates, estimates physical parameters, and produces diagnostic plots. The goal of this workflow was to perform a comprehensive quality audit of the pipeline's scientific correctness, visualization quality, and overall maturity.

A single research agent performed a deep code audit of all seven scientific modules (`bls.py`, `vetting.py`, `preprocess.py`, `parameters.py`, `pipeline.py`, `config.py`, `plotting.py`) and three built-in presets. The audit identified 28 distinct issues: 7 critical (P0), 12 high-priority (P1), and 9 cosmetic/performance (P2). Each issue includes the exact code location, impact description, concrete fix, and estimated implementation complexity.

The pipeline scored 4.7/10 overall. Its strongest area is reproducibility (8/10) — the manifest and config fingerprint system is well-designed. Its weakest areas are false positive control (3/10) and diagnostic output (3/10). The pipeline finds strong transit signals but has no mechanism to assess statistical significance (no SNR or false-alarm probability), silently rejects valid shallow candidates through a vetting logic bug, and produces charts where raw and detrended data are visually indistinguishable. Additionally, the default science preset produces zero visual output, and the quick-look preset cannot find transits at all.

The most significant risk is that the pipeline currently returns "candidates" from pure noise — there is no detection threshold. Implementing BLS SNR computation (~25 lines of code) is the single highest-impact improvement and should be done first.

The recommended path forward is to fix all 7 P0 issues first (estimated ~130 lines total), which would raise the pipeline score to approximately 7/10, then refactor the 600-line pipeline monolith, then address P1 and P2 issues incrementally.

## 2. Chain Overview

| Step | Agent | Artifact | Critic Verdict | Critic Average Score | Key Finding |
|------|-------|----------|----------------|---------------------|-------------|
| 01 | Researcher | 01-research.md | PASS | 9.2 | 28 issues identified (7 P0, 12 P1, 9 P2); pipeline rated 4.7/10; no SNR/FAP is the top critical gap |
| 02 | Summarizer | 02-summary.md | — | — | Executive summary consolidating all findings |

## 3. Key Artifacts

### 01-research.md (Sequence 1)
- **Purpose**: Comprehensive quality audit of the Exohunt BLS transit-search pipeline
- **Status**: Complete
- **Key Content**:
  - 28 issues across 7 modules with severity classification (P0/P1/P2), exact code locations, and concrete fixes
  - Capability Assessment matrix comparing current state against standard transit-search practices across 15 dimensions
  - Pipeline rating across 7 dimensions (detection sensitivity, false positive control, preprocessing quality, diagnostic output, code quality, configuration flexibility, reproducibility)
  - 20 prioritized recommendations (R1-R20) with complexity estimates and validation steps
  - Trade-off analysis of incremental fixes vs. architecture-first refactoring approach
- **Issues Flagged by Critic**: 2 minor (empty references array in frontmatter; Comparison Matrix could include specific citations), 1 suggestion (Issue B3 example could be more illustrative)

## 4. Decisions Made

| Decision | Source Artifact | Rationale | Alternatives Rejected | Impact |
|----------|----------------|-----------|----------------------|--------|
| Classify pipeline issues using P0/P1/P2 severity | 01-research.md | Matches context.md requirement and enables prioritized implementation | Single-tier flat list; CVSS-style scoring | Drives implementation order for all 28 issues |
| Recommend incremental fixes over architecture-first refactor | 01-research.md | P0 science fixes deliver immediate value; project needs backward compatibility | Refactor pipeline.py monolith first, then fix bugs | P0 fixes ship before architectural improvements |
| Rate pipeline 4.7/10 overall | 01-research.md | Weighted average across 7 dimensions; reproducibility (8/10) is strong but detection (4/10) and false positive control (3/10) are critically weak | N/A | Sets baseline for measuring improvement |
| Recommend SNR ≥ 7 as default detection threshold | 01-research.md | Standard threshold in transit surveys (Kepler, TESS-SPOC); configurable to allow tuning | Fixed power threshold; FAP-only threshold | Determines which candidates the pipeline reports |
| Recommend overlay+residual plot design over current 3-panel | 01-research.md | Current panels 1-2 look identical; overlay and residual are standard in transit-search pipelines | Keep current layout with better axis labels; side-by-side zoom panels | Changes the primary diagnostic visualization |

## 5. Risks and Open Items

| # | Type | Description | Source Artifact | Severity | Recommended Action |
|---|------|-------------|-----------------|----------|-------------------|
| 1 | Risk | SNR threshold of 7 may need calibration for TESS-specific noise characteristics | 01-research.md | Medium | Make threshold configurable; calibrate on known planet hosts and non-detections |
| 2 | Risk | Iterative transit masking doubles BLS runtime, may be impractical for batch mode | 01-research.md | Medium | Make masking optional via config flag; default off for quicklook |
| 3 | Risk | Refactoring pipeline.py monolith may introduce regressions | 01-research.md | Medium | Add integration tests comparing full output before/after refactoring |
| 4 | Assumption | Limb darkening correction uses simplified approximation; full treatment needs per-target TIC stellar parameters | 01-research.md | Low | Acceptable for first-pass estimates; document limitation |
| 5 | Assumption | Transit depth suppression assessment based on 3× rule of thumb, not measured on actual pipeline output | 01-research.md | Low | Validate by running pipeline on injected transit signals at various durations |
| 6 | Open Question | Should `quicklook` preset enable BLS? It was intentionally disabled for speed | 01-research.md | Medium | Confirm with project owner; current quicklook BLS settings (n_periods=1200) are already fast |
| 7 | Critic Issue | YAML frontmatter references array is empty despite citing Kovács et al. 2002 and Hippke & Heller 2019 | 01-research.md (critic) | Low | Populate references in a future revision |

## 6. Quality Assessment

- **Overall Verdict**: Ready with caveats. The research artifact is comprehensive and actionable. The 2 minor critic issues do not affect the usability of the findings. The recommendations can be implemented directly from the document.
- **Score Distribution**: Average 9.2/10 across the single evaluated artifact. Range: 8 (structure) to 10 (relevance, actionability).
- **Strongest Area**: Relevance (10/10) and Actionability (10/10) — every finding directly addresses the audit objectives, and every recommendation includes specific code locations, fix descriptions, and complexity estimates.
- **Weakest Area**: Structure (8/10) — the Comparison Matrix could include more specific citations to standard pipeline documentation.
- **Rework Needed**: None. No artifacts received a FAIL verdict.

## 7. Next Steps

| Priority | Action | Owner | Depends On | Expected Outcome |
|----------|--------|-------|-----------|-----------------|
| P0 | Implement BLS SNR computation (R1) — add SNR field to BLSCandidate, add min_snr to BLSConfig | Developer | None | Pipeline has a principled detection threshold; noise peaks no longer reported as candidates |
| P0 | Fix odd/even vetting inconclusive logic (R2) — return "inconclusive" instead of "fail" when data insufficient | Developer | None | Valid shallow/long-period candidates no longer silently rejected |
| P0 | Fix all three preset files (R3) — enable plots in science-default and deep-search, enable BLS in quicklook, fix flatten window | Developer | None | All presets produce both candidates and plots |
| P0 | Fix normalization fallback (R4) — propagate normalized state, handle non-normalized depth correctly | Developer | None | depth_ppm values are always meaningful |
| P0 | Redesign raw-vs-prepared plot (R5) — overlay + residual + percentile bands | Developer | None | Detrending effect is visually obvious |
| P0 | Fix per-sector BLS refinement (R6) — call refine_bls_candidates in per-sector path | Developer | None | Per-sector candidates have same precision as stitched |
| P1 | Decompose pipeline.py monolith (R14) — split into discrete typed stages | Developer | R1-R6 complete | Individual pipeline stages are independently testable |
| P1 | Add VettingConfig and ParameterConfig to config schema (R11) | Developer | R14 (easier after refactor) | Vetting and parameter estimation are user-configurable |
| P1 | Implement remaining P1 recommendations (R7-R13) | Developer | R14 | Pipeline reaches ~9/10 overall score |
| P2 | Implement P2 recommendations (R15-R20) | Developer | P1 items | Pipeline reaches ~10/10 overall score |
