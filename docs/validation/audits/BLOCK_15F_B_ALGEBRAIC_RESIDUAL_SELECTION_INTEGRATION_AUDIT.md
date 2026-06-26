# Block 15F-B Algebraic Residual Selection Integration Audit

## Verdict

Approved with minor fixes.

Block 15F-B correctly integrates the explicit 15F-A configurable algebraic
residual set into the explicit 15E-B residual-selection layer. The new path is
user-requested, evaluation-only, property-free, topology-inference-free,
role-inference-free, production-component-free, and no-solve.

## Branch and Commits

- Branch audited: `phase-15f-b-algebraic-residual-selection-integration`
- Base commit: `fd7da73` (`main`, `origin/main`)
- HEAD before audit: `fd7da73`
- Audit working tree before finalization: uncommitted Block 15F-B changes
- Audit commit: created after this document is added

## Scope Audited

Runtime:

- `src/mpl_sim/network/configurable_residual_selection.py`
- `src/mpl_sim/network/configurable_algebraic_residuals.py`
- `src/mpl_sim/network/__init__.py`

Tests:

- `tests/network/test_configurable_residual_selection.py`
- `tests/network/test_configurable_residual_selection_integration.py`
- `tests/network/test_configurable_algebraic_residual_selection_integration.py`

Docs:

- `docs/roadmap/PROJECT_STATUS.md`
- this audit document

Related modules inspected as needed:

- `src/mpl_sim/network/configurable_scenarios.py`
- `src/mpl_sim/network/closure_integration.py`
- `src/mpl_sim/network/fixed_single_loop_residuals.py`
- `src/mpl_sim/network/parallel_topology_residuals.py`

## Changed Files

Expected 15F-B scope:

- `src/mpl_sim/network/configurable_residual_selection.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_configurable_residual_selection.py`
- `tests/network/test_configurable_algebraic_residual_selection_integration.py`
- `docs/roadmap/PROJECT_STATUS.md`

Audit additions/fixes:

- `docs/validation/audits/BLOCK_15F_B_ALGEBRAIC_RESIDUAL_SELECTION_INTEGRATION_AUDIT.md`
- minor invariant hardening in `ConfigurableResidualSelectionResult`

No frozen architecture documents were modified.

## Public API Changes

- Added `ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC` with value
  `"configurable_algebraic"`.
- Extended `ConfigurableResidualSelectionRequest` with:
  - `algebraic_residual_set`
  - `algebraic_unknown_values`
- Extended `ConfigurableResidualSelectionResult.evaluation_result` to include
  `ConfigurableAlgebraicResidualEvaluationResult`.
- Exported the 15F-A configurable algebraic residual symbols from
  `mpl_sim.network`.
- Extended selection reports with:
  - `residuals_inferred_from_roles: False`
  - `residuals_inferred_from_topology: False`

## Checkpoint Review

### 15F-B.1 API, Mode, Request Integration

Pass.

`CONFIGURABLE_ALGEBRAIC` is a fifth explicit mode. It is not the default and is
reached only through `request.mode`. Existing modes continue to dispatch through
their previous branches.

`ConfigurableResidualSelectionRequest` remains frozen. Mode-specific unknown
mappings, including `algebraic_unknown_values`, are defensively copied with
`MappingProxyType(dict(...))`. The separate algebraic field is safe because it
is consumed only by the configurable algebraic mode and does not alter
single-loop, two-branch, or closure-only unknown-value fields.

### 15F-B.2 Evaluation, Report, No-Inference Behavior

Pass.

Compatibility requires an explicit `ConfigurableAlgebraicResidualSet` and calls
only `validate_algebraic_residuals_against_scenario`. Evaluation occurs only
when compatibility passes and `request.evaluate is True`, then calls only
`evaluate_configurable_algebraic_residuals`.

Reports include selected mode, compatibility details, evaluation residuals and
norms when evaluated, scenario unknown names, `unknown_names_used` when
evaluated, `no_solve: True`, role/topology no-inference flags, and limitation
statements.

### 15F-B.3 Regression and Docs

Pass with minor fixes.

Regression tests for 15F-A, 15E-C, 15E-B, 15E-A, 15D-C, 15D-B, 15D-A, 15C-B,
15B, and production contract inspection passed. `PROJECT_STATUS.md` was aligned
with the final audited 15F-B status and counts.

