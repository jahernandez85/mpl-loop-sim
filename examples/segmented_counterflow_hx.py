"""Segmented counterflow HX evaluation example.

Demonstrates how to use SegmentedMarchModel with SinkInletTempAndFlow,
FlowArrangement.COUNTERFLOW, and CounterflowIterationConfig to run a
bounded fixed-point counterflow iteration.

What this is
------------
- A standalone runnable example using only public package APIs.
- Uses a 4-cell segmented march with iterated counterflow.
- Prints heat rate, outlet enthalpy, convergence flag, residual, and
  iteration count.
- All inputs are explicit named constants; no property lookup occurs.

What this is NOT
----------------
- Not a validated physical design.
- Not full-loop convergence (single component, no loop closure).
- Not a network solver.
- All values are explicit inputs; no automatic property lookup.
- No CoolProp call occurs anywhere in this path.

Imports used
------------
- mpl_sim.core         : FluidState, PureFluid
- mpl_sim.geometry     : MicrochannelGeometry, FinGeometry
- mpl_sim.discretization : DiscretizationSpec, DiscretizationMode
- mpl_sim.correlations : DittusBoelterHTC, ChurchillFrictionGradient
- mpl_sim.hx_models    : (SegmentedMarchModel, SinkInletTempAndFlow,
                          FlowArrangement, CounterflowIterationConfig,
                          PrimaryThermalMode, UAComputationMode, HXSolveRequest)
"""

from __future__ import annotations

from mpl_sim.core import FluidState, PureFluid
from mpl_sim.correlations import ChurchillFrictionGradient, DittusBoelterHTC
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import FinGeometry, MicrochannelGeometry
from mpl_sim.hx_models import (
    CounterflowIterationConfig,
    FlowArrangement,
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SegmentedMarchModel,
    SinkInletTempAndFlow,
    UAComputationMode,
)

# ---------------------------------------------------------------------------
# Explicit inputs — all values are named constants; nothing is inferred.
# ---------------------------------------------------------------------------

FLUID = PureFluid(name="R134a")

# Primary fluid inlet state.
INLET_P_PA = 500_000.0  # [Pa]
INLET_H_JKG = 200_000.0  # [J/kg]

# Primary mass flow rate [kg/s].
PRIMARY_MDOT = 0.05  # [kg/s]

# Explicit primary-side thermodynamic scalars for HTC/DP correlation input.
# These are representative values supplied by the caller; no lookup occurs.
PRIMARY_T_IN_K = 280.0  # [K] primary inlet temperature (needed for NTU march)
PRIMARY_CP_JKG_K = 1_500.0  # [J/kg/K] explicit primary specific heat

# Secondary (sink) side — enters from the opposite end in counterflow.
SECONDARY_T_IN_K = 320.0  # [K] secondary fluid inlet temperature
SECONDARY_MDOT = 0.10  # [kg/s]
SECONDARY_CP_JKG_K = 4_200.0  # [J/kg/K]

# Segmented discretization: 4 equal cells.
N_CELLS = 4
L_CELL_M = 0.05  # [m] per cell length

# Geometry scalars explicitly supplied for DittusBoelterHTC and
# ChurchillFrictionGradient.  These are caller-provided; not inferred.
GEOM_SCALARS: dict[str, float] = {
    "G": 100.0,  # mass flux [kg/m²s]
    "x": 0.3,  # vapour quality [-]; explicit, not inferred
    "D_h": 0.001,  # hydraulic diameter [m]
    "L_cell": L_CELL_M,
    "A_ht": 0.05,  # total heat transfer area [m²]
    "Re": 15_000.0,  # Reynolds number (primary side); ≥10000 for Dittus-Boelter
    "Pr": 3.0,  # Prandtl number (primary side)
    "k": 0.10,  # thermal conductivity [W/m/K]
    "n": 0.4,  # Dittus-Boelter exponent (0.4 for heating, 0.3 for cooling)
    "rho": 800.0,  # density [kg/m³]
    "mu": 1e-3,  # dynamic viscosity [Pa·s]
    "roughness": 0.0,  # smooth-wall assumption [m]
    "A_cs": 1e-5,  # cross-sectional area [m²]
}

# ---------------------------------------------------------------------------
# Geometry — explicit; inert storage only, no physics computed here.
# ---------------------------------------------------------------------------

geom = MicrochannelGeometry(
    N_channels=10,
    D_h_channel=0.001,
    fin_geometry=FinGeometry(
        fin_pitch=500.0,
        fin_height=0.010,
        fin_thickness=0.0002,
    ),
    A_heated=0.05,
    wall_mass=0.20,
    wall_material="aluminium",
)

