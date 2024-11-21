import os
import json
import time
import sqlite3
import asyncio
from typing import Optional, Any, List, Dict

from inference.core.env import MODEL_CACHE_DIR
from inference.core.utils.sqlite_wrapper import SQLiteWrapper
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    InitialisePipelinePayload,
)

from coral_inference.core import logger


class PipelineCache(SQLiteWrapper):
    def __init__(
        self,
        stream_manager_client: Optional[StreamManagerClient],
        db_file_path: str = os.path.join(MODEL_CACHE_DIR, "pipelines.db"),
        table_name: str = "pipelines",
        sqlite_connection: Optional[sqlite3.Connection] = None,
    ):
        self._col_pipeline_id = "pipeline_id"
        self._col_restore_pipeline_id = "restore_pipeline_id"
        self._col_payload_name = "payload"
        self._col_updated_at = "updated_at"
        self._col_created_at = "created_at"

        self.stream_manager_client = stream_manager_client

        super().__init__(
            db_file_path=db_file_path,
            table_name=table_name,
            columns={
                self._col_payload_name: "TEXT NOT NULL",
                self._col_pipeline_id: "CHAR(36) NOT NULL",
                self._col_restore_pipeline_id: "CHAR(36) NOT NULL",
                self._col_updated_at: "INTEGER NOT NULL",
                self._col_created_at: "INTEGER NOT NULL",
            },
            connection=sqlite_connection,
        )

    def create(
        self,
        pipeline_id: str,
        payload: Any,
        sqlite_connection: Optional[sqlite3.Connection] = None,
    ):
        payload_str = json.dumps(payload)
        try:
            self.insert(
                row={
                    self._col_pipeline_id: pipeline_id,
                    self._col_restore_pipeline_id: pipeline_id,
                    self._col_payload_name: payload_str,
                    self._col_updated_at: int(time.time()),
                    self._col_created_at: int(time.time()),
                },
                connection=sqlite_connection,
                with_exclusive=True,
            )
        except Exception as e:
            logger.error(f"Failed to put pipeline {pipeline_id} to cache: {e}")
            raise RuntimeError(f"Failed to put pipeline {pipeline_id} to cache: {e}")

    def empty(self) -> bool:
        try:
            return self.count() == 0
        except Exception:
            return True

    def list(self, pipeline_ids: List[str]) -> List[str]:
        _pipeline_ids = []
        rows = self.select()
        pipeline_id_mapper = {
            r[self._col_restore_pipeline_id]: r[self._col_pipeline_id] for r in rows
        }
        for pipeline_id in pipeline_ids:
            if pipeline_id in pipeline_id_mapper:
                _pipeline_ids.append(pipeline_id_mapper[pipeline_id])
            else:
                logger.warning(f"Pipeline {pipeline_id} not found in cache")
        return _pipeline_ids

    def get(self, pipeline_id: str) -> Dict[str, Any]:
        rows = self.select()
        pipeline_id_mapper = {
            r[self._col_pipeline_id]: r[self._col_restore_pipeline_id] for r in rows
        }
        if pipeline_id in pipeline_id_mapper:
            return pipeline_id_mapper[pipeline_id]
        else:
            logger.warning(f"Pipeline {pipeline_id} not found in cache")
            return None

    def terminate(self, pipeline_id: str):
        try:
            connection: sqlite3.Connection = sqlite3.connect(
                self._db_file_path, timeout=1
            )
            cursor = connection.cursor()
            rows = self.select(cursor=cursor)
            terminate_rows = [
                r for r in rows if r[self._col_pipeline_id] == pipeline_id
            ]

            if not terminate_rows:
                logger.warning(f"No pipeline found with id {pipeline_id} to terminate")
                return

            self.delete(rows=terminate_rows, cursor=cursor)
            connection.commit()
            logger.info(
                f"Terminated pipeline {pipeline_id} -> {terminate_rows[0][self._col_restore_pipeline_id]} rows: {terminate_rows}"
            )
            cursor.close()
            connection.close()
        except Exception as exc:
            logger.debug("Failed to terminate pipeline - %s", exc)
            connection.rollback()
            raise exc

    async def restore(
        self,
        rows: List[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            connection: sqlite3.Connection = sqlite3.connect(
                self._db_file_path, timeout=1
            )
            rows = (
                self.select(connection=connection, cursor=connection.cursor())
                if rows is None
                else rows
            )
            if len(rows) > 0:
                await self._restore(rows=rows, connection=connection)
            else:
                logger.info("No pipeline to restore")
            connection.close()
        except Exception as exc:
            logger.debug("Failed to restore db - %s", exc)
            raise exc

    async def _restore(
        self,
        rows: List[Dict[str, str]],
        connection: sqlite3.Connection,
    ) -> List[Dict[str, Any]]:
        cursor = connection.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")
        except Exception as exc:
            logger.debug("Failed to obtain records - %s", exc)
            raise exc

        try:
            self.delete(rows=rows, cursor=cursor)
        except Exception as exc:
            logger.debug("Failed to delete records - %s", exc)
            connection.rollback()
            raise exc

        try:
            for r in rows:
                payload = json.loads(r[self._col_payload_name])
                pipeline_id = await self.remote_call_restore(payload=payload)
                r[self._col_restore_pipeline_id] = pipeline_id
                logger.info(
                    f"Restored pipeline {r[self._col_pipeline_id]} to {r[self._col_restore_pipeline_id]}"
                )
                self.insert(row=r, cursor=cursor)
            connection.commit()
        except Exception as exc:
            logger.debug("Failed to insert records - %s", exc)
            connection.rollback()
            raise exc

        try:
            rows = self.select(cursor=cursor)
            cursor.close()
        except Exception as exc:
            logger.debug("Failed to delete records - %s", exc)
            connection.rollback()
            raise exc

        return rows

    async def remote_call_restore(self, payload: dict):
        try:
            initialisation_request = InitialisePipelinePayload.model_validate(payload)
            response = await self.stream_manager_client.initialise_pipeline(
                initialisation_request=initialisation_request
            )
            if response.status == "success":
                return response.context.pipeline_id
            else:
                raise RuntimeError(f"Failed to call remote service: {response.status}")
        except Exception as e:
            logger.error(f"Failed to call remote service: {e}")
            raise e
