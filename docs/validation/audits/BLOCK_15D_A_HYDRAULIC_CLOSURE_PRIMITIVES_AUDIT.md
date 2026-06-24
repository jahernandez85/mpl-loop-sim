# Block 15D-A Hydraulic Closure Primitives Audit

## Verdict

**APPROVED WITH MINOR FIXES.**

Block 15D-A correctly adds explicit algebraic hydraulic closure primitives and
targeted category-presence diagnostics without adding hidden physics, production
component execution, property/correlation/HX-backed models, arbitrary-topology
simulation, or a network solve API.

## Git and scope

- Branch: `phase-15d-a-hydraulic-closure-primitives`
- Base commit: `4a7e444`
- HEAD before audit: `4a7e444`
- Base description: merged Block 15C-B
- Frozen architecture documents modified: none

Audited working-tree files:

- `src/mpl_sim/network/hydraulic_closures.py`
- `src/mpl_sim/network/hydraulic_closure_diagnostics.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_hydraulic_closures.py`
- `tests/network/test_hydraulic_closure_diagnostics.py`
- `tests/network/test_hydraulic_closure_parallel_integration.py`
- `docs/roadmap/PROJECT_STATUS.md`

Audit-added file:

- `docs/validation/audits/BLOCK_15D_A_HYDRAULIC_CLOSURE_PRIMITIVES_AUDIT.md`

## Public API added

- `HydraulicClosureKind`
- `HydraulicClosureDeclaration`
- `ImposedMassFlowClosure`
- `ImposedBranchSplitClosure`
- `ImposedPressureClosure`
- `LinearPressureDropClosure`
- `QuadraticPressureDropClosure`
- `PressureCompatibilityClosure`
- `HydraulicClosureResidualSet`
- `build_hydraulic_closure_residuals`
- `HydraulicClosureCategory`
- `HydraulicClosureDiagnostic`
- `HydraulicClosureDiagnosticResult`
- `evaluate_hydraulic_closure_sufficiency`
- `make_two_branch_parallel_diagnostic`

## Checkpoint review

### 15D-A.1 — closure primitives

Approved. All six closures are frozen dataclasses with explicit names and
finite-scalar validation. Bool, non-numeric, NaN, and infinity inputs are
rejected. Linear, quadratic, and compatibility coefficients are explicit and
non-negative. No closure imports or calls properties, correlations, HX models,
production components, `SystemState`, or `FluidState`.

`HydraulicClosureResidualSet` preserves caller order, rejects duplicate residual
names through its factory, validates required unknown values during evaluation,
ignores unrelated extra unknowns, and returns a read-only residual mapping.
Metadata is defensively copied.

### 15D-A.2 — diagnostics

Approved. Diagnostics are deterministic and category based. The fixed
two-branch diagnostic requires total flow, branch split, pressure reference,
branch pressure-drop law, and simplified pressure compatibility categories.
Missing categories and messages are deterministic.

`is_sufficient=True` means only that every required category is represented.
It does not claim combined equation-count validation, symbolic rank analysis,
DAE analysis, arbitrary-network validation, or guaranteed solvability.

### 15D-A.3 — parallel integration

Approved. Tests prove that:

- the 15C-A scenario still builds with 13 unknowns and 13 residuals;
- all 13 15C-B residuals evaluate to zero at the known consistent point;
- all five closure residuals separately evaluate to zero at that point;
- diagnostics transition from missing categories to category-sufficient;
- the split fraction remains explicit and user imposed;
- no combined residual assembly or solve is performed or claimed.

## Closure equations and sign conventions

- Imposed mass flow: `r = mdot - imposed_value`. Exact and tested above/below
  the imposed value.
- Imposed branch split:
  `r = mdot_branch - split_fraction * mdot_total`. The fraction has no default,
  must satisfy `0 < split_fraction < 1`, and is documented as a user constraint,
  not predicted branch distribution.
- Imposed pressure: `r = P - imposed_value`. Exact and property independent.
- Linear pressure drop:
  `r = P_in - P_out - resistance * mdot`. Positive flow implies positive
  `P_in - P_out` for non-negative resistance.
- Quadratic pressure drop:
  `r = P_in - P_out - coefficient * mdot * abs(mdot)`. The sign-preserving
  reverse-flow convention is tested.
- Pressure compatibility:
  `r = resistance_a * mdot_a - resistance_b * mdot_b`. This is a simplified
  equality of two caller-supplied linearized path-drop expressions. It is not a
  general manifold pressure equation, does not traverse topology, and does not
  infer hidden branch laws.