# ---------------------------------------------------------------------------
# Model and discretization.
# ---------------------------------------------------------------------------

model = SegmentedMarchModel()
disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=N_CELLS)

# ---------------------------------------------------------------------------
# Boundary condition and counterflow iteration config.
# ---------------------------------------------------------------------------

# Secondary side enters from the opposite end (counterflow).
bc = SinkInletTempAndFlow(
    T_in=SECONDARY_T_IN_K,
    mdot_secondary=SECONDARY_MDOT,
    cp_secondary=SECONDARY_CP_JKG_K,
)

# Bounded fixed-point iteration: exit when secondary profile change < tolerance.
iteration_cfg = CounterflowIterationConfig(
    enabled=True,
    max_iter=30,
    tolerance=1e-5,
    relaxation=1.0,
)

# ---------------------------------------------------------------------------
# Solve request — explicit injection of all correlations and scalars.
# ---------------------------------------------------------------------------

inlet_state = FluidState(P=INLET_P_PA, h=INLET_H_JKG, identity=FLUID)

req = HXSolveRequest(
    primary_state_in=inlet_state,
    primary_mdot=PRIMARY_MDOT,
    secondary_bc=bc,
    geometry=geom,
    discretization=disc,
    geom_scalars=GEOM_SCALARS,
    # Explicit HTC correlations injected for both sides.
    htc_primary=DittusBoelterHTC(),
    htc_secondary=DittusBoelterHTC(),
    # Explicit DP correlation injected for the primary side.
    dp_primary=ChurchillFrictionGradient(),
    # Primary side uses finite heat capacity (not phase-change isothermal mode).
    primary_T_in=PRIMARY_T_IN_K,
    primary_cp=PRIMARY_CP_JKG_K,
    primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
    ua_computation_mode=UAComputationMode.TWO_SIDED,
    # Counterflow arrangement with iterated solver.
    flow_arrangement=FlowArrangement.COUNTERFLOW,
    counterflow_iteration=iteration_cfg,
)

# ---------------------------------------------------------------------------
# Evaluation.
# ---------------------------------------------------------------------------


def evaluate_example() -> HXSolveResult:
    """Run one deterministic segmented counterflow HX evaluation."""
    return model.solve(req)


# ---------------------------------------------------------------------------
# Results — all diagnostics are explicit.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = evaluate_example()
    print("=== Segmented Counterflow HX Example ===")
    print()
    print(f"  Fluid:              {FLUID.name}")
    print(f"  Inlet P:            {INLET_P_PA / 1e3:.1f} kPa")
    print(f"  Inlet h:            {INLET_H_JKG / 1e3:.1f} kJ/kg")
    print(f"  Primary mdot:       {PRIMARY_MDOT} kg/s")
    print(f"  Primary T_in:       {PRIMARY_T_IN_K:.1f} K")
    print(f"  Primary cp:         {PRIMARY_CP_JKG_K:.0f} J/kg/K")
    print()
    print(f"  Secondary T_in:     {SECONDARY_T_IN_K:.1f} K (enters from opposite end)")
    print(f"  Secondary mdot:     {SECONDARY_MDOT} kg/s")
    print(f"  Secondary cp:       {SECONDARY_CP_JKG_K:.0f} J/kg/K")
    print()
    print(f"  Cells (n_cells):    {N_CELLS}")
    print("  Flow arrangement:   COUNTERFLOW (iterated fixed-point)")
    print()
    print(f"  Q (result):         {result.Q:+.2f} W")
    print(f"  h_out:              {result.primary_state_out.h / 1e3:.4f} kJ/kg")
    print(f"  dP_primary:         {result.dP_primary:.4f} Pa")
    print()
    print(f"  Converged:          {result.converged}")
    print(f"  Iterations:         {result.iteration_count}")
    print(f"  Final residual:     {result.residual:.2e}")
    print()
    if result.verdicts:
        flagged = [v for v in result.verdicts if v.verdict.status.name != "IN_ENVELOPE"]
        if flagged:
            print(f"  Out-of-envelope verdicts: {len(flagged)}")
            for v in flagged:
                print(f"    {v.metadata.name}: {v.verdict.status.name}")
        else:
            print("  All correlation verdicts: IN_ENVELOPE")
    else:
        print("  Correlation verdicts: none (no injected correlations evaluated)")
    print()
    print("NOTE: Not a validated physical design.")
    print("      All values are explicit inputs; no property lookup occurs.")
    print("      This is not full-loop convergence.")
