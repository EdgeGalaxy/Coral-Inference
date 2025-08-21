


def get_influxdb_metrics():
    return {
        'metrics_host': INFLUXDB_METRICS_URL,
        'metrics_token': INFLUXDB_METRICS_TOKEN,
        'metrics_org': INFLUXDB_METRICS_ORG,
        'metrics_bucket': INFLUXDB_METRICS_BUCKET
    }
