# Phase 13C Residual Framework Foundation Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 13C adds a deliberately small residual, unknown, and scaling framework
under `mpl_sim.closed_loop`. It represents scalar unknown declarations,
residual specifications, evaluated residuals, scaled residual vectors, norms,
and convergence checks.

It does not implement a solve algorithm, simultaneous energy and pressure
closure, Newton iteration, a generic `solve(network)` API, arbitrary topology,
network graph classes, property lookup, registry resolution, or new physics.

Two findings were corrected during audit. `ResidualEvaluation` now verifies
that its `spec` is a `ResidualSpec`, and `ResidualVector` verifies that every
entry is a `ResidualEvaluation`. Stale user/status text that still assigned
coupled closure to Phase 13C was updated to Phase 13D. No critical or major
finding remains.

## Scope Audited

- branch, history, working tree, and complete Phase 13C file set;
- authoritative README, example, user-guide, roadmap, architecture,
  interface, correlation-contract, schema, decision-log, and prior-audit
  references;
- `src/mpl_sim/closed_loop/residuals.py`;
- `src/mpl_sim/closed_loop/__init__.py`;
- `tests/closed_loop/test_residual_framework.py`;
- Phase 13A and Phase 13B solver diffs and regression suites;
- README, example index/runtime note, user-guide concepts/quickstart/examples,
  and project status.

No architecture document, solver implementation, network implementation,
component implementation, HX model, correlation, property backend, moving
boundary, or validation harness was added or modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-13c-residual-framework-foundation`
- `git status --short --branch`
- `git log --oneline --decorate -10`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- package-directory and changed-file listings

Both `src/mpl_sim/closed_loop` and `tests/closed_loop` contain proper
`__init__.py` files. No accidental `init.py` exists.

Git emitted non-blocking environment warnings for an unreadable user-level
ignore file, an old inaccessible malformed temp path, and line-ending
normalization. These did not affect the diff or validation.

### Validation

Every pytest command used a repository-local base temp. No test was skipped,
xfailed, or deselected.

- `pytest`
  - **3932 passed**
- `pytest tests/correlations`
  - **512 passed**
- `pytest tests/hx_models tests/components`
  - **1896 passed**
- `pytest tests/loops -v`
  - **33 passed**
- `pytest tests/examples -v`
  - **60 passed**
- `pytest tests/closed_loop -v`
  - **281 passed**
- `pytest tests/closed_loop/test_residual_framework.py`
  - **117 passed**
- all five required example scripts completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **156 files would be left unchanged**

Pytest emitted only the pre-existing optional `.pytest_cache` write warning.

## Actual Implementation Summary

The public Phase 13C API is:

- `UnknownSpec`;
- `ResidualSpec`;
- `ResidualEvaluation`;
- `ResidualVector`.

All four are frozen dataclasses and are importable directly from
`mpl_sim.closed_loop`. The implementation contains representation, validation,
scaling, and norm arithmetic only.

Phase 13A `minimal_solver.py` and Phase 13B `pressure_solver.py` are unchanged.

## Public API

Verified public imports:

```python
from mpl_sim.closed_loop import (
    UnknownSpec,
    ResidualSpec,
    ResidualEvaluation,
    ResidualVector,
)
```

The package now exposes 13 names: four Phase 13A names, five Phase 13B names,
and four Phase 13C names.

## Validation Semantics

Verified:

- `UnknownSpec.name` and `.unit` must be non-empty strings;
- optional unknown bounds must be finite and non-bool;
- paired unknown bounds require `lower < upper`;
- `ResidualSpec.name` and `.unit` must be non-empty strings;
- residual scale must be finite, positive, and non-bool;
- `ResidualEvaluation.spec` must be a `ResidualSpec`;
- residual value must be finite and non-bool;
- `ResidualVector` must be non-empty;
- list input is converted to an immutable tuple;
- every vector entry must be a `ResidualEvaluation`;
- duplicate residual names are rejected;
- insertion order is preserved;
- convergence tolerance must be finite, positive, and non-bool.

No required invalid numeric input is silently accepted.

## Residual Scaling Semantics

For every evaluation:

```text
scaled_value = raw value / residual scale
```

`scaled_values()` preserves residual order. `max_abs_scaled()` is the
L-infinity norm, `l2_scaled()` is the Euclidean norm, and
`is_converged(tolerance)` compares the max-absolute scaled norm with an
inclusive tolerance.

The tests and documentation demonstrate:

```text
energy residual   = h_return - h_reference  [J/kg]
pressure residual = pump_head - dP_total    [Pa]
```

They can be placed in one residual vector for representation and scaling only;
no coupled solve is performed.

## Test Coverage

The 117 focused tests cover all 22 requested items, including valid and invalid
unknowns, residual specs, evaluations, vector construction, duplicate names,
ordering, scaling, norms, tolerance boundaries, energy/pressure examples,
combined representation, public exports, architecture exclusions, and Phase
13A/13B regressions.

No focused test is skipped or xfailed, uses broad
`pytest.raises(Exception)`, or relies only on superficial non-null assertions.

## Documentation and Status

README, example documentation/runtime text, user-guide concepts/quickstart/
examples, and project status now distinguish:

- Phase 13C representation/scaling foundation;
- Phase 13D coupled fixed-architecture energy and pressure closure;
- later generic network graph and configurable solving;
- deferred parallel evaporators, valves, manifolds, recuperators,
  pre/post-heaters, moving-boundary work, and validation harness.

No document claims that coupled closure or `solve(network)` is implemented.

## Architecture Boundary Searches

The required searches found no live Phase 13C:

- CoolProp or `PropertyBackend` import/call;
- `CorrelationRegistry` resolution;
- `mpl_sim.network` or `mpl_sim.solvers` import;
- generic `solve(network)` function;
- `Network`, `Node`, `Branch`, or `Junction` class;
- hidden physical defaults matching the requested patterns;
- coupled nonlinear solve, Newton method, or new physics.

Matches elsewhere were existing architecture packages, historical references,
explicit test/example constants, or negative/deferred-feature statements.

## Findings

### Critical Findings

None.

### Major Findings

None remaining.

Resolved during audit:

1. `ResidualEvaluation` accepted an object that was not a `ResidualSpec`,
   contrary to the explicit validation requirement. Runtime validation and a
   focused regression test were added.

### Minor Findings

Resolved during audit:

1. `ResidualVector` did not explicitly reject non-`ResidualEvaluation`
   entries. Runtime validation and a focused regression test were added.
2. README, quickstart, examples, the Phase 13B example note, and project status
   still labeled coupled closure as Phase 13C. They now consistently defer it
   to Phase 13D.
3. The new residual module required one Black formatting pass.

## Deferred Items

- coupled fixed-architecture energy and pressure closure;
- Newton or other multivariable nonlinear solving;
- generic Network topology and configurable solving;
- parallel evaporators and arbitrary branches;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- moving-boundary and quality-marching models;
- automatic phase inference;
- validation harness and pinned experimental/literature data;
- dynamic/transient simulation.

## Phase Classification

Phase 13C is a representation and scaling foundation checkpoint. It adds no
solve algorithm, graph/topology API, or physical model.

## Merge Readiness

`phase-13c-residual-framework-foundation` is approved for merge into `main` as
a checkpoint. This audit does not merge the branch.
