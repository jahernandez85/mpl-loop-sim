"""Network residual assembly foundation — Phase 13F.

Maps a NetworkGraph topology into explicit structural residual and unknown
declarations.  This is a declaration/specification layer only — it does not
solve, evaluate residuals numerically, or execute component physics.

What this module DOES
---------------------
- Declares one mass-flow unknown per component instance (``mdot:<id>``, kg/s).
- Declares one pressure unknown per graph node (``P:<id>``, Pa; optional).
- Declares one mass-conservation residual per graph node
  (``mass_balance:<id>``, kg/s).
- Declares one pressure-compatibility residual per component instance
  (``pressure_drop:<id>``, Pa; optional).
- Provides an assembly summary with counts and names only (no values).
- Validates structural closed-loop topology when requested.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT solve the network.
- MUST NOT evaluate residuals numerically.
- MUST NOT execute component physics.
- MUST NOT call property backends, correlations, or CoolProp.
- MUST NOT store FluidState, mdot values, pressure values, enthalpy values,
  quality, temperature, or any physical state.
- MUST NOT import mpl_sim.closed_loop, mpl_sim.solvers, mpl_sim.components,
  mpl_sim.properties, mpl_sim.correlations, mpl_sim.calibration,
  mpl_sim.hx_models, or CoolProp.
- MUST NOT expose a ``solve()`` method on any assembly type.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.

Exported names
--------------
NetworkUnknownDeclaration  — one scalar unknown declaration (name + unit only)
NetworkResidualDeclaration — one residual equation declaration (name + unit only)
NetworkUnknownSet          — ordered collection of unknown declarations
NetworkResidualSet         — ordered collection of residual declarations
NetworkResidualAssembly    — combined assembly result with topology summary
assemble_network_residuals — factory: NetworkGraph → NetworkResidualAssembly
"""

from __future__ import annotations

from dataclasses import dataclass

from mpl_sim.network.graph import NetworkGraph

# ---------------------------------------------------------------------------
# Declaration types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkUnknownDeclaration:
    """Declares one scalar unknown for a network residual problem.

    This is a pure declaration — it carries a name and unit only.
    It stores no value, no bound, and no initial guess.

    Fields
    ------
    name : non-empty string, e.g. ``"mdot:evaporator"`` or ``"P:node_a"``
    unit : physical unit string, e.g. ``"kg/s"`` or ``"Pa"``

    Raises
    ------
    TypeError   if name or unit is not a string.
    ValueError  if name or unit is empty or whitespace-only.
    """

    name: str
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("NetworkUnknownDeclaration.name must be a string")
        if not self.name.strip():
            raise ValueError(
                f"NetworkUnknownDeclaration.name must be a non-empty string; got {self.name!r}"
            )
        if not isinstance(self.unit, str):
            raise TypeError("NetworkUnknownDeclaration.unit must be a string")
        if not self.unit.strip():
            raise ValueError(
                f"NetworkUnknownDeclaration.unit must be a non-empty string; got {self.unit!r}"
            )


@dataclass(frozen=True)
class NetworkResidualDeclaration:
    """Declares one residual equation for a network residual problem.

    This is a pure declaration — it carries a name and unit only.
    It stores no value, no scale, and no evaluation result.

    Fields
    ------
    name : non-empty string, e.g. ``"mass_balance:node_a"``
    unit : physical unit string, e.g. ``"kg/s"``

    Raises
    ------
    TypeError   if name or unit is not a string.
    ValueError  if name or unit is empty or whitespace-only.
    """

    name: str
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("NetworkResidualDeclaration.name must be a string")
        if not self.name.strip():
            raise ValueError(
                f"NetworkResidualDeclaration.name must be a non-empty string; got {self.name!r}"
            )
        if not isinstance(self.unit, str):
            raise TypeError("NetworkResidualDeclaration.unit must be a string")
        if not self.unit.strip():
            raise ValueError(
                f"NetworkResidualDeclaration.unit must be a non-empty string; got {self.unit!r}"
            )


