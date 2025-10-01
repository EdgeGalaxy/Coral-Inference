import cv2 as cv
import numpy as np
import pytest
from pydantic import ValidationError
from typing import List, Tuple

from coral_inference.plugins.blocks.visualizations.batch_line_zone.v1 import (
    BatchLineCounterZoneVisualizationBlockV1,
    BatchLineCounterZoneVisualizationManifest,
)
from inference.core.workflows.execution_engine.entities.base import (
    ImageParentMetadata,
    WorkflowImageData,
)


def test_batch_line_counter_zone_validation_when_invalid_image_is_given() -> None:
    # given
    data = {
        "type": "coral_core/batch_line_counter_visualization@v1",
        "name": "batch_line_counter_zone_1",
        "zones": "$inputs.zones",
        "images": "invalid",
        "color": "#FFFFFF",
        "opacity": 0.5,
        "thickness": 3,
        "text_thickness": 1,
        "text_scale": 2.0,
        "count_ins": ["$steps.batch_line_counter.count_in"],
        "count_outs": ["$steps.batch_line_counter.count_out"],
    }

    # when
    with pytest.raises(ValidationError):
        _ = BatchLineCounterZoneVisualizationManifest.model_validate(data)


def test_batch_line_counter_zone_visualization_block() -> None:
    # given
    block = BatchLineCounterZoneVisualizationBlockV1()

    start_images = [
        np.random.randint(0, 255, (1000, 1000, 3), dtype=np.uint8),
        np.random.randint(0, 255, (800, 600, 3), dtype=np.uint8),
    ]

    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some1"),
            numpy_image=start_images[0],
        ),
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some2"),
            numpy_image=start_images[1],
        ),
    ]

    zones = [
        [(10, 10), (100, 100)],
        [(20, 20), (200, 200)],
    ]

    count_ins = [7, 3]
    count_outs = [1, 5]

    outputs = block.run(
        images=images,
        zones=zones,
        copy_image=True,
        color="#FF0000",
        opacity=1.0,
        thickness=3,
        text_thickness=1,
        text_scale=1.0,
        count_ins=count_ins,
        count_outs=count_outs,
    )

    # then
    assert isinstance(outputs, list)
    assert len(outputs) == 2

    for i, output in enumerate(outputs):
        assert isinstance(output, dict)
        assert "image" in output
        assert hasattr(output["image"], "numpy_image")

        # dimensions of output match input
        assert output.get("image").numpy_image.shape == start_images[i].shape
        # check if the image is modified
        assert not np.array_equal(output.get("image").numpy_image, start_images[i])


def test_batch_line_counter_zone_visualization_block_with_copy_false() -> None:
    # given
    block = BatchLineCounterZoneVisualizationBlockV1()

    start_image = np.random.randint(0, 255, (500, 500, 3), dtype=np.uint8)
    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some"),
            numpy_image=start_image,
        )
    ]

    zones = [[(50, 50), (150, 150)]]
    count_ins = [2]
    count_outs = [4]

    outputs = block.run(
        images=images,
        zones=zones,
        copy_image=False,
        color="#00FF00",
        opacity=0.5,
        thickness=2,
        text_thickness=2,
        text_scale=1.5,
        count_ins=count_ins,
        count_outs=count_outs,
    )

    # then
    assert len(outputs) == 1
    output = outputs[0]
    assert isinstance(output, dict)
    assert "image" in output
    assert hasattr(output["image"], "numpy_image")
    assert output.get("image").numpy_image.shape == start_image.shape


def test_batch_line_counter_zone_visualization_block_empty_batch() -> None:
    # given
    block = BatchLineCounterZoneVisualizationBlockV1()

    # when
    outputs = block.run(
        images=[],
        zones=[],
        copy_image=True,
        color="#FF0000",
        opacity=1.0,
        thickness=3,
        text_thickness=1,
        text_scale=1.0,
        count_ins=[],
        count_outs=[],
    )

    # then
    assert outputs == []


def test_batch_line_counter_zone_visualization_block_single_item() -> None:
    # given
    block = BatchLineCounterZoneVisualizationBlockV1()

    start_image = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)
    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="single"),
            numpy_image=start_image,
        )
    ]

    zones = [[(30, 30), (100, 100)]]
    count_ins = [10]
    count_outs = [5]

    outputs = block.run(
        images=images,
        zones=zones,
        copy_image=True,
        color="#0000FF",
        opacity=0.8,
        thickness=4,
        text_thickness=1,
        text_scale=2.0,
        count_ins=count_ins,
        count_outs=count_outs,
    )

    # then
    assert len(outputs) == 1
    output = outputs[0]
    assert isinstance(output, dict)
    assert "image" in output
    assert hasattr(output["image"], "numpy_image")
    assert output.get("image").numpy_image.shape == start_image.shape
    assert not np.array_equal(output.get("image").numpy_image, start_image)


def test_batch_line_counter_zone_visualization_block_cache_usage() -> None:
    # given
    block = BatchLineCounterZoneVisualizationBlockV1()

    # Create two images with the same dimensions
    start_image1 = np.random.randint(0, 255, (400, 400, 3), dtype=np.uint8)
    start_image2 = np.random.randint(0, 255, (400, 400, 3), dtype=np.uint8)

    images1 = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="cache1"),
            numpy_image=start_image1,
        )
    ]

    images2 = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="cache2"),
            numpy_image=start_image2,
        )
    ]

    # Same zone and parameters should use cache
    zones = [[(40, 40), (140, 140)]]
    count_ins = [3]
    count_outs = [7]

    # when - first run
    outputs1 = block.run(
        images=images1,
        zones=zones,
        copy_image=True,
        color="#FF0000",
        opacity=0.5,
        thickness=2,
        text_thickness=1,
        text_scale=1.0,
        count_ins=count_ins,
        count_outs=count_outs,
    )

    # when - second run with same parameters (should use cache)
    outputs2 = block.run(
        images=images2,
        zones=zones,
        copy_image=True,
        color="#FF0000",
        opacity=0.5,
        thickness=2,
        text_thickness=1,
        text_scale=1.0,
        count_ins=count_ins,
        count_outs=count_outs,
    )

    # then
    assert len(outputs1) == 1
    assert len(outputs2) == 1
    # Both should be processed successfully, even though they use the same cached mask
    assert outputs1[0]["image"].numpy_image.shape == start_image1.shape
    assert outputs2[0]["image"].numpy_image.shape == start_image2.shape
