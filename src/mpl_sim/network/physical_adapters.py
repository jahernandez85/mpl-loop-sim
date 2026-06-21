"""Physical residual adapter foundation — Phase 14A.

Provides an explicit adapter layer that turns caller-supplied physical
component residual callbacks into Phase 13G/13H-compatible
NetworkResidualEvaluator objects.

What this module DOES
---------------------
- Defines PhysicalResidualContext: immutable context passed to adapter
  callbacks; carries the current unknown-value mapping and optional caller
  metadata.
- Defines PhysicalResidualAdapter: frozen (residual_name, callback) binding.
  Callback receives a PhysicalResidualContext and returns a float.
- Defines PhysicalResidualAdapterSet: validated, ordered collection of
  PhysicalResidualAdapter entries.
- Defines build_network_residual_evaluators: converts an adapter set + a
  NetworkResidualAssembly into a tuple of NetworkResidualEvaluator objects
  compatible with Phase 13G evaluate_network_residuals and Phase 13H
  solve_network_residual_problem.

What this module DOES NOT DO
-----------------------------
This is an adapter foundation only — it does NOT constitute a full physical
network simulator.  Specifically it MUST NOT and DOES NOT:
- Construct residuals automatically from component physics.
- Execute component instances or call physical component methods.
- Call the frozen component contribution method.
- Call thermodynamic property backends or correlation registries.
- Attach physical state to graph nodes.
- Import CoolProp, scipy, or external optimization libraries.
- Inspect component_type to generate physics.
- Expose a solve(network) method on any type.
- Import or invoke CorrelationRegistry, HeatExchangerModelRegistry,
  FluidState, SystemState, or PropertyBackend.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.calibration, mpl_sim.hx_models, or CoolProp.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT expose a solve(network) method on any type in this module.
- MUST NOT perform property lookup.
- MUST NOT mutate the caller-supplied assembly, adapter set, or metadata.

Exported names
--------------
PhysicalResidualContext          — immutable context passed to adapter callbacks
PhysicalResidualAdapter          — frozen (residual_name, callback) binding
PhysicalResidualAdapterSet       — validated ordered collection of adapters
build_network_residual_evaluators — converts adapters into NetworkResidualEvaluator tuple
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.residual_assembly import NetworkResidualAssembly
from mpl_sim.network.residual_evaluation import NetworkResidualEvaluator

# ---------------------------------------------------------------------------
# PhysicalResidualContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalResidualContext:
    """Immutable context passed to PhysicalResidualAdapter callbacks.

    Carries the current unknown-value mapping and optional caller metadata.
    Does not attach physical state to any graph object, does not call property
    backends, and does not execute component physics.

    Fields
    ------
    unknown_values : MappingProxyType[str, float]
        Read-only view of the unknown name → float map for this evaluation.
        Derived from the Phase 13G evaluation; treat as read-only.
    metadata : MappingProxyType[str, object] | None
        Optional caller-supplied metadata, defensively copied at construction.
        None if no metadata was supplied.

    Validation
    ----------
    - unknown_values must be a Mapping.
    - metadata must be a Mapping or None.
    """

    unknown_values: Mapping[str, float]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        uv = self.unknown_values
        if not isinstance(uv, Mapping):
            raise TypeError(
                "PhysicalResidualContext.unknown_values must be a Mapping; "
                f"got {type(uv).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(uv)))

        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "PhysicalResidualContext.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# PhysicalResidualAdapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalResidualAdapter:
    """Frozen binding of a residual declaration name to its adapter callback.

    One adapter is required per declared residual in the assembly.

    Fields
    ------
    residual_name : non-empty string matching a NetworkResidualDeclaration name
    callback      : callable(context: PhysicalResidualContext) -> float

    The callback receives a PhysicalResidualContext and returns the raw
    residual value in the declared unit.  It may perform any pure computation;
    it must not trigger property lookup, component execution, or graph
    mutation.

    Validation
    ----------
    - residual_name must be a non-empty, non-whitespace string.
    - callback must be callable.
    - Callback return validation (finite, non-bool numeric) is deferred to
      evaluate_network_residuals so that callback exceptions propagate
      naturally.
    """

    residual_name: str
    callback: Callable[[PhysicalResidualContext], float]

    def __post_init__(self) -> None:
        if not isinstance(self.residual_name, str):
            raise TypeError(
                "PhysicalResidualAdapter.residual_name must be a string; "
                f"got {type(self.residual_name).__name__!r}"
            )
        if not self.residual_name.strip():
            raise ValueError(
                "PhysicalResidualAdapter.residual_name must be a non-empty, "
                f"non-whitespace string; got {self.residual_name!r}"
            )
        if not callable(self.callback):
            raise TypeError(
                "PhysicalResidualAdapter.callback must be callable; "
                f"got {type(self.callback).__name__!r}"
            )


# ---------------------------------------------------------------------------
# PhysicalResidualAdapterSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalResidualAdapterSet:
    """Validated, ordered collection of PhysicalResidualAdapter entries.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    residual names.

    Fields
    ------
    adapters : tuple[PhysicalResidualAdapter, ...]
        Ordered adapters, one per declared residual.

    Validation
    ----------
    - Every entry must be a PhysicalResidualAdapter.
    - No two adapters may share a residual_name.
    """

    adapters: tuple[PhysicalResidualAdapter, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.adapters, tuple):
            object.__setattr__(self, "adapters", tuple(self.adapters))
        for i, a in enumerate(self.adapters):
            if not isinstance(a, PhysicalResidualAdapter):
                raise TypeError(
                    f"PhysicalResidualAdapterSet.adapters[{i}] must be a "
                    f"PhysicalResidualAdapter; got {type(a).__name__!r}"
                )
        seen: set[str] = set()
        for a in self.adapters:
            if a.residual_name in seen:
                raise ValueError(
                    "PhysicalResidualAdapterSet: duplicate residual_name " f"{a.residual_name!r}"
                )
            seen.add(a.residual_name)


# ---------------------------------------------------------------------------
# build_network_residual_evaluators
# ---------------------------------------------------------------------------


def build_network_residual_evaluators(
    assembly: object,
    adapters: object,
    *,
    metadata: object = None,
) -> tuple[NetworkResidualEvaluator, ...]:
    """Build NetworkResidualEvaluator callbacks from explicit physical adapters.

    Converts a set of PhysicalResidualAdapter objects into
    NetworkResidualEvaluator objects compatible with Phase 13G
    evaluate_network_residuals and Phase 13H solve_network_residual_problem.

    Each generated evaluator wraps the corresponding adapter callback in a
    PhysicalResidualContext, preserving the assembly residual declaration
    order.  The caller remains responsible for supplying all physical residual
    logic through explicit adapter callbacks.

    Parameters
    ----------
    assembly
        NetworkResidualAssembly from Phase 13F.  Provides residual declaration
        names and insertion order.  Must not be mutated.
    adapters
        PhysicalResidualAdapterSet or iterable of PhysicalResidualAdapter.
        One adapter per declared residual.  Names must match assembly residual
        declarations exactly (no extras, no missing, no duplicates).
    metadata
        Optional Mapping[str, object] passed to each PhysicalResidualContext.
        Defensively copied once at call time.  None by default.

    Returns
    -------
    tuple[NetworkResidualEvaluator, ...]
        One evaluator per residual declaration, in assembly declaration order.
        Each evaluator's callback wraps the corresponding adapter and creates
        a PhysicalResidualContext for each invocation.

    Raises
    ------
    TypeError
        If assembly is not a NetworkResidualAssembly.
        If metadata is not a Mapping or None.
        If any adapter entry is not a PhysicalResidualAdapter.
    ValueError
        If adapter residual names do not match assembly residual names exactly.
        If adapter names contain duplicates (iterable path).

    Notes
    -----
    This function MUST NOT execute component physics, call property backends
    or registries, inspect component_type to generate physics, or attach
    physical state to graph nodes.  The generated evaluators are standard
    NetworkResidualEvaluator objects.
    """
    # --- validate assembly ---
    if not isinstance(assembly, NetworkResidualAssembly):
        raise TypeError(
            "build_network_residual_evaluators: assembly must be a "
            f"NetworkResidualAssembly; got {type(assembly).__name__!r}"
        )

    # --- validate and freeze metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_network_residual_evaluators: metadata must be a Mapping or None; "
            f"got {type(metadata).__name__!r}"
        )
    metadata_proxy: MappingProxyType | None = (
        MappingProxyType(dict(metadata)) if metadata is not None else None  # type: ignore[arg-type]
    )

    # --- normalize adapters ---
    if isinstance(adapters, PhysicalResidualAdapterSet):
        adapter_list: list[PhysicalResidualAdapter] = list(adapters.adapters)
    else:
        try:
            adapter_list = list(adapters)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "build_network_residual_evaluators: adapters must be a "
                "PhysicalResidualAdapterSet or iterable of PhysicalResidualAdapter; "
                f"got {type(adapters).__name__!r}"
            ) from exc
        for i, a in enumerate(adapter_list):
            if not isinstance(a, PhysicalResidualAdapter):
                raise TypeError(
                    f"build_network_residual_evaluators: adapters[{i}] must be a "
                    f"PhysicalResidualAdapter; got {type(a).__name__!r}"
                )

    # --- duplicate check (iterable path; AdapterSet already guards this) ---
    seen_names: set[str] = set()
    for a in adapter_list:
        if a.residual_name in seen_names:
            raise ValueError(
                "build_network_residual_evaluators: duplicate adapter "
                f"residual_name {a.residual_name!r}"
            )
        seen_names.add(a.residual_name)

    # --- exact match with assembly residual declarations ---
    declared: set[str] = set(assembly.residuals.names())
    provided: set[str] = {a.residual_name for a in adapter_list}
    missing = declared - provided
    if missing:
        raise ValueError(
            "build_network_residual_evaluators: missing adapters for declared "
            f"residuals: {sorted(missing)!r}"
        )
    extra = provided - declared
    if extra:
        raise ValueError(
            "build_network_residual_evaluators: adapters contain names not in "
            f"assembly residual declarations: {sorted(extra)!r}"
        )

    # --- build adapter lookup ---
    adapter_by_name: dict[str, PhysicalResidualAdapter] = {a.residual_name: a for a in adapter_list}

    # --- generate evaluators in assembly declaration order ---
    evaluators: list[NetworkResidualEvaluator] = []
    for res_decl in assembly.residuals.residuals:
        adapter = adapter_by_name[res_decl.name]
        ev = NetworkResidualEvaluator(
            name=res_decl.name,
            callback=_make_evaluator_callback(adapter.callback, metadata_proxy),
        )
        evaluators.append(ev)

    return tuple(evaluators)


def _make_evaluator_callback(
    adapter_callback: Callable[[PhysicalResidualContext], float],
    metadata_proxy: MappingProxyType | None,
) -> Callable[[Mapping], float]:
    """Return a Phase 13G-compatible callback that wraps adapter_callback in a context."""

    def callback(values: Mapping) -> float:
        ctx = PhysicalResidualContext(unknown_values=values, metadata=metadata_proxy)
        return adapter_callback(ctx)

    return callback
