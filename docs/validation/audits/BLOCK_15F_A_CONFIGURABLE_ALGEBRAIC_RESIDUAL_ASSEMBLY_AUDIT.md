# Block 15F-A Configurable Algebraic Residual Assembly Audit

## Verdict

Approved with minor fixes.

Block 15F-A correctly implements explicit configurable algebraic residual declarations
and evaluation for configurable scenarios. The implementation remains user-declared,
algebraic, property-free, correlation-free, HX-model-free, production-component-free,
and evaluation-only. No automatic residual inference, role-based physics dispatch,
topology-based residual generation, closure inference, `SystemState` assembly,
`FluidState` construction, production `contribute(...)`, generic `solve(network)`, or
`NetworkGraph.solve()` path was introduced.

## Branch And Commits

- Branch audited: `phase-15f-a-configurable-algebraic-residual-assembly`
- Base commit: `76980b9` (`Merge branch 'phase-15e-c-configurable-selection-closeout'`)
- HEAD before audit: `76980b9`
- Main comparison: `main...HEAD` was empty because 15F-A work was uncommitted in the
  working tree at audit start.

## Scope Audited

Runtime files:

- `src/mpl_sim/network/configurable_algebraic_residuals.py`
- `src/mpl_sim/network/__init__.py`

Test files:

- `tests/network/test_configurable_algebraic_residuals.py`
- `tests/network/test_configurable_algebraic_residuals_integration.py`

Docs:

- `docs/roadmap/PROJECT_STATUS.md`

Related files inspected:

- `src/mpl_sim/network/configurable_scenarios.py`
- `src/mpl_sim/network/configurable_residual_selection.py`
- `src/mpl_sim/network/closure_integration.py`
- `src/mpl_sim/network/thermal_closures.py`
- `src/mpl_sim/network/hydraulic_closures.py`

No frozen architecture documents were modified.

## Public API Added

- `ConfigurableAlgebraicResidualKind`
- `ConfigurableAlgebraicResidualDeclaration`
- `MassBalanceResidualDeclaration`
- `PressureDifferenceResidualDeclaration`
- `ImposedPressureResidualDeclaration`
- `ImposedMassFlowResidualDeclaration`
- `EnthalpyFlowResidualDeclaration`
- `ConfigurableAlgebraicResidualSet`
- `ConfigurableAlgebraicResidualEvaluationResult`
- `build_configurable_algebraic_residual_set`
- `evaluate_configurable_algebraic_residuals`
- `validate_algebraic_residuals_against_scenario`
- `build_configurable_algebraic_residual_report`

These are exported from `mpl_sim.network` and remain narrow to the 15F-A surface.

## Checkpoint Review

15F-A.1 residual declarations: passed. All residual declarations are frozen
dataclasses, validate names/scalars, expose deterministic `required_unknown_names`,
and evaluate only explicit scalar algebra over caller-supplied unknown mappings.

15F-A.2 residual set/evaluation/report: passed with minor fixes. The residual set
preserves declaration order, rejects duplicates and empty sets, rejects bad unknown
values, returns read-only residual mappings, computes max absolute and L2 norms, and
does not evaluate during construction. The report is JSON-serializable and now has
explicit flags for no automatic residual inference and no topology-based residual
inference.

15F-A.3 configurable scenario integration/regression: passed. Compatibility checking
validates declared unknown names against `build_result.unknown_names` only. It does
not generate residuals, evaluate residuals, infer closures, or solve.

## Residual Declaration Review

Mass balance: equation is `r = sum(incoming) - sum(outgoing)`. Names are explicit,
at least one side is required, name validation is present, no graph/role inference
exists, and sign convention is tested.

Pressure difference: equation is `r = P_outlet - P_inlet + delta_p`, with positive
`delta_p` documented as pressure drop and negative as pressure rise. `delta_p` is an
explicit finite scalar. No Darcy-Weisbach, valve law, pump map, density, viscosity,
Reynolds number, friction factor, or correlation call exists.

Imposed pressure: equation is `r = P_unknown - P_imposed`; the pressure unknown and
finite imposed value are explicit. No state or property construction exists.

Imposed mass flow: equation is `r = mdot_unknown - mdot_imposed`; the mass-flow
unknown and finite imposed value are explicit. No pump model or flow prediction exists.

Enthalpy flow: equation is `r = q - mdot * (h_out - h_in)`. `q`, `mdot`, `h_in`, and
`h_out` are explicit unknown names. No `FluidState`, property backend, fluid identity,
phase/quality/saturation logic, or enthalpy-temperature conversion exists. Sign
convention is tested.

## Scenario Compatibility Review

`validate_algebraic_residuals_against_scenario(...)` checks only that declared
unknown names are present in `build_result.unknown_names`. During audit, its
duck-typed boundary was hardened to require `unknown_names` to be a tuple of
non-empty strings. The returned report is plain JSON-serializable data and includes
deterministic missing-unknown reporting plus:

- `no_residuals_inferred_from_roles: True`
- `no_residuals_inferred_from_topology: True`

No residual declarations are generated from roles, component IDs, node IDs, branches,
graph topology, or connection patterns.

## Report Behavior Review

`build_configurable_algebraic_residual_report(...)` returns a plain
JSON-serializable dictionary. It includes status, residual names, residual values,
max absolute residual, L2 norm, unknown names used, limitations, and optional scenario
compatibility. It states:

