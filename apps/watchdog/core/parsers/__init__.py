"""Importing this package registers all log parsers."""
from apps.watchdog.core.parsers import json_log, syslog, text  # noqa: F401
