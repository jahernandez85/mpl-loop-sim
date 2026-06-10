"""
pyp2pl.system.solver
=====================
Steady-state solver for the P2PL loop.

Physics basis (Kokate PhD 2024, Sec. 4.1 / Kokate 2023, Eqs. 13 & 27-30)
--------------------------------------------------------------------------
At steady state, two quantities characterise the operating point:

  m_dot  — system mass flow rate [kg/s]
  P_sys  — system pressure [Pa]  (≈ saturation pressure throughout the loop)

m_dot is determined by Kokate's control law (Eq. 13 + 27):

    m_dot = chi_d * m_sat
    m_sat = q_total / h_fg(P_sys)         [Eq. 13, simplified]

  Derivation: m_sat = alpha_e*As_e*(T_wall - T_sat)/h_fg  (Eq. 13)
  At steady state: alpha_e*As_e*(T_wall - T_sat) = q_total  (energy balance)
  Therefore: m_sat = q_total / h_fg   — no HTC needed.

P_sys is determined by the condenser operating temperature T_sat:
    T_sat = T_coolant + dT_approach
    P_sys = P_sat(T_sat)

  dT_approach is the condensation approach temperature.
  Default: 15 K  (matches Kokate's measured T_sat=20°C at T_cool=5°C).
  The user can override by specifying T_sat_target directly.

Solution procedure
------------------
  1.  Compute P_sys from T_sat = T_coolant + dT_approach.
  2.  Compute m_dot = chi_d * q_total / h_fg(P_sys).
  3.  March around the loop once to get all node states.
  4.  Pump dP = sum of all other component pressure drops.

No iteration needed — the solution is explicit given P_sys and chi_d.
"""

import numpy as np
import CoolProp.CoolProp as CP

from pyp2pl.components.base import PortState
from pyp2pl.system.node import Node


# ---------------------------------------------------------------------------
# Full loop march
# ---------------------------------------------------------------------------

