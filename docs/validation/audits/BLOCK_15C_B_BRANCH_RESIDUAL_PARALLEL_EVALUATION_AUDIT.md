# Block 15C-B Branch Residual / Parallel Evaluation Audit

## Verdict

**APPROVED WITH MINOR FIXES.**

Block 15C-B correctly implements a fixed-topology algebraic residual assembly,
evaluation, and plain-report MVP for the Block 15C-A two-branch topology. It
does not claim or attempt to predict the parallel flow distribution.

No critical or major findings remain.

## Git and scope

- Branch: `phase-15c-b-branch-residual-parallel-evaluation`
- Base commit: `b59a2e8` (`main`, merge of Block 15C-A)
- HEAD before audit: `b59a2e8`
- Pre-audit implementation state: uncommitted working-tree changes
- Runtime changes:
  - `src/mpl_sim/network/parallel_topology_residuals.py`
  - `src/mpl_sim/network/__init__.py`
- Test changes:
  - `tests/network/test_parallel_topology_residuals.py`
  - `tests/network/test_parallel_topology_mvp_closeout.py`
- Documentation changes:
  - `docs/roadmap/PROJECT_STATUS.md`
  - this audit document
- Frozen architecture documents modified: none
- Unrelated generated/cache artifacts included: none

## Public API added

- `ParallelTopologyResidualParameters`
- `ParallelTopologyPhysicalResidualAssembly`
- `build_parallel_topology_physical_residuals`
- `ParallelTopologyEvaluationResult`
- `evaluate_parallel_topology_residuals`
- `build_parallel_topology_report`

No parallel-topology solve request, solve result, or solve function was added.

## Checkpoint review

### 15C.4 — residual assembly

Approved. The factory requires a `ParallelTopologyScenario` and explicit
`ParallelTopologyResidualParameters`. It builds seven fixed algebraic callback
adapters and a directly inspectable `ContributionResidualMap`. It covers each
of the 13 declared residual names exactly once.

### 15C.5 — evaluation and report

Approved. Evaluation requires exact coverage of all 13 unknowns and rejects
bool, non-numeric, NaN, infinity, missing, and extra values. The result is
frozen and defensively copies unknown, residual, and metadata mappings.
Residual order matches `ParallelTopologyResidualNames.all_names()`. Max-absolute
and L2 norms are correct.

The report is plain serializable data, performs no file I/O, identifies the
fixed topology, includes unknowns/residuals/norms, and explicitly says that
solving is deferred.

### 15C.6 — closeout

Approved. Closeout coverage proves the 15C-A scenario still builds, the 15C-B
assembly/evaluation/report path works, a consistent point has zero residuals,
a perturbed point has nonzero residuals, Block 15B remains operational, and all
six production classes still report `NO_CONTRIBUTE_METHOD`.

## Residual equations and sign convention

The six continuity residuals are:

```text
mass_balance:n_pump_out  = mdot_pump - mdot_branch_a - mdot_branch_b
mass_balance:n_a_out     = mdot_branch_a - mdot_merge_a
mass_balance:n_b_out     = mdot_branch_b - mdot_merge_b
mass_balance:n_merge_out = mdot_merge_a + mdot_merge_b - mdot_condenser
mass_balance:n_cond_out  = mdot_condenser - mdot_accumulator
mass_balance:n_acc_out   = mdot_accumulator - mdot_pump
```

The seven pressure residuals are:

```text
pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference
pressure_drop:pump        = P_n_pump_out - P_n_acc_out - pump_pressure_rise
pressure_drop:branch_a    = P_n_a_out - P_n_pump_out + branch_a_pressure_drop
pressure_drop:branch_b    = P_n_b_out - P_n_pump_out + branch_b_pressure_drop
pressure_drop:merge_a     = P_n_merge_out - P_n_a_out + merge_a_pressure_drop
pressure_drop:merge_b     = P_n_merge_out - P_n_b_out + merge_b_pressure_drop
pressure_drop:condenser   = P_n_cond_out - P_n_merge_out + condenser_pressure_drop
```

The sign convention is explicit and tested. Parameters are signed algebraic
inputs; there are no hidden pressure-drop, valve, Kv, Cv, property, correlation,
or HX laws.

## Contribution adapter map

