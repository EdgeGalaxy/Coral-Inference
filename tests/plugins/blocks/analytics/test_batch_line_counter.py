import datetime
from typing import List, Tuple

import numpy as np
import pytest
import supervision as sv

from coral_inference.plugins.blocks.analytics.batch_line_counter.v1 import (
    BatchLineCounterBlockV1,
)
from inference.core.workflows.execution_engine.entities.base import (
    ImageParentMetadata,
    VideoMetadata,
    WorkflowImageData,
)


def test_batch_line_counter() -> None:
    # given
    line_segments = [[[15, 0], [15, 1000]], [[25, 0], [25, 1000]]]

    frame1_detections_batch = [
        sv.Detections(
            xyxy=np.array(
                [
                    [10, 10, 11, 11],
                    [20, 20, 21, 21],
                    [100, 100, 101, 101],
                    [200, 200, 201, 201],
                ]
            ),
            tracker_id=np.array([1, 2, 3, 4]),
        ),
        sv.Detections(
            xyxy=np.array(
                [
                    [20, 10, 21, 11],
                    [30, 20, 31, 21],
                ]
            ),
            tracker_id=np.array([1, 2]),
        ),
    ]

    frame2_detections_batch = [
        sv.Detections(
            xyxy=np.array(
                [[20, 10, 21, 21], [10, 20, 11, 11], [90, 90, 91, 91], [5, 5, 6, 6]]
            ),
            tracker_id=np.array([1, 2, 3, 5]),
        ),
        sv.Detections(
            xyxy=np.array(
                [
                    [
                        30,
                        10,
                        31,
                        11,
                    ],  # moved from left (20) to right (30) of line at x=25
                    [
                        15,
                        20,
                        16,
                        21,
                    ],  # moved from right (30) to left (15) of line at x=25
                ]
            ),
            tracker_id=np.array([1, 2]),
        ),
    ]

    metadata1 = VideoMetadata(
        video_identifier="vid_1",
        frame_number=10,
        frame_timestamp=datetime.datetime.fromtimestamp(1726570875).astimezone(
            tz=datetime.timezone.utc
        ),
    )
    metadata2 = VideoMetadata(
        video_identifier="vid_2",
        frame_number=10,
        frame_timestamp=datetime.datetime.fromtimestamp(1726570875).astimezone(
            tz=datetime.timezone.utc
        ),
    )

    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some1"),
            numpy_image=np.zeros((192, 168, 3), dtype=np.uint8),
            video_metadata=metadata1,
        ),
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some2"),
            numpy_image=np.zeros((192, 168, 3), dtype=np.uint8),
            video_metadata=metadata2,
        ),
    ]

    line_counter_block = BatchLineCounterBlockV1()

    # when - frame 1
    frame1_results = line_counter_block.run(
        images=images,
        detections=frame1_detections_batch,
        line_segments=line_segments,
        triggering_anchor="TOP_LEFT",
    )

    # when - frame 2
    frame2_results = line_counter_block.run(
        images=images,
        detections=frame2_detections_batch,
        line_segments=line_segments,
        triggering_anchor="TOP_LEFT",
    )

    # then - frame 1
    assert len(frame1_results) == 2
    assert frame1_results[0]["count_in"] == 0
    assert frame1_results[0]["count_out"] == 0
    assert len(frame1_results[0]["detections_in"]) == 0
    assert len(frame1_results[0]["detections_out"]) == 0

    assert frame1_results[1]["count_in"] == 0
    assert frame1_results[1]["count_out"] == 0
    assert len(frame1_results[1]["detections_in"]) == 0
    assert len(frame1_results[1]["detections_out"]) == 0

    # then - frame 2
    assert len(frame2_results) == 2
    assert frame2_results[0]["count_in"] == 1
    assert frame2_results[0]["count_out"] == 1
    assert len(frame2_results[0]["detections_in"]) == 1
    assert len(frame2_results[0]["detections_out"]) == 1

    assert frame2_results[1]["count_in"] == 1
    assert frame2_results[1]["count_out"] == 1
    assert len(frame2_results[1]["detections_in"]) == 1
    assert len(frame2_results[1]["detections_out"]) == 1


