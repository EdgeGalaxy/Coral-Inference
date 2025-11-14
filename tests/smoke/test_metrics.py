import datetime
from queue import Empty

import pytest

from coral_inference.core.inference.stream.metric_sink import MetricSink


class DummyClient:
    def __init__(self, host, token, database):  # noqa: ARG002
        self.written_batches = []

    def query(self, query):  # noqa: ARG002
        return [{"connection_test": 1}]

    def write(self, points):
        self.written_batches.append(points)

    def close(self):
        pass


class DummyPoint:
    def __init__(self, measurement):
        self.measurement = measurement
        self.tags = {}
        self.fields = {}
        self.timestamp = None

    def tag(self, key, value):
        self.tags[key] = value
        return self

    def field(self, key, value):
        self.fields[key] = value
        return self

    def time(self, ts):
        self.timestamp = ts
        return self


class DummyFrame:
    def __init__(self):
        self.source_id = "cam-1"
        self.frame_timestamp = datetime.datetime.now()


def test_metric_sink_batches_and_writes(monkeypatch):
    module = "coral_inference.core.inference.stream.metric_sink"
    monkeypatch.setattr(f"{module}.INFLUXDB_METRICS_URL", "http://localhost")
    monkeypatch.setattr(f"{module}.INFLUXDB_METRICS_TOKEN", "token")
    monkeypatch.setattr(f"{module}.INFLUXDB_METRICS_DATABASE", "db")
    monkeypatch.setattr(f"{module}.InfluxDBClient3", DummyClient)
    monkeypatch.setattr(f"{module}.Point", DummyPoint)
    monkeypatch.setattr(MetricSink, "_start_worker_thread", lambda self: None)

    sink = MetricSink.init(
        pipeline_id="pipe-1",
        selected_fields=["prediction.score"],
        queue_size=10,
    )

    sink.on_prediction(
        predictions={"prediction": {"score": 0.9}},
        video_frame=DummyFrame(),
    )

    queue_item = sink._metrics_queue.get(timeout=1)
    sink._process_batch_metrics([queue_item])

    assert sink._client.written_batches, "No metrics written"
    point = sink._client.written_batches[0][0]
    assert point.fields["prediction.score"] == 0.9
    assert point.tags["pipeline_id"] == "pipe-1"
