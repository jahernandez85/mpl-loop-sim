"""Minimal closed MPL solver acceptance example — Phase 13A.

Demonstrates the first minimal closed-loop MPL energy closure using the
public Phase 13A API.  The solver finds the condenser heat removal rate
Q_cond such that the primary fluid enthalpy returns to the reference value:

    h_after_condenser - h_reference = 0  (energy closure condition)

Architecture: reference_state -> evaporator -> condenser -> return_state.

What this demonstrates
----------------------
- The first actual closed-loop solving capability in the library.
- One-variable energy closure via bounded bisection.
- Explicit residual reporting: energy_residual, converged, iteration count.
- Explicit pressure-drop accumulation (diagnostic only; no pressure closure).
- All HX inputs explicit; no automatic closure selection.
- No CoolProp, no PropertyBackend, no network topology assembly.
- No loop-convergence guessing; the bisection bracket is explicit.

What this does NOT demonstrate
-------------------------------
- Pressure closure (deferred to Phase 13B).
- Generic network solving (deferred to Phase 13D).
- Moving-boundary modeling (deferred).
- Automatic phase inference or quality marching (deferred).
- Parallel evaporators, valves, manifolds, or recuperator (deferred).
- Validation against experimental data (deferred to Phase 12 harness).
- Full architecture: fixed at one evaporator + one condenser.

Usage
-----
    python examples/minimal_closed_mpl_solver.py
"""

from __future__ import annotations

from mpl_sim.closed_loop import (
    ClosedLoopSolveConfig,
    MinimalClosedMPLCase,
    solve_minimal_closed_mpl,
)
from mpl_sim.components import (
    ComponentId,
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import (
    FinGeometry,
    MicrochannelGeometry,
    PlateGeometry,
    PortDimensions,
)
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate

if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Explicit example inputs — no hidden defaults, no property lookup.
    # All scalars are named constants; geometry is explicit.
    # ------------------------------------------------------------------

    # Fluid identity (no CoolProp call in this path).
    FLUID = PureFluid(name="R134a")

    # Primary loop reference / inlet state.
    #   P = 800 kPa  (typical MPL operating pressure)
    #   h = 250 kJ/kg (example enthalpy in the two-phase region)
    REFERENCE_P_PA = 800_000.0  # [Pa]
    REFERENCE_H_JKG = 250_000.0  # [J/kg]
    reference_state = FluidState(P=REFERENCE_P_PA, h=REFERENCE_H_JKG, identity=FLUID)

    # Primary mass flow rate [kg/s].
    PRIMARY_MDOT = 0.05  # [kg/s]

    # HX model strategy: lumped ε-NTU (stateless, no registry lookup).
    model = EpsilonNTUModel()

    # Discretization: one lumped control volume.
    disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

    # ------------------------------------------------------------------
    # Evaporator — explicit geometry and scenario.
    # FixedHeatRate BC: primary fluid gains Q_EVAP [W].
    # No HTC or DP correlations needed for this BC.
    # ------------------------------------------------------------------
    Q_EVAP_W = 1000.0  # [W] prescribed heat input to primary side

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
        # No htc_primary, htc_secondary, or dp_primary required for FixedHeatRate.
        # Inject explicit correlations when using SinkInletTempAndFlow or FixedWallTemp.
    )

    # ------------------------------------------------------------------
    # Condenser scenario template — Q will be replaced by the solver.
    # The secondary_bc MUST be FixedHeatRate; the Q value is the unknown.
    # All other fields are used unchanged at every bisection step.
    # ------------------------------------------------------------------
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
    # The placeholder Q=0 is overwritten by the solver at every step.
    cond_scenario_template = CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=0.0),
        model=model,
        discretization=disc,
    )

    # ------------------------------------------------------------------
    # Solver bracket for Q_cond [W].
    # r(lo) = (Q_evap + Q_lo) / mdot must have opposite sign to r(hi).
    # For Q_evap=1000 W, mdot=0.05 kg/s:
    #   r(lo=-5000) = (1000 - 5000) / 0.05 = -80 000 J/kg  (< 0)
    #   r(hi=    0) =  1000         / 0.05 = +20 000 J/kg  (> 0)
    # ------------------------------------------------------------------
    Q_COND_BOUNDS = (-5000.0, 0.0)  # [W] explicit bracket; must enclose root

    # ------------------------------------------------------------------
    # Closed-loop case — fully specified.
    # ------------------------------------------------------------------
    case = MinimalClosedMPLCase(
        reference_state=reference_state,
        primary_mdot=PRIMARY_MDOT,
        evap_component=evap_component,
        evap_scenario=evap_scenario,
        cond_component=cond_component,
        cond_scenario=cond_scenario_template,
        q_cond_bounds=Q_COND_BOUNDS,
    )

    # ------------------------------------------------------------------
    # Solver configuration — explicit, not hidden.
    # ------------------------------------------------------------------
    config = ClosedLoopSolveConfig(
        max_iter=60,  # maximum bisection steps
        tolerance=1e-3,  # energy residual convergence [J/kg]
    )

    # ------------------------------------------------------------------
    # Solve.
    # ------------------------------------------------------------------
    result = solve_minimal_closed_mpl(case, config)

    # ------------------------------------------------------------------
    # Results — all diagnostics explicit; nothing hidden.
    # ------------------------------------------------------------------
    print("=== Minimal Closed MPL Solver (Phase 13A) ===")
    print()
    print("  Architecture: reference -> evaporator -> condenser -> return")
    print("  Solved unknown: Q_cond [W] via FixedHeatRate BC")
    print("  Solve condition: h_return = h_reference (energy closure)")
    print()
    print(f"  Reference state:    P={REFERENCE_P_PA:.0f} Pa,  h={result.h_reference:.1f} J/kg")
    print(f"  primary_mdot:       {PRIMARY_MDOT} kg/s")
    print()
    print(f"  Evaporator Q:       {result.evap_result.Q:+.3f} W  (fixed)")
    print(f"  h after evap:       {result.h_after_evap:.3f} J/kg")
    print(f"  dP evap:            {result.evap_result.dP_primary:.4f} Pa")
    print()
    print(f"  Solved Q_cond:      {result.solved_q_cond:+.6f} W")
    print(f"  h return:           {result.h_return:.6f} J/kg")
    print(f"  dP cond:            {result.cond_result.dP_primary:.4f} Pa")
    print()
    print(f"  Energy residual:    {result.energy_residual:+.2e} J/kg")
    print(f"  Converged:          {result.converged}")
    print(f"  Iterations:         {result.iterations}")
    print()
    print(f"  net_Q (imbalance):  {result.net_Q:+.4f} W    [near-zero when converged]")
    print(f"  net_dh (drift):     {result.net_dh:+.4f} J/kg [near-zero when converged]")
    print(f"  dP total (diag):    {result.dP_total:.4f} Pa  [diagnostic; no P closure]")
    print()
    if result.warnings:
        print(f"  Warnings: {result.warnings}")
    else:
        print("  Warnings: none")
    print()
    print("NOTE: Phase 13A - fixed architecture; not a generic network solver.")
    print("      Pressure closure is NOT implemented; dP_total is diagnostic only.")
    print("      Parallel evaporators, valves, manifolds, recuperator: all deferred.")
    print("      Validation against experimental data: deferred to Phase 12 harness.")
