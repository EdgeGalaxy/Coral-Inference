"""
Monkey patch for app.py to fix timeout and deadlock issues.

This module provides robust fixes for the original app.py by patching
critical functions that can cause deadlocks, timeouts, and unresponsive behavior.

Usage:
    import inference.core.interfaces.stream_manager.manager_app.app_monkey_patch
    # Original app.py functions are now patched with robust versions
"""

import os
import uuid
from uuid import uuid4
import sys
import time
import threading
from functools import wraps
from multiprocessing import Queue
from queue import Empty
from threading import Event
from types import FrameType
from typing import Dict, Optional

from inference.core import logger
from inference.core.interfaces.camera.video_source import StreamState
from inference.core.interfaces.stream_manager.manager_app import app
from inference.core.interfaces.stream_manager.manager_app.entities import (
    PIPELINE_ID_KEY,
    REPORT_KEY,
    SOURCES_METADATA_KEY,
    STATE_KEY,
    STATUS_KEY,
    TYPE_KEY,
    CommandType,
    ErrorType,
    OperationStatus,
)
from inference.core.interfaces.stream_manager.manager_app.serialisation import (
    describe_error,
)


from inference.core.interfaces.stream_manager.manager_app.communication import (
    receive_socket_data,
    send_data_trough_socket,
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    PIPELINE_ID_KEY,
    TYPE_KEY,
    ErrorType,
)
from inference.core.interfaces.stream_manager.manager_app.app import (
    HEADER_SIZE,
    SOCKET_BUFFER_SIZE,
    handle_command,
    PROCESSES_TABLE_LOCK,
    ManagedInferencePipeline,
)
from inference.core.interfaces.stream_manager.manager_app.serialisation import (
    prepare_error_response,
    prepare_response,
)
from inference.core.interfaces.stream_manager.manager_app.errors import (
    MalformedPayloadError,
)

from coral_inference.core.inference.stream_manager.entities import ExtendCommandType


# Configuration
QUEUE_TIMEOUT = float(os.getenv("STREAM_MANAGER_QUEUE_TIMEOUT", "10.0"))
HEALTH_CHECK_TIMEOUT = float(os.getenv("STREAM_MANAGER_HEALTH_CHECK_TIMEOUT", "5.0"))
MAX_HEALTH_FAILURES = int(os.getenv("STREAM_MANAGER_MAX_HEALTH_FAILURES", "3"))
PROCESS_JOIN_TIMEOUT = float(os.getenv("STREAM_MANAGER_PROCESS_JOIN_TIMEOUT", "30.0"))
TERMINATION_GRACE_PERIOD = float(
    os.getenv("STREAM_MANAGER_TERMINATION_GRACE_PERIOD", "5.0")
)

# Global shutdown event
SHUTDOWN_EVENT = Event()

# Track pipeline health
PIPELINE_HEALTH = {}  # pipeline_id -> {'failures': int, 'last_check': float, 'marked_for_removal': bool}


