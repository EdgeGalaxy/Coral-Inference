from __future__ import annotations

import asyncio
from typing import Any, Dict


class MonitorService:
    """Monitor service abstraction placeholder."""

    def __init__(self, monitor) -> None:
        self._monitor = monitor

    async def health(self):
        """Return a tuple indicating whether monitor background tasks look healthy."""
        try:
            status = await self.status()
            running = status.get("running", getattr(self._monitor, "running", True))
            health_attr = getattr(self._monitor, "is_healthy", None)
            if callable(health_attr):
                monitor_healthy = health_attr()
            elif health_attr is not None:
                monitor_healthy = health_attr
            else:
                monitor_healthy = status.get("is_healthy", True)
            influx_info = await self.influx_status()
            influx_ok = True
            if influx_info.get("enabled"):
                influx_ok = influx_info.get("connected", False) and influx_info.get(
                    "healthy", True
                )
            healthy = bool(running) and bool(monitor_healthy) and bool(influx_ok)
            info: Dict[str, Any] = {
                "running": running,
                "is_healthy": monitor_healthy,
                "influx": influx_info,
                "pipelines": status.get("pipeline_count"),
            }
            return healthy, info
        except Exception as exc:
            return False, {"error": str(exc)}

    async def status(self) -> Dict[str, Any]:
        if hasattr(self._monitor, "get_status"):
            return await self._monitor.get_status()
        return {"running": getattr(self._monitor, "running", True)}

    async def disk_usage(self) -> Dict[str, Any]:
        if hasattr(self._monitor, "cleanup_manager"):
            manager = self._monitor.cleanup_manager
            loop = asyncio.get_event_loop()
            current_size = await loop.run_in_executor(
                None, manager._get_directory_size_sync, self._monitor.output_dir
            )
            usage_percentage = (current_size / manager.max_size_gb) * 100
            free_space = max(0, manager.max_size_gb - current_size)
            return {
                "output_dir": str(self._monitor.output_dir),
                "current_size_gb": current_size,
                "max_size_gb": manager.max_size_gb,
                "usage_percentage": usage_percentage,
                "free_space_gb": free_space,
            }
        return {}

    async def flush_cache(self) -> Dict[str, Any]:
        if hasattr(self._monitor, "results_collector"):
            await self._monitor.results_collector.flush_all_caches()
        if getattr(self._monitor, "influxdb_collector", None):
            await self._monitor.influxdb_collector.flush_buffer()
        return {"message": "Cache flushed"}

    async def trigger_cleanup(self) -> Dict[str, Any]:
        if hasattr(self._monitor, "cleanup_manager"):
            await self._monitor.cleanup_manager._cleanup_old_files()
        return {"message": "Cleanup triggered"}

    async def influx_status(self) -> Dict[str, Any]:
        if not getattr(self._monitor, "influxdb_collector", None):
            return {
                "enabled": False,
                "connected": False,
                "message": "InfluxDB collector not initialized",
            }
        collector = self._monitor.influxdb_collector
        is_healthy = False
        if getattr(collector, "connection_manager", None):
            is_healthy = await collector.connection_manager.health_check()
        return {
            "enabled": getattr(self._monitor, "enable_influxdb", False),
            "connected": collector.enabled,
            "healthy": is_healthy,
            "url": getattr(collector, "influxdb_url", None),
            "database": getattr(collector, "influxdb_database", None),
            "measurement": getattr(collector, "measurement", None),
            "buffer_size": len(getattr(collector, "metrics_buffer", []) or []),
            "last_flush_time": getattr(collector, "last_flush_time", None),
        }


__all__ = ["MonitorService"]
