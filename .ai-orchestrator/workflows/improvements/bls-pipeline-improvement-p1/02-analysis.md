---
agent: analysis
sequence: 2
references: ["spec"]
summary: "All seven P1 fixes are technically feasible within the existing stack. Primary risks are bootstrap FAP performance (R7), config resolver complexity (R11), and R7/R13 interaction ordering. R8 is trivial; R11 is the most cross-cutting. Recommend implementing R8 first, R11 second (unblocks config-dependent fixes), then R9/R10, R7, R12, R13 last."
---

## Feasibility Assessment

**R7 — Bootstrap FAP (FR-1 through FR-5)**
- Technical Feasibility: **Feasible with Risk**. Bootstrap requires N=1000 full BLS power computations per candidate. Astropy's `BoxLeastSquares.power()` on a typical TESS light curve (~30k points, 2000 periods) takes ~0.5–2s, so 1000 iterations could take 500–2000s per candidate without optimization. Mitigation: use a reduced period grid for bootstrap (fewer periods) or subsample flux. The opt-in flag (FR-2) limits blast radius.
- Resource Feasibility: Feasible. Single function addition to `bls.py`.
- Integration Feasibility: Feasible. `BLSCandidate` is a frozen dataclass; adding `fap` field is backward-compatible since it's constructed internally.

**R8 — Missing Alias Ratios (FR-6)**
- Technical Feasibility: **Feasible**. One-line change to a tuple literal.
- Resource Feasibility: Trivial.
- Integration Feasibility: Feasible. No API change.

**R9 — Secondary Eclipse Check (FR-7 through FR-11)**
- Technical Feasibility: **Feasible**. Reuses the pattern from `_group_depth_ppm()` with a phase offset of 0.5×period. The existing helper computes depth for odd/even parity groups; secondary eclipse needs depth at phase 0.5 relative to transit_time.
- Resource Feasibility: Feasible. ~40 lines of new code.
- Integration Feasibility: Feasible. Adds fields to `CandidateVettingResult` (frozen dataclass, constructed internally) and a new check in `vet_bls_candidates()`.

**R10 — Phase-Fold Depth Consistency (FR-12 through FR-16)**
- Technical Feasibility: **Feasible**. Phase-fold, split by time midpoint, measure depth in each half. Standard numpy operations.
- Resource Feasibility: Feasible. ~40 lines of new code.
- Integration Feasibility: Feasible. Same pattern as R9.

**R11 — VettingConfig/ParameterConfig (FR-17 through FR-24)**
- Technical Feasibility: **Feasible with Risk**. The config resolver (`resolve_runtime_config()`) uses a layered merge of `_DEFAULTS` → preset TOML → user TOML. Adding two new sections requires updating the merge logic, all three preset files, and all call sites in `pipeline.py`. Risk: the resolver may have section-specific logic that needs extension.
- Resource Feasibility: Medium effort. Touches config.py, pipeline.py, 3 preset TOMLs, and potentially parameters.py.
- Integration Feasibility: Feasible. Backward compatibility guaranteed by `_DEFAULTS` mechanism (FR-24).

**R12 — Diagnostic Annotations (FR-25 through FR-29)**
- Technical Feasibility: **Feasible**. All annotations use standard matplotlib text, patches, and subplot APIs. The function signature change (FR-29) requires updating all call sites.
- Resource Feasibility: Medium effort. Significant matplotlib code for 4 new visual elements plus a new subplot.
- Integration Feasibility: Feasible. Call sites in `pipeline.py` need to pass vetting results and parameter estimates.

**R13 — Iterative Transit Masking (FR-30 through FR-33)**
- Technical Feasibility: **Feasible with Risk**. Depends on lightkurve's `flatten()` accepting a mask. The lightkurve API supports `flatten(mask=...)` on `LightCurve` objects. Risk: mask semantics (True=mask vs True=keep) must be verified.
- Resource Feasibility: Feasible. ~30 lines in the BLS execution block of `pipeline.py`.
- Integration Feasibility: Feasible. Contained within the BLS section of `fetch_and_plot()`.

