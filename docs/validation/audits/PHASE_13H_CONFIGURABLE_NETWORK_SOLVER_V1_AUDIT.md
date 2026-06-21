# Phase 13H Configurable Network Solver V1 Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 13H adds a minimal configurable algebraic solver over the Phase 13F
declarations and Phase 13G residual-evaluation layer. It updates explicit
unknown values to reduce explicit caller-supplied residual callbacks.

The implementation does not construct physical residuals, execute graph
components, resolve registries, call property backends or correlations, attach
physical state to graph objects, or provide `solve(network)`.

Stale user-facing capability claims, incorrect validation counts, and one broad
test exception assertion were corrected during audit. No critical or major
finding remains.

## Scope Audited

- branch, history, working tree, changed files, and public exports;
- authoritative README, examples index, user guides, roadmap, frozen
  architecture, interface, correlation contract, schema, decision log,
  implementation plan, and Phase 13A-13G audits;
- `src/mpl_sim/network/solver.py`;
- `src/mpl_sim/network/__init__.py`;
- Phase 13F/13G declaration and evaluation dependencies;
- `tests/network/test_configurable_solver_v1.py`;
- Phase 13H documentation and project-status updates;
- architecture-boundary searches across source, tests, examples, and user
  documentation.

No architecture document, component/HX/correlation/property implementation,
closed-loop solver, generic solver core, schema, or validation harness was
modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-13h-configurable-network-solver-v1`
- `git status --short --branch`
- `git log --oneline --decorate -12`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- changed-file and package/test directory listings

The branch began at `602fdff`, the Phase 13G merge on `main`.

No accidental `src/mpl_sim/network/init.py` exists. Architecture documents and
physical implementation layers were unchanged.

### Validation

Pytest used separate repository-local system-temp and base-temp roots. No test
was skipped, xfailed, deselected, or excluded.

- `pytest`
  - **4489 passed**
- `pytest tests/correlations`
  - **512 passed**
- `pytest tests/hx_models tests/components`
  - **1896 passed**
- `pytest tests/loops -v`
  - **33 passed**
- `pytest tests/examples -v`
  - **60 passed**
- `pytest tests/closed_loop -v`
  - **393 passed**
- `pytest tests/network -v`
  - **628 passed**
- `pytest tests/network/test_configurable_solver_v1.py -q -ra`
  - **113 passed**
- all six required example scripts
  - completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **167 files would be left unchanged**
- `git diff --check`
  - clean

Pytest emitted only the known non-blocking warning that the optional
`.pytest_cache` path could not be written. All required temporary-path fixtures
ran and passed.

## Actual Implementation Summary

The phase adds:

- `NetworkSolveConfig`;
- `NetworkSolveResult`;
- `solve_network_residual_problem`.

The solve entry point accepts a `NetworkResidualAssembly`, initial
`NetworkUnknownValues` or mapping, explicit `NetworkResidualEvaluator`
callbacks, explicit residual scales, and explicit solver configuration. Every
initial, perturbed, and updated residual evaluation is delegated to
`evaluate_network_residuals`.

## Public API

Verified:

```python
from mpl_sim.network import (
    NetworkSolveConfig,
    NetworkSolveResult,
    solve_network_residual_problem,
)
```

All three names are in `mpl_sim.network.__all__`. Existing Phase 7 and Phase
13E/13F/13G exports remain available. `NetworkGraph` has no `solve` method, and
there is no public `solve(network)` or physical simulator API.

## Solver Method

The numerical method is a bounded damped forward finite-difference Newton
iteration:

1. evaluate the initial residual vector through Phase 13G;
2. require equal unknown and residual counts;
3. build an `n x n` forward-difference Jacobian;
4. solve `J dx = -r` with internal Gaussian elimination and partial pivoting;
5. apply `x_new = x + damping * dx`;
6. evaluate the updated residuals through Phase 13G;
7. converge only when `max_abs_scaled <= tolerance`;
8. stop after the explicit maximum iteration count.

There is no SciPy, NumPy root finder, black-box optimizer, fallback solver, or
unbounded loop.

## Configuration Validation

`NetworkSolveConfig` is frozen and validates:

- `max_iterations` is a non-bool integer greater than or equal to one;
- `tolerance` is finite, positive, numeric, and non-bool;
- `finite_difference_step` is finite, positive, numeric, and non-bool;
- `damping` is finite, numeric, non-bool, and in `(0, 1]`;
- `record_history` is a bool.

Focused tests cover zero, negative, NaN, infinity, Boolean, wrong-type, and
boundary cases.

## Solve Semantics

- caller inputs are not mutated;
- assembly declaration order defines vector order;
- callbacks and scales remain explicit;
- only square systems are iterated;
- an initially converged guess returns zero iterations;
- convergence is claimed only when the final Phase 13G scaled norm satisfies
  the configured tolerance;
- optional history is returned as an immutable tuple;
- no values are attached to a graph, node, or component instance.

## Failure Semantics

- unknown/evaluator/scale mismatches retain Phase 13G validation behavior;
- callback exceptions propagate unchanged;
- non-square systems return `converged=False` with a descriptive reason;
- a singular or near-singular Jacobian returns `converged=False`;
- non-finite updates return `converged=False`;
- iteration exhaustion returns `converged=False`;
- no failure path silently reports success.

## Result Diagnostics

`NetworkSolveResult` is frozen and exposes:

- final unknown values;
- final `NetworkResidualEvaluationResult`;
- initial evaluation;
- convergence flag;
- iteration count;
- status reason;
- optional immutable residual-norm history.

The result makes no physical-validation or physical-network-simulation claim.

## Relationship to Phase 13G Evaluation

The solver imports and calls `evaluate_network_residuals` for the initial
state, every finite-difference perturbation, and every accepted update. It uses
`NetworkUnknownValues`, `NetworkResidualEvaluator`, explicit scales, and the
Phase 13G result object directly. It does not duplicate callback validation or
construct a second residual-evaluation path.

## Test Coverage

The 113 focused tests cover the requested configuration, 1D/2D solve,
analytical solution, convergence, non-convergence, singularity, mismatch,
exception, immutability, public export, regression, architecture-boundary, and
documentation assertions.

No Phase 13H test is skipped or xfailed. The one broad
`pytest.raises(Exception)` assertion was replaced with
`FrozenInstanceError`.

## Documentation and Status

README, quickstart, concepts, examples guide, examples index, and project
status now consistently distinguish:

- implemented Phase 13H callback-only algebraic solving;
- explicit residual callbacks and scales;
- no automatic physical residual construction;
- no component execution or property lookup;
- no physical state on graph nodes;
- no arbitrary-topology physical MPL simulation;
- no experimental validation.

Final counts are 113 focused tests, 628 network tests, and 4489 full-suite
tests.

## Architecture Boundary Searches

Required searches covered CoolProp, `PropertyBackend`,
`CorrelationRegistry`, `solve(network)`, SciPy root APIs, physical state/value
terms, `contribute(`, deferred component families, and validation claims.

Matches in Phase 13H source/tests/docs are negative boundary statements or
tests asserting absence. No prohibited production import or call was found.
The graph, assembly, and evaluation types do not depend on the solver and do
not expose solve methods. The Phase 13H entry point is an algebraic adapter
over explicit declarations/callbacks, not the architecture-level physical
Network/Component/SystemState solver.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

Resolved during audit:

1. README, quickstart, examples guide, and examples index still described
   configurable network solving as deferred. They now describe the Phase 13H
   callback-only solver while keeping physical network simulation deferred.
2. Project status reported 4429 passing tests and claimed five Windows fixture
   errors were excluded. Complete validation with separate local temp roots
   passed all 4489 tests, and status now records the no-exclusion result.
3. One frozen-dataclass test used broad `pytest.raises(Exception)`. It now
   asserts `FrozenInstanceError`.

## Deferred Items

- automatic physical residual construction from components;
- architecture-level Component contribution and SystemState assembly;
- property-backed physical network evaluation;
- arbitrary-topology and parallel-branch simulation;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- adaptive/relative finite-difference steps and advanced globalization;
- moving-boundary modeling;
- validation harnesses and experimental/literature comparison.

## Phase Classification

Phase 13H is a callback-only algebraic solve checkpoint. It solves an explicit
mathematical residual problem but does not simulate or validate a physical MPL
network.

## Merge Readiness

`phase-13h-configurable-network-solver-v1` is approved for merge into `main` as
a checkpoint after the implementation and audit commits are created and
pushed. This audit does not authorize or perform the merge.
