# Phase 13A Minimal Closed MPL Solver Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 13A adds a deliberately narrow, fixed-architecture energy-closure
routine under `mpl_sim.closed_loop`. It evaluates one evaporator once, varies
only the condenser `FixedHeatRate.Q`, and uses bounded bisection to solve:

```text
h_return - h_reference = 0
```

The implementation is not a generic `solve(network)` API, arbitrary-topology
solver, pressure-network solver, validation harness, moving-boundary model, or
new-physics phase. Pressure drop is accumulated only as the `dP_total`
diagnostic.

One solver correctness defect and stale documentation/status claims were
corrected during audit. Full validation then passed with no skipped, xfailed,
or deselected tests. No critical or major finding remains.

## Scope Audited

- repository branch, history, working tree, and complete Phase 13A diff;
- authoritative architecture, interface, correlation, schema, decision-log,
  implementation-plan, and Phase 11U/12A/12B audit references;
- `src/mpl_sim/closed_loop/__init__.py`;
- `src/mpl_sim/closed_loop/minimal_solver.py`;
- `tests/closed_loop/__init__.py`;
- `tests/closed_loop/test_minimal_closed_mpl_solver.py`;
- `tests/examples/test_examples.py`;
- `examples/minimal_closed_mpl_solver.py`;
- README, example index, user-guide examples/quickstart/concepts, and project
  status.

