from typing import Any, Dict, List


def build_metrics_response_from_summary(
    summary: Dict[str, Any] | None,
    level: str | None = "pipeline",
) -> Dict[str, Any]:
    if not summary or not summary.get("data"):
        return {"dates": [], "datasets": []}

    rows = summary["data"]
    dates = sorted({row.get("time") for row in rows if row.get("time")})
    datasets: List[Dict[str, Any]] = []
    normalized_level = level or "pipeline"

    if normalized_level == "pipeline":
        bucket_map = {row.get("time"): row for row in rows if row.get("time")}
        datasets.append(
            {
                "name": "Throughput",
                "data": [
                    float(bucket_map.get(ts, {}).get("avg_throughput", 0) or 0)
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": "Source Count",
                "data": [
                    float(bucket_map.get(ts, {}).get("avg_source_count", 0) or 0)
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": "E2E Latency",
                "data": [
                    float(bucket_map.get(ts, {}).get("avg_e2e_latency", 0) or 0)
                    for ts in dates
                ],
            }
        )
        return {"dates": dates, "datasets": datasets}

    source_rows = {
        (row.get("time"), str(row.get("source_id"))): row
        for row in rows
        if row.get("time") and row.get("source_id") is not None
    }
    source_ids = sorted(
        {
            str(row.get("source_id"))
            for row in rows
            if row.get("source_id") is not None
        }
    )
    for source_id in source_ids:
        datasets.append(
            {
                "name": f"Frame Decoding ({source_id})",
                "data": [
                    float(
                        (
                            source_rows.get((ts, source_id), {}) or {}
                        ).get("avg_frame_decoding_latency", 0)
                        or 0
                    )
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": f"Inference Latency ({source_id})",
                "data": [
                    float(
                        (source_rows.get((ts, source_id), {}) or {}).get(
                            "avg_inference_latency", 0
                        )
                        or 0
                    )
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": f"E2E Latency ({source_id})",
                "data": [
                    float(
                        (source_rows.get((ts, source_id), {}) or {}).get(
                            "avg_e2e_latency", 0
                        )
                        or 0
                    )
                    for ts in dates
                ],
            }
        )

    return {"dates": dates, "datasets": datasets}
