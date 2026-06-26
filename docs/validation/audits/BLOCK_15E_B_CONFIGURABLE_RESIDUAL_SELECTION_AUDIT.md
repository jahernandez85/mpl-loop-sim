# Block 15E-B Configurable Residual Selection Audit

Date: 2026-06-26

## Verdict

Approved with minor corrective fixes.

Block 15E-B correctly implements an explicit configurable residual-selection MVP after audit fixes. Residual modes are caller-selected, roles remain metadata only, closures are not inferred from roles, and evaluation is gated by explicit request data. No solve path, property backend, correlation registry, HX model, production component execution, `SystemState`, or `FluidState` path was added.

## Branch And Commits

- Branch: `phase-15e-b-configurable-residual-selection`
- Base commit: `c451c26` (`Merge branch 'phase-15e-a-configurable-scenario-builder'`)
- HEAD before audit: `c451c26`
- Audit commit: created after this audit document

## Scope Audited

Runtime:
- `src/mpl_sim/network/configurable_residual_selection.py`
- `src/mpl_sim/network/__init__.py`

Tests:
- `tests/network/test_configurable_residual_selection.py`
- `tests/network/test_configurable_residual_selection_integration.py`

Docs:
- `docs/roadmap/PROJECT_STATUS.md`

Related source reviewed:
- `src/mpl_sim/network/configurable_scenarios.py`
- `src/mpl_sim/network/fixed_single_loop_residuals.py`
- `src/mpl_sim/network/fixed_single_loop_runner.py`
- `src/mpl_sim/network/parallel_topology_residuals.py`
- `src/mpl_sim/network/closure_integration.py`
- `src/mpl_sim/network/fixed_single_loop_scenario.py`
- `src/mpl_sim/network/parallel_topology_scenario.py`

## Public API Added

- `ConfigurableResidualMode`
- `ConfigurableResidualSelectionRequest`
- `ConfigurableResidualCompatibilityResult`
- `ConfigurableResidualSelectionResult`
- `select_configurable_residual_strategy`
- `evaluate_selected_configurable_residuals`
- `build_configurable_residual_selection_report`

These are exported from `mpl_sim.network`.

## Checkpoint Review

15E-B.1 residual mode/request/result API: complete after minor fix. `ConfigurableResidualSelectionRequest` is frozen, validates `build_result`, `mode`, mode-specific parameter types, unknown-value mappings, `closure_residual_set`, `metadata`, and `evaluate`. Unknown-value mappings and metadata are defensively copied.

15E-B.2 selection/reporting/explicitness: complete after minor fix. Selection does not infer a mode or closures from roles. Reports are plain JSON-serializable dictionaries with `no_solve: True`, `roles_selected_physics: False`, and `closures_inferred_from_roles: False`.

15E-B.3 evaluation/integration/regression: complete after minor fix. Evaluation occurs only when `request.evaluate=True`, compatibility is satisfied, and explicit mode-specific inputs are supplied. Evaluators reuse existing evaluation-only fixed single-loop, fixed two-branch, and closure integration APIs.

## Residual Mode Review

Declaration-only: accepts any valid `ConfigurableScenarioBuildResult`; does not evaluate residuals; does not require physical parameters; reports no solve.

Fixed single-loop algebraic: explicitly requested; compatible only with the fixed single-loop MVP structural signature; uses `evaluate_fixed_single_loop_residuals` only when `evaluate=True`; never calls `solve_fixed_single_loop_residuals`.

Fixed two-branch parallel algebraic: explicitly requested; compatible only with the fixed two-branch MVP structural signature; uses `evaluate_parallel_topology_residuals` only when `evaluate=True`; no solve.

Closure-only: explicitly requested; requires an explicit `CombinedClosureResidualSet`; closure evaluation also requires explicit unknown values and `evaluate=True`; no closures are inferred from roles.

## Request/Result Validation Review

`ConfigurableResidualSelectionRequest`, `ConfigurableResidualCompatibilityResult`, and `ConfigurableResidualSelectionResult` are frozen dataclasses. Audit fixes added explicit `evaluate: bool = False` validation and defensive copies for unknown-value mappings. `ConfigurableResidualSelectionResult.no_solve` remains always true and carries deferred reasons when evaluation is not performed.

## Compatibility Review

Audit found the original compatibility checks were too narrow: fixed modes checked conventional component/node/branch ID order but not graph edge shape. The audit fixed this by checking graph edge signatures and unknown/residual names against the existing fixed MVP builders, while still ignoring roles and `component_type`. Tests now reject conventional IDs with wrong graph edges.

## Explicitness Safeguard Review

Roles remain metadata only. Tests verify role changes do not alter compatibility for the same structure, roles do not select a residual mode, pump/pipe/valve roles do not create hydraulic closures, evaporator/condenser roles do not create thermal closures, and reports state role/closure inference flags as false.

## Evaluation Behavior Review

Audit found the original selector evaluated automatically when parameters and unknowns were present. The audit fixed this by requiring `request.evaluate=True` before evaluation. Pure selection now remains pure even with complete evaluation inputs. `evaluate_selected_configurable_residuals` raises clearly when evaluation was deferred or compatibility failed.

