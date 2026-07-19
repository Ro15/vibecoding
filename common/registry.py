"""Generic named-plugin registry.

The single mechanism behind every app's extensibility: a plugin (a parser, a
rule, a detector, an alert sink) self-registers under a name via a decorator,
and the engine iterates whatever is registered. Adding one is a new file with
zero edits to the engine — O(1) extension cost.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RegistryEntry:
    name: str
    fn: Callable
    meta: dict = field(default_factory=dict)


class Registry:
    """A registry of named callables, each with optional metadata."""

    def __init__(self, kind: str):
        self.kind = kind
        self._entries: dict[str, RegistryEntry] = {}

    def register(self, name: str, **meta):
        def decorator(fn: Callable):
            self._entries[name] = RegistryEntry(name=name, fn=fn, meta=meta)
            return fn

        return decorator

    def get(self, name: str) -> Callable:
        if name not in self._entries:
            raise KeyError(f"unknown {self.kind}: {name!r}")
        return self._entries[name].fn

    def entry(self, name: str) -> RegistryEntry:
        if name not in self._entries:
            raise KeyError(f"unknown {self.kind}: {name!r}")
        return self._entries[name]

    def all(self) -> dict[str, RegistryEntry]:
        return dict(self._entries)

    def names(self) -> list[str]:
        return list(self._entries)

    def pop(self, name: str, default=None):
        """Remove an entry (used by tests to keep the global registry clean)."""
        return self._entries.pop(name, default)


def severity_bands(value: float, high: float, medium: float) -> str:
    """Shared severity classifier used by cost, risk, and alert scoring."""
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"
