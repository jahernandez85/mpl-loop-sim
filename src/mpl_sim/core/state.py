"""SystemState, StateLayout, and variable-handle primitives — Phase 1C.

Implements the solver-owned flat state vector and the mapping objects that
identify and locate each scalar unknown within it.

STORED:     P, h, mdot per port-node; named component internal states.
NOT STORED: T, x, rho, mu, k, sigma, cp, phase, or any derived quantity.

This module imports only: standard library, numpy, and mpl_sim.core.port.
It does not import property engines, numerical schemes, component logic,
or network topology.

INTERFACE_SPEC.md §4.2–§4.4  <<FROZEN>>
"""

from __future__ import annotations

import enum
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np

from mpl_sim.core.port import PortId

# ---------------------------------------------------------------------------
# VariableKind
# ---------------------------------------------------------------------------


class VariableKind(enum.Enum):
    """Kind of a scalar slot in the flat SystemState vector.

    P        pressure                [Pa]
    H        specific enthalpy       [J/kg]
    MDOT     mass flow rate          [kg/s]
    INTERNAL named component internal state (wall T, V_g, inventory, …)
    """

    P = "P"
    H = "H"
    MDOT = "MDOT"
    INTERNAL = "INTERNAL"


# ---------------------------------------------------------------------------
# StateVariableId
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateVariableId:
    """Immutable identifier for one scalar slot in the flat state vector.

    Fields:
        kind       : P | H | MDOT | INTERNAL
        owner      : component_id string owning this slot
        local_name : port_name for P/H/MDOT; state name for INTERNAL

    Hashable and structurally comparable; safe as a dict key or set element.
    """

    kind: VariableKind
    owner: str
    local_name: str


# ---------------------------------------------------------------------------
# PortVariableHandle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortVariableHandle:
    """Maps a PortId to the three primary-unknown indices in SystemState.

    Stores indices only — never thermodynamic values.  Created at Network
    assembly and immutable for the life of the assembled problem.

    INTERFACE_SPEC.md §4.2  <<FROZEN>>
    """

    port: PortId
    slot_P: int
    slot_h: int
    slot_mdot: int


# ---------------------------------------------------------------------------
# InternalStateHandle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InternalStateHandle:
    """Maps a component's named internal state to its slot(s) in SystemState.

    For Lumped/Segmented components ``slot`` is fixed at assembly.
    For MovingBoundary components ``slots`` is resolved per step (not frozen
    at assembly); ``slot`` still carries the leading slot for convenience.

    INTERFACE_SPEC.md §4.4  <<FROZEN>>
    """

    component: str  # ComponentId string
    name: str
    slot: int  # primary (fixed-count) slot index
    slots: tuple[int, ...] | None = None  # variable-count (MovingBoundary) seam


# ---------------------------------------------------------------------------
# StateLayout
# ---------------------------------------------------------------------------


class StateLayout:
    """Ordered mapping between StateVariableIds and flat-vector indices.

    Constructed once (typically at Network assembly) from an ordered sequence
    of StateVariableIds.  Immutable after construction.

    Provides:
        index_of(var)                    → int
        variable_at(index)               → StateVariableId
        port_handle(port)                → PortVariableHandle
        internal_handle(component, name) → InternalStateHandle
        names()                          → {index: qualified_name}
        len(layout), iter(layout)

    Duplicate StateVariableIds are rejected at construction time.

    INTERFACE_SPEC.md §4.3 (StateLayout contract)
    """

    def __init__(self, variables: Sequence[StateVariableId]) -> None:
        variables_list: list[StateVariableId] = list(variables)
        seen: set[StateVariableId] = set()
        for var in variables_list:
            if var in seen:
                raise ValueError(f"Duplicate StateVariableId in layout: {var!r}")
            seen.add(var)
        self._variables: list[StateVariableId] = variables_list
        self._index_of: dict[StateVariableId, int] = {v: i for i, v in enumerate(variables_list)}

    # ------------------------------------------------------------------
    # Sequence-like interface
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._variables)

    def __iter__(self) -> Iterator[StateVariableId]:
        return iter(self._variables)

    # ------------------------------------------------------------------
    # Index ↔ variable lookup
    # ------------------------------------------------------------------

    def index_of(self, var: StateVariableId) -> int:
        """Return the flat-vector index for ``var``.

        Raises KeyError if ``var`` is not present in the layout.
        """
        try:
            return self._index_of[var]
        except KeyError:
            raise KeyError(f"StateVariableId not found in layout: {var!r}") from None

    def variable_at(self, index: int) -> StateVariableId:
        """Return the StateVariableId at position ``index``.

        Raises IndexError if ``index`` is out of range.
        """
        try:
            return self._variables[index]
        except IndexError:
            raise IndexError(
                f"Index {index} out of range for layout of length {len(self)}"
            ) from None

    # ------------------------------------------------------------------
    # Handle construction
    # ------------------------------------------------------------------

    def port_handle(self, port: PortId) -> PortVariableHandle:
        """Return a PortVariableHandle mapping ``port`` to its P/h/mdot slots.

        Looks up the three StateVariableIds
            (P,    owner=port.component_id, local_name=port.port_name)
            (H,    owner=port.component_id, local_name=port.port_name)
            (MDOT, owner=port.component_id, local_name=port.port_name)
        and returns their indices.

        Raises KeyError if any of the three variables is absent from the layout.
        """
        p_var = StateVariableId(VariableKind.P, port.component_id, port.port_name)
        h_var = StateVariableId(VariableKind.H, port.component_id, port.port_name)
        m_var = StateVariableId(VariableKind.MDOT, port.component_id, port.port_name)
        return PortVariableHandle(
            port=port,
            slot_P=self.index_of(p_var),
            slot_h=self.index_of(h_var),
            slot_mdot=self.index_of(m_var),
        )

    def internal_handle(self, component: str, name: str) -> InternalStateHandle:
        """Return an InternalStateHandle for the named internal state.

        Raises KeyError if the (INTERNAL, component, name) variable is absent.
        """
        var = StateVariableId(VariableKind.INTERNAL, component, name)
        slot = self.index_of(var)
        return InternalStateHandle(component=component, name=name, slot=slot)

    # ------------------------------------------------------------------
    # names() — ordered introspectable view [F18 precondition]
    # ------------------------------------------------------------------

    def names(self) -> dict[int, str]:
        """Return an ordered {index: qualified_name} mapping.

        Qualified name format:
          port variables:   "<owner>.<local_name>.<KIND>"  e.g. "pump_1.out.P"
          internal states:  "<owner>.<local_name>"         e.g. "pipe_1.wall_T_0"

        The ordered introspectable state list is the precondition for the
        Sensitivity / Linearisation seam [F18] and the future DAE assembler.
        """
        result: dict[int, str] = {}
        for i, var in enumerate(self._variables):
            if var.kind is VariableKind.INTERNAL:
                result[i] = f"{var.owner}.{var.local_name}"
            else:
                result[i] = f"{var.owner}.{var.local_name}.{var.kind.value}"
        return result


