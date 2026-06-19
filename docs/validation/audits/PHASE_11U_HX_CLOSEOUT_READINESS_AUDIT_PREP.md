# Phase 11U — Heat-Exchanger Family Closeout / Readiness Audit Preparation

**Date:** 2026-06-19
**Branch:** `phase-11u-hx-closeout-readiness-audit`
**Baseline:** Phase 11T iterated counterflow segmented solver (merged to `main`)
**Purpose:** Consolidate and verify the full Phase 11 HX implementation (11A–11T); update status documentation; prepare for Codex closeout audit.

---

## 1. Pre-Audit Validation

All prerequisite checks passed before any documentation changes were made.

| Check | Result |
|---|---|
| Branch | `phase-11u-hx-closeout-readiness-audit` ✓ |
| Working tree | Clean ✓ |
| `pytest` (full suite) | **3558 passed** ✓ |
| `pytest tests/correlations tests/hx_models tests/components` | **2408 passed** ✓ |
| `pytest tests/hx_models/test_segmented_counterflow_phase_change_foundation.py` | 76 passed ✓ |
| `pytest tests/hx_models/test_segmented_counterflow_iteration.py` | 92 passed ✓ |
| `ruff check src tests` | **All checks passed** ✓ |
| `black --check --no-cache src tests` | **All checks passed** ✓ |

---

## 2. Phase 11 Capability Matrix

### 2.1 HX Strategies

| Strategy | Class | BC Support | HTC | DP | Notes |
|---|---|---|---|---|---|
| Epsilon-NTU | `EpsilonNTUModel` | All four BC classes | PRIMARY_ONLY, TWO_SIDED | Single-phase + two-phase | Lumped; co-current sign convention |
| LMTD | `LMTDModel` | `FixedWallTemp`, `AmbientCoupling` | PRIMARY_ONLY | Single-phase + two-phase | `SinkInletTempAndFlow`, `FixedHeatRate` explicitly unsupported |
| Segmented march | `SegmentedMarchModel` | All four BC classes | PRIMARY_ONLY per cell, TWO_SIDED per cell | Single-phase + two-phase per cell | Co-current, one-pass counterflow, iterated counterflow |

### 2.2 Secondary Boundary Conditions

| BC class | `EpsilonNTUModel` | `LMTDModel` | `SegmentedMarchModel` |
|---|---|---|---|
| `FixedHeatRate` | ✓ | ✗ (explicit) | ✓ |
| `SinkInletTempAndFlow` | ✓ | ✗ (explicit) | ✓ (co-current + counterflow) |
| `FixedWallTemp` | ✓ | ✓ | ✓ |
| `AmbientCoupling` | ✓ | ✓ | ✓ |

### 2.3 Closure Support

| Slot | Status | Implemented closures | Remaining deferred |
|---|---|---|---|
| Primary HTC | ✓ Injectable via `htc_primary` | `DittusBoelterHTC`, `GnielinskiHTC`, `ShahBoilingHTC`, `YanCondensationHTC` | Chen (CoolProp dependency), Bennett-Chen, Gungor-Winterton, Kandlikar, Kim-Mudawar 2012 |
| Secondary HTC | ✓ Injectable via `htc_secondary` | Same pool | Same deferred pool |
| Primary DP (single-phase) | ✓ Injectable via `dp_primary`, `dp_primary_is_two_phase=False` (default) | `ChurchillFrictionGradient` | — |
| Primary DP (two-phase) | ✓ Injectable via `dp_primary`, `dp_primary_is_two_phase=True` | `MSHTwoPhaseFrictionGradient` | Homogeneous/Cicchitti, Kim-Mudawar 2013 |
| q-flux plumbing | ✓ `HXSolveRequest.q_flux_primary` | Explicit; required by `ShahBoilingHTC` | — |
| HTC multiplier | ✓ `HXSolveRequest.htc_multiplier` | Applies to UA (not `UA_ambient`) | — |
| Friction multiplier | ✓ `HXSolveRequest.friction_multiplier` | Applies after gradient-to-drop conversion | — |

### 2.4 Segmented Capabilities

