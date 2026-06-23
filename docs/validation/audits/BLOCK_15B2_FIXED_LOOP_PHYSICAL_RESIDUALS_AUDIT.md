# Block 15B.2 Fixed-Loop Physical Residuals Audit

## Verdict

Approved with minor fixes.

Block 15B.2 adds a narrow fixed single-loop physical residual assembly layer. It
does not implement arbitrary-topology simulation, production component execution,
generic graph solving, SystemState assembly, FluidState construction,
property/correlation/HX execution, or a generic `solve(network)` API.

## Branch And Commits

- Branch audited: `phase-15b2-fixed-loop-physical-residuals`
- Base commit: `555b21e` (`Merge branch 'phase-15b1-fixed-single-loop-scenario'`)
- HEAD before audit: `555b21e`
- Worktree payload before audit: uncommitted Block 15B.2 source, tests, and roadmap edits

## Scope Audited

Changed files audited:

- `src/mpl_sim/network/fixed_single_loop_residuals.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_fixed_single_loop_residuals.py`
- `docs/roadmap/PROJECT_STATUS.md`

Audit-created file:

- `docs/validation/audits/BLOCK_15B2_FIXED_LOOP_PHYSICAL_RESIDUALS_AUDIT.md`

No frozen architecture document was modified.

## Public API Added

Exported from `mpl_sim.network`:

- `FixedSingleLoopResidualParameters`
- `FixedSingleLoopPhysicalResidualAssembly`
- `build_fixed_single_loop_physical_residuals`
- `build_component_contribution_from_fixed_single_loop_residuals`

## Source/API Review

`FixedSingleLoopResidualParameters` is a frozen dataclass with four required
explicit scalar numeric parameters:

- `pump_pressure_rise`
- `evaporator_pressure_drop`
- `condenser_pressure_drop`
- `accumulator_pressure_reference`

It rejects bool, non-numeric values, NaN, and infinities. Values are stored as
float. Signs are intentionally not constrained in this MVP; the parameters are
explicit signed algebraic inputs, not pressure-drop laws or pump curves.

`FixedSingleLoopPhysicalResidualAssembly` is frozen and stores only the 15B.1
scenario, explicit parameters, a `ContributionResidualMap`, a
`ComponentContributionAdapterSet`, and optional defensively copied metadata. It
does not store SystemState, FluidState, property backends, production component
objects, or HX/correlation objects.

`build_fixed_single_loop_physical_residuals(...)` accepts only
`FixedSingleLoopScenario` plus `FixedSingleLoopResidualParameters`, creates fixed
residual mappings and four fixed component adapters, and uses only explicit
unknown/residual names from the scenario. Exact component coverage and declared
residual coverage are enforced by the existing Phase 14C/14A adapter path during
evaluation.

The convenience wrapper calls the explicit adapter callback for one fixed-loop
component and returns a Phase 14C `ComponentContribution`. It does not execute
production components or call any `contribute(...)` method.

## Residual Equations And Sign Convention

The implemented residual equations are:

```text
mass_balance:n_cond_out = mdot_condenser - mdot_accumulator
mass_balance:n_acc_out = mdot_accumulator - mdot_pump
mass_balance:n_pump_out = mdot_pump - mdot_evaporator
mass_balance:n_evap_out = mdot_evaporator - mdot_condenser

pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference
pressure_drop:pump = P_n_pump_out - P_n_acc_out - pump_pressure_rise
pressure_drop:evaporator = P_n_evap_out - P_n_pump_out + evaporator_pressure_drop
pressure_drop:condenser = P_n_cond_out - P_n_evap_out + condenser_pressure_drop
```

Positive conventional `pump_pressure_rise` means pump outlet pressure exceeds
pump inlet pressure. Positive conventional evaporator/condenser pressure drops
mean inlet pressure exceeds outlet pressure. The accumulator pressure residual is
a trivial reference-pressure anchor.

Tests verify zero residuals at a consistent point, nonzero off-solution
residuals, parameter sensitivity for pump rise and pressure drops, mass-flow
mismatch behavior, and residual ordering matching the 15B.1 scenario
declaration. No pump curve, pressure-drop law, heat-transfer law, accumulator
law, property lookup, correlation, or HX model is implemented.

## Fixed-Scenario-Only Review

The implementation consumes `FixedSingleLoopScenario` and hard-codes the fixed
15B.1 residual attribution. It does not inspect `component_type`, does not loop
over arbitrary graph topology to infer equations, does not accept arbitrary
networks, and does not add `solve(network)` or `NetworkGraph.solve()`.

## Validation Results

Commands run:

```powershell
Remove-Item -Recurse -Force .pytest_tmp -ErrorAction SilentlyContinue
pytest tests/network/test_fixed_single_loop_residuals.py -q --basetemp=.pytest_tmp

Remove-Item -Recurse -Force .pytest_tmp -ErrorAction SilentlyContinue
pytest tests/network/test_fixed_single_loop_scenario.py -q --basetemp=.pytest_tmp

Remove-Item -Recurse -Force .pytest_tmp -ErrorAction SilentlyContinue
pytest tests/network/test_production_bridge_closeout_integration.py -q --basetemp=.pytest_tmp

Remove-Item -Recurse -Force .pytest_tmp -ErrorAction SilentlyContinue
pytest tests/network -q --basetemp=.pytest_tmp

Remove-Item -Recurse -Force .pytest_tmp -ErrorAction SilentlyContinue
pytest -q --basetemp=.pytest_tmp

ruff check src tests examples
black --check --no-cache --verbose src tests examples
git diff --check
```

