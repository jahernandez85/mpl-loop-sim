# PROJECT_STATUS.md

Operational memory for the MPL simulation framework.
This document is not architecture. It does not redesign anything. It tracks where the project is and what to do next.

---

## 1. Current Status

| Field | Value |
|---|---|
| **Project name** | MPL Loop Simulation Library |
| **Repository** | `mpl-loop-sim` |
| **Branch** | `phase-15d-a-hydraulic-closure-primitives` |
| **Stage** | Block 15D-A — Hydraulic Closure Primitives MVP: explicit algebraic closure declarations and residual sets, closure sufficiency diagnostics, parallel integration proof |
| **Completed phase** | **Block 15D-A — Hydraulic Closure Primitives MVP** |
| **Previous completed phase** | Block 15C-B — Branch Residual and Parallel Evaluation MVP |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Phase 5A audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 7 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 8 checkpoint audit verdict** | **APPROVED FOR MERGE AS PHASE 8 CHECKPOINT - CONTINUE PHASE 8** |
| **Phase 8 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 8 status** | **Complete. Phase 8A, 8B, 8C, 8D, and 8E are complete.** |
| **Phase 9 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 9 status** | **Complete. Result primitives, schema primitives, canonical serialization, validation invariant primitives, and safe serialization adapters are complete.** |
| **Phase 10 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 10 status** | **Complete. Pump map/command behavior, pump power/efficiency seam, shaft-speed/inertia named seam, accumulator `VolumePressureLaw` integration, PCA closure, `V_g` state seam, network pressure-reference wiring, and pump-driven accumulator-referenced loop acceptance shape are implemented at planned V1 fidelity.** |
| **Phase 11 foundation audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11 foundation status** | **Checkpoint complete. HeatExchangerModel contract/registry, secondary BC value objects, V1 `EpsilonNTUModel` fixed-heat-rate path, and Evaporator/Condenser component wrappers are implemented and tested. Full Phase 11 physics remains in progress.** |
| **Phase 11B audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11B status** | **Checkpoint complete. `EpsilonNTUModel` now supports `SinkInletTempAndFlow` with explicit `primary_T_in`, explicit `PrimaryThermalMode`, explicit `UAComputationMode`, explicit finite-capacity `primary_cp`, injected HTC/DP correlations, and tested heating/cooling sign convention.** |
| **Phase 11C audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11C status** | **Checkpoint complete. `EvaporatorHXInput` exposes and forwards `htc_secondary`; Evaporator/Condenser wrapper tests verify sink-side HX field forwarding; `EpsilonNTUModel` rejects invalid geometry/correlation scalars and invalid HTC/DP outputs without silent fallback.** |
| **Phase 11D audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11D status** | **Checkpoint complete. `EpsilonNTUModel` now supports `FixedWallTemp` and `AmbientCoupling` with explicit primary inlet temperature, explicit wall/ambient inputs, correct heating/cooling sign convention, tested enthalpy balance, and preserved correlation/calibration boundaries.** |
| **Phase 11E audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11E status** | **Checkpoint complete. `LMTDModel` is implemented as a limited foundation supporting `FixedWallTemp` and `AmbientCoupling`; `SinkInletTempAndFlow` and `FixedHeatRate` remain explicitly unsupported in `LMTDModel`.** |
| **Phase 11F audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11F status** | **Checkpoint complete. `SegmentedMarchModel` is implemented as a limited foundation supporting only `FixedHeatRate`; segment-wise secondary coupling and local HTC/UA solving remain deferred.** |
| **Phase 11G audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11G status** | **Checkpoint complete. Cross-model family contract tests added (`test_hx_model_family_contracts.py`); import-boundary coverage extended to `lmtd.py` and `segmented.py`; no new physics added.** |
| **Phase 11H audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11H status** | **Checkpoint complete. `SegmentedMarchModel` now supports both `FixedHeatRate` and finite-capacity segmented `FixedWallTemp`, with explicit primary temperature/cp marching, per-cell injected HTC, optional per-cell injected DP, and diagnostic-only cell temperatures.** |
| **Phase 11I audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11I status** | **Checkpoint complete. `SegmentedMarchModel` now also supports finite-capacity segmented `AmbientCoupling` using prescribed `UA_ambient / n_cells`, explicit primary temperature/cp marching, no primary HTC call, optional per-cell injected DP, and diagnostic-only cell temperatures.** |
| **Phase 11J audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11J status** | **Checkpoint complete. `SegmentedMarchModel` now also supports finite-capacity co-current segmented `SinkInletTempAndFlow` with explicit primary/secondary capacities, two-sided per-cell HTC/UA, local epsilon-NTU marching, optional per-cell injected DP, and diagnostic-only primary/secondary temperatures.** |
| **Phase 11K audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11K status** | **Checkpoint complete. Current migrated-contract inventory completed: no HTC or two-phase DP correlations are active under `src/mpl_sim/correlations`; `ChurchillFrictionGradient` (single-phase DP) and `PcaVolumePressureLaw` (volume-pressure law, not an HX closure) are implemented. No adapter utilities were needed — existing seams are sufficient. New focused test file `tests/hx_models/test_hx_closure_integration_contracts.py` added (52 tests) covering all three HX model strategies and all four secondary BC classes for closure injection, verdict propagation, invalid-output rejection, multiplier placement, and registry-resolution absence.** |
| **Phase 11L audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11L status** | **Checkpoint complete. Single-phase HTC correlations migrated under `src/mpl_sim/correlations`: `DittusBoelterHTC` and `GnielinskiHTC` are implemented, exported, and tested. Both implement `CorrelationRole.HTC`, require explicit `Re`, `Pr`, `k` via `HTCInput.geom_scalars` and `D_h` from `HTCInput.D_h`, return `CorrelationOutput.value[0]` = h [W/m²/K], and carry `ValidityVerdict` + `ClosureMetadata`. `DittusBoelterHTC` additionally requires explicit `n` for the Pr exponent. Neither correlation calls CoolProp, PropertyBackend, or uses hidden defaults. Boiling HTC, condensation HTC, and two-phase DP remain deferred.** |
| **Phase 11M audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11M status** | **Checkpoint complete. `ShahBoilingHTC` and `YanCondensationHTC` are implemented, exported, and tested under the current `CorrelationRole.HTC` contract with explicit scalar inputs, one-element HTC outputs, validity verdicts, metadata, and no property lookup or hidden defaults. Existing HX builders forward all `geom_scalars`, so `YanCondensationHTC` is directly injectable when callers provide its required scalars. `ShahBoilingHTC` HX injection remains deferred because current builders do not populate `HTCInput.q_flux`. Remaining two-phase HTC closures, two-phase DP, moving boundary, and full-loop integration remain deferred.** |
| **Phase 11N audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11N status** | **Checkpoint complete. `HXSolveRequest.q_flux_primary: float | None` adds strict explicit primary-side heat-flux validation and all three HX strategies pass it unchanged to primary `HTCInput.q_flux`. Epsilon-NTU and segmented two-sided paths explicitly keep secondary `HTCInput.q_flux=None`. `ShahBoilingHTC` is injectable through EpsilonNTU, LMTD, and Segmented fixed-wall paths when all required scalars and q-flux are supplied. No Q/A inference, abs(), clipping, or hidden fallback exists. `YanCondensationHTC` remains injectable and q-flux-independent. Two-phase DP, remaining HTC closures, moving boundary, and full-loop integration remain deferred.** |
| **Phase 11P audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11P status** | **Checkpoint complete. All three HX strategies support explicit primary-side `TwoPhaseDPInput` construction and Pa/m-to-Pa conversion when `dp_primary_is_two_phase=True`; default single-phase behavior remains unchanged.** |
| **Phase 11Q status** | **Checkpoint complete. `EvaporatorHXInput` and `CondenserHXInput` now include `q_flux_primary: float | None = None` and `dp_primary_is_two_phase: bool = False`; both fields are forwarded explicitly to `HXSolveRequest` by `evaluate_heat_exchanger`. Evaporator can now use `ShahBoilingHTC` (with explicit `q_flux_primary`) and `MSHTwoPhaseFrictionGradient` (with `dp_primary_is_two_phase=True`) through the component wrapper. Condenser can now use `YanCondensationHTC` and `MSHTwoPhaseFrictionGradient` through the component wrapper. No hidden defaults, no automatic closure selection, no registry resolution in components.** |
| **Phase 11R audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11R status** | **Checkpoint complete. `EvaporatorScenarioBinding` and `CondenserScenarioBinding` added as immutable frozen dataclasses in `src/mpl_sim/components/evaporator.py` and `src/mpl_sim/components/condenser.py`; `geom_scalars` stored as a defensive `MappingProxyType` copy; both types exported from `mpl_sim.components`. `EvaporatorComponent.evaluate_scenario(primary_state_in, primary_mdot, scenario)` and `CondenserComponent.evaluate_scenario(...)` added as scenario-bound helpers that build the respective `*HXInput` from runtime state + immutable scenario binding and delegate to `evaluate_heat_exchanger`. These helpers are NOT the frozen `contribute(trial, ctx) -> ComponentContribution` contract from INTERFACE_SPEC §11.1; that contract remains deferred. Phase 11Q scenario fields (`q_flux_primary`, `dp_primary_is_two_phase`) are now accessible through the scenario helper path, not only through direct `evaluate_heat_exchanger` calls.** |
| **Phase 11S status** | **Checkpoint complete. `FlowArrangement` enum (`CO_CURRENT`, `COUNTERFLOW`) added to `src/mpl_sim/hx_models/base.py` and exported from `mpl_sim.hx_models`. `HXSolveRequest.flow_arrangement: FlowArrangement | None = None` added; default `None` preserves all existing behavior. `SegmentedProfile.flow_arrangement: FlowArrangement | None = None` added to record which arrangement was used. `SegmentedMarchModel` now dispatches `SinkInletTempAndFlow` to `_solve_sink_inlet_cocurrent` (for `None`/`CO_CURRENT`) or `_solve_sink_inlet_counterflow_onepass` (for `COUNTERFLOW`). COUNTERFLOW is a one-pass approximation only: primary marches forward using `bc.T_in` as fixed secondary temperature estimate for all cells; secondary profile derived by backward integration after the primary march (diagnostics only). A fully coupled converged counterflow solution is deferred. Phase-change scalar passing (`x`, `h_fg`, `rho_l`, `rho_v`, `mu_l`, `mu_v`) remains explicit via `geom_scalars`; no `primary_T_sat` or `primary_h_fg` fields were added to `HXSolveRequest` because existing correlations do not require them there.** |
| **Phase 11T status** | **Checkpoint complete. `CounterflowIterationConfig` frozen dataclass added to `src/mpl_sim/hx_models/base.py` with fields `enabled`, `max_iter`, `tolerance`, `relaxation` and `__post_init__` validation. `HXSolveRequest.counterflow_iteration: CounterflowIterationConfig | None = None` added with early validation (only `SinkInletTempAndFlow` + `COUNTERFLOW` accepted when `enabled=True`). `HXSolveResult` extended with `iteration_count: int = 0`, `converged: bool | None = None`, `residual: float | None = None`. `SegmentedMarchModel._solve_sink_inlet_counterflow_iterated` added: bounded fixed-point iteration over the secondary temperature profile using co-current ε-NTU per cell, backward secondary integration, and under-relaxation. Non-convergence returns `converged=False` and is never silent. One-pass path (`enabled=False` or `counterflow_iteration=None`) is unchanged. `CounterflowIterationConfig` exported from `mpl_sim.hx_models`.** |
| **Phase 11U audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11U status** | **Closeout readiness audit complete. 3558 tests passing (3548 pre-audit + 10 new export-consistency tests). Capability matrix and support exceptions documented. Architecture boundaries confirmed clean. Public exports verified. No new physics added. See `PHASE_11U_HX_CLOSEOUT_READINESS_AUDIT.md`.** |
| **Phase 11 final closeout verdict** | **APPROVED AS CHECKPOINT ONLY - PHASE 11 REMAINS OPEN** |
| **Phase 11 status** | **The current HX-family checkpoint (11A–11U) is ready. `EpsilonNTUModel` and `SegmentedMarchModel` support all four secondary BC classes; `LMTDModel` intentionally supports only `FixedWallTemp` and `AmbientCoupling`. Co-current, one-pass counterflow, and iterated counterflow are implemented only for segmented `SinkInletTempAndFlow`. Active public closures are injectable, including `ChurchillFrictionGradient` and `MSHTwoPhaseFrictionGradient`. Immutable scenario bindings are implemented. 1575 Phase 11 tests pass across 29 files. Full-loop convergence, network contribution integration, moving boundary, remaining closures, and validation remain deferred.** |
| **Phase 14E status** | **Checkpoint complete. Controlled toy component execution harness implemented. `ToyComponentExecutionContext`, `ToyComponentExecutor`, `ToyComponentExecutorSet`, `execute_toy_component_contributions`, `build_component_contribution_from_toy_execution` added to `mpl_sim.network` in new `toy_component_execution.py` module. Toy execution layer: `ToyComponentExecutionContext` is an immutable context (binding context + defensive unknown-values copy + optional metadata); `ToyComponentExecutor` binds a `ComponentInstanceId` to a caller-supplied toy callback returning `Mapping[str, float]` or `ContributionRecordSet`; `ToyComponentExecutorSet` is an ordered, validated, duplicate-rejecting collection; `execute_toy_component_contributions` validates exact binding coverage, invokes each toy callback, validates all outputs (no bool/NaN/inf/non-numeric values, no empty names, no wrong-component records, no duplicates), and returns a `ContributionRecordSet`; `build_component_contribution_from_toy_execution` is a convenience wrapper to Phase 14D mapping and Phase 14C `ComponentContribution`. No real component execution, no `Component.contribute(...)`, no `SystemState`, no `FluidState`, no property lookup, no `CoolProp`, no automatic physics from `component_type`. Fully integrated with Phase 14D residual map, Phase 14C adapter, Phase 14A physical adapters, and Phase 13G/13H evaluation/solve stack. 75 focused tests; 1066 network tests; 4927 tests total. See `PHASE_14E_CONTROLLED_TOY_COMPONENT_EXECUTION_AUDIT.md`.** |
| **Phase 14D status** | **Checkpoint complete. Component contribution contract adapter prep implemented. `ContributionRecord`, `ContributionRecordSet`, `ContributionResidualMap`, `map_contribution_records_to_component_contribution` added to `mpl_sim.network` in new `contribution_contract.py` module. Value-object layer: `ContributionRecord` is a frozen scalar value object (component_id, name, value, optional unit); `ContributionRecordSet` is an ordered validated collection rejecting duplicates; `ContributionResidualMap` is an explicit defensively-copied (ComponentInstanceId, contribution_name) → residual_name mapping; `map_contribution_records_to_component_contribution` selects records by component ID, translates names via explicit map, and returns a Phase 14C `ComponentContribution`. No real component execution, no `Component.contribute(...)`, no `SystemState`, no property lookup, no automatic physics from `component_type`. 92 focused tests; 991 network tests; 4852 tests total.** |
| **Phase 14C status** | **Checkpoint complete. Minimal component contribution adapter foundation implemented. `ComponentContributionContext`, `ComponentContribution`, `ComponentContributionAdapter`, `ComponentContributionAdapterSet`, `build_physical_adapters_from_contributions` added to `mpl_sim.network` in new `contribution_adapters.py` module. Explicit adapter layer: caller-supplied contribution callbacks (not real component classes) are bound to `ComponentInstanceId` objects; builder validates exact coverage against binding_set; generated `PhysicalResidualAdapter` callbacks invoke all contribution callbacks at evaluation time, validate residual name coverage (undeclared names rejected), and return the requested residual value. Fully integrated with Phase 14A `build_network_residual_evaluators` and Phase 13G/13H evaluation/solve paths. 78 focused tests; 899 network tests; 4760 tests total.** |
| **Phase 14B status** | **Checkpoint complete. Component binding and state-vector mapping foundation implemented. `ComponentBinding`, `ComponentBindingSet`, `ComponentStateMap`, `NetworkBindingContext`, `build_binding_context` added to `mpl_sim.network` in new `component_binding.py` module. Explicit binding/mapping declaration layer: one binding per graph component instance; unknown/residual name → component/node ID mappings defensively copied as `MappingProxyType`; builder validates exact coverage, assembly declarations, and graph ID references. No component execution, no property lookup, no CoolProp, no graph state attachment. 111 focused tests; 821 network tests; 4682 tests total.** |
| **Phase 14A status** | **Checkpoint complete. Physical residual adapter foundation implemented. `PhysicalResidualContext`, `PhysicalResidualAdapter`, `PhysicalResidualAdapterSet`, `build_network_residual_evaluators` added to `mpl_sim.network` in new `physical_adapters.py` module. Explicit adapter layer converts caller-supplied callbacks into Phase 13G `NetworkResidualEvaluator` objects; preserves assembly residual order; validates exact name match (missing/extra rejected). Context is immutable with defensive copies of unknown_values and metadata. No automatic component execution, no property lookup, no CoolProp, no graph state attachment. Adapters integrate with Phase 13G `evaluate_network_residuals` and Phase 13H `solve_network_residual_problem` through explicit evaluator tuples. 82 focused tests; 710 network tests; 4571 tests total.** |
| **Phase 13H status** | **Checkpoint complete. Configurable network solver v1 implemented. `NetworkSolveConfig`, `NetworkSolveResult`, `solve_network_residual_problem` added to `mpl_sim.network` in new `solver.py` module. Damped finite-difference Newton method: forward FD Jacobian (n perturbed evaluations per iteration), Gaussian elimination with partial pivoting, damped update `x_new = x + damping * dx`. Convergence: `max_abs_scaled <= tolerance`. Singularity detection: pivot below `1e-14` → `converged=False`. Only square systems (`n_unknowns == n_residuals`) accepted. Initial convergence check: if already converged before first iteration returns `iteration_count=0`. Callback exceptions propagate without being swallowed. No scipy, no numpy root-finders, no component execution, no property lookup, no physical state on graph nodes. 113 focused tests in `tests/network/test_configurable_solver_v1.py`; 628 total network tests; 4489 tests total.** |
| **Phase 13G status** | **Checkpoint complete. Network residual evaluation foundation implemented. `NetworkUnknownValues`, `NetworkResidualEvaluator`, `NetworkResidualEvaluationResult`, `evaluate_network_residuals` added to `mpl_sim.network` in new `residual_evaluation.py` module. Evaluation-only layer: accepts `NetworkResidualAssembly` (Phase 13F) + explicit unknown values + explicit residual callbacks + explicit scales → `ResidualVector` (Phase 13C) in assembly declaration order. Strict validation: missing/extra unknowns, missing/extra evaluators (with duplicate detection), missing/extra scales, non-finite values, bool values, and non-finite/bool callback returns all rejected. Callback exceptions propagate without being swallowed. No solver, no component execution, no property lookup, no graph physical-state attachment. 95 focused tests in `tests/network/test_residual_evaluation_foundation.py`.** |
| **Phase 13F status** | **Checkpoint complete. Network residual assembly foundation implemented. `NetworkUnknownDeclaration`, `NetworkResidualDeclaration`, `NetworkUnknownSet`, `NetworkResidualSet`, `NetworkResidualAssembly`, `assemble_network_residuals` added to `mpl_sim.network` in new `residual_assembly.py` module. Declaration-only layer: one mass-flow unknown per component instance (kg/s), one pressure unknown per node (Pa, optional), one mass-balance residual per node (kg/s), one pressure-compatibility residual per component instance (Pa, optional). Deterministic graph-insertion-order assembly. Optional closed-loop structural validation. No solve, no residual evaluation, no component execution, no property lookup. 122 focused tests in `tests/network/test_residual_assembly_foundation.py`; 4281 tests total.** |
| **Phase 13E status** | **Checkpoint complete. Network graph foundation implemented. `GraphNodeId`, `ComponentInstanceId`, `GraphNode`, `ComponentInstance`, `NetworkGraph` added to `mpl_sim.network` in new `graph.py` module. Physics-free topology representation with strict type/value validation (no blank IDs, wrong ID types, duplicates, dangling references, or self-loops). `validate_closed_single_loop()` structural check added. 115 focused tests in `tests/network/test_graph_foundation.py`. No physics, no solver, no residual assembly. 4159 tests total.** |
| **Phase 13D audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 13D status** | **Checkpoint complete. Coupled fixed-architecture energy+pressure closure implemented. `CoupledClosureConfig`, `MinimalCoupledClosureCase`, `MinimalCoupledClosureResult`, `solve_minimal_coupled_closure` added to `mpl_sim.closed_loop`. Nested scalar bisection (Option A): outer bisects primary_mdot for pressure closure; inner bisects Q_cond for energy closure at each outer step. Both residuals driven to zero; ResidualVector provides scaled convergence diagnostics. 112 focused tests in `tests/closed_loop/test_minimal_coupled_closure.py`. Phase 13A/13B solvers and Phase 13C framework unchanged. 4044 tests total.** |
| **Phase 13C audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 13C status** | **Checkpoint complete. Residual/unknown/scaling framework foundation implemented. `UnknownSpec`, `ResidualSpec`, `ResidualEvaluation`, `ResidualVector` added to `mpl_sim.closed_loop`. Provides named, scaled, validated value objects for residual representation. Does NOT implement a generic `solve(network)` API or simultaneous multi-variable solving. Phase 13A/13B solvers unchanged. 117 focused tests in `tests/closed_loop/test_residual_framework.py`. 3932 tests total.** |
| **Phase 13B audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 13B status** | **Checkpoint complete. Minimal pressure closure solver implemented. `solve_minimal_pressure_closure`, `PumpHeadCurve`, `PressureClosureConfig`, `MinimalPressureClosureCase`, `MinimalPressureClosureResult` added to `mpl_sim.closed_loop`. Fixed architecture: reference_state -> evaporator -> condenser. Solves for primary_mdot via bounded bisection (pressure closure: pump_head(mdot) = dP_total(mdot)). Explicit component flow areas set trial `G = mdot/A`; both DP closures are required. Pressure-only (Option A); energy_residual is diagnostic. Private `_scalar_solve._bisect_bounded` refactored from Phase 13A. Focused tests in `tests/closed_loop/test_minimal_pressure_closure.py`.** |
| **Phase 13A audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 13A status** | **Checkpoint complete. Minimal closed MPL solver implemented. `mpl_sim.closed_loop` package added with `solve_minimal_closed_mpl`, `MinimalClosedMPLCase`, `MinimalClosedMPLResult`, and `ClosedLoopSolveConfig`. Fixed architecture: reference_state -> evaporator -> condenser -> return. Solves for Q_cond via bounded bisection (energy closure: h_return = h_reference). Bracket sign change and exact endpoint roots are handled explicitly. Pressure closure is diagnostic only (dP_total). 85 focused tests in `tests/closed_loop/test_minimal_closed_mpl_solver.py`. See `PHASE_13A_MINIMAL_CLOSED_MPL_SOLVER_AUDIT.md`.** |
| **Phase 12B audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 12B status** | **Checkpoint complete. Examples and user documentation quickstart added. See `PHASE_12B_EXAMPLES_USER_DOCS_QUICKSTART_AUDIT.md` and the Phase 12B entry below.** |
| **Phase 12A audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 12A status** | **Checkpoint complete. Minimal loop assembly acceptance example implemented. `examples/minimal_evaporator_condenser_loop.py` provides `MinimalLoopResult` frozen dataclass and `evaluate_minimal_evaporator_condenser_loop(...)` function. 33 focused acceptance tests in `tests/loops/test_minimal_loop_example.py` cover all 12 required items. Not a full network solver; no loop convergence; no moving-boundary model; no property lookup. Net energy imbalance and enthalpy drift reported explicitly. 3591 tests passing. See `PHASE_12A_MINIMAL_LOOP_ASSEMBLY_AUDIT.md`.** |
| **Block 15A.1 status** | **Checkpoint complete and independently audited. Production component bridge boundary MVP introduced. `ProductionBridgeExecutionContext`, `ProductionContributionBridgeProtocol`, `ProductionComponentBridgeBinding`, `ProductionComponentBridgeSet`, `execute_production_bridge_contributions`, `build_component_contribution_from_production_bridge_execution` added to `mpl_sim.network` in new `production_component_bridge.py` module. Bridge boundary is the first controlled seam toward future production component contribution execution. Does NOT execute real production component classes. Does NOT define or call a method named `contribute`. Does NOT assemble `SystemState` or `FluidState`. Does NOT call CoolProp, PropertyBackend, correlations, or any registry. All six known production classes (`Component`, `Pipe`, `PumpComponent`, `AccumulatorComponent`, `EvaporatorComponent`, `CondenserComponent`) still have `NO_CONTRIBUTE_METHOD` as confirmed by Phase 14G inspection — no `contribute(...)` is implemented on any production class. Bridge objects used in tests are controlled stubs (NOT real production components) exposing `produce_records`. Physical production-component execution and Block 15B physical single-loop network work remain deferred. No arbitrary-topology physical simulation exists. Fully integrated with the existing Phase 14D/14C/14A/13G path. 75 focused bridge tests; 1264 network tests; 5125 tests in the full suite, including 60 example tests. See `BLOCK_15A1_PRODUCTION_BRIDGE_BOUNDARY_AUDIT.md`.** |
| **Block 15A.4 status** | **Closeout checkpoint complete and independently audited. Block 15A — Production Component Bridge MVP — is complete within its planned MVP scope. No new runtime modules added. New test file `tests/network/test_production_bridge_closeout_integration.py` (38 focused tests) proves the full end-to-end path: explicitly supplied production-like producers read unknowns through `ReadOnlyUnknownView` (Block 15A.2), return `ContributionRecordSet` records, records map through `ContributionResidualMap` (Phase 14D) to `ComponentContribution` (Phase 14C), contributions build `PhysicalResidualAdapterSet` (Phase 14C), `build_network_residual_evaluators` (Phase 14A) converts to `NetworkResidualEvaluator` tuple, `evaluate_network_residuals` (Phase 13G) evaluates at the known algebraic solution point (all residuals zero), and `solve_network_residual_problem` (Phase 13H) converges from an off-solution initial guess to the known algebraic solution. The solver compatibility proof remains callback-only, explicitly algebraic, and non-physical. Residual ordering follows assembly declaration order. All six production component classes still report `NO_CONTRIBUTE_METHOD`. No CoolProp, no PropertyBackend, no CorrelationRegistry, no HX model, no SystemState, no FluidState, no `contribute(...)` call, no `component_type` physics dispatch, no generic network-graph solve. Block 15A provides: controlled bridge boundary (15A.1), read-only unknown-vector view (15A.2), controlled production-like producer path (15A.3), and integration proof through the existing Phase 14D/14C/14A/13G/13H stack (15A.4). Block 15A does NOT implement: real production component execution, production `Component.contribute(...)`, `SystemState` assembly, `FluidState` construction, property-backed/correlation-backed/HX-model-backed graph execution, Block 15B physical single-loop network simulation, arbitrary-topology physical simulation, or generic `solve(network)` / `NetworkGraph.solve()`. 38 new focused tests; 1418 network tests; 5279 tests in the full suite. Lint and format clean. See `BLOCK_15A4_PRODUCTION_BRIDGE_CLOSEOUT_AUDIT.md`. Verified 2026-06-23.** |
| **Block 15A.3 status** | **Checkpoint complete. Controlled production-like bridge path MVP introduced. `ProductionLikeBridgeContext`, `ProductionLikeRecordProducerProtocol`, `ProductionLikeComponentBinding`, `ProductionLikeComponentSet`, `execute_production_like_contributions`, `build_component_contribution_from_production_like_execution` added to `mpl_sim.network` in new `production_like_bridge.py` module. Production-like objects are explicitly supplied by the caller and use `produce_records(...)` — not `contribute(...)`. `ProductionLikeBridgeContext` includes a pre-built `ReadOnlyUnknownView` (Block 15A.2) that lets stub producers read component-scoped and node-scoped unknowns without accessing the full unknown vector directly. Context construction validates exact assembly unknown coverage via `ReadOnlyUnknownView`. Execution loop validates exact producer coverage, validates return types and record ownership, checks for duplicates, and propagates producer exceptions. Convenience wrapper feeds records through Phase 14D `ContributionResidualMap` to Phase 14C `ComponentContribution`. Does NOT execute real production component classes. Does NOT define or call any method named `contribute`. Does NOT assemble `SystemState` or `FluidState`. Does NOT call CoolProp, PropertyBackend, correlations, or any registry. Does NOT attach physical state to graph nodes. Does NOT infer physics from `component_type`. Does NOT add `solve(network)` or `NetworkGraph.solve()`. All six known production classes (`Component`, `Pipe`, `PumpComponent`, `AccumulatorComponent`, `EvaporatorComponent`, `CondenserComponent`) still have `NO_CONTRIBUTE_METHOD` as confirmed by Phase 14G inspection. Block 15B physical single-loop network simulation remains deferred. Arbitrary-topology physical simulation remains deferred. Fully backward-compatible with Block 15A.1 and 15A.2.** |
| **Block 15A.2 status** | **Checkpoint complete. Read-only unknown/state bridge MVP introduced. `ReadOnlyUnknownView`, `ComponentUnknownView`, `NodeUnknownView`, `build_readonly_unknown_view` added to `mpl_sim.network` in new `readonly_state_bridge.py` module. This checkpoint makes Block 15A.1 more useful by giving bridge providers a safe way to read unknown-vector values by component/node mapping through the existing `NetworkBindingContext` and `ComponentStateMap`. `ReadOnlyUnknownView` is a frozen, validated read-only view of the full unknown-value vector: validates that all assembly-declared unknowns are present, no extras, all values finite and non-bool; exposes values by raw unknown name; provides component-scoped and node-scoped sub-views. `ComponentUnknownView` exposes only unknowns mapped to a specific `ComponentInstanceId` via `ComponentStateMap.unknown_to_component`. `NodeUnknownView` exposes only unknowns mapped to a specific `GraphNodeId` via `ComponentStateMap.unknown_to_node`. `build_readonly_unknown_view` accepts both `NetworkUnknownValues` and plain `Mapping[str, float]`. Does NOT assemble `SystemState`. Does NOT create `FluidState`. Does NOT execute real production components. Does NOT define or call `Component.contribute(...)`. Does NOT call CoolProp, PropertyBackend, correlations, or any registry. Does NOT add `solve(network)` or `NetworkGraph.solve()`. Block 15B physical single-loop network simulation remains deferred. Arbitrary-topology physical simulation remains deferred. Fully backward-compatible with Block 15A.1 — existing bridge behavior unchanged, `ProductionBridgeExecutionContext` unmodified. 61 focused tests; 1325 network tests; 5186 tests in the full suite, including 60 example tests.** |
| **Phase 14G status** | **Checkpoint complete. Production component contribution contract inspection implemented. `ProductionComponentContractStatus`, `ProductionComponentContributionSignature`, `ProductionComponentInspectionResult`, `inspect_production_component_contract`, `inspect_known_production_component_contracts` added to `mpl_sim.network` in new `production_component_inspection.py` module. Inspection layer: static only; uses `inspect` module; never instantiates production component classes; never calls `contribute(...)` or any other component method; all known production components (`Component`, `Pipe`, `PumpComponent`, `AccumulatorComponent`, `EvaporatorComponent`, `CondenserComponent`) return `NO_CONTRIBUTE_METHOD` — the production `contribute(...)` contract is not yet implemented on any class. `ProductionComponentContractStatus` provides string constants for inspection outcomes. `ProductionComponentContributionSignature` captures parameter names, return annotation, state/context dependency flags, and varargs/kwargs flags. `ProductionComponentInspectionResult` stores class name, module name, status, optional signature, and notes tuple — no component instance stored. 60 focused tests; 1189 network tests; 5050 tests total.** |
| **Phase 14F status** | **Checkpoint complete. Component-like contribution provider adapter implemented. `ComponentProviderExecutionContext`, `ComponentContributionProviderProtocol`, `ComponentContributionProviderBinding`, `ComponentContributionProviderSet`, `execute_component_provider_contributions`, `build_component_contribution_from_provider_execution` added to `mpl_sim.network` in new `component_provider_adapters.py` module. Provider layer: `ComponentProviderExecutionContext` is an immutable context (binding context + defensive unknown-values copy + optional metadata); `ComponentContributionProviderBinding` binds a `ComponentInstanceId` to a controlled provider object with a callable `produce_records` method (NOT named `contribute`); `ComponentContributionProviderSet` is an ordered, validated, duplicate-rejecting collection; `execute_component_provider_contributions` validates exact binding coverage, invokes each provider's `produce_records`, validates all return types (must be `ContributionRecordSet`), validates record ownership, checks for duplicates, and returns a `ContributionRecordSet`; `build_component_contribution_from_provider_execution` is a convenience wrapper to Phase 14D mapping and Phase 14C `ComponentContribution`. No real component execution, no `Component.contribute(...)`, no method named `contribute` defined, no `SystemState`, no `FluidState`, no property lookup, no `CoolProp`, no automatic physics from `component_type`. Fully integrated with Phase 14D residual map, Phase 14C adapter, Phase 14A physical adapters, and Phase 13G/13H evaluation/solve stack. 63 focused tests; 1129 network tests; 4990 tests total.** |
| **Block 15B.1 status** | **Checkpoint complete and independently audited. Fixed single-loop scenario declaration MVP introduced. `FixedSingleLoopComponentIds`, `FixedSingleLoopNodeIds`, `FixedSingleLoopUnknownNames`, `FixedSingleLoopResidualNames`, `FixedSingleLoopScenario`, `build_fixed_single_loop_scenario` added to `mpl_sim.network` in new `fixed_single_loop_scenario.py` module. Introduces explicit topology, unknown, and residual declarations for the fixed minimal loop: accumulator -> pump -> evaporator -> condenser -> accumulator. All containers are frozen dataclasses; the factory validates uniqueness, non-emptiness, and type correctness before constructing the graph, assembly, and binding context. The scenario holds a `NetworkGraph` (4 nodes, 4 components, validated closed single loop), a `NetworkResidualAssembly` (8 unknowns, 8 residuals), and a `NetworkBindingContext` (full state map for all unknowns and residuals). Does NOT execute production component physics. Does NOT assemble `SystemState`. Does NOT create `FluidState`. Does NOT call CoolProp, PropertyBackend, correlations, or HX models. Does NOT infer physics from `component_type`. Does NOT add `solve(network)` or `NetworkGraph.solve()`. All six production classes still report `NO_CONTRIBUTE_METHOD`. Block 15B.2 remains responsible for physical residual assembly. Arbitrary-topology physical simulation remains deferred. Generic `solve(network)` / `NetworkGraph.solve()` remain forbidden/deferred. 84 focused tests; 38 Block 15A.4 closeout regression tests; 1502 network tests; 5363 full-suite tests; six examples passed; Ruff, Black, and diff checks clean. See `BLOCK_15B1_FIXED_SINGLE_LOOP_SCENARIO_AUDIT.md`. Verified 2026-06-23.** |
| **Block 15D-A status** | **Checkpoint complete. Block 15D-A — Hydraulic Closure Primitives MVP — introduces explicit algebraic closure primitives for hydraulic networks. New modules: `src/mpl_sim/network/hydraulic_closures.py` and `src/mpl_sim/network/hydraulic_closure_diagnostics.py`. Public API: `HydraulicClosureKind`; `HydraulicClosureDeclaration`; `ImposedMassFlowClosure` (`r = mdot - imposed_value`); `ImposedBranchSplitClosure` (`r = mdot_branch - split_fraction * mdot_total`, with explicit `0 < split_fraction < 1`, a user-imposed constraint rather than predicted distribution); `ImposedPressureClosure` (`r = P - imposed_value`); `LinearPressureDropClosure` (`r = P_in - P_out - resistance * mdot`); `QuadraticPressureDropClosure` (`r = P_in - P_out - coefficient * mdot * abs(mdot)`); `PressureCompatibilityClosure` (`r = resistance_a * mdot_a - resistance_b * mdot_b`, a simplified equality of caller-supplied linearized path-drop expressions, not a general manifold pressure equation); `HydraulicClosureResidualSet`; `build_hydraulic_closure_residuals`; `HydraulicClosureCategory`; `HydraulicClosureDiagnostic`; `HydraulicClosureDiagnosticResult`; `evaluate_hydraulic_closure_sufficiency`; and `make_two_branch_parallel_diagnostic`. Block 15D-A is not property-, correlation-, or HX-backed; does not execute production components; does not assemble `SystemState` or construct `FluidState`; and adds no generic `solve(network)` or `NetworkGraph.solve()`. Real valve Kv/Cv, Darcy-Weisbach, friction-factor, and property-dependent laws remain deferred. Diagnostics are deterministic category-presence checks for the fixed two-branch MVP only; they do not validate combined equation count, symbolic rank, arbitrary-network closure, or DAE solvability. Integration proves the 15C-B residuals and the closure residuals separately evaluate to zero at the same consistent point; no combined residual assembly or solve is performed or claimed. All six production classes remain `NO_CONTRIBUTE_METHOD`. Later blocks remain responsible for thermal closures, production component adapters, property/correlation/HX-backed closures, configurable scenario building, and physically predictive branch-flow solves.** |
| **Block 15D-A audit** | **Approved with minor fixes. See `docs/validation/audits/BLOCK_15D_A_HYDRAULIC_CLOSURE_PRIMITIVES_AUDIT.md`. Verified 2026-06-24.** |
| **Block 15C-B status** | **Checkpoint complete and independently audited. Block 15C-B — Branch Residual and Parallel Evaluation MVP — introduces explicit algebraic residual assembly and evaluation for the fixed 15C-A parallel topology. New module `src/mpl_sim/network/parallel_topology_residuals.py` added. New public symbols: `ParallelTopologyResidualParameters` (7 explicit scalar parameters: accumulator_pressure_reference, pump_pressure_rise, branch_a/b_pressure_drop, merge_a/b_pressure_drop, condenser_pressure_drop); `ParallelTopologyPhysicalResidualAssembly` (frozen: scenario + parameters + ContributionResidualMap + ComponentContributionAdapterSet with 7 adapters covering all 13 residuals); `build_parallel_topology_physical_residuals` (deterministic factory); `ParallelTopologyEvaluationResult` (frozen evaluation result with read-only unknown/residual maps, max-abs and L2 norms); `evaluate_parallel_topology_residuals` (validates 13 unknowns, evaluates all 13 residuals via Phase 14A/13G infrastructure, returns frozen result); `build_parallel_topology_report` (plain serializable dict, no file writes, no pandas). Residual equations — mass-balance (6): `mass_balance:n_cond_out = mdot_condenser - mdot_accumulator`; `mass_balance:n_acc_out = mdot_accumulator - mdot_pump`; `mass_balance:n_pump_out = mdot_pump - mdot_branch_a - mdot_branch_b`; `mass_balance:n_a_out = mdot_branch_a - mdot_merge_a`; `mass_balance:n_b_out = mdot_branch_b - mdot_merge_b`; `mass_balance:n_merge_out = mdot_merge_a + mdot_merge_b - mdot_condenser`. Pressure residuals (7): `pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference`; `pressure_drop:pump = P_n_pump_out - P_n_acc_out - pump_pressure_rise`; `pressure_drop:branch_a = P_n_a_out - P_n_pump_out + branch_a_pressure_drop`; `pressure_drop:branch_b = P_n_b_out - P_n_pump_out + branch_b_pressure_drop`; `pressure_drop:merge_a = P_n_merge_out - P_n_a_out + merge_a_pressure_drop`; `pressure_drop:merge_b = P_n_merge_out - P_n_b_out + merge_b_pressure_drop`; `pressure_drop:condenser = P_n_cond_out - P_n_merge_out + condenser_pressure_drop`. All residuals evaluate to zero at consistent point (m=1.0, split 0.4/0.6, compatible branch drops: 30000+20000=40000+10000=50000). Solving is EXPLICITLY DEFERRED: (a) mass-flow subspace has 2 degrees of freedom (rank of 6 mass-balance equations = 5; 7 unknowns - 5 = 2 free parameters: total flow + branch split ratio); (b) 7 pressure equations for 6 unknowns are overdetermined unless branch compatibility condition holds (dP_a + dP_ma == dP_b + dP_mb); Phase 13H requires a square determined system. A physical solve requires explicit total-flow and branch-split closure constraints plus pressure compatibility handling; this MVP does not invent them. Contribution attribution: accumulator (mass_balance:n_cond_out + pressure_drop:accumulator), pump (mass_balance:n_acc_out + pressure_drop:pump), branch_a (mass_balance:n_a_out + pressure_drop:branch_a), branch_b (mass_balance:n_b_out + pressure_drop:branch_b), merge_a (mass_balance:n_pump_out + pressure_drop:merge_a), merge_b (mass_balance:n_merge_out + pressure_drop:merge_b), condenser (pressure_drop:condenser only). Does NOT: execute production components, call `contribute(...)`, assemble `SystemState`, create `FluidState`, call CoolProp/PropertyBackend/correlations/HX models, infer physics from `component_type`, implement arbitrary-topology physical simulation, generic `solve(network)`, or `NetworkGraph.solve()`. All six production classes remain `NO_CONTRIBUTE_METHOD`. Test files: `tests/network/test_parallel_topology_residuals.py` (90 tests covering parameters, assembly, residual equations, sign convention, evaluation, solver-deferred, report, boundary invariants); `tests/network/test_parallel_topology_mvp_closeout.py` (62 tests: 15C-A regression, 15C-B assembly+evaluation+report, Block 15C completeness assertions, Block 15B regression, Phase 14G regression, public API). 152 new focused tests; 2047 network tests; 5908 full-suite tests; six examples passed; Ruff, Black, and diff checks clean. See `BLOCK_15C_B_BRANCH_RESIDUAL_PARALLEL_EVALUATION_AUDIT.md`. Verified 2026-06-24.** |
| **Block 15C-A status** | **Checkpoint complete and independently audited. Junction/manifold, fixed two-branch parallel topology, and valve/local-loss declarations are implemented as frozen, validated symbolic objects. The 6-node/7-component scenario declares a 13×13 name/unit structure only; it has no equations or callbacks. `require_closed_loop=False` skips only closed-single-loop validation, while graph, assembly, binding coverage, IDs/names, branches, and manifolds remain validated. No branch residual assembly, physical flow split, valve/local-loss equations, production component execution, `SystemState`, `FluidState`, property/correlation/HX calls, arbitrary-topology physical simulation, generic `solve(network)`, or `NetworkGraph.solve()` was added. Block 15C-B remains responsible for branch residual assembly and parallel topology evaluation. All six production classes remain `NO_CONTRIBUTE_METHOD`. 63 topology-declaration tests; 81 parallel-topology tests; 1,895 network tests; 5,756 full-suite tests; six examples passed; Ruff, Black, and diff checks clean. See `BLOCK_15C_A_TOPOLOGY_DECLARATION_FOUNDATION_AUDIT.md`. Verified 2026-06-24.** |
| **Block 15B.4 status** | **Closeout checkpoint complete and independently audited. Block 15B — Minimal Physical Single-Loop Network MVP — is complete within its planned MVP scope. Tests-and-docs-only checkpoint: no new runtime modules added. New test file `tests/network/test_fixed_single_loop_mvp_closeout.py` (47 focused acceptance/integration tests) proves the full fixed-loop MVP path end-to-end and documents the mass-flow gauge design explicitly. Full path exercised: `build_fixed_single_loop_scenario` (15B.1) → `FixedSingleLoopResidualParameters` + `build_fixed_single_loop_physical_residuals` (15B.2) → `evaluate_fixed_single_loop_residuals` (zero residuals at consistent point, nonzero at perturbed points) → `solve_fixed_single_loop_residuals` (converges from off-pressure guess; preserves continuity-consistent mass-flow gauge; inconsistent gauge yields `converged=False` with reason string containing "continuity") → `build_fixed_single_loop_report` (plain JSON-serializable dict, no file writes). Gauge behavior explicitly tested: consistent gauge preserved in `solved_unknown_values`; solver does not alter mdot unknowns; different consistent gauge values yield the same pressure solution; the absolute common mass-flow level is NOT determined by this solver. Regression coverage: 15B.3 (100 pass), 15B.2 (102 pass), 15B.1 (84 pass), 15A.4 (38 pass), all six production classes still report `NO_CONTRIBUTE_METHOD`. Architecture boundary tests: no CoolProp, no PropertyBackend, no SystemState, no FluidState, no CorrelationRegistry, no `.contribute(...)` attribute call, no bare `import mpl_sim.components`, no mpl_sim.properties in the new test file. Public API audit: no new public symbols added to `mpl_sim.network.__all__` beyond the 15B.3 baseline; all 15B.3 exports present. 47 new focused tests; 1751 network tests; 5612 full-suite tests; six examples passed; Ruff, Black, and diff checks clean. Block 15B provides: fixed single-loop scenario declaration (15B.1); explicit parameterized algebraic residual assembly (15B.2); fixed-loop residual evaluation (15B.3); fixed-loop pressure-subsystem solve using existing Phase 13H callback-only solver (15B.3); lightweight report generation (15B.3); acceptance/integration proof (15B.4). The solve uses an explicit mass-flow gauge and does NOT determine the absolute common mass-flow level. Block 15B does NOT implement: arbitrary-topology physical simulation; generic `solve(network)`; `NetworkGraph.solve()`; real production component execution; production `Component.contribute(...)`; `SystemState` assembly; `FluidState` construction; property-backed residuals; correlation-backed residuals; HX-model-backed residuals. Later blocks remain responsible for topology extensions, real component execution, and property/correlation/HX-backed physics. See `BLOCK_15B4_FIXED_LOOP_CLOSEOUT_AUDIT.md`. Verified 2026-06-24.** |
| **Block 15B.3 status** | **Checkpoint complete and independently audited. Fixed single-loop evaluate/solve/report MVP introduced. `FixedSingleLoopEvaluationResult`, `FixedSingleLoopSolveRequest`, `FixedSingleLoopSolveResult`, `evaluate_fixed_single_loop_residuals`, `solve_fixed_single_loop_residuals`, `build_fixed_single_loop_report` added to `mpl_sim.network` in new `fixed_single_loop_runner.py` module. Evaluation path: accepts scenario (15B.1) + parameters (15B.2) + explicit unknown values → builds 15B.2 physical assembly internally → Phase 14A evaluators → Phase 13G `evaluate_network_residuals` → frozen `FixedSingleLoopEvaluationResult` with residual values, residual ordering, max-absolute and L2 norms. Solver path: accepts `FixedSingleLoopSolveRequest` and uses the explicit, continuity-consistent initial mass-flow values as the fixed gauge for the underdetermined common mass-flow level; the existing Phase 13H `solve_network_residual_problem` solves the determined four-pressure subsystem using the original 15B.2 pressure residual callbacks; all eight original residuals are then re-evaluated before returning a frozen `FixedSingleLoopSolveResult`. Inconsistent initial mass flows fail clearly without iteration. No new solver infrastructure is added. Report path: `build_fixed_single_loop_report` returns a plain serializable dict with scenario symbolic IDs, unknown values, residual values, norms, and convergence status. Does NOT execute production components. Does NOT assemble `SystemState`. Does NOT create `FluidState`. Does NOT call CoolProp, PropertyBackend, correlations, or HX models. Does NOT infer physics from `component_type`. Does NOT add `solve(network)` or `NetworkGraph.solve()`. Does NOT implement arbitrary-topology simulation. All six production classes still report `NO_CONTRIBUTE_METHOD`. Block 15B.3 is still fixed-architecture only. 100 focused tests; 1704 network tests; 5565 full-suite tests; six examples passed; Ruff, Black, and diff checks clean. See `BLOCK_15B3_FIXED_LOOP_RUN_REPORT_AUDIT.md`. Verified 2026-06-23.** |
| **Block 15B.2 status** | **Checkpoint complete and independently audited. Fixed single-loop physical residual assembly MVP introduced. `FixedSingleLoopResidualParameters`, `FixedSingleLoopPhysicalResidualAssembly`, `build_fixed_single_loop_physical_residuals`, `build_component_contribution_from_fixed_single_loop_residuals` added to `mpl_sim.network` in new `fixed_single_loop_residuals.py` module. Bridge from the 15B.1 declaration to physical-style residual evaluation using the existing Phase 14A/14C/14D contribution infrastructure. Explicit parameterized algebraic residual equations for all 8 residuals of the fixed loop (4 mass-balance continuity + 4 explicit pressure residuals). Sign convention: `pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference`; `pressure_drop:pump = P_n_pump_out - P_n_acc_out - pump_pressure_rise`; `pressure_drop:evaporator = P_n_evap_out - P_n_pump_out + evaporator_pressure_drop`; `pressure_drop:condenser = P_n_cond_out - P_n_evap_out + condenser_pressure_drop`. Contribution attribution: each component owns 1 mass-balance residual + 1 pressure residual; adapter set has 4 entries. All 4 parameters required explicitly; bool/NaN/inf rejected. Evaluation path: `adapter_set` → `build_physical_adapters_from_contributions` → `build_network_residual_evaluators` → `evaluate_network_residuals`. Does NOT execute production components. Does NOT assemble `SystemState`. Does NOT create `FluidState`. Does NOT call CoolProp, PropertyBackend, correlations, or HX models. Does NOT infer physics from `component_type`. Does NOT add `solve(network)` or `NetworkGraph.solve()`. Does NOT implement arbitrary-topology simulation. All six production classes still report `NO_CONTRIBUTE_METHOD`. Block 15B.3 (minimal solve/report helper) remains deferred. 102 focused tests; 84 Block 15B.1 scenario regression tests; 38 Block 15A.4 closeout regression tests; 1604 network tests; 5465 full-suite tests; six examples passed; Ruff, Black, and diff checks clean. See `BLOCK_15B2_FIXED_LOOP_PHYSICAL_RESIDUALS_AUDIT.md`. Verified 2026-06-23.** |
| **Block 15D-B status** | **Checkpoint complete and independently audited. Block 15D-B — Thermal Closure Primitives MVP — introduces explicit algebraic thermal closure primitives. New modules: `src/mpl_sim/network/thermal_closures.py` and `src/mpl_sim/network/thermal_closure_diagnostics.py`. Public API: `ThermalClosureKind`; `ThermalClosureDeclaration`; `FixedHeatRateClosure` (`r = q - q_fixed`); `ImposedEnthalpyClosure` (`r = h - h_imposed`, user-imposed scalar, not a property calculation); `ImposedTemperatureLikeClosure` (`r = theta - theta_imposed`, symbolic scalar closure, not property-backed temperature); `SensibleHeatRateClosure` (`r = q - mdot * cp * (theta_out - theta_in)`, explicit positive cp required, no property lookup); `EnthalpyFlowHeatRateClosure` (`r = q - mdot * (h_out - h_in)`, no phase logic, no property backend); `EffectivenessHeatRateClosure` (`r = q - effectiveness * q_max`, purely algebraic, 0 <= effectiveness <= 1, NOT a real HX effectiveness-NTU model); `RecuperatorEnergyBalanceClosure` (`r = q_hot + q_cold`, enforces energy consistency only, no UA/LMTD/NTU/HTC); `ThermalClosureResidualSet`; `build_thermal_closure_residuals`; `ThermalClosureCategory`; `ThermalClosureDiagnostic`; `ThermalClosureDiagnosticResult`; `evaluate_thermal_closure_sufficiency`; `make_basic_thermal_loop_diagnostic` (requires HEAT_RATE + ENTHALPY_FLOW_RELATION); `make_recuperator_thermal_diagnostic` (requires RECUPERATOR_ENERGY_BALANCE + ENTHALPY_FLOW_RELATION). Block 15D-B is not property-backed, not correlation-backed, not HX-model-backed. It does not execute production components, does not assemble `SystemState`, does not construct `FluidState`, and adds no generic `solve(network)` or `NetworkGraph.solve()`. Imposed enthalpy and temperature-like closures are user-imposed scalar constraints, not thermodynamic property calculations. Sensible heat and enthalpy-flow closures are explicit algebraic relations with caller-supplied values. Simplified effectiveness/recuperator closures do not represent real HX models. Real LMTD/NTU/UA, HTC, phase, quality, saturation, property-dependent relations, and HX-backed closures remain deferred. Later blocks remain responsible for production component adapters, property/correlation/HX-backed closures, configurable scenario building, and physically predictive solves. All six production classes remain `NO_CONTRIBUTE_METHOD`. See `BLOCK_15D_B_THERMAL_CLOSURE_PRIMITIVES_AUDIT.md`. Verified 2026-06-25.** |
| **Branch status** | **Block 15D-B on `phase-15d-b-thermal-closure-primitives`, based on merged Block 15D-A.** |
| **Current active phase** | **Block 15D-B — Thermal Closure Primitives MVP** |
| **Next immediate slice** | Post-15D-B planning: valve Kv/Cv, Darcy-Weisbach, property-backed closures, configurable scenario building, and combined solve of closure+physical residuals remain future work |
| **Baseline before this block** | Block 15D-A: 6113 tests. The previously recorded 6106 total was stale/internally inconsistent: 5908 + 205 = 6113. |
| **Test status** | **6316 passed, 0 errors, 0 failed, 0 skipped, 0 xfailed, 0 deselected (corrected baseline 6113 + 203 Block 15D-B new tests: 128 thermal closure primitives + 39 thermal closure diagnostics + 36 thermal closure integration). Network suite: 2455 passed (2252 + 203). Six examples passed.** |
| **Lint status** | **Ruff: clean (0 violations). git diff --check: clean.** |
| **Format status** | **Black: clean (0 reformats needed).** |

