# Phase 13B Pressure Closure Foundation Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 13B adds a deliberately narrow, fixed-architecture pressure-closure
routine under `mpl_sim.closed_loop`. It solves the scalar residual:

```text
pump_head(primary_mdot) - dP_total(primary_mdot) = 0
dP_total = dP_evap + dP_cond
```

The implementation is pressure-only Option A. The energy residual
`h_return - h_reference` remains a first-class diagnostic and is not solved.

One major acceptance defect was found and corrected during audit. The original
case held scenario mass flux `G` fixed, so changing `primary_mdot` did not make
the HX pressure drops flow-dependent. The approved API now requires explicit
evaporator and condenser flow areas, sets each trial `G = primary_mdot / A`,
and requires an explicit `dp_primary` closure for both HX scenarios. The
deterministic acceptance case therefore balances a nonzero, flow-dependent
loop pressure drop rather than merely finding the zero of a pump curve.

No critical or major finding remains.

## Scope Audited

- branch, history, working tree, and complete Phase 13B file set;
- authoritative architecture, interface, correlation, schema, decision-log,
  implementation-plan, and Phase 11U/12A/12B/13A audit references;
- `src/mpl_sim/closed_loop/_scalar_solve.py`;
- `src/mpl_sim/closed_loop/minimal_solver.py`;
- `src/mpl_sim/closed_loop/pressure_solver.py`;
- `src/mpl_sim/closed_loop/__init__.py`;
- `tests/closed_loop/test_minimal_pressure_closure.py`;
- `tests/examples/test_examples.py`;
- `examples/minimal_pressure_closure.py`;
- README, example index, user-guide examples/quickstart/concepts, and project
  status.

