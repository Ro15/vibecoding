"""Plugin registries for billing-export providers and detection rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

_PROVIDERS: dict[str, Callable] = {}
_RULES: dict[str, "RuleEntry"] = {}


@dataclass
class RuleEntry:
    name: str
    category: str
    evaluate: Callable


def provider(name: str):
    def decorator(fn: Callable):
        _PROVIDERS[name] = fn
        return fn

    return decorator


def get_provider(name: str) -> Callable:
    if name not in _PROVIDERS:
        raise KeyError(f"unknown provider: {name!r}")
    return _PROVIDERS[name]


def all_providers() -> dict[str, Callable]:
    return dict(_PROVIDERS)


def rule(name: str, category: str):
    def decorator(fn: Callable):
        _RULES[name] = RuleEntry(name=name, category=category, evaluate=fn)
        return fn

    return decorator


def all_rules() -> dict[str, RuleEntry]:
    return dict(_RULES)


def severity_for(monthly_savings: float) -> str:
    if monthly_savings >= 50.0:
        return "high"
    if monthly_savings >= 10.0:
        return "medium"
    return "low"
