# Block 15C-A Topology Declaration Foundation Audit

## Verdict

**APPROVED WITH MINOR FIXES.**

Block 15C-A remains strictly topology/declaration-only. No critical or major
findings remain. Two minor findings were corrected during audit:

1. `ParallelTopologyScenario` now validates consistency among its graph,
   declaration assembly, binding context, ID/name containers, branches, and
   split/merge manifolds.
2. `PROJECT_STATUS.md` now distinguishes structural residual declarations from
   prohibited physical/branch residual assembly.

## Branch and commits

- Branch: `phase-15c-a-topology-declaration-foundation`
- Base commit: `e4745ab` (`main`, merge of Block 15B.4)
- HEAD before audit: `e4745ab`
- Audit date: 2026-06-24

The 15C-A implementation was uncommitted at audit start, so `main...HEAD` was
empty. The effective implementation scope was verified from the working tree
against `HEAD`.

## Scope and changed files

Runtime:

- `src/mpl_sim/network/topology_declarations.py`
- `src/mpl_sim/network/parallel_topology_scenario.py`
- `src/mpl_sim/network/__init__.py`

Tests:

- `tests/network/test_topology_declarations.py`
- `tests/network/test_parallel_topology_scenario.py`

Documentation:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/validation/audits/BLOCK_15C_A_TOPOLOGY_DECLARATION_FOUNDATION_AUDIT.md`

No frozen architecture or interface document was modified.

## Public API added

- `JunctionRole`
- `JunctionDeclaration`
- `ManifoldDeclaration`
- `ValveDeclaration`
- `TopologyBranchId`
- `ParallelBranchDeclaration`
- `ParallelTopologyComponentIds`
- `ParallelTopologyNodeIds`
- `ParallelTopologyUnknownNames`
- `ParallelTopologyResidualNames`
- `ParallelTopologyScenario`
- `build_parallel_topology_scenario`

All are exported from `mpl_sim.network`.

## Checkpoint review

### 15C.1 — Junction/manifold declarations

Approved. `JunctionRole` is a symbolic SPLIT/MERGE enum. Junction and manifold
objects are frozen, validate identifiers, roles, labels, node types, uniqueness,
and cardinality, and defensively copy metadata into read-only mappings. They
store no split ratios, pressure laws, physical values, or equations.

### 15C.2 — Parallel topology declaration

Approved with the minor consistency hardening described above. The factory is a
deterministic, keyword-only builder for one fixed two-branch topology. It does
not accept an arbitrary graph, infer physics from `component_type`, execute
components, create callbacks, or solve.

The scenario declares six nodes, seven component instances, thirteen unknown
names, and thirteen residual names. The declaration is square, but it is not a
physical residual system: declarations contain names and unit labels only.

### 15C.3 — Valve/local-loss declaration

Approved. `ValveDeclaration` stores only typed connectivity, an optional
symbolic residual name, and read-only metadata. It has no Kv/Cv, opening
command, loss coefficient, pressure-drop law, equation, property lookup, or
component execution.

## Declaration-only and 13×13 review

No physical equations or residual callbacks were added. The new scenario calls
the existing Phase 13F `assemble_network_residuals`, whose output consists only
of `NetworkUnknownDeclaration` and `NetworkResidualDeclaration` values.

The names `mdot:*`, `P:*`, `mass_balance:*`, and `pressure_drop:*` are symbolic
declaration labels. They do not infer physical meaning, dispatch component
physics, or create evaluators.

Absent from Block 15C-A:

- branch, split, manifold, valve, or local-loss equations;
- numerical residual callbacks;
- physical parameters or hidden defaults;
- solver calls or generic graph solve APIs;
- `SystemState` assembly or `FluidState` construction;
- property, correlation, or HX-model calls;
- production component execution;
- report or file output.

## `require_closed_loop=False` review

Approved. The parallel graph has split and merge nodes with degree two, so it is
not a closed *single* loop and must not call
`NetworkGraph.validate_closed_single_loop()`.

This option skips only that single-loop-specific validator. The graph
constructor still validates node/component types, duplicate IDs, node
references, and self-loops. Structural assembly still validates graph presence
and emits deterministic declarations. Binding construction validates exact
component coverage, declared names, and graph references. The audit hardening
adds scenario-level cross-consistency checks for all IDs, names, mappings,
branches, and manifolds.

This path does not provide arbitrary-topology physical simulation.

## Validation results

All final commands passed:

| Validation | Result |
|---|---:|
| Topology declaration focused tests | 63 passed |
| Parallel topology focused tests | 81 passed |
| Block 15B.4 closeout regression | 47 passed |
| Block 15B.3 runner regression | 100 passed |
| Network suite | 1,895 passed |
| Full suite | 5,756 passed |
| Skipped / xfailed / deselected | 0 / 0 / 0 |
| Examples | 6 of 6 passed |
| Ruff | clean |
| Black | clean |
| `git diff --check` | clean |

Pytest used repository-local `--basetemp` directories and disabled the cache
provider after an existing Windows permission warning on `.pytest_cache`.

Examples passed:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

## Boundary-search results

The required searches were run across the new runtime modules, focused tests,
the network package, production components, and project status documentation.

- Executable allowed: construction of symbolic `ComponentInstance` objects,
  structural declaration assembly, binding/state-map declarations, and
  scenario consistency validation.
- Documentation negative statements: references to CoolProp,
  `PropertyBackend`, `SystemState`, `FluidState`, `contribute(...)`,
  `solve(network)`, physical split/loss equations, and deferred capabilities.
- Test negative assertions: AST/import checks and absence-of-field checks.
- Existing non-15C test fixtures: local mock classes named `contribute` in the
  Phase 14G inspection tests; these are non-production inspection fixtures and
  are never invoked by 15C-A.
- Prohibited executable hits in Block 15C-A: none.

No new `def contribute`, `.contribute(...)` call, generic `solve(network)`, or
`NetworkGraph.solve()` exists.

## Production-contract regression

Direct inspection and existing regression tests report
`NO_CONTRIBUTE_METHOD` for all six known production classes:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`PROJECT_STATUS.md` accurately records that 15C-A is declaration-only, that
15C-B remains responsible for branch residual assembly and parallel topology
evaluation, and that arbitrary-topology physical simulation, production
component execution, `SystemState`, `FluidState`, properties/correlations/HX
calls, generic `solve(network)`, and `NetworkGraph.solve()` remain deferred.

## Findings

- Critical: none.
- Major: none.
- Minor fixed:
  - public scenario cross-consistency validation was incomplete;
  - status wording could be read as denying the intentional structural
    declaration assembly.
- Minor remaining: none.

## Deferred items

Block 15C-B or later remains responsible for:

- branch residual assembly and parallel topology evaluation;
- physical flow split and pressure compatibility equations;
- manifold mass/pressure equations;
- valve/local-loss equations and explicit physical parameters;
- production component execution;
- property/correlation/HX-backed physics;
- arbitrary-topology physical simulation;
- generic `solve(network)` or `NetworkGraph.solve()`.

## Readiness

Block 15C-A is ready to close. It is merge-ready after the audit commit is
created and pushed to the verified project remote.