| Capability | Status | Notes |
|---|---|---|
| Co-current (default) | ✓ | Both inlets at cell 0; `FlowArrangement.CO_CURRENT` or `None` |
| Counterflow one-pass | ✓ | `FlowArrangement.COUNTERFLOW` without `counterflow_iteration`; primary marches forward using `bc.T_in` as fixed secondary estimate; backward secondary profile is diagnostic only; not a converged solution |
| Counterflow iterated | ✓ | `FlowArrangement.COUNTERFLOW` + `CounterflowIterationConfig(enabled=True)`; bounded fixed-point iteration over secondary temperature profile; under-relaxation; returns `converged`, `residual`, `iteration_count`; non-convergence is reported not raised |
| Convergence diagnostics | ✓ | `HXSolveResult.converged`, `.residual`, `.iteration_count` |
| Per-cell DP conversion | ✓ | `L_cell` from `geom_scalars` used per cell; gradient [Pa/m] × `L_cell` = drop [Pa] |
| Phase-change scalar passing | ✓ | `x`, `h_fg`, `rho_l`, `rho_v`, `mu_l`, `mu_v` via `geom_scalars` → `HTCInput.geom_scalars` / `TwoPhaseDPInput.property_scalars` (Decision 011) |
| Per-cell `cell_geom_scalars` | ✗ deferred | Not needed by current correlations |
| Moving boundary | ✗ deferred | — |
| Quality marching / phase inference | ✗ deferred | — |

### 2.5 Component Wrappers

| Interface | Class | Status |
|---|---|---|
| Direct HX solve | `evaluate_heat_exchanger(inp)` | ✓ `EvaporatorComponent`, `CondenserComponent` |
| Scenario-bound helper | `evaluate_scenario(primary_state_in, primary_mdot, scenario)` | ✓ with `EvaporatorScenarioBinding` / `CondenserScenarioBinding` |
| Frozen component contract | `contribute(trial, ctx) -> ComponentContribution` | ✗ deferred (INTERFACE_SPEC §11.1) |
| Scenario binding immutability | `geom_scalars` as `MappingProxyType` | ✓ deeply immutable |

### 2.6 Explicitly Deferred Items

The following are outside Phase 11U scope and remain deferred:

- **Moving-boundary modeling** — phase-zone tracking, two-zone/three-zone marching
- **Full-loop convergence** — network residual assembly with Evaporator/Condenser
- **Network assembly** — topology wiring of HX components
- **Valves / manifolds** — not planned in Phase 11
- **Additional two-phase HTC closures** — Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian, Kim-Mudawar 2012
- **Additional two-phase DP closures** — Homogeneous/Cicchitti, Kim-Mudawar 2013
- **Per-cell geometry / property variation** — `cell_geom_scalars` mechanism
- **Quality marching / phase inference** — `primary_T_sat`, `primary_h_fg` on `HXSolveRequest`
- **Validation harness** — literature data pinning, physical residual acceptance cases
- **`contribute(trial, ctx)` component contract** — requires `ComponentTrialState` and `EvalContext`
- **CoolProp inside HX** — architecture boundary; forbidden per [F6]
- **`MOVING_BOUNDARY` model** — declared seam in `HeatExchangerModelKind`, no implementation

---

## 3. Public API / Export Consistency

### 3.1 `mpl_sim.hx_models`

