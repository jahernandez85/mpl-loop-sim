"""Volume-pressure law closures -- Phase 10G.

Implements the VOLUME_PRESSURE_LAW correlation role.

PCA (Polytropic Charged Accumulator) law:
  P = P_charge * (V_charge / V_g) ^ n

  where:
    P_charge  : charge pressure [Pa]          (law_params["charge_pressure"])
    V_charge  : charge volume [m3]            (law_params["charge_volume"])
    n         : polytropic index [-]          (law_params["polytropic_index"])
    V_g       : current gas volume [m3]       (inp.V_g)
    V_total   : containment volume [m3]       (inp.V_total)

  Physical behavior:
    - P decreases as V_g increases (gas spring -- n > 0).
    - P = P_charge when V_g = V_charge.
    - Monotonic; P > 0 for all V_g > 0 given P_charge > 0 and n > 0.

  Validity envelope:
    - V_g must be in (0, V_total]: IN_ENVELOPE.
    - V_g > V_total: EXTRAPOLATED (physically marginal but computable).
    - V_g <= 0 or non-finite: OUT_OF_RANGE; returns NaN.

HCA (Heater-Controlled Accumulator) law:
  Declared as a slot name only in V1 (no numeric closure implemented yet).
  Use VolumePressureLawKind.HCA to name the seam; the closure will be
  added when existing docs provide sufficient HCA law parameters.

Architecture rules enforced here:
  - No import of components/, geometry/, network/, solvers/, properties/.
  - No CoolProp call.
  - No mutable state.
  - CorrelationInput received as VolumePressureLawInput (scalar/data-only).
  - CorrelationOutput always returned; no bare float.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
    VolumePressureLawInput,
)

# ---------------------------------------------------------------------------
# PCA (Polytropic Charged Accumulator) validity envelope
# ---------------------------------------------------------------------------

_PCA_SOURCE = SourceRef(
    citation=("Polytropic gas law: P * V^n = const.  " "Standard accumulator pre-charge model."),
    doi=None,
    notes="V_g in (0, V_total] is IN_ENVELOPE; V_g > V_total is EXTRAPOLATED.",
)

_PCA_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(
        Bound(
            quantity=BoundedQuantity.NAMED_SCALAR,
            min=0.0,
            max=None,
            units="V_g [m3] -- must be > 0",
        ),
        Bound(
            quantity=BoundedQuantity.NAMED_SCALAR,
            min=0.0,
            max=None,
            units="V_total [m3] -- must be > 0",
        ),
    ),
    source=_PCA_SOURCE,
    notes="Requires law_params: charge_volume, charge_pressure, polytropic_index.",
)

_PCA_METADATA = ClosureMetadata(
    name="pca_volume_pressure_law",
    version="1.0.0",
    source=_PCA_SOURCE,
)

_PCA_ENVELOPE_REF = EnvelopeRef(
    correlation_name="pca_volume_pressure_law",
    correlation_version="1.0.0",
)

_REQUIRED_PCA_PARAMS = ("charge_volume", "charge_pressure", "polytropic_index")


# ---------------------------------------------------------------------------
# PcaVolumePressureLaw
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PcaVolumePressureLaw(Correlation):
    """Polytropic Charged Accumulator volume-pressure law.

    Implements VOLUME_PRESSURE_LAW role using the polytropic gas relation:

        P = P_charge * (V_charge / V_g) ^ n

    Required keys in inp.law_params:
        "charge_volume"    : V_charge [m3] -- must be > 0
        "charge_pressure"  : P_charge [Pa] -- must be > 0
        "polytropic_index" : n [-] -- must be > 0

    Input:
        inp.V_g     : current gas volume [m3] -- must be > 0
        inp.V_total : containment volume [m3] -- used for validity check

    Output (CorrelationOutput):
        value    : (P,) -- derived pressure [Pa]; NaN if V_g <= 0
        verdict  : IN_ENVELOPE when 0 < V_g <= V_total; EXTRAPOLATED otherwise
        metadata : name="pca_volume_pressure_law", version="1.0.0"
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.VOLUME_PRESSURE_LAW

    def envelope(self) -> ValidityEnvelope:
        return _PCA_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        """Evaluate the PCA law.

        Parameters
        ----------
        inp : VolumePressureLawInput

        Returns
        -------
        CorrelationOutput with value=(P,) in Pa.
        """
        if not isinstance(inp, VolumePressureLawInput):
            raise TypeError(
                f"PcaVolumePressureLaw requires VolumePressureLawInput; "
                f"got {type(inp).__name__!r}"
            )

        # Validate required law_params keys.
        for key in _REQUIRED_PCA_PARAMS:
            if key not in inp.law_params:
                raise ValueError(
                    f"PcaVolumePressureLaw requires law_params[{key!r}]; "
                    f"available keys: {sorted(inp.law_params)!r}"
                )

        V_charge = float(inp.law_params["charge_volume"])
        P_charge = float(inp.law_params["charge_pressure"])
        n = float(inp.law_params["polytropic_index"])
        V_g = inp.V_g
        V_total = inp.V_total

        # Validate law_params values.
        if not math.isfinite(V_charge) or V_charge <= 0:
            raise ValueError(f"charge_volume must be finite and > 0; got {V_charge!r}")
        if not math.isfinite(P_charge) or P_charge <= 0:
            raise ValueError(f"charge_pressure must be finite and > 0; got {P_charge!r}")
        if not math.isfinite(n) or n <= 0:
            raise ValueError(f"polytropic_index must be finite and > 0; got {n!r}")

        # OUT_OF_RANGE: V_g <= 0 or non-finite.
        if not math.isfinite(V_g) or V_g <= 0:
            return CorrelationOutput(
                value=(math.nan,),
                verdict=ValidityVerdict(
                    status=ValidityStatus.OUT_OF_RANGE,
                    envelope=_PCA_ENVELOPE_REF,
                    violated=(_PCA_ENVELOPE.bounds[0],),
                    detail=f"V_g must be > 0; got {V_g!r}",
                ),
                metadata=_PCA_METADATA,
            )

        # Compute P via polytropic relation.
        P = P_charge * (V_charge / V_g) ** n

        # Determine verdict based on V_g vs V_total.
        if V_g <= V_total:
            verdict = ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=_PCA_ENVELOPE_REF,
                violated=(),
            )
        else:
            verdict = ValidityVerdict(
                status=ValidityStatus.EXTRAPOLATED,
                envelope=_PCA_ENVELOPE_REF,
                violated=(_PCA_ENVELOPE.bounds[0],),
                detail=(
                    f"V_g={V_g!r} exceeds V_total={V_total!r}; " f"result is physically marginal"
                ),
            )

        return CorrelationOutput(
            value=(P,),
            verdict=verdict,
            metadata=_PCA_METADATA,
        )
