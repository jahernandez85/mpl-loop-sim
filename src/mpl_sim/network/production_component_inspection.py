"""Production component contribution contract inspection — Phase 14G.

Provides static, read-only inspection of production component classes to
characterise their current contribution boundary.  The module inspects class
structures using ``inspect`` and typing utilities only.  It never instantiates
production component classes, never calls any component method, and never
triggers property, correlation, CoolProp, or SystemState code paths.

What this module DOES
---------------------
- Defines ProductionComponentContractStatus: string-constant class describing
  the outcome of inspecting a production component class.
- Defines ProductionComponentContributionSignature: frozen value object
  describing the signature of a contribution-like method found on a class.
- Defines ProductionComponentInspectionResult: frozen value object recording
  one class inspection outcome.
- Defines inspect_production_component_contract: inspects a single class
  object statically, detects whether a ``contribute`` method exists, analyses
  its signature without calling it, and returns a
  ProductionComponentInspectionResult.
- Defines inspect_known_production_component_contracts: inspects a curated
  set of known production component classes, returning an immutable tuple of
  ProductionComponentInspectionResult objects.

What this module DOES NOT DO
-----------------------------
This is a static inspection layer only.  It MUST NOT and DOES NOT:
- Instantiate any production component class.
- Call ``contribute(...)`` or any other method on any component.
- Call ``produce_records(...)`` or any Phase 14F provider method.
- Assemble SystemState, FluidState, or any physical state.
- Compute or look up thermodynamic properties.
- Call CoolProp, PropertyBackend, or any property engine.
- Call CorrelationRegistry, HeatExchangerModelRegistry, or any registry.
- Attach physical state to graph nodes.
- Infer or generate physics from component_type.
- Implement solve(network).
- Become part of provider or toy execution paths.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import mpl_sim.solvers, mpl_sim.properties, mpl_sim.calibration,
  or CoolProp at module level.
- MUST NOT import mpl_sim.components at module level (imports happen in
  inspect_known_production_component_contracts function body only).
- MUST NOT invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT expose a solve(network) method on any type in this module.
- MUST NOT be imported by provider or toy execution modules.

Exported names
--------------
ProductionComponentContractStatus       — string-constant inspection outcome class
ProductionComponentContributionSignature — frozen signature description value object
ProductionComponentInspectionResult     — frozen class inspection result value object
inspect_production_component_contract   — inspect one class statically
inspect_known_production_component_contracts — inspect known production classes
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import FunctionType

# ---------------------------------------------------------------------------
# ProductionComponentContractStatus
# ---------------------------------------------------------------------------


class ProductionComponentContractStatus:
    """String constants describing the result of inspecting a production class.

    Use these constants as the ``status`` field of
    ``ProductionComponentInspectionResult``.

    Attributes
    ----------
    NO_CONTRIBUTE_METHOD    : class has no method named ``contribute``
    HAS_CONTRIBUTE_METHOD   : class has a method named ``contribute``
    SIGNATURE_COMPATIBLE    : ``contribute`` signature is directly compatible
                              with Phase 14F ``produce_records`` protocol
    SIGNATURE_INCOMPATIBLE  : ``contribute`` exists but signature does not match
    REQUIRES_SYSTEM_STATE   : ``contribute`` exists and parameters suggest
                              SystemState dependency
    REQUIRES_ADAPTER        : ``contribute`` exists but a bridge adapter is
                              required before real component integration
    INSPECTION_UNSUPPORTED  : class or method cannot be statically inspected
    """

    NO_CONTRIBUTE_METHOD: str = "NO_CONTRIBUTE_METHOD"
    HAS_CONTRIBUTE_METHOD: str = "HAS_CONTRIBUTE_METHOD"
    SIGNATURE_COMPATIBLE: str = "SIGNATURE_COMPATIBLE"
    SIGNATURE_INCOMPATIBLE: str = "SIGNATURE_INCOMPATIBLE"
    REQUIRES_SYSTEM_STATE: str = "REQUIRES_SYSTEM_STATE"
    REQUIRES_ADAPTER: str = "REQUIRES_ADAPTER"
    INSPECTION_UNSUPPORTED: str = "INSPECTION_UNSUPPORTED"


_VALID_CONTRACT_STATUSES: frozenset[str] = frozenset(
    {
        ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
        ProductionComponentContractStatus.HAS_CONTRIBUTE_METHOD,
        ProductionComponentContractStatus.SIGNATURE_COMPATIBLE,
        ProductionComponentContractStatus.SIGNATURE_INCOMPATIBLE,
        ProductionComponentContractStatus.REQUIRES_SYSTEM_STATE,
        ProductionComponentContractStatus.REQUIRES_ADAPTER,
        ProductionComponentContractStatus.INSPECTION_UNSUPPORTED,
    }
)


# ---------------------------------------------------------------------------
# Name sets for dependency detection
# ---------------------------------------------------------------------------

_STATE_LIKE_NAMES: frozenset[str] = frozenset(
    {"state", "system_state", "sys_state", "s", "fluid_state"}
)
_CONTEXT_LIKE_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "bind_ctx", "binding_context", "exec_ctx"}
)
_MISSING = object()


def _annotation_text(annotation: object) -> str | None:
    """Return a stable string form without resolving forward references."""
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", None) or repr(annotation)


def _annotation_suggests(annotation: object, concepts: tuple[str, ...]) -> bool:
    """Detect a named concept in an annotation without evaluating it."""
    text = _annotation_text(annotation)
    if text is None:
        return False
    normalized = "".join(character.lower() for character in text if character.isalnum())
    return any(concept in normalized for concept in concepts)


# ---------------------------------------------------------------------------
# ProductionComponentContributionSignature
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionComponentContributionSignature:
    """Frozen value object describing the signature of a contribution-like method.

    Records static signature information only.  Does not call the method, does
    not instantiate the owning class, and does not store any executable object.

    Fields
    ------
    class_name            : name of the inspected class (non-empty)
    method_name           : name of the inspected method (non-empty)
    parameter_names       : immutable tuple of non-self parameter names
    return_annotation     : string representation of the return annotation, or None
    requires_system_state : True if any parameter name suggests SystemState dependency
    requires_context      : True if any parameter name suggests context dependency
    has_varargs           : True if the method accepts *args
    has_kwargs            : True if the method accepts **kwargs
    """

    class_name: str
    method_name: str
    parameter_names: tuple[str, ...]
    return_annotation: str | None
    requires_system_state: bool
    requires_context: bool
    has_varargs: bool
    has_kwargs: bool

    def __post_init__(self) -> None:
        if not isinstance(self.class_name, str):
            raise TypeError("ProductionComponentContributionSignature.class_name must be str")
        if not self.class_name.strip():
            raise ValueError(
                "ProductionComponentContributionSignature.class_name must be non-empty"
            )
        if not isinstance(self.method_name, str):
            raise TypeError("ProductionComponentContributionSignature.method_name must be str")
        if not self.method_name.strip():
            raise ValueError(
                "ProductionComponentContributionSignature.method_name must be non-empty"
            )
        if isinstance(self.parameter_names, (str, bytes)):
            raise TypeError(
                "ProductionComponentContributionSignature.parameter_names "
                "must be an iterable of strings"
            )
        try:
            parameter_names = tuple(self.parameter_names)
        except TypeError as exc:
            raise TypeError(
                "ProductionComponentContributionSignature.parameter_names "
                "must be an iterable of strings"
            ) from exc
        if any(not isinstance(name, str) or not name.strip() for name in parameter_names):
            raise ValueError(
                "ProductionComponentContributionSignature.parameter_names "
                "must contain non-empty strings"
            )
        object.__setattr__(self, "parameter_names", parameter_names)
        if self.return_annotation is not None and not isinstance(self.return_annotation, str):
            raise TypeError(
                "ProductionComponentContributionSignature.return_annotation " "must be str or None"
            )
        if not isinstance(self.requires_system_state, bool):
            raise TypeError(
                "ProductionComponentContributionSignature.requires_system_state " "must be bool"
            )
        if not isinstance(self.requires_context, bool):
            raise TypeError(
                "ProductionComponentContributionSignature.requires_context must be bool"
            )
        if not isinstance(self.has_varargs, bool):
            raise TypeError("ProductionComponentContributionSignature.has_varargs must be bool")
        if not isinstance(self.has_kwargs, bool):
            raise TypeError("ProductionComponentContributionSignature.has_kwargs must be bool")


# ---------------------------------------------------------------------------
# ProductionComponentInspectionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionComponentInspectionResult:
    """Frozen value object recording one production class inspection outcome.

    Does not store component instances, executable callbacks, or physical values.

    Fields
    ------
    class_name  : name of the inspected class (non-empty)
    module_name : fully qualified module name of the class (non-empty)
    status      : one of the ProductionComponentContractStatus string constants
    signature   : ProductionComponentContributionSignature if method found, else None
    notes       : immutable tuple of string observations about the inspection
    """

    class_name: str
    module_name: str
    status: str
    signature: ProductionComponentContributionSignature | None
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.class_name, str):
            raise TypeError("ProductionComponentInspectionResult.class_name must be str")
        if not self.class_name.strip():
            raise ValueError("ProductionComponentInspectionResult.class_name must be non-empty")
        if not isinstance(self.module_name, str):
            raise TypeError("ProductionComponentInspectionResult.module_name must be str")
        if not self.module_name.strip():
            raise ValueError("ProductionComponentInspectionResult.module_name must be non-empty")
        if self.status not in _VALID_CONTRACT_STATUSES:
            raise ValueError(
                "ProductionComponentInspectionResult.status must be a valid "
                "ProductionComponentContractStatus value"
            )
        if self.signature is not None and not isinstance(
            self.signature, ProductionComponentContributionSignature
        ):
            raise TypeError(
                "ProductionComponentInspectionResult.signature must be "
                "ProductionComponentContributionSignature or None; "
                f"got {type(self.signature).__name__!r}"
            )
        if isinstance(self.notes, (str, bytes)):
            raise TypeError(
                "ProductionComponentInspectionResult.notes must be an iterable of strings"
            )
        try:
            notes = tuple(self.notes)
        except TypeError as exc:
            raise TypeError(
                "ProductionComponentInspectionResult.notes must be an iterable of strings"
            ) from exc
        if any(not isinstance(note, str) or not note.strip() for note in notes):
            raise ValueError(
                "ProductionComponentInspectionResult.notes must contain non-empty strings"
            )
        object.__setattr__(self, "notes", notes)


# ---------------------------------------------------------------------------
# inspect_production_component_contract
# ---------------------------------------------------------------------------


def inspect_production_component_contract(
    cls: object,
) -> ProductionComponentInspectionResult:
    """Inspect a class statically for its contribution boundary.

    Determines whether the class has a method named ``contribute``, analyses
    the method signature without calling it, and records compatibility facts.
    Never instantiates the class, never calls any method, never resolves
    properties or correlations.

    Parameters
    ----------
    cls
        A class object (type) to inspect.  Must be a type; otherwise raises
        TypeError.

    Returns
    -------
    ProductionComponentInspectionResult
        Frozen inspection result.  The result stores no component instance,
        no executable callback, and no physical value.

    Raises
    ------
    TypeError
        If ``cls`` is not a class (type).
    """
    if not isinstance(cls, type):
        raise TypeError(
            "inspect_production_component_contract: cls must be a class (type); "
            f"got {type(cls).__name__!r}"
        )

    class_name = cls.__name__
    module_name = cls.__module__ or "<unknown>"

    # Static lookup deliberately bypasses descriptor binding and metaclass
    # ``__getattribute__`` hooks. Inspection must not become an execution path.
    attr = inspect.getattr_static(cls, "contribute", _MISSING)
    if attr is _MISSING:
        return ProductionComponentInspectionResult(
            class_name=class_name,
            module_name=module_name,
            status=ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
            signature=None,
            notes=(
                "No 'contribute' method found on this class or its MRO.",
                "Production component contribute(...) contract is deferred.",
                "Block 15A will define a controlled production-component bridge.",
            ),
        )

    if isinstance(attr, (staticmethod, classmethod)):
        signature_target = attr.__func__
    elif isinstance(attr, FunctionType):
        signature_target = attr
    else:
        return ProductionComponentInspectionResult(
            class_name=class_name,
            module_name=module_name,
            status=ProductionComponentContractStatus.INSPECTION_UNSUPPORTED,
            signature=None,
            notes=(
                "'contribute' exists but is not a directly inspectable function, "
                "staticmethod, or classmethod; descriptor binding was not executed.",
            ),
        )

    # --- inspect signature without calling ---
    try:
        sig = inspect.signature(signature_target)
    except (ValueError, TypeError):
        return ProductionComponentInspectionResult(
            class_name=class_name,
            module_name=module_name,
            status=ProductionComponentContractStatus.INSPECTION_UNSUPPORTED,
            signature=None,
            notes=("Signature of 'contribute' could not be inspected statically.",),
        )

    param_names: list[str] = []
    has_varargs = False
    has_kwargs = False
    requires_system_state = False
    requires_context = False

    for name, param in sig.parameters.items():
        if name in {"self", "cls"}:
            continue
        lower_name = name.lower()
        requires_system_state = requires_system_state or (
            lower_name in _STATE_LIKE_NAMES
            or _annotation_suggests(
                param.annotation,
                ("systemstate", "fluidstate", "componenttrialstate", "state"),
            )
        )
        requires_context = requires_context or (
            lower_name in _CONTEXT_LIKE_NAMES
            or _annotation_suggests(
                param.annotation,
                ("evalcontext", "networkbindingcontext", "executioncontext", "context"),
            )
        )
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            has_varargs = True
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            has_kwargs = True
        else:
            param_names.append(name)

    return_annotation_str = _annotation_text(sig.return_annotation)

    contribution_sig = ProductionComponentContributionSignature(
        class_name=class_name,
        method_name="contribute",
        parameter_names=tuple(param_names),
        return_annotation=return_annotation_str,
        requires_system_state=requires_system_state,
        requires_context=requires_context,
        has_varargs=has_varargs,
        has_kwargs=has_kwargs,
    )

    note_list: list[str] = [
        f"Found 'contribute' method with parameters: {tuple(param_names)!r}.",
        "Phase 14F 'produce_records' protocol is not directly compatible.",
        "A bridge adapter will be required before real component integration.",
    ]

    if requires_system_state:
        status = ProductionComponentContractStatus.REQUIRES_SYSTEM_STATE
        note_list.append(
            "Signature suggests SystemState dependency — "
            "SystemState assembly is not yet implemented."
        )
    else:
        status = ProductionComponentContractStatus.REQUIRES_ADAPTER

    if requires_context:
        note_list.append(
            "Signature suggests context/binding dependency — "
            "a NetworkBindingContext bridge will be needed."
        )

    return ProductionComponentInspectionResult(
        class_name=class_name,
        module_name=module_name,
        status=status,
        signature=contribution_sig,
        notes=tuple(note_list),
    )


# ---------------------------------------------------------------------------
# inspect_known_production_component_contracts
# ---------------------------------------------------------------------------


def inspect_known_production_component_contracts() -> (
    tuple[ProductionComponentInspectionResult, ...]
):
    """Inspect a curated set of known production component classes.

    Imports production component classes inside the function body only.
    The imports do not trigger CoolProp, PropertyBackend, or any correlation
    or registry execution — component class definitions are pure structural
    declarations.

    Never instantiates any class.  Never calls any method.  Returns an
    immutable tuple of ProductionComponentInspectionResult objects.

    The results record what is currently compatible, what is incompatible,
    and what must be built before real component integration is safe.

    Returns
    -------
    tuple[ProductionComponentInspectionResult, ...]
        Immutable ordered tuple of inspection results for the known
        production component classes.
    """
    from mpl_sim.components.accumulator import AccumulatorComponent  # noqa: PLC0415
    from mpl_sim.components.base import Component  # noqa: PLC0415
    from mpl_sim.components.condenser import CondenserComponent  # noqa: PLC0415
    from mpl_sim.components.evaporator import EvaporatorComponent  # noqa: PLC0415
    from mpl_sim.components.pipe import Pipe  # noqa: PLC0415
    from mpl_sim.components.pump import PumpComponent  # noqa: PLC0415

    known_classes = (
        Component,
        Pipe,
        PumpComponent,
        AccumulatorComponent,
        EvaporatorComponent,
        CondenserComponent,
    )
    return tuple(inspect_production_component_contract(cls) for cls in known_classes)