# ---------------------------------------------------------------------------
# SystemState
# ---------------------------------------------------------------------------


class SystemState:
    """Solver-owned flat state vector.

    Holds a one-dimensional NumPy float64 array of primary unknowns alongside
    the StateLayout that assigns each slot a stable identity.

    STORED:      P, h, mdot per port-node + named component internal states.
    NOT STORED:  T, x, rho, mu, k, sigma, cp, phase, or any derived quantity.

    Only the Solver should mutate a SystemState in-place.  Nothing outside the
    Solver should hold a mutable reference to one
    (INTERFACE_SPEC.md §4.3  <<FROZEN>>).

    Supports copy-and-bump (``with_updated`` / ``with_updated_by_index``) for
    finite-difference Jacobian construction without mutating the original.
    """

    def __init__(
        self,
        layout: StateLayout,
        values: np.ndarray | Sequence[float],
    ) -> None:
        arr = np.asarray(values, dtype=np.float64)
        if arr.ndim != 1:
            raise ValueError(f"values must be 1-D; got shape {arr.shape}")
        if len(arr) != len(layout):
            raise ValueError(f"values length {len(arr)} does not match layout length {len(layout)}")
        self._layout = layout
        self._values: np.ndarray = arr.copy()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def layout(self) -> StateLayout:
        """The StateLayout describing the variable ordering."""
        return self._layout

    @property
    def values(self) -> np.ndarray:
        """A copy of the underlying flat float64 array."""
        return self._values.copy()

    def __len__(self) -> int:
        return len(self._layout)

    # ------------------------------------------------------------------
    # Read access
    # ------------------------------------------------------------------

    def get_by_index(self, index: int) -> float:
        """Return the value at slot ``index``."""
        return float(self._values[index])

    def get(self, var: StateVariableId) -> float:
        """Return the value for ``var``."""
        return float(self._values[self._layout.index_of(var)])

    # ------------------------------------------------------------------
    # Write access — in-place mutation (intended for the Solver only)
    # ------------------------------------------------------------------

    def set_by_index(self, index: int, value: float) -> None:
        """Mutate the value at slot ``index`` in-place."""
        self._values[index] = float(value)

    def set(self, var: StateVariableId, value: float) -> None:
        """Mutate the value for ``var`` in-place."""
        self._values[self._layout.index_of(var)] = float(value)

    # ------------------------------------------------------------------
    # Copy / copy-and-bump (finite-difference Jacobian workflows)
    # ------------------------------------------------------------------

    def copy(self) -> SystemState:
        """Return an independent copy.  Modifying the copy leaves this unchanged."""
        return SystemState(self._layout, self._values)

    def with_updated(self, var: StateVariableId, value: float) -> SystemState:
        """Return a new SystemState with ``var`` set to ``value``.

        The original is not modified.  Equivalent to a single-slot copy-and-bump.
        """
        new = self.copy()
        new.set(var, value)
        return new

    def with_updated_by_index(self, index: int, value: float) -> SystemState:
        """Return a new SystemState with slot ``index`` set to ``value``.

        The original is not modified.
        """
        new = self.copy()
        new.set_by_index(index, value)
        return new