| Symbol | In `__all__` | Tested in `__all__` | Live test (import+use) |
|---|---|---|---|
| `HeatExchangerModelKind` | ✓ | — | ✓ |
| `SinkInletTempAndFlow` | ✓ | — | ✓ extensive |
| `FixedWallTemp` | ✓ | — | ✓ extensive |
| `FixedHeatRate` | ✓ | — | ✓ extensive |
| `AmbientCoupling` | ✓ | — | ✓ extensive |
| `SecondaryFluidBC` | ✓ | — | ✓ |
| `FlowArrangement` | ✓ | test_phase11_public_exports.py (Phase 11U) | ✓ extensive |
| `CounterflowIterationConfig` | ✓ | test_segmented_counterflow_iteration.py | ✓ extensive |
| `HXSolveRequest` | ✓ | test_phase11_public_exports.py (Phase 11U) | ✓ extensive |
| `HXSolveResult` | ✓ | test_phase11_public_exports.py (Phase 11U) | ✓ extensive |
| `HeatExchangerModel` | ✓ | — | ✓ |
| `UnsupportedHeatExchangerBoundaryConditionError` | ✓ | — | ✓ |
| `HeatExchangerModelRegistry` | ✓ | — | ✓ |
| `create_empty_hx_model_registry` | ✓ | — | ✓ |
| `EpsilonNTUModel` | ✓ | test_hx_model_family_contracts.py | ✓ extensive |
| `LMTDModel` | ✓ | test_hx_model_family_contracts.py | ✓ extensive |
| `SegmentedMarchModel` | ✓ | test_hx_model_family_contracts.py | ✓ extensive |
| `SegmentedCellRecord` | ✓ | test_hx_model_family_contracts.py | ✓ |
| `SegmentedProfile` | ✓ | test_hx_model_family_contracts.py | ✓ |

### 3.2 `mpl_sim.components`

| Symbol | In `__all__` | Tested in `__all__` | Live test |
|---|---|---|---|
| `EvaporatorComponent` | ✓ | — | ✓ extensive |
| `EvaporatorHXInput` | ✓ | — | ✓ |
| `EvaporatorScenarioBinding` | ✓ | test_evaporator_condenser_contribution_scenario_binding.py | ✓ |
| `CondenserComponent` | ✓ | — | ✓ extensive |
| `CondenserHXInput` | ✓ | — | ✓ |
| `CondenserScenarioBinding` | ✓ | test_evaporator_condenser_contribution_scenario_binding.py | ✓ |

### 3.3 `mpl_sim.correlations`

| Symbol | In `__all__` | Tested in `__all__` | Live test |
|---|---|---|---|
| `DittusBoelterHTC` | ✓ | test_single_phase_htc.py | ✓ extensive |
| `GnielinskiHTC` | ✓ | test_single_phase_htc.py | ✓ extensive |
| `ShahBoilingHTC` | ✓ | test_two_phase_htc.py | ✓ extensive |
| `YanCondensationHTC` | ✓ | test_two_phase_htc.py | ✓ extensive |
| `MSHTwoPhaseFrictionGradient` | ✓ | test_phase11_public_exports.py (Phase 11U) | ✓ extensive |
| `ChurchillFrictionGradient` | ✓ | test_single_phase_dp.py | ✓ |

---

## 4. Regression Test Inventory

### 4.1 Phase 11 HX-Family Test Files