No call to `solve_fixed_single_loop_residuals` exists in the new runtime path. Existing fixed-loop closeout tests still exercise that older fixed-loop solver path independently; 15E-B does not call it.

## Report Behavior Review

`build_configurable_residual_selection_report` returns a plain JSON-serializable dictionary. It includes selected mode, compatibility status/reasons, evaluation status, residual values and norms when evaluation occurred, `no_solve`, explicit false role/closure inference flags, component/node/branch IDs, declaration names, and limitations. It does not write files, import pandas, or plot.

## Validation Results

All validation used repository-local base temp directories and `-p no:cacheprovider`.

- 15E-B residual-selection tests: 83 passed.
- 15E-B integration tests: 32 passed.
- 15E-B focused total: 115 passed.
- 15E-A regression: 174 passed.
- 15D-C regression: 104 passed.
- 15D-B regression: 203 passed.
- 15D-A regression: 205 passed.
- 15C-B regression: 152 passed.
- 15B fixed-loop regression: 333 passed.
- Production contract regression: 60 passed; known classes still `NO_CONTRIBUTE_METHOD`.
- Network suite: 2848 passed.
- Full suite: 6709 passed.
- Skips/xfails/deselections: none observed in the clean validation runs.

Examples:
- `python examples/minimal_evaporator_condenser_loop.py`: passed.
- `python examples/fixed_heat_rate_hx.py`: passed.
- `python examples/segmented_counterflow_hx.py`: passed.
- `python examples/minimal_closed_mpl_solver.py`: passed.
- `python examples/minimal_pressure_closure.py`: passed.
- `python examples/minimal_coupled_closure.py`: passed.

Quality gates:
- `ruff check src tests examples`: passed.
- `black --check --no-cache --verbose src tests examples`: passed, 221 files unchanged.
- `git diff --check`: passed.

## Full-Suite Count Discrepancy

Claude reported `6497 passed excluding pre-existing env errors`, which was not accepted. The prior audited 15E-A full-suite count was 6594. After audit fixes, 15E-B has 115 tests, so the expected full-suite count is `6594 + 115 = 6709`; the fresh full-suite run collected and passed exactly 6709 tests.

The lower 6497 count is best explained as an incomplete or excluded run, not the actual branch state. A stale `.pytest_15eb_network` temp root reproduced a Windows cleanup permission error during the first network-suite attempt. Rerunning with a genuinely fresh repo-local temp root passed cleanly, and the stale temp roots were removed with elevated permissions. No unresolved full-suite errors remain.

## Boundary Search Results

Searches covered CoolProp/property/correlation references, `contribute`, `SystemState`/`FluidState`, `component_type`, roles, solve patterns, properties/components/correlations/HX imports, production component class names, file writing, physical-property/HX terminology, and least-squares/root/minimize terms.

Classification:
- New 15E-B runtime hits are documentation/limitation negative statements, fixed conventional ID labels, report fields, and allowed calls to existing evaluation-only APIs.
- New 15E-B tests contain helper scenario declarations, negative assertions, and integration calls to existing evaluation-only APIs.
- Broad repository hits for `solve_fixed_single_loop_residuals` are existing fixed-loop tests/runtime, not 15E-B runtime calls.
- Broad repository hits for `CoolProp`, `PropertyBackend`, `CorrelationRegistry`, `SystemState`, `FluidState`, `contribute`, and `NetworkGraph.solve` are older documentation negative statements or boundary tests unless already part of pre-existing non-15E-B modules.
- No prohibited executable hit was found in the 15E-B runtime implementation.

## Documentation Alignment

`docs/roadmap/PROJECT_STATUS.md` now states that 15E-B:
- adds explicit residual modes for configurable scenario declarations;
- requires explicit user-requested modes and explicit `evaluate=True` for evaluation;
- treats roles as metadata only;
- does not infer closures or physical equations from roles;
- reuses fixed single-loop and fixed two-branch evaluation-only layers only when structurally compatible and explicitly selected;
- evaluates closure-only residuals only with explicit closure sets and unknown values;
- does not solve;
- is not property-, correlation-, or HX-backed;
- does not execute production components;
- does not assemble `SystemState` or construct `FluidState`;
- does not add generic `solve(network)` or `NetworkGraph.solve`;
- leaves production adapters, property/correlation/HX-backed closures, rank/solvability analysis, and physically predictive solves to later blocks.

## Findings

Critical: none.

Major: none remaining.

Minor fixed:
- Added explicit `evaluate: bool = False` so selection does not automatically evaluate.
- Added defensive copies for unknown-value mappings.
- Strengthened fixed-mode compatibility with graph edge signatures and unknown/residual name checks.
- Added tests for explicit evaluation gating and same-ID wrong-topology incompatibility.
- Corrected roadmap counts and wording.

Minor remaining: none.

## Deferred Items

- Configurable physical residual assembly beyond known fixed MVP structures.
- Production component adapters.
- Property/correlation/HX-backed closures.
- Rank/solvability analysis.
- Physically predictive solves.

## Readiness

Block 15E-B is ready to merge.

Merge readiness: yes.
