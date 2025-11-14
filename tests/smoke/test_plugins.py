import os

import coral_inference.plugins as plugins

from coral_inference.plugins.blocks.analytics.batch_line_counter.v1 import (
    BatchLineCounterBlockV1,
)
from coral_inference.plugins.blocks.visualizations.batch_line_zone.v1 import (
    BatchLineCounterZoneVisualizationBlockV1,
)


def test_plugins_register_blocks_and_env():
    blocks = plugins.load_blocks()
    assert BatchLineCounterBlockV1 in blocks
    assert BatchLineCounterZoneVisualizationBlockV1 in blocks
    assert os.environ.get("WORKFLOWS_PLUGINS") == "coral_inference.plugins"
