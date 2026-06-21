"""Minimal coupled fixed-architecture closure example — Phase 13D.

Demonstrates the first coupled fixed-architecture energy+pressure closure
using the public Phase 13D API.  The solver finds primary_mdot and Q_cond
simultaneously such that both closure conditions are satisfied:

    energy_residual   = h_return - h_reference = 0   (energy closure)
    pressure_residual = pump_head(mdot) - dP_total(mdot) = 0  (pressure closure)

where:

    dP_total = dP_evap(mdot) + dP_cond(mdot)
    G_evap   = primary_mdot / evap_flow_area
    G_cond   = primary_mdot / cond_flow_area

Architecture: reference_state -> evaporator -> condenser.

Solver strategy: Option A — nested scalar bisection.
  Outer: bisect primary_mdot for pressure residual = 0.
  Inner: at each outer trial mdot, bisect Q_cond for energy residual = 0.

What this demonstrates
----------------------
- Two-variable coupled closure (energy + pressure) via nested scalar bisection.
- Both residuals driven to zero simultaneously.
- Explicit pump-head law via PumpHeadCurve.
- Explicit Q_cond bracket for inner energy solve.
- Explicit mdot bracket for outer pressure solve.
- ResidualVector for convergence diagnostics with configured scales.
- All HX inputs explicit; no automatic closure selection.
- No CoolProp, no PropertyBackend, no network topology assembly.

What this does NOT demonstrate
-------------------------------
- Generic network solving with arbitrary topology (deferred to Phase 13E/13F).
- Parallel evaporator branches (deferred to Phase 14+).
- Valves, manifolds, recuperator, pre/post-heaters (deferred).
- Moving-boundary modeling (deferred).
- Automatic phase inference or quality marching (deferred).
- Validation against experimental data (deferred to Phase 12 harness).
- This is not a validated physical model.
- Fixed architecture only: one evaporator + one condenser + one pump law.

Usage
-----
    python examples/minimal_coupled_closure.py
"""

from __future__ import annotations

