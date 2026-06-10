"""
pyp2pl.system.loop
==================
Loop — the main user-facing class for P2PL steady-state simulation.

Usage
-----
    from pyp2pl.system.loop import Loop
    from pyp2pl.components import (
        Pump, Preheater, MicrochannelEvaporator,
        FlatPlateCondenser, Reservoir
    )

    # 1. Define components
    pump = Pump(fluid='R134a', eta=0.8, mode='ideal')
    preh = Preheater(fluid='R134a', mode='target_sat')
    evap = MicrochannelEvaporator(fluid='R134a', q_flux=10e4)
    cond = FlatPlateCondenser(fluid='R134a', T_coolant_in=278.15)
    res  = Reservoir(fluid='R134a')

    # 2. Assemble loop  (order = flow direction, pump first)
    loop = Loop(fluid='R134a', components=[pump, preh, evap, cond, res])

    # 3. Solve
    state = loop.solve(T_coolant=278.15, verbose=True)

    # 4. Results
    print(state.summary())
    state.plot_Ph()
    state.plot_loop()
    df = state.to_dataframe()

Topology rule
-------------
Components are listed in **flow order**, starting from the pump outlet.
The loop is automatically closed: the last component's outlet feeds back
into the pump inlet.

The accumulator can be placed at any index — this is the key feature for
the accumulator-position study:

    # Accumulator UPSTREAM of evaporator (Kokate reference)
    loop1 = Loop('R134a', [pump, preh, acc, evap, cond, res])

    # Accumulator DOWNSTREAM of evaporator
    loop2 = Loop('R134a', [pump, preh, evap, acc, cond, res])
"""

from typing import List, Optional

from pyp2pl.system.solver  import solve_steady_state
from pyp2pl.system.results import LoopState
from pyp2pl.system.node    import Node


