# Phase 11 HeatExchangerModel, Evaporator and Condenser Foundation Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

The `phase-11-heat-exchanger-model` branch implements a clean Phase 11 foundation checkpoint. It adds the `HeatExchangerModel` contract, secondary boundary-condition value objects, a separate `HeatExchangerModelRegistry`, a V1 `EpsilonNTUModel` fixed-heat-rate path, and foundational Evaporator and Condenser wrappers that delegate to injected HX models and correlations.

The branch preserves the frozen architecture boundaries: HX models are not correlations, the HX model registry is separate from the correlation registry, components remain local and value-free at their ports, and no Network, Solver, PropertyBackend construction, or direct CoolProp dependency is introduced into `hx_models/` or the new HX components.

This is not full Phase 11 completion. The roadmap's full Phase 11 scope still includes full sink-side epsilon-NTU behavior, numeric LMTD, segmented march, moving-boundary seam activation beyond declaration, migrated boiling/condensation HTC and two-phase DP closures, and full loop residual integration. Those are deferred continuation items after this checkpoint merge.

## Scope Audited

Source files inspected:

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/registry.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/components/base.py`
- `src/mpl_sim/components/pipe.py`
- `src/mpl_sim/components/pump.py`
- `src/mpl_sim/components/accumulator.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/registry.py`
- adjacent packages under `core/`, `geometry/`, `calibration/`, `network/`, `solvers/`, `properties/`, `schema/`, `results/`, and `validation/`

Tests inspected:

- `tests/hx_models/test_hx_model_contract.py`
- `tests/hx_models/test_hx_model_registry.py`
- `tests/hx_models/test_secondary_bc.py`
- `tests/hx_models/test_epsilon_ntu_model.py`
- `tests/hx_models/test_hx_model_architecture_boundaries.py`
- `tests/components/test_evaporator_component.py`
- `tests/components/test_condenser_component.py`
- `tests/components/test_heat_exchanger_component_boundaries.py`
- adjacent component, correlation, network, solver, schema, result, property, geometry, and calibration tests as relevant

Documentation consulted:

- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/PROJECT_STATUS.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_CLOSEOUT_AUDIT.md`
- `docs/validation/audits/PHASE_9_SCHEMA_RESULTS_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_FINAL_AUDIT.md`

## Commands Executed

- `git branch --show-current` - `phase-11-heat-exchanger-model`
- `git status` - clean working tree on `phase-11-heat-exchanger-model`; Git warned that `C:\Users\AndresH/.config/git/ignore` was permission-denied.
- `git log --oneline --decorate -8` - HEAD is `72854d4 feat: add heat exchanger model and hx component foundations`; `main` is at `5d10eee docs: close out phase 10 pump and accumulator`.
- `git diff --stat main...HEAD` - 16 files changed, 3625 insertions, 2 deletions. The diff is limited to HX model files, Evaporator/Condenser/component exports, and Phase 11 tests.
- `pytest` - 2235 passed, 1 Windows `.pytest_cache` permission warning.
- `ruff check .` - passed.
- `black --check src tests` - passed; 113 files would be left unchanged.
- `pytest tests/hx_models tests/components` - 835 passed, 1 Windows `.pytest_cache` permission warning.

Architecture-boundary searches:

- `Select-String ... 'CoolProp'` over `src/mpl_sim/hx_models` and `src/mpl_sim/components` found documentation/comment references only; no direct CoolProp import or call in the audited implementation.
- `Select-String ... 'mpl_sim.network'` over `src/mpl_sim/hx_models` and `src/mpl_sim/components` found no matches.
- `Select-String ... 'mpl_sim.solvers'` over `src/mpl_sim/hx_models` and `src/mpl_sim/components` found no matches.
- `Select-String ... 'CorrelationRegistry'` over `src/mpl_sim/hx_models` found only registry-separation comments in `registry.py`; no dependency.
- `Select-String ... 'CorrelationRole.*LMTD|CorrelationRole.*NTU|HEAT_EXCHANGE'` over `src/mpl_sim/correlations` and `src/mpl_sim/hx_models` found no matches.
- `Select-String ... '\.get\('` over `src/mpl_sim/hx_models` and `src/mpl_sim/components` found one use: `roughness=gs.get("roughness", 0.0)` in `epsilon_ntu.py`, documented and tested as an optional smooth-wall assumption.
- `Select-String ... 'NotImplementedError'` over `src/mpl_sim/hx_models` and `src/mpl_sim/components` found only `UnsupportedHeatExchangerBoundaryConditionError(NotImplementedError)` in `base.py`, used for explicit unsupported BC rejection.
- Search for dangerous hidden defaults (`D_h = 1e-3`, `rho = 1.0`, `mu = 1e-5`, `L_cell = 1.0`, `G = primary_mdot`, `x = 0.0`) found no matches.

## Audit Checklist

### HeatExchangerModel Separation

Pass. `HeatExchangerModel` is an ABC strategy with `kind()` and `solve()`, not a `Correlation`. `HeatExchangerModelKind` owns `EPSILON_NTU`, `LMTD`, `SEGMENTED_MARCH`, and `MOVING_BOUNDARY`; these are not `CorrelationRole` values. `HeatExchangerModelRegistry` is independent from `CorrelationRegistry`, stores `HeatExchangerModel` instances only, and rejects non-HX-model registration.

`hx_models/` avoids Network, Solver, PropertyBackend, and CoolProp imports. `EpsilonNTUModel` does not resolve any registry internally. It consumes injected `htc_primary`, `htc_secondary`, and `dp_primary` correlation objects from `HXSolveRequest`; V1 uses primary HTC and DP paths for fixed-heat-rate evaluation and verdict propagation.

### EpsilonNTUModel

Pass for foundation scope. V1 clearly supports only `FixedHeatRate`; `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling` raise `UnsupportedHeatExchangerBoundaryConditionError` with specific messages. The fixed-heat-rate sign convention is documented and tested: positive `Q` raises primary enthalpy, negative `Q` lowers it, and `h_out = h_in + Q / mdot`.

`primary_state_out` is a new `FluidState`, not stored on a Port or component. `dP_primary` is derived from the injected `dp_primary` correlation when present. The no-DP-correlation path returns neutral `0.0` DP and leaves outlet pressure unchanged; that neutral seam is explicit and tested. Correlation verdicts are propagated into `HXSolveResult.verdicts`. Calibration multipliers are reported, friction scales DP output, and fixed-heat-rate conservation is not altered by HTC or friction multipliers.

### Hidden Physical Defaults

Pass with one acceptable optional default. Required physical scalars are explicit and finite:

- HTC input requires `G`, `D_h`, and `x`.
- DP input requires `G`, `D_h`, `L_cell`, `rho`, and `mu`.
- `rho` and `mu` must be positive.

Missing required keys raise `ValueError` with clear messages naming the missing key and available keys. No dangerous fallback values remain for `D_h`, `rho`, `mu`, `L_cell`, `G`, or `x`. The only remaining `.get()` is `roughness=gs.get("roughness", 0.0)`, documented as a smooth-wall assumption and covered by tests.

### EvaporatorComponent

Pass for foundation scope. `EvaporatorComponent` is a frozen local component with exactly inlet and outlet ports. Ports are constructed as connectivity-only `Port` objects with no values. The component owns inert `MicrochannelGeometry` and declares `T_wall` as a named frozen internal-state seam, without storing derived thermodynamic state.

The HX model slot is supplied through `EvaporatorHXInput.model`, separate from `htc_primary` and `dp_primary` correlation slots. The component builds an `HXSolveRequest` from caller-supplied state, mass flow, secondary BC, discretization, geometry scalars, correlations, and calibration multipliers, then delegates to the injected model. It does not store scenario state on the component and does not import Network, Solver, properties, or CoolProp.

### CondenserComponent