## Configurable Algebraic Mode Review

Compatibility:

- Requires explicit `algebraic_residual_set`.
- Validates declared unknown names against `build_result.unknown_names`.
- Missing unknown names produce incompatible selection and deterministic reasons.
- Does not evaluate.
- Does not inspect roles or topology to create residual declarations.
- Does not fall back to declaration-only or fixed modes.

Evaluation:

- Runs only when `evaluate=True`.
- Requires explicit `algebraic_unknown_values`.
- Calls only `evaluate_configurable_algebraic_residuals`.
- Missing values, bools, non-numeric values, NaN, and infinity are rejected by
  the 15F-A evaluator.
- Extra unknowns are ignored consistently with 15F-A.
- No solving, production component execution, property calls, correlations, HX
  models, `SystemState`, or `FluidState` are involved.

Report:

- Includes selected mode, compatibility reasons, residual values and norms when
  evaluated, scenario unknown names, `unknown_names_used`, `no_solve: True`,
  and no-inference flags.
- Remains JSON-serializable.

## Existing Modes Review

- `DECLARATION_ONLY`: unchanged; never evaluates residuals, even if evaluation
  fields are supplied.
- `FIXED_SINGLE_LOOP_ALGEBRAIC`: unchanged explicit mode; evaluation-only fixed
  path, no solve through the selection layer.
- `FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC`: unchanged explicit mode;
  evaluation-only fixed two-branch path.
- `CLOSURE_ONLY`: unchanged explicit mode; requires caller-supplied
  `CombinedClosureResidualSet`; no closure inference from roles.

## Request Field Design Review

`algebraic_residual_set` is necessary for explicit user-declared residual
selection and is required for compatibility in `CONFIGURABLE_ALGEBRAIC` mode.

`algebraic_unknown_values` is a separate mode-specific value mapping. This avoids
overloading the existing fixed-loop, two-branch, and closure unknown mappings.
It is defensively copied and read-only after request construction. It does not
bypass common evaluation validation because the 15F-A evaluator performs the
actual required-name and scalar checks.

Pure selection with `evaluate=False` does not evaluate even when all values are
supplied. Missing algebraic values defer selection evaluation clearly, while
`evaluate_selected_configurable_residuals` raises with a clear reason.

## Boundary Search Results

Searches run:

- `CoolProp|PropertyBackend|CorrelationRegistry`
- `contribute\(`
- `\.contribute\(`
- `def contribute`
- `SystemState|FluidState`
- `component_type`
- `role`
- `def solve|solve\(network|NetworkGraph\.solve|solve_fixed_single_loop_residuals`
- `mpl_sim\.properties|mpl_sim\.components|mpl_sim\.correlations|mpl_sim\.hx_models`
- production component class names
- file-writing patterns
- property/HX/correlation vocabulary
- `least_squares|lstsq|pinv|root|fsolve|minimize`

Classification:

- New 15F-B runtime hits were documentation negative statements, enum/report
  metadata, compatibility/evaluation dispatch, or allowed imports of existing
  explicit network residual modules.
- `SystemState`, `FluidState`, CoolProp, PropertyBackend, correlation, HX,
  `component_type`, and role hits in the new runtime path are negative
  statements only.
- `solve_fixed_single_loop_residuals` is mentioned as a prohibition and remains
  absent from `configurable_residual_selection.py` imports and calls.
- Existing repository solver/fixed-loop hits are pre-existing scoped APIs outside
  15F-B and not used by configurable algebraic selection.
- No prohibited executable 15F-B hits found.

## Validation Commands and Results

Focused and regression tests:

- `pytest tests/network/test_configurable_algebraic_residual_selection_integration.py -q --basetemp=.pytest_15fb_new -p no:cacheprovider`
  - 53 passed
- `pytest tests/network/test_configurable_residual_selection.py tests/network/test_configurable_residual_selection_integration.py -q --basetemp=.pytest_15fb_selection -p no:cacheprovider`
  - 115 passed
- `pytest tests/network/test_configurable_algebraic_residuals.py tests/network/test_configurable_algebraic_residuals_integration.py -q --basetemp=.pytest_15fb_15fa -p no:cacheprovider`
  - 180 passed
- `pytest tests/network/test_configurable_residual_selection_closeout.py -q --basetemp=.pytest_15fb_15ec -p no:cacheprovider`
  - 65 passed