## Post-14G block strategy

The following blocks are planning only; none is implemented by Phase 14G.

### Block 15A — Production Component Bridge MVP (**COMPLETE** as of Block 15A.4)

Block 15A is complete. Implemented across four checkpoints (15A.1–15A.4):
- controlled bridge boundary (`ProductionBridgeExecutionContext`, 15A.1);
- read-only unknown-vector view (`ReadOnlyUnknownView`, 15A.2);
- controlled production-like producer path (`execute_production_like_contributions`, 15A.3);
- integration proof through existing Phase 14D/14C/14A/13G/13H stack (15A.4 closeout).

Block 15A does NOT implement: real production `Component.contribute(...)`, `SystemState`
assembly, `FluidState` construction, property-backed/correlation-backed/HX-model-backed
graph execution, Block 15B physical single-loop network simulation, arbitrary-topology
physical simulation, or generic `solve(network)` / `NetworkGraph.solve()`.

### Block 15B — Minimal Physical Single-Loop Network MVP (**COMPLETE** as of Block 15B.4)

Block 15B is complete. Implemented across four checkpoints (15B.1–15B.4):
- fixed single-loop scenario declaration (`build_fixed_single_loop_scenario`, 15B.1);
- explicit parameterized algebraic residual assembly (`build_fixed_single_loop_physical_residuals`, 15B.2);
- fixed-loop residual evaluation and pressure-subsystem solve via Phase 13H callback-only solver
  (`evaluate_fixed_single_loop_residuals`, `solve_fixed_single_loop_residuals`, 15B.3);
