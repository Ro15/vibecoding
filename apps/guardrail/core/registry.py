"""Guardrail parser + policy registries, built on the shared common core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from common.registry import Registry

_parsers = Registry("parser")
_policies = Registry("policy")


@dataclass
class PolicyEntry:
    name: str
    severity: str
    framework: str
    rtypes: tuple
    evaluate: Callable


def parser(name: str):
    return _parsers.register(name)


def get_parser(name: str) -> Callable:
    return _parsers.get(name)


def all_parsers() -> dict[str, Callable]:
    return {name: e.fn for name, e in _parsers.all().items()}


def policy(name: str, severity: str, framework: str, rtypes):
    return _policies.register(name, severity=severity, framework=framework,
                              rtypes=tuple(rtypes))


def all_policies() -> dict[str, PolicyEntry]:
    return {name: PolicyEntry(name=name, severity=e.meta["severity"],
                              framework=e.meta["framework"], rtypes=e.meta["rtypes"],
                              evaluate=e.fn)
            for name, e in _policies.all().items()}
