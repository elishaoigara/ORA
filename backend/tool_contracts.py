"""Typed tool contracts and shared safety policy for ORA Phase 6."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


RISK_CLASSES = frozenset({
    "read_only",
    "personal_change",
    "external_write",
    "external_communication",
    "irreversible",
    "financial",
})

APPROVAL_REQUIRED_RISKS = frozenset({
    "external_write",
    "external_communication",
    "irreversible",
    "financial",
})


def _type_matches(value: Any, type_name: str) -> bool:
    if type_name in {"any", "object"}:
        return True
    if type_name == "str":
        return isinstance(value, str)
    if type_name == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "bool":
        return isinstance(value, bool)
    if type_name == "dict":
        return isinstance(value, dict)
    if type_name == "list":
        return isinstance(value, list)
    return True


class ToolContractError(ValueError):
    """Raised when a tool request violates its typed contract."""


@dataclass(frozen=True)
class ToolSpec:
    """Machine-readable contract shared by the registry, API, and approval UI."""

    name: str
    version: str = "1"
    description: str = ""
    input_schema: dict[str, dict[str, Any]] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=lambda: {"ok": "bool"})
    risk: str = "read_only"
    side_effect: str = "none"
    action_type: str | None = None
    timeout_seconds: int = 30
    max_retries: int = 0
    approval_required: bool | None = None

    def __post_init__(self) -> None:
        if self.risk not in RISK_CLASSES:
            raise ValueError(f"Unknown risk class: {self.risk}")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")

    @property
    def needs_approval(self) -> bool:
        if self.approval_required is not None:
            return bool(self.approval_required)
        return self.risk in APPROVAL_REQUIRED_RISKS

    def validate(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        values = payload or {}
        if not isinstance(values, dict):
            raise ToolContractError("tool input must be an object")

        errors: list[str] = []
        for name, definition in self.input_schema.items():
            required = bool(definition.get("required", False))
            if required and (name not in values or values[name] in (None, "")):
                errors.append(f"{name} is required")
                continue
            if name in values and values[name] is not None:
                expected = str(definition.get("type", "any"))
                if not _type_matches(values[name], expected):
                    errors.append(f"{name} must be {expected}")

        if errors:
            raise ToolContractError("; ".join(errors))
        return values

    def idempotency_key(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return f"tool:{self.name}:v{self.version}:{digest}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "risk": self.risk,
            "side_effect": self.side_effect,
            "action_type": self.action_type,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "requires_approval": self.needs_approval,
        }
