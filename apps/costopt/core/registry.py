"""CostOpt's provider + rule registries, built on the shared common core."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from common.registry import Registry

_providers = Registry("provider")
_rules = Registry("rule")


@dataclass
class RuleEntry:
    name: str
    category: str
    evaluate: Callable


# --- providers (billing-export parsers) ---

def provider(name: str):
    return _providers.register(name)


def get_provider(name: str) -> Callable:
    return _providers.get(name)


def all_providers() -> dict[str, Callable]:
    return {name: e.fn for name, e in _providers.all().items()}


# --- rules (detection logic) ---

def rule(name: str, category: str):
    return _rules.register(name, category=category)


def all_rules() -> dict[str, RuleEntry]:
    return {name: RuleEntry(name=name, category=e.meta["category"], evaluate=e.fn)
            for name, e in _rules.all().items()}


def severity_for(monthly_savings: float, policies: dict | None = None) -> str:
    from apps.costopt.core.policies import severity_for as _sev
    return _sev(monthly_savings, policies)


# Test hooks: keep the module-global registries pristine across tests.
_PROVIDERS = _providers
_RULES = _rules
