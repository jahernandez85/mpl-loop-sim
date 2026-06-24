# Block 15B.4 Fixed-Loop Closeout Audit

## Verdict

**APPROVED WITH MINOR DOCUMENTATION FIXES.**

Block 15B.4 is a tests-and-docs-only closeout checkpoint. Block 15B may be
marked complete only within the planned **Minimal Physical Single-Loop Network
MVP** scope.

## Branch and commits

- Branch: `phase-15b4-fixed-loop-closeout`
- Base commit: `af69892`
- HEAD before audit: `af69892`
- Base relationship: the branch started at the current `main` commit.

## Scope audited

- `tests/network/test_fixed_single_loop_mvp_closeout.py`
- `docs/roadmap/PROJECT_STATUS.md`
- Existing Block 15B runtime APIs:
  - `src/mpl_sim/network/fixed_single_loop_scenario.py`
  - `src/mpl_sim/network/fixed_single_loop_residuals.py`
  - `src/mpl_sim/network/fixed_single_loop_runner.py`
- Network architecture boundaries and production-component contract inspection.

## Changed files

Before audit finalization, the Block 15B.4 change set contained only:

- new test: `tests/network/test_fixed_single_loop_mvp_closeout.py`
- updated operational status: `docs/roadmap/PROJECT_STATUS.md`

The audit added this document and corrected stale current-phase wording in
`PROJECT_STATUS.md`. No runtime source file was created or modified. No frozen
architecture document was modified. No generated artifact or cache file is
part of the change set.

## Closeout coverage review

The 47-test closeout file covers the complete fixed-loop MVP path:

1. scenario construction;
2. explicit residual-parameter validation;
3. algebraic residual assembly;
4. zero residuals at a known consistent point;
5. nonzero residuals after pressure or mass-flow perturbation;
6. convergence from a controlled off-solution pressure guess;
7. all eight unknowns in the solve result;
8. all eight residuals in the solve result;
9. residual ordering preserved from the scenario;
10. plain JSON-serializable report generation;
11. no report file writes.

The test file also verifies final residual tolerance and the analytically known
pressure solution. The report builder returns data only and has no output path,
`open`, `write_text`, CSV, or JSON-writing call.

## Mass-flow gauge behavior

- A continuity-consistent mass-flow gauge is preserved exactly in
  `solved_unknown_values`.
- The pressure solve does not optimize or invent mass flow.
- Different consistent gauges produce the same pressure solution while retaining
  their different mass-flow values.
- An inconsistent gauge returns `converged=False` before pressure iteration.
- The failure reason explicitly mentions fixed-loop continuity and the gauge.
- The absolute common mass-flow level is **not solved** by Block 15B.

This is an explicit algebraic fixed-loop MVP, not a full physical loop solver.

## Block 15B completion wording

`PROJECT_STATUS.md` now states that Block 15B provides:

- fixed single-loop scenario declaration;
- explicit parameterized algebraic residual assembly;
- fixed-loop residual evaluation;
- fixed-loop pressure-subsystem solve through the existing callback-only solver;
- lightweight report generation;
- acceptance/integration proof.

It also states that Block 15B does not provide arbitrary-topology physical
simulation, generic `solve(network)`, `NetworkGraph.solve()`, production
component execution, production `Component.contribute(...)`, `SystemState`
assembly, `FluidState` construction, or property/correlation/HX-backed
residuals.

## Validation results

All required validation commands passed:

| Validation | Result |
|---|---:|
| Block 15B.4 closeout | 47 passed |
| Block 15B.3 runner regression | 100 passed |
| Block 15B.2 residual regression | 102 passed |
| Block 15B.1 scenario regression | 84 passed |
| Block 15A.4 closeout regression | 38 passed |
| Network suite | 1751 passed |
| Full suite | 5612 passed |
| Skipped | 0 |
| Xfailed | 0 |
| Deselected | 0 |
| Six examples | 6 passed |
| Ruff | clean |
| Black | clean; 195 files unchanged |
| `git diff --check` | clean |

Pytest emitted only a local cache warning because the existing `.pytest_cache`
directory was not writable. Repository-local `--basetemp=.pytest_tmp` execution
worked and all tests passed.

## Boundary-search results

Required searches were run for property engines, registries, state objects,
component execution, `component_type`, generic solve APIs, production classes,
topology claims, and file-writing calls.

Classification:

- **Executable allowed:** explicit fixed-loop callback assembly and the existing
  `solve_network_residual_problem`; static imports of production classes solely
  for contract inspection; pre-existing general network assembly references to
  `SystemState` outside the Block 15B fixed-loop modules.
- **Documentation negative statements:** references saying CoolProp,
  `PropertyBackend`, correlations, HX models, `SystemState`, `FluidState`,
  production execution, arbitrary topology, and generic solve APIs are absent
  or deferred.
- **Test negative assertions:** AST/source checks prohibiting those same paths.
- **Executable suspicious:** none in the Block 15B.4 change set or fixed-loop
  runtime modules.
- **Prohibited:** none.

The fixed-loop modules do not import or call CoolProp, `PropertyBackend`,
`CorrelationRegistry`, HX models, production components, or correlations. They
do not assemble `SystemState`, construct `FluidState`, call `.contribute(...)`,
define `contribute`, implement `solve(network)`, attach `solve` to
`NetworkGraph`, or dispatch physics from `component_type`.

## Production contract regression

Phase 14G contract inspection still returns `NO_CONTRIBUTE_METHOD` for:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

The closeout suite verifies each class individually and through the bulk
inspection helper.

## Findings

### Critical

None.

### Major

None.

### Minor fixed

- `PROJECT_STATUS.md` contained stale lower sections identifying Block 15B.2 as
  current and Block 15B.3 as future work. Those sections were aligned with the
  validated Block 15B.4 closeout.
- Historical Block 15A wording saying Block 15B “remains deferred” was clarified
  to say it was deferred beyond Block 15A and is now complete within fixed-loop
  MVP scope.
- The last-updated status and audit index were refreshed.

### Minor remaining

None.

## Deferred items

The following remain outside Block 15B:

- arbitrary-topology physical simulation;
- topology extensions and configurable scenario building;
- real production component execution;
- production `Component.contribute(...)`;
- generic `solve(network)` and `NetworkGraph.solve()`;
- fixed-loop `SystemState` assembly or `FluidState` construction;
- automatic physics from `component_type`;
- property-, correlation-, and HX-model-backed network residuals;
- determination of the absolute common mass-flow level.

## Completion and merge readiness

Block 15B is complete **within the planned fixed-loop MVP scope only**. With no
critical or major findings, passing full validation, accurate documentation,
and no runtime changes in 15B.4, the branch is ready to commit, push, and merge.
