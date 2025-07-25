import os

from coral_inference.plugins.blocks import load_custom_blocks
from coral_inference.plugins.kinds import load_custom_kinds


def load_blocks():
    return load_custom_blocks()


def load_kinds():
    return load_custom_kinds()


# inference load this module, load_blocks and load_kinds will be called
os.environ["WORKFLOWS_PLUGINS"] = "coral_inference.plugins"