def test_batch_line_counter_no_trackers() -> None:
    # given
    line_segments = [[[15, 0], [15, 1000]]]
    detections_batch = [
        sv.Detections(
            xyxy=np.array([[10, 10, 11, 11]]),
        )
    ]
    metadata = VideoMetadata(
        video_identifier="vid_1",
        frame_number=10,
        frame_timestamp=datetime.datetime.fromtimestamp(1726570875).astimezone(
            tz=datetime.timezone.utc
        ),
    )
    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some"),
            numpy_image=np.zeros((192, 168, 3), dtype=np.uint8),
            video_metadata=metadata,
        )
    ]
    line_counter_block = BatchLineCounterBlockV1()

    # when
    with pytest.raises(
        ValueError,
        match="tracker_id not initialized, BatchLineCounterBlockV1 requires detections to be tracked",
    ):
        _ = line_counter_block.run(
            images=images,
            detections=detections_batch,
            line_segments=line_segments,
            triggering_anchor="TOP_LEFT",
        )


def test_batch_line_counter_too_short_line_segment() -> None:
    # given
    line_segments = [[[15, 0]]]
    detections_batch = [
        sv.Detections(
            xyxy=np.array([[10, 10, 11, 11]]),
            tracker_id=np.array([1]),
        )
    ]
    metadata = VideoMetadata(
        video_identifier="vid_1",
        frame_number=10,
        frame_timestamp=datetime.datetime.fromtimestamp(1726570875).astimezone(
            tz=datetime.timezone.utc
        ),
    )
    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some"),
            numpy_image=np.zeros((192, 168, 3), dtype=np.uint8),
            video_metadata=metadata,
        )
    ]
    line_counter_block = BatchLineCounterBlockV1()

    # when
    with pytest.raises(
        ValueError,
        match="BatchLineCounterBlockV1 requires line zone to be a list containing exactly 2 points",
    ):
        _ = line_counter_block.run(
            images=images,
            detections=detections_batch,
            line_segments=line_segments,
            triggering_anchor="TOP_LEFT",
        )


def test_batch_line_counter_too_long_line_segment() -> None:
    # given
    line_segments = [[[15, 0], [15, 1000], [3, 3]]]
    detections_batch = [
        sv.Detections(
            xyxy=np.array([[10, 10, 11, 11]]),
            tracker_id=np.array([1]),
        )
    ]
    metadata = VideoMetadata(
        video_identifier="vid_1",
        frame_number=10,
        frame_timestamp=datetime.datetime.fromtimestamp(1726570875).astimezone(
            tz=datetime.timezone.utc
        ),
    )
    images = [
        WorkflowImageData(
            parent_metadata=ImageParentMetadata(parent_id="some"),
            numpy_image=np.zeros((192, 168, 3), dtype=np.uint8),
            video_metadata=metadata,
        )
    ]
    line_counter_block = BatchLineCounterBlockV1()

    # when
    with pytest.raises(
        ValueError,
        match="BatchLineCounterBlockV1 requires line zone to be a list containing exactly 2 points",
    ):
        _ = line_counter_block.run(
            images=images,
            detections=detections_batch,
            line_segments=line_segments,
            triggering_anchor="TOP_LEFT",
        )


def test_batch_line_counter_empty_batch() -> None:
    # given
    line_counter_block = BatchLineCounterBlockV1()

    # when
    result = line_counter_block.run(
        images=[],
        detections=[],
        line_segments=[],
        triggering_anchor="TOP_LEFT",
    )

    # then
    assert result == []


def test_batch_line_counter_single_item_batch() -> None:
    # given
    line_segment = [[15, 0], [15, 1000]]
    detection = sv.Detections(
        xyxy=np.array([[10, 10, 11, 11]]),
        tracker_id=np.array([1]),
    )
    metadata = VideoMetadata(
        video_identifier="vid_1",
        frame_number=10,
        frame_timestamp=datetime.datetime.fromtimestamp(1726570875).astimezone(
            tz=datetime.timezone.utc
        ),
    )
    image = WorkflowImageData(
        parent_metadata=ImageParentMetadata(parent_id="some"),
        numpy_image=np.zeros((192, 168, 3), dtype=np.uint8),
        video_metadata=metadata,
    )
    line_counter_block = BatchLineCounterBlockV1()

    # when
    result = line_counter_block.run(
        images=[image],
        detections=[detection],
        line_segments=[line_segment],
        triggering_anchor="TOP_LEFT",
    )

    # then
    assert len(result) == 1
    assert result[0]["count_in"] == 0
    assert result[0]["count_out"] == 0
    assert len(result[0]["detections_in"]) == 0
    assert len(result[0]["detections_out"]) == 0
