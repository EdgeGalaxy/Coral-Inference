

from inference.core.managers.pingback import PingbackInfo


def get_influxdb_metrics():
    return {
        'metrics_host': INFLUXDB_METRICS_URL,
        'metrics_token': INFLUXDB_METRICS_TOKEN,
        'metrics_org': INFLUXDB_METRICS_ORG,
        'metrics_bucket': INFLUXDB_METRICS_BUCKET
    }


class PatchPingbackInfo(PingbackInfo):
    def __init__(self, manager):
        super().__init__(manager)
        self.environment_info = self.environment_info | get_influxdb_metrics()