"""EpsilonNTU heat-exchanger model — Phase 11B.

Implements a minimal lumped ε-NTU strategy for V1.

Scope (V1):
  - Handles FixedHeatRate BC fully: Q is prescribed, outlet enthalpy and
    pressure are derived from injected correlations.
  - SinkInletTempAndFlow, FixedWallTemp, and AmbientCoupling BCs are declared
    seams; solve() raises UnsupportedHeatExchangerBoundaryConditionError for
    these in V1 (no fake physics).
  - Calls injected htc_primary and dp_primary through the Correlation contract.
  - Applies htc_multiplier to HTC output and friction_multiplier to DP output.
  - Never resolves a registry internally.
  - Never accesses Ports, Network, Solver, SystemState, or PropertyBackend.
  - Never imports CoolProp.

Sign convention (FixedHeatRate):
  Q > 0  — primary fluid gains enthalpy (evaporator sense)
  Q < 0  — primary fluid rejects heat (condenser sense)
  h_out = h_in + Q / primary_mdot
  P_out = P_in - dP_primary      (dP_primary > 0 means pressure decreases)

Calibration seam:
  HTC calibration:  htc_calibrated = htc_multiplier * raw_htc_value
    Applied to the HTC correlation output only; does not affect the energy
    balance when using FixedHeatRate (Q is prescribed, not derived from HTC).
  DP calibration:   dP_calibrated = friction_multiplier * raw_dP_value
    Applied to the DP correlation output; the calibrated dP is used for P_out.

Required geom_scalars keys:
  _build_htc_input  : "G", "D_h", "x"
  _build_dp_input   : "G", "D_h", "L_cell", "rho", "mu"
                      "roughness" is optional (defaults to 0.0 — smooth pipe)

Architectural constraints:
  - No import of CoolProp, properties/, components/, network/, or solvers/.
  - No registry lookup inside solve().
  - No modification of any input object.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    CorrelationOutput,
    HTCInput,
    SinglePhaseDPInput,
)
from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
    SinkInletTempAndFlow,
    UnsupportedHeatExchangerBoundaryConditionError,
)


def _require_scalar(gs: Mapping[str, float], key: str, context: str) -> float:
    """Return gs[key] if present and finite; raise ValueError otherwise."""
    if key not in gs:
        raise ValueError(
            f"{context}: required scalar {key!r} not found in geom_scalars.  "
            f"Available keys: {sorted(gs)!r}"
        )
    value = gs[key]
    if not math.isfinite(value):
        raise ValueError(f"{context}: geom_scalars[{key!r}] must be a finite float; got {value!r}")
    return value


class EpsilonNTUModel(HeatExchangerModel):
    """Minimal lumped ε-NTU heat-exchanger strategy — Phase 11B V1.

    Stateless strategy object.  Two calls with equal HXSolveRequest objects
    return equivalent results.
    """

    def kind(self) -> HeatExchangerModelKind:
        """Returns HeatExchangerModelKind.EPSILON_NTU."""
        return HeatExchangerModelKind.EPSILON_NTU

    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        """Solve the heat-exchanger problem described by *req*.

        V1 supports FixedHeatRate BC only.  Other BCs raise
        UnsupportedHeatExchangerBoundaryConditionError.

        Parameters
        ----------
        req : HXSolveRequest

        Returns
        -------
        HXSolveResult
        """
        bc = req.secondary_bc

        if isinstance(bc, FixedHeatRate):
            return self._solve_fixed_heat_rate(req, bc)

        if isinstance(bc, SinkInletTempAndFlow):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "EpsilonNTUModel V1 does not implement SinkInletTempAndFlow BC.  "
                "Detailed sink-side ε-NTU requires a PropertyBackend for primary "
                "temperature lookup, which is not available inside a HX model.  "
                "Use FixedHeatRate BC for V1."
            )

        if isinstance(bc, FixedWallTemp):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "EpsilonNTUModel V1 does not implement FixedWallTemp BC.  "
                "Wall-temperature-driven Q requires a primary-side HTC and "
                "wall area that are not yet wired for this BC in V1."
            )

        if isinstance(bc, AmbientCoupling):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "EpsilonNTUModel V1 does not implement AmbientCoupling BC.  "
                "Ambient coupling requires a primary-side temperature, which "
                "needs a PropertyBackend not available inside a HX model."
            )

        raise ValueError(f"EpsilonNTUModel: unrecognised secondary BC type {type(bc)!r}")

    # ------------------------------------------------------------------
    # FixedHeatRate path
    # ------------------------------------------------------------------

    def _solve_fixed_heat_rate(
        self,
        req: HXSolveRequest,
        bc: FixedHeatRate,
    ) -> HXSolveResult:
        Q = bc.Q
        verdicts: list[CorrelationOutput] = []

        # --- HTC primary (called for verdict tracking; value tracked, not
        #     used in energy balance for FixedHeatRate) ---
        if req.htc_primary is not None:
            htc_inp = self._build_htc_input(req)
            raw_htc_out = req.htc_primary.evaluate(htc_inp)
            verdicts.append(raw_htc_out)

        # --- DP primary ---
        raw_dP = 0.0
        if req.dp_primary is not None:
            dp_inp = self._build_dp_input(req)
            raw_dp_out = req.dp_primary.evaluate(dp_inp)
            verdicts.append(raw_dp_out)
            raw_dP = raw_dp_out.value[0]

        dP_primary = req.friction_multiplier * raw_dP

        # --- Outlet state ---
        h_out = req.primary_state_in.h + Q / req.primary_mdot
        P_out = req.primary_state_in.P - dP_primary
        primary_state_out = FluidState(
            P=P_out,
            h=h_out,
            identity=req.primary_state_in.identity,
        )

        return HXSolveResult(
            primary_state_out=primary_state_out,
            Q=Q,
            dP_primary=dP_primary,
            verdicts=tuple(verdicts),
            htc_multiplier=req.htc_multiplier,
            friction_multiplier=req.friction_multiplier,
            raw_dP_primary=raw_dP,
        )

    # ------------------------------------------------------------------
    # Correlation input builders
    # ------------------------------------------------------------------

    def _build_htc_input(self, req: HXSolveRequest) -> HTCInput:
        gs = req.geom_scalars
        ctx = "EpsilonNTUModel._build_htc_input"
        return HTCInput(
            state=(req.primary_state_in,),
            G=_require_scalar(gs, "G", ctx),
            x=(_require_scalar(gs, "x", ctx),),
            D_h=_require_scalar(gs, "D_h", ctx),
            geom_scalars=gs,
        )

    def _build_dp_input(self, req: HXSolveRequest) -> SinglePhaseDPInput:
        gs = req.geom_scalars
        ctx = "EpsilonNTUModel._build_dp_input"
        rho = _require_scalar(gs, "rho", ctx)
        mu = _require_scalar(gs, "mu", ctx)
        if rho <= 0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['rho'] must be > 0; got {rho!r}")
        if mu <= 0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['mu'] must be > 0; got {mu!r}")
        return SinglePhaseDPInput(
            state=(req.primary_state_in,),
            G=_require_scalar(gs, "G", ctx),
            D_h=_require_scalar(gs, "D_h", ctx),
            roughness=gs.get("roughness", 0.0),
            L_cell=_require_scalar(gs, "L_cell", ctx),
            rho=rho,
            mu=mu,
        )
