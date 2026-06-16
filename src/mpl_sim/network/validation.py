"""Network topology validation -- Phase 7B / 10I.

Validates component and connection declarations for structural correctness.

Phase 10I adds:
- validate_topology accepts optional pressure_references parameter.
- When supplied (not None), checks:
    * Each PressureReferenceWiring references a known component.
    * Each referenced component is of kind ACCUMULATOR.
    * Exactly one pressure-reference wiring is present.
- When pressure_references is None, the check is skipped entirely
  (backward compatibility for Pipe-only test networks).

Architecture constraints:
- MUST NOT import from solvers/, properties/, correlations/, calibration/.
- MUST NOT import CoolProp.
- MUST NOT compute physics or call any component evaluation methods.
- Imports from topology.py are TYPE_CHECKING-only to avoid a circular
  dependency (topology.py imports this module at runtime).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mpl_sim.components.base import Component, ComponentKind
from mpl_sim.core.port import PortRole

if TYPE_CHECKING:
    from mpl_sim.network.topology import NetworkConnection, PressureReferenceWiring


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkValidationResult:
    """Immutable result of a topology validation pass.

    Fields:
        is_valid : True iff no errors were found
        errors   : tuple of human-readable error strings (empty when valid)
    """

    is_valid: bool
    errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Role compatibility
# ---------------------------------------------------------------------------

_COMPATIBLE_PAIRS: frozenset[frozenset[PortRole]] = frozenset(
    {
        frozenset({PortRole.INLET, PortRole.OUTLET}),
    }
)


def _roles_compatible(r1: PortRole, r2: PortRole) -> bool:
    """Return True if the two port roles may be joined by a connection.

    Rules (INTERFACE_SPEC §4.1):
    - BIDIRECTIONAL connects to any role.
    - INLET ↔ OUTLET are the canonical pipe-to-pipe pair.
    - BRANCH ↔ BRANCH is valid for junction-to-junction wiring.
    - All other combinations are incompatible.
    """
    if PortRole.BIDIRECTIONAL in (r1, r2):
        return True
    if frozenset({r1, r2}) in _COMPATIBLE_PAIRS:
        return True
    if r1 is PortRole.BRANCH and r2 is PortRole.BRANCH:
        return True
    return False


# ---------------------------------------------------------------------------
# validate_topology
# ---------------------------------------------------------------------------


def validate_topology(
    components: Mapping[str, Component],
    connections: Sequence[NetworkConnection],
    pressure_references: Sequence[PressureReferenceWiring] | None = None,
) -> NetworkValidationResult:
    """Validate the structural integrity of a network topology.

    Checks performed (always):
    1. Duplicate connection ids.
    2. Self-connections (from_component == to_component).
    3. Connections referencing unknown components.
    4. Connections referencing unknown ports.
    5. Incompatible port roles.
    6. One-to-one port connectivity (V1: each port <= 1 connection).

    Checks performed (when pressure_references is not None):
    7. Each PressureReferenceWiring references a known component.
    8. Each referenced component is of kind ACCUMULATOR.
    9. Exactly one pressure-reference wiring is present.

    Duplicate component ids are NOT checked here; the caller (NetworkTopology)
    is responsible for catching those before building the mapping.

    Does not compute physics, call correlations, call property backends,
    or import CoolProp, solvers, or calibration.

    Parameters
    ----------
    components          : mapping of component_id_name -> Component (structural access only)
    connections         : sequence of NetworkConnection declarations
    pressure_references : optional sequence of PressureReferenceWiring.
                          Pass None to skip pressure-reference validation.

    Returns
    -------
    NetworkValidationResult with is_valid flag and tuple of error strings.
    """
    errors: list[str] = []

    # Build port-role lookup: (component_name, port_name) → PortRole.
    # Only calls comp.ports() — no physical evaluation.
    port_roles: dict[tuple[str, str], PortRole] = {}
    for cid, comp in components.items():
        for port in comp.ports():
            port_roles[(cid, port.id.port_name)] = port.role

    # --- Pass 1: duplicate connection ids ---
    seen_conn_ids: set[str] = set()
    for conn in connections:
        cid_val: str = conn.connection_id.value
        if cid_val in seen_conn_ids:
            errors.append(f"Duplicate connection id: {cid_val!r}")
        else:
            seen_conn_ids.add(cid_val)

    # --- Pass 2: per-connection structural checks ---
    port_conn_count: dict[tuple[str, str], int] = {}

    for conn in connections:
        from_comp = conn.from_component
        from_port = conn.from_port
        to_comp = conn.to_component
        to_port = conn.to_port
        label = conn.connection_id.value

        # Self-connection
        if from_comp == to_comp:
            errors.append(
                f"Connection {label!r}: self-connection on component {from_comp!r} is not allowed"
            )
            continue

        from_exists = from_comp in components
        to_exists = to_comp in components

        if not from_exists:
            errors.append(f"Connection {label!r}: unknown from-component {from_comp!r}")
        if not to_exists:
            errors.append(f"Connection {label!r}: unknown to-component {to_comp!r}")

        # Skip port/role checks if either component is unknown.
        if not (from_exists and to_exists):
            continue

        from_key = (from_comp, from_port)
        to_key = (to_comp, to_port)

        from_port_ok = from_key in port_roles
        to_port_ok = to_key in port_roles

        if not from_port_ok:
            errors.append(
                f"Connection {label!r}: unknown port {from_port!r} " f"on component {from_comp!r}"
            )
        if not to_port_ok:
            errors.append(
                f"Connection {label!r}: unknown port {to_port!r} " f"on component {to_comp!r}"
            )

        if from_port_ok and to_port_ok:
            r1 = port_roles[from_key]
            r2 = port_roles[to_key]
            if not _roles_compatible(r1, r2):
                errors.append(
                    f"Connection {label!r}: incompatible port roles "
                    f"{r1.value} ({from_comp!r}.{from_port!r}) "
                    f"↔ {r2.value} ({to_comp!r}.{to_port!r})"
                )
            # Track for one-to-one check (only count valid-port connections).
            port_conn_count[from_key] = port_conn_count.get(from_key, 0) + 1
            port_conn_count[to_key] = port_conn_count.get(to_key, 0) + 1

    # --- Pass 3: one-to-one connectivity (V1) ---
    for (comp_name, port_name), count in port_conn_count.items():
        if count > 1:
            errors.append(
                f"Port {port_name!r} on component {comp_name!r} has {count} connections "
                f"(V1 requires one-to-one port connectivity)"
            )

    # --- Pass 4: pressure-reference wiring (optional) ---
    if pressure_references is not None:
        pref_list = list(pressure_references)

        # Exactly one required.
        if len(pref_list) != 1:
            errors.append(
                f"Exactly one pressure-reference wiring is required when declared; "
                f"got {len(pref_list)}"
            )
        else:
            pref = pref_list[0]
            # Referenced component must exist.
            if pref.component_id not in components:
                errors.append(
                    f"PressureReferenceWiring references unknown component "
                    f"{pref.component_id!r}"
                )
            else:
                # Referenced component must be an ACCUMULATOR.
                kind = components[pref.component_id].kind()
                if kind is not ComponentKind.ACCUMULATOR:
                    errors.append(
                        f"PressureReferenceWiring component {pref.component_id!r} "
                        f"must be kind ACCUMULATOR; got {kind.value!r}"
                    )

    return NetworkValidationResult(
        is_valid=len(errors) == 0,
        errors=tuple(errors),
    )