# ---------------------------------------------------------------------------
# Collection types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkUnknownSet:
    """Ordered, immutable collection of unknown declarations for one assembly.

    All unknowns are declaration-only; no physical values are stored.
    Insertion order is preserved.  Duplicate names are rejected.

    Fields
    ------
    unknowns : tuple of NetworkUnknownDeclaration (insertion order)

    Methods
    -------
    names()  : tuple[str, ...] — unknown names in insertion order
    count()  : int             — number of declared unknowns
    """

    unknowns: tuple[NetworkUnknownDeclaration, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.unknowns, tuple):
            object.__setattr__(self, "unknowns", tuple(self.unknowns))
        for i, u in enumerate(self.unknowns):
            if not isinstance(u, NetworkUnknownDeclaration):
                raise TypeError(
                    f"NetworkUnknownSet.unknowns[{i}] must be a "
                    f"NetworkUnknownDeclaration; got {type(u).__name__!r}"
                )
        seen: set[str] = set()
        for u in self.unknowns:
            if u.name in seen:
                raise ValueError(f"NetworkUnknownSet: duplicate unknown name {u.name!r}")
            seen.add(u.name)

    def names(self) -> tuple[str, ...]:
        """Unknown names in insertion order."""
        return tuple(u.name for u in self.unknowns)

    def count(self) -> int:
        """Number of declared unknowns."""
        return len(self.unknowns)


@dataclass(frozen=True)
class NetworkResidualSet:
    """Ordered, immutable collection of residual declarations for one assembly.

    All residuals are declaration-only; no physical values are stored.
    Insertion order is preserved.  Duplicate names are rejected.

    Fields
    ------
    residuals : tuple of NetworkResidualDeclaration (insertion order)

    Methods
    -------
    names()  : tuple[str, ...] — residual names in insertion order
    count()  : int             — number of declared residuals
    """

    residuals: tuple[NetworkResidualDeclaration, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.residuals, tuple):
            object.__setattr__(self, "residuals", tuple(self.residuals))
        for i, r in enumerate(self.residuals):
            if not isinstance(r, NetworkResidualDeclaration):
                raise TypeError(
                    f"NetworkResidualSet.residuals[{i}] must be a "
                    f"NetworkResidualDeclaration; got {type(r).__name__!r}"
                )
        seen: set[str] = set()
        for r in self.residuals:
            if r.name in seen:
                raise ValueError(f"NetworkResidualSet: duplicate residual name {r.name!r}")
            seen.add(r.name)

    def names(self) -> tuple[str, ...]:
        """Residual names in insertion order."""
        return tuple(r.name for r in self.residuals)

    def count(self) -> int:
        """Number of declared residuals."""
        return len(self.residuals)


# ---------------------------------------------------------------------------
# Assembly result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkResidualAssembly:
    """Result of assembling network residual/unknown declarations from a graph.

    Contains declaration-only objects.  No physical values, no solver state,
    no FluidState, no mdot values, no pressure values, no enthalpy values.

    This type MUST NOT be used to evaluate residuals numerically.
    This type MUST NOT expose a solve() method.

    Fields
    ------
    unknowns  : NetworkUnknownSet  — all declared unknowns
    residuals : NetworkResidualSet — all declared residuals

    Methods
    -------
    summary() : dict — counts and names only; no physical values.
    """

    unknowns: NetworkUnknownSet
    residuals: NetworkResidualSet

    def __post_init__(self) -> None:
        if not isinstance(self.unknowns, NetworkUnknownSet):
            raise TypeError(
                "NetworkResidualAssembly.unknowns must be a NetworkUnknownSet; "
                f"got {type(self.unknowns).__name__!r}"
            )
        if not isinstance(self.residuals, NetworkResidualSet):
            raise TypeError(
                "NetworkResidualAssembly.residuals must be a NetworkResidualSet; "
                f"got {type(self.residuals).__name__!r}"
            )

    def summary(self) -> dict[str, object]:
        """Assembly summary: counts and names only.

        Contains no physical values, FluidState, mdot, pressure, enthalpy,
        quality, temperature, or any solver state.

        Returns
        -------
        dict with keys:
            ``unknown_count``   — int
            ``unknown_names``   — list[str]
            ``residual_count``  — int
            ``residual_names``  — list[str]
        """
        return {
            "unknown_count": self.unknowns.count(),
            "unknown_names": list(self.unknowns.names()),
            "residual_count": self.residuals.count(),
            "residual_names": list(self.residuals.names()),
        }


# ---------------------------------------------------------------------------
# Units (module-level constants — no physical values, only unit labels)
# ---------------------------------------------------------------------------

