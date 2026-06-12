"""FluidIdentity — discriminated union naming which fluid a state describes.

Exactly three variants: PureFluid, Mixture, CustomFluid.
All are immutable value objects with structural equality.
No thermodynamic properties are stored here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PureFluid:
    """A single named pure fluid, e.g. 'R134a', 'Acetone', 'Water'."""

    name: str


@dataclass(frozen=True)
class Mixture:
    """A defined mixture with ordered (species, mole_fraction) pairs.

    components is an ordered tuple so that equality is deterministic:
    Mixture((("R134a", 0.7), ("R32", 0.3))) != Mixture((("R32", 0.3), ("R134a", 0.7))).

    model is an optional string naming the equation-of-state model (e.g. "HEOS").
    """

    components: tuple[tuple[str, float], ...]
    model: str | None = None


@dataclass(frozen=True)
class CustomFluid:
    """An opaque handle into a custom property backend."""

    handle: str


# The discriminated union.  Every FluidState.identity must be one of these three.
FluidIdentity = PureFluid | Mixture | CustomFluid
