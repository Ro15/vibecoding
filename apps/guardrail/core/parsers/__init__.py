"""Importing this package registers all IaC parsers."""
from apps.guardrail.core.parsers import cloudformation, hcl, tfplan  # noqa: F401
