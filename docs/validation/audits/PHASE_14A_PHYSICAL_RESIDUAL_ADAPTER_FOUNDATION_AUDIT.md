# Phase 14A Physical Residual Adapter Foundation Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 14A adds an explicit callback adapter layer between Phase 13F residual
declarations and the Phase 13G/13H evaluation and solve stack. Caller-supplied
`PhysicalResidualAdapter` callbacks are matched by residual name and converted
into ordinary Phase 13G `NetworkResidualEvaluator` objects.

The phase does not infer physics from `ComponentInstance.component_type`,
execute components, call `contribute(...)`, resolve registries, call properties
or correlations, import CoolProp, attach state to graph objects, or provide a
physical MPL simulator.

Strict mapping validation, test exception specificity, stale user-facing
status text, and final validation counts were corrected during audit. No
critical or major finding remains.

## Scope Audited

- branch, history, working tree, changed files, and public exports;
- README, examples index, user guides, project status, implementation plan,
  frozen architecture/interface/correlation/schema documents, decision log,
  and Phase 13A-13H audits;
- `src/mpl_sim/network/physical_adapters.py`;
- `src/mpl_sim/network/__init__.py`;
- unchanged Phase 13F/13G/13H assembly, evaluation, and solve dependencies;
- `tests/network/test_physical_residual_adapter_foundation.py`;
- Phase 14A documentation and status claims;
- architecture-boundary searches across source, tests, examples, and user
  documentation.