- lightweight report generation (`build_fixed_single_loop_report`, 15B.3);
- acceptance/integration proof with full-path tests and gauge behavior documentation (15B.4 closeout).

The solve uses an explicit mass-flow gauge: the caller supplies continuity-consistent mass-flow
values; the solver preserves them and solves only the determined pressure subsystem.  The absolute
common mass-flow level is NOT determined by this solver.

Block 15B does NOT implement:
- arbitrary-topology physical simulation;
- generic `solve(network)` / `NetworkGraph.solve()`;
- real production `Component.contribute(...)`;
- `SystemState` assembly or `FluidState` construction;
- property-backed, correlation-backed, or HX-model-backed residuals.

Later blocks remain responsible for topology extensions, real component execution, and
property/correlation/HX-backed physics.

### Block 15C — Topology Extensions MVP

- junction/manifold foundation;
- parallel evaporator topology;
- valve/pressure-loss element;
- branch residual assembly.

### Block 15D — Configurable MPL Scenario v1

- scenario schema;
- component selection;
- network build from scenario;
- run and diagnostics.

Each future block may use internal checkpoints, but every checkpoint must
preserve architecture boundaries and pass the full validation gate before
merge.

Block 15B.4 fixed-loop MVP closeout is complete. Block 15B — Minimal Physical Single-Loop Network MVP — is now complete.

- **`tests/network/test_fixed_single_loop_mvp_closeout.py`** added — 47 focused
  acceptance/integration tests proving the full fixed-loop MVP path end-to-end.
- **No new runtime module added.** All existing APIs from Blocks 15B.1–15B.3 were sufficient.
- **Full path exercised:** `build_fixed_single_loop_scenario` (15B.1) →
  `FixedSingleLoopResidualParameters` + `build_fixed_single_loop_physical_residuals` (15B.2) →
  `evaluate_fixed_single_loop_residuals` (zero at consistent point, nonzero at perturbed points) →
  `solve_fixed_single_loop_residuals` (converges from off-pressure with consistent gauge) →
  `build_fixed_single_loop_report` (plain JSON-serializable dict, no file writes).
- **Gauge behavior explicitly documented and tested:**
  - Consistent gauge (all mdot equal) is preserved in `solved_unknown_values`.
  - Solver does not alter mdot unknowns — only the pressure subsystem is solved.
  - Different consistent gauge values yield the same pressure solution; the absolute
    common mass-flow level is NOT determined by this solver.
  - Inconsistent gauge (mdot_pump ≠ mdot_accumulator) gives `converged=False` and
    a reason string containing "continuity".
- **Regression confirmed:** 15B.3 (100), 15B.2 (102), 15B.1 (84), 15A.4 (38) pass;
  all six production classes still report `NO_CONTRIBUTE_METHOD`.
- **Architecture boundaries confirmed:** no CoolProp, PropertyBackend, SystemState,
  FluidState, CorrelationRegistry, `.contribute(...)` call, or bare `mpl_sim.components`
  namespace import in the new test file; no executable `NetworkGraph.solve()` or
  bare `def solve` in the three fixed-loop runtime modules; no `component_type` Name
  nodes in fixed-loop runtime modules.
- **Public API audit:** no new symbols added to `mpl_sim.network.__all__` beyond the
  15B.3 baseline; all 15B.3 exports remain present; no private symbols.
- **Block 15B provides** (complete): fixed single-loop scenario declaration (15B.1);
  explicit parameterized algebraic residual assembly (15B.2); fixed-loop residual
  evaluation, pressure-subsystem solve, and report generation (15B.3); acceptance/
  integration proof with gauge behavior documentation (15B.4).
- **Block 15B does NOT implement:** arbitrary-topology physical simulation; generic
  `solve(network)` / `NetworkGraph.solve()`; real production `Component.contribute(...)`;
  `SystemState` assembly; `FluidState` construction; property-backed, correlation-backed,
  or HX-model-backed residuals.
- **Later blocks remain responsible for:** topology extensions, real component execution,
  and property/correlation/HX-backed physics.

Block 15A.4 production bridge closeout is complete. Block 15A — Production Component Bridge MVP — is now complete.

- **`tests/network/test_production_bridge_closeout_integration.py`** added — 38 focused
  integration tests proving the full end-to-end path from production-like producers
  through the existing Phase 14D/14C/14A/13G/13H residual stack.
- **No new runtime module added.** All existing APIs from Blocks 15A.1–15A.3 and
  Phases 14D/14C/14A/13G/13H were sufficient.
- **Controlled algebraic system** (4 unknowns / 4 residuals, unique solution at
  ``{mdot:evap=0.1, mdot:cond=0.1, P:n1=200.0, P:n2=150.0}``) used to verify the
  full path without property lookup, real component execution, or HX models.
- **End-to-end path verified:**
  ``execute_production_like_contributions`` (15A.3)
  → ``map_contribution_records_to_component_contribution`` (14D)
  → ``ComponentContribution`` (14C)
  → ``build_physical_adapters_from_contributions`` (14C)
  → ``build_network_residual_evaluators`` (14A)
  → ``evaluate_network_residuals`` (13G): all residuals zero at solution point.
- **Phase 13H solver compatibility verified:** ``solve_network_residual_problem``
  converges from an off-solution initial guess to the exact algebraic solution.
  This is algebraic callback solving only — NOT ``solve(network)``, NOT physical
  network simulation.
- **Residual ordering verified:** matches assembly declaration order (nodes first,
  then components; both in graph insertion order).
- **All six production classes still report ``NO_CONTRIBUTE_METHOD``.**
- **Block 15A provides** (complete): controlled bridge boundary (15A.1); read-only
  unknown-vector view (15A.2); controlled production-like producer path (15A.3);
  integration proof through the existing Phase 14D/14C/14A/13G/13H stack (15A.4).
- **Block 15A does NOT implement:** real production ``Component.contribute(...)``;
  ``SystemState`` assembly; ``FluidState`` construction; property-backed,
  correlation-backed, or HX-model-backed graph execution; Block 15B physical
  single-loop network simulation; arbitrary-topology physical simulation; generic
  ``solve(network)`` or ``NetworkGraph.solve()``.
- **Block 15B was deferred beyond Block 15A and is now complete within its fixed-loop MVP scope.**
- **Arbitrary-topology physical simulation remains deferred.**

Block 15A.3 controlled production-like bridge path MVP is complete as a checkpoint.

