"""EpsilonNTU heat-exchanger model — Phase 11B/11D.

Implements a minimal lumped ε-NTU strategy for V1.

Scope (V1):
  - Handles FixedHeatRate BC fully: Q is prescribed, outlet enthalpy and
    pressure are derived from injected correlations.
  - Handles SinkInletTempAndFlow BC: lumped ε-NTU calculation with explicit
    primary thermal mode and UA computation mode — no hidden assumptions.
  - Handles FixedWallTemp BC: lumped wall-temperature conductance path;
    requires primary_T_in, A_ht, and htc_primary from the caller.
  - Handles AmbientCoupling BC: UA_ambient drives Q directly; primary_T_in
    required; no HTC correlation needed for the energy balance.
  - Calls injected htc_primary, htc_secondary, and dp_primary through the
    Correlation contract.
  - Applies htc_multiplier at the UA seam and friction_multiplier to DP output.
  - Never resolves a registry internally.
  - Never accesses Ports, Network, Solver, SystemState, or PropertyBackend.
  - Never imports CoolProp.

Sign convention (both paths):
  Q > 0  — primary fluid gains enthalpy (evaporator/heating sense)
  Q < 0  — primary fluid rejects heat (condenser/cooling sense)
  h_out = h_in + Q / primary_mdot
  P_out = P_in - dP_primary      (dP_primary > 0 means pressure decreases)

SinkInletTempAndFlow sign convention:
  Q = epsilon * C_min * (T_secondary_in - T_primary_in)
    T_secondary_in > T_primary_in  →  Q > 0  (primary absorbs heat — evaporator)
    T_primary_in  > T_secondary_in →  Q < 0  (primary rejects heat — condenser)

Calibration seam:
  HTC calibration:  h_eff = htc_multiplier * raw_htc_value
    Applied to each HTC output before UA is computed; affects UA, NTU, ε, Q.
    For FixedHeatRate: Q is prescribed, so htc_multiplier is tracked only.
  DP calibration:   dP_calibrated = friction_multiplier * raw_dP_value
    Applied to the DP correlation output; the calibrated dP is used for P_out.

Primary thermal mode (SinkInletTempAndFlow only — explicit, no inference):
  FINITE_CAPACITY      — primary_cp required; Cr = C_primary/C_secondary
  CONSTANT_TEMPERATURE — Cr = 0; primary_cp must be absent from request

UA computation mode (SinkInletTempAndFlow only — explicit, no fallback):
  PRIMARY_ONLY — UA = h_primary * A_ht; htc_primary required
  TWO_SIDED    — 1/UA = 1/(h_p·A) + 1/(h_s·A); both HTCs required

Required geom_scalars keys:
  _build_htc_input       : "G", "D_h", "x"
  _build_dp_input        : "G", "D_h", "L_cell", "rho", "mu"
                           "roughness" is optional (defaults to 0.0 — smooth pipe)
  _solve_sink_inlet      : "A_ht" (heat-transfer area [m²]) — plus HTC/DP keys
  _solve_fixed_wall_temp : "A_ht" — plus "G", "D_h", "x" for htc_primary input
                           and "G", "D_h", "L_cell", "rho", "mu" if dp_primary
  _solve_ambient_coupling: none for energy; "G", "D_h", "L_cell", "rho", "mu"
                           if dp_primary is supplied

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
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
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


def _epsilon_counterflow(NTU: float, Cr: float) -> float:
    """Counterflow heat-exchanger effectiveness.

    Parameters
    ----------
    NTU : number of transfer units (UA / C_min); must be >= 0
    Cr  : heat-capacity-rate ratio C_min/C_max; 0 <= Cr <= 1

    Returns
    -------
    epsilon in [0, 1]

    Formula
    -------
    Cr == 0  (phase-change stream or infinite C_max):
        ε = 1 - exp(-NTU)
    Cr == 1  (balanced streams — special case to avoid 0/0):
        ε = NTU / (1 + NTU)
    0 < Cr < 1:
        ε = (1 - exp(-NTU*(1-Cr))) / (1 - Cr*exp(-NTU*(1-Cr)))
    """
    if Cr == 0.0:
        return 1.0 - math.exp(-NTU)
    if abs(Cr - 1.0) < 1e-9:
        return NTU / (1.0 + NTU)
    exp_term = math.exp(-NTU * (1.0 - Cr))
    return (1.0 - exp_term) / (1.0 - Cr * exp_term)


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

        Supported secondary BCs: FixedHeatRate, SinkInletTempAndFlow,
        FixedWallTemp, AmbientCoupling.

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
            return self._solve_sink_inlet(req, bc)

        if isinstance(bc, FixedWallTemp):
            return self._solve_fixed_wall_temp(req, bc)

        if isinstance(bc, AmbientCoupling):
            return self._solve_ambient_coupling(req, bc)

        raise UnsupportedHeatExchangerBoundaryConditionError(
            f"EpsilonNTUModel: unrecognised secondary BC type {type(bc)!r}"
        )

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
            if not math.isfinite(raw_dP):
                raise ValueError(
                    f"EpsilonNTUModel: DP correlation output must be finite; got {raw_dP!r}"
                )

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
    # SinkInletTempAndFlow path
    # ------------------------------------------------------------------

    def _solve_sink_inlet(
        self,
        req: HXSolveRequest,
        bc: SinkInletTempAndFlow,
    ) -> HXSolveResult:
        ctx = "EpsilonNTUModel._solve_sink_inlet"

        # --- Require explicit primary temperature (checked first) ---
        if req.primary_T_in is None:
            raise ValueError(
                "EpsilonNTUModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is SinkInletTempAndFlow.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )
        primary_T_in = req.primary_T_in

        # --- Require explicit primary thermal mode (no None-inference of phase change) ---
        if req.primary_thermal_mode is None:
            raise ValueError(
                "EpsilonNTUModel: primary_thermal_mode is required for "
                "SinkInletTempAndFlow.  "
                "Specify PrimaryThermalMode.FINITE_CAPACITY or CONSTANT_TEMPERATURE."
            )

        # --- Require explicit UA computation mode (no implicit single-sided fallback) ---
        if req.ua_computation_mode is None:
            raise ValueError(
                "EpsilonNTUModel: ua_computation_mode is required for "
                "SinkInletTempAndFlow.  "
                "Specify UAComputationMode.PRIMARY_ONLY or TWO_SIDED."
            )

        # --- Require explicit heat-transfer area ---
        A_ht = _require_scalar(req.geom_scalars, "A_ht", ctx)
        if A_ht <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['A_ht'] must be > 0; got {A_ht!r}")

        verdicts: list[CorrelationOutput] = []

        # --- UA computation: explicit mode, no implicit fallback ---
        if req.ua_computation_mode is UAComputationMode.PRIMARY_ONLY:
            # htc_primary required; validated at HXSolveRequest construction
            htc_p_inp = self._build_htc_input(req)
            raw_htc_p_out = req.htc_primary.evaluate(htc_p_inp)  # type: ignore[union-attr]
            verdicts.append(raw_htc_p_out)
            h_p_raw = raw_htc_p_out.value[0]
            if not math.isfinite(h_p_raw) or h_p_raw <= 0.0:
                raise ValueError(
                    f"EpsilonNTUModel: primary HTC output must be finite and > 0 "
                    f"(UAComputationMode.PRIMARY_ONLY); got {h_p_raw!r}"
                )
            h_p_eff = req.htc_multiplier * h_p_raw
            UA = h_p_eff * A_ht

        else:  # TWO_SIDED
            # Both htc_primary and htc_secondary required; validated at construction
            htc_p_inp = self._build_htc_input(req)
            raw_htc_p_out = req.htc_primary.evaluate(htc_p_inp)  # type: ignore[union-attr]
            verdicts.append(raw_htc_p_out)
            h_p_raw = raw_htc_p_out.value[0]
            if not math.isfinite(h_p_raw) or h_p_raw <= 0.0:
                raise ValueError(
                    f"EpsilonNTUModel: primary HTC output must be finite and > 0 "
                    f"(UAComputationMode.TWO_SIDED); got {h_p_raw!r}"
                )

            htc_s_inp = self._build_secondary_htc_input(req)
            raw_htc_s_out = req.htc_secondary.evaluate(htc_s_inp)  # type: ignore[union-attr]
            verdicts.append(raw_htc_s_out)
            h_s_raw = raw_htc_s_out.value[0]
            if not math.isfinite(h_s_raw) or h_s_raw <= 0.0:
                raise ValueError(
                    f"EpsilonNTUModel: secondary HTC output must be finite and > 0 "
                    f"(UAComputationMode.TWO_SIDED); got {h_s_raw!r}"
                )

            h_p_eff = req.htc_multiplier * h_p_raw
            h_s_eff = req.htc_multiplier * h_s_raw
            UA = 1.0 / (1.0 / (h_p_eff * A_ht) + 1.0 / (h_s_eff * A_ht))

        # --- Heat-capacity rates: explicit thermal mode, no None-inference ---
        C_secondary = bc.mdot_secondary * bc.cp_secondary

        if req.primary_thermal_mode is PrimaryThermalMode.FINITE_CAPACITY:
            # primary_cp required; validated at HXSolveRequest construction
            C_primary = req.primary_mdot * req.primary_cp  # type: ignore[operator]
            C_min = min(C_primary, C_secondary)
            C_max = max(C_primary, C_secondary)
            Cr = C_min / C_max
        else:  # CONSTANT_TEMPERATURE
            C_min = C_secondary
            Cr = 0.0

        # --- ε-NTU ---
        NTU = UA / C_min
        epsilon = _epsilon_counterflow(NTU, Cr)

        # Q = heat added to primary fluid
        #   T_secondary > T_primary  →  Q > 0  (primary absorbs heat — evaporator)
        #   T_primary  > T_secondary →  Q < 0  (primary rejects heat — condenser)
        Q = epsilon * C_min * (bc.T_in - primary_T_in)

        # --- Outlet enthalpy ---
        h_out = req.primary_state_in.h + Q / req.primary_mdot

        # --- DP primary (identical path to FixedHeatRate) ---
        raw_dP = 0.0
        if req.dp_primary is not None:
            dp_inp = self._build_dp_input(req)
            raw_dp_out = req.dp_primary.evaluate(dp_inp)
            verdicts.append(raw_dp_out)
            raw_dP = raw_dp_out.value[0]
            if not math.isfinite(raw_dP):
                raise ValueError(
                    f"EpsilonNTUModel: DP correlation output must be finite; got {raw_dP!r}"
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
    # FixedWallTemp path
    # ------------------------------------------------------------------

    def _solve_fixed_wall_temp(
        self,
        req: HXSolveRequest,
        bc: FixedWallTemp,
    ) -> HXSolveResult:
        ctx = "EpsilonNTUModel._solve_fixed_wall_temp"

        # Require explicit primary inlet temperature — caller must supply it.
        if req.primary_T_in is None:
            raise ValueError(
                "EpsilonNTUModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is FixedWallTemp.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )
        primary_T_in = req.primary_T_in

        # Require heat-transfer area for UA = h_primary * A_ht.
        A_ht = _require_scalar(req.geom_scalars, "A_ht", ctx)
        if A_ht <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['A_ht'] must be > 0; got {A_ht!r}")

        # Require primary HTC correlation — it is the only thermal resistance here.
        if req.htc_primary is None:
            raise ValueError(
                "EpsilonNTUModel: htc_primary is required when secondary_bc is "
                "FixedWallTemp.  The primary-side HTC is needed to compute "
                "UA = h_primary * A_ht."
            )

        verdicts: list[CorrelationOutput] = []

        # UA = htc_multiplier * h_primary_raw * A_ht  (calibration seam)
        htc_inp = self._build_htc_input(req)
        raw_htc_out = req.htc_primary.evaluate(htc_inp)
        verdicts.append(raw_htc_out)
        h_p_raw = raw_htc_out.value[0]
        if not math.isfinite(h_p_raw) or h_p_raw <= 0.0:
            raise ValueError(
                f"EpsilonNTUModel: primary HTC output must be finite and > 0 "
                f"(FixedWallTemp); got {h_p_raw!r}"
            )

        h_p_eff = req.htc_multiplier * h_p_raw
        UA = h_p_eff * A_ht

        # Q > 0: primary gains heat (T_wall > T_primary_in)
        # Q < 0: primary rejects heat (T_wall < T_primary_in)
        Q = UA * (bc.T_wall - primary_T_in)

        h_out = req.primary_state_in.h + Q / req.primary_mdot

        # DP path — identical pattern to FixedHeatRate and SinkInletTempAndFlow.
        raw_dP = 0.0
        if req.dp_primary is not None:
            dp_inp = self._build_dp_input(req)
            raw_dp_out = req.dp_primary.evaluate(dp_inp)
            verdicts.append(raw_dp_out)
            raw_dP = raw_dp_out.value[0]
            if not math.isfinite(raw_dP):
                raise ValueError(
                    f"EpsilonNTUModel: DP correlation output must be finite; got {raw_dP!r}"
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
        # Require explicit primary inlet temperature — caller must supply it.
        if req.primary_T_in is None:
            raise ValueError(
                "EpsilonNTUModel: HXSolveRequest.primary_T_in is required when "
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

        # DP path — optional; identical pattern to other BC paths.
        raw_dP = 0.0
        if req.dp_primary is not None:
            dp_inp = self._build_dp_input(req)
            raw_dp_out = req.dp_primary.evaluate(dp_inp)
            verdicts.append(raw_dp_out)
            raw_dP = raw_dp_out.value[0]
            if not math.isfinite(raw_dP):
                raise ValueError(
                    f"EpsilonNTUModel: DP correlation output must be finite; got {raw_dP!r}"
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
        ctx = "EpsilonNTUModel._build_htc_input"
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['G'] must be > 0; got {G!r}")
        x_val = _require_scalar(gs, "x", ctx)
        if not (0.0 <= x_val <= 1.0):
            raise ValueError(f"EpsilonNTUModel: geom_scalars['x'] must be in [0, 1]; got {x_val!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        return HTCInput(
            state=(req.primary_state_in,),
            G=G,
            x=(x_val,),
            D_h=D_h,
            geom_scalars=gs,
            q_flux=req.q_flux_primary,
        )

    def _build_secondary_htc_input(self, req: HXSolveRequest) -> HTCInput:
        """Build HTCInput for the secondary-side HTC call.

        Secondary HTC always receives q_flux=None; primary heat flux must not
        reach the secondary-side correlation.
        """
        gs = req.geom_scalars
        ctx = "EpsilonNTUModel._build_secondary_htc_input"
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['G'] must be > 0; got {G!r}")
        x_val = _require_scalar(gs, "x", ctx)
        if not (0.0 <= x_val <= 1.0):
            raise ValueError(f"EpsilonNTUModel: geom_scalars['x'] must be in [0, 1]; got {x_val!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        return HTCInput(
            state=(req.primary_state_in,),
            G=G,
            x=(x_val,),
            D_h=D_h,
            geom_scalars=gs,
            q_flux=None,
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
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['G'] must be > 0; got {G!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        L_cell = _require_scalar(gs, "L_cell", ctx)
        if L_cell <= 0.0:
            raise ValueError(f"EpsilonNTUModel: geom_scalars['L_cell'] must be > 0; got {L_cell!r}")
        return SinglePhaseDPInput(
            state=(req.primary_state_in,),
            G=G,
            D_h=D_h,
            roughness=gs.get("roughness", 0.0),
            L_cell=L_cell,
            rho=rho,
            mu=mu,
        )
