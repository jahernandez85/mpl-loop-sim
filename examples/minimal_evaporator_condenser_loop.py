"""Minimal evaporator-condenser loop acceptance example — Phase 12A.

Demonstrates how to wire an EvaporatorComponent and a CondenserComponent
end-to-end using public Phase 11 APIs.  This is NOT a full network solver.
No loop convergence is attempted; net energy imbalance is reported explicitly.

What this proves
----------------
- The library can assemble and evaluate a minimal thermal loop path using
  existing Phase 11 HX components (EvaporatorComponent, CondenserComponent,
  EvaporatorScenarioBinding, CondenserScenarioBinding, EpsilonNTUModel).
- Evaporator Q > 0 heats the primary stream; h_after_evap > h_initial.
- Condenser Q < 0 cools the primary stream; h_after_cond < h_after_evap.
- Evaporator outlet state feeds directly into the condenser inlet.
- Net energy imbalance (Q_evap + Q_cond) and enthalpy drift (h_final - h_initial)
  are reported explicitly, not hidden.
- Pressure drops accumulate: dP_total = dP_evap + dP_cond.
- All HTC/DP closures are injected explicitly; no automatic selection occurs.
- No CoolProp, no PropertyBackend, no network assembly, no loop convergence.

What this does NOT prove
------------------------
- Full loop closure (net_Q may be non-zero; net_dh may be non-zero).
- Moving-boundary modeling.
- Phase inference or quality marching.
- Property lookup (FluidState carries only P, h, identity).
- Full network assembly or pressure-flow solving.
- The frozen contribute(trial, ctx) -> ComponentContribution contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mpl_sim.components import (
    ComponentId,
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.correlations import ValidityStatus
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import (
    FinGeometry,
    MicrochannelGeometry,
    PlateGeometry,
    PortDimensions,
)
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate, HXSolveResult

# ---------------------------------------------------------------------------
# MinimalLoopResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalLoopResult:
    """Structured result from a minimal evaporator-condenser loop evaluation.

    This is not a converged network solution.  net_Q and net_dh are reported
    explicitly so the caller can inspect the energy imbalance rather than
    having it suppressed.

    Fields
    ------
    evap_result   : full HXSolveResult from the evaporator evaluation
    cond_result   : full HXSolveResult from the condenser evaluation
    h_initial     : primary inlet enthalpy [J/kg]
    h_after_evap  : primary enthalpy after evaporator [J/kg]
    h_after_cond  : primary enthalpy after condenser (final) [J/kg]
    Q_evap        : evaporator heat transfer [W]; positive = primary gains heat
    Q_cond        : condenser heat transfer [W]; negative = primary rejects heat
    net_Q         : Q_evap + Q_cond [W]; non-zero means loop is not energy-closed
    net_dh        : h_after_cond - h_initial [J/kg]; non-zero means loop is open
    dP_evap       : evaporator primary pressure drop [Pa]
    dP_cond       : condenser primary pressure drop [Pa]
    dP_total      : dP_evap + dP_cond [Pa]
    warnings      : non-IN_ENVELOPE correlation verdict notes (empty when all in-envelope)
    """

    evap_result: HXSolveResult
    cond_result: HXSolveResult
    h_initial: float
    h_after_evap: float
    h_after_cond: float
    Q_evap: float
    Q_cond: float
    net_Q: float
    net_dh: float
    dP_evap: float
    dP_cond: float
    dP_total: float
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# evaluate_minimal_evaporator_condenser_loop
# ---------------------------------------------------------------------------


def evaluate_minimal_evaporator_condenser_loop(
    inlet_state: FluidState,
    primary_mdot: float,
    evap_component: EvaporatorComponent,
    evap_scenario: EvaporatorScenarioBinding,
    cond_component: CondenserComponent,
    cond_scenario: CondenserScenarioBinding,
) -> MinimalLoopResult:
    """Evaluate a minimal evaporator-condenser loop (one explicit forward pass).

    Steps
    -----
    1. Evaluate the evaporator with the supplied inlet state and mass flow.
    2. Feed the evaporator primary outlet state into the condenser as its inlet.
    3. Assemble diagnostics: net heat balance, enthalpy drift, accumulated DP.

    This is NOT a full network solver.  A single forward pass is performed; no
    loop-closure iteration is attempted.  The net energy imbalance (net_Q) and
    enthalpy drift (net_dh) are always reported in the result — never suppressed.

    Parameters
    ----------
    inlet_state    : FluidState — primary fluid inlet (P, h, identity)
    primary_mdot   : float — primary mass flow rate [kg/s]; must be finite and > 0
    evap_component : EvaporatorComponent — fully configured evaporator
    evap_scenario  : EvaporatorScenarioBinding — evaporator scenario (closures + BC)
    cond_component : CondenserComponent — fully configured condenser
    cond_scenario  : CondenserScenarioBinding — condenser scenario (closures + BC)

    Returns
    -------
    MinimalLoopResult
    """
    if not math.isfinite(primary_mdot) or primary_mdot <= 0:
        raise ValueError(
            f"evaluate_minimal_evaporator_condenser_loop: "
            f"primary_mdot must be finite and > 0; got {primary_mdot!r}"
        )

    # Step 1: Evaporator — primary fluid absorbs heat (Q_evap > 0 expected).
    evap_result = evap_component.evaluate_scenario(inlet_state, primary_mdot, evap_scenario)

    # Step 2: Condenser — evaporator outlet feeds condenser inlet directly.
    cond_inlet_state = evap_result.primary_state_out
    cond_result = cond_component.evaluate_scenario(cond_inlet_state, primary_mdot, cond_scenario)

    # Step 3: Diagnostics.
    h_initial = inlet_state.h
    h_after_evap = evap_result.primary_state_out.h
    h_after_cond = cond_result.primary_state_out.h
    Q_evap = evap_result.Q
    Q_cond = cond_result.Q
    net_Q = Q_evap + Q_cond
    net_dh = h_after_cond - h_initial
    dP_evap = evap_result.dP_primary
    dP_cond = cond_result.dP_primary
    dP_total = dP_evap + dP_cond

    warnings: list[str] = []
    for co in evap_result.verdicts + cond_result.verdicts:
        if co.verdict.status is not ValidityStatus.IN_ENVELOPE:
            note = f"{co.metadata.name}: {co.verdict.status.name}"
            if co.verdict.detail:
                note += f" — {co.verdict.detail}"
            warnings.append(note)

    return MinimalLoopResult(
        evap_result=evap_result,
        cond_result=cond_result,
        h_initial=h_initial,
        h_after_evap=h_after_evap,
        h_after_cond=h_after_cond,
        Q_evap=Q_evap,
        Q_cond=Q_cond,
        net_Q=net_Q,
        net_dh=net_dh,
        dP_evap=dP_evap,
        dP_cond=dP_cond,
        dP_total=dP_total,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Standalone example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Explicit example inputs — no hidden defaults, no property lookup.
    # All scalars are named constants; geometry is explicit.
    # ------------------------------------------------------------------

    # Fluid identity (no CoolProp call in this path).
    FLUID = PureFluid(name="R134a")

    # Primary loop inlet: explicit thermodynamic state.
    #   P = 800 kPa  (typical evaporator operating pressure)
    #   h = 250 kJ/kg (example enthalpy below saturation)
    INLET_P_PA = 800_000.0  # [Pa]
    INLET_H_JKG = 250_000.0  # [J/kg]
    inlet_state = FluidState(P=INLET_P_PA, h=INLET_H_JKG, identity=FLUID)

    # Primary mass flow rate [kg/s].
    PRIMARY_MDOT = 0.05  # [kg/s]

    # HX model strategy: lumped ε-NTU (stateless, no registry).
    model = EpsilonNTUModel()

    # Discretization: one lumped control volume.
    disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

    # ------------------------------------------------------------------
    # Evaporator — explicit geometry and scenario.
    # FixedHeatRate BC: primary fluid gains Q_EVAP [W].
    # No HTC or DP correlations injected in this minimal case.
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
        # No htc_primary, htc_secondary, or dp_primary: FixedHeatRate does not
        # require them.  Inject them explicitly when needed.
    )

    # ------------------------------------------------------------------
    # Condenser — explicit geometry and scenario.
    # FixedHeatRate BC: primary fluid rejects |Q_COND| [W].
    # Q_COND < 0 so the primary stream is cooled.
    # ------------------------------------------------------------------
    Q_COND_W = -800.0  # [W] heat removed from primary side (< 0)

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
    )

    # ------------------------------------------------------------------
    # Loop evaluation — one explicit forward pass.
    # ------------------------------------------------------------------
    result = evaluate_minimal_evaporator_condenser_loop(
        inlet_state=inlet_state,
        primary_mdot=PRIMARY_MDOT,
        evap_component=evap_component,
        evap_scenario=evap_scenario,
        cond_component=cond_component,
        cond_scenario=cond_scenario,
    )

    # ------------------------------------------------------------------
    # Results — all diagnostics are explicit; nothing is hidden.
    # ------------------------------------------------------------------
    print("=== Minimal Evaporator-Condenser Loop (Phase 12A) ===")
    print()
    print(f"  Inlet state:      P={INLET_P_PA:.0f} Pa, h={result.h_initial:.1f} J/kg")
    print(f"  primary_mdot:     {PRIMARY_MDOT} kg/s")
    print()
    print(f"  Evaporator Q:     {result.Q_evap:+.1f} W  (Q > 0 heats primary)")
    print(f"  h after evap:     {result.h_after_evap:.1f} J/kg")
    print(f"  dP evap:          {result.dP_evap:.2f} Pa")
    print()
    print(f"  Condenser Q:      {result.Q_cond:+.1f} W  (Q < 0 cools primary)")
    print(f"  h after cond:     {result.h_after_cond:.1f} J/kg")
    print(f"  dP cond:          {result.dP_cond:.2f} Pa")
    print()
    print(f"  Net Q (imbalance): {result.net_Q:+.1f} W    [not zero -- loop not closed]")
    print(f"  Net dh (drift):    {result.net_dh:+.1f} J/kg [not zero -- loop not closed]")
    print(f"  Total dP:          {result.dP_total:.2f} Pa")
    print()
    if result.warnings:
        print(f"  Warnings: {result.warnings}")
    else:
        print("  Warnings: none")
    print()
    print("NOTE: This is not a converged loop solution.  net_Q and net_dh")
    print("      are reported to surface the imbalance, not to close the loop.")