- **`src/mpl_sim/network/production_like_bridge.py`** added — controlled
  production-like stub/adapter path making Block 15A.1 more concrete by
  exposing the Block 15A.2 ``ReadOnlyUnknownView`` directly inside the
  execution context.
- **`ProductionLikeBridgeContext`** — frozen context carrying the Phase 14B
  binding context, defensively copied read-only unknown values, a pre-built
  ``ReadOnlyUnknownView`` for component- and node-scoped access, and optional
  metadata.  Construction validates exact assembly unknown coverage via
  ``ReadOnlyUnknownView`` — a stricter guarantee than the plain Block 15A.1
  bridge context.  Stores no ``SystemState``, creates no ``FluidState``, calls
  no property backend.
- **`ProductionLikeRecordProducerProtocol`** — ``typing.Protocol`` with
  ``runtime_checkable``; structural duck-type check for ``produce_records``.
  Method is deliberately NOT named ``contribute`` and does NOT call
  ``Component.contribute(...)``.
- **`ProductionLikeComponentBinding`` / ``ProductionLikeComponentSet`** —
  immutable, ordered, duplicate-rejecting bindings from component IDs to
  controlled production-like producers exposing a callable ``produce_records``
  method.
- **`execute_production_like_contributions(...)`** — validates exact producer
  coverage (missing and extra producer bindings rejected), builds a shared
  ``ProductionLikeBridgeContext`` (which validates exact unknown coverage via
  ``ReadOnlyUnknownView``), invokes each producer's ``produce_records(ctx)``
  in binding order, validates return types (``ContributionRecordSet`` required),
  validates record ownership and duplicates, propagates producer exceptions, and
  returns a ``ContributionRecordSet``.
- **`build_component_contribution_from_production_like_execution(...)`** — thin
  wrapper through Phase 14D ``ContributionResidualMap`` mapping to Phase 14C
  ``ComponentContribution``.
- **What "production-like" means here:**
  - object has an explicit component instance ID binding;
  - object reads scoped unknowns via ``ReadOnlyUnknownView`` (Block 15A.2);
  - object returns explicit ``ContributionRecordSet``;
  - object is NOT one of the real production component classes;
  - object is NOT inferred from ``component_type``;
  - object does NOT call component physics, HX models, correlations, or
    properties.
- **What this does NOT do:**
  - Does NOT execute real production component classes.
  - Does NOT define or call any method named ``contribute``.
  - Does NOT assemble ``SystemState`` or ``FluidState``.
  - Does NOT call CoolProp, PropertyBackend, correlations, or any registry.
  - Does NOT attach physical state to graph nodes.
  - Does NOT infer physics from ``component_type``.
  - Does NOT add ``solve(network)`` or ``NetworkGraph.solve()``.
  - Does NOT implement Block 15B physical single-loop simulation.
  - Does NOT implement arbitrary-topology physical simulation.
- **Phase 14G still confirmed:** all six known production classes
  (``Component``, ``Pipe``, ``PumpComponent``, ``AccumulatorComponent``,
  ``EvaporatorComponent``, ``CondenserComponent``) have ``NO_CONTRIBUTE_METHOD``.
  The production-like bridge does not pretend they are executable.
- **Block 15A.3 producers** used in tests are controlled stubs (NOT real
  production components); they expose ``produce_records`` only and use
  ``ctx.view.for_component(...)`` / ``ctx.view.for_node(...)`` to read unknowns.
- **Block 15B was deferred beyond Block 15A and is now complete within its fixed-loop MVP scope.**
- **Arbitrary-topology physical simulation remains deferred.**

Block 15A.1 production component bridge boundary MVP is complete as a checkpoint.

- **`src/mpl_sim/network/production_component_bridge.py`** added — first controlled
  bridge boundary toward future production component contribution execution.
- **`ProductionBridgeExecutionContext`** — frozen context carrying the Phase 14B
  binding context plus defensively copied read-only unknown values and metadata.
  Stores no `SystemState`, creates no `FluidState`, calls no property backend.
- **`ProductionContributionBridgeProtocol`** — `typing.Protocol` with
  `runtime_checkable`; structural duck-type check for `produce_records`.
  Method is deliberately NOT named `contribute` and does NOT call
  `Component.contribute(...)`.
- **`ProductionComponentBridgeBinding` / `ProductionComponentBridgeSet`** —
  immutable, ordered, duplicate-rejecting bindings from component IDs to
  controlled bridge objects exposing a callable `produce_records` method.
- **`execute_production_bridge_contributions(...)`** — validates exact binding
  coverage (missing and extra bridge bindings rejected), invokes each bridge
  object's `produce_records(ctx)`, validates return type (`ContributionRecordSet`
  required), validates record ownership and duplicates, propagates bridge
  exceptions, and returns a `ContributionRecordSet`.
- **`build_component_contribution_from_production_bridge_execution(...)`** — thin
  wrapper through Phase 14D mapping to Phase 14C `ComponentContribution`.
- **What this does NOT do:**
  - Does NOT execute real production component classes.
  - Does NOT define or call any method named `contribute`.
  - Does NOT assemble `SystemState` or `FluidState`.
  - Does NOT call CoolProp, PropertyBackend, correlations, or any registry.
  - Does NOT attach physical state to graph nodes.
  - Does NOT infer physics from `component_type`.
  - Does NOT add `solve(network)` or `NetworkGraph.solve()`.
  - Does NOT implement Block 15B physical single-loop simulation.
- **Phase 14G still confirmed:** all six known production classes
  (`Component`, `Pipe`, `PumpComponent`, `AccumulatorComponent`,
  `EvaporatorComponent`, `CondenserComponent`) have `NO_CONTRIBUTE_METHOD`.
  The bridge boundary does not pretend they are executable.
- **Block 15A.1 bridge objects** used in tests are controlled stubs (NOT real
  production components); they expose `produce_records` only.
  Physical production-component execution remains deferred to later Block
  15A/15B work.
- **No arbitrary-topology physical simulation exists.**

Phase 14F component-like contribution provider adapter is complete as a checkpoint.

- **`src/mpl_sim/network/component_provider_adapters.py`** added — controlled
  provider objects expose `produce_records` (NOT `contribute`).
- **`ComponentProviderExecutionContext`** — frozen context carrying the Phase 14B
  binding context plus defensively copied unknown values and metadata.
- **`ComponentContributionProviderProtocol`** — `typing.Protocol` with
  `runtime_checkable`; structural duck-type check for `produce_records`.
- **`ComponentContributionProviderBinding` / `ComponentContributionProviderSet`** —
  immutable, ordered, duplicate-rejecting bindings from component IDs to
  provider objects with a callable `produce_records` method.
- **`execute_component_provider_contributions(...)`** — validates exact binding
  coverage, calls `provider.produce_records(ctx)`, validates return type
  (`ContributionRecordSet` required), validates record ownership and duplicates,
  and returns a Phase 14D `ContributionRecordSet`.
- **`build_component_contribution_from_provider_execution(...)`** — thin wrapper
  through Phase 14D mapping to Phase 14C `ComponentContribution`.
- **No production execution:** no real component classes,
  `Component.contribute(...)`, `SystemState`, `FluidState`, property or
  correlation lookup, registry resolution, or `component_type` physics.

Phase 14D component contribution contract adapter prep remains complete as a checkpoint.

- **`src/mpl_sim/network/contribution_contract.py`** added — explicit
  contribution-record and residual-name mapping contracts.
- **`ContributionRecord`** — frozen scalar value object carrying only
  `ComponentInstanceId`, contribution name, finite numeric value, and optional
  unit.
- **`ContributionRecordSet`** — ordered immutable collection; rejects wrong
  entry types and duplicate `(component_id, name)` pairs.
- **`ContributionResidualMap`** — defensively copied immutable mapping from
  `(ComponentInstanceId, contribution_name)` to residual declaration name.
- **`map_contribution_records_to_component_contribution`** — selects one
  component's explicit records, applies the explicit name map, validates
  allowed residual declarations, and returns a Phase 14C
  `ComponentContribution`.
- **No automatic physics:** no `component_type` inference, no real component
  execution, no `contribute(...)` calls, no property/correlation lookup, no
  CoolProp, no `SystemState`, no `FluidState`, no graph-state attachment.
- **Integration tested:** explicit pre-built records flow through the unchanged
  Phase 14C adapter and Phase 13G one-shot evaluation path.

Phase 14C minimal component contribution adapter foundation is complete as a checkpoint.

- **`src/mpl_sim/network/contribution_adapters.py`** added — explicit
  contribution callback adapter layer within `mpl_sim.network`.
- **`ComponentContributionContext`, `ComponentContribution`,
  `ComponentContributionAdapter`, and `ComponentContributionAdapterSet`** —
  frozen callback context/result/binding contracts with defensive copies and
  deterministic ordering.
- **`build_physical_adapters_from_contributions(...)`** — validates exact coverage
  of binding_set components (missing and extra adapters rejected); generates one
  `PhysicalResidualAdapter` per assembly residual in assembly declaration order;
  generated callbacks call all contribution callbacks at evaluation time, validate
  residual name coverage against assembly declarations, and raise clearly on
  missing/undeclared/wrong-type contributions.
- **Integration tested:** Phase 13G one-shot evaluation and Phase 13H Newton
  solve both verified on toy solvable contribution problems.

Phase 14B component binding and state-vector mapping foundation is complete as a checkpoint.

- **`src/mpl_sim/network/component_binding.py`** added — binding and mapping
  declaration layer within `mpl_sim.network`.
- **`ComponentBinding`** — frozen `(instance_id, binding_name)` declaration
  linking a `ComponentInstanceId` to a caller-supplied label; optional
  opaque `metadata` defensively copied as `MappingProxyType`.
- **`ComponentBindingSet`** — ordered immutable collection of
  `ComponentBinding`; rejects wrong entry types and duplicate instance IDs;
  preserves insertion order; provides `instance_ids()` and `by_instance_id()`.
- **`ComponentStateMap`** — explicit mapping from unknown/residual string keys
  to `ComponentInstanceId` or `GraphNodeId` values; all four mapping fields
  stored as immutable `MappingProxyType`; rejects empty/whitespace keys and
  wrong value types; stores no numerical values.
- **`NetworkBindingContext`** — frozen context combining `NetworkGraph`,
  `NetworkResidualAssembly`, `ComponentBindingSet`, `ComponentStateMap`, and
  optional metadata; does not execute anything.
- **`build_binding_context(...)`** — validates exact binding coverage of graph
  component instances (missing/extra rejected); validates mapped names against
  assembly declarations; validates all state-map ID references against the
  graph (unknown component or node IDs rejected); returns an immutable
  `NetworkBindingContext`.
- **No automatic physics:** no `component_type` inference, no component
  execution, no `contribute(...)`, no property/correlation lookup, no CoolProp,
  no graph-state attachment, no numerical solver state.

Phase 14A physical residual adapter foundation is complete as a checkpoint.

- **`src/mpl_sim/network/physical_adapters.py`** added — explicit adapter-only
  bridge from caller callbacks to Phase 13G `NetworkResidualEvaluator`.
- **`PhysicalResidualContext`** — frozen context with defensively copied,
  read-only unknown values and optional metadata.
- **`PhysicalResidualAdapter`** — frozen residual-name/callback binding.
- **`PhysicalResidualAdapterSet`** — ordered immutable collection with entry
  type and duplicate-name validation.
- **`build_network_residual_evaluators(...)`** — validates exact residual-name
  coverage and returns evaluators in assembly declaration order.
- **No automatic physics:** no `component_type` inference, component execution,
  `contribute(...)`, property/correlation lookup, CoolProp, or graph-state
  attachment.

Phase 13H configurable network solver v1 is complete as a checkpoint.

- **`src/mpl_sim/network/solver.py`** added — configurable algebraic residual solver within `mpl_sim.network`.
- **`NetworkSolveConfig`** — frozen dataclass: `max_iterations: int`, `tolerance: float`, `finite_difference_step: float`, `damping: float = 1.0`, `record_history: bool = False`. Strict validation: bool rejected on all numeric fields; `max_iterations >= 1`; all floats finite and > 0; `damping <= 1.0`; `record_history` must be bool.
- **`NetworkSolveResult`** — frozen dataclass: `converged: bool`, `iteration_count: int`, `reason: str`, `final_unknown_values: NetworkUnknownValues`, `final_evaluation: NetworkResidualEvaluationResult`, `initial_evaluation: NetworkResidualEvaluationResult`, `residual_norm_history: tuple[float, ...] | None`.
- **`solve_network_residual_problem(assembly, initial_values, evaluators, scales, config) -> NetworkSolveResult`** — damped forward finite-difference Newton solver. Accepts `NetworkUnknownValues` or a plain `Mapping` as initial values. Delegates all residual evaluation to Phase 13G `evaluate_network_residuals`. Requires square system (`n_unknowns == n_residuals`); returns non-converged result immediately if mismatched. Checks initial convergence before first iteration (returns `iteration_count=0` if already converged). Each iteration: builds n×n FD Jacobian (n perturbed evaluations), solves `J dx = -r` via Gaussian elimination with partial pivoting (`_SINGULAR_THRESHOLD = 1e-14`), applies damped update `x_new = x + damping * dx`, checks finite values, evaluates new residuals, checks convergence. Singularity returns non-converged. Callback exceptions propagate unchanged. When `record_history=True`, `max_abs_scaled` is appended after each iteration.
- **`mpl_sim.network.__init__.py`** updated — three Phase 13H symbols added to `__all__`; Phase 7, 13E, 13F, 13G exports unchanged.
- **`tests/network/test_configurable_solver_v1.py`** added — 113 focused tests covering all 30 required coverage items; AST-based boundary checks confirm no scipy/fsolve/root/least_squares imports and no `contribute(` call in solver source.
- **`docs/user_guide/CONCEPTS.md`** updated — "Configurable Network Solver v1 (Phase 13H)" section added with code example, solver method description, and "What this is NOT" list; "What is NOT implemented" table updated.
- **Architecture boundary:** `solver.py` imports only `math`, `collections.abc.Mapping`, `dataclasses`, `mpl_sim.network.residual_assembly`, `mpl_sim.network.residual_evaluation`. No scipy, numpy root-finders, CoolProp, PropertyBackend, CorrelationRegistry, component modules. No `contribute(` call. No `def solve(self` method.
- **No physics added:** no FluidState, fluid properties, component execution, or physical residual construction. All residuals are explicitly caller-supplied callbacks.
- **Phase 13A through 13G and all prior tests unchanged.** 4489 tests pass with no skips, xfails, deselections, or fixture errors.

Phase 13F network residual assembly foundation is complete as a checkpoint.

- **`src/mpl_sim/network/residual_assembly.py`** added — declaration-only assembly module within `mpl_sim.network`.
- **`NetworkUnknownDeclaration`** — frozen dataclass declaring one scalar unknown (name + unit only; no value, no bounds, no initial guess).
- **`NetworkResidualDeclaration`** — frozen dataclass declaring one residual equation (name + unit only; no value, no scale, no evaluation).
- **`NetworkUnknownSet`** — immutable ordered collection of `NetworkUnknownDeclaration`; duplicate names rejected; provides `names()` and `count()`.
- **`NetworkResidualSet`** — immutable ordered collection of `NetworkResidualDeclaration`; duplicate names rejected; provides `names()` and `count()`.
- **`NetworkResidualAssembly`** — immutable result of assembly; holds `NetworkUnknownSet` and `NetworkResidualSet`; `summary()` returns counts/names with no physical values; no `solve()` method.
- **`assemble_network_residuals(graph, *, require_closed_loop, include_pressure_unknowns, include_pressure_residuals)`** — factory function mapping `NetworkGraph` → `NetworkResidualAssembly`. Declares: one mass-flow unknown per component instance (`"mdot:<id>"`, kg/s); one pressure unknown per node (`"P:<id>"`, Pa, optional default enabled); one mass-balance residual per node (`"mass_balance:<id>"`, kg/s); one pressure-compatibility residual per component instance (`"pressure_drop:<id>"`, Pa, optional default enabled). Assembly order follows graph insertion order (deterministic). Validates input type, non-empty graph, and optionally closed-loop structure.
- **`mpl_sim.network.__init__.py`** updated — six Phase 13F symbols added to `__all__`; Phase 7 and 13E exports unchanged.
- **`tests/network/test_residual_assembly_foundation.py`** added — 122 focused tests covering all 24 required coverage items: declaration types, collection types, units, deterministic ordering, summary content, empty-graph rejection, non-graph rejection, strict Boolean option validation, closed-loop mode, no-solve boundary, no-value boundary, no-component-execution boundary, no-property-lookup boundary, public exports, and docs honest-claims check.
- **`docs/user_guide/CONCEPTS.md`** updated — "Network Residual Assembly Foundation (Phase 13F)" section added; "What is NOT implemented" table updated.
- **`docs/roadmap/PROJECT_STATUS.md`** updated — Phase 13F status, milestone, history.
- **Architecture boundary:** `residual_assembly.py` imports only stdlib (`__future__`, `dataclasses`) and `mpl_sim.network.graph`. MUST NOT and does NOT import `mpl_sim.closed_loop`, `mpl_sim.components`, `mpl_sim.solvers`, `mpl_sim.properties`, `mpl_sim.correlations`, `mpl_sim.calibration`, `mpl_sim.hx_models`, or CoolProp.
- **No physics added:** no FluidState, mdot values, pressure values, enthalpy values, quality, HTC, ΔP, property lookup, or solver in the assembly module.
- **No solve() method:** `NetworkResidualAssembly` has no `solve()`, `evaluate()`, or convergence method.
- **No residual evaluation:** declarations carry only name and unit; no numerical values computed or stored.
- **Phase 13E and all prior tests unchanged.** All existing tests continue to pass.

Phase 13E network graph foundation is complete as a checkpoint.

- **`src/mpl_sim/network/graph.py`** added — new module within the existing `mpl_sim.network` package; five public types: `GraphNodeId`, `ComponentInstanceId`, `GraphNode`, `ComponentInstance`, `NetworkGraph`.
- **`GraphNodeId`** — frozen dataclass wrapping a non-empty string; identifies a named fluid connection point (not a component).
- **`ComponentInstanceId`** — frozen dataclass wrapping a non-empty string; identifies a named component instance in the graph.
- **`GraphNode`** — frozen dataclass holding one `GraphNodeId`; represents a fluid topology junction with no physical values.
- **`ComponentInstance`** — frozen dataclass with `instance_id`, `component_type` (string), `inlet_node`, `outlet_node`; rejects empty `component_type` and self-loops (`inlet_node == outlet_node`).
- **`NetworkGraph`** — immutable class holding nodes and component instances in insertion order; validates: no duplicate node IDs, no duplicate instance IDs, all component node references exist in graph. Optional `validate_closed_single_loop()` checks single-loop structure without physics.
- **`mpl_sim.network.__init__.py`** updated — five Phase 13E types added to `__all__`; Phase 7 exports (NetworkTopology, NetworkNode, etc.) unchanged.
- **`tests/network/test_graph_foundation.py`** added — 115 focused tests covering all 22 required coverage items: strict ID/type validation, graph construction, deterministic ordering, duplicate rejection, unknown node rejection, self-loop rejection, summary content, architecture boundaries (no CoolProp, no solvers, no closed_loop imports), public exports, and docs honest-claims checks.
- **`docs/user_guide/CONCEPTS.md`** updated — "Network Graph Foundation (Phase 13E)" section added; "What is NOT implemented" table updated.
- **`README.md` and `docs/user_guide/QUICKSTART.md`** were updated at the Phase 13E checkpoint to list topology representation as implemented while residual assembly and configurable solving were still deferred; Phase 13F documentation above supersedes that historical capability statement.
- **`docs/roadmap/PROJECT_STATUS.md`** updated — Phase 13E status, milestone, history.
- **Architecture boundary:** `graph.py` imports only stdlib (`__future__`, `collections.abc`, `dataclasses`); does NOT import `mpl_sim.closed_loop`, `mpl_sim.components`, `mpl_sim.solvers`, `mpl_sim.properties`, `mpl_sim.correlations`, `mpl_sim.calibration`, `mpl_sim.hx_models`, or CoolProp.
- **No physics added:** no FluidState, mdot, pressure, enthalpy, quality, HTC, ΔP, property lookup, or solver in the graph module.
- **No solve() method:** `NetworkGraph` has no `solve()`, `assemble_residuals()`, or convergence method.
- **Phase 13D and all prior tests unchanged.** 4159 total tests pass (4044 pre-Phase 13E + 115 new).

Phase 13D coupled fixed-architecture energy+pressure closure is complete as a checkpoint.

