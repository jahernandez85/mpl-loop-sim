"""Fixed-heat-rate HX evaluation example.

Demonstrates how to create a FluidState, configure an EvaporatorComponent with
a FixedHeatRate boundary condition, and evaluate it to obtain heat transfer Q,
outlet enthalpy, and pressure drop.

What this is
------------
- A standalone runnable example using only public package APIs.
- All inputs are explicit named constants; no property lookup occurs.

What this is NOT
----------------
- Not a validated physical design.
- Not a full-loop convergence.
- Not a network solver.
- All values are explicit inputs; no automatic property lookup.
- No CoolProp call occurs anywhere in this path.

Imports used
------------
- mpl_sim.core     : FluidState, PureFluid
- mpl_sim.geometry : MicrochannelGeometry, FinGeometry
- mpl_sim.discretization : DiscretizationSpec, DiscretizationMode
- mpl_sim.hx_models : EpsilonNTUModel, FixedHeatRate
- mpl_sim.components : ComponentId, EvaporatorComponent, EvaporatorScenarioBinding
"""

from __future__ import annotations

from mpl_sim.components import (
    ComponentId,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import FinGeometry, MicrochannelGeometry
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate, HXSolveResult

# ---------------------------------------------------------------------------
# Explicit inputs — all values are named constants; nothing is inferred.
# ---------------------------------------------------------------------------

# Fluid identity (no CoolProp call; identity is a label only in this path).
FLUID = PureFluid(name="R134a")

# Primary loop inlet state: pressure and specific enthalpy explicitly supplied.
#   P = 600 kPa  (example operating pressure)
#   h = 220 kJ/kg (example subcooled / two-phase enthalpy; not looked up)
INLET_P_PA = 600_000.0  # [Pa]
INLET_H_JKG = 220_000.0  # [J/kg]

# Primary mass flow rate [kg/s].
PRIMARY_MDOT = 0.04  # [kg/s]

# Prescribed heat input to the primary side [W].
Q_FIXED_W = 750.0  # [W]; positive = primary gains heat (evaporator sign)

# ---------------------------------------------------------------------------
# Geometry — explicit; inert storage only, no physics computed here.
# ---------------------------------------------------------------------------

evap_geom = MicrochannelGeometry(
    N_channels=16,
    D_h_channel=0.0008,  # hydraulic diameter [m]
    fin_geometry=FinGeometry(
        fin_pitch=400.0,  # fins per metre
        fin_height=0.008,  # [m]
        fin_thickness=0.00015,  # [m]
    ),
    A_heated=0.04,  # heated area [m²]
    wall_mass=0.15,  # [kg]
    wall_material="aluminium",
)

# ---------------------------------------------------------------------------
# Component assembly — no registry, no network, no solver.
# ---------------------------------------------------------------------------

component = EvaporatorComponent(
    component_id=ComponentId(name="evap_fixed_q"),
    geometry=evap_geom,
)

# HX model strategy: lumped ε-NTU — stateless, no hidden defaults.
model = EpsilonNTUModel()
disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

# Scenario binding: FixedHeatRate boundary condition.
# No HTC or DP correlations are required for FixedHeatRate.
scenario = EvaporatorScenarioBinding(
    secondary_bc=FixedHeatRate(Q=Q_FIXED_W),
    model=model,
    discretization=disc,
)

# ---------------------------------------------------------------------------
# Evaluation — one explicit forward pass through the evaporator.
# ---------------------------------------------------------------------------


def evaluate_example() -> HXSolveResult:
    """Run one deterministic fixed-heat-rate evaporator evaluation."""
    inlet_state = FluidState(P=INLET_P_PA, h=INLET_H_JKG, identity=FLUID)
    return component.evaluate_scenario(
        primary_state_in=inlet_state,
        primary_mdot=PRIMARY_MDOT,
        scenario=scenario,
    )


# ---------------------------------------------------------------------------
# Results — all diagnostics are explicit.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = evaluate_example()
    print("=== Fixed-Heat-Rate HX Example ===")
    print()
    print(f"  Fluid:              {FLUID.name}")
    print(f"  Inlet P:            {INLET_P_PA / 1e3:.1f} kPa")
    print(f"  Inlet h:            {INLET_H_JKG / 1e3:.1f} kJ/kg")
    print(f"  Primary mdot:       {PRIMARY_MDOT} kg/s")
    print(f"  Prescribed Q:       {Q_FIXED_W:+.1f} W")
    print()
    print(f"  Q (result):         {result.Q:+.1f} W")
    print(f"  h_out:              {result.primary_state_out.h / 1e3:.3f} kJ/kg")
    print(f"  dh (Q/mdot):        {result.Q / PRIMARY_MDOT:+.3f} J/kg")
    print(f"  dP_primary:         {result.dP_primary:.2f} Pa")
    print()
    print("NOTE: Not a validated physical design.")
    print("      All values are explicit inputs; no property lookup occurs.")
