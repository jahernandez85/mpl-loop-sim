"""Minimal pressure closure solver example — Phase 13B.

Demonstrates the minimal fixed-architecture pressure closure using the
public Phase 13B API.  The solver finds the primary mass flow rate primary_mdot
such that the pump head matches the total loop pressure drop:

    pump_head(mdot) - dP_total(mdot) = 0   (pressure closure condition)

where:

    dP_total = dP_evap + dP_cond

Architecture: reference_state -> evaporator -> condenser.

What this demonstrates
----------------------
- One-variable pressure closure via bounded bisection.
- Explicit pump-head law via PumpHeadCurve (constant or linear curve).
- Explicit mdot bracket; sign change validated at startup.
- Pressure residual reporting: converged, iterations, pressure_residual.
- Loop pressure drop accumulation: dP_evap, dP_cond, dP_total.
- Pump head at the solution reported explicitly.
- Energy residual h_return - h_reference as a diagnostic (NOT solved).
- All HX inputs explicit; no automatic closure selection.
- No CoolProp, no PropertyBackend, no network topology assembly.

What this does NOT demonstrate
-------------------------------
- Generic network solving (deferred to Phase 13D).
- Energy closure (deferred; energy_residual is diagnostic only in Phase 13B).
- Combined pressure + energy closure (deferred to Phase 13C).
- Moving-boundary modeling (deferred).
- Automatic phase inference or quality marching (deferred).
- Parallel evaporators, valves, manifolds, or recuperator (deferred).
- Validation against experimental data (deferred to Phase 12 harness).
- Full architecture: fixed at one evaporator + one condenser + one pump law.
- This is not a validated physical model.

Usage
-----
    python examples/minimal_pressure_closure.py
"""

from __future__ import annotations

from mpl_sim.closed_loop import (
    MinimalPressureClosureCase,
    PressureClosureConfig,
    PumpHeadCurve,
    solve_minimal_pressure_closure,
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
    """Explicit deterministic example law: dP = coefficient * G [Pa]."""

    def __init__(self, coefficient: float, name: str) -> None:
        self.coefficient = coefficient
        self.name = name
        self._source = SourceRef(citation="Phase 13B deterministic acceptance law")
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
            value=(self.coefficient * inp.G,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name=self.name, correlation_version="1"),
                violated=(),
            ),
            metadata=ClosureMetadata(name=self.name, version="1", source=self._source),
        )