- **`src/mpl_sim/closed_loop/coupled_solver.py`** added — fixed one-evaporator + one-condenser coupled closure using nested bounded scalar bisection.
- **Unknowns:** `Q_cond` and `primary_mdot`; **residuals:** `h_return - h_reference` and `pump_head(mdot) - dP_total(mdot)`.
- **`ResidualVector`** is returned with explicit energy and pressure scales plus scaled convergence diagnostics.
- **`tests/closed_loop/test_minimal_coupled_closure.py`** contains 112 focused tests, including analytical roots, endpoint handling, explicit non-convergence, strict configuration/case validation, architecture boundaries, public imports, and Phase 13A/13B regressions.
- **No generic network API, arbitrary topology, new physics, property lookup, registry resolution, validation harness, or additional component family was introduced.**

Phase 13C residual/unknown/scaling framework foundation remains complete as a checkpoint.

- **`src/mpl_sim/closed_loop/residuals.py`** added — Phase 13C public module; four frozen dataclasses: `UnknownSpec`, `ResidualSpec`, `ResidualEvaluation`, `ResidualVector`.
- **`UnknownSpec`** — declares a scalar unknown with `name`, `unit`, and optional `lower`/`upper` bounds. All fields strictly validated; bool rejected as bound.
- **`ResidualSpec`** — declares a residual with `name`, `unit`, and characteristic `scale` (finite, > 0, non-bool). Scale non-dimensionalises the raw residual.
- **`ResidualEvaluation`** — pairs a `ResidualSpec` with a raw `value` (finite, non-bool). Exposes `scaled_value = value / spec.scale` as a property.
- **`ResidualVector`** — ordered, non-empty collection of `ResidualEvaluation` objects with unique `spec.name`; accepts list or tuple input (auto-converts to tuple). Methods: `scaled_values()`, `max_abs_scaled()` (L-infinity), `l2_scaled()` (Euclidean), `is_converged(tolerance)` (validates tolerance strictly).
- **`mpl_sim.closed_loop.__init__.py`** updated: 13 total public exports (4 Phase 13A + 5 Phase 13B + 4 Phase 13C).
- **`tests/closed_loop/test_residual_framework.py`** — 117 focused tests covering all 22 required coverage items including strict spec/vector-entry type validation, energy and pressure residual representation examples, combined residual vectors, no-network/no-solver boundary checks, public exports, and Phase 13A/13B regression.
- **`docs/user_guide/CONCEPTS.md`** updated: added "Residual / Unknown / Scaling Framework" section; updated "What is NOT implemented" table.
- **Phase 13A/13B solvers unchanged.** All existing tests continue to pass. No new physics, no property lookup, no network topology.
- **Does NOT implement:** `solve(network)`, simultaneous multi-variable solving, coupled energy+pressure closure (deferred to Phase 13D), network graph (deferred), or any topology classes.

Phase 13B minimal pressure closure solver is complete as a checkpoint.

- **`src/mpl_sim/closed_loop/_scalar_solve.py`** added — private bounded bisection utility shared by Phase 13A and 13B solvers. Not part of the public API.
- **`src/mpl_sim/closed_loop/minimal_solver.py`** refactored to use `_bisect_bounded`; behaviour is identical; all 85 Phase 13A tests continue to pass.
- **`src/mpl_sim/closed_loop/pressure_solver.py`** added — Phase 13B core; `solve_minimal_pressure_closure` finds `primary_mdot` such that `pump_head(mdot) = dP_evap(mdot) + dP_cond(mdot)` using bounded bisection over a caller-supplied bracket.
- **`PumpHeadCurve`** — explicit pump-head law: constant or linear `ΔP_pump(mdot) = head_Pa - slope_Pa_s_kg * mdot`. Validated; frozen dataclass.
- **`PressureClosureConfig`** — solver config with same validation rules as `ClosedLoopSolveConfig`.
- **`MinimalPressureClosureCase`** — fixed architecture case; requires `mdot_bounds`, explicit positive evaporator/condenser flow areas, and an injected `dp_primary` closure for each HX scenario.
- **`MinimalPressureClosureResult`** — full result: `converged`, `iterations`, `evaluations`, `pressure_residual`, `solved_primary_mdot`, `pump_head`, `dP_evap`, `dP_cond`, `dP_total`, component results, states, `energy_residual` (diagnostic only), `warnings`.
- **`mpl_sim.closed_loop.__init__.py`** updated: nine total public exports (four Phase 13A + five Phase 13B).
- **`tests/closed_loop/test_minimal_pressure_closure.py`** contains focused tests covering all 15 required coverage items plus PumpHeadCurve unit tests and Phase 13A regression.
- **`examples/minimal_pressure_closure.py`** is standalone, import-safe, public-API-only, property-lookup-free, and explicit that energy closure, combined pressure+energy closure, arbitrary topology, validation, and additional components remain deferred.
- **Formulation (Option A):** pressure-only closure; energy_residual = h_return - h_reference is reported but not solved. Combined closure is deferred to Phase 13D.

Phase 13A minimal closed MPL solver is complete as a checkpoint.

- **`src/mpl_sim/closed_loop/`** added with a proper `__init__.py`, four intentional public exports, and no accidental `init.py`.
- **`solve_minimal_closed_mpl`** evaluates the evaporator once, varies only the condenser `FixedHeatRate.Q`, and solves `h_return - h_reference = 0` using bounded bisection over a caller-supplied bracket.
- **`MinimalClosedMPLResult`** reports convergence, iterations, residual, solved condenser heat rate, component results, states, `net_Q`, `net_dh`, `dP_total`, and warnings.
- **`tests/closed_loop/test_minimal_closed_mpl_solver.py`** contains 85 focused tests, including exact endpoint-root handling and direct observation that the evaporator outlet object feeds every condenser evaluation.
- **`examples/minimal_closed_mpl_solver.py`** is standalone, import-safe, public-API-only, property-lookup-free, and explicit that pressure closure, arbitrary topology, validation, and additional components remain deferred.
- **Validation:** 3722 full-suite tests passed with no deselection; focused correlation/HX/component/loop/example/closed-loop suites passed; all four examples ran; Ruff and Black checks passed.

Phase 12B examples and user documentation quickstart is complete as a checkpoint.

- **`examples/fixed_heat_rate_hx.py`** added — standalone ε-NTU FixedHeatRate evaporator example. Explicit `FluidState`, `MicrochannelGeometry`, `EvaporatorScenarioBinding`. No correlations required for this BC; prints Q, h_out, dP. Deterministic: h_out = h_in + Q/mdot.
- **`examples/segmented_counterflow_hx.py`** added — `SegmentedMarchModel` + `SinkInletTempAndFlow` + `FlowArrangement.COUNTERFLOW` + `CounterflowIterationConfig(enabled=True)`. Injects `DittusBoelterHTC` (primary + secondary) and `ChurchillFrictionGradient`. Prints Q, h_out, dP, converged, residual, iteration_count. All IN_ENVELOPE for Re=15000.
- **`examples/README.md`** updated — covers all three examples with run commands and "what it is NOT" section.
- **`tests/examples/test_examples.py`** added — 34 smoke tests covering: file and documentation references, importability without solve-on-import behavior, standalone run (exit code 0), AST-verified public API imports, expected diagnostics, runtime no-file-write checks, no external imports, and honest claims.
- **`src/mpl_sim/hx_models/__init__.py`** updated — exports `PrimaryThermalMode` and `UAComputationMode` (previously not exported; required for `SinkInletTempAndFlow` scenarios through component wrappers).
- **`README.md`** rewritten — reflects current library state: what it does, what it does not, quick start, simplest example, doc index, architecture philosophy.
- **`docs/user_guide/QUICKSTART.md`** added — answers the 10 required user questions: what is it, what can it do, what can it not do, how to run tests, how to run examples, simplest example, core concepts, how the layers relate, architecture boundaries, recommended next steps.
- **`docs/user_guide/CONCEPTS.md`** added — explains FluidState, secondary BCs, HX model strategies, correlations, components, geom_scalars, the segmented counterflow path, and deferred capabilities.
- **`docs/user_guide/EXAMPLES.md`** added — annotated walkthrough of all three examples with representative output, when-to-use guidance, and common patterns.
- **Architecture boundaries**: no new CoolProp, PropertyBackend, CorrelationRegistry, network, or solver imports in examples/. `PrimaryThermalMode` and `UAComputationMode` export addition is a public API gap fix, not a new architecture concept.
- **NOT implemented** (all deferred): full network solver; loop convergence iteration; moving-boundary model; validation harness; valves/manifolds; new HTC/DP closures; automatic phase inference; hidden property defaults; plotting.

Phase 12A minimal loop assembly acceptance case is complete as a checkpoint.

- **`examples/minimal_evaporator_condenser_loop.py`** added — standalone runnable example and importable module:
  - **`MinimalLoopResult`** frozen dataclass: `evap_result`, `cond_result`, `h_initial`, `h_after_evap`, `h_after_cond`, `Q_evap`, `Q_cond`, `net_Q`, `net_dh`, `dP_evap`, `dP_cond`, `dP_total`, `warnings`.
  - **`evaluate_minimal_evaporator_condenser_loop(inlet_state, primary_mdot, evap_component, evap_scenario, cond_component, cond_scenario)`** — one explicit forward pass: (1) evaluate evaporator; (2) feed evap outlet to condenser inlet; (3) assemble diagnostics. No loop convergence. No hidden global state.
  - Validates `primary_mdot` is finite and > 0; raises `ValueError` with field name in message otherwise.
  - `net_Q` and `net_dh` are always reported, never suppressed — caller sees the energy imbalance.
  - `warnings` collects non-`IN_ENVELOPE` correlation verdicts from both components.
  - `__main__` block uses explicit `R134a` fluid identity, explicit geometry (MicrochannelGeometry + PlateGeometry), explicit `FixedHeatRate` BCs, and explicit `EpsilonNTUModel` + `DiscretizationMode.LUMPED`. No CoolProp call occurs.
- **`examples/__init__.py`** added — makes `examples/` a Python package importable in tests.
- **`tests/loops/test_minimal_loop_example.py`** added — 33 acceptance tests covering all 12 required items:
  1. Minimal loop runs end-to-end.
  2. Evaporator outlet feeds condenser inlet.
  3. Heat signs correct (Q_evap > 0, Q_cond < 0).
  4. Enthalpy changes consistent with Q/mdot.
  5. Pressure drops accumulate exactly.
  6. Net loop imbalance reported (not hidden).
  7. Explicit closures required/injected.
  8. Missing required inputs fail clearly.
  9. No property lookup (nonexistent fluid name completes without error).
  10. Public example imports work (smoke test via `subprocess`).
  11. Existing Phase 11 HX tests remain passing (suite-level gate: 3591 total).
  12. Example executes as standalone smoke test with exit code 0.
- The example and focused tests import framework symbols through public package APIs.
- **`pyproject.toml`** adds pytest `pythonpath = ["."]` so the importable
  `examples` package is available during collection without runtime path mutation.
- **Architecture boundaries**: no CoolProp, no PropertyBackend, no CorrelationRegistry, no network, no solvers in `examples/` or `tests/loops/`. Verified by grep.
- **NOT implemented** (all deferred): full network solver; loop convergence iteration; moving-boundary model; validation harness; valves/manifolds; new HTC/DP closures; automatic phase inference; hidden property defaults.
- **Test arithmetic** (deterministic, no property lookup): Q_evap=1000 W, Q_cond=-800 W, mdot=0.05 kg/s → h_after_evap=270 000 J/kg, h_after_cond=254 000 J/kg, net_dh=+4 000 J/kg, net_Q=+200 W.

Phase 11T iterated counterflow segmented solver is complete as a checkpoint.

- **`CounterflowIterationConfig`** frozen dataclass added to `src/mpl_sim/hx_models/base.py`:
  - Fields: `enabled: bool = False`, `max_iter: int = 20`, `tolerance: float = 1e-6`, `relaxation: float = 1.0`.
  - `__post_init__` validates: `max_iter` is a non-boolean `int >= 1`, `tolerance` is finite and `> 0`, and `relaxation` is finite and in `(0, 1]`. Invalid values raise `ValueError` with the field name in the message.
  - Exported from `mpl_sim.hx_models` and listed in `__all__`.
- **`HXSolveRequest.counterflow_iteration: CounterflowIterationConfig | None = None`** added.
  - Default `None` preserves all existing behavior (one-pass and co-current paths unchanged).
  - Early validation in `__post_init__`: if `enabled=True`, requires `SinkInletTempAndFlow` secondary BC and `FlowArrangement.COUNTERFLOW`; any other combination raises `ValueError`.
- **`HXSolveResult`** extended with three new fields (defaulting to non-iterated values):
  - `iteration_count: int = 0` — number of iterations performed.
  - `converged: bool | None = None` — `True` if residual ≤ tolerance, `False` if max_iter reached without convergence, `None` for non-iterated paths.
  - `residual: float | None = None` — final max-absolute-difference residual across the secondary profile; `None` for non-iterated paths.
- **`SegmentedMarchModel._solve_sink_inlet_counterflow_iterated`** added:
  - Accepts `req`, `bc` (`SinkInletTempAndFlow`), and `cfg` (`CounterflowIterationConfig`).
  - Validates same prerequisites as one-pass: `FINITE_CAPACITY`, explicit `primary_T_in`/`primary_cp`, `TWO_SIDED`, positive `A_ht`, both HTC correlations.
  - Initializes secondary temperature profile as `[bc.T_in] * n_cells`.
  - Each iteration: (1) forward primary march over all cells using current `T_s_profile`; (2) backward secondary integration from cell `n-1` (inlet) to cell `0`; (3) residual = max absolute difference between new and previous secondary profile; (4) under-relaxation update of `T_s_profile`.
  - Per-cell heat transfer uses the co-current ε-NTU formula (same as one-pass), consistent with the segmented approximation.
  - Loop exits early when `residual <= cfg.tolerance` (`converged = True`); otherwise runs to `cfg.max_iter` and returns `converged = False`. Non-convergence never raises; caller inspects result fields.
  - `SegmentedCellRecord` in the iterated path includes `htc_secondary` (unlike the one-pass path).
  - Returns `HXSolveResult(..., iteration_count=..., converged=..., residual=...)`.
- **Dispatch updated in `SegmentedMarchModel.solve()`**:
  - `COUNTERFLOW` + `cfg.enabled=True` → `_solve_sink_inlet_counterflow_iterated`.
  - `COUNTERFLOW` + `cfg is None` or `cfg.enabled=False` → `_solve_sink_inlet_counterflow_onepass` (unchanged).
  - `None` / `CO_CURRENT` → `_solve_sink_inlet_cocurrent` (unchanged).
- **Deferred** (unchanged from Phase 11S):
  - Moving-boundary modeling.
  - Full-loop convergence acceptance.
  - Per-cell `cell_geom_scalars` mechanism.
  - Remaining two-phase HTC and DP closures.
  - `primary_T_sat` / `primary_h_fg` on `HXSolveRequest`.
  - Validation harnesses and valves/manifolds.
- `CounterflowIterationConfig.max_iter` validation is strict: requires a plain `int` (bool and float explicitly rejected via `isinstance`), and `>= 1`. `bool` subclasses `int` so both `True` and `False` are caught before the `< 1` check. `float("nan")`, `float("inf")`, and `1.5` are also rejected.
- New test file `tests/hx_models/test_segmented_counterflow_iteration.py` with **92 tests** covering all 19 required Phase 11T coverage items plus real-closure regression tests:
  - Controlled algorithmic tests use `_ConstHTC` / `_ConstDP` / `_ConstTwoPhaseDP` for precise arithmetic verification (gradient-to-drop, profile consistency, relaxation effects).
  - Real-closure regression tests (`TestRealCorrelationIteratedMode`) exercise `ShahBoilingHTC` (with explicit `q_flux_primary`), `YanCondensationHTC` (no q-flux required), and `MSHTwoPhaseFrictionGradient` (with `dp_primary_is_two_phase=True`) end-to-end through the iterated solver, including missing-scalar failure modes and energy-balance checks.

Phase 11S segmented counterflow / phase-change coupling foundation is complete as a checkpoint.

- **`FlowArrangement`** enum added to `src/mpl_sim/hx_models/base.py` with members `CO_CURRENT` and `COUNTERFLOW`. Exported from `mpl_sim.hx_models`.
- **`HXSolveRequest.flow_arrangement: FlowArrangement | None = None`** added. Default `None` preserves all existing behavior across every path and every HX model. Other models (`EpsilonNTUModel`, `LMTDModel`) silently ignore the field.
- **`SegmentedProfile.flow_arrangement: FlowArrangement | None = None`** added. Records the arrangement actually used. Single-stream paths (`FixedHeatRate`, `FixedWallTemp`, `AmbientCoupling`) record `None`; `SinkInletTempAndFlow` co-current records `CO_CURRENT`; counterflow records `COUNTERFLOW`.
- **`SegmentedMarchModel` dispatch updated**: `SinkInletTempAndFlow` now checks `req.flow_arrangement`:
  - `None` or `CO_CURRENT` → `_solve_sink_inlet_cocurrent` (existing behavior, unchanged).
  - `COUNTERFLOW` → `_solve_sink_inlet_counterflow_onepass` (new one-pass foundation).
  - Any other value → `ValueError` with clear message.
- **`_solve_sink_inlet_counterflow_onepass`** added — one-pass counterflow approximation:
  - Primary inlet at cell 0; secondary inlet at cell n-1 (opposite end from primary).
  - Forward primary march: Q_cell in each cell is computed using `bc.T_in` (the counterflow secondary inlet) as a **fixed estimate** for the secondary temperature in all cells. This is the one-pass approximation.
  - After the primary march: secondary temperature profile is derived by backward integration from cell n-1 to cell 0 and stored in `SegmentedCellRecord.secondary_T_in` / `secondary_T_out` as diagnostics. These values do **not** feed back into Q_cell.
  - **LIMITATION**: Not a converged counterflow solution. A fully coupled nonlinear counterflow solve requires iteration between primary and secondary profiles; that iteration is deferred.
  - Same validations as co-current: `FINITE_CAPACITY`, explicit `primary_T_in`, explicit `primary_cp`, `TWO_SIDED` UA mode, `htc_primary`, `htc_secondary`, positive `A_ht`.
- **Phase-change primary scalar-passing** (Phase 11S):
  - `x`, `h_fg`, `rho_l`, `rho_v`, `mu_l`, `mu_v` continue to be passed via `geom_scalars` — the existing mechanism — to `HTCInput` and `TwoPhaseDPInput`. No new `primary_T_sat` or `primary_h_fg` fields were added to `HXSolveRequest` because existing correlations (`ShahBoilingHTC`, `YanCondensationHTC`, `MSHTwoPhaseFrictionGradient`) do not require them at the request level.
  - `dp_primary_is_two_phase=True` + `TwoPhaseDPInput` property-scalars mechanism remains fully operative in counterflow path.
  - `q_flux_primary` passes to primary HTC (not secondary) in counterflow — same as co-current.
- **Deferred** (unchanged from Phase 11R):
  - Fully coupled (iterated) counterflow nonlinear solve.
  - Per-cell `cell_geom_scalars` mechanism (not needed by current tests).
  - `primary_T_sat` / `primary_h_fg` on `HXSolveRequest` (not needed by existing correlations).
  - Moving-boundary modeling.
  - Full-loop convergence acceptance.
  - Remaining two-phase HTC and DP closures.
  - Validation harnesses and valves/manifolds.
- New test file `tests/hx_models/test_segmented_counterflow_phase_change_foundation.py` with **76 tests** covering all 15 required Phase 11S coverage items, including direct real-correlation Shah and Yan counterflow checks added during audit closeout.

Phase 11R component contribution-path scenario binding is complete as a checkpoint.

