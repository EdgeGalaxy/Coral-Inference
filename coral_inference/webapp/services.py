from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Callable
from datetime import datetime, timezone
import inspect


@dataclass
class HealthStatus:
    healthy: bool
    details: Dict[str, Any]


class HealthService:
    """Simple health probe aggregator for WebApp."""

    def __init__(self) -> None:
        self._checks: list[tuple[str, Callable[..., Any]]] = []

    def register_check(self, name: str, check_func) -> None:
        """Register a check callable returning (healthy: bool, info: Dict)."""
        self._checks.append((name, check_func))

    async def _run_check(self, func: Callable[..., Any]) -> Any:
        """Run a health check and handle sync/async callables uniformly."""
        if inspect.iscoroutinefunction(func):
            return await func()
        result = func()
        if inspect.isawaitable(result):
            return await result
        return result

    async def readiness(self) -> HealthStatus:
        checks: Dict[str, Any] = {}
        healthy = True
        for name, func in self._checks:
            try:
                result = await self._run_check(func)
            except Exception as exc:  # pragma: no cover - defensive
                healthy = False
                checks[name] = {"healthy": False, "error": str(exc)}
                continue
            if isinstance(result, tuple):
                check_ok, info = result
                healthy = healthy and bool(check_ok)
                checks[name] = {"healthy": bool(check_ok), "info": info}
            else:
                healthy = healthy and bool(result)
                checks[name] = {"healthy": bool(result)}
        timestamp = datetime.now(timezone.utc).isoformat()
        return HealthStatus(
            healthy=healthy, details={"checks": checks, "timestamp": timestamp}
        )

    async def liveness(self) -> HealthStatus:
        """Liveness check: simply report the aggregator itself is alive."""
        timestamp = datetime.now(timezone.utc).isoformat()
        return HealthStatus(
            healthy=True,
            details={"checks": {"service": {"healthy": True}}, "timestamp": timestamp},
        )


__all__ = ["HealthService", "HealthStatus"]