| Component | Residuals |
|---|---|
| accumulator | `mass_balance:n_cond_out`, `pressure_drop:accumulator` |
| pump | `mass_balance:n_acc_out`, `pressure_drop:pump` |
| branch_a | `mass_balance:n_a_out`, `pressure_drop:branch_a` |
| branch_b | `mass_balance:n_b_out`, `pressure_drop:branch_b` |
| merge_a | `mass_balance:n_pump_out`, `pressure_drop:merge_a` |
| merge_b | `mass_balance:n_merge_out`, `pressure_drop:merge_b` |
| condenser | `pressure_drop:condenser` |

These are fixed callbacks for the declared scenario. They do not execute
production components, traverse an arbitrary graph to infer physics, define
`contribute`, or call `.contribute(...)`.

## Solve deferral

Solve deferral is technically honest:

- The six continuity equations have rank five over seven mass-flow unknowns.
  The mass-flow subspace therefore has two degrees of freedom: total flow and
  branch split.
- The pressure subsystem has seven equations over six pressure unknowns and is
  consistent only when the two branch-path drops are compatible.
- Phase 13H expects a square determined problem.

A physically meaningful solve requires two explicit mass-flow closure
constraints and explicit pressure compatibility handling, potentially supplied
later by imposed constraints or physical branch laws. Block 15C-B does not
invent those closures, add hidden gauges, use least squares/pseudoinverses, or
silently impose a split ratio.

## Validation results

All commands used repository-local pytest temporary directories and disabled
the pytest cache provider.

| Validation | Result |
|---|---:|
| `test_parallel_topology_residuals.py` | 90 passed |
| `test_parallel_topology_mvp_closeout.py` | 62 passed |
| `test_topology_declarations.py` | 63 passed |
| `test_parallel_topology_scenario.py` | 81 passed |
| `test_fixed_single_loop_mvp_closeout.py` | 47 passed |
| `tests/network` | 2047 passed |
| Full suite | 5908 passed |
| Skipped / xfailed / deselected | 0 / 0 / 0 |
| Six required examples | all passed |
| Ruff | passed, 0 violations |
| Black | passed, 202 files unchanged |
| `git diff --check` | passed |

The six examples were:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

## Boundary-search results

Required searches were run for properties/CoolProp, contribution APIs,
`SystemState`, `FluidState`, `component_type`, generic solve APIs, production
components, file I/O, numerical least-squares/root helpers, and hidden
flow-split/gauge/closure language.

- Executable allowed: fixed algebraic callback construction and existing
  evaluation infrastructure.
- Documentation negative statements: expected prohibition/deferred-language
  hits.
- Test negative assertions: expected boundary tests and source inspections.
- Expected regression imports: production component classes are imported only
  to verify `NO_CONTRIBUTE_METHOD`.
- Prohibited executable hits in the Block 15C-B runtime: none.

No Block 15C-B runtime import or call was found for CoolProp,
`PropertyBackend`, `CorrelationRegistry`, `SystemState`, `FluidState`,
production components, correlations, HX models, least squares, pseudoinverse,
generic root solving, file writing, `component_type` dispatch, or a generic
network solve.

## Production contract regression

Phase 14G inspection reports `NO_CONTRIBUTE_METHOD` for:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`PROJECT_STATUS.md` accurately records the fixed-topology evaluation/report
scope, the 90 + 62 focused tests, 2047 network tests, 5908 full-suite tests,
solve deferral, and the prohibited/deferred architecture items.

## Findings and corrective changes

### Critical

None.

### Major

None.

### Minor fixed

1. Solver-deferral wording called the missing mass-flow constraints
   “gauge-fixing.” This could imply that arbitrary gauges are sufficient.
   Runtime/report/test documentation now states that two explicit closure
   constraints and pressure compatibility handling are required and must not be
   invented by this MVP.
2. `PROJECT_STATUS.md` still described Block 15C-A as the current branch/phase
   and showed the old baseline counts. The rows were updated for Block 15C-B.

### Minor remaining

None.

## Deferred items

- Physically closed parallel-flow distribution
- Explicit valve/Kv/Cv/local-loss equations
- Flow-dependent branch pressure-drop laws
- Arbitrary-topology physical simulation
- Production component execution and production `Component.contribute(...)`
- `SystemState` assembly and `FluidState` construction
- Property-, correlation-, and HX-model-backed residuals
- Generic `solve(network)` and `NetworkGraph.solve()`
- Configurable scenarios beyond this fixed topology

## Block 15C completion and merge readiness

Block 15C is complete **within the topology-extension MVP scope**: declarations
from 15C-A plus fixed-topology residual assembly, evaluation, reporting, and
closeout proof from 15C-B.

**Merge readiness: yes**, subject to the final post-edit validation, audit
commit, remote verification, and successful branch push recorded by the audit
agent.