## Risk Register

| Risk ID | Description | Affected Requirements | Likelihood (1-5) | Impact (1-5) | Risk Score | Mitigation Strategy |
|---------|-------------|----------------------|-------------------|--------------|------------|---------------------|
| RISK-1 | Bootstrap FAP runtime exceeds 60s/candidate with full BLS grid (N=1000 × ~1s per BLS call) | FR-3, NFR-1 | 4 | 3 | 12 | Use reduced period grid (e.g., 200 periods) for bootstrap iterations. Document expected runtime in config comments. |
| RISK-2 | Config resolver `resolve_runtime_config()` has section-specific parsing that doesn't generalize to new `[vetting]`/`[parameters]` sections | FR-22, FR-24 | 3 | 4 | 12 | Read resolver code thoroughly before implementation. Add integration test for round-trip config with new sections. |
| RISK-3 | R7+R13 interaction: if both enabled, FAP must run on second-pass BLS only (FR-33), but the pipeline flow may compute FAP during first pass | FR-33 | 3 | 3 | 9 | Implement R13 masking loop to produce final candidates, then compute FAP only on those final candidates. |
| RISK-4 | `save_candidate_diagnostics()` signature change (FR-29) breaks existing call sites if not all callers are updated | FR-29 | 2 | 4 | 8 | Use keyword-only arguments with defaults of `None` for new parameters so existing callers continue to work. |
| RISK-5 | lightkurve `flatten(mask=...)` mask semantics (True=masked vs True=kept) may differ from assumption | FR-31 | 2 | 3 | 6 | Verify mask convention in lightkurve docs/source before implementation. Add assertion on output length. |
| RISK-6 | New `CandidateVettingResult` fields break candidate JSON/CSV serialization in pipeline output | FR-8, FR-13 | 2 | 3 | 6 | Ensure pipeline's candidate serialization uses dataclass field iteration (not hardcoded field lists). Check `_CANDIDATE_CSV_COLUMNS` in pipeline.py. |

## Dependency Map

**Internal Dependencies:**
- R11 (config) → R7 (needs `bls.compute_fap`, `bls.fap_iterations` in config), R9 (needs `vetting.secondary_eclipse_max_fraction`), R10 (needs `vetting.depth_consistency_max_fraction`), R13 (needs `bls.iterative_masking`)
- R9, R10 → R12 (diagnostic plots need vetting result fields from R9/R10)
- R7 ↔ R13 (interaction rule: FAP on final pass only)

**External Dependencies:**
- astropy `BoxLeastSquares` — used by R7 bootstrap. Stable API, low risk.
- lightkurve `LightCurve.flatten(mask=...)` — used by R13. Must verify mask parameter exists.
- matplotlib — used by R12. Stable API, low risk.

**Critical Path:**
R11 (config) → R9/R10 (vetting checks using config) → R12 (plots using vetting results) → R13 (masking, interacts with R7)

R8 has zero dependencies and can be done at any time.

## Requirements Gaps

1. **FR-3 bootstrap grid size**: The spec says N=1000 flux shuffles but does not specify whether the bootstrap BLS uses the same period/duration grid as the main search or a reduced grid. Suggest adding: "Bootstrap BLS iterations MUST use the same duration grid but MAY use a reduced period grid (minimum 200 periods) for performance."
2. **FR-31 mask definition**: The spec says "mask in-transit points from top candidate" but does not specify whether to mask only the top-1 candidate or all candidates above SNR threshold. Suggest: "Mask in-transit points from the rank-1 candidate only."
3. **FR-12 odd/even subplot data source**: The spec says "odd/even transit comparison subplot" but does not specify whether this uses the existing `odd_depth_ppm`/`even_depth_ppm` from vetting or recomputes from raw data. Suggest: "Use `odd_depth_ppm` and `even_depth_ppm` from `CandidateVettingResult`."
4. **Candidate CSV columns (RISK-6)**: The pipeline has a hardcoded `_CANDIDATE_CSV_COLUMNS` list. New fields (`fap`, `pass_secondary_eclipse`, `secondary_eclipse_depth_fraction`, `pass_depth_consistency`, `depth_consistency_fraction`) must be added. This is not explicitly stated in the spec.

