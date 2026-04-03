from typing import Dict, Optional

from coral_inference.runtime.contracts import (
    MaterializedModelPackage,
    RuntimeLockfile,
)


class RuntimeRegistry:
    def __init__(self) -> None:
        self._lockfiles: Dict[str, RuntimeLockfile] = {}
        self._packages: Dict[str, MaterializedModelPackage] = {}

    def register_lockfile(self, lockfile: RuntimeLockfile) -> None:
        self._lockfiles[lockfile.deployment_id] = lockfile

    def get_lockfile(self, deployment_id: str) -> Optional[RuntimeLockfile]:
        return self._lockfiles.get(deployment_id)

    def register_materialized_package(
        self,
        package: MaterializedModelPackage,
    ) -> None:
        self._packages[package.package_id] = package

    def get_materialized_package(
        self,
        package_id: str,
    ) -> Optional[MaterializedModelPackage]:
        return self._packages.get(package_id)