Pass for foundation scope. `CondenserComponent` is a frozen local component with exactly inlet and outlet ports and inert `PlateGeometry`. It declares no V1 internal states and stores no derived T, quality, HTC, DP, UA, or profile data.

The HX model slot is supplied through `CondenserHXInput.model`, separate from primary HTC, secondary HTC, and DP correlation slots. Secondary BCs are passed explicitly through the input object. The component delegates to the injected HX model and avoids Network, Solver, properties, and CoolProp. It does not pretend to implement validated condenser physics; fixed heat-rate behavior is a foundation path and unsupported physical BCs remain explicit model-level errors.

### Layer Boundaries

Pass. The branch does not modify Pump, Accumulator, Network, Solver, schema/result/validation primitives, property backends, calibration primitives, or geometry primitives beyond adding component exports. `git diff --name-only main...HEAD` is limited to HX model source, Evaporator/Condenser source, component exports, and tests. Existing Phase 10 pressure-reference wiring and solver behavior are untouched.

### Tests

Pass. Tests cover the contract and architectural boundaries, not only happy paths:

- HX model contract, kind enumeration, immutable solve requests, result shape, and registry separation.
- Unsupported secondary BCs.
- FixedHeatRate sign convention and `Q / mdot` enthalpy updates.
- DP correlation use, neutral no-DP path, verdict propagation, and friction multiplier behavior.
- Missing required scalar failures and optional roughness behavior.
- HX models not being correlations and epsilon-NTU/LMTD not being `CorrelationRole` entries.
- Network/Solver/CoolProp/property import boundaries.
- Evaporator and Condenser ports, local delegation, model/correlation slot separation, no stored derived state, and Phase 10 component boundary preservation.

No suspicious test pattern was found where dummy defaults hide missing physical data in `EpsilonNTUModel`; the missing-scalar tests intentionally exercise the failure paths.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- `EvaporatorHXInput` and `CondenserHXInput` use `geom_scalars: Mapping[str, float] = ()` and normalize non-mappings to `{}` in `__post_init__`. This is not a physical hidden default and is not a merge blocker, but a future cleanup could use a conventional `default_factory=dict` for readability if the codebase later allows mutable-default-safe factories on these input dataclasses.
- `HXSolveRequest.htc_secondary` exists and Condenser forwards it, but `EpsilonNTUModel` V1 does not use the secondary HTC path. This is acceptable for the fixed-heat-rate foundation because sink-side epsilon-NTU physics is explicitly deferred.

## Deferred Items

The following remain deferred Phase 11 continuation items:

- full `SinkInletTempAndFlow` epsilon-NTU solve;
- `FixedWallTemp` and `AmbientCoupling` evaluation;
- numeric LMTD model;
- segmented-march model;
- moving-boundary model beyond declared kind/seam;
- boiling and condensation HTC closure migrations;
- two-phase DP closure migrations;
- secondary-side HTC/UA integration for real sink-driven HX calculations;
- quality/property-bound validation through the property backend;
- full loop residual integration with Evaporator and Condenser;
- physical validation/literature harness activation;
- DOE/surrogate generation;
- dynamics and control.

## Phase Classification

This branch is a **Phase 11 foundation/checkpoint that should be merged before continuing Phase 11**.

It is not full Phase 11 completion. `IMPLEMENTATION_PLAN.md` full Phase 11 acceptance expects a complete loop with HX models consuming correlations and secondary BCs, strategy swap readiness across epsilon-NTU/LMTD/segmented paths, migrated HTC and DP closures, and physical Evaporator/Condenser behavior. This branch intentionally implements only the contract, registry, V1 fixed-heat-rate path, and component delegation foundation.

## Merge Readiness

`phase-11-heat-exchanger-model` is safe to merge as a Phase 11 checkpoint.

The branch has no observed architecture violations, no failing tests, no lint/format failures, and no source/test blockers. Continue Phase 11 after merge with sink-side HX physics, LMTD/segmented strategies, correlation migrations, and loop integration.

