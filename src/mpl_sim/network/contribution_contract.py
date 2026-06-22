"""Component contribution contract adapter prep — Phase 14D.

Provides small, explicit, value-object style contracts for contribution records
and contribution-to-residual mapping.  This is a preparation layer that
describes how future real component contribution outputs can be adapted into
the existing Phase 14C contribution-adapter stack.

What this module DOES
---------------------
- Defines ContributionRecord: a frozen value object representing one named
  scalar contribution emitted by a future component contribution contract.
  Stores component_id, name, value, and optional unit.  Does not execute
  components, look up properties, or assemble state.
- Defines ContributionRecordSet: immutable, ordered collection of
  ContributionRecord objects.  Rejects wrong types and duplicate
  (component_id, name) pairs.  Preserves insertion order.
- Defines ContributionResidualMap: explicit mapping from
  (ComponentInstanceId, contribution_name) pairs to declared residual names.
  Mapping is defensively copied at construction.  Validates all key and value
  types.  Does not store physical values, component objects, or state.
- Defines map_contribution_records_to_component_contribution: selects
  ContributionRecord objects for a given ComponentInstanceId, translates their
  names to residual names using an explicit ContributionResidualMap, and
  returns a Phase 14C ComponentContribution.  Does not execute a component,
  call contribute(...), assemble state, or compute properties.

What this module DOES NOT DO
-----------------------------
This is a contribution contract adapter preparation layer only.
It MUST NOT and DOES NOT:
- Call or execute existing real component classes.
- Call the frozen component contribution method (contribute(...)).
- Assemble SystemState, FluidState, or any physical state.
- Compute or look up thermodynamic properties.
- Call CoolProp, PropertyBackend, or any property engine.
- Call CorrelationRegistry, HeatExchangerModelRegistry, or any registry.
- Attach physical state (FluidState, mdot, pressure, enthalpy) to graph nodes.
- Infer or generate physics from component_type.
- Implement solve(network) or automatic residual construction from component type.
- Import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.correlations, mpl_sim.calibration, or mpl_sim.hx_models.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.calibration, mpl_sim.hx_models, or CoolProp.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT expose a solve(network) method on any type in this module.
- MUST NOT perform property lookup, component execution, or contribute(...) calls.
- MUST NOT mutate the caller-supplied records, mappings, or metadata.

Exported names
--------------
ContributionRecord                              — frozen value object for one named scalar
ContributionRecordSet                           — validated ordered collection of ContributionRecord
ContributionResidualMap                         — (component_id, name) → residual name mapping
map_contribution_records_to_component_contribution — convert records to ComponentContribution
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.contribution_adapters import ComponentContribution
from mpl_sim.network.graph import ComponentInstanceId

# ---------------------------------------------------------------------------
# ContributionRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContributionRecord:
    """Frozen value object representing one named scalar contribution.

    Represents a single named scalar contribution that a future component
    contribution contract might emit.  Stores the contributing component's
    identity, the contribution name, the scalar value, and an optional unit
    annotation.

    No component is executed.  No property is looked up.  No state is
    assembled.  This is a pure data object for contract adapter preparation.

    Fields
    ------
    component_id : ComponentInstanceId identifying the contributing component
    name         : non-empty, non-whitespace contribution name
    value        : finite numeric scalar (int or float, not bool)
    unit         : optional non-empty, non-whitespace unit annotation

    Validation
    ----------
    - component_id must be a ComponentInstanceId.
    - name must be a non-empty, non-whitespace string.
    - value must be a finite numeric (int or float); bool is rejected.
    - unit, if supplied, must be a non-empty, non-whitespace string.
    """

    component_id: ComponentInstanceId
    name: str
    value: float
    unit: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ContributionRecord.component_id must be a ComponentInstanceId; "
                f"got {type(self.component_id).__name__!r}"
            )
        if not isinstance(self.name, str):
            raise TypeError(
                "ContributionRecord.name must be a str; " f"got {type(self.name).__name__!r}"
            )
        if not self.name.strip():
            raise ValueError(
                "ContributionRecord.name must be a non-empty, non-whitespace string; "
                f"got {self.name!r}"
            )
        v = self.value
        if isinstance(v, bool):
            raise TypeError(f"ContributionRecord.value must not be bool; got {v!r}")
        if not isinstance(v, (int, float)):
            raise TypeError(
                "ContributionRecord.value must be a finite numeric (int or float); "
                f"got {type(v).__name__!r}"
            )
        if not math.isfinite(v):
            raise ValueError(f"ContributionRecord.value must be finite; got {v!r}")
        object.__setattr__(self, "value", float(v))
        u = self.unit
        if u is not None:
            if not isinstance(u, str):
                raise TypeError(
                    "ContributionRecord.unit must be a str or None; " f"got {type(u).__name__!r}"
                )
            if not u.strip():
                raise ValueError(
                    "ContributionRecord.unit must be non-empty, non-whitespace if "
                    f"supplied; got {u!r}"
                )


# ---------------------------------------------------------------------------
# ContributionRecordSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContributionRecordSet:
    """Immutable, ordered collection of ContributionRecord objects.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    (component_id, name) pairs.

    Fields
    ------
    records : tuple[ContributionRecord, ...]
        Ordered records, one per named contribution.

    Validation
    ----------
    - Every entry must be a ContributionRecord.
    - No two records may share a (component_id, name) pair.
    """

    records: tuple[ContributionRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            object.__setattr__(self, "records", tuple(self.records))
        for i, r in enumerate(self.records):
            if not isinstance(r, ContributionRecord):
                raise TypeError(
                    f"ContributionRecordSet.records[{i}] must be a ContributionRecord; "
                    f"got {type(r).__name__!r}"
                )
        seen: set[tuple[str, str]] = set()
        for r in self.records:
            key = (r.component_id.value, r.name)
            if key in seen:
                raise ValueError(
                    "ContributionRecordSet: duplicate (component_id, name) pair "
                    f"({r.component_id.value!r}, {r.name!r})"
                )
            seen.add(key)


# ---------------------------------------------------------------------------
# ContributionResidualMap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContributionResidualMap:
    """Explicit mapping from (ComponentInstanceId, contribution_name) to residual name.

    Translates contribution record identities into the residual names declared
    in a NetworkResidualAssembly.  The mapping is defensively copied at
    construction time.  No physical values, component objects, or state are
    stored.

    Fields
    ------
    mapping : immutable mapping from (ComponentInstanceId, contribution_name)
              to residual name string

    Validation
    ----------
    - mapping must be a Mapping.
    - Every key must be a 2-tuple of (ComponentInstanceId, str).
    - The contribution_name (key[1]) must be non-empty and non-whitespace.
    - Every residual name (value) must be a non-empty, non-whitespace string.
    - Mapping is defensively copied; post-construction mutation of the source
      does not affect this object.
    """

    mapping: Mapping

    def __post_init__(self) -> None:
        m = self.mapping
        if not isinstance(m, Mapping):
            raise TypeError(
                "ContributionResidualMap.mapping must be a Mapping; " f"got {type(m).__name__!r}"
            )
        validated: dict[tuple[ComponentInstanceId, str], str] = {}
        for key, residual_name in m.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise TypeError(
                    "ContributionResidualMap.mapping keys must be 2-tuples of "
                    f"(ComponentInstanceId, str); got key {key!r}"
                )
            component_id, contribution_name = key
            if not isinstance(component_id, ComponentInstanceId):
                raise TypeError(
                    "ContributionResidualMap.mapping key[0] must be a "
                    f"ComponentInstanceId; got {type(component_id).__name__!r}"
                )
            if not isinstance(contribution_name, str):
                raise TypeError(
                    "ContributionResidualMap.mapping key[1] must be a str; "
                    f"got {type(contribution_name).__name__!r}"
                )
            if not contribution_name.strip():
                raise ValueError(
                    "ContributionResidualMap.mapping key[1] must be non-empty, "
                    f"non-whitespace; got {contribution_name!r}"
                )
            if not isinstance(residual_name, str):
                raise TypeError(
                    "ContributionResidualMap.mapping values must be str; "
                    f"got {type(residual_name).__name__!r}"
                )
            if not residual_name.strip():
                raise ValueError(
                    "ContributionResidualMap.mapping values must be non-empty, "
                    f"non-whitespace; got {residual_name!r}"
                )
            validated[(component_id, contribution_name)] = residual_name
        object.__setattr__(self, "mapping", MappingProxyType(validated))


# ---------------------------------------------------------------------------
# map_contribution_records_to_component_contribution
# ---------------------------------------------------------------------------


def map_contribution_records_to_component_contribution(
    component_id: object,
    record_set: object,
    residual_map: object,
    *,
    allowed_residual_names: frozenset[str] | set[str] | None = None,
) -> ComponentContribution:
    """Convert selected ContributionRecord objects into a Phase 14C ComponentContribution.

    Selects records from record_set that belong to the requested component_id,
    translates each record's contribution name to a residual name using
    residual_map, and returns a ComponentContribution with the resulting
    residual_values mapping.  Order follows the insertion order of the
    record_set.

    Parameters
    ----------
    component_id
        ComponentInstanceId of the component whose records to select.
    record_set
        ContributionRecordSet containing all records.
    residual_map
        ContributionResidualMap providing the name translation.
    allowed_residual_names
        Optional set of declared residual names.  If supplied, any mapped
        residual name not in this set is rejected with ValueError.

    Returns
    -------
    ComponentContribution
        Phase 14C contribution result with residual_values populated from
        the mapped records, in record_set insertion order.

    Raises
    ------
    TypeError
        If component_id is not a ComponentInstanceId.
        If record_set is not a ContributionRecordSet.
        If residual_map is not a ContributionResidualMap.
    ValueError
        If a selected record has no entry in residual_map (missing mapping).
        If a mapped residual name is not in allowed_residual_names (undeclared).
        If two records for this component map to the same residual name.

    Notes
    -----
    This function MUST NOT execute real component classes, call contribute(...),
    assemble SystemState, inspect component_type, call property backends or
    registries, or attach physical state to graph nodes.  All translation is
    performed through the explicit ContributionResidualMap.
    """
    if not isinstance(component_id, ComponentInstanceId):
        raise TypeError(
            "map_contribution_records_to_component_contribution: component_id must be "
            f"a ComponentInstanceId; got {type(component_id).__name__!r}"
        )
    if not isinstance(record_set, ContributionRecordSet):
        raise TypeError(
            "map_contribution_records_to_component_contribution: record_set must be "
            f"a ContributionRecordSet; got {type(record_set).__name__!r}"
        )
    if not isinstance(residual_map, ContributionResidualMap):
        raise TypeError(
            "map_contribution_records_to_component_contribution: residual_map must be "
            f"a ContributionResidualMap; got {type(residual_map).__name__!r}"
        )

    validated_allowed_names: frozenset[str] | None = None
    if allowed_residual_names is not None:
        if not isinstance(allowed_residual_names, (set, frozenset)):
            raise TypeError(
                "map_contribution_records_to_component_contribution: "
                "allowed_residual_names must be a set or frozenset of strings, "
                f"or None; got {type(allowed_residual_names).__name__!r}"
            )
        for name in allowed_residual_names:
            if not isinstance(name, str):
                raise TypeError(
                    "map_contribution_records_to_component_contribution: every "
                    "allowed_residual_names entry must be a str; "
                    f"got {type(name).__name__!r}"
                )
            if not name.strip():
                raise ValueError(
                    "map_contribution_records_to_component_contribution: every "
                    "allowed_residual_names entry must be non-empty and "
                    f"non-whitespace; got {name!r}"
                )
        validated_allowed_names = frozenset(allowed_residual_names)

    selected = [r for r in record_set.records if r.component_id == component_id]

    residual_values: dict[str, float] = {}
    for record in selected:
        key = (record.component_id, record.name)
        if key not in residual_map.mapping:
            raise ValueError(
                "map_contribution_records_to_component_contribution: no residual "
                f"mapping for ({component_id.value!r}, {record.name!r})"
            )
        residual_name = residual_map.mapping[key]
        if validated_allowed_names is not None and residual_name not in validated_allowed_names:
            raise ValueError(
                "map_contribution_records_to_component_contribution: mapped residual "
                f"name {residual_name!r} is not in allowed_residual_names"
            )
        if residual_name in residual_values:
            raise ValueError(
                "map_contribution_records_to_component_contribution: duplicate output "
                f"residual name {residual_name!r} after mapping"
            )
        residual_values[residual_name] = record.value

    return ComponentContribution(residual_values=residual_values)