- **`EvaporatorScenarioBinding`** added in `src/mpl_sim/components/evaporator.py`. Immutable frozen dataclass holding all scenario-specific configuration (everything in `EvaporatorHXInput` except runtime `primary_state_in` and `primary_mdot`), including `q_flux_primary` and `dp_primary_is_two_phase` from Phase 11Q. `geom_scalars` stored as `MappingProxyType(dict(...))` in `__post_init__` so neither `binding.geom_scalars[key] = val` nor post-construction mutation of the source dict can affect the binding.
- **`CondenserScenarioBinding`** added in `src/mpl_sim/components/condenser.py`. Mirrors `EvaporatorScenarioBinding` for the condenser; same `MappingProxyType` immutability guarantee.
- **`EvaporatorComponent.evaluate_scenario(primary_state_in, primary_mdot, scenario)`** added: scenario-bound helper that builds `EvaporatorHXInput` from runtime state + immutable scenario binding and delegates to `evaluate_heat_exchanger`. No registry access, no closure selection, no property lookup. NOT the frozen `contribute(trial, ctx) -> ComponentContribution` contract from INTERFACE_SPEC §11.1, which remains deferred.
- **`CondenserComponent.evaluate_scenario(primary_state_in, primary_mdot, scenario)`** added: same pattern for condenser.
- Both new types exported from `mpl_sim.components` and listed in `__all__`.
- **Evaporator scenarios now reachable through `evaluate_scenario()`**:
  - Shah boiling HTC + `q_flux_primary` + two-phase DP: set `EvaporatorScenarioBinding(htc_primary=ShahBoilingHTC(), q_flux_primary=..., dp_primary=MSHTwoPhaseFrictionGradient(), dp_primary_is_two_phase=True, ...)`.
  - Missing `q_flux_primary` for Shah fails clearly via `HXSolveRequest` validation.
  - Missing two-phase DP property scalar fails clearly via builder validation.
- **Condenser scenarios now reachable through `evaluate_scenario()`**:
  - Yan condensation HTC + two-phase DP: set `CondenserScenarioBinding(htc_primary=YanCondensationHTC(), dp_primary=MSHTwoPhaseFrictionGradient(), dp_primary_is_two_phase=True, ...)`.
  - `YanCondensationHTC` does not require `q_flux_primary`; field defaults to `None`.
- `evaluate_scenario()` produces identical results to `evaluate_heat_exchanger()` for the same inputs (verified by cross-reference tests).
- **No hidden defaults, no automatic closure selection, no registry resolution inside components.** All scenarios explicitly configured by caller through `*ScenarioBinding`.
- **Deferred** (unchanged): frozen `contribute(trial, ctx) -> ComponentContribution` contract from INTERFACE_SPEC §11.1 (requires `ComponentTrialState` and `EvalContext`, not yet implemented); broader counterflow and phase-change segmented coupling; moving boundary; full-loop convergence acceptance; additional two-phase DP and HTC closures; validation harnesses; valves/manifolds after Phase 11.
- New test file `tests/components/test_evaporator_condenser_contribution_scenario_binding.py` covering all 13 required items plus `MappingProxyType` immutability tests (geom_scalars read-only, source-dict isolation, frozen field assignment rejection).

Phase 11Q evaporator/condenser scenario plumbing foundation is complete as a checkpoint.

- **`EvaporatorHXInput.q_flux_primary: float | None = None`** and **`EvaporatorHXInput.dp_primary_is_two_phase: bool = False`** added in `src/mpl_sim/components/evaporator.py`. Both are forwarded explicitly in `evaluate_heat_exchanger` to `HXSolveRequest`.
- **`CondenserHXInput.q_flux_primary: float | None = None`** and **`CondenserHXInput.dp_primary_is_two_phase: bool = False`** added in `src/mpl_sim/components/condenser.py`. Both are forwarded explicitly in `evaluate_heat_exchanger` to `HXSolveRequest`.
- **Evaporator explicit scenarios now covered**:
  - Single-phase HTC + single-phase DP: caller injects any HTC correlation (e.g. `GnielinskiHTC`) and any single-phase DP correlation with `dp_primary_is_two_phase=False` (default).
  - Boiling HTC + q_flux + two-phase DP: caller injects `ShahBoilingHTC` as `htc_primary`, supplies `q_flux_primary`, and sets `dp_primary_is_two_phase=True` with `MSHTwoPhaseFrictionGradient` as `dp_primary`.
  - Missing `q_flux_primary` when using `ShahBoilingHTC` fails clearly via `HXSolveRequest` validation.
  - Missing two-phase DP property scalar fails clearly via `HXSolveRequest` builder validation.
- **Condenser explicit scenarios now covered**:
  - Condensation HTC + two-phase DP: caller injects `YanCondensationHTC` as `htc_primary` and sets `dp_primary_is_two_phase=True` with `MSHTwoPhaseFrictionGradient` as `dp_primary`.
  - `YanCondensationHTC` does not require `q_flux_primary`; the field defaults to `None`.
- **No hidden defaults, no automatic closure selection, no registry resolution inside components.** All scenarios are explicitly configured by the caller.
- **Deferred** (unchanged): counterflow and broader phase-change segmented coupling; moving boundary; full-loop convergence acceptance; additional two-phase DP and HTC closures; validation harnesses; valves/manifolds after Phase 11.
- New test file `tests/components/test_evaporator_condenser_scenario_plumbing.py` with 51 tests covering all 13 required scenario items: forwarding, integration, failure modes, unchanged geometry-scalar forwarding, and architecture boundary searches.

Phase 11P two-phase DP HX builder and gradient-to-drop plumbing is complete as a checkpoint.

- **`HXSolveRequest.dp_primary_is_two_phase: bool = False`** added in `src/mpl_sim/hx_models/base.py`. When `True` the active HX model builds `TwoPhaseDPInput` instead of `SinglePhaseDPInput` and multiplies the Pa/m gradient output by `L_cell` to produce a Pa pressure drop. When `False` (default) the existing single-phase DP behaviour is unchanged.
- **Two-phase DP builders added to all three HX models**:
  - `EpsilonNTUModel._build_two_phase_dp_input(req)` in `src/mpl_sim/hx_models/epsilon_ntu.py`
  - `LMTDModel._build_two_phase_dp_input(req)` in `src/mpl_sim/hx_models/lmtd.py`
  - `SegmentedMarchModel._build_two_phase_dp_input_for_cell(req, cell_state)` in `src/mpl_sim/hx_models/segmented.py`
- **Gradient-to-drop conversion**: `raw_dP_Pa = raw_dp_out.value[0] * dp_inp.L_cell`. The raw Pa value (pre-calibration) is stored in `HXSolveResult.raw_dP_primary`. `friction_multiplier` is applied after conversion, producing `dP_primary` [Pa].
- **Required geom_scalars for two-phase path**: `G`, `x`, `D_h`, `L_cell`, `rho_l`, `rho_v`, `mu_l`, `mu_v`. The four fluid-property scalars are forwarded into `TwoPhaseDPInput.property_scalars` (Decision 011). Missing or non-positive values raise `ValueError` with the key name in the message.
- **Supported in EpsilonNTU**: all four BC paths (FixedHeatRate, SinkInletTempAndFlow, FixedWallTemp, AmbientCoupling).
- **Supported in LMTD**: both BC paths (FixedWallTemp, AmbientCoupling).
- **Supported in Segmented**: all four BC paths (FixedHeatRate, FixedWallTemp, AmbientCoupling, SinkInletTempAndFlow); per-cell conversion uses `L_cell` from geom_scalars for each cell call.
- **No auto-detection by correlation class**; no registry resolution; no CoolProp; no PropertyBackend; no hidden defaults.
- New test file `tests/hx_models/test_hx_two_phase_dp_plumbing.py` with 122 tests covering: single-phase path unchanged, TwoPhaseDPInput construction, exact property-scalar forwarding, the complete missing/invalid scalar matrix, gradient-to-drop conversion, friction_multiplier placement, hidden-default absence, per-cell segmented conversion, every supported BC path in all three models, wrong mode/correlation combinations, registry absence, and CoolProp/PropertyBackend absence.

Phase 11O two-phase DP correlation migration is complete as a checkpoint.

- **`MSHTwoPhaseFrictionGradient`** — Müller-Steinhagen & Heck (1986) two-phase frictional pressure gradient. Formula: `dP/dx = [A + 2(B-A)x](1-x)^(1/3) + B*x³`, where A = all-liquid Darcy-Weisbach gradient and B = all-vapor Darcy-Weisbach gradient, each using Churchill (1977) friction factor at smooth-wall conditions. Implements `CorrelationRole.TWO_PHASE_DP`, returns `CorrelationOutput.value[0]` = dP/dx [Pa/m] (gradient, not integrated drop). Migration source: `legacy/PyP2PL/pyp2pl/correlations/dp_twophase.py` `msh_frictional_gradient`; confirmed against `legacy/MPL_Simulator/mpl/correlations.py` `MullerSteinhagenHeckDP`. Reference: Müller-Steinhagen & Heck (1986) Chem. Eng. Process. 20(6):297–308; evaluated by Ould Didi et al. (2002); used by Kokate PhD (2024) Appendix B.
- **Output semantics**: gradient dP/dx [Pa/m], positive = pressure decreasing in flow direction. Gravity and acceleration gradients are NOT included (Component terms per §3.2). Same sign convention and output form as `ChurchillFrictionGradient`.
- **Required explicit inputs via `TwoPhaseDPInput`**: `G` [kg/m²s], `x[0]` quality ∈ [0, 1], and `D_h` [m], plus caller-supplied `rho_l`, `rho_v`, `mu_l`, and `mu_v` entries in the immutable `property_scalars` mapping authorized by Decision 011. The mapping defaults empty. MSH validates required keys as finite and strictly positive; missing or invalid entries raise `ValueError`. No direct `TwoPhaseDPInput.rho_l/rho_v/mu_l/mu_v` fields remain.
- **Validity envelope**: quality x ∈ [0, 1]; D_h ≥ 1 μm. No G bounds declared (source does not establish explicit limits). `EXTRAPOLATED` for D_h < 1 μm; `IN_ENVELOPE` for x ∈ [0, 1], D_h ≥ 1 μm. x outside [0, 1] is a hard `ValueError` (physically impossible).
- **HX injection at the Phase 11O checkpoint**: originally deferred because HX models only built `SinglePhaseDPInput`. Phase 11P resolves that deferral with an explicit two-phase builder mode, Decision 011 property-scalar forwarding, and gradient-to-drop multiplication by `L_cell`.
- No CoolProp, no PropertyBackend, no quality clamping, no hidden defaults, no automatic closure selection, no CorrelationRegistry resolution inside HX models.
- `tests/correlations/test_two_phase_dp.py` contains 83 tests covering the contract field manifest, immutable mapping behavior, required scalar failures, independent numerical verification, quality endpoints, Reynolds envelope boundaries, Pa/m and `L_cell` semantics, refrigerant scope, registry/export behavior, architecture boundaries, and the HX input/output boundary.
- `MSHTwoPhaseFrictionGradient` exported from `mpl_sim.correlations`.

Phase 11N explicit q_flux plumbing is complete and approved as a checkpoint.

- `HXSolveRequest.q_flux_primary: float | None = None` added in `src/mpl_sim/hx_models/base.py`. Validation: finite and strictly positive when supplied; zero, negative, NaN, and infinite values raise `ValueError`.
- All three HX model input builders updated to thread the field through:
  - `EpsilonNTUModel._build_htc_input` passes `q_flux=req.q_flux_primary`
  - `LMTDModel._build_htc_input` passes `q_flux=req.q_flux_primary`
  - `SegmentedMarchModel._build_htc_input_for_cell` passes `q_flux=req.q_flux_primary`
- Epsilon-NTU and segmented two-sided secondary HTC builders explicitly pass `q_flux=None`; primary q-flux never leaks to secondary HTC.
- `HTCInput.q_flux` already existed in the frozen correlation contract (no contract change).
- `ShahBoilingHTC` can now be injected into all three HX models when the caller supplies all required property scalars plus an explicit positive heat flux in `q_flux_primary`.
- `YanCondensationHTC` does not read `q_flux`; it remains injectable as before through explicit `geom_scalars`.
- No automatic heat-flux inference, no `Q / A_ht` fallback, no hidden default. `q_flux_primary=None` (the default) leaves `HTCInput.q_flux=None`; correlations that require it will raise their own `ValueError`.
- No CoolProp, no `PropertyBackend`, no `CorrelationRegistry` resolution inside HX models. `FluidState` remains pure `(P, h, identity)`.
- New test file `tests/hx_models/test_hx_q_flux_plumbing.py` with 46 tests covering validation, passthrough, side isolation, Shah injection/failures/Q sensitivity/verdicts, Yan regression, and architecture boundaries.

Phase 11M two-phase HTC correlation foundation is complete as a checkpoint.
Phase 11L single-phase HTC correlation migration is complete as a checkpoint.
Phase 11K HX closure integration inventory and adapter foundation is approved and safe to merge as a checkpoint.
The Phase 11 final closeout assessment is checkpoint-only: Phase 11 remains open.

- **Phase 11M** adds two active two-phase HTC closures to `src/mpl_sim/correlations/two_phase_htc.py`:
  - **`ShahBoilingHTC`** — saturated flow boiling HTC via Shah (1982). Formula: `alpha = max(alpha_cb, alpha_nb)`; `alpha_l` = Dittus-Boelter liquid-only baseline at total mass flux G; N from convection number C0 and Froude number; four nucleate-boiling regime branches. Requires explicit `G`, `x`, `D_h`, `q_flux` from `HTCInput` fields plus `rho_l`, `rho_v`, `mu_l`, `k_l`, `Pr_l`, `h_fg` from `geom_scalars`. Quality must be strictly in (0, 1); ValueError for x ≤ 0 or x ≥ 1 (formula singular). Migration source: `legacy/MPL_Simulator/mpl/correlations.py` `ShahBoilingHTC` class; formula reference: Kokate & Park 2023 Appendix A / Kokate PhD 2024 Appendix A.
  - **`YanCondensationHTC`** — condensation HTC via Yan, Lio & Lin (1999). Formula: `G_eq = G * (1 - x + x * sqrt(rho_l/rho_v))`, `Re_eq = G_eq * D_h / mu_l`, `h = 4.118 * Re_eq^0.4 * Pr_l^(1/3) * k_l / D_h`. Requires explicit `G`, `x`, `D_h` from `HTCInput` fields plus `rho_l`, `rho_v`, `mu_l`, `k_l`, `Pr_l` from `geom_scalars`. Quality must be in [0, 1]; ValueError for x < 0 or x > 1; EXTRAPOLATED at endpoints x=0 and x=1. Migration source: `legacy/MPL_Simulator/mpl/correlations.py` `YanCondensationHTC` class; reference: Kokate & Park 2023.
  - Both implement `CorrelationRole.HTC`, return `CorrelationOutput.value[0]` = h [W/m²/K], carry `ValidityVerdict` + `ClosureMetadata`, and are exported from `mpl_sim.correlations`.
  - No CoolProp, no PropertyBackend, no quality clamping, no hidden defaults. All fluid property scalars must be supplied explicitly.
  - New test file `tests/correlations/test_two_phase_htc.py` added with 97 tests covering role, envelope, output shape, independently checked numerical values and Shah regime branches, validity verdicts, invalid input rejection, package exports, registry registration, architecture boundaries, and closure-specific HX injection status.
  - **HX injection status**: existing HX builders forward the complete `geom_scalars` mapping, so `YanCondensationHTC` is directly injectable when its explicit liquid/vapor scalars are supplied. `ShahBoilingHTC` remains deferred at HX level because the builders currently leave `HTCInput.q_flux=None`; future integration must add explicit heat-flux plumbing rather than a hidden default.

- **Phase 11L** adds two active single-phase HTC closures to `src/mpl_sim/correlations/`:
  - **`DittusBoelterHTC`** — turbulent pipe flow HTC via Dittus & Boelter (1930). Formula: `Nu = 0.023 * Re^0.8 * Pr^n`, `h = Nu * k / D_h`. Requires explicit `Re`, `Pr`, `k`, `n` from `geom_scalars` and `D_h` from `HTCInput.D_h`. Envelope: Re ≥ 10 000, Pr ∈ [0.6, 160], D_h ≥ 1 μm.
  - **`GnielinskiHTC`** — turbulent/transitional pipe flow HTC via Gnielinski (1976). Formula: Petukhov friction factor + modified Nusselt form, `h = Nu * k / D_h`. Requires explicit `Re`, `Pr`, `k` from `geom_scalars` and `D_h` from `HTCInput.D_h`. Envelope: Re ∈ [3 000, 5×10⁶], Pr ∈ [0.5, 2 000], D_h ≥ 1 μm.
  - Both implement `CorrelationRole.HTC`, return `CorrelationOutput.value[0]` = h [W/m²/K], carry `ValidityVerdict` + `ClosureMetadata`, and are exported from `mpl_sim.correlations`.
  - Both reject non-finite/non-positive required inputs with `ValueError`. Out-of-envelope but evaluable inputs return honest extrapolated values flagged `EXTRAPOLATED` — no clamping.
  - No CoolProp, no PropertyBackend, no hidden defaults. All fluid property scalars must be supplied explicitly by the caller.
  - New test file `tests/correlations/test_single_phase_htc.py` added with 82 tests covering role, envelope, output shape, numerical accuracy, validity verdict, invalid input rejection, package exports, registry registration, architecture boundaries, and HX model injection contracts (EpsilonNTUModel and SegmentedMarchModel).

- Updated closure inventory for `src/mpl_sim/correlations/`:
  - **Single-phase DP**: `ChurchillFrictionGradient` — implemented and tested.
  - **Volume-pressure law**: `PcaVolumePressureLaw` — implemented and tested.
  - **Single-phase HTC**: `DittusBoelterHTC`, `GnielinskiHTC` — **implemented and tested in Phase 11L**.
  - **Boiling HTC**: `ShahBoilingHTC` — **implemented and tested in Phase 11M** (Shah 1982, saturated flow boiling). Remaining (Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian, Kim-Mudawar 2012) deferred.
  - **Condensation HTC**: `YanCondensationHTC` — **implemented and tested in Phase 11M** (Yan et al. 1999, plate HX condensation). Remaining deferred.
  - **Two-phase DP**: `MSHTwoPhaseFrictionGradient` — **implemented and tested in Phase 11O** (MSH 1986, Churchill ff) and wired into HX models in Phase 11P. Remaining Homogeneous/Cicchitti and Kim-Mudawar 2013 closures are deferred.
  - **Placeholder/test**: none in production code; test-only stubs used in test files only.

- Phase 11K: No adapter or factory utilities were added: the existing `HXSolveRequest` injection seams are already sufficient for consuming any `Correlation`-contract-compliant closure without registry resolution or hidden defaults.
- Remaining boiling/condensation HTC migration, two-phase DP migration, moving boundary, counterflow segmented coupling, and full-loop integration remain deferred.

Phase 11J segmented sink coupling is approved and safe to merge as a checkpoint.
The Phase 11 final closeout assessment is checkpoint-only: Phase 11 remains open.

- `SegmentedMarchModel` now supports all four secondary BC classes in limited form: `FixedHeatRate`, finite-capacity segmented `FixedWallTemp`, finite-capacity segmented `AmbientCoupling`, and finite-capacity co-current segmented `SinkInletTempAndFlow`.
- The segmented sink path is explicitly co-current/parallel flow; both stream inlets enter cell 0. Counterflow is not claimed and remains deferred.
- The sink path requires explicit `primary_T_in`, finite positive `primary_cp`, `PrimaryThermalMode.FINITE_CAPACITY`, finite positive secondary inlet temperature/mass flow/cp, finite positive `A_ht`, both injected HTC correlations, and `UAComputationMode.TWO_SIDED`.
- Each sink cell evaluates primary HTC then secondary HTC, assembles two-sided `UA_cell`, applies co-current epsilon-NTU, and marches primary enthalpy plus diagnostic primary/secondary temperatures.
- `UAComputationMode.PRIMARY_ONLY` and `PrimaryThermalMode.CONSTANT_TEMPERATURE` are rejected clearly; no single-sided fallback or phase-change behavior is inferred.
- `SegmentedCellRecord` / `SegmentedProfile` remain immutable diagnostics. Cell primary and secondary temperatures are not stored in `FluidState`, on Ports, or in `SystemState`.
- `friction_multiplier` affects DP and pressure only; `raw_dP_primary` remains pre-calibration.
- Counterflow segmented sink coupling, phase-change segmented coupling, boiling/condensation HTC and two-phase-DP closure migrations, moving boundary, and full-loop integration remain deferred.
- Required validation passed on 2026-06-18: 2770 full tests, 1370 targeted HX/component tests, Ruff clean, and Black clean across 124 files.

Phase 11G HX model consolidation remains complete.