## Complexity Estimate

| Component | Complexity | Rationale | Key Challenges |
|-----------|-----------|-----------|----------------|
| R7 — Bootstrap FAP | **High** | FR-3 requires N=1000 BLS iterations per candidate. Performance tuning needed (RISK-1). | Achieving <60s runtime; reduced grid design; NaN handling when bootstrap fails. |
| R8 — Alias Ratios | **Low** | FR-6 is a single tuple modification. | None. |
| R9 — Secondary Eclipse | **Medium** | FR-7 through FR-11 add a new vetting function and 2 dataclass fields. Reuses existing depth measurement pattern. | Phase 0.5 alignment; insufficient-data handling. |
| R10 — Depth Consistency | **Medium** | FR-12 through FR-16 add a new vetting function and 2 dataclass fields. Standard phase-fold + split. | Defining "first half" vs "second half" by time midpoint; edge cases with gaps. |
| R11 — Config Schema | **High** | FR-17 through FR-24 touch config.py, pipeline.py, 3 preset TOMLs, and resolve_runtime_config(). Most cross-cutting change. | Config resolver extension; ensuring backward compatibility (FR-24); wiring 6 constants through pipeline. |
| R12 — Diagnostic Plots | **Medium** | FR-25 through FR-29 add 4 visual elements and change function signature. | Matplotlib layout with additional subplot; text positioning; passing vetting data through call chain. |
| R13 — Iterative Masking | **Medium** | FR-30 through FR-33 add a conditional loop in pipeline.py. | lightkurve mask semantics; R7 interaction ordering; ensuring second-pass candidates fully replace first-pass. |

## Open Questions

1. **Bootstrap grid reduction (FR-3, NFR-1)**: Should bootstrap iterations use a reduced period grid for performance? Default assumption: Yes, use 200 periods for bootstrap to keep runtime manageable. Impact: affects NFR-1 compliance.
2. **Mask target for R13 (FR-31)**: Mask only rank-1 candidate or all candidates? Default assumption: rank-1 only, as stated in context.md ("mask in-transit points"). Impact: affects candidate quality from second pass.

## Recommendations

1. **P0 — Verify lightkurve flatten mask API** (RISK-5, FR-31): Before implementing R13, confirm that `LightCurve.flatten(mask=...)` exists and document the mask convention (True=masked or True=kept). Owner: code agent during R13 implementation.
2. **P0 — Read config resolver code** (RISK-2, FR-22): Before implementing R11, read `resolve_runtime_config()` in full to understand section-specific parsing logic. Owner: architecture agent.
3. **P1 — Implement in dependency order** (all): R8 → R11 → R9 → R10 → R7 → R12 → R13. This respects the internal dependency map and minimizes rework. Owner: impl-plan agent.
4. **P1 — Add new fields to CSV column list** (RISK-6, FR-8, FR-13): Ensure `_CANDIDATE_CSV_COLUMNS` in pipeline.py is updated with `fap`, `pass_secondary_eclipse`, `secondary_eclipse_depth_fraction`, `pass_depth_consistency`, `depth_consistency_fraction`. Owner: code agent.
5. **P2 — Use keyword-only args for diagnostic signature** (RISK-4, FR-29): Add new parameters to `save_candidate_diagnostics()` as keyword-only with `None` defaults to maintain backward compatibility during incremental deployment. Owner: code agent.
