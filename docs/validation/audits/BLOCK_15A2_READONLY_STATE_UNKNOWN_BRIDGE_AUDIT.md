# Block 15A.2 Read-only State/Unknown Bridge Audit

## Verdict

**APPROVED WITH MINOR FIXES.**

No critical or major findings remain. One minor documentation inconsistency was
corrected during the audit. Block 15A.2 is ready to merge.

## Branch and commits

- Branch audited: `phase-15a2-readonly-state-unknown-bridge`
- Base commit: `8058b4a` (`main`, merge of Block 15A.1)
- HEAD before audit: `8058b4a`
- Implementation state before audit: uncommitted changes in the four expected
  Block 15A.2 files

## Scope audited

- `src/mpl_sim/network/readonly_state_bridge.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_readonly_state_bridge.py`
- `docs/roadmap/PROJECT_STATUS.md`
- Block 15A.1 compatibility and production-contract regression
- Architecture boundary searches across network source, network tests,
  components, and project status documentation

No frozen architecture document was modified.

## Public API added

- `ReadOnlyUnknownView`
- `ComponentUnknownView`
- `NodeUnknownView`
- `build_readonly_unknown_view`

All four names are explicitly imported and listed in `mpl_sim.network.__all__`.

## Source and API review

`ReadOnlyUnknownView` is a frozen dataclass. It defensively copies the supplied
mapping into `MappingProxyType`, validates non-empty string keys, rejects bool,
non-numeric, NaN, and infinite values, and requires exact coverage of the
unknowns declared by the binding context assembly. Raw lookup rejects
wrong-type, empty, whitespace-only, and undeclared names.

`for_component(...)` requires `ComponentInstanceId`, rejects IDs outside the
binding set, and exposes only entries declared by
`ComponentStateMap.unknown_to_component`. Components with no mapped unknowns
receive an explicit empty, read-only view.

`for_node(...)` requires `GraphNodeId`, rejects IDs outside the graph, and
exposes only entries declared by `ComponentStateMap.unknown_to_node`. Nodes with
no mapped unknowns receive an explicit empty, read-only view.

The factory accepts only `NetworkBindingContext` plus either
`NetworkUnknownValues` or `Mapping`. It returns the same immutable,
exact-coverage-validated view.

The implementation does not infer semantics from unknown names or
`component_type`, does not attach values to graph or component objects, and
does not construct residuals.

## Block 15A.1 integration

`ProductionBridgeExecutionContext` and
`production_component_bridge.py` were not modified. A controlled bridge can
use:

```python
build_readonly_unknown_view(ctx.binding_context, ctx.unknown_values)
```

inside `produce_records(...)`. The full 75-test Block 15A.1 bridge suite remains
backward-compatible.

## Validation results

All required commands passed on 2026-06-22:

| Validation | Result |
|---|---:|
| `pytest tests/network/test_readonly_state_bridge.py -q --basetemp=.pytest_tmp` | 61 passed |
| `pytest tests/network/test_production_component_bridge_boundary.py -q --basetemp=.pytest_tmp` | 75 passed |
| `pytest tests/network -q --basetemp=.pytest_tmp` | 1325 passed |
| `pytest -q --basetemp=.pytest_tmp` | 5186 passed |
| Skipped | 0 |
| Xfailed | 0 |
| Deselected | 0 |
| `ruff check src tests examples` | passed |
| `black --check --no-cache --verbose src tests examples` | passed; 185 files unchanged |
| `git diff --check` | passed |

The first focused run emitted one `PytestCacheWarning` because an existing
workspace `.pytest_cache` directory was not writable. The required
repository-local `.pytest_tmp` basetemp worked, and all test commands passed.

## Example execution

All six required examples exited successfully:

- `examples/minimal_evaporator_condenser_loop.py`
- `examples/fixed_heat_rate_hx.py`
- `examples/segmented_counterflow_hx.py`
- `examples/minimal_closed_mpl_solver.py`
- `examples/minimal_pressure_closure.py`
- `examples/minimal_coupled_closure.py`

## Boundary-search results

Required text searches and AST-backed tests were reviewed and classified:

- `CoolProp`, `PropertyBackend`, and `CorrelationRegistry` hits in the new
  module are documentation-only negative boundary statements.
- Corresponding network-test hits are test descriptions and negative
  assertions.
- No executable forbidden import exists in
  `readonly_state_bridge.py`.
- `SystemState` and `FluidState` hits are documentation or negative tests; no
  import, construction, or assembly exists.
- `component_type` hits are documentation, fixture construction, and an AST
  negative assertion; the new module performs no attribute access or physics
  inference.
- `contribute(` and `.contribute(` hits are existing documentation, test
  fixtures for the Phase 14G inspector, and negative assertions. No new
  executable definition or call exists.
- The only executable network solve entry point remains the existing
  `solve_network_residual_problem`; no `solve(network)` or
  `NetworkGraph.solve()` was added.
- No `mpl_sim.properties`, `mpl_sim.components`, or
  `mpl_sim.correlations` import exists in the new module.

No prohibited boundary hit was found.

## Production-contract regression

`inspect_known_production_component_contracts()` reports
`NO_CONTRIBUTE_METHOD` for all six known production classes:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`PROJECT_STATUS.md` accurately records Block 15A.2 as a checkpoint. It states
that the checkpoint adds a read-only unknown-vector view for bridge providers,
does not assemble `SystemState`, does not create `FluidState`, does not execute
production components, and does not define or call
`Component.contribute(...)`. Block 15B physical single-loop simulation and
arbitrary-topology physical simulation remain deferred.

No separate roadmap file was created.

## Findings

### Critical

None.

### Major

None.

### Minor fixed

- `PROJECT_STATUS.md` sections 4, 5, the closeout-artifact list, and the final
  status note still described Block 15A.1 as the active/unmerged checkpoint.
  They were updated to the audited Block 15A.2 state and exact validation
  counts.

### Minor remaining

None.

## Corrective changes made

- Corrected stale Block 15A.1 wording in `docs/roadmap/PROJECT_STATUS.md`.
- Added this independent audit record.

No implementation or architecture change was required.

## Deferred items

- Real production-component execution
- `SystemState` assembly
- `FluidState` construction
- Production `Component.contribute(...)`
- Block 15B physical single-loop network simulation
- Arbitrary-topology physical simulation
- Generic `solve(network)` or `NetworkGraph.solve()`

## Merge readiness

**Yes.** Block 15A.2 is merge-ready after the audit commit and successful push
of `phase-15a2-readonly-state-unknown-bridge`.