- New focused test file `tests/hx_models/test_hx_model_family_contracts.py` added (54 tests).
- Cross-model contracts verified: all three implemented models (`EpsilonNTUModel`, `LMTDModel`, `SegmentedMarchModel`) subclass `HeatExchangerModel`, return their correct and distinct `HeatExchangerModelKind`, and are registerable/resolvable through `HeatExchangerModelRegistry`.
- `HeatExchangerModelKind` confirmed to have exactly four declared seams: `EPSILON_NTU`, `LMTD`, `SEGMENTED_MARCH`, `MOVING_BOUNDARY`.
- No `MovingBoundaryModel` class is implemented or exported; `MOVING_BOUNDARY` remains a declared seam only.
- Unsupported BCs in `LMTDModel` (`FixedHeatRate`, `SinkInletTempAndFlow`) and `SegmentedMarchModel` (`SinkInletTempAndFlow`, `FixedWallTemp`, `AmbientCoupling`) confirmed to raise `UnsupportedHeatExchangerBoundaryConditionError`.
- `EpsilonNTUModel` `FixedHeatRate` path confirmed still supported.
- Import-boundary coverage extended to `lmtd.py` and `segmented.py` (previously `test_hx_model_architecture_boundaries.py` covered only `base.py`, `epsilon_ntu.py`, `registry.py`).
- All exports (`EpsilonNTUModel`, `LMTDModel`, `SegmentedMarchModel`, `SegmentedCellRecord`, `SegmentedProfile`) verified in `mpl_sim.hx_models.__all__`.
- No new physics was added. No `MovingBoundaryModel` was implemented. No architecture documents were modified.
- Final Phase 11 closeout is not yet supported by `IMPLEMENTATION_PLAN.md`: required HTC/DP closure migrations, meaningful segmented per-cell HTC/secondary coupling, and the converged full-loop acceptance case remain incomplete.

Phase 11F segmented HX model foundation checkpoint is complete and safe to merge as a checkpoint.

- New `SegmentedMarchModel` is implemented under `src/mpl_sim/hx_models/segmented.py`.
- `SegmentedMarchModel.kind()` returns `HeatExchangerModelKind.SEGMENTED_MARCH`.
- `SegmentedMarchModel` is exported from `mpl_sim.hx_models` and can be registered/resolved through `HeatExchangerModelRegistry`.
- `SegmentedCellRecord` and `SegmentedProfile` are immutable diagnostic value objects exported from `mpl_sim.hx_models`.
- Supported in this checkpoint: `FixedHeatRate`.
- Explicitly unsupported in this checkpoint: `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling`.
- `FixedHeatRate` is split evenly over explicit `UNIFORM` `n_cells`, with per-cell `h_out = h_in + Q_cell / primary_mdot`.
- Optional primary DP is handled cell-wise through injected `dp_primary`; `raw_dP_primary` is the pre-calibration sum of raw cell DP outputs.
- `friction_multiplier` affects DP and pressure only, not heat rate or enthalpy.
- `HXSolveResult.zone_profile` carries the diagnostic `SegmentedProfile`; it is not stored in `SystemState` or attached to Ports.
- `SegmentedMarchModel` does not import CoolProp, construct or call `PropertyBackend`, import Network/Solver, or resolve `CorrelationRegistry`.
- Phase 11 remains incomplete; segment-wise secondary coupling, local HTC/UA solving, moving-boundary modeling, migrated boiling/condensation HTC and two-phase DP closures, loop residual integration, validation harnesses, DOE, dynamics, controls, fitting, and optimization remain deferred.

Phase 11E LMTD HX model foundation checkpoint remains complete and safe to merge as a checkpoint.

- New `LMTDModel` is implemented under `src/mpl_sim/hx_models/lmtd.py`.
- `LMTDModel.kind()` returns `HeatExchangerModelKind.LMTD`.
- `LMTDModel` is exported from `mpl_sim.hx_models` and can be registered/resolved through `HeatExchangerModelRegistry`.
- `LMTDModel` is a `HeatExchangerModel`, not a `Correlation`, and LMTD remains absent from `CorrelationRole`.
- Supported in this checkpoint: `FixedWallTemp` and `AmbientCoupling`.
- Explicitly unsupported in this checkpoint: `SinkInletTempAndFlow` and `FixedHeatRate`.
- `FixedWallTemp` requires explicit `primary_T_in`, explicit finite positive `A_ht`, and injected `htc_primary`.
- `FixedWallTemp` computes `Q = htc_multiplier * h_primary * A_ht * (T_wall - primary_T_in)`.
- `AmbientCoupling` computes `Q = UA_ambient * (T_ambient - primary_T_in)` without requiring `A_ht` or `htc_primary`.
- `htc_multiplier` deliberately does not affect `UA_ambient`; this boundary is tested.
- DP remains injected through `dp_primary`; `friction_multiplier` affects DP only.
- `LMTDModel` does not import CoolProp, construct or call `PropertyBackend`, import Network/Solver, or resolve `CorrelationRegistry`.
- Phase 11 remains incomplete; full two-stream LMTD solving, primary outlet-temperature iteration, LMTD correction factors, segmented march, moving boundary, migrated boiling/condensation HTC and two-phase DP closures, loop residual integration, validation harnesses, DOE, dynamics, controls, fitting, and optimization remain deferred.

Phase 11D HX boundary-condition expansion checkpoint remains complete and safe to merge as a checkpoint.

- `EpsilonNTUModel` now supports all declared `SecondaryFluidBC` variants: `FixedHeatRate`, `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling`.
- `FixedWallTemp` requires explicit `primary_T_in`, explicit finite positive `A_ht`, and injected `htc_primary`.
- `FixedWallTemp` computes `Q = htc_multiplier * h_primary * A_ht * (T_wall - primary_T_in)`, with `Q > 0` heating the primary side and `Q < 0` cooling it.
- `FixedWallTemp` rejects invalid HTC outputs before computing UA, propagates HTC/DP verdicts, and keeps `friction_multiplier` limited to DP.
- `AmbientCoupling` requires explicit `primary_T_in` and uses `UA_ambient` and `T_ambient` directly for `Q = UA_ambient * (T_ambient - primary_T_in)`.
- `AmbientCoupling` does not require `A_ht` or `htc_primary` for energy calculation.
- `AmbientCoupling` deliberately does not apply `htc_multiplier` to `UA_ambient`; this calibration boundary is tested.
- Both new paths test heating/cooling sign convention and `h_out = h_in + Q / primary_mdot`.
- `UnsupportedHeatExchangerBoundaryConditionError` remains only as a future-proof guard for unrecognized BC objects.
- No hidden defaults were added for water cp, heat-transfer area, hydraulic diameter, density, viscosity, primary temperature, wall temperature, ambient temperature, ambient UA, HTC, or DP.
- HX models and wrappers still do not import CoolProp, construct PropertyBackend, import Network/Solver, or resolve `CorrelationRegistry`.
- Phase 11 remains incomplete; LMTD, segmented march, moving boundary, migrated HTC/DP closures, loop residual integration, validation harnesses, DOE, dynamics, controls, fitting, and optimization remain deferred.

Phase 11C HX wrapper and input-hardening checkpoint remains complete and safe to merge as a checkpoint.

- `EvaporatorHXInput` now exposes `htc_secondary`.
- `EvaporatorComponent` forwards `htc_secondary` into `HXSolveRequest`, so `UAComputationMode.TWO_SIDED` can be exercised through the wrapper when both HTC correlations are supplied.
- Evaporator and Condenser component tests verify forwarding of `primary_T_in`, `primary_cp`, `primary_thermal_mode`, `ua_computation_mode`, `htc_primary`, `htc_secondary`, `dp_primary`, `htc_multiplier`, and `friction_multiplier` using recording/dummy HX models.
- `EpsilonNTUModel` rejects missing, non-finite, non-positive, or out-of-range required scalars where used: `G`, `D_h`, `L_cell`, `rho`, `mu`, `A_ht`, and vapor quality `x`.
- HTC outputs used for UA must be finite and strictly positive in `PRIMARY_ONLY` and `TWO_SIDED`; invalid outputs raise before UA is computed.
- DP outputs must be finite. Signed DP remains intentional: negative DP is allowed as pressure recovery, with no `abs` or clipping.
- Friction calibration still affects DP only and does not affect `Q` or enthalpy balance.
- No hidden defaults were added for heat-transfer area, hydraulic diameter, density, viscosity, mass flux, quality, water/cp, phase-change inference, or single-sided UA fallback. The explicit `roughness = 0.0` smooth-wall convention remains the only accepted default.
- HX models and wrappers still do not import CoolProp, construct PropertyBackend, import Network/Solver, or resolve `CorrelationRegistry`.
- `docs/presentations` lint/noise is unrelated to Phase 11C and should be handled later in a separate `chore/remove-presentation-artifacts` or docs cleanup branch.

Phase 11B sink-side epsilon-NTU checkpoint remains complete and safe to merge as a checkpoint.

- `SinkInletTempAndFlow` is now implemented in `EpsilonNTUModel` as a lumped counterflow epsilon-NTU heat balance.
- `PrimaryThermalMode` is explicit: `FINITE_CAPACITY` requires explicit positive `primary_cp`; `CONSTANT_TEMPERATURE` forbids `primary_cp` and represents the isothermal/phase-change limit without inference from `None`.
- `UAComputationMode` is explicit: `PRIMARY_ONLY` requires primary HTC; `TWO_SIDED` requires primary and secondary HTC and uses the series resistance formula.
- `primary_T_in`, sink-side `T_in`, sink `mdot_secondary`, sink `cp_secondary`, `primary_mdot`, and `A_ht` are explicit and validated.
- The sign convention is explicit and tested: `Q > 0` heats the primary side, `Q < 0` cools it, and `h_out = h_in + Q / primary_mdot`.
- HTC/UA calibration affects UA, NTU, epsilon, and Q; friction calibration affects `dP_primary` and not energy balance.
- Correlation verdicts from HTC and DP calls are propagated into `HXSolveResult`.
- HX models still do not import CoolProp, construct PropertyBackend, resolve `CorrelationRegistry`, import Network/Solver, or store derived properties.
- Components forward the new primary thermal and UA mode fields into `HXSolveRequest`; Phase 11C completed Evaporator secondary-HTC forwarding.

Phase 11 foundation checkpoint remains complete and safe to merge as a checkpoint.

- `HeatExchangerModelKind`, `HXSolveRequest`, `HXSolveResult`, secondary-fluid BC value objects, and `HeatExchangerModel` contract under `src/mpl_sim/hx_models/base.py`.
- Separate `HeatExchangerModelRegistry` under `src/mpl_sim/hx_models/registry.py`.
- V1 `EpsilonNTUModel` under `src/mpl_sim/hx_models/epsilon_ntu.py`, supporting `FixedHeatRate` only and explicitly rejecting unsupported BCs.
- Required HX model physical scalars are explicit and finite; no hidden `D_h`, `rho`, `mu`, `L_cell`, `G`, or `x` defaults remain.
- Optional missing `roughness` is documented and tested as a smooth-wall assumption.
- `EvaporatorComponent` and `CondenserComponent` wrappers under `src/mpl_sim/components/`, with value-free inlet/outlet ports and local delegation to injected HX models.
- HX model slots are separate from HTC/DP correlation slots.
- Components and HX models avoid Network, Solver, PropertyBackend construction, and direct CoolProp calls.
- Tests cover HX contract, registry separation, unsupported BCs, missing physical scalars, optional roughness, component boundaries, and architecture-boundary searches.

This checkpoint changed Phase 11 source/tests and documentation only. It did not modify Pump, Accumulator, Network pressure-reference wiring, Solver behavior, schemas/results/validation primitives, property backends, calibration primitives, or frozen architecture documents.

Phase 10 remains complete and already safe to merge.

- Pump component foundation under `src/mpl_sim/components/pump.py`.
- Pump prescribed pressure-rise seam: `delta_p = delta_p_setpoint * pressure_rise_multiplier`.
- Pump performance-map behavior through `PumpPerformanceMap` and `evaluate_pump_map`.
- Pump command scope through `PumpSpeedCommand`, `PumpFlowTarget`, and target binding checks.
- Pump power/efficiency seam through explicit scalar `PumpPowerInput`.
- Pump geometry and named-frozen shaft-speed/inertia seam with `internal_state_names()` including `omega`.
- Pump hydraulic summary with raw and scaled pressure-rise reporting.
- Accumulator component foundation under `src/mpl_sim/components/accumulator.py`.
- Accumulator prescribed pressure-reference seam: `p_ref = p_setpoint`.
- Accumulator `VolumePressureLawBinding`, `evaluate_volume_pressure_law`, and `V_g` internal-state seam.
- Accumulator pressure summary with setpoint echo.
- `VOLUME_PRESSURE_LAW` correlation role and PCA volume-pressure law closure.
- HCA remains a declared seam; no numeric HCA closure was required for Phase 10 closeout because the implementation plan conditions it on feasible legacy support.
- Network-owned pressure-reference wiring through `PressureReferenceWiring`.
- Minimal pump-driven, accumulator-referenced loop acceptance shape covered by tests.
- Pump and Accumulator exports from `src/mpl_sim/components/__init__.py`.

Pump and Accumulator remain local, immutable, physics-light components. They do not call CoolProp, `PropertyBackend`, Network, Solver, physical residual assembly, dynamic simulation, fitting, or optimization. Pump does not import correlations. Accumulator imports only the correlation contract and delegates law evaluation to caller-supplied correlations. Ports remain value-free, and `SystemState` remains the owner of numerical state values.

This Phase 10 audit closeout changed documentation only. No source code and no test files were modified during audit closeout.

The following remain deferred unless explicitly planned in Phase 11 or later:

- explicit pressure-reference port-name validation hardening;
- full physical residual assembly;
- pressure/flow solving for physically converged pump/accumulator loops;
- pump shaft-speed dynamics and control laws;
- accumulator dynamic inventory integration and `dP/dt`;
- HCA numeric closure if future legacy/data support justifies it;
- NPSH checks;
- optimization and fitting;
- dynamic simulation and controls;
- full sink-side Evaporator/Condenser heat-exchanger physics, phase change, migrated HTC/DP closures, and two-phase pressure drop until Phase 11 continuation work completes.

---

## 2. Authoritative Documents

All binding architecture and roadmap documents remain frozen unless a future task explicitly authorizes changes through the decision process.

| Document | Purpose | Authority level |
|---|---|---|
| `docs/architecture/ARCHITECTURE_MASTER.md` | Single source of architectural truth; frozen decisions [F1]-[F18] | Highest |
| `docs/architecture/INTERFACE_SPEC.md` | Frozen contracts and signatures for every DAG layer | Binding |
| `docs/architecture/CORRELATION_CONTRACT.md` | Closure contract, per-role input manifests, validity-envelope format | Binding |
| `docs/architecture/SCHEMA_SPEC.md` | Serialization schemas for tuple, Result, dataset, validation case | Binding |
| `docs/validation/TEST_PLAN_V1.md` | Test levels, acceptance gates, anti-pattern compliance tests | Binding |
| `docs/roadmap/IMPLEMENTATION_PLAN.md` | Authoritative phase order for all coding work | Binding |
| `docs/architecture/ARCHITECTURE_FINAL_AUDIT.md` | Pre-implementation coherence audit | Reference |
| `docs/decisions/DECISION_LOG.md` | Frozen governance record | Binding |

Key authority statements:

- `ARCHITECTURE_MASTER.md` remains the single source of architectural truth.
- `IMPLEMENTATION_PLAN.md` is the authority for phase order and build sequence.
- `TEST_PLAN_V1.md` defines acceptance gates.
- `DECISION_LOG.md` is required for any future frozen-contract change.

---

## 3. Completed Milestones

| Milestone | Status |
|---|---|
| Architecture master, interface spec, schema spec, correlation contract, test plan, implementation roadmap, final architecture audit | Complete |
| GitHub repository initialized | Complete |
| **Phase 0 - Repository Preparation and Tooling** | **Complete** |
| **Phase 1A - FluidIdentity and FluidState** | **Complete** |
| **Phase 1B - Port primitives** | **Complete** |
| **Phase 1C - SystemState and StateLayout** | **Complete** |
| **Phase 1 audit** | **Complete; approved for Phase 2** |
| **Phase 2A - PropertyBackend interface contract** | **Complete** |
| **Phase 2B - CoolPropBackend** | **Complete** |
| **Phase 2C - PropertyBackend registry and backend selection binding** | **Complete** |
| **Phase 2 property layer foundation** | **Complete** |
| **Phase 3A - Correlation contract primitives** | **Complete** |
| **Phase 3B - Correlation registry** | **Complete** |
| **Phase 3C - Churchill single-phase friction-gradient closure** | **Complete** |
| **Phase 3 correlation layer foundation** | **Complete; approved for Phase 4** |
| **Phase 4A - Immutable geometry primitives** | **Complete** |
| **Phase 4B - Discretization primitives** | **Complete** |
| **Phase 4 geometry and discretization foundation** | **Complete; approved for Phase 5** |
| **Phase 5A - Calibration primitives and registry** | **Complete** |
| **Phase 5A calibration audit** | **Complete; approved for Phase 6** |
| **Phase 6A - Component contract and Pipe skeleton** | **Complete** |
| **Phase 6B - Pipe single-phase friction-only kernel** | **Complete** |
| **Phase 6C - Pipe gravity pressure contribution** | **Complete** |
| **Phase 6D - Pipe acceleration pressure contribution** | **Complete** |
| **Phase 6E - Pipe mechanical pressure summary scaffold** | **Complete** |
| **Phase 6F - Pipe friction-only calibration placement proof** | **Complete** |
| **Phase 6 final audit** | **Complete; approved for Phase 7** |
| **Phase 7A - Network identity and topology primitives** | **Complete** |
| **Phase 7B - Connection validation and graph checks** | **Complete** |
| **Phase 7C - Network SystemState assembly** | **Complete** |
| **Phase 7 final audit** | **Complete; approved for Phase 8** |
| **Phase 8A - Solver contract primitives** | **Complete** |
| **Phase 8B - Residual evaluation interface** | **Complete** |
| **Phase 8C - Minimal convergence-gate steady solver** | **Complete** |
| **Phase 8D - Assembled steady problem wrapper, convergence metadata, and update interface** | **Complete** |
| **Phase 8E - Fixed-point steady solver loop** | **Complete** |
| **Phase 8 final audit** | **Complete; approved for merge and next phase** |
| **Phase 9 - Result and schema serialization** | **Complete** |
| **Phase 9 final audit** | **Complete; approved for merge and next phase** |
| **Phase 10 Pump and Accumulator foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 10** |
| **Phase 10 Pump and Accumulator final closeout** | **Complete; approved for merge and next phase** |
| **Phase 11 HeatExchangerModel, Evaporator and Condenser foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11B Sink-side epsilon-NTU checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11C HX wrapper and input hardening checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11D HX boundary-condition expansion checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11E LMTD HX model foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11F segmented HX model foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11G HX model consolidation checkpoint** | **Complete; safe to merge as Phase 11G checkpoint** |
| **Phase 11 final closeout assessment** | **Checkpoint only; Phase 11 remains open** |
| **Phase 11K HX closure integration inventory and adapter foundation checkpoint** | **Complete; safe to merge as Phase 11K checkpoint** |
| **Phase 11L Single-phase HTC correlation migration checkpoint** | **Complete; safe to merge as Phase 11L checkpoint** |
| **Phase 11M Two-phase HTC correlation migration foundation** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11N Explicit q_flux plumbing for HTC injection** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11O Two-phase DP correlation migration** | **Complete; audited and approved for merge as checkpoint on `phase-11o-two-phase-dp-migration`** |
| **Phase 11P Two-phase DP HX builder and gradient-to-drop plumbing** | **Complete; audited and approved for merge as checkpoint on `phase-11p-two-phase-dp-hx-plumbing`** |
| **Phase 11Q Evaporator/Condenser scenario plumbing foundation** | **Complete; implemented on `phase-11q-evaporator-condenser-scenario-plumbing`** |
| **Phase 11R Component contribution-path scenario binding** | **Complete; implemented on `phase-11r-component-contribution-scenario-binding`** |
| **Phase 11S Segmented counterflow / phase-change coupling foundation** | **Complete; implemented on `phase-11s-segmented-counterflow-phase-change-foundation`** |
| **Phase 11T Iterated counterflow segmented solver** | **Complete; implemented on `phase-11t-iterated-counterflow-segmented-solver`** |
| **Phase 11U HX closeout / readiness audit** | **Complete; approved checkpoint on `phase-11u-hx-closeout-readiness-audit`** |
| **Phase 12A Minimal Loop Assembly** | **Complete; implemented on `phase-12a-minimal-loop-assembly`** |
| **Phase 12B Examples and User Documentation Quickstart** | **Complete; implemented on `phase-12b-examples-user-docs-quickstart`** |
| **Phase 13A Minimal Closed MPL Solver** | **Complete; audited and approved checkpoint on `phase-13a-minimal-closed-mpl-solver`** |
| **Phase 13B Minimal Pressure Closure / Pump-Head Residual Foundation** | **Complete; implemented on `phase-13b-pressure-closure-foundation`** |
| **Phase 13C Residual / Unknown / Scaling Framework Foundation** | **Complete; implemented on `phase-13c-residual-framework-foundation`** |
| **Phase 13D Coupled Fixed-Architecture Energy+Pressure Closure** | **Complete; audited and approved checkpoint on `phase-13d-coupled-fixed-closure`** |
| **Phase 13E Network Graph Foundation** | **Complete; implemented on `phase-13e-network-graph-foundation`** |
| **Phase 13F Network Residual Assembly Foundation** | **Complete; implemented on `phase-13f-network-residual-assembly`** |
| **Phase 13G Network Residual Evaluation Foundation** | **Complete; implemented on `phase-13g-network-residual-evaluation`** |
| **Phase 13H Configurable Network Solver v1** | **Complete; implemented on `phase-13h-configurable-network-solver-v1`** |
| **Phase 14A Physical Residual Adapter Foundation** | **Complete; implemented on `phase-14a-physical-residual-adapter-foundation`** |
| **Phase 14B Component Binding and State-Vector Mapping Foundation** | **Complete; implemented on `phase-14b-component-binding-state-mapping`** |
| **Phase 14C Minimal Component Contribution Adapter Foundation** | **Complete; implemented on `phase-14c-minimal-component-contribution-adapter`** |
| **Phase 14D Component Contribution Contract Adapter Prep** | **Complete; implemented on `phase-14d-component-contribution-contract-prep`** |
| **Phase 14E Controlled Toy Component Execution Harness** | **Complete; implemented on `phase-14e-controlled-toy-component-execution`** |
| **Phase 14F Minimal Component-Like Contribution Provider Adapter** | **Complete; implemented on `phase-14f-component-like-provider-adapter`** |