def march_loop(components, m_dot, P_init, h_init, fluid):
    """
    March once around the component list.
    Returns (nodes, results).
    """
    _LABELS = {
        'Pump':                   'pump_outlet',
        'Preheater':              'preheater_outlet',
        'MicrochannelEvaporator': 'evaporator_outlet',
        'FlatPlateCondenser':     'condenser_outlet',
        'Reservoir':              'reservoir_outlet',
        'Accumulator':            'accumulator_outlet',
        'Pipe':                   'pipe_outlet',
    }
    nodes, results = [], []
    P_cur, h_cur = P_init, h_init

    for comp in components:
        inlet = PortState(P=P_cur, h=h_cur, m_dot=m_dot, fluid=fluid)
        res   = comp.compute(inlet)
        cname = comp.__class__.__name__
        label = _LABELS.get(cname, cname.lower() + '_outlet')
        node  = Node(P=res.outlet.P, h=res.outlet.h,
                     m_dot=res.outlet.m_dot, fluid=fluid, label=label)
        nodes.append(node)
        results.append(res)
        P_cur, h_cur = res.outlet.P, res.outlet.h

    return nodes, results


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def solve_steady_state(
    components:      list,
    fluid:           str,
    T_coolant:       float,
    chi_d:           float = 0.8,
    dT_approach:     float = 15.0,
    T_sat_target:    float = None,
    P_sys_override:  float = None,
    verbose:         bool  = False,
) -> dict:
    """
    Find the steady-state operating point of the P2PL loop.

    Parameters
    ----------
    components    : list  ordered BaseComponent objects, pump first
    fluid         : str   CoolProp fluid name
    T_coolant     : K     condenser coolant inlet temperature
    chi_d         : float desired flow ratio m_dot / m_sat  (Kokate: 0.8)
    dT_approach   : K     condensation approach temperature above T_coolant
                          T_sat = T_coolant + dT_approach  (default 15 K)
                          Calibrated against Kokate: 5°C + 15K = 20°C → 572 kPa
    T_sat_target  : K     override T_sat directly (overrides dT_approach)
    P_sys_override: Pa    override system pressure directly
    verbose       : bool  print solution details

    Returns
    -------
    dict: nodes, results, converged, iterations, residual, m_dot, pump_dP
    """
    # ---- Find key components ----
    pump_idx = evap_idx = None
    for i, comp in enumerate(components):
        if 'Pump'       in comp.__class__.__name__: pump_idx = i
        if 'Evaporator' in comp.__class__.__name__: evap_idx = i
    if pump_idx is None:
        raise ValueError("No Pump in component list.")
    if evap_idx is None:
        raise ValueError("No Evaporator in component list.")

    evap = components[evap_idx]

    # ---- System pressure ----
    if P_sys_override is not None:
        P_sys = P_sys_override
    elif T_sat_target is not None:
        P_sys = CP.PropsSI('P', 'T', T_sat_target, 'Q', 0, fluid)
    else:
        T_sat = T_coolant + dT_approach
        P_sys = CP.PropsSI('P', 'T', T_sat, 'Q', 0, fluid)

    T_sat_sol = CP.PropsSI('T', 'P', P_sys, 'Q', 0, fluid)
    h_fg      = (CP.PropsSI('H', 'P', P_sys, 'Q', 1, fluid) -
                 CP.PropsSI('H', 'P', P_sys, 'Q', 0, fluid))
    h_l       = CP.PropsSI('H', 'P', P_sys, 'Q', 0, fluid)

    # ---- m_dot from control law (Kokate Eq. 13 + 27) ----
    # m_sat = q_total / h_fg   (exact: follows from wall energy balance)
    # m_dot = chi_d * m_sat
    q_total = evap.q_flux * evap.geo.As_total
    m_sat   = q_total / h_fg
    m_dot   = chi_d * m_sat

    if verbose:
        print(f"  P_sys   = {P_sys/1e3:.1f} kPa  "
              f"T_sat = {T_sat_sol-273.15:.2f}°C")
        print(f"  q_total = {q_total:.1f} W  "
              f"h_fg = {h_fg/1e3:.2f} kJ/kg")
        print(f"  m_sat   = {m_sat*1e3:.3f} g/s  "
              f"m_dot = {m_dot*1e3:.3f} g/s  "
              f"(chi_d={chi_d})")

    # ---- Initial enthalpy: subcooled liquid ~2K below T_sat ----
    h_init = CP.PropsSI('H', 'T', T_sat_sol - 2.0, 'P', P_sys, fluid)

    # ---- Set reservoir reference ----
    for comp in components:
        if 'Reservoir' in comp.__class__.__name__:
            if comp._P_v_ref is None:
                comp.set_reference_pressure(P_sys)

    # ---- Compute pump dP (sum of all other component drops) ----
    pump = components[pump_idx]
    total_dP = _total_dp(components, m_dot, P_sys, h_init, fluid, pump_idx)
    pump.delta_P_ideal = max(total_dP, 0.0)

    # ---- Final march ----
    nodes, results = march_loop(components, m_dot, P_sys, h_init, fluid)

    # Loop closure residual
    final_res = abs(nodes[-1].P - P_sys) if nodes else float('nan')

    if verbose:
        print(f"  pump_dP = {pump.delta_P_ideal/1e3:.3f} kPa  "
              f"loop_residual = {final_res:.2f} Pa")

    return {
        'nodes':      nodes,
        'results':    results,
        'converged':  True,   # explicit solution — always converges
        'iterations': 1,
        'residual':   final_res,
        'm_dot':      m_dot,
        'pump_dP':    pump.delta_P_ideal,
        'chi_d':      chi_d,
        'P_system':   P_sys,
        'T_sat_C':    T_sat_sol - 273.15,
        'q_total_W':  q_total,
        'm_sat_gs':   m_sat * 1e3,
    }


def _total_dp(components, m_dot, P_init, h_init, fluid, pump_idx):
    """Compute total loop pressure drop (sum over all components except pump)."""
    total_dP = 0.0
    P_cur, h_cur = P_init, h_init
    for i, comp in enumerate(components):
        if i == pump_idx:
            continue
        inlet = PortState(P=P_cur, h=h_cur, m_dot=m_dot, fluid=fluid)
        res   = comp.compute(inlet)
        total_dP += max(0.0, inlet.P - res.outlet.P)
        P_cur, h_cur = res.outlet.P, res.outlet.h
    return total_dP