No architecture document, component/HX/correlation/property implementation,
closed-loop solver, existing network residual semantics, generic solver core,
schema, or validation harness was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-14a-physical-residual-adapter-foundation`
- `git status --short --branch`
- `git log --oneline --decorate -12`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
- changed-file and package/test directory listings

The branch began at `ed67adb`, the Phase 13H merge on `main`.

No accidental `src/mpl_sim/network/init.py` exists. The untracked
`.pytest_tmp/` environment artifact was excluded from the commit scope.

### Validation

All pytest runs used separate repository-local system-temp and base-temp roots.
No tests were skipped, xfailed, deselected, or excluded.

- `pytest`
  - **4571 passed**
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
  - **710 passed**
- `pytest tests/network/test_physical_residual_adapter_foundation.py -q -ra`
  - **82 passed**
- all six required example scripts
  - completed successfully
- `ruff check src tests examples`
  - clean
- `black --check --no-cache --verbose src tests examples`
  - **169 files would be left unchanged**
- `git diff --check`
  - clean

Pytest emitted only the known non-blocking warning that the optional
`.pytest_cache` path could not be written. All required temporary-path fixtures
ran and passed.

## Actual Implementation Summary

The phase adds:

- `PhysicalResidualContext`;
- `PhysicalResidualAdapter`;
- `PhysicalResidualAdapterSet`;
- `build_network_residual_evaluators`.

The builder validates exact adapter coverage of assembly residual declarations,
orders adapters by assembly declaration order, and returns a tuple of Phase 13G
evaluators. Each evaluator wraps the current unknown-value mapping and optional
explicit metadata in a new `PhysicalResidualContext`, then calls only the
caller-supplied adapter callback.

## Public API

Verified:

```python
from mpl_sim.network import (
    PhysicalResidualContext,
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    build_network_residual_evaluators,
)
```

All four names are in `mpl_sim.network.__all__`. Existing Phase 7 and Phase
13E/13F/13G/13H exports remain available. `NetworkGraph` has no `solve` method,
and no automatic `solve(network)` or physical simulator API was added.

## Context Semantics

`PhysicalResidualContext` is frozen and:

- requires a real `Mapping` for unknown values;
- defensively copies unknown values into a `MappingProxyType`;
- accepts optional metadata only as a real `Mapping`;
- defensively copies metadata into a `MappingProxyType`;
- carries no graph, component, property backend, registry, or physical state;
- performs no property computation or component execution.

The context is created per generated evaluator invocation. It does not mutate
the Phase 13G unknown mapping or any topology object.

## Adapter Semantics

`PhysicalResidualAdapter` is a frozen `(residual_name, callback)` binding:

- residual names must be non-empty, non-whitespace strings;
- callbacks must be callable;
- callback signature is explicit:
  `callback(context: PhysicalResidualContext) -> float`;
- callback exceptions propagate unchanged;
- numeric, Boolean, type, NaN, and infinity return validation remains owned by
  Phase 13G;
- no adapter is generated from component type or component objects.

## Adapter Set Semantics

`PhysicalResidualAdapterSet`:

- is frozen;
- normalizes input to an immutable tuple;
- validates every entry type;
- rejects duplicate residual names;
- preserves deterministic caller insertion order;
- stores no hidden backend, registry, graph, or mutable solver state.

## Evaluator Builder Semantics

`build_network_residual_evaluators`:

- requires `NetworkResidualAssembly`;
- accepts a validated adapter set or iterable of adapters;
- rejects wrong entry types and duplicate names;
- rejects missing and extra adapter names;
- returns evaluators in assembly residual declaration order;
- returns actual Phase 13G `NetworkResidualEvaluator` instances;
- freezes optional metadata before callback construction;
- passes only the Phase 13G unknown mapping through
  `PhysicalResidualContext`;
- does not mutate assembly, adapters, source mappings, metadata, or graph;
- does not inspect `component_type`, execute components, call
  `contribute(...)`, or call properties/correlations.

## Relationship to Phase 13G/13H

Generated evaluators are consumed directly by
`evaluate_network_residuals`. Phase 13G still owns evaluator-name validation,
callback return validation, residual construction, and scaled diagnostics.

The Phase 13H integration test passes the same generated evaluator tuple into
`solve_network_residual_problem` and converges a square linear toy problem.
Phase 14A introduces no alternate evaluation or solve path.

## Toy Adapter Behavior

The focused tests verify explicit algebraic mass-balance-style and
pressure-drop-style callbacks. Their constants are local test/documentation
values only, not library defaults, physical correlations, or validation data.

Phase 13G returns exactly the callback outputs in declaration order. The Phase
13H toy solve updates only explicit unknown values and invokes only the
generated callback evaluators.

## Test Coverage

The 82 focused tests cover all requested context, adapter, adapter-set,
builder, Phase 13G, Phase 13H, immutability, error, public-export,
documentation, and architecture-boundary cases.

No focused Phase 14A test is skipped or xfailed. Broad
`pytest.raises(Exception)` checks were replaced with `FrozenInstanceError`.
Public imports are used for behavior; direct module imports are used only to
verify public-export identity.

## Documentation and Status

README, quickstart, concepts, examples guide, examples index, and project
status now consistently distinguish:

- implemented Phase 14A explicit physical-style callback adapters;
- caller-supplied callbacks and metadata;
- compatibility with Phase 13G evaluation and Phase 13H solving;
- no automatic residual construction from component types;
- no component execution, properties, correlations, or graph-state storage;
- no physical MPL simulator or experimental validation.

Final counts are 82 focused tests, 710 network tests, and 4571 full-suite
tests.

## Architecture Boundary Searches

Required searches covered CoolProp, `PropertyBackend`,
`CorrelationRegistry`, `solve(network)`, SciPy root APIs, `FluidState`,
`SystemState`, physical value terminology, `contribute(`, `component_type`,
deferred component families, and validation claims.

Matches in the new Phase 14A module are negative boundary documentation only.
Executable imports are limited to:

- `collections.abc.Callable` and `Mapping`;
- `dataclasses.dataclass`;
- `types.MappingProxyType`;
- Phase 13F `NetworkResidualAssembly`;
- Phase 13G `NetworkResidualEvaluator`.

No prohibited production dependency, component execution, inferred physics,
property/correlation lookup, graph mutation, or simulator claim was found.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

Resolved during audit:

1. Context and builder mapping checks accepted any object exposing an
   `items()` method. They now require `collections.abc.Mapping`, with focused
   impostor regression tests.
2. Three frozen-dataclass tests used broad `pytest.raises(Exception)`. They now
   assert `FrozenInstanceError`.
3. README, quickstart, examples guide/index, and lower project-status sections
   still presented Phase 13H as current or physical adapters as wholly
   deferred. They now describe Phase 14A while keeping component binding and
   physical simulation deferred.
4. Pre-audit status counts were replaced with the final 82 focused, 710
   network, and 4571 full-suite results.

## Deferred Items

- component binding and state-vector mapping;
- automatic physical residual construction from component contributions;
- architecture-level `SystemState`/component contribution assembly;
- component execution and property-backed physical network evaluation;
- arbitrary-topology and parallel-branch simulation;
- valves, manifolds, recuperators, pre-heaters, and post-heaters;
- moving-boundary modeling;
- validation harnesses and experimental/literature comparison.

## Phase Classification

Phase 14A is an explicit callback adapter checkpoint. It provides a typed bridge
to the existing residual evaluator and algebraic solver but does not itself
construct, execute, simulate, or validate physical network models.

## Merge Readiness

`phase-14a-physical-residual-adapter-foundation` is approved for merge into
`main` as a checkpoint after the implementation and audit commits are created
and pushed. This audit does not authorize or perform the merge.
