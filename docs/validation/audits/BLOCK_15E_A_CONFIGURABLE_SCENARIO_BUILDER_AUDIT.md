# Block 15E-A Configurable Scenario Builder Audit

## Verdict

Approved with minor fixes. No critical or major findings remain.

## Branch and commits

- Branch: `phase-15e-a-configurable-scenario-builder`
- Base commit: `0f3a5a588c4defcc431e2eee6db31be448013126`
- HEAD before audit: `0f3a5a588c4defcc431e2eee6db31be448013126`
- Implementation was uncommitted at audit start.

## Scope audited

- `src/mpl_sim/network/configurable_scenarios.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_configurable_scenarios.py`
- `tests/network/test_configurable_scenarios_fixed_equivalence.py`
- `docs/roadmap/PROJECT_STATUS.md`
- Related graph, residual assembly, binding, fixed-loop, parallel-topology,
  closure-integration, and production-contract inspection modules.

No frozen architecture document was modified.

## Public API

- `ScenarioComponentRole`
- `ScenarioComponentSpec`
- `ScenarioNodeSpec`
- `ScenarioConnectionSpec`
- `ScenarioBranchSpec`
- `ConfigurableScenarioSpec`
- `ConfigurableScenarioBuildResult`
- `build_configurable_scenario`
- `build_configurable_scenario_report`

The exports are narrow and intentional.

## Checkpoint review

### 15E-A.1 — Specs

Approved. Specs are frozen declaration objects with deterministic tuple
ordering, ID/type validation, defensive top-level metadata copies, read-only
metadata views, exact component-connection coverage, cross-reference checks,
and structural branch-path validation.

### 15E-A.2 — Builder and report

Approved. The builder creates only `NetworkGraph`,
`NetworkResidualAssembly`, and `NetworkBindingContext` declarations. The
report is a plain JSON-serializable dictionary with
`status: "declaration_only"`, `no_solve: true`, counts, names, roles, and
limitations. It performs no file writes.

### 15E-A.3 — Fixed equivalence and regression

Approved. Tests compare component/node IDs, deterministic unknown/residual
names, binding maps, and ordered graph edges against the fixed 15B and 15C
builders. They make no physical- or solve-equivalence claim.

## Declaration-only and role review

`ScenarioComponentRole` is metadata only. Its value is copied into the
physics-free `ComponentInstance.component_type` label and reported as metadata;
there is no role-based branch, callback selection, closure selection, component
import, or physical equation dispatch.

`assemble_network_residuals(... include_pressure_unknowns=True,
include_pressure_residuals=True)` creates name/unit declarations only.
`build_binding_context(...)` validates explicit mappings only. Neither
evaluates residuals or physical callbacks.

The builder does not:

- infer hydraulic or thermal closures;
- evaluate physical residuals;
- predict branch flow or pressure distribution;
- instantiate or execute production components;
- construct `SystemState` or `FluidState`;
- call properties, correlations, CoolProp, or HX models;
- solve equations or add `solve(network)` / `NetworkGraph.solve()`.

## Spec validation review

Validated:

- non-empty typed scenario, component, node, connection, and branch IDs;
- role enum type;
- deterministic/read-only tags and metadata containers;
- duplicate component, node, connection-component, branch, and
  branch-component IDs;
- connection and branch self-loops;
- unknown component/node references;
- exact one-connection coverage for every component;
- ordered branch component connectivity from declared inlet to outlet;
- optional closed-single-loop structural validation during build.

Open/non-single-loop declarations remain explicitly supported by
`require_closed_loop=False`; this is topology support only.

## Build result and naming review

The frozen build result carries the validated spec, graph, declaration
assembly, binding context, deterministic IDs/names, limitations, and optional
read-only metadata. It contains no physical values or state objects.

Naming follows the existing declaration conventions:

- `mdot:<component_id>`
- `P:<node_id>`
- `mass_balance:<node_id>`
- `pressure_drop:<component_id>`

Ordering follows component and node declaration order.

## Validation results

All pytest runs used fresh repository-local base-temp roots and disabled the
pytest cache provider.

| Validation | Result |
|---|---:|
| Configurable scenario tests | 125 passed |
| Fixed-equivalence tests | 49 passed |
| Block 15D-C regressions | 104 passed |
| Block 15D-B regressions | 203 passed |
| Block 15D-A regressions | 205 passed |
| Block 15C-B regressions | 152 passed |
| Network suite | 2733 passed |
| Full suite | 6594 passed |
| Skipped / xfailed / deselected | 0 / 0 / 0 |

All six required examples passed:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

Quality gates:

- Ruff: passed.
- Black: passed.
- `git diff --check`: passed.

Two stale pre-audit `.pytest_15ea_full` and `.pytest_15ea_network` directories
were permission-locked. They were not reused, fresh uniquely named roots
passed, and the stale directories were removed with verified workspace-local
elevated cleanup. Immediate post-test deletion of the final focused temp roots
also encountered transient Windows locks when cleanup was chained in the same
shell command; standalone pytest commands exited 0, and the roots were removed
afterward with verified elevated cleanup. No pytest collection or execution
error occurred.

## Boundary-search review

Searches covered CoolProp/property/correlation registries, production
`contribute`, `SystemState`/`FluidState`, `component_type`, roles, solve APIs,
production component/HX imports, file writes, phase/property/HX terminology,
and numerical root/least-squares functions.

Classifications:

- Executable allowed: role type validation, role-to-graph metadata label,
  report role serialization, graph/assembly/binding construction.
- Documentation negative statements: architecture limitations and deferred
  capabilities.
- Test negative assertions: absence of imports, state objects, solve methods,
  and production execution.
- Executable suspicious: none.
- Prohibited: none.

No production `def contribute`, `.contribute(...)` call, configurable-scenario
property/HX/correlation import, state construction, file write, or solver call
was found.

## Production-contract regression

All known production classes remain `NO_CONTRIBUTE_METHOD`:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`PROJECT_STATUS.md` now records the declaration-only capability, structural
equivalence, exact final counts, audit reference, limitations, and deferred
work without claiming physical simulation.

## Findings and corrective changes

### Critical

None.

### Major

None.

### Minor fixed

- Moved missing component-connection detection from builder time to scenario
  spec validation.
- Rejected connection and branch self-loops.
- Rejected duplicate component IDs within a branch.
- Validated branch component ordering and endpoint connectivity.
- Validated tag element types and non-empty values.
- Added direct fixed/configurable ordered graph-edge comparisons.
- Corrected stale project-status phase text and validation counts.

### Minor remaining

None.

## Deferred items

Later blocks remain responsible for configurable physical residual selection,
production component adapters/execution, property/correlation/HX-backed
closures, combined physical residual assembly, rank/solvability analysis, and
physically predictive solves.

## Readiness

Block 15E-A is ready within its controlled configurable
declaration/assembly scope. It is merge-ready after the audit commit and
successful branch push.
