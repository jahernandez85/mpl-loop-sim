"""SegmentedMarchModel heat-exchanger model — Phase 11F/11H/11I/11J.

Implements a segmented forward-march strategy.

Supported BCs (Phase 11F/11H/11I/11J):
  - FixedHeatRate: Q is prescribed; enthalpy is marched cell-by-cell over
    n_cells equal segments.
  - FixedWallTemp: Wall temperature is prescribed; the primary stream is marched
    cell by cell; each cell computes a local heat rate from the injected HTC
    correlation and the local primary temperature.  Requires explicit
    PrimaryThermalMode.FINITE_CAPACITY, primary_T_in, primary_cp, A_ht, and
    htc_primary.
  - AmbientCoupling: Ambient temperature and conductance are prescribed.  The
    primary stream is marched cell by cell using prescribed UA_ambient divided
    equally over n_cells.  No primary HTC correlation is required or called.
    Requires explicit PrimaryThermalMode.FINITE_CAPACITY, primary_T_in, and
    primary_cp.
  - SinkInletTempAndFlow: Both primary and secondary streams have finite heat
    capacities.  Implemented as an explicit co-current (parallel-flow)
    foundation.  Each cell applies per-cell ε-NTU with co-current effectiveness.
    Counterflow is deferred.  Requires explicit PrimaryThermalMode.FINITE_CAPACITY,
    primary_T_in, primary_cp, A_ht, htc_primary, htc_secondary, and
    UAComputationMode.TWO_SIDED.

Common to all paths:
  - Requires DiscretizationSpec with mode=UNIFORM and explicit n_cells >= 1.
  - Rejects LUMPED and MOVING_BOUNDARY modes with a clear ValueError.
  - Calls the injected dp_primary correlation once per cell (cell-wise DP march)
    when supplied; total raw DP is the sum of cell raw DP outputs;
    friction_multiplier applies to the total.
  - Pressure is marched cell-by-cell using calibrated per-cell DP.
  - Returns a SegmentedProfile (zone_profile) containing one SegmentedCellRecord
    per cell for diagnostics.

Sign convention:
  Q > 0  — primary fluid gains enthalpy (evaporator/heating sense)
  Q < 0  — primary fluid rejects heat (condenser/cooling sense)
  h_out  = h_in + Q_total / primary_mdot
  P_out  = P_in - dP_primary     (dP_primary > 0 means pressure decreases)

FixedHeatRate cell energy march:
  Q_cell = Q_total / n_cells
  h_{i+1} = h_i + Q_cell / primary_mdot

FixedWallTemp cell energy march:
  A_cell  = A_ht / n_cells
  UA_cell = htc_multiplier * h_primary_cell * A_cell
  Q_cell  = UA_cell * (T_wall - T_cell_in)
  h_{i+1} = h_i + Q_cell / primary_mdot
  T_{i+1} = T_i + Q_cell / (primary_mdot * primary_cp)

AmbientCoupling cell energy march:
  UA_cell = UA_ambient / n_cells   (htc_multiplier does NOT apply)
  Q_cell  = UA_cell * (T_ambient - T_cell_in)
  h_{i+1} = h_i + Q_cell / primary_mdot
  T_{i+1} = T_i + Q_cell / (primary_mdot * primary_cp)

SinkInletTempAndFlow cell energy march (explicit co-current foundation):
  A_cell     = A_ht / n_cells
  UA_cell    = htc_multiplier applied to two-sided series resistance:
               UA_cell = 1 / (1/(h_p_eff*A_cell) + 1/(h_s_eff*A_cell))
               where h_p_eff = htc_multiplier * h_p_raw
                     h_s_eff = htc_multiplier * h_s_raw
  C_primary  = primary_mdot * primary_cp
  C_secondary = secondary_mdot * cp_secondary
  C_min = min(C_primary, C_secondary)
  Cr    = C_min / max(C_primary, C_secondary)
  NTU   = UA_cell / C_min
  epsilon = (1 - exp(-NTU*(1+Cr))) / (1+Cr)   [co-current formula]
  Q_cell = epsilon * C_min * (T_secondary_in - T_primary_in)
  h_{i+1}         = h_i + Q_cell / primary_mdot
  T_primary_{i+1} = T_primary_i + Q_cell / C_primary
  T_secondary_{i+1} = T_secondary_i - Q_cell / C_secondary

  Flow arrangement: co-current (parallel flow).
  Secondary inlet is at the SAME end as primary inlet (cell 0).
  Counterflow and implicit counterflow solving are deferred.

Cell pressure march (when dp_primary is supplied — all paths):
  raw_dP_cell_i = dp_primary.evaluate(cell_i_inlet_state)
  dP_cell_i     = friction_multiplier * raw_dP_cell_i
  P_{i+1}       = P_i - dP_cell_i
  dP_primary    = friction_multiplier * sum(raw_dP_cell_i)

Unsupported / deferred:
  - PrimaryThermalMode.CONSTANT_TEMPERATURE for all segmented paths.
  - UAComputationMode.PRIMARY_ONLY for SinkInletTempAndFlow (two-stream
    physics requires both HTC values).
  - Counterflow segmented sink coupling.
  - Phase-change segmented coupling.
  - Moving-boundary model.

Architectural constraints:
  - No import of CoolProp, properties/, components/, network/, or solvers/.
  - No registry lookup inside solve().
  - No CorrelationRegistry resolution.
  - No modification of any input object.
  - Cell temperatures stored only in zone_profile diagnostics; never in FluidState.
  - htc_multiplier does not affect AmbientCoupling: UA_ambient is already prescribed.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    CorrelationOutput,
    HTCInput,
    SinglePhaseDPInput,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
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

# ---------------------------------------------------------------------------
# Cell-profile value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SegmentedCellRecord:
    """Immutable diagnostic record for one cell in a segmented HX march.

    All values are in SI units.  This is diagnostic output only;
    it must not be stored in SystemState and must not be attached to Ports.

    Fields
    ------
    cell_index      : zero-based cell index
    Q_cell          : heat transferred to primary fluid in this cell [W]
    h_in            : primary enthalpy at cell inlet [J/kg]
    h_out           : primary enthalpy at cell outlet [J/kg]
    raw_dP_cell     : pre-calibration pressure drop for this cell [Pa]; 0.0 if no DP
    dP_cell         : calibrated pressure drop for this cell [Pa]; 0.0 if no DP
    P_in            : primary pressure at cell inlet [Pa]
    P_out           : primary pressure at cell outlet [Pa]
    T_in            : primary temperature at cell inlet [K]; None for FixedHeatRate path
    T_out           : primary temperature at cell outlet [K]; None for FixedHeatRate path
    htc_primary     : raw primary HTC output for this cell [W/(m²·K)];
                      None for FixedHeatRate and AmbientCoupling paths
    UA_cell         : effective UA for this cell [W/K]; None for FixedHeatRate path
    secondary_T_in  : secondary temperature at cell inlet [K]; SinkInletTempAndFlow only
    secondary_T_out : secondary temperature at cell outlet [K]; SinkInletTempAndFlow only
    htc_secondary   : raw secondary HTC output for this cell [W/(m²·K)];
                      SinkInletTempAndFlow only
    epsilon         : ε-NTU effectiveness for this cell; SinkInletTempAndFlow only
    NTU             : number of transfer units for this cell; SinkInletTempAndFlow only
    C_primary       : primary heat-capacity rate [W/K]; SinkInletTempAndFlow only
    C_secondary     : secondary heat-capacity rate [W/K]; SinkInletTempAndFlow only
    """

    cell_index: int
    Q_cell: float
    h_in: float
    h_out: float
    raw_dP_cell: float = 0.0
    dP_cell: float = 0.0
    P_in: float = 0.0
    P_out: float = 0.0
    T_in: float | None = None
    T_out: float | None = None
    htc_primary: float | None = None
    UA_cell: float | None = None
    secondary_T_in: float | None = None
    secondary_T_out: float | None = None
    htc_secondary: float | None = None
    epsilon: float | None = None
    NTU: float | None = None
    C_primary: float | None = None
    C_secondary: float | None = None


@dataclass(frozen=True)
class SegmentedProfile:
    """Immutable collection of per-cell records from a segmented HX march.

    cells : one SegmentedCellRecord per cell, in march order (index 0 to n-1).

    This is diagnostic output only; it is placed in HXSolveResult.zone_profile
    and must not be stored in SystemState.
    """

    cells: tuple[SegmentedCellRecord, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _require_n_cells(disc: DiscretizationSpec) -> int:
    """Extract and validate n_cells from a DiscretizationSpec.

    Only UNIFORM mode is accepted; LUMPED and MOVING_BOUNDARY are rejected
    because SegmentedMarchModel requires explicit, counted segmentation.
    """
    if disc.mode is not DiscretizationMode.UNIFORM:
        raise ValueError(
            f"SegmentedMarchModel requires DiscretizationMode.UNIFORM with "
            f"explicit n_cells >= 1; got mode {disc.mode!r}.  "
            f"LUMPED represents one implicit control volume and is not accepted "
            f"by SegmentedMarchModel; supply UNIFORM with n_cells >= 1 instead."
        )
    n = disc.n_cells
    # DiscretizationSpec already enforces n_cells >= 1 for UNIFORM, but we
    # check explicitly so the contract is stated at this boundary too.
    if n is None or n < 1:
        raise ValueError(
            f"SegmentedMarchModel: n_cells must be a positive integer for UNIFORM "
            f"discretization; got {n!r}."
        )
    return n


def _epsilon_cocurrent(NTU: float, Cr: float) -> float:
    """Co-current (parallel-flow) heat-exchanger effectiveness.

    Parameters
    ----------
    NTU : number of transfer units (UA / C_min); must be >= 0
    Cr  : heat-capacity-rate ratio C_min/C_max; 0 <= Cr <= 1

    Returns
    -------
    epsilon in [0, 1/(1+Cr)]

    Formula
    -------
    ε = (1 - exp(-NTU*(1+Cr))) / (1+Cr)

    This formula is well-defined for all NTU >= 0 and Cr in [0, 1].
    No special-case branching is needed.
    """
    return (1.0 - math.exp(-NTU * (1.0 + Cr))) / (1.0 + Cr)


# ---------------------------------------------------------------------------
# SegmentedMarchModel
# ---------------------------------------------------------------------------


class SegmentedMarchModel(HeatExchangerModel):
    """Segmented forward-march heat-exchanger strategy — Phase 11F/11H/11I/11J.

    Stateless strategy object.  Two calls with equal HXSolveRequest objects
    return equivalent results.

    Supported BCs: FixedHeatRate, FixedWallTemp, AmbientCoupling,
                   SinkInletTempAndFlow (explicit co-current foundation).

    SinkInletTempAndFlow note: implemented as an explicit co-current
    (parallel-flow) per-cell ε-NTU march.  Both primary and secondary inlets
    are at cell 0.  Counterflow is deferred.  Requires TWO_SIDED UA mode.

    DP handling: cell-wise.  dp_primary (if supplied) is called once per cell
    with the cell inlet state; raw DP values are summed; friction_multiplier
    is applied to the total.  Pressure is marched per cell using calibrated DP.
    Cell-wise DP is consistent with the segmentation philosophy and avoids
    introducing a lumped DP approximation.

    L_cell in geom_scalars is treated as the per-cell length (the caller is
    responsible for supplying the correct per-cell value).
    """

    def kind(self) -> HeatExchangerModelKind:
        """Returns HeatExchangerModelKind.SEGMENTED_MARCH."""
        return HeatExchangerModelKind.SEGMENTED_MARCH

    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        """Solve the heat-exchanger problem described by *req*.

        Supported secondary BCs: FixedHeatRate, FixedWallTemp, AmbientCoupling,
        SinkInletTempAndFlow (explicit co-current foundation).

        Parameters
        ----------
        req : HXSolveRequest

        Returns
        -------
        HXSolveResult

        Raises
        ------
        ValueError
            If discretization mode is not UNIFORM, n_cells is missing/invalid,
            or a required input is absent or invalid for the active BC.
        UnsupportedHeatExchangerBoundaryConditionError
            For unrecognised BC types only.
        """
        bc = req.secondary_bc

        if isinstance(bc, FixedHeatRate):
            return self._solve_fixed_heat_rate(req, bc)

        if isinstance(bc, FixedWallTemp):
            return self._solve_fixed_wall_temp(req, bc)

        if isinstance(bc, AmbientCoupling):
            return self._solve_ambient_coupling(req, bc)

        if isinstance(bc, SinkInletTempAndFlow):
            return self._solve_sink_inlet_cocurrent(req, bc)

        raise UnsupportedHeatExchangerBoundaryConditionError(
            f"SegmentedMarchModel: unrecognised secondary BC type {type(bc)!r}"
        )

    # ------------------------------------------------------------------
    # FixedHeatRate path
    # ------------------------------------------------------------------

    def _solve_fixed_heat_rate(
        self,
        req: HXSolveRequest,
        bc: FixedHeatRate,
    ) -> HXSolveResult:
        n_cells = _require_n_cells(req.discretization)

        Q_total = bc.Q
        Q_cell = Q_total / n_cells

        verdicts: list[CorrelationOutput] = []
        cell_records: list[SegmentedCellRecord] = []

        h_current = req.primary_state_in.h
        P_current = req.primary_state_in.P
        raw_dP_total = 0.0

        for i in range(n_cells):
            h_in = h_current
            P_in = P_current

            h_out = h_in + Q_cell / req.primary_mdot

            raw_dP_cell = 0.0
            dP_cell = 0.0

            if req.dp_primary is not None:
                cell_state = FluidState(
                    P=P_in,
                    h=h_in,
                    identity=req.primary_state_in.identity,
                )
                dp_inp = self._build_dp_input(req, cell_state)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP_cell = raw_dp_out.value[0]
                if not math.isfinite(raw_dP_cell):
                    raise ValueError(
                        f"SegmentedMarchModel: DP correlation output must be finite "
                        f"for cell {i}; got {raw_dP_cell!r}"
                    )
                dP_cell = req.friction_multiplier * raw_dP_cell

            P_out = P_in - dP_cell
            raw_dP_total += raw_dP_cell

            cell_records.append(
                SegmentedCellRecord(
                    cell_index=i,
                    Q_cell=Q_cell,
                    h_in=h_in,
                    h_out=h_out,
                    raw_dP_cell=raw_dP_cell,
                    dP_cell=dP_cell,
                    P_in=P_in,
                    P_out=P_out,
                )
            )

            h_current = h_out
            P_current = P_out

        dP_primary = req.friction_multiplier * raw_dP_total
        primary_state_out = FluidState(
            P=P_current,
            h=h_current,
            identity=req.primary_state_in.identity,
        )

        profile = SegmentedProfile(cells=tuple(cell_records))

        return HXSolveResult(
            primary_state_out=primary_state_out,
            Q=Q_total,
            dP_primary=dP_primary,
            verdicts=tuple(verdicts),
            htc_multiplier=req.htc_multiplier,
            friction_multiplier=req.friction_multiplier,
            raw_dP_primary=raw_dP_total,
            zone_profile=profile,
        )

    # ------------------------------------------------------------------
    # DP input builder
    # ------------------------------------------------------------------

    def _build_dp_input(self, req: HXSolveRequest, cell_state: FluidState) -> SinglePhaseDPInput:
        gs = req.geom_scalars
        ctx = "SegmentedMarchModel._build_dp_input"
        rho = _require_scalar(gs, "rho", ctx)
        if rho <= 0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['rho'] must be > 0; got {rho!r}")
        mu = _require_scalar(gs, "mu", ctx)
        if mu <= 0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['mu'] must be > 0; got {mu!r}")
        G = _require_scalar(gs, "G", ctx)
        if G <= 0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['G'] must be > 0; got {G!r}")
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        L_cell = _require_scalar(gs, "L_cell", ctx)
        if L_cell <= 0:
            raise ValueError(
                f"SegmentedMarchModel: geom_scalars['L_cell'] must be > 0; got {L_cell!r}"
            )
        return SinglePhaseDPInput(
            state=(cell_state,),
            G=G,
            D_h=D_h,
            roughness=gs.get("roughness", 0.0),
            L_cell=L_cell,
            rho=rho,
            mu=mu,
        )

    # ------------------------------------------------------------------
    # AmbientCoupling path
    # ------------------------------------------------------------------

    def _solve_ambient_coupling(
        self,
        req: HXSolveRequest,
        bc: AmbientCoupling,
    ) -> HXSolveResult:
        n_cells = _require_n_cells(req.discretization)

        # --- Require explicit primary inlet temperature ---
        if req.primary_T_in is None:
            raise ValueError(
                "SegmentedMarchModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is AmbientCoupling.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )

        # --- Require FINITE_CAPACITY; CONSTANT_TEMPERATURE is deferred ---
        if req.primary_thermal_mode is PrimaryThermalMode.CONSTANT_TEMPERATURE:
            raise ValueError(
                "SegmentedMarchModel: PrimaryThermalMode.CONSTANT_TEMPERATURE is not "
                "supported for AmbientCoupling segmented coupling.  "
                "Phase-change segmented ambient coupling is deferred."
            )
        if req.primary_thermal_mode is not PrimaryThermalMode.FINITE_CAPACITY:
            raise ValueError(
                "SegmentedMarchModel: primary_thermal_mode must be "
                "PrimaryThermalMode.FINITE_CAPACITY for AmbientCoupling segmented "
                f"coupling; got {req.primary_thermal_mode!r}."
            )

        # --- Require explicit primary_cp ---
        if req.primary_cp is None:
            raise ValueError(
                "SegmentedMarchModel: HXSolveRequest.primary_cp is required when "
                "secondary_bc is AmbientCoupling with FINITE_CAPACITY thermal mode.  "
                "Supply the precomputed primary-side specific heat [J/kg/K]."
            )

        # UA_ambient is already prescribed; htc_multiplier does NOT apply here.
        UA_cell = bc.UA_ambient / n_cells

        verdicts: list[CorrelationOutput] = []
        cell_records: list[SegmentedCellRecord] = []

        h_current = req.primary_state_in.h
        P_current = req.primary_state_in.P
        T_current = req.primary_T_in
        raw_dP_total = 0.0
        Q_total = 0.0

        for i in range(n_cells):
            h_in = h_current
            P_in = P_current
            T_in = T_current

            Q_cell = UA_cell * (bc.T_ambient - T_in)
            h_out = h_in + Q_cell / req.primary_mdot
            T_out = T_in + Q_cell / (req.primary_mdot * req.primary_cp)

            # --- DP: one call per cell ---
            raw_dP_cell = 0.0
            dP_cell = 0.0
            if req.dp_primary is not None:
                cell_state = FluidState(
                    P=P_in,
                    h=h_in,
                    identity=req.primary_state_in.identity,
                )
                dp_inp = self._build_dp_input(req, cell_state)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP_cell = raw_dp_out.value[0]
                if not math.isfinite(raw_dP_cell):
                    raise ValueError(
                        f"SegmentedMarchModel: DP correlation output must be finite "
                        f"for cell {i}; got {raw_dP_cell!r}"
                    )
                dP_cell = req.friction_multiplier * raw_dP_cell

            P_out = P_in - dP_cell
            raw_dP_total += raw_dP_cell
            Q_total += Q_cell

            cell_records.append(
                SegmentedCellRecord(
                    cell_index=i,
                    Q_cell=Q_cell,
                    h_in=h_in,
                    h_out=h_out,
                    raw_dP_cell=raw_dP_cell,
                    dP_cell=dP_cell,
                    P_in=P_in,
                    P_out=P_out,
                    T_in=T_in,
                    T_out=T_out,
                    htc_primary=None,
                    UA_cell=UA_cell,
                )
            )

            h_current = h_out
            P_current = P_out
            T_current = T_out

        dP_primary = req.friction_multiplier * raw_dP_total
        primary_state_out = FluidState(
            P=P_current,
            h=h_current,
            identity=req.primary_state_in.identity,
        )
        profile = SegmentedProfile(cells=tuple(cell_records))

        return HXSolveResult(
            primary_state_out=primary_state_out,
            Q=Q_total,
            dP_primary=dP_primary,
            verdicts=tuple(verdicts),
            htc_multiplier=req.htc_multiplier,
            friction_multiplier=req.friction_multiplier,
            raw_dP_primary=raw_dP_total,
            zone_profile=profile,
        )

    # ------------------------------------------------------------------
    # FixedWallTemp path
    # ------------------------------------------------------------------

    def _solve_fixed_wall_temp(
        self,
        req: HXSolveRequest,
        bc: FixedWallTemp,
    ) -> HXSolveResult:
        ctx = "SegmentedMarchModel._solve_fixed_wall_temp"
        n_cells = _require_n_cells(req.discretization)

        # --- Require explicit primary inlet temperature ---
        if req.primary_T_in is None:
            raise ValueError(
                "SegmentedMarchModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is FixedWallTemp.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )

        # --- Require FINITE_CAPACITY; CONSTANT_TEMPERATURE is deferred ---
        if req.primary_thermal_mode is PrimaryThermalMode.CONSTANT_TEMPERATURE:
            raise ValueError(
                "SegmentedMarchModel: PrimaryThermalMode.CONSTANT_TEMPERATURE is not "
                "supported for FixedWallTemp segmented wall coupling.  "
                "Phase-change segmented wall coupling is deferred."
            )
        if req.primary_thermal_mode is not PrimaryThermalMode.FINITE_CAPACITY:
            raise ValueError(
                "SegmentedMarchModel: primary_thermal_mode must be "
                "PrimaryThermalMode.FINITE_CAPACITY for FixedWallTemp segmented wall "
                f"coupling; got {req.primary_thermal_mode!r}."
            )

        # --- Require explicit primary_cp (validated finite/positive at construction) ---
        if req.primary_cp is None:
            raise ValueError(
                "SegmentedMarchModel: HXSolveRequest.primary_cp is required when "
                "secondary_bc is FixedWallTemp with FINITE_CAPACITY thermal mode.  "
                "Supply the precomputed primary-side specific heat [J/kg/K]."
            )

        # --- Require heat-transfer area ---
        A_ht = _require_scalar(req.geom_scalars, "A_ht", ctx)
        if A_ht <= 0.0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['A_ht'] must be > 0; got {A_ht!r}")

        # --- Require primary HTC correlation ---
        if req.htc_primary is None:
            raise ValueError(
                "SegmentedMarchModel: htc_primary is required when secondary_bc is "
                "FixedWallTemp.  The primary-side HTC is needed to compute "
                "UA_cell = htc_multiplier * h_primary_cell * A_cell."
            )

        A_cell = A_ht / n_cells
        verdicts: list[CorrelationOutput] = []
        cell_records: list[SegmentedCellRecord] = []

        h_current = req.primary_state_in.h
        P_current = req.primary_state_in.P
        T_current = req.primary_T_in
        raw_dP_total = 0.0
        Q_total = 0.0

        for i in range(n_cells):
            h_in = h_current
            P_in = P_current
            T_in = T_current

            cell_state = FluidState(
                P=P_in,
                h=h_in,
                identity=req.primary_state_in.identity,
            )

            # --- HTC: one call per cell ---
            htc_inp = self._build_htc_input_for_cell(req, cell_state)
            raw_htc_out = req.htc_primary.evaluate(htc_inp)
            verdicts.append(raw_htc_out)
            h_primary_cell = raw_htc_out.value[0]
            if not math.isfinite(h_primary_cell) or h_primary_cell <= 0.0:
                raise ValueError(
                    f"SegmentedMarchModel: primary HTC output must be finite and > 0 "
                    f"for cell {i} (FixedWallTemp); got {h_primary_cell!r}"
                )

            UA_cell = req.htc_multiplier * h_primary_cell * A_cell
            Q_cell = UA_cell * (bc.T_wall - T_in)
            h_out = h_in + Q_cell / req.primary_mdot
            T_out = T_in + Q_cell / (req.primary_mdot * req.primary_cp)

            # --- DP: one call per cell; HTC verdict precedes DP verdict ---
            raw_dP_cell = 0.0
            dP_cell = 0.0
            if req.dp_primary is not None:
                dp_inp = self._build_dp_input(req, cell_state)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP_cell = raw_dp_out.value[0]
                if not math.isfinite(raw_dP_cell):
                    raise ValueError(
                        f"SegmentedMarchModel: DP correlation output must be finite "
                        f"for cell {i}; got {raw_dP_cell!r}"
                    )
                dP_cell = req.friction_multiplier * raw_dP_cell

            P_out = P_in - dP_cell
            raw_dP_total += raw_dP_cell
            Q_total += Q_cell

            cell_records.append(
                SegmentedCellRecord(
                    cell_index=i,
                    Q_cell=Q_cell,
                    h_in=h_in,
                    h_out=h_out,
                    raw_dP_cell=raw_dP_cell,
                    dP_cell=dP_cell,
                    P_in=P_in,
                    P_out=P_out,
                    T_in=T_in,
                    T_out=T_out,
                    htc_primary=h_primary_cell,
                    UA_cell=UA_cell,
                )
            )

            h_current = h_out
            P_current = P_out
            T_current = T_out

        dP_primary = req.friction_multiplier * raw_dP_total
        primary_state_out = FluidState(
            P=P_current,
            h=h_current,
            identity=req.primary_state_in.identity,
        )
        profile = SegmentedProfile(cells=tuple(cell_records))

        return HXSolveResult(
            primary_state_out=primary_state_out,
            Q=Q_total,
            dP_primary=dP_primary,
            verdicts=tuple(verdicts),
            htc_multiplier=req.htc_multiplier,
            friction_multiplier=req.friction_multiplier,
            raw_dP_primary=raw_dP_total,
            zone_profile=profile,
        )

    # ------------------------------------------------------------------
    # SinkInletTempAndFlow path — explicit co-current foundation
    # ------------------------------------------------------------------

    def _solve_sink_inlet_cocurrent(
        self,
        req: HXSolveRequest,
        bc: SinkInletTempAndFlow,
    ) -> HXSolveResult:
        """Explicit co-current (parallel-flow) per-cell ε-NTU march.

        Both primary and secondary inlets are at cell 0.
        Counterflow and implicit converged solving are deferred.
        UAComputationMode.PRIMARY_ONLY is not supported; TWO_SIDED is required.
        PrimaryThermalMode.CONSTANT_TEMPERATURE is not supported; deferred.
        """
        ctx = "SegmentedMarchModel._solve_sink_inlet_cocurrent"
        n_cells = _require_n_cells(req.discretization)

        # --- Require FINITE_CAPACITY; CONSTANT_TEMPERATURE is deferred ---
        if req.primary_thermal_mode is PrimaryThermalMode.CONSTANT_TEMPERATURE:
            raise ValueError(
                "SegmentedMarchModel: PrimaryThermalMode.CONSTANT_TEMPERATURE is not "
                "supported for SinkInletTempAndFlow segmented coupling.  "
                "Phase-change segmented sink coupling is deferred."
            )
        if req.primary_thermal_mode is not PrimaryThermalMode.FINITE_CAPACITY:
            raise ValueError(
                "SegmentedMarchModel: primary_thermal_mode must be "
                "PrimaryThermalMode.FINITE_CAPACITY for SinkInletTempAndFlow segmented "
                f"coupling; got {req.primary_thermal_mode!r}."
            )

        # --- Require explicit primary inlet temperature ---
        if req.primary_T_in is None:
            raise ValueError(
                "SegmentedMarchModel: HXSolveRequest.primary_T_in is required when "
                "secondary_bc is SinkInletTempAndFlow.  "
                "Supply the precomputed primary inlet temperature [K] from the caller."
            )

        # --- Require explicit primary_cp (enforced by FINITE_CAPACITY at construction) ---
        if req.primary_cp is None:
            raise ValueError(
                "SegmentedMarchModel: HXSolveRequest.primary_cp is required when "
                "secondary_bc is SinkInletTempAndFlow with FINITE_CAPACITY thermal mode.  "
                "Supply the precomputed primary-side specific heat [J/kg/K]."
            )

        # --- Require TWO_SIDED; PRIMARY_ONLY is not supported for two-stream coupling ---
        if req.ua_computation_mode is UAComputationMode.PRIMARY_ONLY:
            raise ValueError(
                "SegmentedMarchModel: UAComputationMode.PRIMARY_ONLY is not supported "
                "for SinkInletTempAndFlow segmented coupling.  "
                "Two-stream finite-capacity coupling requires both HTC values; "
                "use UAComputationMode.TWO_SIDED and supply htc_secondary."
            )

        # --- Require heat-transfer area ---
        A_ht = _require_scalar(req.geom_scalars, "A_ht", ctx)
        if A_ht <= 0.0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['A_ht'] must be > 0; got {A_ht!r}")

        # --- Require primary HTC correlation ---
        if req.htc_primary is None:
            raise ValueError(
                "SegmentedMarchModel: htc_primary is required when secondary_bc is "
                "SinkInletTempAndFlow.  Needed to compute per-cell two-sided UA."
            )

        # --- Require secondary HTC correlation ---
        if req.htc_secondary is None:
            raise ValueError(
                "SegmentedMarchModel: htc_secondary is required when secondary_bc is "
                "SinkInletTempAndFlow.  Needed to compute per-cell two-sided UA."
            )

        A_cell = A_ht / n_cells
        C_primary = req.primary_mdot * req.primary_cp
        C_secondary = bc.mdot_secondary * bc.cp_secondary

        verdicts: list[CorrelationOutput] = []
        cell_records: list[SegmentedCellRecord] = []

        h_current = req.primary_state_in.h
        P_current = req.primary_state_in.P
        T_p_current = req.primary_T_in
        T_s_current = bc.T_in  # co-current: secondary inlet at same end as primary
        raw_dP_total = 0.0
        Q_total = 0.0

        for i in range(n_cells):
            h_in = h_current
            P_in = P_current
            T_p_in = T_p_current
            T_s_in = T_s_current

            cell_state = FluidState(
                P=P_in,
                h=h_in,
                identity=req.primary_state_in.identity,
            )

            # --- Primary HTC: one call per cell ---
            htc_p_inp = self._build_htc_input_for_cell(req, cell_state)
            raw_htc_p_out = req.htc_primary.evaluate(htc_p_inp)
            verdicts.append(raw_htc_p_out)
            h_p_raw = raw_htc_p_out.value[0]
            if not math.isfinite(h_p_raw) or h_p_raw <= 0.0:
                raise ValueError(
                    f"SegmentedMarchModel: primary HTC output must be finite and > 0 "
                    f"for cell {i} (SinkInletTempAndFlow); got {h_p_raw!r}"
                )

            # --- Secondary HTC: one call per cell ---
            htc_s_inp = self._build_htc_input_for_cell(req, cell_state)
            raw_htc_s_out = req.htc_secondary.evaluate(htc_s_inp)
            verdicts.append(raw_htc_s_out)
            h_s_raw = raw_htc_s_out.value[0]
            if not math.isfinite(h_s_raw) or h_s_raw <= 0.0:
                raise ValueError(
                    f"SegmentedMarchModel: secondary HTC output must be finite and > 0 "
                    f"for cell {i} (SinkInletTempAndFlow); got {h_s_raw!r}"
                )

            # --- Two-sided UA: htc_multiplier applied at the UA seam ---
            # HXSolveRequest permits htc_multiplier = 0.0 (explicit calibration
            # zero-out).  When the multiplier is zero both effective HTCs are
            # zero and the series-resistance formula would divide by zero.
            # Treat this as zero UA: NTU = 0, epsilon = 0, Q_cell = 0.
            h_p_eff = req.htc_multiplier * h_p_raw
            h_s_eff = req.htc_multiplier * h_s_raw
            if h_p_eff == 0.0 or h_s_eff == 0.0:
                UA_cell = 0.0
            else:
                UA_cell = 1.0 / (1.0 / (h_p_eff * A_cell) + 1.0 / (h_s_eff * A_cell))

            # --- Per-cell ε-NTU (co-current) ---
            C_min = min(C_primary, C_secondary)
            C_max = max(C_primary, C_secondary)
            Cr = C_min / C_max
            NTU = UA_cell / C_min
            epsilon = _epsilon_cocurrent(NTU, Cr)

            # Q > 0: primary gains heat (T_secondary > T_primary)
            # Q < 0: primary rejects heat (T_primary > T_secondary)
            Q_cell = epsilon * C_min * (T_s_in - T_p_in)
            h_out = h_in + Q_cell / req.primary_mdot
            T_p_out = T_p_in + Q_cell / C_primary
            # Secondary loses energy when primary gains (Q > 0 → T_s decreases)
            T_s_out = T_s_in - Q_cell / C_secondary

            # --- DP: one call per cell; HTC verdicts precede DP verdict ---
            raw_dP_cell = 0.0
            dP_cell = 0.0
            if req.dp_primary is not None:
                dp_inp = self._build_dp_input(req, cell_state)
                raw_dp_out = req.dp_primary.evaluate(dp_inp)
                verdicts.append(raw_dp_out)
                raw_dP_cell = raw_dp_out.value[0]
                if not math.isfinite(raw_dP_cell):
                    raise ValueError(
                        f"SegmentedMarchModel: DP correlation output must be finite "
                        f"for cell {i}; got {raw_dP_cell!r}"
                    )
                dP_cell = req.friction_multiplier * raw_dP_cell

            P_out = P_in - dP_cell
            raw_dP_total += raw_dP_cell
            Q_total += Q_cell

            cell_records.append(
                SegmentedCellRecord(
                    cell_index=i,
                    Q_cell=Q_cell,
                    h_in=h_in,
                    h_out=h_out,
                    raw_dP_cell=raw_dP_cell,
                    dP_cell=dP_cell,
                    P_in=P_in,
                    P_out=P_out,
                    T_in=T_p_in,
                    T_out=T_p_out,
                    htc_primary=h_p_raw,
                    UA_cell=UA_cell,
                    secondary_T_in=T_s_in,
                    secondary_T_out=T_s_out,
                    htc_secondary=h_s_raw,
                    epsilon=epsilon,
                    NTU=NTU,
                    C_primary=C_primary,
                    C_secondary=C_secondary,
                )
            )

            h_current = h_out
            P_current = P_out
            T_p_current = T_p_out
            T_s_current = T_s_out

        dP_primary = req.friction_multiplier * raw_dP_total
        primary_state_out = FluidState(
            P=P_current,
            h=h_current,
            identity=req.primary_state_in.identity,
        )
        profile = SegmentedProfile(cells=tuple(cell_records))

        return HXSolveResult(
            primary_state_out=primary_state_out,
            Q=Q_total,
            dP_primary=dP_primary,
            verdicts=tuple(verdicts),
            htc_multiplier=req.htc_multiplier,
            friction_multiplier=req.friction_multiplier,
            raw_dP_primary=raw_dP_total,
            zone_profile=profile,
        )

    # ------------------------------------------------------------------
    # HTC input builder
    # ------------------------------------------------------------------

    def _build_htc_input_for_cell(self, req: HXSolveRequest, cell_state: FluidState) -> HTCInput:
        gs = req.geom_scalars
        ctx = "SegmentedMarchModel._build_htc_input_for_cell"
        G = _require_scalar(gs, "G", ctx)
        if G <= 0.0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['G'] must be > 0; got {G!r}")
        x_val = _require_scalar(gs, "x", ctx)
        if not (0.0 <= x_val <= 1.0):
            raise ValueError(
                f"SegmentedMarchModel: geom_scalars['x'] must be in [0, 1]; got {x_val!r}"
            )
        D_h = _require_scalar(gs, "D_h", ctx)
        if D_h <= 0.0:
            raise ValueError(f"SegmentedMarchModel: geom_scalars['D_h'] must be > 0; got {D_h!r}")
        return HTCInput(
            state=(cell_state,),
            G=G,
            x=(x_val,),
            D_h=D_h,
            geom_scalars=gs,
            q_flux=req.q_flux_primary,
        )
