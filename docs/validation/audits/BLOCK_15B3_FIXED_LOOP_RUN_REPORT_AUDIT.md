# Block 15B.3 Fixed-Loop Run/Report Audit

## Verdict

**APPROVED after corrective audit fix.** No critical or major findings remain.

## Branch and commits

- Branch: `phase-15b3-fixed-loop-run-report`
- Base commit: `fbb852beb24078b77a726147c8e4468cd6e2f84f`
- HEAD before audit: `fbb852beb24078b77a726147c8e4468cd6e2f84f`
- Audit date: 2026-06-23

## Scope audited

Block 15B.3 adds a fixed-single-loop-only evaluate/solve/report layer over the
15B.1 scenario, 15B.2 residual assembly, Phase 13G evaluation, and Phase 13H
callback-only solver. Frozen architecture documents were not modified.

Changed files:

- `src/mpl_sim/network/fixed_single_loop_runner.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_fixed_single_loop_runner.py`
- `docs/roadmap/PROJECT_STATUS.md`
- `docs/validation/audits/BLOCK_15B3_FIXED_LOOP_RUN_REPORT_AUDIT.md`

## Public API added

- `FixedSingleLoopEvaluationResult`
- `FixedSingleLoopSolveRequest`
- `FixedSingleLoopSolveResult`
- `evaluate_fixed_single_loop_residuals`
- `solve_fixed_single_loop_residuals`
- `build_fixed_single_loop_report`

## Source and behavior review

Evaluation validates exact unknown coverage and finite, numeric, non-bool values;
builds the 15B.2 residual assembly; evaluates through existing adapter/evaluation
infrastructure; preserves scenario residual order; and returns frozen results with
read-only mappings, maximum absolute residual, and L2 residual.

At the known consistent point all eight residuals are zero. Away from that point,
mass-flow or pressure perturbations produce nonzero residuals, and both reported
norms match direct calculations.

The loop's four mass-balance equations leave the common mass-flow level
underdetermined. The corrected solve path uses the request's explicit,
continuity-consistent mass-flow values as a fixed gauge and delegates only the
determined four-pressure subsystem to `solve_network_residual_problem`. It uses
the original 15B.2 pressure callbacks and re-evaluates all eight original
residuals before returning. A controlled zero-pressure guess converges to the
known pressure solution; all final residuals are within tolerance. Inconsistent
mass-flow gauges return a clear non-converged result without iteration.

Reports are plain serializable dictionaries containing symbolic scenario IDs,
unknowns, residual ordering and values, norms, and convergence diagnostics. They
do not write files or add reporting dependencies.

## Fixed-loop-only and architecture review

The implementation consumes `FixedSingleLoopScenario` and
`FixedSingleLoopResidualParameters`. It does not inspect arbitrary graph topology,
dispatch physics from `component_type`, execute production components, construct
`SystemState` or `FluidState`, call properties/correlations/HX models, add
`solve(network)`, or attach solving behavior to `NetworkGraph`.

## Validation results

- Block 15B.3 focused: **100 passed**
- Block 15B.2 residual regression: **102 passed**
- Block 15B.1 scenario regression: **84 passed**
- Block 15A.4 closeout regression: **38 passed**
- Production contract inspection: **60 passed**
- Network suite: **1704 passed**
- Full suite: **5565 passed**
- Skipped/xfailed/deselected: **none reported**
- Six required examples: **all passed**
- `ruff check src tests examples`: **passed**
- `black --check --no-cache --verbose src tests examples`: **passed**
- `git diff --check`: **passed**

Pytest emitted an existing warning that `.pytest_cache` was not writable. All
test executions used writable repository-local `--basetemp` directories and
completed successfully.

## Boundary-search results

- `CoolProp`, `PropertyBackend`, `CorrelationRegistry`, `SystemState`,
  `FluidState`, `component_type`, arbitrary-topology, and generic-solve hits in
  the new runner are documentation negative statements or test negative assertions.
- Production component names appear only in contract-inspection regression tests.
- No executable `.contribute(...)` call or `def contribute` was added.
- No executable property, correlation, HX-model, or production-component import
  exists in the runner.
- The sole allowed executable solver integration is the fixed-loop call to the
  existing `solve_network_residual_problem`.
- No `solve(network)` or `NetworkGraph.solve()` implementation exists.

## Production-contract regression

`Component`, `Pipe`, `PumpComponent`, `AccumulatorComponent`,
`EvaporatorComponent`, and `CondenserComponent` all continue to report
`NO_CONTRIBUTE_METHOD`.

## Documentation alignment

`PROJECT_STATUS.md` accurately describes 15B.1, 15B.2, and 15B.3; records the
fixed mass-flow gauge and callback-only pressure solve; preserves all architecture
negations; and reports the final validation counts.

## Findings and corrective changes

- Critical findings: none.
- Major finding found and fixed: the initial implementation exposed a solve API
  whose controlled off-solution path always failed on the known singular
  mass-flow Jacobian. The wrapper was narrowed to solve the determined pressure
  subsystem while retaining explicit continuity-consistent mass flow and a final
  all-eight-residual check.
- Minor findings fixed: documentation and focused solver tests were updated to
  describe and prove the corrected behavior; Black formatting was applied.
- Remaining minor findings: none.

## Deferred items

Arbitrary-topology simulation, automatic physics selection, real production
component execution, property/correlation/HX-backed execution, `SystemState`
assembly, and `FluidState` construction remain deferred.

## Readiness

Block 15B.3 is ready. The branch is merge-ready after the audit commit and push.
