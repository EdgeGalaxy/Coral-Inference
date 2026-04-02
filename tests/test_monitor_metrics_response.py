from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "docker"))

from config.core.monitor.metrics_response_builder import build_metrics_response_from_summary
from config.core.pipeline.pipeline_routes import _normalise_pipeline_status_response


def test_build_metrics_response_from_summary_source_level_is_not_duplicated():
    summary = {
        "data": [
            {
                "time": "2026-04-02T00:00:00Z",
                "source_id": "cam-1",
                "avg_frame_decoding_latency": 10,
                "avg_inference_latency": 20,
                "avg_e2e_latency": 30,
            },
            {
                "time": "2026-04-02T00:00:10Z",
                "source_id": "cam-1",
                "avg_frame_decoding_latency": 11,
                "avg_inference_latency": 21,
                "avg_e2e_latency": 31,
            },
        ]
    }

    metrics = build_metrics_response_from_summary(summary=summary, level="source")

    assert metrics["dates"] == [
        "2026-04-02T00:00:00Z",
        "2026-04-02T00:00:10Z",
    ]
    assert [dataset["name"] for dataset in metrics["datasets"]] == [
        "Frame Decoding (cam-1)",
        "Inference Latency (cam-1)",
        "E2E Latency (cam-1)",
    ]
    assert metrics["datasets"][0]["data"] == [10.0, 11.0]
    assert metrics["datasets"][1]["data"] == [20.0, 21.0]
    assert metrics["datasets"][2]["data"] == [30.0, 31.0]


def test_build_metrics_response_from_summary_pipeline_level_uses_summary_fields():
    summary = {
        "data": [
            {
                "time": "2026-04-02T00:00:00Z",
                "avg_throughput": 5,
                "avg_source_count": 2,
                "avg_e2e_latency": 42,
            }
        ]
    }

    metrics = build_metrics_response_from_summary(summary=summary, level="pipeline")

    assert metrics["dates"] == ["2026-04-02T00:00:00Z"]
    assert [dataset["name"] for dataset in metrics["datasets"]] == [
        "Throughput",
        "Source Count",
        "E2E Latency",
    ]
    assert metrics["datasets"][0]["data"] == [5.0]
    assert metrics["datasets"][1]["data"] == [2.0]
    assert metrics["datasets"][2]["data"] == [42.0]


def test_normalise_pipeline_status_response_standardizes_report_shape():
    response = _normalise_pipeline_status_response(
        {
            "status": "warning",
            "context": {
                "request_id": "req-1",
                "pipeline_id": "pipe-1",
            },
            "report": {
                "sources_metadata": [
                    {
                        "source_id": 1,
                        "source_reference": "rtsp://demo",
                        "state": "running",
                    }
                ],
                "video_source_status_updates": [
                    {
                        "timestamp": "2026-04-02T12:00:00Z",
                        "severity": "error",
                        "event_type": "SOURCE_ERROR",
                        "payload": None,
                    }
                ],
            },
        }
    )

    assert response.status == "warning"
    assert response.context.pipeline_id == "pipe-1"
    assert response.report["sources_metadata"][0]["state"] == "RUNNING"
    assert response.report["video_source_status_updates"][0]["severity"] == "ERROR"
    assert response.report["video_source_status_updates"][0]["payload"] == {}