_MDOT_UNIT: str = "kg/s"
_PRESSURE_UNIT: str = "Pa"


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def assemble_network_residuals(
    graph: object,
    *,
    require_closed_loop: bool = False,
    include_pressure_unknowns: bool = True,
    include_pressure_residuals: bool = True,
) -> NetworkResidualAssembly:
    """Assemble structural unknown and residual declarations from a NetworkGraph.

    Given a ``NetworkGraph``, this function builds explicit structural
    declarations in graph insertion order:

    Unknowns
    ^^^^^^^^
    - One mass-flow unknown per component instance:
        ``name = "mdot:<instance_id>"``, ``unit = "kg/s"``
    - One pressure unknown per graph node (if ``include_pressure_unknowns``):
        ``name = "P:<node_id>"``, ``unit = "Pa"``

    Residuals
    ^^^^^^^^^
    - One mass-conservation residual per graph node:
        ``name = "mass_balance:<node_id>"``, ``unit = "kg/s"``
    - One pressure-compatibility residual per component instance
      (if ``include_pressure_residuals``):
        ``name = "pressure_drop:<instance_id>"``, ``unit = "Pa"``

    This function is declaration-only.  It MUST NOT:
    - solve the network
    - evaluate residuals numerically
    - execute component physics
    - call correlations, property backends, or CoolProp
    - store FluidState, mdot values, pressure values, or enthalpy values
    - import or invoke mpl_sim.closed_loop solvers

    Parameters
    ----------
    graph
        Must be a ``NetworkGraph``.  Raises ``TypeError`` if not.
    require_closed_loop
        If ``True``, call ``graph.validate_closed_single_loop()`` before
        assembly.  Raises ``ValueError`` if the graph is not a valid closed
        single loop.  Default: ``False`` (open topologies accepted).
    include_pressure_unknowns
        If ``True`` (default), declare one pressure unknown per graph node.
    include_pressure_residuals
        If ``True`` (default), declare one pressure-compatibility residual per
        component instance.

    Returns
    -------
    NetworkResidualAssembly
        Immutable assembly with ``NetworkUnknownSet`` and ``NetworkResidualSet``.
        Contains declarations only — no numerical values.

    Raises
    ------
    TypeError
        If ``graph`` is not a ``NetworkGraph``.
        If any option is not a boolean.
    ValueError
        If the graph has no nodes.
        If the graph has no component instances.
        If ``require_closed_loop=True`` and the graph is not a closed single
        loop (the error message comes from ``validate_closed_single_loop``).
    """
    if not isinstance(graph, NetworkGraph):
        raise TypeError(
            f"assemble_network_residuals: graph must be a NetworkGraph; "
            f"got {type(graph).__name__!r}"
        )

    options = {
        "require_closed_loop": require_closed_loop,
        "include_pressure_unknowns": include_pressure_unknowns,
        "include_pressure_residuals": include_pressure_residuals,
    }
    for option_name, option_value in options.items():
        if not isinstance(option_value, bool):
            raise TypeError(
                f"assemble_network_residuals: {option_name} must be a bool; "
                f"got {type(option_value).__name__!r}"
            )

    if len(graph.nodes()) == 0:
        raise ValueError("assemble_network_residuals: graph must contain at least one node")
    if len(graph.instances()) == 0:
        raise ValueError(
            "assemble_network_residuals: graph must contain at least one component instance"
        )

    if require_closed_loop:
        graph.validate_closed_single_loop()

    # Build unknowns in deterministic graph-insertion order.
    unknown_list: list[NetworkUnknownDeclaration] = []

    for inst in graph.instances():
        unknown_list.append(
            NetworkUnknownDeclaration(
                name=f"mdot:{inst.instance_id.value}",
                unit=_MDOT_UNIT,
            )
        )

    if include_pressure_unknowns:
        for node in graph.nodes():
            unknown_list.append(
                NetworkUnknownDeclaration(
                    name=f"P:{node.node_id.value}",
                    unit=_PRESSURE_UNIT,
                )
            )

    # Build residuals in deterministic graph-insertion order.
    residual_list: list[NetworkResidualDeclaration] = []

    for node in graph.nodes():
        residual_list.append(
            NetworkResidualDeclaration(
                name=f"mass_balance:{node.node_id.value}",
                unit=_MDOT_UNIT,
            )
        )

    if include_pressure_residuals:
        for inst in graph.instances():
            residual_list.append(
                NetworkResidualDeclaration(
                    name=f"pressure_drop:{inst.instance_id.value}",
                    unit=_PRESSURE_UNIT,
                )
            )

    return NetworkResidualAssembly(
        unknowns=NetworkUnknownSet(unknowns=tuple(unknown_list)),
        residuals=NetworkResidualSet(residuals=tuple(residual_list)),
    )
