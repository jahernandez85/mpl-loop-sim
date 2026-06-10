"""
pyp2pl.system.results
======================
LoopState — container for the steady-state solution of a P2PL loop.

Returned by Loop.solve().  Provides:
  - summary()         human-readable table of all node states
  - to_dataframe()    pandas DataFrame of nodal states + component metrics
  - plot_Ph()         pressure-enthalpy diagram
  - plot_loop()       bar charts of ΔP, ΔT, heat flows around the loop
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class LoopState:
    """
    Complete steady-state solution of a P2PL loop.

    Attributes
    ----------
    nodes       : list of Node  — fluid state at each nodal point
    components  : list          — the component objects (same order as nodes)
    results     : list of ComponentResult — output of each component.compute()
    converged   : bool          — True if the solver converged
    iterations  : int           — number of solver iterations
    residual    : float         — final pressure-balance residual [Pa]
    m_dot       : float         — system mass flow rate [kg/s]
    fluid       : str           — working fluid name
    """
    nodes:      list
    components: list
    results:    list
    converged:  bool
    iterations: int
    residual:   float
    m_dot:      float
    fluid:      str
    extra:      Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Human-readable summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        lines = []
        lines.append("=" * 75)
        lines.append(f"  PyP2PL Steady-State Solution   fluid={self.fluid}  "
                     f"ṁ={self.m_dot*1e3:.3f} g/s")
        lines.append(f"  Converged: {self.converged}   "
                     f"Iterations: {self.iterations}   "
                     f"Residual: {self.residual:.2e} Pa")
        lines.append("=" * 75)

        # Node table
        lines.append(f"\n  {'#':<3} {'Label':<22} {'P [kPa]':>9} "
                     f"{'T [°C]':>8} {'h [kJ/kg]':>10} {'x [-]':>7} "
                     f"{'Phase':<12}")
        lines.append("  " + "-" * 72)
        for i, node in enumerate(self.nodes):
            x_str = f"{node.x:7.3f}" if node.x >= 0 else "  s.ph."
            lines.append(f"  {i:<3} {node.label:<22} {node.P/1e3:>9.2f} "
                         f"{node.T_C:>8.2f} {node.h/1e3:>10.2f} "
                         f"{x_str:>7} {node.phase:<12}")

        # Component metrics
        lines.append("\n  Component performance:")
        lines.append("  " + "-" * 72)
        for comp, res in zip(self.components, self.results):
            name = comp.__class__.__name__
            lines.append(f"\n  [{name}]")
            for k, v in res.metrics.items():
                if isinstance(v, float):
                    lines.append(f"    {k:<25} = {v:.4g}")
                else:
                    lines.append(f"    {k:<25} = {v}")
            if res.warnings:
                for w in res.warnings:
                    lines.append(f"    *** WARNING: {w}")

        # System-level summary
        lines.append("\n" + "=" * 75)
        lines.append("  System summary:")
        lines.append(f"    Q_evap      = {self._q_evap()/1e0:.2f} W")
        lines.append(f"    Q_cond      = {self._q_cond()/1e0:.2f} W")
        lines.append(f"    W_pump      = {self._w_pump():.4f} W")
        lines.append(f"    COP         = {self._cop():.1f}")
        lines.append(f"    P_high      = {self._p_high()/1e3:.2f} kPa")
        lines.append(f"    P_low       = {self._p_low()/1e3:.2f} kPa")
        lines.append(f"    T_wall_max  = {self._t_wall_max():.2f} °C")
        lines.append("=" * 75)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Export to pandas DataFrame
    # ------------------------------------------------------------------

    def to_dataframe(self):
        """
        Return a pandas DataFrame with one row per node.
        Columns: label, P_kPa, T_C, h_kJ_kg, x, phase, m_dot_gs
        """
        import pandas as pd
        rows = []
        for node in self.nodes:
            rows.append({
                'label':    node.label,
                'P_kPa':    node.P / 1e3,
                'T_C':      node.T_C,
                'h_kJ_kg':  node.h / 1e3,
                'x':        node.x,
                'phase':    node.phase,
                'm_dot_gs': node.m_dot * 1e3,
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------

    def plot_Ph(self, show=True, ax=None):
        """
        Pressure-enthalpy (P-h) diagram showing the loop cycle.
        Overlays the saturation dome for the working fluid.
        """
        import numpy as np
        import matplotlib.pyplot as plt
        import CoolProp.CoolProp as CP

        if ax is None:
            fig, ax = plt.subplots(figsize=(9, 5))

        fluid = self.fluid

        # --- Saturation dome ---
        T_min = CP.PropsSI('Tmin', '', 0, '', 0, fluid) + 2
        T_crit = CP.PropsSI('Tcrit', '', 0, '', 0, fluid)
        T_arr = np.linspace(T_min, T_crit - 0.5, 200)
        h_l = [CP.PropsSI('H', 'T', T, 'Q', 0, fluid) / 1e3 for T in T_arr]
        h_v = [CP.PropsSI('H', 'T', T, 'Q', 1, fluid) / 1e3 for T in T_arr]
        P_s = [CP.PropsSI('P', 'T', T, 'Q', 0, fluid) / 1e3 for T in T_arr]
        ax.plot(h_l, P_s, 'k-',  lw=1.2, label='Sat. liquid')
        ax.plot(h_v, P_s, 'k--', lw=1.2, label='Sat. vapor')

        # --- Loop cycle points ---
        h_pts = [n.h / 1e3 for n in self.nodes]
        P_pts = [n.P / 1e3 for n in self.nodes]
        # Close the loop
        h_pts.append(h_pts[0])
        P_pts.append(P_pts[0])

        ax.plot(h_pts, P_pts, 'o-', color='#2E6DB4', lw=2,
                markersize=6, label='Cycle')

        # Label each node
        for i, node in enumerate(self.nodes):
            ax.annotate(f" {i}\n{node.label.split('_')[0]}",
                        xy=(node.h / 1e3, node.P / 1e3),
                        fontsize=8, color='#1B3A6B')

        ax.set_xlabel('Specific enthalpy h [kJ/kg]', fontsize=11)
        ax.set_ylabel('Pressure P [kPa]', fontsize=11)
        ax.set_title(f'P-h Diagram — {fluid}', fontsize=12)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

        if show:
            plt.tight_layout()
            plt.show()
        return ax

    def plot_loop(self, show=True):
        """
        Three-panel overview: pressure around loop, temperatures, heat flows.
        """
        import matplotlib.pyplot as plt
        import numpy as np

        labels = [n.label for n in self.nodes]
        P_kPa  = [n.P / 1e3 for n in self.nodes]
        T_C    = [n.T_C for n in self.nodes]
        x_vals = [n.x for n in self.nodes]

        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        fig.suptitle(f'P2PL Steady State — {self.fluid}  '
                     f'ṁ={self.m_dot*1e3:.2f} g/s', fontsize=11)

        # Panel 1: Pressure
        ax = axes[0]
        ax.plot(range(len(P_kPa)), P_kPa, 'o-', color='#2E6DB4', lw=2)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
        ax.set_ylabel('Pressure [kPa]')
        ax.set_title('Pressure profile')
        ax.grid(True, alpha=0.3)

        # Panel 2: Temperature + quality
        ax2 = axes[1]
        ax2.plot(range(len(T_C)), T_C, 'o-', color='#C0561A', lw=2, label='T [°C]')
        ax2.set_xticks(range(len(labels)))
        ax2.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
        ax2.set_ylabel('Temperature [°C]', color='#C0561A')
        ax2.tick_params(axis='y', labelcolor='#C0561A')
        ax3 = ax2.twinx()
        x_plot = [x if x >= 0 else None for x in x_vals]
        ax3.plot(range(len(x_plot)), x_plot, 's--', color='#1E6B3A',
                 lw=1.5, markersize=5, label='x [-]')
        ax3.set_ylabel('Vapor quality x [-]', color='#1E6B3A')
        ax3.set_ylim(-0.05, 1.05)
        ax3.tick_params(axis='y', labelcolor='#1E6B3A')
        ax2.set_title('Temperature & quality')
        ax2.grid(True, alpha=0.3)

        # Panel 3: Heat flows
        ax = axes[2]
        q_e = self._q_evap()
        q_c = self._q_cond()
        w_p = self._w_pump()
        bars = ax.bar(['Q_evap', 'Q_cond', 'W_pump'],
                      [q_e, q_c, w_p],
                      color=['#C0561A', '#2E6DB4', '#5A5A5A'])
        ax.set_ylabel('Power [W]')
        ax.set_title(f'Energy flows  (COP={self._cop():.1f})')
        for bar, val in zip(bars, [q_e, q_c, w_p]):
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() * 1.02,
                    f'{val:.1f} W', ha='center', fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        if show:
            plt.show()
        return fig

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _q_evap(self) -> float:
        for comp, res in zip(self.components, self.results):
            if 'MicrochannelEvaporator' in comp.__class__.__name__:
                return res.metrics.get('q_total_W', 0.0)
        return 0.0

    def _q_cond(self) -> float:
        for comp, res in zip(self.components, self.results):
            if 'Condenser' in comp.__class__.__name__:
                return res.metrics.get('q_total_W', 0.0)
        return 0.0

    def _w_pump(self) -> float:
        for comp, res in zip(self.components, self.results):
            if 'Pump' in comp.__class__.__name__:
                return res.metrics.get('W_pump_W', 0.0)
        return 0.0

    def _cop(self) -> float:
        w = self._w_pump()
        return self._q_evap() / w if w > 1e-9 else float('inf')

    def _p_high(self) -> float:
        return max(n.P for n in self.nodes)

    def _p_low(self) -> float:
        return min(n.P for n in self.nodes)

    def _t_wall_max(self) -> float:
        for comp, res in zip(self.components, self.results):
            if 'Evaporator' in comp.__class__.__name__:
                return res.metrics.get('T_wall_max_C',
                       res.metrics.get('T_wall_avg_C', float('nan')))
        return float('nan')
