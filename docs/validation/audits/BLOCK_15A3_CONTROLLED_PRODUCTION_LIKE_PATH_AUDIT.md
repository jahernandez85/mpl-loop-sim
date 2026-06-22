# Block 15A.3 Controlled Production-like Path Audit

## Verdict

**APPROVED WITH MINOR FIXES — READY TO MERGE**

No critical or major findings remain. One minor context/view consistency issue
was corrected during audit.

## Branch and commits

- Branch: `phase-15a3-controlled-production-like-path`
- Base commit: `fabf64a09ca159f5c68b5f6b4292c42d5333660f`
- HEAD before audit: `fabf64a09ca159f5c68b5f6b4292c42d5333660f`

The Block 15A.3 implementation was present as uncommitted work on the expected
branch when the audit began.

## Scope audited

- `src/mpl_sim/network/production_like_bridge.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_production_like_bridge_path.py`
- `docs/roadmap/PROJECT_STATUS.md`
- relevant Phase 15A.1, Phase 15A.2, Phase 14D/14C, graph, binding, inspection,
  component, and architecture-boundary surfaces

No frozen architecture document was modified.

## Public API added

- `ProductionLikeBridgeContext`
- `ProductionLikeRecordProducerProtocol`
- `ProductionLikeComponentBinding`
- `ProductionLikeComponentSet`
- `execute_production_like_contributions(...)`
- `build_component_contribution_from_production_like_execution(...)`

All six names are exported intentionally from `mpl_sim.network`.

## Source and API review

- The producer protocol is runtime-checkable and requires only callable
  `produce_records(context)`.
- Component bindings require `ComponentInstanceId` and a callable producer.
- Component sets preserve order, are frozen, defensively normalize to a tuple,
  reject wrong item types, and reject duplicate component IDs.
- Execution validates exact binding coverage, exact unknown coverage, finite
  non-bool values, return types, record ownership, and duplicate records.
- Producer exceptions propagate.
- The result remains `ContributionRecordSet`.
- The convenience wrapper delegates through
  `map_contribution_records_to_component_contribution` and therefore retains
  the explicit `ContributionResidualMap`; it adds no residual-name inference.
- No production component is imported, instantiated, or executed.

## Pre-built ReadOnlyUnknownView design review

The design is acceptable after the audit fix.

The initial implementation accepted a caller-supplied `view` in the public
`ProductionLikeBridgeContext` constructor. That allowed a valid
`ReadOnlyUnknownView` to be paired with unrelated `binding_context` or
`unknown_values`, creating an inconsistent duplicate validation path.

The corrected context makes `view` an `init=False` frozen field and constructs
it only through `build_readonly_unknown_view(binding_context, unknown_values)`
inside `__post_init__`. The validated view then supplies the defensively copied
unknown-value mapping. Exact coverage and finite/non-bool validation therefore
remain centralized in the Block 15A.2 factory. No `SystemState` or `FluidState`
is created, and no physical values are attached to graph, component, node, or
port objects.

## Validation results

Commands were run with repository-local pytest temporary directories.

| Validation | Result |
|---|---:|
| `pytest tests/network/test_production_like_bridge_path.py -q --basetemp=.pytest_tmp` | 55 passed |
| `pytest tests/network/test_production_component_bridge_boundary.py -q --basetemp=.pytest_tmp` | 75 passed |
| `pytest tests/network/test_readonly_state_bridge.py -q --basetemp=.pytest_tmp` | 61 passed |
| `pytest tests/network -q --basetemp=.pytest_tmp` | 1380 passed |
| `pytest -q --basetemp=.pytest_tmp` | 5241 passed |
| skipped / xfailed / deselected | 0 / 0 / 0 |
| `ruff check src tests examples` | passed |
| `black --check --no-cache --verbose src tests examples` | passed; 187 files unchanged |
| `git diff --check` | passed |

Pytest emitted only the pre-existing Windows warning that `.pytest_cache`
could not be written; the requested `.pytest_tmp` base directory worked and all
test commands completed successfully.

## Example results

All six examples completed successfully:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

## Boundary searches

Required searches covered CoolProp, `PropertyBackend`, `CorrelationRegistry`,
production components, HX models, correlation packages, `SystemState`,
`FluidState`, `component_type`, `contribute`, and generic network solve forms.

Classification:

- Executable allowed: normal imports from the network binding, contribution,
  graph, and read-only-view modules; the existing explicitly named
  `solve_network_residual_problem` outside the new module.
- Executable suspicious: none.
- Documentation negative statements: hits describing prohibited behavior.
- Test negative assertions: AST/source checks and contract-inspection fixtures.
- Prohibited: none.

The new module has no executable import or reference to `SystemState`,
`FluidState`, CoolProp, `PropertyBackend`, `CorrelationRegistry`, HX models,
production components, or correlations. It neither defines nor calls
`contribute`, does not inspect `component_type`, and provides no
`solve(network)` or `NetworkGraph.solve()` path.

## Production contract regression

Phase 14G inspection still reports `NO_CONTRIBUTE_METHOD` for all six known
production classes:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`docs/roadmap/PROJECT_STATUS.md` now accurately states that Block 15A.3 is a
checkpoint, uses explicitly supplied production-like producers and the Block
15A.2 read-only view, and does not execute production components, define or call
`Component.contribute(...)`, assemble `SystemState`, create `FluidState`, call
properties/correlations/HX models, or implement Block 15B or arbitrary-topology
physical simulation. The stale active-phase and next-action sections were
updated, and this audit is referenced without creating a separate roadmap file.

## Findings

### Critical

None.

### Major

None remaining.

### Minor fixed

1. `ProductionLikeBridgeContext` initially accepted an independently supplied
   view, permitting inconsistent context state. The view is now constructed
   internally and exclusively through `build_readonly_unknown_view`.
2. Roadmap active-phase, next-action, audit-reference, date, and validation
   status text still described Block 15A.2. These sections were updated for
   Block 15A.3.
3. One audit-added unused test local was removed before final lint validation.

### Minor remaining

None.

## Deferred items

- Real production component execution
- Production `Component.contribute(...)`
- `SystemState` assembly and `FluidState` construction
- Physical Block 15B single-loop simulation
- Generic or arbitrary-topology physical simulation
- Automatic property, correlation, HX-model, or component-type physics

## Merge readiness

**Yes.** Block 15A.3 is ready to merge after the audit commit is created and
the expected remote is verified. It must not be merged into `main` by this
audit branch workflow.