The linear and quadratic primitives are explicit algebraic equations only.
They are not Darcy-Weisbach, friction-factor, valve Kv/Cv, density-, viscosity-,
Reynolds-, property-, or correlation-backed models. Coefficient units and
physical interpretation remain the caller's responsibility.

## Validation results

All pytest commands used repository-local `--basetemp=.pytest_tmp` and
`-p no:cacheprovider`.

| Validation | Result |
|---|---:|
| `test_hydraulic_closures.py` | 122 passed |
| `test_hydraulic_closure_diagnostics.py` | 41 passed |
| `test_hydraulic_closure_parallel_integration.py` | 42 passed |
| New 15D-A tests total | 205 passed |
| `test_parallel_topology_residuals.py` | 90 passed |
| `test_parallel_topology_mvp_closeout.py` | 62 passed |
| Network suite | 2252 passed |
| Full suite | 6106 passed |
| Failed/errors | 0 |
| Skipped/xfailed/deselected | 0/0/0 |
| Six required examples | 6 passed |
| Ruff | clean |
| Black | clean; 207 files unchanged |
| `git diff --check` | clean |

Required examples passed:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

## Windows temporary-directory error classification

The stale repository-local `.pytest_tmp` initially reproduced a Windows access
denial during cleanup. The exact resolved path was verified to remain inside
the repository and was removed with elevated filesystem access. After that
cleanup, every focused test, the network suite, and the full suite passed with a
fresh repository-local base temp and pytest cache disabled.

The previously reported seven errors did not recur. They are classified as
stale temporary-directory/permission artifacts rather than product test
failures. There are no unresolved full-suite errors.

## Boundary-search results

Searches covered CoolProp/property/registry names, `SystemState`, `FluidState`,
production components, `component_type`, `contribute`, solve APIs, property/
component/correlation/HX imports, file I/O, Darcy-Weisbach and related physical
terms, and numerical root/least-squares solvers.

Classification:

- Executable allowed: explicit arithmetic, validation, immutable containers,
  deterministic category inspection, and test-only source reading.
- Executable suspicious: none.
- Documentation negative statements: present and correctly state prohibited
  boundaries.
- Test negative assertions: present and correctly enforce imports/calls/API
  absence.
- Prohibited executable hits: none.

No new closure or diagnostic code constructs `SystemState` or `FluidState`,
calls CoolProp/`PropertyBackend`/`CorrelationRegistry`, calls HX models or
production components, dispatches physics from `component_type`, writes files,
calls or defines production `contribute`, or adds `solve(network)` or
`NetworkGraph.solve()`.

## Production-contract regression

Direct inspection reports `NO_CONTRIBUTE_METHOD` for:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`PROJECT_STATUS.md` accurately records the explicit algebraic scope, user-
imposed split, simplified linearized compatibility equation, category-only
diagnostic limits, architecture exclusions, deferred physical models, clean
full-suite result, and Windows temp-error classification.

## Findings

### Critical

None.

### Major

None.

### Minor fixed

1. Tightened pressure-compatibility wording so it cannot be read as a general
   manifold or nonlinear physical compatibility law.
2. Corrected a test name/comment that said compatibility alone “closes” a split
   even though the demonstrated set did not contain branch mass balance.
3. Corrected an integration docstring coefficient from `75,000` to `125,000`
   for the total branch-A linearized path resistance.
4. Clarified that 15C-B and closure residuals are evaluated separately and that
   the diagnostic does not validate combined equation count or rank.
5. Replaced the stale “6106 passed, 7 errors” status with the independently
   verified clean-temp result.

### Minor remaining

None.

## Deferred items

- Thermal closure primitives
- Real valve Kv/Cv laws
- Darcy-Weisbach and friction-factor models
- Density-, viscosity-, Reynolds-, and property-dependent pressure drop
- Correlation- and HX-backed closures
- Production component adapters and execution
- Configurable scenario building
- Combined closure/physical residual assembly
- Symbolic rank or DAE solvability analysis
- Physically predictive branch-flow solution
- Arbitrary-topology physical simulation
- Generic `solve(network)` and `NetworkGraph.solve()`

## Readiness

Block 15D-A is complete within its explicit hydraulic-closure-primitives MVP
scope. No critical or major findings remain. The branch is ready to merge after
the audit commit is pushed; it must not be interpreted as providing a combined
parallel-network solve or predictive hydraulic component physics.
