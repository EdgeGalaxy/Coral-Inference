import hashlib
from typing import Dict, List, Literal, Optional, Tuple, Type, Union

import cv2 as cv
import numpy as np
import supervision as sv
from pydantic import ConfigDict, Field

from inference.core.workflows.core_steps.visualizations.common.base import (
    OUTPUT_IMAGE_KEY,
    VisualizationBlock,
    VisualizationManifest,
    WorkflowBlockManifest,
)
from inference.core.workflows.core_steps.visualizations.common.utils import str_to_color
from inference.core.workflows.execution_engine.entities.base import (
    WorkflowImageData,
    Batch,
    OutputDefinition,
)
from inference.core.workflows.execution_engine.entities.types import (
    FLOAT_KIND,
    FLOAT_ZERO_TO_ONE_KIND,
    INTEGER_KIND,
    LIST_OF_VALUES_KIND,
    STRING_KIND,
    IMAGE_KIND,
    FloatZeroToOne,
    Selector,
)
from inference.core.workflows.prototypes.block import BlockResult, WorkflowBlockManifest


class BatchLineCounterZoneVisualizationManifest(WorkflowBlockManifest):
    type: Literal["coral_core/batch_line_counter_visualization@v1"]
    model_config = ConfigDict(
        json_schema_extra={
            "name": "Batch Line Counter Visualization",
            "version": "v1",
            "short_description": "Line zone visualization for multi-view mode.",
            "long_description": "Multi-view version of line counter zone visualization with better performance.",
            "license": "Apache-2.0",
            "block_type": "visualization",
        }
    )

    images: Selector(kind=[IMAGE_KIND]) = Field(
        title="Images",
        description="Batch of images to be visualized",
        examples=["$steps.preprocessing.images"],
    )
    zones: Union[list, Selector(kind=[LIST_OF_VALUES_KIND])] = Field(
        title="Line Zones",
        description="Batch of line zones, each zone consists of two points.",
        examples=["$inputs.line_zones"],
    )
    color: Union[str, Selector(kind=[STRING_KIND])] = Field(
        title="Zone Color",
        description="Color of the zone.",
        default="#5bb573",
        examples=["WHITE", "$inputs.color"],
    )
    thickness: Union[int, Selector(kind=[INTEGER_KIND])] = Field(
        title="Line Thickness",
        description="Pixel thickness of the line.",
        default=2,
        examples=[2, "$inputs.thickness"],
    )
    text_thickness: Union[int, Selector(kind=[INTEGER_KIND])] = Field(
        title="Text Thickness",
        description="Pixel thickness of the text.",
        default=1,
        examples=[1, "$inputs.text_thickness"],
    )
    text_scale: Union[float, Selector(kind=[FLOAT_KIND])] = Field(
        title="Text Scale",
        description="Scale factor of the text.",
        default=1.0,
        examples=[1.0, "$inputs.text_scale"],
    )
    count_ins: Union[int, Selector(kind=[INTEGER_KIND])] = Field(
        title="Count In",
        description="Batch of incoming count values from line counter.",
        examples=["$steps.batch_line_counter.count_in"],
    )
    count_outs: Union[int, Selector(kind=[INTEGER_KIND])] = Field(
        title="Count Out",
        description="Batch of outgoing count values from line counter.",
        examples=["$steps.batch_line_counter.count_out"],
    )
    opacity: Union[FloatZeroToOne, Selector(kind=[FLOAT_ZERO_TO_ONE_KIND])] = Field(
        title="Opacity",
        description="Opacity of the line overlay.",
        default=0.3,
        examples=[0.3, "$inputs.opacity"],
    )

    @classmethod
    def get_parameters_accepting_batches(cls) -> List[str]:
        return ["images", "count_ins", "count_outs"]

    @classmethod
    def get_execution_engine_compatibility(cls) -> Optional[str]:
        return ">=1.3.0,<2.0.0"

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(
                name=OUTPUT_IMAGE_KEY,
                kind=[
                    IMAGE_KIND,
                ],
            ),
        ]


class BatchLineCounterZoneVisualizationBlockV1(VisualizationBlock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache: Dict[str, np.ndarray] = {}

    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return BatchLineCounterZoneVisualizationManifest

    def getAnnotator(self, **kwargs):
        pass  # Not used in batch processing

    def run(
        self,
        images: Batch[WorkflowImageData],
        zones: Union[List[Tuple[int, int]], Batch[List[Tuple[int, int]]]],
        color: str,
        thickness: int,
        text_thickness: int,
        text_scale: float,
        count_ins: Batch[int],
        count_outs: Batch[int],
        opacity: float,
        copy_image: bool = True,
    ) -> BlockResult:
        results = []

        # 检测输入类型，统一处理为批处理格式
        if isinstance(zones, list) and len(zones) > 0:
            # 检查是否为单个线段格式 [[x1,y1], [x2,y2]]
            if (
                len(zones) == 2
                and isinstance(zones[0], (list, tuple))
                and len(zones[0]) == 2
                and isinstance(zones[0][0], (int, float))
            ):
                # 单个线段，复制给所有图像
                line_segments_batch = [zones] * len(images)
            else:
                # 已经是批处理格式
                line_segments_batch = zones
        else:
            # 不支持其他格式
            raise ValueError("Unsupported input format.")

        for image, zone, count_in, count_out in zip(
            images, zones, count_ins, count_outs
        ):
            h, w, *_ = image.numpy_image.shape
            zone_fingerprint = hashlib.md5(str(zone).encode()).hexdigest()
            key = f"{zone_fingerprint}_{color}_{opacity}_{w}_{h}"

            x1, y1 = zone[0]
            x2, y2 = zone[1]

            if key not in self._cache:
                mask = np.zeros(
                    shape=image.numpy_image.shape,
                    dtype=image.numpy_image.dtype,
                )
                mask = cv.line(
                    img=mask,
                    pt1=(x1, y1),
                    pt2=(x2, y2),
                    color=str_to_color(color).as_bgr(),
                    thickness=thickness,
                )
                self._cache[key] = mask

            mask = self._cache[key].copy()

            np_image = image.numpy_image
            if copy_image:
                np_image = np_image.copy()

            annotated_image = cv.addWeighted(
                src1=mask,
                alpha=opacity,
                src2=np_image,
                beta=1,
                gamma=0,
            )

            annotated_image = sv.draw_text(
                scene=annotated_image,
                text=f"in: {count_in}, out: {count_out}",
                text_anchor=sv.Point(x1, y1),
                text_thickness=text_thickness,
                text_scale=text_scale,
                background_color=sv.Color.WHITE,
                text_padding=0,
            )

            result = {
                OUTPUT_IMAGE_KEY: WorkflowImageData.copy_and_replace(
                    origin_image_data=image, numpy_image=annotated_image
                )
            }
            results.append(result)

        return results