if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Explicit example inputs — no hidden defaults, no property lookup.
    # All scalars are named constants; geometry is explicit.
    # ------------------------------------------------------------------

    # Fluid identity (no CoolProp call in this path).
    FLUID = PureFluid(name="R134a")

    # Primary loop reference / inlet state.
    REFERENCE_P_PA = 800_000.0  # [Pa]
    REFERENCE_H_JKG = 250_000.0  # [J/kg]
    reference_state = FluidState(P=REFERENCE_P_PA, h=REFERENCE_H_JKG, identity=FLUID)

    # HX model strategy: lumped ε-NTU (stateless, no registry lookup).
    model = EpsilonNTUModel()

    # Discretization: one lumped control volume.
    disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

    # ------------------------------------------------------------------
    # Evaporator — explicit geometry and scenario.
    # FixedHeatRate BC: primary fluid gains Q_EVAP [W].
    # No HTC or DP correlations needed for this BC.
    # Primary pressure drop is supplied by an explicit deterministic closure.
    # ------------------------------------------------------------------
    Q_EVAP_W = 1_000.0  # [W] prescribed heat input to primary side
    EVAP_FLOW_AREA_M2 = 0.01
    EVAP_DP_PER_G = 100.0
    dp_geom_scalars = {
        "G": 1.0,  # replaced from trial mdot / flow area by the pressure solver
        "D_h": 0.001,
        "L_cell": 1.0,
        "rho": 1000.0,
        "mu": 0.001,
        "roughness": 0.0,
    }

    evap_geom = MicrochannelGeometry(
        N_channels=20,
        D_h_channel=0.001,  # [m]
        fin_geometry=FinGeometry(
            fin_pitch=500.0,  # [1/m]
            fin_height=0.010,  # [m]
            fin_thickness=0.0002,  # [m]
        ),
        A_heated=0.05,  # [m²]
        wall_mass=0.20,  # [kg]
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
    # Condenser — explicit geometry and scenario.
    # FixedHeatRate BC: primary fluid rejects Q_COND [W].
    # Primary pressure drop is supplied by an explicit deterministic closure.
    # Note: Q_EVAP + Q_COND != 0; loop is NOT energy-balanced.
    # The energy_residual in the result will be non-zero (diagnostic).
    # ------------------------------------------------------------------
    Q_COND_W = -800.0  # [W] prescribed heat rejection from primary side
    COND_FLOW_AREA_M2 = 0.02
    COND_DP_PER_G = 50.0

    cond_geom = PlateGeometry(
        N_plates=10,
        chevron_angle=45.0,  # [deg]
        plate_spacing=0.002,  # [m]
        port_dims=PortDimensions(diameter=0.015),  # [m]
        A_per_plate=0.05,  # [m²]
    )
    cond_component = CondenserComponent(
        component_id=ComponentId(name="condenser"),
        geometry=cond_geom,
    )
    cond_scenario = CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=Q_COND_W),
        model=model,
        discretization=disc,
        geom_scalars=dp_geom_scalars,
        dp_primary=LinearMassFluxPressureDrop(COND_DP_PER_G, "cond_linear_dp"),
    )

    # ------------------------------------------------------------------
    # Pump-head law — explicit linear curve.
    #
    #   ΔP_pump(mdot) = HEAD_PA - SLOPE_PA_S_KG * mdot
    #
    # The explicit pressure-drop laws give:
    #
    #   dP_total = 100*(mdot/0.01) + 50*(mdot/0.02)
    #             = 12500*mdot
    #   5625 - 100000*mdot - 12500*mdot = 0
    #   mdot* = 0.05 kg/s
    #
    # This gives an exact, deterministic, CoolProp-free acceptance case.
    # ------------------------------------------------------------------
    HEAD_PA = 5_625.0  # [Pa]  pump head at zero flow
    SLOPE_PA_S_KG = 100_000.0  # [Pa·s/kg]  head slope with mdot
    pump_curve = PumpHeadCurve(head_Pa=HEAD_PA, slope_Pa_s_kg=SLOPE_PA_S_KG)

    # ------------------------------------------------------------------
    # Bracket for primary_mdot [kg/s].
    #
    # With dP_total = 12500*mdot:
    #   r(lo=0.01) = 5625 - 112500*0.01 = +4500 Pa  (> 0)
    #   r(hi=0.50) = 5625 - 112500*0.50 = -50625 Pa (< 0)
    # → sign change confirmed; bracket encloses root at 0.05 kg/s.
    # ------------------------------------------------------------------
    MDOT_BOUNDS = (0.01, 0.50)  # [kg/s] explicit bracket; must enclose root

    # ------------------------------------------------------------------
    # Pressure closure case — fully specified.
    # ------------------------------------------------------------------
    case = MinimalPressureClosureCase(
        reference_state=reference_state,
        pump_head_curve=pump_curve,
        evap_component=evap_component,
        evap_scenario=evap_scenario,
        evap_flow_area=EVAP_FLOW_AREA_M2,
        cond_component=cond_component,
        cond_scenario=cond_scenario,
        cond_flow_area=COND_FLOW_AREA_M2,
        mdot_bounds=MDOT_BOUNDS,
    )

    # ------------------------------------------------------------------
    # Solver configuration — explicit, not hidden.
    # ------------------------------------------------------------------
    config = PressureClosureConfig(
        max_iter=60,  # maximum bisection steps
        tolerance=0.01,  # pressure residual convergence [Pa]
    )

    # ------------------------------------------------------------------
    # Solve.
    # ------------------------------------------------------------------
    result = solve_minimal_pressure_closure(case, config)

    # ------------------------------------------------------------------
    # Results — all diagnostics explicit; nothing hidden.
    # ------------------------------------------------------------------
    print("=== Minimal Pressure Closure Solver (Phase 13B) ===")
    print()
    print("  Architecture: reference -> evaporator -> condenser")
    print("  Solved unknown: primary_mdot [kg/s] via pump-head balance")
    print("  Solve condition: pump_head(mdot) = dP_total(mdot)  (pressure closure)")
    print("  Closure type: pressure-only (Option A); energy residual is diagnostic")
    print()
    print(f"  Reference state:    P={REFERENCE_P_PA:.0f} Pa,  h={result.h_reference:.1f} J/kg")
    print()
    print("  Pump-head law (linear curve):")
    print(f"    head_Pa           = {HEAD_PA:.1f} Pa")
    print(f"    slope_Pa_s_kg     = {SLOPE_PA_S_KG:.1f} Pa·s/kg")
    print()
    print(f"  Solved primary_mdot:  {result.solved_primary_mdot:.6f} kg/s")
    print(f"  Pump head at solution:{result.pump_head:+.4f} Pa")
    print()
    print(f"  dP_evap (diagnostic): {result.dP_evap:.4f} Pa")
    print(f"  dP_cond (diagnostic): {result.dP_cond:.4f} Pa")
    print(f"  dP_total (evap+cond): {result.dP_total:.4f} Pa")
    print()
    print(f"  Pressure residual:    {result.pressure_residual:+.4e} Pa  [near zero when converged]")
    print(f"  Converged:            {result.converged}")
    print(f"  Iterations:           {result.iterations}")
    print(f"  Evaluations:          {result.evaluations}")
    print()
    print("  Energy residual (diagnostic only, NOT solved):")
    print(f"    h_return - h_reference = {result.energy_residual:+.2f} J/kg")
    print(f"    h_reference:  {result.h_reference:.1f} J/kg")
    print(f"    h_return:     {result.h_return:.1f} J/kg")
    print(f"    (Non-zero because Q_evap={Q_EVAP_W} W, Q_cond={Q_COND_W} W — not balanced)")
    print()
    if result.warnings:
        print(f"  Warnings: {result.warnings}")
    else:
        print("  Warnings: none")
    print()
    print("NOTE: Phase 13B — fixed architecture; not a generic network solver.")
    print("      Pressure closure solves mdot, not Q_cond.  Energy balance is")
    print("      diagnostic only (Option A).  Combined pressure + energy closure")
    print("      is deferred to Phase 13C.")
    print("      Parallel evaporators, valves, manifolds, recuperator: all deferred.")
    print("      Validation against experimental data: deferred to Phase 12 harness.")
    print("      This is not a validated physical model.")