No architecture document was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-13a-minimal-closed-mpl-solver`
- `git status --short --branch`
- `git log --oneline --decorate -10`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- package-directory listings for `src/mpl_sim/closed_loop` and
  `tests/closed_loop`

Both packages contain proper `__init__.py` files. No accidental `init.py`
exists.

Git emitted non-blocking environment warnings for the unreadable user-level
ignore file and an old inaccessible generated temp directory. Neither warning
changed the tracked diff or validation result.

### Validation

- `pytest`
  - **3722 passed**
  - no skips, xfails, or deselections
  - all four `TestExamplesDoNotWriteFiles` tests ran and passed
- `pytest tests/correlations`
  - **512 passed**
- `pytest tests/hx_models tests/components`
  - **1896 passed**
- `pytest tests/loops -v`
  - **33 passed**
- `pytest tests/examples -v`
  - **46 passed**
- `pytest tests/closed_loop -v`
  - **85 passed**
- all four example scripts completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **150 files would be left unchanged**

Pytest reported only an optional cache-write warning in the execution
environment. Normal `tmp_path` fixtures worked; no local-temp workaround or
test deselection was required.

## Actual Implementation Summary

The public package exports exactly:

- `ClosedLoopSolveConfig`;
- `MinimalClosedMPLCase`;
- `MinimalClosedMPLResult`;
- `solve_minimal_closed_mpl`.

`MinimalClosedMPLCase` accepts explicit reference state, primary mass flow,
evaporator/component scenario, condenser/component scenario, and condenser
heat-rate bracket. It has no Network or arbitrary graph input.

The routine orchestrates existing public component, core, correlation, and HX
model APIs. It imports no `mpl_sim.network`, `mpl_sim.solvers`, or
`mpl_sim.properties` module and resolves no registry.

This package is classified as a fixed case-specific orchestration helper. It
does not alter or replace the architecture's generic, physics-free Solver
under `mpl_sim.solvers`.

## Solver Formulation

1. Evaluate the evaporator once from the explicit reference state and mass
   flow.
2. Pass that exact outlet `FluidState` object to every condenser evaluation.
3. Replace only the condenser scenario's `FixedHeatRate.Q`.
4. Compute the residual as `h_return - h_reference` in J/kg.
5. Bisect the explicit caller-supplied condenser heat-rate bracket.

For the deterministic fixed-heat-rate acceptance case, the analytical root is
`Q_cond = -Q_evap`. The returned state reaches the reference enthalpy within
the configured tolerance without overwriting the state directly.

## Solver Algorithm and Configuration

Verified:

- finite caller-supplied bracket bounds;
- strict `lo < hi`;
- startup sign-change validation;
- exact roots at either bracket endpoint accepted explicitly;
- no fallback bracket or hidden physical default;
- `max_iter` is a non-bool integer greater than or equal to one;
- tolerance is finite and strictly positive;
- bounded iteration only;
- deterministic behavior;
- explicit `converged=False` and residual diagnostics on non-convergence;
- component/HX exceptions are not swallowed.

`iterations` counts midpoint bisection evaluations and is zero when an exact
endpoint root is returned. The two startup endpoint evaluations are documented
as outside that count.

## Energy Closure Semantics

Verified:

- reference state and primary mass flow are explicit;
- evaporator heat input is supplied by its scenario;
- condenser heat removal is the sole solved scalar;
- `energy_residual = residual = net_dh = h_return - h_reference`;
- `net_Q = Q_evap + Q_cond`;
- `dP_total = dP_evap + dP_cond`;
- pressure closure and pressure residual are not fabricated;
- Phase 11/12 heat-rate sign conventions are preserved.

## Result Diagnostics

`MinimalClosedMPLResult` is a frozen dataclass exposing:

- convergence flag and bisection iteration count;
- final residual and named energy residual;
- solved condenser heat rate;
- evaporator and condenser `HXSolveResult` objects;
- reference, post-evaporator, and return states;
- enthalpy checkpoints;
- `net_Q`, `net_dh`, and diagnostic `dP_total`;
- non-`IN_ENVELOPE` warning messages.

The result does not expose a pressure residual or imply pressure closure.

## Example and Documentation

The Phase 13A example:

- imports only public `mpl_sim.*` package APIs;
- performs no solve on import;
- runs as a standalone script;
- writes no files;
- requires no internet, external data, CoolProp call, or property lookup;
- prints evaporator and solved condenser heat rates, final enthalpy, energy
  residual, convergence, iteration count, and pressure-drop diagnostic;
- explicitly states the fixed architecture and deferred generic topology,
  pressure closure, extra components, and validation.

README, user-guide, example-index, concepts, and project-status text now
distinguish the implemented minimal energy closure from deferred generic
network and pressure closure.

## Test Coverage

The 85 focused closed-loop tests cover:

- deterministic energy closure and analytical condenser heat rate;
- final enthalpy and residual tolerance;
- convergence and non-convergence diagnostics;
- invalid brackets and both exact endpoint-root cases;
- all required invalid configuration values;
- direct observation that the evaporator is evaluated once and its exact
  outlet object feeds every condenser evaluation;
- energy and pressure diagnostics;
- missing/invalid inputs;
- property-lookup and registry-resolution absence;
- no generic network API;
- public package exports and frozen dataclasses.

The 46 example tests include import safety, standalone execution, public API
imports, expected diagnostics, external-dependency checks, and all four
runtime no-file-write checks.

No focused Phase 13A test is skipped or xfailed, uses
`pytest.raises(Exception)`, or relies on private framework imports for the
public behavior under test.

## Architecture Boundary Searches

Required searches found no live Phase 13A:

- CoolProp or `PropertyBackend` import/call;
- `CorrelationRegistry` resolution;
- `mpl_sim.network` or `mpl_sim.solvers` import;
- generic `solve(network)` API;
- hidden physical default matching the requested magic-number patterns;
- false arbitrary-topology, pressure-closure, or validation claim.

Matches outside the Phase 13A path were established package implementations,
explicit test inputs, historical documentation, or negative/deferred-feature
statements.

## Findings

### Critical Findings

None.

### Major Findings

None remaining.

Resolved during audit:

1. A valid root exactly at either bracket endpoint passed startup validation
   but was discarded by the midpoint loop. The solver now returns endpoint
   roots explicitly, with focused lower- and upper-endpoint tests.
2. README, concepts, quickstart, and project status still claimed that all
   loop energy closure was deferred or reported the deselected-test result.
   They now describe the narrow Phase 13A capability and the complete
   no-deselection validation result.

### Minor Findings

Resolved during audit:

1. The closed-loop implementation imported framework types through internal
   module paths. It now consumes the existing public package APIs.
2. The original handoff tests inferred condenser input from arithmetic. A
   recording-model test now observes the exact object passed to every
   condenser evaluation and verifies the evaporator runs once.

## Deferred Items

- pressure closure and pump-head balancing;
- arbitrary Network topology and parallel components;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- frozen `contribute(trial, ctx)` integration for HX components;
- moving-boundary and quality-marching models;
- automatic phase inference;
- validation harness and pinned experimental/literature data;
- additional HTC and DP closures;
- dynamic/transient simulation.

## Phase Classification

Phase 13A is a minimal fixed-architecture, one-variable energy-closure
acceptance checkpoint. It reuses existing HX/component behavior and adds no new
heat-transfer, pressure-drop, property, topology, or moving-boundary physics.

## Merge Readiness

`phase-13a-minimal-closed-mpl-solver` is approved for merge into `main` as a
checkpoint after the implementation and audit commits are created and pushed.
This audit does not authorize or perform the merge.
