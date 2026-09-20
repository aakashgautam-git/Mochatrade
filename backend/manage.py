#!/usr/bin/env python
"""Django command-line utility for MochaTrade Crisis Command."""
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ImportError(
            "Django is not installed or the virtualenv is not active. "
            "Run `make setup` from the repo root."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
