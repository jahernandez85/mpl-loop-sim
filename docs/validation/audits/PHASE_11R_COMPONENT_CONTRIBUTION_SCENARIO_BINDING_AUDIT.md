# Phase 11R Component Contribution Scenario Binding Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11R adds immutable evaporator and condenser scenario-binding value
objects and narrow `evaluate_scenario(...)` helpers. The helpers combine
explicit runtime primary state and mass flow with a pre-bound scenario, build
the existing component HX input type, and delegate to
`evaluate_heat_exchanger()`.

This focused re-audit confirms that both previous major findings are resolved:

1. the incompatible methods named `contribute(primary_state_in,
   primary_mdot, scenario)` were removed and replaced with
   `evaluate_scenario(...)`; and
2. each scenario binding now stores `geom_scalars` as a defensive
   `MappingProxyType(dict(...))` copy, preventing both nested mutation and
   aliasing through the caller's source dictionary.

The new helpers are explicitly documented as separate from the frozen
`contribute(trial, ctx) -> ComponentContribution` contract in
`INTERFACE_SPEC.md` section 11.1. That contract remains deferred.

No critical, major, or minor finding remains.

## Scope Audited

- `docs/architecture/INTERFACE_SPEC.md`
- `docs/roadmap/PROJECT_STATUS.md`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `src/mpl_sim/components/__init__.py`
- `tests/components/test_evaporator_condenser_contribution_scenario_binding.py`
- component, HX-model, correlation, registry, network, and solver boundaries

No architecture document, HX model, correlation implementation, registry,
network, solver, valve, manifold, or moving-boundary implementation was
modified. No accidental `src/mpl_sim/components/init.py` exists.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11r-component-contribution-scenario-binding`
- `git status --short --branch`
  - expected Phase 11R component, test, and status paths only before closeout
- `git log --oneline --decorate -10`
  - branch base and `main`: `77c1282`
- `git diff --stat`
  - component wrappers, package exports, and status changes only before audit
- `git diff --stat main...HEAD`
  - empty because implementation remained uncommitted at audit start
- `git diff --cached --stat`
  - empty at audit start
- `git diff --check`
  - clean

Git emitted non-blocking warnings that the user-level ignore file could not be
read.

### Validation

- `pytest`
  - passed: `3380 passed`
- `pytest tests/correlations`
  - passed: `512 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1718 passed`
- `pytest tests/components/test_evaporator_condenser_contribution_scenario_binding.py -v`
  - passed: `77 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `135 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## Previous Blocking Findings and Resolution

### Frozen contribute contract

Resolved.

`INTERFACE_SPEC.md` section 11.1 freezes the component contribution signature
as:

```text
contribute(trial: ComponentTrialState, ctx: EvalContext)
    -> ComponentContribution
```

Neither `EvaporatorComponent` nor `CondenserComponent` now defines a
`contribute` method. The Phase 11R adapter is named `evaluate_scenario`, returns
`HXSolveResult`, and is consistently described as a scenario-bound evaluation
helper rather than the frozen contribution contract.

Focused tests assert that both components have `evaluate_scenario` and do not
have `contribute`. `PROJECT_STATUS.md` explicitly states that the frozen
contract remains deferred.

### Scenario binding immutability

Resolved.

Both scenario bindings are frozen dataclasses. Their only mapping field,
`geom_scalars`, is typed as `Mapping[str, float]` and converted during
construction to a defensive `MappingProxyType(dict(...))` copy.

Runtime and focused-test evidence confirms:

- direct dataclass field assignment raises `FrozenInstanceError`;
- replacing or adding an entry through `binding.geom_scalars[...]` raises
  `TypeError`;
- mutation of the original source dictionary after construction does not
  alter the binding;
- no closure or physical scalar default was added by the correction.

## Scenario Binding API Verification

`EvaporatorScenarioBinding` and `CondenserScenarioBinding` mirror every
corresponding `*HXInput` field except the explicit runtime fields
`primary_state_in` and `primary_mdot`.

The bindings carry:

- secondary boundary condition and HX model;
- discretization;
- immutable geometry-scalar mapping;
- primary and secondary HTC correlations;
- primary DP correlation;
- HTC and friction multipliers;
- primary thermal fields and UA computation mode;
- `q_flux_primary`;
- `dp_primary_is_two_phase`.

Both types are exported from `mpl_sim.components` and included in `__all__`.

## Scenario Helper Verification

Both `evaluate_scenario(...)` methods:

- accept explicit `primary_state_in` and `primary_mdot` runtime values;
- accept the corresponding immutable scenario binding;
- construct the correct existing `EvaporatorHXInput` or `CondenserHXInput`;
- forward every scenario field without closure selection or inferred values;
- delegate directly to `evaluate_heat_exchanger()`;
- do not duplicate `HXSolveRequest` construction;
- do not access a registry, property backend, network, or solver;
- do not infer phase from `FluidState`;
- produce the same HX result semantics as direct
  `evaluate_heat_exchanger()` for equivalent inputs.

Evaporator tests cover explicit Shah boiling HTC, q-flux forwarding,
two-phase MSH DP, missing q-flux, and missing two-phase DP scalars. Condenser
tests cover explicit Yan condensation HTC, optional MSH two-phase DP, omitted
q-flux, and missing two-phase DP scalars.

## Test Coverage

The 77 focused tests cover:

- absence of incompatible `contribute` methods;
- availability and behavior of `evaluate_scenario`;
- frozen field assignment;
- read-only nested mappings;
- source-dictionary isolation;
- default behavior and energy balance;
- q-flux and two-phase-DP mode forwarding;
- exact geometry-scalar forwarding;
- scenario-helper/direct-evaluation result equivalence;
- Shah and Yan success paths;
- missing q-flux and missing DP-scalar failures;
- no automatic Shah, Yan, or MSH selection;
- no component registry resolution;
- no CoolProp or `PropertyBackend` import;
- package exports.

The tests exercise `evaluate_scenario()` directly and do not merely repeat
`evaluate_heat_exchanger()` coverage.

## Critical Searches

Searches found:

- no `def contribute` in components or component tests;
- the expected `evaluate_scenario`, scenario-binding, `MappingProxyType`, and
  `geom_scalars` references;
- no prohibited CoolProp or `PropertyBackend` implementation dependency;
- no Network or Solver import in components or HX models;
- no `CorrelationRegistry` resolution in components or HX models;
- no hidden production density, viscosity, diameter, quality, length, heat
  flux, or heat-capacity defaults;
- no accidental package `init.py`.

Matches for dependency names were comments/docstrings documenting boundaries,
existing registry documentation, or explicit test fixture values.

## Findings

### Critical Findings

None.

### Major Findings

None. Both prior major findings are resolved.

### Minor Findings

None. Stale pre-audit test counts in `PROJECT_STATUS.md` were corrected during
closeout.

## Deferred Items

- frozen `contribute(trial, ctx) -> ComponentContribution` implementation;
- remaining two-phase HTC and DP closures;
- broader counterflow and phase-change segmented coupling;
- moving-boundary modeling;
- full-loop convergence acceptance;
- validation harnesses and later valves/manifolds.

## Phase Classification

Phase 11R is an approved component-level checkpoint. Phase 11 remains open.

## Merge Readiness

`phase-11r-component-contribution-scenario-binding` is approved for merge into
`main` as a Phase 11R checkpoint after the two closeout commits are created and
pushed. This audit does not authorize or perform the merge.
