"""Calibration primitives — Phase 5A.

Data-only value objects for the calibration layer (Layer 4).
Foundation for the calibration seam that future components will consume.

Architectural constraints enforced here:
- No import of CoolProp, properties, correlations, geometry, discretization,
  components, network, or solvers.
- No thermodynamic state stored or computed.
- No physics computations, no parameter estimation, no optimization.
- All objects are immutable.
- Calibration does not call PropertyBackend.
- Calibration does not change the meaning of physical geometry.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum, auto

# ---------------------------------------------------------------------------
# CalibrationMode — frozen per INTERFACE_SPEC §9.1
# ---------------------------------------------------------------------------


class CalibrationMode(Enum):
    """Overall calibration mode for a run.

    NONE: pure predictive physics; all factors are 1.0; the honest baseline.
    TARGET: factors chosen to meet a stated experimental target; results are
            flagged calibrated and never compared as-equal to NONE runs.

    Dataset-fitting is NOT a calibration mode — it is identification territory.
    """

    NONE = auto()
    TARGET = auto()


# ---------------------------------------------------------------------------
# CalibrationTarget — frozen per INTERFACE_SPEC §9.2
# ---------------------------------------------------------------------------


class CalibrationTarget(Enum):
    """What a CalibrationFactor targets.

    Pressure-drop calibration applies ONLY to the friction gradient (R*),
    never to gravity or acceleration [F14].
    Heat-transfer calibration applies to HTC or UA at the output seam.
    """

    FRICTION_GRADIENT = auto()
    HTC = auto()
    UA = auto()


# ---------------------------------------------------------------------------
# CalibrationScope — frozen per INTERFACE_SPEC §9.3
# ---------------------------------------------------------------------------


class CalibrationScope(Enum):
    """Resolution scope for calibration factors.

    Resolution order: SLOT → COMPONENT → GLOBAL → neutral (value=1, mode=NONE).
    """

    SLOT = auto()
    COMPONENT = auto()
    GLOBAL = auto()


# ---------------------------------------------------------------------------
# SeamLocation — identifies where a CalibrationFactor is applied
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeamLocation:
    """Identifies the documented point of application for a CalibrationFactor.

    component_id: the component where the factor is applied (name/id string).
    slot_name: the correlation slot name; None for component-level or global factors.
    scope: the resolution scope (SLOT, COMPONENT, or GLOBAL).
    """

    component_id: str
    slot_name: str | None
    scope: CalibrationScope

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("SeamLocation.component_id must be non-empty")
        if self.slot_name is not None and not self.slot_name:
            raise ValueError("SeamLocation.slot_name, if provided, must be non-empty")
        if not isinstance(self.scope, CalibrationScope):
            raise TypeError(
                f"SeamLocation.scope must be a CalibrationScope, got {type(self.scope)!r}"
            )


# ---------------------------------------------------------------------------
# CalibrationFactor — frozen per INTERFACE_SPEC §9.2
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationFactor:
    """A named, explicit calibration multiplier at a documented seam.

    target: what is being scaled (FRICTION_GRADIENT | HTC | UA).
    value: the multiplier (1.0 == neutral).
    mode: NONE or TARGET.
    seam: where and at what scope it is applied.

    A factor scales a closure output, never a balance.
    Gravity and acceleration are never scaled [F14].
    """

    target: CalibrationTarget
    value: float
    mode: CalibrationMode
    seam: SeamLocation

    def __post_init__(self) -> None:
        if not isinstance(self.target, CalibrationTarget):
            raise TypeError(
                f"CalibrationFactor.target must be a CalibrationTarget, "
                f"got {type(self.target)!r}"
            )
        if not math.isfinite(self.value):
            raise ValueError(f"CalibrationFactor.value must be finite; got {self.value!r}")
        if not isinstance(self.mode, CalibrationMode):
            raise TypeError(
                f"CalibrationFactor.mode must be a CalibrationMode, " f"got {type(self.mode)!r}"
            )
        if not isinstance(self.seam, SeamLocation):
            raise TypeError(
                f"CalibrationFactor.seam must be a SeamLocation, " f"got {type(self.seam)!r}"
            )


# ---------------------------------------------------------------------------
# CalibrationReport — frozen per INTERFACE_SPEC §9.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationReport:
    """Mandatory report present in every Result.

    factors: every non-neutral factor applied in the run (empty under NONE).
    mode: the run's overall calibration mode.

    A Result without a CalibrationReport is malformed (INTERFACE_SPEC §9.4).
    """

    factors: tuple[CalibrationFactor, ...]
    mode: CalibrationMode

    def __post_init__(self) -> None:
        object.__setattr__(self, "factors", tuple(self.factors))
        if not isinstance(self.mode, CalibrationMode):
            raise TypeError(
                f"CalibrationReport.mode must be a CalibrationMode, " f"got {type(self.mode)!r}"
            )
        for f in self.factors:
            if not isinstance(f, CalibrationFactor):
                raise TypeError(
                    f"CalibrationReport.factors must contain CalibrationFactor "
                    f"objects, got {type(f)!r}"
                )

    @staticmethod
    def empty(mode: CalibrationMode = CalibrationMode.NONE) -> CalibrationReport:
        """Return a CalibrationReport with no factors."""
        return CalibrationReport(factors=(), mode=mode)

    @property
    def is_empty(self) -> bool:
        """True if no factors are recorded in this report."""
        return len(self.factors) == 0


# ---------------------------------------------------------------------------
# CalibrationTargetKind — metadata-only target-kind enumeration
# ---------------------------------------------------------------------------


class CalibrationTargetKind(Enum):
    """The high-level kind of entity a CalibrationTargetId refers to.

    Metadata only — no actual correlation/component/property/geometry
    classes are imported or referenced.
    """

    CORRELATION = auto()
    COMPONENT = auto()
    PROPERTY_BACKEND = auto()
    GEOMETRY = auto()


# ---------------------------------------------------------------------------
# CalibrationTargetId — immutable identifier for a calibration target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationTargetId:
    """An immutable, content-addressable identifier for a calibration target.

    kind: the high-level entity kind (CORRELATION, COMPONENT, etc.).
    name: the name or identifier string of the target entity.
    field_name: optional field or parameter name within the target entity.

    Does not import or reference the actual correlation/component classes.
    Equality is structural (kind + name + field_name).
    """

    kind: CalibrationTargetKind
    name: str
    field_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CalibrationTargetKind):
            raise TypeError(
                f"CalibrationTargetId.kind must be a CalibrationTargetKind, "
                f"got {type(self.kind)!r}"
            )
        if not self.name:
            raise ValueError("CalibrationTargetId.name must be non-empty")
        if self.field_name is not None and not self.field_name:
            raise ValueError("CalibrationTargetId.field_name, if provided, must be non-empty")


# ---------------------------------------------------------------------------
# CalibrationModifierKind — the algebraic form of a modifier
# ---------------------------------------------------------------------------


class CalibrationModifierKind(Enum):
    """The algebraic form of a CalibrationModifier.

    MULTIPLIER: y_calibrated = scale * y
    OFFSET:     y_calibrated = y + offset
    AFFINE:     y_calibrated = scale * y + offset
    """

    MULTIPLIER = auto()
    OFFSET = auto()
    AFFINE = auto()


# ---------------------------------------------------------------------------
# CalibrationModifier — immutable value object for one modifier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationModifier:
    """An immutable value object describing one scalar calibration modifier.

    kind: the algebraic form.
    target: the CalibrationTargetId this modifier applies to.
    scale: the multiplicative coefficient.
    offset: the additive offset.
    note: optional source/reference/note string.

    Both scale and offset must be finite (no NaN, no infinity).

    Intended algebraic forms:
    - MULTIPLIER: apply_to_scalar(y) = scale * y  (offset is 0.0)
    - OFFSET:     apply_to_scalar(y) = y + offset  (scale is 1.0)
    - AFFINE:     apply_to_scalar(y) = scale * y + offset
    """

    kind: CalibrationModifierKind
    target: CalibrationTargetId
    scale: float
    offset: float
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CalibrationModifierKind):
            raise TypeError(
                f"CalibrationModifier.kind must be a CalibrationModifierKind, "
                f"got {type(self.kind)!r}"
            )
        if not isinstance(self.target, CalibrationTargetId):
            raise TypeError(
                f"CalibrationModifier.target must be a CalibrationTargetId, "
                f"got {type(self.target)!r}"
            )
        if not math.isfinite(self.scale):
            raise ValueError(f"CalibrationModifier.scale must be finite; got {self.scale!r}")
        if not math.isfinite(self.offset):
            raise ValueError(f"CalibrationModifier.offset must be finite; got {self.offset!r}")

    # ------------------------------------------------------------------
    # Static factory methods (convenience constructors)
    # ------------------------------------------------------------------

    @staticmethod
    def multiplier(
        target: CalibrationTargetId,
        factor: float,
        *,
        note: str | None = None,
    ) -> CalibrationModifier:
        """Construct a MULTIPLIER modifier: y_calibrated = factor * y."""
        if not math.isfinite(factor):
            raise ValueError(f"Multiplier factor must be finite; got {factor!r}")
        return CalibrationModifier(
            kind=CalibrationModifierKind.MULTIPLIER,
            target=target,
            scale=factor,
            offset=0.0,
            note=note,
        )

    @staticmethod
    def offset(
        target: CalibrationTargetId,
        offset_value: float,
        *,
        note: str | None = None,
    ) -> CalibrationModifier:
        """Construct an OFFSET modifier: y_calibrated = y + offset_value."""
        if not math.isfinite(offset_value):
            raise ValueError(f"Offset must be finite; got {offset_value!r}")
        return CalibrationModifier(
            kind=CalibrationModifierKind.OFFSET,
            target=target,
            scale=1.0,
            offset=offset_value,
            note=note,
        )

    @staticmethod
    def affine(
        target: CalibrationTargetId,
        scale: float,
        offset_value: float,
        *,
        note: str | None = None,
    ) -> CalibrationModifier:
        """Construct an AFFINE modifier: y_calibrated = scale * y + offset_value."""
        if not math.isfinite(scale):
            raise ValueError(f"Affine scale must be finite; got {scale!r}")
        if not math.isfinite(offset_value):
            raise ValueError(f"Affine offset must be finite; got {offset_value!r}")
        return CalibrationModifier(
            kind=CalibrationModifierKind.AFFINE,
            target=target,
            scale=scale,
            offset=offset_value,
            note=note,
        )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    def apply_to_scalar(self, value: float) -> float:
        """Apply this modifier to a scalar value.

        MULTIPLIER: scale * value
        OFFSET:     value + offset
        AFFINE:     scale * value + offset

        Generic, physics-independent transformation.
        Does not reference any correlation, component, or property.
        """
        if self.kind is CalibrationModifierKind.MULTIPLIER:
            return self.scale * value
        if self.kind is CalibrationModifierKind.OFFSET:
            return value + self.offset
        # AFFINE
        return self.scale * value + self.offset


# ---------------------------------------------------------------------------
# CalibrationSet — immutable ordered collection of CalibrationModifier objects
# ---------------------------------------------------------------------------


class CalibrationSet:
    """An immutable, ordered collection of CalibrationModifier objects.

    Zero or more modifiers. Ordering is deterministic (preserves insertion order).
    After construction the set is frozen; mutating the original iterable does not
    affect this object.

    Does not import or depend on components, correlations, properties, or network.
    """

    __slots__ = ("_modifiers",)

    def __init__(self, modifiers: Iterable[CalibrationModifier] = ()) -> None:
        snapshot: tuple[CalibrationModifier, ...] = tuple(modifiers)
        for m in snapshot:
            if not isinstance(m, CalibrationModifier):
                raise TypeError(
                    f"CalibrationSet: all elements must be CalibrationModifier "
                    f"instances, got {type(m)!r}"
                )
        object.__setattr__(self, "_modifiers", snapshot)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("CalibrationSet is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CalibrationSet is immutable")

    # ------------------------------------------------------------------
    # Read-only interface
    # ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """True if the set contains no modifiers."""
        return len(self._modifiers) == 0

    def __len__(self) -> int:
        return len(self._modifiers)

    def __iter__(self) -> Iterator[CalibrationModifier]:
        return iter(self._modifiers)

    def __repr__(self) -> str:
        return f"CalibrationSet({list(self._modifiers)!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CalibrationSet):
            return self._modifiers == other._modifiers
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._modifiers)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def modifiers_for(self, target: CalibrationTargetId) -> tuple[CalibrationModifier, ...]:
        """Return all modifiers whose target matches *target*.

        Matching is by equality of CalibrationTargetId value objects.
        Returns a tuple (may be empty); preserves insertion order.
        """
        if not isinstance(target, CalibrationTargetId):
            raise TypeError(
                f"modifiers_for: target must be a CalibrationTargetId, " f"got {type(target)!r}"
            )
        return tuple(m for m in self._modifiers if m.target == target)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def empty() -> CalibrationSet:
        """Return an empty CalibrationSet."""
        return CalibrationSet()