Exact results:

- Block 15B.2 focused tests: 102 passed
- Block 15B.1 scenario regression: 84 passed
- Block 15A.4 closeout regression: 38 passed
- Network suite: 1604 passed
- Full suite: 5465 passed
- Skipped/xfailed/deselected: none observed
- Pytest warning: cache write warning for `.pytest_cache` due Windows permission; tests passed
- Ruff: passed
- Black: passed; 192 files would be left unchanged
- Diff check: passed

Six examples run successfully:

- `python examples/minimal_evaporator_condenser_loop.py`
- `python examples/fixed_heat_rate_hx.py`
- `python examples/segmented_counterflow_hx.py`
- `python examples/minimal_closed_mpl_solver.py`
- `python examples/minimal_pressure_closure.py`
- `python examples/minimal_coupled_closure.py`

## Boundary Searches

Searches run:

```powershell
rg -n "CoolProp|PropertyBackend|CorrelationRegistry" src/mpl_sim/network tests/network docs/roadmap/PROJECT_STATUS.md
rg -n "contribute\(" src/mpl_sim/network tests/network src/mpl_sim/components
rg -n "\.contribute\(" src/mpl_sim/network tests/network src/mpl_sim/components
rg -n "def contribute" src/mpl_sim/components src/mpl_sim/network
rg -n "SystemState|FluidState" src/mpl_sim/network/fixed_single_loop_residuals.py tests/network/test_fixed_single_loop_residuals.py
rg -n "component_type" src/mpl_sim/network/fixed_single_loop_residuals.py tests/network/test_fixed_single_loop_residuals.py
rg -n "def solve|solve\(network|NetworkGraph\.solve" src/mpl_sim/network tests/network
rg -n "mpl_sim\.properties|mpl_sim\.components|mpl_sim\.correlations|mpl_sim\.hx_models" src/mpl_sim/network/fixed_single_loop_residuals.py
rg -n "Pipe|PumpComponent|AccumulatorComponent|EvaporatorComponent|CondenserComponent" src/mpl_sim/network/fixed_single_loop_residuals.py tests/network/test_fixed_single_loop_residuals.py
rg -n "arbitrary|generic topology|topology builder|component_type.*if|if .*component_type" src/mpl_sim/network/fixed_single_loop_residuals.py tests/network/test_fixed_single_loop_residuals.py
```

Classification:

- `CoolProp`, `PropertyBackend`, `CorrelationRegistry`: documentation negative
  statements and test negative assertions only in the audited files; no
  executable prohibited use.
- `contribute(` and `.contribute(`: documentation negative statements, test
  negative assertions, and pre-existing production contract inspection fixtures;
  no new executable call or production method.
- `def contribute`: only pre-existing test fixtures for inspection; no
  production class or network implementation defines it.
- `SystemState` / `FluidState`: documentation negative statements and test
  negative assertions only in 15B.2 files.
- `component_type`: one negative statement only in the 15B.2 module.
- `def solve|solve(network)|NetworkGraph.solve`: pre-existing
  `solve_network_residual_problem` is present; 15B.2 adds only negative
  statements and tests, no generic network solve API.
- `mpl_sim.properties|mpl_sim.components|mpl_sim.correlations|mpl_sim.hx_models`
  in `fixed_single_loop_residuals.py`: negative boundary docstring only.
- Production component class names in 15B.2 files: test contract-status
  assertions only.
- Arbitrary/generic topology patterns: negative statements only.

No prohibited executable hit was found.

## Production Contract Regression

`tests/network/test_fixed_single_loop_residuals.py` verifies that all six known
production classes still report `NO_CONTRIBUTE_METHOD`:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

The focused 15B.2 suite passed.

## Documentation Alignment

`docs/roadmap/PROJECT_STATUS.md` now states that Block 15B.2 is fixed-loop
physical residual assembly, uses explicit parameterized algebraic residuals for
the 15B.1 scenario, and does not execute production components, assemble
SystemState, create FluidState, call properties/correlations/HX models,
implement arbitrary topology, or add generic network solve APIs.

Minor audit corrections made:

- Clarified parameter sign wording in `fixed_single_loop_residuals.py` so it
  matches tested signed-algebraic MVP behavior.
- Updated stale roadmap text that still described Block 15B.1 as the active
  phase and moved next action to Block 15B.3.

## Findings

Critical findings: none.

Major findings: none.

Minor findings fixed:

- Parameter sign wording implied positivity while tests intentionally allow
  signed algebraic parameters.
- Later roadmap section still described Block 15B.1 as active and Block 15B.2 as
  future work.

Minor findings remaining: none.

## Deferred Items

- Block 15B.3 remains responsible for any minimal fixed-loop solve/evaluate/report
  helper.
- Arbitrary-topology physical simulation remains deferred.
- Production `Component.contribute(...)`, SystemState assembly, FluidState
  construction, property-backed residuals, correlation-backed residuals, and HX
  model-backed residuals remain deferred.

## Readiness

Block 15B.2 is ready.

Merge readiness: yes, after this audit document and roadmap reference are
committed and the branch is pushed.
