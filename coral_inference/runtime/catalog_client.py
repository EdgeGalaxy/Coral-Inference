from typing import Optional

import requests

from coral_inference.runtime.contracts import RuntimeLockfile


class ReefRuntimePackageClient:
    def __init__(
        self,
        *,
        backend_url: str,
        internal_secret: str,
        timeout: int = 60,
    ) -> None:
        self._backend_url = backend_url.rstrip("/")
        self._internal_secret = internal_secret
        self._timeout = timeout

    def fetch_deployment_lockfile(
        self,
        *,
        workspace_id: str,
        deployment_id: str,
        bearer_token: Optional[str] = None,
    ) -> RuntimeLockfile:
        url = (
            f"{self._backend_url}/workspaces/{workspace_id}/deployments/"
            f"{deployment_id}/runtime-package/noauth"
        )
        token = bearer_token or self._internal_secret
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Internal-Secret": self._internal_secret,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return RuntimeLockfile.model_validate(response.json())
