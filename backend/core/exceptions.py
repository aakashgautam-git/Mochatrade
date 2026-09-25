"""Map domain errors onto HTTP, so a user mistake is never a 500."""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default

from .runner import PolicyUnavailable, ScenarioUnavailable


def api_exception_handler(exc, context):
    if isinstance(exc, PolicyUnavailable):
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, ScenarioUnavailable):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, ValueError):
        # e.g. queueing an action at a tick the engine has already passed.
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return drf_default(exc, context)
