"""SegmentedMarchModel heat-exchanger model — Phase 11F.

Implements a minimal segmented forward-march strategy.

Scope (Phase 11F):
  - Handles FixedHeatRate BC only: Q is prescribed; enthalpy is marched
    cell-by-cell over n_cells equal segments.
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

Cell energy march:
  Q_cell = Q_total / n_cells
  h_{i+1} = h_i + Q_cell / primary_mdot

Cell pressure march (when dp_primary is supplied):
  raw_dP_cell_i = dp_primary.evaluate(cell_i_inlet_state)
  dP_cell_i     = friction_multiplier * raw_dP_cell_i
  P_{i+1}       = P_i - dP_cell_i
  dP_primary    = friction_multiplier * sum(raw_dP_cell_i)

Unsupported BCs (Phase 11F):
  - SinkInletTempAndFlow: raises UnsupportedHeatExchangerBoundaryConditionError.
  - FixedWallTemp:        raises UnsupportedHeatExchangerBoundaryConditionError.
  - AmbientCoupling:      raises UnsupportedHeatExchangerBoundaryConditionError.
  Segment-wise secondary coupling and local HTC/UA solving are deferred.

Architectural constraints:
  - No import of CoolProp, properties/, components/, network/, or solvers/.
  - No registry lookup inside solve().
  - No CorrelationRegistry resolution.
  - No modification of any input object.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    CorrelationOutput,
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
    SinkInletTempAndFlow,
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
    cell_index  : zero-based cell index
    Q_cell      : heat transferred to primary fluid in this cell [W]
    h_in        : primary enthalpy at cell inlet [J/kg]
    h_out       : primary enthalpy at cell outlet [J/kg]
    raw_dP_cell : pre-calibration pressure drop for this cell [Pa]; 0.0 if no DP correlation
    dP_cell     : calibrated pressure drop for this cell [Pa]; 0.0 if no DP correlation
    P_in        : primary pressure at cell inlet [Pa]
    P_out       : primary pressure at cell outlet [Pa]
    """

    cell_index: int
    Q_cell: float
    h_in: float
    h_out: float
    raw_dP_cell: float = 0.0
    dP_cell: float = 0.0
    P_in: float = 0.0
    P_out: float = 0.0


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


# ---------------------------------------------------------------------------
# SegmentedMarchModel
# ---------------------------------------------------------------------------


class SegmentedMarchModel(HeatExchangerModel):
    """Minimal segmented forward-march heat-exchanger strategy — Phase 11F.

    Stateless strategy object.  Two calls with equal HXSolveRequest objects
    return equivalent results.

    Supported BCs: FixedHeatRate.
    Unsupported:   SinkInletTempAndFlow, FixedWallTemp, AmbientCoupling.

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

        Supported secondary BCs: FixedHeatRate.

        Parameters
        ----------
        req : HXSolveRequest

        Returns
        -------
        HXSolveResult

        Raises
        ------
        ValueError
            If discretization mode is not UNIFORM, or n_cells is missing/invalid.
        UnsupportedHeatExchangerBoundaryConditionError
            For SinkInletTempAndFlow, FixedWallTemp, and AmbientCoupling BCs.
        """
        bc = req.secondary_bc

        if isinstance(bc, FixedHeatRate):
            return self._solve_fixed_heat_rate(req, bc)

        if isinstance(bc, SinkInletTempAndFlow):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "SegmentedMarchModel does not support SinkInletTempAndFlow in Phase 11F.  "
                "Segment-wise secondary-fluid coupling and local UA solving are deferred."
            )

        if isinstance(bc, FixedWallTemp):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "SegmentedMarchModel does not support FixedWallTemp in Phase 11F.  "
                "Segment-wise wall-temperature coupling is deferred."
            )

        if isinstance(bc, AmbientCoupling):
            raise UnsupportedHeatExchangerBoundaryConditionError(
                "SegmentedMarchModel does not support AmbientCoupling in Phase 11F.  "
                "Segment-wise ambient coupling is deferred."
            )

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
