# Phase 13G Network Residual Evaluation Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 13G adds a one-shot residual-evaluation layer over the Phase 13F
`NetworkResidualAssembly`. It accepts explicit unknown values, explicit named
callbacks, and explicit residual scales, then creates Phase 13C
`ResidualEvaluation` and `ResidualVector` objects in assembly declaration
order.

The phase does not solve or iterate the network, adjust unknowns, execute
components, resolve registries, call property backends or correlations, attach
physical state to graph objects, or add `solve(network)`.

One immutability defect and stale user-facing phase statements were corrected
during audit. No critical or major finding remains.

## Scope Audited

- branch, history, working tree, and complete Phase 13G change set;
- authoritative README, examples index, user guides, roadmap, frozen
  architecture, interface, correlation contract, schema, decision log,
  implementation plan, and Phase 13A-13F audits;
- `src/mpl_sim/network/residual_evaluation.py`;
- `src/mpl_sim/network/__init__.py`;
- `tests/network/test_residual_evaluation_foundation.py`;
- Phase 13G concepts, quickstart, examples-guide, README, and project-status
  updates;
- architecture-boundary searches across network, closed-loop, examples, user
  documentation, and tests.

No architecture document, closed-loop solver, component/HX/correlation
implementation, property backend, generic solver, schema, or validation
harness was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-13g-network-residual-evaluation`
- `git status --short --branch`
- `git log --oneline --decorate -10`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- package and test directory listings

The branch began at `7b27d83`, the Phase 13F merge on `main`.

No accidental `src/mpl_sim/network/init.py` exists. Package exports are in
`src/mpl_sim/network/__init__.py`.

### Validation

All pytest runs used repository-local base-temp directories. No tests were
skipped, xfailed, or deselected.

- `pytest`
  - **4376 passed**
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
  - **515 passed**
- `pytest tests/network/test_residual_evaluation_foundation.py -q -ra`
  - **95 passed**
- all six required example scripts
  - completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **165 files would be left unchanged**
- `git diff --check`
  - clean

Pytest emitted only the known non-blocking warning that the optional
`.pytest_cache` path could not be written in the execution environment.
Repository-local `tmp_path` and base-temp use completed successfully.

## Actual Implementation Summary

The phase adds:

- `NetworkUnknownValues`;
- `NetworkResidualEvaluator`;
- `NetworkResidualEvaluationResult`;
- `evaluate_network_residuals`.

The evaluation function validates all inputs before invoking callbacks, maps
evaluators by residual name, invokes each declared callback exactly once in
assembly order, constructs a `ResidualSpec` and `ResidualEvaluation` for each
return value, wraps the evaluations in a `ResidualVector`, and returns the
vector and its scaled diagnostics.

## Public API

Verified:

```python
from mpl_sim.network import (
    NetworkUnknownValues,
    NetworkResidualEvaluator,
    NetworkResidualEvaluationResult,
    evaluate_network_residuals,
)
```

All four names are present in `mpl_sim.network.__all__`. Existing Phase 7,
13E, and 13F exports remain available. No Phase 13G `solve`, `Solver`,
optimizer, component executor, physics object, or property-backed object is
exported.

## Unknown Value Semantics

Verified:

- `NetworkUnknownValues` is a frozen dataclass;
- input mappings are defensively copied into a new `MappingProxyType`;
- mutation of either a source dict or a source mapping proxy cannot change
  stored values;
- keys must be non-empty, non-whitespace strings;
- values must be finite non-bool `int` or `float` values;
- strings, booleans, NaN, and infinities are rejected;
- assembly matching rejects missing and extra unknown names;
- values are not attached to `NetworkGraph`, `GraphNode`, or
  `ComponentInstance`.

## Evaluator and Callback Semantics

Verified:

- `NetworkResidualEvaluator` is a frozen `(name, callback)` pair;
- names must be non-empty, non-whitespace strings;
- callbacks must be callable;
- evaluator names must match residual declarations exactly;
- missing, extra, and duplicate evaluators are rejected;
- each callback receives only the immutable unknown-value mapping;
- callback exceptions propagate unchanged;
- callback returns must be finite, non-bool numeric values;
- no callback is generated from component type, topology physics, registry
  selection, or a property backend.

## Scale Validation

Verified:

- scales are explicit and keyed by residual name;
- scale keys must exactly match residual declaration names;
- missing and extra scales are rejected;
- values must be finite, positive, non-bool numeric values;
- zero, negative, NaN, infinity, boolean, and non-numeric values are rejected;
- no implicit or hidden scale exists.

## Evaluation Semantics

Verified:

- assembly input must be `NetworkResidualAssembly`;
- unknown values must be `NetworkUnknownValues`;
- evaluator and scale collections are fully validated before evaluation;
- residual declaration order is preserved exactly;
- each declared callback is invoked once;
- raw values equal callback returns;
- names and units come from Phase 13F declarations;
- scales come from the explicit scale map;
- Phase 13C `ResidualSpec`, `ResidualEvaluation`, and `ResidualVector` are
  used directly;
- inputs are not mutated;
- there is no update loop, convergence loop, bisection, Newton method, root
  finder, optimizer, SciPy dependency, or automatic unknown adjustment.

## Result Diagnostics

`NetworkResidualEvaluationResult` is frozen and exposes:

- the original assembly;
- immutable unknown values;
- an evaluation tuple;
- the Phase 13C `ResidualVector`;
- scaled values;
- maximum absolute scaled residual;
- L2 scaled residual.

The scaled values and norms are obtained from `ResidualVector`. The result has
no iteration count, convergence claim, solved values, or solver method.

## Test Coverage

The 95 focused tests cover all 34 requested items plus strict type validation,
defensive-copy behavior for both ordinary mappings and mapping proxies,
immutability, callback-call counts, public export identity, AST/import
boundaries, and documentation honesty.

No focused test is skipped or xfailed, uses broad
`pytest.raises(Exception)`, or substitutes private imports for the required
public API verification.

## Documentation and Status

README, quickstart, concepts, examples guide, and project status now
consistently distinguish:

- implemented Phase 13E topology representation;
- implemented Phase 13F declaration assembly;
- implemented Phase 13G explicit one-shot residual evaluation;
- deferred Phase 13H configurable solving;
- no component execution, property lookup, graph-state attachment, arbitrary
  topology simulation, or experimental validation in Phase 13G.

Final counts are recorded as 95 focused tests, 515 network tests, and 4376
full-suite tests.

## Architecture Boundary Searches

Required searches were run for CoolProp, `PropertyBackend`,
`CorrelationRegistry`, `solve(network)`, `def solve`, SciPy root/optimization
APIs, `FluidState`, `SystemState`, physical-value terminology,
`contribute(`, deferred component families, and validation claims.

Matches in the new Phase 13G source are negative documentation or tests
asserting absence. Other matches are established pre-existing modules,
examples, historical documentation, or explicit deferred-capability text.
The only `mpl_sim.closed_loop` import in Phase 13G production code is the
Phase 13C pure value-type import from `closed_loop.residuals`.

No prohibited live dependency, iterative solve, automatic physics,
component execution, property lookup, registry resolution, or graph-state
attachment was found.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

Resolved during audit:

1. `NetworkUnknownValues` retained an incoming `MappingProxyType` directly.
   If that proxy wrapped a mutable source dict, later source mutation changed
   the supposedly immutable unknown-value set. Construction now always copies
   the mapping before creating its own proxy, with focused regression
   coverage.
2. README, quickstart, and examples-guide text still identified Phase 13F as
   current or Phase 13G residual evaluation as future work. They now describe
   the Phase 13G checkpoint and defer configurable solving to Phase 13H.
3. Project status used the pre-audit focused/full-suite counts. It now records
   95 focused tests and 4376 total tests.

## Deferred Items

- iterative configurable network solving;
- automatic unknown updates and convergence control;
- automatic physical residual construction;
- component execution from graph instances;
- property lookup and registry resolution;
- physical-state attachment to graph objects;
- arbitrary-topology and parallel-branch simulation;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- moving-boundary modeling;
- validation harnesses and experimental/literature comparison.

## Phase Classification

Phase 13G is an explicit one-shot residual-evaluation checkpoint. It evaluates
a caller-defined residual problem but does not solve, simulate, or validate a
physical network.

## Merge Readiness

`phase-13g-network-residual-evaluation` is approved for merge into `main` as a
checkpoint after the implementation and audit commits are created and pushed.
This audit does not authorize or perform the merge.