Closeout artifacts:

- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- `docs/validation/audits/PHASE_2_PROPERTY_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`
- `docs/validation/audits/PHASE_5A_CALIBRATION_PRIMITIVES_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_CHECKPOINT_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_7_NETWORK_ASSEMBLY_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_9_SCHEMA_RESULTS_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_CLOSEOUT_AUDIT.md`
- `docs/validation/audits/PHASE_11_HEAT_EXCHANGER_MODEL_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11B_SINK_SIDE_EPSILON_NTU_AUDIT.md`
- `docs/validation/audits/PHASE_11C_HX_WRAPPER_INPUT_HARDENING_AUDIT.md`
- `docs/validation/audits/PHASE_11D_HX_BOUNDARY_CONDITION_EXPANSION_AUDIT.md`
- `docs/validation/audits/PHASE_11E_LMTD_HX_MODEL_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11F_SEGMENTED_HX_MODEL_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11G_HX_MODEL_CONSOLIDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11_FINAL_CLOSEOUT_AUDIT.md`
- `docs/validation/audits/PHASE_11H_SEGMENTED_WALL_HTC_COUPLING_AUDIT.md`
- `docs/validation/audits/PHASE_11I_SEGMENTED_AMBIENT_COUPLING_AUDIT.md`
- `docs/validation/audits/PHASE_11J_SEGMENTED_SINK_COUPLING_AUDIT.md`
- `docs/validation/audits/PHASE_11K_HX_CLOSURE_ADAPTER_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11L_SINGLE_PHASE_HTC_CORRELATIONS_AUDIT.md`
- `docs/validation/audits/PHASE_11M_TWO_PHASE_HTC_MIGRATION_AUDIT.md`
- `docs/validation/audits/PHASE_11N_EXPLICIT_Q_FLUX_HTC_PLUMBING_AUDIT.md`
- `docs/validation/audits/PHASE_11O_TWO_PHASE_DP_MIGRATION_AUDIT.md`
- `docs/validation/audits/PHASE_11P_TWO_PHASE_DP_HX_PLUMBING_AUDIT.md`
- `docs/validation/audits/PHASE_11Q_EVAPORATOR_CONDENSER_SCENARIO_PLUMBING_AUDIT.md`
- `docs/validation/audits/PHASE_11R_COMPONENT_CONTRIBUTION_SCENARIO_BINDING_AUDIT.md`
- `docs/validation/audits/PHASE_11S_SEGMENTED_COUNTERFLOW_PHASE_CHANGE_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11T_ITERATED_COUNTERFLOW_SEGMENTED_SOLVER_AUDIT.md`
- `docs/validation/audits/PHASE_11U_HX_CLOSEOUT_READINESS_AUDIT_PREP.md`
- `docs/validation/audits/PHASE_11U_HX_CLOSEOUT_READINESS_AUDIT.md`
- `docs/validation/audits/PHASE_13A_MINIMAL_CLOSED_MPL_SOLVER_AUDIT.md`
- `docs/validation/audits/PHASE_13B_PRESSURE_CLOSURE_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_13C_RESIDUAL_FRAMEWORK_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_13D_COUPLED_FIXED_CLOSURE_AUDIT.md`
- `docs/validation/audits/PHASE_13E_NETWORK_GRAPH_FOUNDATION_AUDIT.md`
- `docs/validation/audits/BLOCK_15A1_PRODUCTION_BRIDGE_BOUNDARY_AUDIT.md`
- `docs/validation/audits/BLOCK_15A2_READONLY_STATE_UNKNOWN_BRIDGE_AUDIT.md`
- `docs/validation/audits/BLOCK_15A3_CONTROLLED_PRODUCTION_LIKE_PATH_AUDIT.md`
- `docs/validation/audits/BLOCK_15A4_PRODUCTION_BRIDGE_CLOSEOUT_AUDIT.md`
- `docs/validation/audits/BLOCK_15B1_FIXED_SINGLE_LOOP_SCENARIO_AUDIT.md`
- `docs/validation/audits/BLOCK_15B4_FIXED_LOOP_CLOSEOUT_AUDIT.md`

---

## 4. Current Active Phase

**Block 15B.4 — Fixed Single-Loop MVP Closeout / Acceptance Integration** is
implemented and independently audited on `phase-15b4-fixed-loop-closeout`.

The implemented capability is intentionally narrow:

- the Block 15B.1 fixed single-loop declaration remains the only accepted
  scenario shape;
- all four residual parameters are explicit finite scalar values supplied by
  the caller;
- residual evaluation uses explicit algebraic callbacks for the declared
  fixed-loop unknown and residual names;
- the solve preserves the caller's continuity-consistent mass-flow gauge and
  solves only the determined four-pressure subsystem through the existing
  callback-only solver;
- all eight original residuals are re-evaluated after the pressure solve;
- report generation returns a plain serializable dictionary and writes no files;
- no real production component execution, `Component.contribute(...)`,
  `SystemState` assembly, `FluidState` construction, property/correlation
  lookup, CoolProp, component-type inference, graph-state attachment, generic
  `solve(network)`, or arbitrary-topology physical simulation.

Block 15B is complete only within the planned Minimal Physical Single-Loop
Network MVP scope. It is an algebraic fixed-loop MVP, not an arbitrary-topology
physical simulator. The absolute common mass-flow level is not determined by
the solve. Block 15A remains complete within its planned Production Component
Bridge MVP scope.

Phase boundaries to preserve:

- Keep `mpl_sim.closed_loop` fixed and case-specific; do not grow it into
  `solve(network)` or arbitrary topology.
- Preserve the generic, physics-free Phase 8 solver core in `mpl_sim.solvers`.
- Do not turn Network into a solver.
- Do not make Pipe, Pump, or Accumulator network-aware or solver-aware.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto component or Port objects.
- Keep `SystemState` as the only owner of numerical values.
- Keep arbitrary topology, moving boundaries, validation, valves, manifolds,
  recuperators, and pre/post-heaters in later phases.

---

## 5. Next Immediate Actions

1. Begin Block 15C only through an explicitly reviewed topology-extension scope.
2. Keep production-component execution, `SystemState` assembly, `FluidState`
   construction, property/correlation/HX-model calls, arbitrary topology, and
   generic `solve(network)` / `NetworkGraph.solve()` deferred unless separately
   scoped and reviewed.
3. Preserve the Phase 8 boundary: solver core remains generic and physics-free.
4. Preserve the Phase 7/13E-15B boundary: graph, assembly, binding, mapping,
   contribution-adapter, contribution-record, toy-executor, provider-adapter,
   inspection, production-bridge, read-only-view, and production-like bridge
   types remain explicit topology/declaration/adapter/value objects with no
   generic solve methods; Block 15B remains fixed-scenario and algebraic.
5. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
6. Keep dynamic controls, fitting, optimization, DOE generation, and literature validation deferred unless explicitly requested.
7. Run `pytest`, scoped lint appropriate to the branch, and `black --check src tests examples` before reporting the next implementation task complete.

---

## 6. Non-Negotiable Implementation Rules

These rules are operational forms of the frozen decisions. Violating any is a review failure.

| Rule | Source |
|---|---|
| Do not modify frozen architecture docs during coding | `IMPLEMENTATION_PLAN.md` |
| Do not introduce new architecture concepts | `ARCHITECTURE_MASTER.md` |
| Do not copy legacy code directly into `src/` | `IMPLEMENTATION_PLAN.md` |
| Do not call CoolProp outside `properties/` | [F6] |
| Do not store derived properties anywhere | [F3] |
| Do not put values on Port | [F10] |
| Do not make Solver depend on physics | [F1] |
| Do not put mesh/segment count in Geometry | [F16] |
| Do not put accumulator law parameters in AccumulatorGeometry | [F9] |
| Do not weaken a test to make code pass | `IMPLEMENTATION_PLAN.md` |
| Calibration must not be inside a correlation | [F5] |
| A correlation must not receive a Component or Geometry object | [F4] |
| Network must never know the Solver | [F1] |
| Components must never know their Network or neighbours | [F7] |

---

## 7. Current Known Blockers and Deferred Work

None block merging the Phase 11F segmented HX model foundation checkpoint.

| Item | What it affects | Resolution path |
|---|---|---|
| Explicit pressure-reference port-name validation not separately enforced | Minor network validation hardening | Add a focused validation test/check if pressure-reference port identity becomes semantically important |
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent if boundary risks grow |
| Full physical minimal `Result` artifact not yet implemented | Future schema/result integration | Add when later loop artifacts can produce physical run results |
| Physical invariant calculations not yet implemented | Future validation/residual integration | Keep primitives data-only until physical balances are explicitly planned |
| Full `ReproducibilityTuple` serialization not yet implemented | Future schema/result integration | Build on Phase 9 canonical primitives when physical tuple inputs are ready |
| Component serialization not yet implemented | Future schema integration | Add only safe serializers; avoid component-internal coupling |
| Physical residual assembly not yet implemented | Future solver integration | Add only when explicitly planned, keeping adapters separate from solver core |
| Newton and finite-difference Jacobian not yet implemented | Future solver strategy work | Introduce only when explicitly planned |
| Pressure solving and flow solving not yet implemented | Future loop solving work | Implement through generic residual/update contracts, not by coupling solver to components |
| Full two-stream LMTD and full segmented-march strategies not implemented | Phase 11 continuation | Build on the Phase 11E `LMTDModel` foundation and Phase 11F `SegmentedMarchModel` foundation; implement as `HeatExchangerModel` strategies, not correlations |
| Presentation artifact lint/noise remains on this branch lineage | Docs cleanup | Handle `docs/presentations` separately in `chore/remove-presentation-artifacts` or a docs cleanup branch |
| Remaining boiling/condensation HTC closures not migrated | Phase 11 continuation | Chen blocked by CoolProp inside legacy function; Bennett-Chen, Gungor-Winterton, Kandlikar, Kim-Mudawar 2012 deferred until safe legacy sources confirmed |
| Remaining two-phase DP closures not migrated | Phase 11 continuation | Homogeneous/Cicchitti and Kim-Mudawar 2013; port under correlation contract |
| Two-phase DP HX injection — `dp_primary_is_two_phase=True` wired | **Phase 11P complete** | All three HX models build `TwoPhaseDPInput` and multiply gradient × `L_cell` |
| Full loop residual integration with Evaporator and Condenser not implemented | Phase 11 continuation | Integrate through component/local residual adapters while keeping Solver physics-free |
| Heat transfer, phase change, and two-phase pressure drop incomplete | Phase 11+ | Continue in planned Phase 11 slices; do not fake Phase 12 validation |
| 29 property CSV files missing | Future `TabulatedPropertyBackend`; `sigma_e`/`eps_r` | Data recovery task; does not block CoolProp-backed V1 path |
| Literature validation data must be lifted and pinned | Literature tests | Phase 12 validation-data task |
| Full artifact metadata for content-hash canonicalization rule | Future tuple/result artifacts | Phase 9 implements sorted-key compact JSON + SHA-256; record the rule in full artifact metadata when those artifacts are added |

---

## 8. Instructions for Future AI Agents

Before any coding task, read in order:

1. `docs/roadmap/PROJECT_STATUS.md`
2. `docs/roadmap/IMPLEMENTATION_PLAN.md`
3. `docs/validation/TEST_PLAN_V1.md`
4. Relevant sections of `docs/architecture/INTERFACE_SPEC.md`
5. Relevant audit/closeout documents in `docs/validation/audits/`

Rules for the next implementation session:

- The Phase 11F segmented HX model foundation checkpoint is safe to merge.
- The branch `phase-11f-segmented-hx-model-foundation` is safe to merge into `main` as a checkpoint.
- Phase 10 is complete.
- Phase 11 is not complete; continue Phase 11 heat-exchanger work according to `IMPLEMENTATION_PLAN.md`.
- `FixedHeatRate`, `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling` are implemented in `EpsilonNTUModel`; Phase 11C completed wrapper sink-side forwarding and input/output hardening; Phase 11D completed fixed-wall and ambient boundary-condition support; Phase 11E added limited `LMTDModel` support for `FixedWallTemp` and `AmbientCoupling` while keeping `SinkInletTempAndFlow` and `FixedHeatRate` explicitly unsupported in `LMTDModel`; Phase 11F added limited `SegmentedMarchModel` support for `FixedHeatRate` while keeping segment-wise secondary coupling and local HTC/UA solving deferred. Continue with full HX strategies, correlation migrations, and loop integration.
- Do not reopen Phase 9 unless a new task explicitly requests a Phase 9 fix.
- Keep schema/results/validation serialization data-only and physics-free.
- Keep solver core generic and physics-free.
- Keep physical residual adapters separate from solver core.
- Keep Network topology/assembly/reference wiring separate from solver behavior.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Keep Pump and Accumulator local; do not add network or solver behavior to either component.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, solvers, schema, and results.
- Continue Pump and Accumulator only for focused fixes or hardening; continue Phase 11 from the Phase 11F HX checkpoint. Keep dynamic controls, fitting, optimization, DOE, literature validation, Newton/Jacobian expansion, and transient solving deferred unless explicitly requested.
- Run `pytest`, appropriate scoped lint, and `black --check src tests` before reporting any implementation task complete. Keep scoped audit commands tied to the requested branch surface.
- Do not include `Co-Authored-By` lines unless explicitly requested.
- Phase 14A added `PhysicalResidualContext`, `PhysicalResidualAdapter`,
  `PhysicalResidualAdapterSet`, and `build_network_residual_evaluators` to
  `mpl_sim.network`. These are explicit callback adapters only: no component
  execution, `component_type` inference, properties, correlations, CoolProp,
  or graph-state mutation.
- Phase 14B added `ComponentBinding`, `ComponentBindingSet`,
  `ComponentStateMap`, `NetworkBindingContext`, and `build_binding_context` to
  `mpl_sim.network`. These are immutable declarations only: no numerical
  state, component execution, `component_type` inference, properties,
  correlations, CoolProp, or graph-state mutation.
- Phase 14C added `ComponentContributionContext`, `ComponentContribution`,
  `ComponentContributionAdapter`, `ComponentContributionAdapterSet`, and
  `build_physical_adapters_from_contributions` to `mpl_sim.network`. These
  adapt explicit caller-supplied callbacks only: no real component execution,
  `Component.contribute(...)`, `SystemState`, property/correlation lookup,
  component-type inference, CoolProp, or graph-state mutation.
- Phase 14D added `ContributionRecord`, `ContributionRecordSet`,
  `ContributionResidualMap`, and
  `map_contribution_records_to_component_contribution` to `mpl_sim.network`.
  These are value-object contracts and explicit name translation only: no real
  component execution, `Component.contribute(...)`, `SystemState`,
  `FluidState`, property/correlation lookup, component-type inference,
  CoolProp, or graph-state mutation.
- Phase 14E added `ToyComponentExecutionContext`, `ToyComponentExecutor`,
  `ToyComponentExecutorSet`, `execute_toy_component_contributions`, and
  `build_component_contribution_from_toy_execution`. These execute only
  explicit caller-supplied toy functions and add no production component,
  property, correlation, state-assembly, or component-type inference path.
- Phase 14G added `ProductionComponentContractStatus`,
  `ProductionComponentContributionSignature`, `ProductionComponentInspectionResult`,
  `inspect_production_component_contract`, and
  `inspect_known_production_component_contracts` to `mpl_sim.network`. These are
  static inspection utilities using Python's `inspect` module: no component
  instantiation, no `contribute(...)` call, no `SystemState`, no `FluidState`,
  no property/correlation lookup, no component-type inference, no CoolProp,
  no graph-state attachment. All known production components return
  `NO_CONTRIBUTE_METHOD`.
- Phase 14F added `ComponentProviderExecutionContext`,
  `ComponentContributionProviderProtocol`, `ComponentContributionProviderBinding`,
  `ComponentContributionProviderSet`, `execute_component_provider_contributions`,
  and `build_component_contribution_from_provider_execution` to `mpl_sim.network`.
  These drive controlled provider objects via a `produce_records` method (NOT
  named `contribute`), return `ContributionRecordSet`, validate record ownership
  and duplicates, and feed the Phase 14D/14C/14A/13G/13H stack. No real
  component execution, `Component.contribute(...)`, method named `contribute`,
  `SystemState`, `FluidState`, property/correlation lookup, component-type
  inference, CoolProp, or graph-state mutation.
- Phase 13H added `NetworkSolveConfig`, `NetworkSolveResult`, `solve_network_residual_problem` to `mpl_sim.network`. The solver is a damped FD Newton method with internal Gaussian elimination — no scipy, no numpy root-finders. Accepts explicit evaluator callbacks and scales only; does NOT construct residuals from component physics. Physical network residual construction (from Pipe, Pump, Accumulator component contributions) is deferred to Phase 14+.
- Phase 11P added `HXSolveRequest.dp_primary_is_two_phase: bool = False`. When `True`, HX models build `TwoPhaseDPInput` with `rho_l`, `rho_v`, `mu_l`, `mu_v` from `geom_scalars` into `property_scalars`, and multiply `value[0] * L_cell` for gradient-to-drop conversion. Single-phase DP path (default `False`) is unchanged.
- Two-phase DP is now injectable into all three HX models using `MSHTwoPhaseFrictionGradient` when the caller supplies required scalars in `geom_scalars` and sets `dp_primary_is_two_phase=True`.
- Phase 11Q added `q_flux_primary: float | None = None` and `dp_primary_is_two_phase: bool = False` to both `EvaporatorHXInput` and `CondenserHXInput`, forwarding both fields explicitly to `HXSolveRequest`. Evaporator scenarios with `ShahBoilingHTC` + q_flux + two-phase DP, and condenser scenarios with `YanCondensationHTC` + two-phase DP, are now representable through the component wrappers without hidden defaults or automatic closure selection.
- Phase 11T added `CounterflowIterationConfig` and `HXSolveRequest.counterflow_iteration: CounterflowIterationConfig | None = None`. When `enabled=True` (requires `SinkInletTempAndFlow` + `COUNTERFLOW`), `SegmentedMarchModel` performs bounded fixed-point iteration over the secondary temperature profile. `HXSolveResult` now carries `iteration_count`, `converged`, and `residual`; these are `0`/`None`/`None` on all non-iterated paths. The one-pass counterflow and co-current paths are completely unchanged.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-24 |
| **Updated by** | Codex |
| **Status note** | Block 15B.4 fixed-loop MVP closeout independently audited on `phase-15b4-fixed-loop-closeout`; 5612 full-suite tests, 1751 network tests, 47 focused Block 15B.4 tests, 100 Block 15B.3 runner tests, 102 Block 15B.2 residual tests, 84 Block 15B.1 scenario tests, and 38 Block 15A.4 closeout regression tests passed with no skips, xfails, or deselections; all six example programs, Ruff, Black, and diff checks passed; all six known production classes still return `NO_CONTRIBUTE_METHOD`; Block 15B is complete only within the planned fixed-loop MVP scope. |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