from mpl_sim.closed_loop import (
    CoupledClosureConfig,
    MinimalCoupledClosureCase,
    PumpHeadCurve,
    solve_minimal_coupled_closure,
)
from mpl_sim.components import (
    ComponentId,
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.correlations import (
    AnyFluid,
    ClosureMetadata,
    Correlation,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SinglePhaseDPInput,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import (
    FinGeometry,
    MicrochannelGeometry,
    PlateGeometry,
    PortDimensions,
)
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate


class LinearMassFluxPressureDrop(Correlation):
    """Explicit deterministic example DP law: dP = coefficient * G [Pa].

    No property lookup; no CoolProp.  Used only in this example to keep
    the pressure balance analytical and exact.
    """

    def __init__(self, coefficient: float, name: str) -> None:
        self._coeff = coefficient
        self._name = name
        self._source = SourceRef(citation="Phase 13D deterministic acceptance law")
        self._envelope = ValidityEnvelope(
            fluid_families=(AnyFluid(),),
            bounds=(),
            source=self._source,
        )

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return self._envelope

    def evaluate(self, inp: SinglePhaseDPInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(self._coeff * inp.G,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name=self._name, correlation_version="1"),
                violated=(),
            ),
            metadata=ClosureMetadata(name=self._name, version="1", source=self._source),
        )


if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Explicit example inputs — no hidden defaults, no property lookup.
    # All scalars are named constants; geometry is explicit.
    # ------------------------------------------------------------------

    # Fluid identity — no CoolProp call in this path.
    FLUID = PureFluid(name="R134a")

    # Primary loop reference / inlet state.
    REFERENCE_P_PA = 800_000.0  # [Pa]
    REFERENCE_H_JKG = 250_000.0  # [J/kg]
    reference_state = FluidState(P=REFERENCE_P_PA, h=REFERENCE_H_JKG, identity=FLUID)

    # HX model strategy: lumped ε-NTU (stateless, no registry lookup).
    model = EpsilonNTUModel()
    disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

    # ------------------------------------------------------------------
    # Deterministic pressure-drop laws.
    #
    # dP_evap = EVAP_DP_PER_G * G_evap = 100 * (mdot / 0.01) = 10000 * mdot
    # dP_cond = COND_DP_PER_G * G_cond = 50  * (mdot / 0.02) =  2500 * mdot
    # dP_total = 12500 * mdot
    #
    # Pump law: ΔP_pump(mdot) = HEAD_PA - SLOPE_PA_S_KG * mdot
    #                          = 5625 - 100000 * mdot
    #
    # Pressure root: 5625 = 112500 * mdot  →  mdot* = 0.05 kg/s
    #
    # Energy law (FixedHeatRate with one lumped cell):
    #   h_change = Q / mdot   (explicit; no property lookup)
    #
    # With Q_evap = 200 W, energy closure requires Q_cond = -200 W:
    #   h_return = h_ref + (Q_evap + Q_cond)/mdot = h_ref + 0 = h_ref  ✓
    #
    # At mdot* = 0.05 kg/s:
    #   dP_evap  = 10000 * 0.05 = 500 Pa
    #   dP_cond  =  2500 * 0.05 = 125 Pa
    #   dP_total = 625 Pa
    #   pump_head = 5625 - 5000 = 625 Pa  ✓ (equals dP_total)
    # ------------------------------------------------------------------
    EVAP_FLOW_AREA_M2 = 0.01  # [m²]  evaporator primary flow area
    COND_FLOW_AREA_M2 = 0.02  # [m²]  condenser primary flow area
    EVAP_DP_PER_G = 100.0  # [Pa/(kg·m⁻²·s⁻¹)]
    COND_DP_PER_G = 50.0  # [Pa/(kg·m⁻²·s⁻¹)]

    dp_geom_scalars = {
        "G": 1.0,  # replaced by mdot / flow_area during solve
        "D_h": 0.001,  # [m]
        "L_cell": 1.0,  # [m]
        "rho": 1000.0,  # [kg/m³]
        "mu": 0.001,  # [Pa·s]
        "roughness": 0.0,
    }

    # ------------------------------------------------------------------
    # Evaporator — fixed heat input Q_evap to primary side.
    # ------------------------------------------------------------------
    Q_EVAP_W = 200.0  # [W] heat added to primary
    evap_geom = MicrochannelGeometry(
        N_channels=20,
        D_h_channel=0.001,
        fin_geometry=FinGeometry(fin_pitch=500.0, fin_height=0.010, fin_thickness=0.0002),
        A_heated=0.05,
        wall_mass=0.20,
        wall_material="aluminium",
    )
    evap_component = EvaporatorComponent(
        component_id=ComponentId(name="evaporator"),
        geometry=evap_geom,
    )
    evap_scenario = EvaporatorScenarioBinding(
        secondary_bc=FixedHeatRate(Q=Q_EVAP_W),
        model=model,
        discretization=disc,
        geom_scalars=dp_geom_scalars,
        dp_primary=LinearMassFluxPressureDrop(EVAP_DP_PER_G, "evap_linear_dp"),
    )

    # ------------------------------------------------------------------
    # Condenser — Q_cond is the unknown; the solver replaces its value
    # via FixedHeatRate at each inner bisection step.
    # The initial Q here is the template value; the solver overwrites it.
    # ------------------------------------------------------------------
    Q_COND_TEMPLATE_W = -800.0  # [W] template only; solver finds true Q_cond
    cond_geom = PlateGeometry(
        N_plates=10,
        chevron_angle=45.0,
        plate_spacing=0.002,
        port_dims=PortDimensions(diameter=0.015),
        A_per_plate=0.05,
    )
    cond_component = CondenserComponent(
        component_id=ComponentId(name="condenser"),
        geometry=cond_geom,
    )
    cond_scenario = CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=Q_COND_TEMPLATE_W),
        model=model,
        discretization=disc,
        geom_scalars=dp_geom_scalars,
        dp_primary=LinearMassFluxPressureDrop(COND_DP_PER_G, "cond_linear_dp"),
    )

    # ------------------------------------------------------------------
    # Pump-head law — explicit linear curve.
    #   ΔP_pump(mdot) = HEAD_PA - SLOPE_PA_S_KG * mdot
    # ------------------------------------------------------------------
    HEAD_PA = 5_625.0  # [Pa] pump head at zero flow
    SLOPE_PA_S_KG = 100_000.0  # [Pa·s/kg] head slope with mdot
    pump_curve = PumpHeadCurve(head_Pa=HEAD_PA, slope_Pa_s_kg=SLOPE_PA_S_KG)

    # ------------------------------------------------------------------
    # Brackets for the two unknowns.
    #
    # Q_cond bracket — must enclose the energy root Q_cond* = -Q_evap = -200 W:
    #   r(-500) = (-500 + 200)/mdot < 0  for any mdot > 0
    #   r(0)    = (0    + 200)/mdot > 0  for any mdot > 0
    #   → sign change confirmed; bracket encloses -200 W.
    #
    # mdot bracket — must enclose the pressure root mdot* = 0.05 kg/s:
    #   r(0.01) = 5625 - 112500*0.01 = +4500 Pa  (> 0)
    #   r(0.50) = 5625 - 112500*0.50 = -50625 Pa (< 0)
    #   → sign change confirmed; bracket encloses 0.05 kg/s.
    # ------------------------------------------------------------------
    Q_COND_BOUNDS = (-500.0, 0.0)  # [W]    inner bracket for Q_cond
    MDOT_BOUNDS = (0.01, 0.50)  # [kg/s] outer bracket for mdot

    # ------------------------------------------------------------------
    # Coupled closure case — fully specified; no hidden defaults.
    # ------------------------------------------------------------------
    case = MinimalCoupledClosureCase(
        reference_state=reference_state,
        pump_head_curve=pump_curve,
        evap_component=evap_component,
        evap_scenario=evap_scenario,
        evap_flow_area=EVAP_FLOW_AREA_M2,
        cond_component=cond_component,
        cond_scenario=cond_scenario,
        cond_flow_area=COND_FLOW_AREA_M2,
        q_cond_bounds=Q_COND_BOUNDS,
        mdot_bounds=MDOT_BOUNDS,
    )

    # ------------------------------------------------------------------
    # Solver configuration — explicit tolerances and scales.
    # ------------------------------------------------------------------
    config = CoupledClosureConfig(
        energy_tolerance=1e-6,  # [J/kg]  inner energy bisection stop
        pressure_tolerance=0.01,  # [Pa]    outer pressure bisection stop
        energy_scale=1000.0,  # [J/kg]  for ResidualVector scaled norm
        pressure_scale=100.0,  # [Pa]    for ResidualVector scaled norm
        inner_max_iter=60,  # inner bisection step limit
        outer_max_iter=60,  # outer bisection step limit
    )

    # ------------------------------------------------------------------
    # Solve.
    # ------------------------------------------------------------------
    result = solve_minimal_coupled_closure(case, config)

    # ------------------------------------------------------------------
    # Results — all diagnostics explicit; nothing hidden.
    # ------------------------------------------------------------------
    print("=== Minimal Coupled Fixed-Architecture Closure (Phase 13D) ===")
    print()
    print("  Architecture: reference -> evaporator -> condenser")
    print("  Solver: nested scalar bisection (Option A)")
    print("    Outer: bisect primary_mdot for pressure residual = 0")
    print("    Inner: bisect Q_cond for energy residual = 0 at each outer step")
    print()
    print(f"  Reference state: P={REFERENCE_P_PA:.0f} Pa,  h={result.h_reference:.1f} J/kg")
    print()
    print("  Solved unknowns:")
    print(
        f"    primary_mdot  = {result.solved_primary_mdot:.6f} kg/s  "
        f"(analytical: {0.05:.6f} kg/s)"
    )
    print(
        f"    Q_cond        = {result.solved_q_cond:+.4f} W  " f"(analytical: {-Q_EVAP_W:+.4f} W)"
    )
    print()
    print("  Residuals at solution:")
    print(
        f"    energy_residual   = {result.energy_residual:+.4e} J/kg  "
        f"[tolerance: {config.energy_tolerance:.0e} J/kg]"
    )
    print(
        f"    pressure_residual = {result.pressure_residual:+.4e} Pa  "
        f"[tolerance: {config.pressure_tolerance:.2f} Pa]"
    )
    print()
    print("  ResidualVector (scaled convergence diagnostics):")
    print(
        f"    max_abs_scaled = {result.max_abs_scaled:.4e}  "
        f"(L-inf norm of [energy/scale, pressure/scale])"
    )
    print(f"    l2_scaled      = {result.residual_vector.l2_scaled():.4e}")
    print(f"    is_converged(1e-3) = {result.residual_vector.is_converged(1e-3)}")
    print()
    print("  Pressure balance:")
    print(f"    pump_head  = {result.pump_head:.4f} Pa")
    print(f"    dP_evap    = {result.dP_evap:.4f} Pa")
    print(f"    dP_cond    = {result.dP_cond:.4f} Pa")
    print(
        f"    dP_total   = {result.dP_total:.4f} Pa  "
        f"(= dP_evap + dP_cond = {result.dP_evap + result.dP_cond:.4f} Pa)"
    )
    print()
    print("  Energy balance:")
    print(f"    h_reference     = {result.h_reference:.2f} J/kg")
    print(f"    h_after_evap    = {result.state_after_evap.h:.2f} J/kg")
    print(f"    h_return        = {result.h_return:.2f} J/kg")
    print(f"    net dh (return - ref) = {result.h_return - result.h_reference:+.2e} J/kg")
    print()
    print("  Solver diagnostics:")
    print(f"    converged              = {result.converged}")
    print(f"    outer_iterations       = {result.outer_iterations}")
    print(f"    inner_iterations_total = {result.inner_iterations_total}")
    print(f"    inner_evaluations_total = {result.inner_evaluations_total}")
    print()
    if result.warnings:
        print(f"  Warnings: {result.warnings}")
    else:
        print("  Warnings: none")
    print()
    print("NOTE: Phase 13D - fixed architecture; NOT a generic network solver.")
    print("      Coupled closure solves BOTH Q_cond and primary_mdot simultaneously.")
    print("      Architecture is fixed at one evaporator + one condenser.")
    print("      No arbitrary topology changes, no parallel evaporators.")
    print("      No valves, manifolds, recuperator, or pre/post-heaters.")
    print("      Validation against experimental data: deferred.")
    print("      This is not a validated physical model.")
    print("      Next: Phase 13E (network graph foundation) and 13F (configurable solver).")
