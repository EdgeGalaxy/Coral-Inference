from coral_inference.plugins.blocks.analytics.batch_line_counter.v1 import BatchLineCounterBlockV1
from coral_inference.plugins.blocks.visualizations.batch_line_zone.v1 import BatchLineCounterZoneVisualizationBlockV1

def load_custom_blocks():
    return [
        BatchLineCounterBlockV1,
        BatchLineCounterZoneVisualizationBlockV1,

    ]
