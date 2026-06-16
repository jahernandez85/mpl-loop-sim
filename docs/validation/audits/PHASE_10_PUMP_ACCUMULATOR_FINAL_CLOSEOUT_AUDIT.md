# Phase 10 Pump and Accumulator Final Closeout Audit

## Verdict

**APPROVED FOR MERGE AND NEXT PHASE**

## Summary

The previous Phase 10 audit approved the first Pump and Accumulator foundation as a safe checkpoint only. It did not close Phase 10 because pump map/command behavior, pump power and shaft-speed seams, accumulator `V_g`, `VolumePressureLaw` integration, PCA/HCA coverage, network pressure-reference wiring, and the minimal pump-driven accumulator-referenced loop shape were still pending.

The current `phase-10b-pump-map-accumulator-law` branch implements the remaining Phase 10 scope at the planned V1 fidelity. Pump map/command and power seams are local and deterministic; accumulator pressure-law binding and `V_g` named state are present; the `VOLUME_PRESSURE_LAW` role has a PCA closure; Network owns identity-only pressure-reference wiring; and tests cover the minimal pump-driven, accumulator-referenced acceptance shape without inventing physical convergence.

Phase 10 is complete and safe to merge into `main`. The project is ready to advance to Phase 11 after merge.

## Scope Audited

Source files inspected:

- `src/mpl_sim/components/base.py`
- `src/mpl_sim/components/pipe.py`
- `src/mpl_sim/components/pump.py`
- `src/mpl_sim/components/accumulator.py`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/registry.py`
- `src/mpl_sim/correlations/volume_pressure_law.py`
- `src/mpl_sim/correlations/__init__.py`
- `src/mpl_sim/network/topology.py`
- `src/mpl_sim/network/validation.py`
- `src/mpl_sim/network/assembly.py`
- `src/mpl_sim/network/__init__.py`
- `src/mpl_sim/core/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/solvers/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/schema/`
- `src/mpl_sim/results/`
- `src/mpl_sim/validation/`
- `pyproject.toml`

Test files inspected:

- `tests/components/test_pump_component.py`
- `tests/components/test_accumulator_component.py`
- `tests/correlations/test_volume_pressure_law_contract.py`
- `tests/correlations/test_pca_volume_pressure_law.py`
- `tests/network/test_pressure_reference.py`
- `tests/network/test_pump_accumulator_loop.py`
- `tests/network/test_network_assembly.py`
- adjacent component, correlation, network, solver, schema, result, property, geometry, calibration, validation, and unit tests

Documentation inspected:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_9_SCHEMA_RESULTS_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_7_NETWORK_ASSEMBLY_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`

## Audit Checklist

**Pump foundation:** `PumpComponent` remains a frozen dataclass implementing the component contract, with one inlet and one outlet port, `ComponentKind.PUMP`, value-free ports, no `SystemState` mutation, and no Network, Solver, CoolProp, or `PropertyBackend` dependency.

**Pump map and command:** `PumpGeometry`, `PumpMapPoint`, `PumpPerformanceMap`, `PumpSpeedCommand`, `PumpFlowTarget`, `PumpPowerInput`, and `PumpPowerSummary` are immutable or data-only. Scalar inputs reject NaN/infinity where they are evaluated. Command binding validates the target pump id. Existing prescribed pressure-rise behavior remains backward compatible. Map evaluation is deterministic and local. The sign convention remains explicit. The power/efficiency seam uses only caller-supplied `mdot`, `delta_p`, `specific_volume`, and `efficiency`. `internal_state_names()` includes `"omega"` as the frozen shaft-speed seam. No dynamic derivative, controller, network solve, or solver call is implemented.