No architecture document, HX physics implementation, component
implementation, correlation implementation, network solver, generic solver
framework, moving-boundary model, or validation harness was added or modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-13b-pressure-closure-foundation`
- `git status --short --branch`
- `git log --oneline --decorate -10`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- changed-file and package-file listings

Git emitted non-blocking environment warnings for an unreadable user-level
ignore file and an old malformed temp-directory path. Neither affected the
tracked diff or validation.

### Validation

Every pytest command used a fresh repository-local base temp under
`.pytest_tmp_phase13b_final`. No test was deselected.

- `pytest`
  - **3815 passed**
  - no skips, xfails, or deselections
- `pytest tests/correlations`
  - **512 passed**
- `pytest tests/hx_models tests/components`
  - **1896 passed**
- `pytest tests/loops -v`
  - **33 passed**
- `pytest tests/examples -v`
  - **60 passed**
- `pytest tests/closed_loop -v`
  - **164 passed**
- all five required example scripts completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **154 files would be left unchanged**

Pytest emitted only the pre-existing optional `.pytest_cache` write warning.
The local `tmp_path` fixtures all ran and passed.

## Actual Implementation Summary

The public Phase 13B API is:

- `PumpHeadCurve`;
- `PressureClosureConfig`;
- `MinimalPressureClosureCase`;
- `MinimalPressureClosureResult`;
- `solve_minimal_pressure_closure`.

The case accepts exactly one reference state, one evaporator component and
scenario, one condenser component and scenario, one explicit pump-head curve,
two explicit primary flow areas, and one caller-supplied mass-flow bracket.
It has no graph, Network, topology, valve, junction, or arbitrary component
collection input.

The private `_bisect_bounded` helper is shared with Phase 13A but is not
exported. Phase 13A behavior remains unchanged.

## Pressure Closure Formulation

For every trial `primary_mdot`:

1. set evaporator mass flux to `primary_mdot / evap_flow_area`;
2. evaluate the evaporator from the explicit reference state;
3. set condenser mass flux to `primary_mdot / cond_flow_area`;
4. evaluate the condenser from the evaporator outlet state;
5. compute `dP_total = dP_evap + dP_cond`;
6. compute `pressure_residual = pump_head(primary_mdot) - dP_total`.

The solver never overwrites component pressure-drop outputs. Pressure closure
is obtained only through repeated component/HX evaluations.

## Pump-Head Law

`PumpHeadCurve` is a frozen explicit value object:

```text
pump_head(mdot) = head_Pa - slope_Pa_s_kg * mdot
```

It supports constant head when the slope is zero. Both parameters must be
finite. There is no hidden pump curve, mass-flow guess, property lookup, or
registry resolution. Pump head at the returned solution is reported.

## Solver Algorithm and Configuration

Verified:

- finite caller-supplied mass-flow bounds;
- strict positive lower bound and `lower < upper`;
- startup sign-change validation;
- exact roots at either endpoint;
- no invented bracket or hidden initial guess;
- non-bool integer `max_iter >= 1`;
- finite positive pressure tolerance;
- bounded bisection only;
- explicit `converged=False` on iteration exhaustion;
- component exceptions propagate;
- iteration count and complete loop-evaluation count are reported.

The two endpoint evaluations are included in `evaluations`. Endpoint roots
return `iterations=0` and `evaluations=2`.

## Pressure Closure Semantics

The approved deterministic case uses explicit linear mass-flux pressure-drop
closures:

```text
dP_evap = 100 * (mdot / 0.01)
dP_cond =  50 * (mdot / 0.02)
dP_total = 12500 * mdot
pump_head = 5625 - 100000 * mdot
```

The analytical root is exactly `primary_mdot = 0.05 kg/s`. At the numerical
solution, pump head is approximately `625 Pa`, total loop pressure drop is
approximately `625 Pa`, and the pressure residual is within `0.01 Pa`.

The fixed heat rates remain intentionally unbalanced, so the returned energy
residual is approximately `+4000 J/kg`. This confirms that Phase 13B does not
claim simultaneous energy and pressure closure.

## Result Diagnostics

`MinimalPressureClosureResult` is a frozen dataclass exposing:

- `converged`;
- `iterations`;
- `evaluations`;
- `pressure_residual`;
- `solved_primary_mdot`;
- pump head at the solution;
- `dP_evap`, `dP_cond`, and `dP_total`;
- evaporator and condenser `HXSolveResult` objects;
- reference, post-evaporator, and return states;
- reference and return enthalpy;
- diagnostic `energy_residual`;
- non-`IN_ENVELOPE` warnings.

## Example and Documentation

The Phase 13B example:

- imports only public `mpl_sim.*` APIs;
- performs no solve on import;
- runs as a standalone script;
- writes no files;
- requires no external data, internet, CoolProp call, property lookup, or
  registry resolution;
- prints solved mass flow, pump head, component and total pressure drops,
  pressure residual, energy diagnostic, convergence, iterations, and
  evaluations;
- states the fixed architecture and deferred generic topology, simultaneous
  closure, additional components, moving-boundary work, and validation.

README, quickstart, examples guide, example index, and project status describe
Phase 13B as pressure-only fixed-architecture closure and do not overclaim a
generic network solver or validated physical model.

## Test Coverage

The focused Phase 13B tests cover:

- deterministic nonzero pressure closure and analytical mass flow;
- pressure residual sign convention and tolerance;
- exact `dP_total = dP_evap + dP_cond`;
- trial mass-flux dependence on explicit component flow areas;
- pump-head reporting;
- diagnostic nonzero energy residual;
- same-sign bracket rejection;
- both endpoint-root cases;
- explicit non-convergence;
- all requested invalid solver configurations;
- invalid mass-flow bounds and flow areas;
- missing evaporator or condenser DP closure;
- property-lookup and registry-resolution absence;
- no generic network API;
- public exports and frozen result/config objects;
- example import safety, execution, diagnostics, and no-file-write behavior;
- Phase 13A regression after the private bisection refactor.

No focused Phase 13B test is skipped or xfailed, uses broad
`pytest.raises(Exception)`, or requires test deselection.

## Architecture Boundary Searches

The required searches found no live Phase 13B:

- CoolProp or `PropertyBackend` import/call;
- `CorrelationRegistry` resolution;
- `mpl_sim.network` or `mpl_sim.solvers` import;
- generic `solve(network)` API;
- hidden physical default matching the requested magic-number patterns;
- false arbitrary-topology, simultaneous-closure, validation, or
  full-loop-convergence claim.

Matches were existing package implementations, explicit test/example inputs,
historical architecture text, or negative/deferred-feature statements.

## Findings

### Critical Findings

None.

### Major Findings

None remaining.

Resolved during audit:

1. The original acceptance case kept `geom_scalars["G"]` fixed while solving
   for `primary_mdot`; therefore HX pressure drop was not genuinely a function
   of the solved mass flow. The case now requires explicit component flow
   areas, derives trial `G = mdot/A`, requires both DP closures, and tests a
   nonzero analytical pressure balance.

### Minor Findings

Resolved during audit:

1. The result reported bisection iterations but not complete component
   evaluation count. `evaluations` is now explicit and tested.
2. Documentation and representative output still described the zero-DP
   acceptance case. They now show the nonzero loop-loss balance and explicit
   flow-area/DP requirements.

## Deferred Items

- simultaneous energy and pressure closure;
- generic Network topology and parallel components;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- full pump-component/network integration;
- moving-boundary and quality-marching models;
- automatic phase inference;
- validation harness and pinned experimental/literature data;
- dynamic/transient simulation.

## Phase Classification

Phase 13B is a minimal fixed-architecture, one-variable pressure-closure
acceptance checkpoint. It reuses existing HX/component/correlation behavior
and adds no new production heat-transfer or pressure-drop physics.

## Merge Readiness

`phase-13b-pressure-closure-foundation` is approved for merge into `main` as a
checkpoint. This audit does not merge the branch.
