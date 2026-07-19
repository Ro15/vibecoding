"""Watchdog parser + detector registries, built on the shared common core."""
from __future__ import annotations

from typing import Callable

from common.registry import Registry

_parsers = Registry("parser")
_detectors = Registry("detector")


def parser(name: str):
    return _parsers.register(name)


def get_parser(name: str) -> Callable:
    return _parsers.get(name)


def all_parsers() -> dict[str, Callable]:
    return {name: e.fn for name, e in _parsers.all().items()}


def detector(name: str):
    return _detectors.register(name)


def get_detector(name: str) -> Callable:
    return _detectors.get(name)


def all_detectors() -> dict[str, Callable]:
    return {name: e.fn for name, e in _detectors.all().items()}