def with_timeout(timeout_seconds: float, default_return=None):
    """Decorator to add timeout protection to functions"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = [default_return]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout_seconds)

            if thread.is_alive():
                logger.warning(
                    f"Function {func.__name__} timed out after {timeout_seconds}s"
                )
                return default_return

            if exception[0]:
                raise exception[0]

            return result[0]

        return wrapper

    return decorator


def safe_queue_put(queue: Queue, item, timeout: float = QUEUE_TIMEOUT) -> bool:
    """Safe queue put with timeout"""
    try:
        queue.put(item, timeout=timeout)
        return True
    except Exception as e:
        logger.warning(f"Failed to put item in queue: {e}")
        return False


def safe_queue_get(queue: Queue, timeout: float = QUEUE_TIMEOUT):
    """Safe queue get with timeout"""
    try:
        return queue.get(timeout=timeout)
    except Empty:
        raise TimeoutError(f"Queue get timed out after {timeout}s")
    except Exception as e:
        logger.warning(f"Failed to get item from queue: {e}")
        raise


def patched_get_response_ignoring_thrash(
    responses_queue: Queue, matching_request_id: str
) -> dict:
    """Patched version with timeout and retry logic"""
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries and time.time() - start_time < QUEUE_TIMEOUT * 2:
        try:
            response = safe_queue_get(responses_queue, timeout=QUEUE_TIMEOUT)
            if response[0] == matching_request_id:
                return response[1]

            logger.warning(
                f"Dropping response for request_id={response[0]} (expected {matching_request_id})"
            )

        except TimeoutError:
            retry_count += 1
            logger.warning(
                f"Retry {retry_count}/{max_retries} for request {matching_request_id}"
            )
            continue

    # Timeout fallback
    logger.error(f"Response timeout for request {matching_request_id}")
    return describe_error(
        exception=None,
        error_type=ErrorType.OPERATION_ERROR,
        public_error_message="Pipeline response timeout. Please try again.",
    )


def patched_handle_command(
    processes_table: Dict[str, app.ManagedInferencePipeline],
    request_id: str,
    pipeline_id: str,
    command: dict,
) -> dict:
    """Patched version with timeout protection"""
    if pipeline_id not in processes_table:
        return describe_error(
            exception=None,
            error_type=ErrorType.NOT_FOUND,
            public_error_message=f"Could not find InferencePipeline with id={pipeline_id}.",
        )

    managed_pipeline = processes_table[pipeline_id]

    # Check if pipeline is marked for removal
    if PIPELINE_HEALTH.get(pipeline_id, {}).get("marked_for_removal", False):
        return describe_error(
            exception=None,
            error_type=ErrorType.OPERATION_ERROR,
            public_error_message=f"Pipeline {pipeline_id} is being terminated.",
        )

    # Use timeout for operation lock
    lock_acquired = managed_pipeline.operation_lock.acquire(timeout=QUEUE_TIMEOUT)
    if not lock_acquired:
        logger.warning(f"Failed to acquire lock for pipeline {pipeline_id}")
        return describe_error(
            exception=None,
            error_type=ErrorType.OPERATION_ERROR,
            public_error_message="Pipeline is busy, try again later.",
        )

    try:
        success = safe_queue_put(managed_pipeline.command_queue, (request_id, command))
        if not success:
            return describe_error(
                exception=None,
                error_type=ErrorType.OPERATION_ERROR,
                public_error_message="Failed to send command to pipeline.",
            )

        return patched_get_response_ignoring_thrash(
            responses_queue=managed_pipeline.responses_queue,
            matching_request_id=request_id,
        )
    finally:
        managed_pipeline.operation_lock.release()


def patched_execute_termination(
    signal_number: int,
    frame: FrameType,
    processes_table: Dict[str, app.ManagedInferencePipeline],
) -> None:
    """Patched termination with timeout protection"""
    logger.info(f"Received termination signal {signal_number}")
    SHUTDOWN_EVENT.set()

    start_time = time.time()

    with app.PROCESSES_TABLE_LOCK:
        pipeline_ids = list(processes_table.keys())

        # Phase 1: Mark all for removal and send termination signals
        for pipeline_id in pipeline_ids:
            PIPELINE_HEALTH[pipeline_id] = {
                "marked_for_removal": True,
                "failures": 0,
                "last_check": time.time(),
            }

            try:
                managed_pipeline = processes_table[pipeline_id]
                process = managed_pipeline.pipeline_manager
                if process.is_alive():
                    logger.info(f"Terminating pipeline: {pipeline_id}")
                    process.terminate()
            except Exception as e:
                logger.error(f"Error terminating pipeline {pipeline_id}: {e}")

        # Phase 2: Wait for graceful shutdown
        time.sleep(TERMINATION_GRACE_PERIOD)

        # Phase 3: Force kill and cleanup remaining processes
        for pipeline_id in pipeline_ids:
            if pipeline_id not in processes_table:
                continue

            managed_pipeline = processes_table[pipeline_id]
            process = managed_pipeline.pipeline_manager

            try:
                if process.is_alive():
                    logger.warning(f"Force killing pipeline: {pipeline_id}")
                    process.kill()

                # Join with timeout
                join_thread = threading.Thread(target=process.join)
                join_thread.start()
                join_thread.join(timeout=PROCESS_JOIN_TIMEOUT)

                if join_thread.is_alive():
                    logger.error(
                        f"Pipeline {pipeline_id} failed to join within timeout"
                    )
                else:
                    logger.info(f"Pipeline {pipeline_id} joined successfully")

            except Exception as e:
                logger.error(f"Error during cleanup of pipeline {pipeline_id}: {e}")
            finally:
                # Always remove from table
                if pipeline_id in processes_table:
                    del processes_table[pipeline_id]

    total_time = time.time() - start_time
    logger.info(f"Termination completed in {total_time:.2f}s")
    sys.exit(0)


def patched_join_inference_pipeline(
    processes_table: Dict[str, app.ManagedInferencePipeline], pipeline_id: str
) -> None:
    """Patched join with timeout"""
    with app.PROCESSES_TABLE_LOCK:
        if pipeline_id not in processes_table:
            logger.warning(f"Pipeline {pipeline_id} not found for joining")
            return

        managed_pipeline = processes_table[pipeline_id]
        PIPELINE_HEALTH[pipeline_id] = {
            "marked_for_removal": True,
            "failures": 0,
            "last_check": time.time(),
        }

    try:
        inference_pipeline_manager = managed_pipeline.pipeline_manager

        # Join with timeout in separate thread
        join_thread = threading.Thread(target=inference_pipeline_manager.join)
        join_thread.start()
        join_thread.join(timeout=PROCESS_JOIN_TIMEOUT)

        if join_thread.is_alive():
            logger.warning(f"Pipeline {pipeline_id} join timeout, force terminating")
            inference_pipeline_manager.terminate()
            time.sleep(1)
            if inference_pipeline_manager.is_alive():
                inference_pipeline_manager.kill()

        with app.PROCESSES_TABLE_LOCK:
            if pipeline_id in processes_table:
                del processes_table[pipeline_id]
                logger.info(f"Pipeline {pipeline_id} removed from table")

    except Exception as e:
        logger.error(f"Error joining pipeline {pipeline_id}: {e}")
        # Ensure cleanup even on error
        with app.PROCESSES_TABLE_LOCK:
            if pipeline_id in processes_table:
                del processes_table[pipeline_id]
    finally:
        # Clean up health tracking
        PIPELINE_HEALTH.pop(pipeline_id, None)


def perform_safe_health_check(
    pipeline_id: str, managed_pipeline: app.ManagedInferencePipeline
) -> bool:
    """Perform health check with timeout protection"""
    try:
        command = {
            TYPE_KEY: CommandType.STATUS,
            PIPELINE_ID_KEY: pipeline_id,
        }

        start_time = time.time()
        response = patched_handle_command(
            processes_table=app.PROCESSES_TABLE,
            request_id=uuid.uuid4().hex,
            pipeline_id=pipeline_id,
            command=command,
        )

        duration = time.time() - start_time
        if duration > HEALTH_CHECK_TIMEOUT:
            logger.warning(f"Health check for {pipeline_id} took {duration:.2f}s")
            return False

        # Check response validity
        if response.get(STATUS_KEY) != OperationStatus.SUCCESS:
            return False

        # Check if sources are depleted
        if REPORT_KEY in response and SOURCES_METADATA_KEY in response[REPORT_KEY]:
            all_sources_statuses = set(
                source_metadata[STATE_KEY]
                for source_metadata in response[REPORT_KEY][SOURCES_METADATA_KEY]
                if STATE_KEY in source_metadata
            )

            if all_sources_statuses and all_sources_statuses.issubset(
                {StreamState.ENDED, StreamState.ERROR}
            ):
                logger.info(
                    f"All sources depleted in pipeline {pipeline_id}, scheduling termination"
                )
                # Schedule async termination
                threading.Thread(
                    target=lambda: terminate_pipeline_async(pipeline_id), daemon=True
                ).start()
                return False

        return True

    except Exception as e:
        logger.warning(f"Health check failed for {pipeline_id}: {e}")
        return False


def terminate_pipeline_async(pipeline_id: str) -> None:
    """Async pipeline termination"""
    try:
        command = {
            TYPE_KEY: CommandType.TERMINATE,
            PIPELINE_ID_KEY: pipeline_id,
        }
        response = patched_handle_command(
            processes_table=app.PROCESSES_TABLE,
            request_id=uuid.uuid4().hex,
            pipeline_id=pipeline_id,
            command=command,
        )

        if response.get(STATUS_KEY) == OperationStatus.SUCCESS:
            patched_join_inference_pipeline(
                processes_table=app.PROCESSES_TABLE, pipeline_id=pipeline_id
            )
        else:
            logger.error(f"Failed to terminate pipeline {pipeline_id}: {response}")
            force_cleanup_pipeline(pipeline_id)

    except Exception as e:
        logger.error(f"Error terminating pipeline {pipeline_id}: {e}")
        force_cleanup_pipeline(pipeline_id)


def force_cleanup_pipeline(pipeline_id: str) -> None:
    """Force cleanup of failed pipeline"""
    try:
        with app.PROCESSES_TABLE_LOCK:
            if pipeline_id not in app.PROCESSES_TABLE:
                return

            managed_pipeline = app.PROCESSES_TABLE[pipeline_id]
            process = managed_pipeline.pipeline_manager

            logger.warning(f"Force cleaning up pipeline {pipeline_id}")

            if process.is_alive():
                process.terminate()
                time.sleep(1)
                if process.is_alive():
                    process.kill()

            del app.PROCESSES_TABLE[pipeline_id]
            logger.info(f"Pipeline {pipeline_id} force removed")

    except Exception as e:
        logger.error(f"Error during force cleanup of {pipeline_id}: {e}")
    finally:
        PIPELINE_HEALTH.pop(pipeline_id, None)


def patched_check_process_health() -> None:
    """Patched health check with timeout protection"""
    logger.info("Starting patched health check daemon")

    while not SHUTDOWN_EVENT.is_set():
        try:
            start_time = time.time()
            total_ram_usage = app._get_current_process_ram_usage_mb()

            with app.PROCESSES_TABLE_LOCK:
                pipelines_to_check = list(app.PROCESSES_TABLE.items())

            # Process health checks outside of lock to prevent blocking
            pipelines_to_remove = []

            for pipeline_id, managed_pipeline in pipelines_to_check:
                try:
                    # Initialize health tracking if needed
                    if pipeline_id not in PIPELINE_HEALTH:
                        PIPELINE_HEALTH[pipeline_id] = {
                            "failures": 0,
                            "last_check": time.time(),
                            "marked_for_removal": False,
                        }

                    # Skip if marked for removal
                    if PIPELINE_HEALTH[pipeline_id]["marked_for_removal"]:
                        continue

                    process = managed_pipeline.pipeline_manager

                    # Check if process is alive
                    if not process.is_alive():
                        logger.warning(f"Pipeline {pipeline_id} is not alive")
                        pipelines_to_remove.append(pipeline_id)
                        continue

                    # Update RAM usage safely
                    try:
                        process_ram_usage_mb = app._get_process_memory_usage_mb(
                            process=process
                        )
                        managed_pipeline.ram_usage_queue.append(process_ram_usage_mb)
                        total_ram_usage += process_ram_usage_mb
                    except Exception as e:
                        logger.warning(
                            f"Failed to get RAM usage for {pipeline_id}: {e}"
                        )
                        PIPELINE_HEALTH[pipeline_id]["failures"] += 1

                    # Check RAM limits
                    if (
                        app.STREAM_MANAGER_MAX_RAM_MB is not None
                        and total_ram_usage > app.STREAM_MANAGER_MAX_RAM_MB
                    ):
                        logger.warning(f"Pipeline {pipeline_id} exceeds RAM limit")

                    # Skip idle pipelines for status checks
                    if managed_pipeline.is_idle:
                        continue

                    # Perform health check with timeout
                    health_check_success = perform_safe_health_check(
                        pipeline_id, managed_pipeline
                    )

                    if health_check_success:
                        PIPELINE_HEALTH[pipeline_id]["failures"] = 0
                        PIPELINE_HEALTH[pipeline_id]["last_check"] = time.time()
                    else:
                        PIPELINE_HEALTH[pipeline_id]["failures"] += 1
                        logger.warning(
                            f"Health check failed for {pipeline_id} "
                            f"(failures: {PIPELINE_HEALTH[pipeline_id]['failures']})"
                        )

                    # Mark for removal after max failures
                    if PIPELINE_HEALTH[pipeline_id]["failures"] >= MAX_HEALTH_FAILURES:
                        logger.error(
                            f"Pipeline {pipeline_id} failed too many health checks, removing"
                        )
                        pipelines_to_remove.append(pipeline_id)

                except Exception as e:
                    logger.error(f"Error checking pipeline {pipeline_id}: {e}")
                    pipelines_to_remove.append(pipeline_id)

            # Remove failed pipelines
            for pipeline_id in pipelines_to_remove:
                force_cleanup_pipeline(pipeline_id)

            # Log health check duration
            duration = time.time() - start_time
            if duration > 5.0:  # Log if health check takes too long
                logger.warning(f"Health check took {duration:.2f}s")

        except Exception as e:
            logger.error(f"Error in health check loop: {e}", exc_info=True)

        # Sleep with shutdown check
        for _ in range(10):  # Check shutdown every 0.1s for 1s total
            if SHUTDOWN_EVENT.is_set():
                break
            time.sleep(0.1)

    logger.info("Patched health check daemon stopped")


def patched_ensure_idle_pipelines_warmed_up(expected_warmed_up_pipelines: int) -> None:
    """Patched warm-up with shutdown protection"""
    logger.info(
        f"Starting patched warm-up daemon for {expected_warmed_up_pipelines} pipelines"
    )

    while not SHUTDOWN_EVENT.is_set():
        try:
            with app.PROCESSES_TABLE_LOCK:
                # Only count non-marked pipelines
                idle_pipelines = len(
                    [
                        pipeline_id
                        for pipeline_id, managed_pipeline in app.PROCESSES_TABLE.items()
                        if managed_pipeline.is_idle
                        and not PIPELINE_HEALTH.get(pipeline_id, {}).get(
                            "marked_for_removal", False
                        )
                    ]
                )

            if idle_pipelines < expected_warmed_up_pipelines:
                pipeline_id = app.spawn_managed_pipeline_process(
                    processes_table=app.PROCESSES_TABLE
                )
                if pipeline_id:
                    logger.info(f"Spawned warm-up pipeline: {pipeline_id}")
                    PIPELINE_HEALTH[pipeline_id] = {
                        "failures": 0,
                        "last_check": time.time(),
                        "marked_for_removal": False,
                    }
                else:
                    logger.warning("Failed to spawn warm-up pipeline")

        except Exception as e:
            logger.error(f"Error in warm-up loop: {e}")

        # Sleep with shutdown check
        for _ in range(50):  # Check every 0.1s for 5s total
            if SHUTDOWN_EVENT.is_set():
                break
            time.sleep(0.1)

    logger.info("Patched warm-up daemon stopped")


def rewrite_handle(self) -> None:
    pipeline_id: Optional[str] = None
    request_id = str(uuid4())
    try:
        data = receive_socket_data(
            source=self.request,
            header_size=HEADER_SIZE,
            buffer_size=SOCKET_BUFFER_SIZE,
        )
        data[TYPE_KEY] = ExtendCommandType(data[TYPE_KEY])
        if data[TYPE_KEY] is ExtendCommandType.LIST_PIPELINES:
            return self._list_pipelines(request_id=request_id)
        if data[TYPE_KEY] is ExtendCommandType.INIT:
            return self._initialise_pipeline(request_id=request_id, command=data)
        if data[TYPE_KEY] is ExtendCommandType.WEBRTC:
            return self._start_webrtc(request_id=request_id, command=data)

        pipeline_id = data[PIPELINE_ID_KEY]
        if data[TYPE_KEY] is ExtendCommandType.TERMINATE:
            self._terminate_pipeline(
                request_id=request_id, pipeline_id=pipeline_id, command=data
            )
        else:
            response = handle_command(
                processes_table=self._processes_table,
                request_id=request_id,
                pipeline_id=pipeline_id,
                command=data,
            )
            serialised_response = prepare_response(
                request_id=request_id, response=response, pipeline_id=pipeline_id
            )
            send_data_trough_socket(
                target=self.request,
                header_size=HEADER_SIZE,
                data=serialised_response,
                request_id=request_id,
                pipeline_id=pipeline_id,
            )
    except (KeyError, ValueError, MalformedPayloadError) as error:
        logger.exception(
            f"Invalid payload in processes manager. error={error} request_id={request_id}..."
        )
        payload = prepare_error_response(
            request_id=request_id,
            error=error,
            error_type=ErrorType.INVALID_PAYLOAD,
            pipeline_id=pipeline_id,
        )
        send_data_trough_socket(
            target=self.request,
            header_size=HEADER_SIZE,
            data=payload,
            request_id=request_id,
            pipeline_id=pipeline_id,
        )
    except Exception as error:
        logger.error(
            f"Internal error in processes manager. error={error} request_id={request_id}..."
        )
        payload = prepare_error_response(
            request_id=request_id,
            error=error,
            error_type=ErrorType.INTERNAL_ERROR,
            pipeline_id=pipeline_id,
        )
        send_data_trough_socket(
            target=self.request,
            header_size=HEADER_SIZE,
            data=payload,
            request_id=request_id,
            pipeline_id=pipeline_id,
        )


def rewrite_execute_termination(
    signal_number: int,
    frame: FrameType,
    processes_table: Dict[str, ManagedInferencePipeline],
) -> None:
    with PROCESSES_TABLE_LOCK:
        pipeline_ids = list(processes_table.keys())
        for pipeline_id in pipeline_ids:
            logger.info(f"Terminating pipeline: {pipeline_id}")
            processes_table[pipeline_id].pipeline_manager.terminate()
            logger.info(f"Pipeline: {pipeline_id} terminated.")
            logger.info(f"Joining pipeline: {pipeline_id}")
            processes_table[pipeline_id].pipeline_manager.join()
            logger.info(f"Pipeline: {pipeline_id} joined.")
        logger.info(f"Termination handler completed.")
        sys.exit(0)
