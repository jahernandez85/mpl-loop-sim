"""LMTDModel heat-exchanger model — Phase 11E.

Implements a minimal lumped LMTD-foundation strategy.

Scope (Phase 11E):
  - Handles FixedWallTemp BC: lumped wall-temperature conductance path;
    requires primary_T_in, A_ht, and htc_primary from the caller.
    UA = htc_multiplier * h_primary * A_ht
    Q  = UA * (T_wall - primary_T_in)
  - Handles AmbientCoupling BC: UA_ambient drives Q directly; primary_T_in
    required; no HTC correlation needed for the energy balance.
    Q = UA_ambient * (T_ambient - primary_T_in)
  - Calls injected htc_primary (FixedWallTemp only) and dp_primary through
    the Correlation contract.
  - Applies htc_multiplier at the UA seam (FixedWallTemp only).
  - Does NOT apply htc_multiplier to UA_ambient (AmbientCoupling).
  - Applies friction_multiplier to DP output only.
  - Never resolves a registry internally.
  - Never accesses Ports, Network, Solver, SystemState, or PropertyBackend.
  - Never imports CoolProp.

Unsupported BCs (Phase 11E):
  - SinkInletTempAndFlow: raises UnsupportedHeatExchangerBoundaryConditionError.
  - FixedHeatRate: raises UnsupportedHeatExchangerBoundaryConditionError.

LMTD foundation note:
  The FixedWallTemp path uses a single-ended lumped conductance formula
  (UA * ΔT) rather than a true two-ended logarithmic-mean temperature
  difference, because the primary outlet temperature is not known a priori.
  This is an intentional Phase 11E seam — full two-stream LMTD solving
  (with SinkInletTempAndFlow) is deferred to a later phase.

Sign convention (both paths):
  Q > 0  — primary fluid gains enthalpy (evaporator/heating sense)
  Q < 0  — primary fluid rejects heat (condenser/cooling sense)
  h_out = h_in + Q / primary_mdot
  P_out = P_in - dP_primary      (dP_primary > 0 means pressure decreases)

Calibration seam:
  HTC calibration:  h_eff = htc_multiplier * raw_htc_value  (FixedWallTemp only)
  DP calibration:   dP_calibrated = friction_multiplier * raw_dP_value

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
    TwoPhaseDPInput,
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


class LMTDModel(HeatExchangerModel):
    """Minimal lumped LMTD-foundation heat-exchanger strategy — Phase 11E.

    Stateless strategy object.  Two calls with equal HXSolveRequest objects
    return equivalent results.

    Supported BCs: FixedWallTemp, AmbientCoupling.
    Unsupported:   SinkInletTempAndFlow, FixedHeatRate.
    """

    def kind(self) -> HeatExchangerModelKind:
        """Returns HeatExchangerModelKind.LMTD."""
        return HeatExchangerModelKind.LMTD

    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        """Solve the heat-exchanger problem described by *req*.

        Supported secondary BCs: FixedWallTemp, AmbientCoupling.

        Parameters
        ----------
        req : HXSolveRequest

        Returns
        -------
        HXSolveResult

        Raises
        ------
        UnsupportedHeatExchangerBoundaryConditionError
            For SinkInletTempAndFlow and FixedHeatRate BCs.
        """
        bc = req.secondary_bc

        if isinstance(bc, FixedWallTemp):
            return self._solve_fixed_wall_temp(req, bc)

        if isinstance(bc, AmbientCoupling):
            return self._solve_ambient_coupling(req, bc)

        if isinstance(bc, SinkInletTempAndFlow):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "LMTDModel does not support SinkInletTempAndFlow in Phase 11E.  "
                "Full two-stream LMTD solving with known secondary inlet conditions "
                "requires primary outlet temperature iteration and is deferred."
            )

        if isinstance(bc, FixedHeatRate):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "LMTDModel does not support FixedHeatRate in Phase 11E.  "
                "When Q is prescribed, LMTD is unnecessary; use EpsilonNTUModel "
                "or FixedHeatRate passthrough instead."
            )

        raise UnsupportedHeatExchangerBoundaryConditionError(
            f"LMTDModel: unrecognised secondary BC type {type(bc)!r}"
        )

    # ------------------------------------------------------------------
    # FixedWallTemp path
    # ------------------------------------------------------------------

    def _solve_fixed_wall_temp(
        self,
        req: HXSolveRequest,
        bc: FixedWallTemp,
    ) -> HXSolveResult:
        ctx = "LMTDModel._solve_fixed_wall_temp"

        if req.primary_T_in is None:
            raise ValueError(
                "LMTDModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is FixedWallTemp.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )
        primary_T_in = req.primary_T_in

        A_ht = _require_scalar(req.geom_scalars, "A_ht", ctx)
        if A_ht <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['A_ht'] must be > 0; got {A_ht!r}")

        if req.htc_primary is None:
            raise ValueError(
                "LMTDModel: htc_primary is required when secondary_bc is FixedWallTemp.  "
                "The primary-side HTC is needed to compute UA = h_primary * A_ht."
            )

        verdicts: list[CorrelationOutput] = []

        # UA = htc_multiplier * h_primary_raw * A_ht  (calibration seam)
        htc_inp = self._build_htc_input(req)
        raw_htc_out = req.htc_primary.evaluate(htc_inp)
        verdicts.append(raw_htc_out)
        h_p_raw = raw_htc_out.value[0]
        if not math.isfinite(h_p_raw) or h_p_raw <= 0.0:
            raise ValueError(
                f"LMTDModel: primary HTC output must be finite and > 0 "
                f"(FixedWallTemp); got {h_p_raw!r}"
            )

        h_p_eff = req.htc_multiplier * h_p_raw
        UA = h_p_eff * A_ht

        # Q > 0: primary gains heat (T_wall > T_primary_in)
        # Q < 0: primary rejects heat (T_wall < T_primary_in)
        Q = UA * (bc.T_wall - primary_T_in)

        h_out = req.primary_state_in.h + Q / req.primary_mdot

        raw_dP = 0.0
        if req.dp_primary is not None:
            if req.dp_primary_is_two_phase:
                dp_inp = self._build_two_phase_dp_input(req)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP_gradient = raw_dp_out.value[0]
                if not math.isfinite(raw_dP_gradient):
                    raise ValueError(
                        f"LMTDModel: two-phase DP gradient must be finite; "
                        f"got {raw_dP_gradient!r}"
                    )
                raw_dP = raw_dP_gradient * dp_inp.L_cell
            else:
                dp_inp = self._build_dp_input(req)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP = raw_dp_out.value[0]
                if not math.isfinite(raw_dP):
                    raise ValueError(
                        f"LMTDModel: DP correlation output must be finite; got {raw_dP!r}"
                    )

        dP_primary = req.friction_multiplier * raw_dP
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
    # AmbientCoupling path
    # ------------------------------------------------------------------

    def _solve_ambient_coupling(
        self,
        req: HXSolveRequest,
        bc: AmbientCoupling,
    ) -> HXSolveResult:
        if req.primary_T_in is None:
            raise ValueError(
                "LMTDModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is AmbientCoupling.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )
        primary_T_in = req.primary_T_in

        verdicts: list[CorrelationOutput] = []

        # UA_ambient is the explicit overall conductance supplied by the caller.
        # htc_multiplier is NOT applied to UA_ambient — there is no primary-side
        # HTC correlation here, and UA_ambient is already the calibrated physical
        # input rather than a raw correlation output.
        # Q > 0: ambient hotter than primary (primary absorbs heat)
        # Q < 0: ambient colder than primary (primary rejects heat)
        Q = bc.UA_ambient * (bc.T_ambient - primary_T_in)

        h_out = req.primary_state_in.h + Q / req.primary_mdot

        raw_dP = 0.0
        if req.dp_primary is not None:
            if req.dp_primary_is_two_phase:
                dp_inp = self._build_two_phase_dp_input(req)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP_gradient = raw_dp_out.value[0]
                if not math.isfinite(raw_dP_gradient):
                    raise ValueError(
                        f"LMTDModel: two-phase DP gradient must be finite; "
                        f"got {raw_dP_gradient!r}"
                    )
                raw_dP = raw_dP_gradient * dp_inp.L_cell
            else:
                dp_inp = self._build_dp_input(req)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP = raw_dp_out.value[0]
                if not math.isfinite(raw_dP):
                    raise ValueError(
                        f"LMTDModel: DP correlation output must be finite; got {raw_dP!r}"
                    )

        dP_primary = req.friction_multiplier * raw_dP
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
        ctx = "LMTDModel._build_htc_input"
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['G'] must be > 0; got {G!r}")
        x_val = _require_scalar(gs, "x", ctx)
        if not (0.0 <= x_val <= 1.0):
            raise ValueError(f"LMTDModel: geom_scalars['x'] must be in [0, 1]; got {x_val!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        return HTCInput(
            state=(req.primary_state_in,),
            G=G,
            x=(x_val,),
            D_h=D_h,
            geom_scalars=gs,
            q_flux=req.q_flux_primary,
        )

    def _build_dp_input(self, req: HXSolveRequest) -> SinglePhaseDPInput:
        gs = req.geom_scalars
        ctx = "LMTDModel._build_dp_input"
        rho = _require_scalar(gs, "rho", ctx)
        mu = _require_scalar(gs, "mu", ctx)
        if rho <= 0:
            raise ValueError(f"LMTDModel: geom_scalars['rho'] must be > 0; got {rho!r}")
        if mu <= 0:
            raise ValueError(f"LMTDModel: geom_scalars['mu'] must be > 0; got {mu!r}")
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['G'] must be > 0; got {G!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        L_cell = _require_scalar(gs, "L_cell", ctx)
        if L_cell <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['L_cell'] must be > 0; got {L_cell!r}")
        return SinglePhaseDPInput(
            state=(req.primary_state_in,),
            G=G,
            D_h=D_h,
            roughness=gs.get("roughness", 0.0),
            L_cell=L_cell,
            rho=rho,
            mu=mu,
        )

    def _build_two_phase_dp_input(self, req: HXSolveRequest) -> TwoPhaseDPInput:
        """Build TwoPhaseDPInput for the primary-side two-phase DP call.

        Required geom_scalars keys: G, x, D_h, L_cell, rho_l, rho_v, mu_l, mu_v.
        rho_l, rho_v, mu_l, mu_v are forwarded into TwoPhaseDPInput.property_scalars.
        L_cell is stored in the returned object; the caller multiplies value[0] by
        L_cell to convert the Pa/m gradient to a pressure drop in Pa.
        """
        gs = req.geom_scalars
        ctx = "LMTDModel._build_two_phase_dp_input"
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['G'] must be > 0; got {G!r}")
        x_val = _require_scalar(gs, "x", ctx)
        if not (0.0 <= x_val <= 1.0):
            raise ValueError(f"LMTDModel: geom_scalars['x'] must be in [0, 1]; got {x_val!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        L_cell = _require_scalar(gs, "L_cell", ctx)
        if L_cell <= 0.0:
            raise ValueError(f"LMTDModel: geom_scalars['L_cell'] must be > 0; got {L_cell!r}")
        property_scalars: dict[str, float] = {}
        for key in ("rho_l", "rho_v", "mu_l", "mu_v"):
            val = _require_scalar(gs, key, ctx)
            if val <= 0.0:
                raise ValueError(f"LMTDModel: geom_scalars[{key!r}] must be > 0; got {val!r}")
            property_scalars[key] = val
        return TwoPhaseDPInput(
            state=(req.primary_state_in,),
            G=G,
            x=(x_val,),
            D_h=D_h,
            L_cell=L_cell,
            property_scalars=property_scalars,
        )