**VolumePressureLaw / PCA / HCA:** `CorrelationRole.VOLUME_PRESSURE_LAW` and `VolumePressureLawInput` exist. The input is scalar/data-only and does not receive Component, Geometry, or Accumulator objects. `PcaVolumePressureLaw` implements the polytropic PCA relation `P = P_charge * (V_charge / V_g) ** n`, returns positive pressure for valid positive inputs, rejects invalid law parameters, reports `OUT_OF_RANGE` for invalid `V_g`, and is tested for hand-calculated values and monotonic pressure decrease as `V_g` increases. HCA is declared as a V1 seam only; this is acceptable for closeout because the docs mark HCA as "if feasible" from legacy support, while PCA and the interchangeable law slot carry the Phase 10 V1 acceptance.

**Accumulator law slot and `V_g`:** `AccumulatorComponent` remains local and immutable, with one bidirectional fluid port and containment-only `AccumulatorGeometry`. It does not store `P_sys`, place pressure values on ports, integrate inventory, flash thermodynamics, or compute mass/energy balances. `VolumePressureLawBinding` is data-only and mutation-isolated. `internal_state_names()` includes `"V_g"`. `evaluate_volume_pressure_law()` builds a `VolumePressureLawInput` from explicit `V_g`, containment `V_total`, and law parameters, delegates to the caller-supplied correlation, and returns the derived pressure summary without mutating the component.

**Network pressure-reference wiring:** Network owns identity-only pressure-reference wiring through `PressureReferenceWiring` and `NetworkTopology`. Exactly one pressure reference is enforced when pressure references are declared. Zero and multiple references are rejected; missing components are rejected; non-accumulator components are rejected. The wiring stores component/port identity only and carries no pressure value. Network does not evaluate accumulator laws, import volume-pressure closures, solve pressure, or call Solver.

**Minimal pump-driven accumulator-referenced loop acceptance:** `tests/network/test_pump_accumulator_loop.py` covers the planned acceptance shape: pump command binding, pump map pressure contribution, accumulator PCA pressure derivation from `V_g`, and a Network topology with exactly one accumulator pressure reference. It intentionally does not fake full physical convergence or residual assembly.

**Layer boundaries:** Components do not import Network, Solvers, CoolProp, or `PropertyBackend`. Pump does not import correlations. Accumulator imports only the correlation contract, not the registry or concrete law closures. Correlation closures do not import components, geometry, network, solvers, properties, or CoolProp. Network imports generic component structure, not concrete Pump/Accumulator classes, and does not call law evaluation. Solvers remain generic and do not import Pump, Accumulator, or volume-pressure laws. Ports remain value-free; `SystemState` remains the owner of numerical state values.

**Tests:** Tests cover Pump construction, port roles, kind, immutability, prescribed pressure rise, map behavior, command binding, wrong binding, finite scalar validation, sign convention, power/efficiency, shaft-speed seam, and import boundaries. Accumulator tests cover construction, bidirectional port, geometry containment, immutability, prescribed reference seam, law binding, `V_g`, PCA-derived pressure, invalid `V_g` behavior through the law, no `P_sys`, no law parameters in geometry, and import boundaries. Correlation tests cover the role, input contract, PCA validation, hand calculations, monotonicity, HCA seam decision, and import boundaries. Network tests cover exactly-one pressure reference, zero/multiple references, missing and invalid referenced components, identity-only wiring, and the pump/accumulator acceptance shape.

**Phase 10 completeness:** The remaining Phase 10 items from the previous checkpoint are now complete at V1 fidelity. Full physical loop convergence remains a later residual/solver integration concern; it is not required by this closeout because no residual assembly for the pump/accumulator loop is planned in this slice.

**Branch merge readiness:** `phase-10b-pump-map-accumulator-law` is safe to merge into `main`.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- `PressureReferenceWiring.port_name` is stored but the pressure-reference validation currently checks the referenced component kind rather than explicitly verifying that the referenced port name exists on that component. Existing connection validation catches bad connection ports, and the planned pressure-reference identity is primarily component-level, so this is not a Phase 10 merge blocker. A focused follow-up test/check would make the wiring contract tighter.

## Phase 10 Status

Phase 10 is complete.

Completed items:

- Pump component foundation with inlet/outlet ports and `ComponentKind.PUMP`.
- Backward-compatible prescribed pressure-rise seam.
- Pump performance-map evaluation.
- Pump speed command and flow target binding.
- Pump power/efficiency seam using explicit scalar inputs.
- Pump geometry and named-frozen shaft-speed/inertia seam.
- Accumulator component foundation with one bidirectional port and containment-only geometry.
- Prescribed accumulator pressure-reference seam.
- `V_g` named internal-state seam; `P_sys` is not stored.
- `VolumePressureLawBinding` and accumulator law-slot evaluation.
- `VOLUME_PRESSURE_LAW` correlation role and `VolumePressureLawInput`.
- PCA volume-pressure closure and deterministic numerical tests.
- HCA retained as a declared seam, acceptable for V1 closeout.
- Network-owned pressure-reference wiring with exactly-one accumulator reference validation.
- Minimal pump-driven, accumulator-referenced loop acceptance shape.
- Import-boundary and architecture-boundary tests.

Remaining deferred items:

- Explicit pressure-reference port-name validation can be tightened as a small future network validation follow-up.
- Full physical residual assembly, pressure/flow convergence for real loops, and dynamic pressure/inventory derivatives remain deferred to later planned solver/component integration work.

Items explicitly out of scope for Phase 10:

- Evaporator.
- Condenser.
- `HeatExchangerModel`.
- Heat transfer.
- Phase change.
- Two-phase pressure drop.
- Dynamic simulation.
- Controls.
- Fitting.
- Optimization.
- Solver behavior changes.

## Merge Readiness

`phase-10b-pump-map-accumulator-law` can be merged into `main`.

The branch closes Phase 10 without source/test architecture violations. The only noted follow-up is minor validation hardening and does not block merge or next-phase readiness.

## Next Phase Readiness

The project is ready to advance to **Phase 11 - HeatExchangerModel, Evaporator and Condenser** after merge.

Phase 11 should focus on the heat-exchanger model interface, HeatExchangerModel registry/strategy work, Evaporator, and Condenser. Dynamic simulation, controls, fitting, optimization, and unplanned solver behavior changes remain deferred.

## Recommended Follow-ups

- Keep pressure-reference wiring in Network.
- Keep law evaluation out of Network.
- Keep components local and solver-unaware.
- Keep correlations scalar/data-only.
- Avoid fake loop convergence before residual assembly exists.
- Add an explicit pressure-reference port-name validation test/check if pressure-reference wiring begins to rely on port identity.
- Add import-boundary tooling if coupling risk grows.

## Verification

Ran:

- `pytest` - **1983 passed**, with one Windows `.pytest_cache` permission warning.
- `ruff check .` - **passed**.
- `black --check src tests` - **passed**, 99 files would be left unchanged.

`black --check .` was not used because `.pytest_cache` can produce Windows permission issues in this workspace; the requested `black --check src tests` command passed.

## Files Inspected

Main documentation inspected:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_9_SCHEMA_RESULTS_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_7_NETWORK_ASSEMBLY_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`

Main source files inspected:

- `src/mpl_sim/components/base.py`
- `src/mpl_sim/components/pipe.py`
- `src/mpl_sim/components/pump.py`
- `src/mpl_sim/components/accumulator.py`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/registry.py`
- `src/mpl_sim/correlations/volume_pressure_law.py`
- `src/mpl_sim/correlations/__init__.py`
- `src/mpl_sim/network/topology.py`
- `src/mpl_sim/network/validation.py`
- `src/mpl_sim/network/assembly.py`
- `src/mpl_sim/network/__init__.py`
- `src/mpl_sim/core/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/solvers/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/schema/`
- `src/mpl_sim/results/`
- `src/mpl_sim/validation/`
- `pyproject.toml`

Main test files inspected:

- `tests/components/test_pump_component.py`
- `tests/components/test_accumulator_component.py`
- `tests/correlations/test_volume_pressure_law_contract.py`
- `tests/correlations/test_pca_volume_pressure_law.py`
- `tests/network/test_pressure_reference.py`
- `tests/network/test_pump_accumulator_loop.py`
- `tests/network/test_network_assembly.py`
- adjacent tests under `tests/`