| Test file | Tests | Phase | Coverage area |
|---|---|---|---|
| `test_hx_model_contract.py` | 41 | 11A | HX contract, abstract base, registry isolation |
| `test_hx_model_registry.py` | 18 | 11A | Registry register/resolve/duplicate/missing |
| `test_epsilon_ntu_model.py` | 46 | 11A/B | EpsilonNTU FixedHeatRate + SinkInletTempAndFlow foundation |
| `test_epsilon_ntu_sink_side.py` | 59 | 11B | SinkInletTempAndFlow full coverage |
| `test_epsilon_ntu_ambient_coupling.py` | 25 | 11D | AmbientCoupling in EpsilonNTU |
| `test_epsilon_ntu_fixed_wall_temp.py` | 32 | 11D | FixedWallTemp in EpsilonNTU |
| `test_secondary_bc.py` | 39 | 11A/D | BC value-object validation |
| `test_lmtd_model.py` | 72 | 11E | LMTDModel FixedWallTemp + AmbientCoupling |
| `test_hx_model_architecture_boundaries.py` | 30 | 11A/G | Import-boundary enforcement for all HX modules |
| `test_hx_model_family_contracts.py` | 54 | 11G | Cross-model subclass, kind, registry, `__all__` |
| `test_hx_model_input_hardening.py` | 44 | 11C | Scalar validation, rejection of invalid inputs |
| `test_hx_closure_integration_contracts.py` | 52 | 11K | Closure injection / verdict propagation (all 3 models × all 4 BCs) |
| `test_hx_q_flux_plumbing.py` | 46 | 11N | `q_flux_primary` threading, Shah injection, side isolation |
| `test_hx_two_phase_dp_plumbing.py` | 122 | 11P | Two-phase DP builders, property-scalar forwarding, gradient→drop |
| `test_segmented_march_model.py` | 53 | 11F | SegmentedMarchModel FixedHeatRate foundation |
| `test_segmented_wall_htc_coupling.py` | 57 | 11H | SegmentedMarchModel FixedWallTemp per-cell HTC |
| `test_segmented_ambient_coupling.py` | 53 | 11I | SegmentedMarchModel AmbientCoupling |
| `test_segmented_sink_coupling.py` | 63 | 11J | SegmentedMarchModel SinkInletTempAndFlow co-current |
| `test_segmented_counterflow_phase_change_foundation.py` | 76 | 11S | FlowArrangement, one-pass counterflow, phase-change scalar passing |
| `test_segmented_counterflow_iteration.py` | 92 | 11T | CounterflowIterationConfig, iterated solver, diagnostics, real closures |
| `test_phase11_public_exports.py` | 10 | 11U | Public-path identity and `__all__` consistency |
| **HX models subtotal** | **1084** | 11A–11U | |
| `test_single_phase_htc.py` | 82 | 11L | DittusBoelterHTC, GnielinskiHTC |
| `test_two_phase_htc.py` | 97 | 11M | ShahBoilingHTC, YanCondensationHTC |
| `test_two_phase_dp.py` | 83 | 11O | MSHTwoPhaseFrictionGradient |
| **Phase 11 correlation subtotal** | **262** | 11L/M/O | |
| `test_evaporator_component.py` | 35 | 11A/C | Evaporator wrapper foundation |
| `test_condenser_component.py` | 43 | 11A/C | Condenser wrapper foundation |
| `test_heat_exchanger_component_boundaries.py` | 23 | 11A | HX component import boundaries |
| `test_evaporator_condenser_scenario_plumbing.py` | 51 | 11Q | q_flux_primary + dp_primary_is_two_phase forwarding |
| `test_evaporator_condenser_contribution_scenario_binding.py` | 77 | 11R | ScenarioBinding immutability, evaluate_scenario cross-reference |
| **Phase 11 component subtotal** | **229** | 11A/C/Q/R | |
| **Phase 11 grand total** | **1575** | 11A–11U | 29 test files |

### 4.2 Full Suite Summary

| Scope | Tests | Status |
|---|---|---|
| Full `pytest` | 3558 | ✓ all passed |
| `tests/correlations` | 512 | ✓ all passed |
| `tests/hx_models` | 1084 | ✓ all passed |
| `tests/components` (HX-related) | 229 | ✓ all passed |
| Phase 11 HX family total | 1575 | ✓ all passed |
| `ruff check src tests` | — | ✓ clean |
| `black --check src tests` | — | ✓ clean |

---

## 5. Architecture Boundary Search Results

All searches executed against `src/mpl_sim/hx_models`, `src/mpl_sim/components`, `src/mpl_sim/correlations`, and `tests/`.

### 5.1 Live Import Boundaries

| Pattern searched | Live hits in production code | Verdict |
|---|---|---|
| `CoolProp` in HX/components/correlations | 0 live imports — all occurrences are in docstring text (`"No CoolProp"`) | ✓ Clean |
| `PropertyBackend` in HX/components/correlations | 0 live imports — all in docstrings/comments | ✓ Clean |
| `mpl_sim.network` in HX/components/correlations | 0 live imports | ✓ Clean |
| `mpl_sim.solvers` in HX/components/correlations | 0 live imports | ✓ Clean |
| `CorrelationRegistry` in HX/components | 0 live imports — `correlations/registry.py` defines it; HX models do not use it | ✓ Clean |

### 5.2 Hidden-Default and Magic-Number Search