- no solve
- no properties
- no correlations
- no HX models
- no production components
- no role-based physics
- no automatic residual inference
- no topology-based residual inference
- no automatic closure inference

It does not write files, import pandas, plot, evaluate components, or imply physical
predictiveness.

## Validation Results

All successful pytest runs used `-p no:cacheprovider`.

- 15F-A core: `pytest tests/network/test_configurable_algebraic_residuals.py -q --basetemp=.pytest_15fa_core -p no:cacheprovider` passed; 152 tests collected.
- 15F-A integration: `pytest tests/network/test_configurable_algebraic_residuals_integration.py -q --basetemp=.pytest_15fa_integration -p no:cacheprovider` passed; 28 tests collected.
- 15E-C regression: 65 passed.
- 15E-B regression: 115 passed (83 unit + 32 integration).
- 15E-A regression: 174 passed (125 configurable scenarios + 49 fixed equivalence).
- 15D-C regression: 104 passed (69 closure integration + 35 parallel context).
- 15D-B regression: 203 passed.
- 15D-A regression: 205 passed.
- 15C-B regression: 152 passed (90 residuals + 62 closeout).
- 15B regression: initial requested base-temp hit Windows `PermissionError`; rerun with `.pytest_15fa_15b_retry` passed, 249 tests collected.
- Production contract regression: 60 passed; all six known production classes remain `NO_CONTRIBUTE_METHOD`.
- Network suite: initial requested base-temp hit the same Windows `PermissionError`; rerun with `.pytest_15fa_network_retry` and final rerun with `.pytest_15fa_network_final` passed, 3093 tests collected.
- Full suite: initial requested base-temp hit the same Windows `PermissionError`; rerun with `.pytest_15fa_full_retry` and final rerun with `.pytest_15fa_full_final` passed, 6954 tests collected.
- Skips/xfails/deselections: none reported in successful runs.

Full-suite arithmetic:

- Block 15E-C baseline: 6774
- Block 15F-A new tests: 180
- Expected: 6954
- Observed collected/passing total: 6954

Windows temp/cache issue:

- Reproduced as pytest setup `PermissionError` while removing stale repo-local
  base-temp roots in no-file-write `tmp_path` tests.
- Classified as environmental Windows temp-root cleanup behavior, not a 15F-A
  implementation failure.
- Fresh alternate repo-local base-temp reruns passed cleanly.

## Examples

All six examples exited with code 0:

- `python examples/minimal_evaporator_condenser_loop.py`
- `python examples/fixed_heat_rate_hx.py`
- `python examples/segmented_counterflow_hx.py`
- `python examples/minimal_closed_mpl_solver.py`
- `python examples/minimal_pressure_closure.py`
- `python examples/minimal_coupled_closure.py`

## Lint, Format, Diff Check

- `ruff check src tests examples`: passed.
- `black --check --no-cache --verbose src tests examples`: passed; 225 files unchanged after audit formatting.
- `git diff --check`: passed. It prints only the existing CRLF warning for `PROJECT_STATUS.md` when applicable.

## Boundary Searches

Searches were run for:

- `CoolProp|PropertyBackend|CorrelationRegistry`
- `contribute(`, `.contribute(`, `def contribute`
- `SystemState|FluidState`
- `component_type`, `role`
- `def solve|solve(network|NetworkGraph.solve|solve_fixed_single_loop_residuals`
- forbidden imports from properties/components/correlations/HX models
- production component class names
- file I/O patterns
- saturation/quality/phase/LMTD/NTU/UA/HTC/property tokens
- least-squares/root/minimize solver tokens

Classification:

- 15F-A executable code: no prohibited hits.
- 15F-A source hits: negative documentation/limitations only.
- 15F-A tests: negative assertions, source-inspection reads, and role-invariance tests only.
- Broader repo hits: existing allowed Phase 13H/fixed-loop solver APIs, historical docs, and negative boundary tests. These are outside the 15F-A implementation path and do not add generic `solve(network)` or `NetworkGraph.solve()`.
- Production `def contribute`: none in production source. Hits are test-local inspection fixtures only.
- `.contribute(` calls: no executable source calls in 15F-A or production component paths.

## Documentation Alignment

`docs/roadmap/PROJECT_STATUS.md` was updated to make Block 15F-A the current
active phase, preserve the explicit no-solve/no-property/no-role/topology-inference
boundaries, correct a stale Phase 13H wording to "callback-only residual solver",
and record final counts.

## Findings

Critical: none.

Major: none.

Minor fixed:

- Added explicit report flags for no automatic residual inference and no
  topology-based residual inference.
- Hardened scenario compatibility duck typing to validate `unknown_names` shape.
- Fixed one non-interpolated f-string error message.
- Ran Black formatting on the new 15F-A runtime module.
- Updated roadmap status from 15E-C to 15F-A and clarified stale solver wording.

Minor remaining:

- None.

## Deferred Items

- Richer configurable physical residual assembly.
- Production component adapters.
- Property/correlation/HX-backed closures.
- Rank/solvability analysis.
- Physically predictive solves.
- Arbitrary-topology physical simulation.

## Readiness

Block 15F-A is ready to merge within its explicit configurable algebraic residual
assembly foundation MVP scope.

Merge readiness: yes, after committing this audit and pushing the audited branch.
