# Phase 13F Network Residual Assembly Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 13F adds a declaration-only mapping from `NetworkGraph` topology to
ordered unknown and residual declarations. It stores names and units only.
It does not evaluate residuals, solve a network, execute components, attach
physical values, call properties or correlations, or add `solve(network)`.

Strict option validation and documentation consistency findings were corrected
during audit. No critical or major finding remains.

## Scope Audited

- branch, history, working tree, and complete Phase 13F change set;
- authoritative README, examples guide, user guides, roadmap, architecture,
  interface, correlation contract, schema, decision log, implementation plan,
  and prior Phase 11U/12A/12B/13A/13B/13C/13D/13E audits;
- `src/mpl_sim/network/residual_assembly.py`;
- `src/mpl_sim/network/__init__.py`;
- `tests/network/test_residual_assembly_foundation.py`;
- Phase 13F documentation and project-status changes;
- architecture-boundary searches across network, closed-loop, examples,
  user documentation, and tests.

No architecture document, closed-loop solver, component/HX/correlation
implementation, property backend, generic solver, schema, or validation
harness was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-13f-network-residual-assembly`
- `git status --short --branch`
- `git log --oneline --decorate -10`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- changed-file and package listings

The branch began at `7011a34`, the Phase 13E merge on `main`.

No accidental `src/mpl_sim/network/init.py` exists. Package exports are in
`src/mpl_sim/network/__init__.py`.

### Validation

All successful pytest runs used separate repository-local system-temp and
base-temp directories. No tests were skipped, xfailed, or deselected.

- `pytest -ra`
  - **4281 passed**
- `pytest tests/correlations -ra`
  - **512 passed**
- `pytest tests/hx_models tests/components -ra`
  - **1896 passed**
- `pytest tests/loops -v -ra`
  - **33 passed**
- `pytest tests/examples -v -ra`
  - **60 passed**
- `pytest tests/closed_loop -v -ra`
  - **393 passed**
- `pytest tests/network -v -ra`
  - **420 passed**
- `pytest tests/network/test_residual_assembly_foundation.py -v -ra`
  - **122 passed**
- all six required example scripts
  - completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **163 files would be left unchanged**
- `git diff --check`
  - clean

An initial aggregate run used a nested base-temp directory that disappeared
before five `tmp_path` fixtures were created; 4276 tests had passed and those
five fixtures errored before test execution. The complete suite was rerun with
separate system-temp and base-temp roots and passed all 4281 tests. This was an
environment layout issue, not a source/test failure.

Pytest emitted only the known non-blocking warning that `.pytest_cache` could
not be written in the execution environment.

## Actual Implementation Summary

The phase adds:

- `NetworkUnknownDeclaration`;
- `NetworkResidualDeclaration`;
- `NetworkUnknownSet`;
- `NetworkResidualSet`;
- `NetworkResidualAssembly`;
- `assemble_network_residuals`.

Assembly follows graph insertion order. It declares one `mdot:<id>` unknown
per component instance, optionally one `P:<id>` unknown per node, one
`mass_balance:<id>` residual per node, and optionally one
`pressure_drop:<id>` residual per component instance.

## Public API

Verified:

```python
from mpl_sim.network import (
    NetworkUnknownDeclaration,
    NetworkResidualDeclaration,
    NetworkUnknownSet,
    NetworkResidualSet,
    NetworkResidualAssembly,
    assemble_network_residuals,
)
```

All six names are present in `mpl_sim.network.__all__`. Existing Phase 7 and
Phase 13E exports remain available. No `solve`, `Solver`, residual evaluator,
physics object, or component executor is exported.

## Declaration Semantics

Verified:

- both declaration types are frozen dataclasses;
- declaration fields are exactly `name` and `unit`;
- non-string, empty, and whitespace-only names/units are rejected;
- collection storage is converted defensively to tuples;
- collection entry types and duplicate names are validated;
- insertion order is preserved;
- assembly fields are exactly the unknown and residual sets;
- summaries contain counts and names only;
- no value, scale, guess, bound, state, property, or component field exists.

## Assembly Behavior

Verified:

- non-`NetworkGraph` input is rejected;
- graphs with no nodes or no component instances are rejected;
- all three option flags require actual Boolean values;
- mass-flow unknowns use `mdot:<component_id>` and `kg/s`;
- pressure unknowns use `P:<node_id>` and `Pa`;
- mass-balance residuals use `mass_balance:<node_id>` and `kg/s`;
- pressure-drop residuals use `pressure_drop:<component_id>` and `Pa`;
- optional pressure declarations are enabled by default and can be disabled;
- `require_closed_loop=True` delegates to
  `NetworkGraph.validate_closed_single_loop()`;
- open graphs are accepted by default;
- the input graph is not mutated;
- no numerical residual or physical quantity is computed.

## Layering and Imports

`residual_assembly.py` imports only:

- `__future__`;
- `dataclasses`;
- `mpl_sim.network.graph.NetworkGraph`.

It does not import `mpl_sim.closed_loop`, components, HX models, correlations,
properties, solvers, `FluidState`, `SystemState`, `PropertyBackend`,
`CorrelationRegistry`, or CoolProp.

## Test Coverage

The 122 focused tests cover all 24 requested items plus strict declaration,
collection, assembly-field, immutability, duplicate-name, option-type, public
export, and documentation checks.

No focused test is skipped or xfailed, uses
`pytest.raises(Exception)`, or substitutes private imports for public API
verification. The audit strengthened the Phase 13F documentation assertion so
it inspects the Phase 13F section rather than accepting the word `not`
anywhere in the document.

## Documentation and Status

README, quickstart, concepts, examples guide, and project status now
consistently distinguish:

- implemented Phase 13E topology representation;
- implemented Phase 13F declaration-only residual assembly;
- deferred numerical residual evaluation and configurable network solving;
- deferred arbitrary-topology simulation and component-family integration;
- deferred experimental validation.

Final counts are recorded as 122 focused tests, 420 network tests, and 4281
full-suite tests.

## Architecture Boundary Searches

Required searches were run for CoolProp, `PropertyBackend`,
`CorrelationRegistry`, `solve(network)`, `def solve`, `FluidState`,
`SystemState`, physical-value terminology, `contribute(`, deferred component
families, and validation claims.

Matches in the new Phase 13F source are negative documentation or tests
asserting absence. Other matches are established pre-existing modules,
historical documentation, examples, or explicit deferred-capability text. No
prohibited live dependency, numerical residual evaluation, component
execution, physical-value storage, or generic network solve was found.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

Resolved during audit:

1. The three assembly option flags accepted arbitrary truthy/falsy values.
   They now require `bool`, with focused regression coverage.
2. README, quickstart, examples-guide, and project-status text still described
   network residual assembly as deferred or used placeholder counts. They now
   describe Phase 13F accurately and record final validation counts.
3. A focused documentation test could pass whenever the word `not` appeared
   anywhere in `CONCEPTS.md`. It now checks the Phase 13F section directly.

## Deferred Items

- numerical network residual evaluation;
- configurable network solving;
- pressure/mass-flow solution over a graph;
- arbitrary-topology and parallel-branch simulation;
- component execution from graph instances;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- physical-state attachment and property lookup;
- moving-boundary modeling;
- validation harnesses and literature/experimental comparison.

## Phase Classification

Phase 13F is a declaration-assembly checkpoint. It defines the shape and
ordering of a future network residual problem without evaluating or solving
that problem.

## Merge Readiness

`phase-13f-network-residual-assembly` is approved for merge into `main` as a
checkpoint after the implementation and audit commits are created and pushed.
This audit does not authorize or perform the merge.