- `pytest tests/network/test_configurable_scenarios.py tests/network/test_configurable_scenarios_fixed_equivalence.py -q --basetemp=.pytest_15fb_15ea -p no:cacheprovider`
  - 174 passed
- `pytest tests/network/test_closure_integration.py tests/network/test_closure_integration_parallel_context.py -q --basetemp=.pytest_15fb_15dc -p no:cacheprovider`
  - 104 passed
- `pytest tests/network/test_thermal_closures.py tests/network/test_thermal_closure_diagnostics.py tests/network/test_thermal_closure_integration.py -q --basetemp=.pytest_15fb_15db -p no:cacheprovider`
  - 203 passed
- `pytest tests/network/test_hydraulic_closures.py tests/network/test_hydraulic_closure_diagnostics.py tests/network/test_hydraulic_closure_parallel_integration.py -q --basetemp=.pytest_15fb_15da -p no:cacheprovider`
  - 205 passed
- `pytest tests/network/test_parallel_topology_residuals.py tests/network/test_parallel_topology_mvp_closeout.py -q --basetemp=.pytest_15fb_15cb -p no:cacheprovider`
  - 152 passed
- `pytest tests/network/test_fixed_single_loop_mvp_closeout.py tests/network/test_fixed_single_loop_runner.py tests/network/test_fixed_single_loop_residuals.py -q --basetemp=.pytest_15fb_15b -p no:cacheprovider`
  - 249 passed
- `pytest tests/network/test_production_component_contract_inspection.py -q --basetemp=.pytest_15fb_prod_contract -p no:cacheprovider`
  - 60 passed

Broad suites:

- `pytest tests/network -q --basetemp=.pytest_15fb_network -p no:cacheprovider`
  - reproduced Windows `PermissionError` base-temp cleanup issue
- `pytest tests/network -q --basetemp=.pytest_15fb_network_fresh -p no:cacheprovider`
  - 3146 passed
- `pytest -q --basetemp=.pytest_15fb_full -p no:cacheprovider`
  - reproduced Windows `PermissionError` base-temp cleanup issue
- `pytest -q --basetemp=.pytest_15fb_full_fresh -p no:cacheprovider`
  - 7007 passed

No skips, xfails, or deselections were reported in the successful fresh runs.

## Full-Suite Count Arithmetic

- 15F-A audited baseline: 6954 passed
- 15F-B new tests: 53 passed
- Expected: 7007
- Observed full suite: 7007 passed

## Examples

All six examples exited 0:

- `python examples/minimal_evaporator_condenser_loop.py`
- `python examples/fixed_heat_rate_hx.py`
- `python examples/segmented_counterflow_hx.py`
- `python examples/minimal_closed_mpl_solver.py`
- `python examples/minimal_pressure_closure.py`
- `python examples/minimal_coupled_closure.py`

## Ruff, Black, Diff Check

- `ruff check src tests examples`: passed
- `black --check --no-cache --verbose src tests examples`: passed,
  226 files unchanged
- `git diff --check`: passed

## Production Contract Regression

`tests/network/test_production_component_contract_inspection.py` passed
60 tests. The six known production classes remain `NO_CONTRIBUTE_METHOD`:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation Alignment

`PROJECT_STATUS.md` now states that Block 15F-B integrates explicit configurable
algebraic residual sets into the residual-selection layer through an explicit
user-requested mode. It records that algebraic residuals must be supplied
explicitly, are validated against scenario unknown names only, and do not infer
residuals from roles or topology. It also preserves deferred status for richer
physical residual assembly, production component adapters, property/correlation
/HX-backed closures, rank/solvability analysis, and physically predictive
solves.

## Findings

Critical: none.

Major: none.

Minor fixed:

- `ConfigurableResidualSelectionResult` now rejects direct construction with
  `no_solve=False`.
- `PROJECT_STATUS.md` was updated from stale 15F-A active/status text to the
  final audited 15F-B status.
- Final audit document added.

Minor remaining: none.

## Deferred Items

- Richer configurable physical residual assembly.
- Production component adapters.
- Property/correlation/HX-backed closures.
- Rank and solvability analysis.
- Physically predictive solves.

## Readiness

Block 15F-B is ready to merge.

Merge readiness: yes.