| Pattern | Production-code hits | Assessment |
|---|---|---|
| `4180` | 0 in production; test fixtures only | ✓ No hidden water-cp default |
| `rho_l *= 1000`, `rho_v *= 1`, `mu_l *= 1e-3` | 0 | ✓ No embedded fluid constants |
| `D_h *= 1e-3`, `L_cell *= 1`, `x *= 0.5` | 0 | ✓ No scaled-back magic numbers |
| `T_sat`, `h_fg` assignment in production | 0 defaults; `h_fg = _require_positive(gs, ...)` is input validation | ✓ Validation, not default |

### 5.3 Clipping and Silent Clamping

| Pattern | Production-code hits | Assessment |
|---|---|---|
| `np.clip`, `np.maximum`, `np.minimum` | 0 in HX/components/correlations | ✓ No silent clamping |
| `abs(` | `abs(Cr - 1.0)` in epsilon_ntu.py:126 (capacity-ratio branch check); `abs(inp.G)` in single_phase_dp.py:214 (sign normalization for Churchill) | ✓ Legitimate mathematical use; no hidden clipping of output |

**Overall boundary assessment: CLEAN.** No architecture violations found. All boundary rules from `ARCHITECTURE_MASTER.md` [F1]–[F18] are respected.

---

## 6. Coverage Gaps Addressed in Phase 11U

One export test file was added:

**`tests/hx_models/test_phase11_public_exports.py`**

This fills `__all__` assertion gaps for symbols that were imported and used in tests but whose `__all__` membership was not explicitly asserted:

- `FlowArrangement` in `mpl_sim.hx_models.__all__`
- `HXSolveRequest` in `mpl_sim.hx_models.__all__`
- `HXSolveResult` in `mpl_sim.hx_models.__all__`
- `MSHTwoPhaseFrictionGradient` in `mpl_sim.correlations.__all__`

No new physics, no new correlations, no new HX model behavior was added.

---

## 7. What Phase 11 Is and Is Not

### Is (ready as a current HX-family checkpoint)

- A self-consistent HX model family with three strategies covering all four declared secondary BC types
- An explicit, injection-based closure architecture with no hidden defaults and no automatic closure selection
- Explicit two-phase scalar passing via `geom_scalars` / `property_scalars` (Decision 011)
- Explicit gradient-to-drop conversion using caller-supplied `L_cell`
- Explicit co-current, one-pass counterflow, and iterated counterflow flow arrangements
- Convergence diagnostics (`converged`, `residual`, `iteration_count`)
- Immutable scenario bindings (`EvaporatorScenarioBinding`, `CondenserScenarioBinding`)
- 1575 Phase 11 tests across 29 test files, all passing

### Is Not (system-level integration remains deferred)

- A full-loop convergence acceptance case
- A moving-boundary or phase-zone-tracking model
- A complete two-phase HTC closure library
- A complete two-phase DP closure library
- A network solver or topology integrator
- A literature-validated physical acceptance case
- A component with the frozen `contribute(trial, ctx)` contract

---

## 8. Recommended Next Phase

After Phase 11U closeout, the recommended continuation is:

**Option A (remaining Phase 11 closures):** Port `HomogeneousTwoPhaseFrictionGradient` and `KimMudawar2013TwoPhaseFrictionGradient` under the existing `CorrelationRole.TWO_PHASE_DP` contract if safe legacy sources are confirmed.

**Option B (full-loop convergence):** Implement a minimal loop acceptance case wiring `EvaporatorComponent` and `CondenserComponent` through the Phase 8 fixed-point solver, exercising the `evaluate_heat_exchanger` path end-to-end.

**Option C (Phase 12):** Advance to Phase 12 (validation harness, literature data pinning, systematic test plan acceptance) while leaving remaining closure migrations to a future Phase 11 slice.

The current Phase 11 HX-family checkpoint is ready for merge. Phase 11 remains
open for roadmap-level system integration, remaining closure migrations,
moving-boundary work, and validation.

---

## 9. Audit Verdict

**READY FOR CODEX CLOSEOUT REVIEW.**

The current Phase 11 HX-family checkpoint (11A–11U) is ready for final audit.
All 3558 tests pass. All architecture boundaries are clean. All intended
public types are exported and reachable. The capability matrix is documented.
Deferred items are clearly enumerated. No new physics was added in Phase 11U.