class Loop:
    """
    Pumped two-phase loop — assembles components and runs the solver.

    Parameters
    ----------
    fluid      : str   CoolProp fluid name (e.g. 'R134a', 'R1234yf').
    components : list  Ordered list of BaseComponent objects in flow direction.
                       Must include exactly one Pump component.

    Example
    -------
    See module docstring above.
    """

    def __init__(self, fluid: str, components: list):
        self.fluid      = fluid
        self.components = components
        self._validate()

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(
        self,
        T_coolant:     float,
        chi_d:         float           = 0.8,
        dT_approach:   float           = 15.0,
        T_sat_target:  Optional[float] = None,
        P_sys_override: Optional[float] = None,
        verbose:       bool            = False,
    ) -> LoopState:
        """
        Find the steady-state operating point of the loop.

        Parameters
        ----------
        T_coolant    : K    Condenser coolant inlet temperature.
        chi_d        : float Desired flow ratio m_dot/m_sat  (Kokate: 0.8).
        dT_approach  : K    Condensation approach temperature above T_coolant.
                            T_sat = T_coolant + dT_approach  (default 15 K).
                            Calibrated: 5°C + 15 K = 20°C → P=572 kPa (Kokate).
        T_sat_target : K    Override T_sat directly (ignores dT_approach).
        P_sys_override: Pa  Override system pressure directly.
        verbose      : bool Print solution details.

        Returns
        -------
        LoopState — complete steady-state solution.
        """
        sol = solve_steady_state(
            components     = self.components,
            fluid          = self.fluid,
            T_coolant      = T_coolant,
            chi_d          = chi_d,
            dT_approach    = dT_approach,
            T_sat_target   = T_sat_target,
            P_sys_override = P_sys_override,
            verbose        = verbose,
        )

        # Add pump_inlet node at the front (= last node, loop closure)
        nodes = sol['nodes']
        if nodes:
            pump_inlet = Node(
                P     = nodes[-1].P,
                h     = nodes[-1].h,
                m_dot = sol['m_dot'],
                fluid = self.fluid,
                label = 'pump_inlet',
            )
            all_nodes = [pump_inlet] + nodes
        else:
            all_nodes = []

        state = LoopState(
            nodes      = all_nodes,
            components = self.components,
            results    = sol['results'],
            converged  = sol['converged'],
            iterations = sol['iterations'],
            residual   = sol['residual'],
            m_dot      = sol['m_dot'],
            fluid      = self.fluid,
            extra      = {k: v for k, v in sol.items()
                          if k not in ('nodes', 'results', 'converged',
                                       'iterations', 'residual', 'm_dot')},
        )

        if not state.converged:
            err = sol.get('error', 'Unknown solver error.')
            print(f"\n  [Loop.solve] WARNING: Solver did not converge.\n  {err}\n"
                  f"  Try: wider m_dot_bounds, different P_init, or verbose=True.\n")

        return state

    # ------------------------------------------------------------------
    # Parametric sweep utility
    # ------------------------------------------------------------------

    def sweep(
        self,
        param:        str,
        values:       list,
        T_coolant:    float,
        sweep_target: str   = 'auto',
        verbose:      bool  = False,
    ) -> list:
        """
        Run solve() for a range of values of one parameter.

        Parameters
        ----------
        param   : str   Parameter to vary. Supported:
                        'q_flux'       — evaporator heat flux [W/m²]
                        'T_coolant'    — condenser coolant inlet temperature [K]
                        'm_dot'        — fix mass flow rate (overrides solver)
                        'charge_ratio' — reservoir charge ratio [-]
        values  : list  Values to sweep over.
        T_coolant : K   Baseline coolant temperature (overridden if param='T_coolant').
        verbose : bool

        Returns
        -------
        list of LoopState — one per value in `values`.

        Example
        -------
        >>> import numpy as np
        >>> results = loop.sweep('q_flux', np.linspace(5e4, 20e4, 10), T_coolant=278.15)
        >>> for r in results:
        ...     print(r.extra.get('param_value'), r._t_wall_max())
        """
        states = []
        for val in values:
            self._set_param(param, val)
            T_cl = val if param == 'T_coolant' else T_coolant
            state = self.solve(T_coolant=T_cl, verbose=verbose)
            state.extra['param_name']  = param
            state.extra['param_value'] = val
            states.append(state)
        return states

    def sweep_to_dataframe(self, states: list, metrics: list = None):
        """
        Convert a list of LoopState objects (from sweep()) into a
        tidy pandas DataFrame.

        Parameters
        ----------
        states  : list of LoopState from sweep()
        metrics : list of metric keys to extract from component results.
                  If None, extracts a default set.

        Returns
        -------
        pandas DataFrame with one row per sweep point.
        """
        import pandas as pd

        default_metrics = [
            'q_total_W', 'HTC_avg', 'T_wall_avg_C', 'T_wall_max_C',
            'delta_P_kPa', 'x_out', 'x_in',
        ]
        metric_keys = metrics or default_metrics

        rows = []
        for state in states:
            row = {
                'param_name':  state.extra.get('param_name',  ''),
                'param_value': state.extra.get('param_value', float('nan')),
                'm_dot_gs':    state.m_dot * 1e3,
                'converged':   state.converged,
                'P_high_kPa':  state._p_high() / 1e3,
                'P_low_kPa':   state._p_low()  / 1e3,
                'T_wall_max_C':state._t_wall_max(),
                'Q_evap_W':    state._q_evap(),
                'Q_cond_W':    state._q_cond(),
                'W_pump_W':    state._w_pump(),
                'COP':         state._cop(),
            }
            # Add per-component metrics
            for comp, res in zip(state.components, state.results):
                prefix = comp.__class__.__name__[:4].lower() + '_'
                for k in metric_keys:
                    if k in res.metrics:
                        row[prefix + k] = res.metrics[k]
            rows.append(row)

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate(self):
        """Check that the component list is valid."""
        pump_count = sum(
            1 for c in self.components if 'Pump' in c.__class__.__name__
        )
        if pump_count == 0:
            raise ValueError(
                "Loop must contain exactly one Pump component."
            )
        if pump_count > 1:
            raise ValueError(
                "Loop contains more than one Pump — not supported yet."
            )
        evap_count = sum(
            1 for c in self.components if 'Evaporator' in c.__class__.__name__
        )
        if evap_count == 0:
            raise ValueError(
                "Loop must contain at least one Evaporator component."
            )

    def _set_param(self, param: str, value):
        """Update a loop parameter before each sweep point."""
        if param == 'q_flux':
            for comp in self.components:
                if 'Evaporator' in comp.__class__.__name__:
                    comp.q_flux = value
        elif param == 'T_coolant':
            for comp in self.components:
                if 'Condenser' in comp.__class__.__name__:
                    comp.T_cl_in = value
        elif param == 'charge_ratio':
            for comp in self.components:
                if 'Reservoir' in comp.__class__.__name__:
                    comp.geo.charge_ratio = value
                    comp._P_v_ref = None  # reset reference
        elif param == 'm_dot':
            pass   # handled separately in solve() via m_dot_init
        else:
            raise ValueError(
                f"Unknown sweep parameter '{param}'. "
                f"Supported: 'q_flux', 'T_coolant', 'charge_ratio'."
            )
