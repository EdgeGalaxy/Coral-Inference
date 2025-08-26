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
    OutputDefinition
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
            "short_description": "多视角模式下应用线段区域可视化。",  
            "long_description": "多视角版本的线段计数器区域可视化，提供更好的性能表现。",  
            "license": "Apache-2.0",  
            "block_type": "visualization",  
        }  
    )  
      
    images: Selector(kind=[IMAGE_KIND]) = Field(  
        title="图像",
        description="待可视化的图像批次",  
        examples=["$steps.preprocessing.images"],  
    )  
    zones: Selector(kind=[LIST_OF_VALUES_KIND]) = Field(  
        title="线段区域",
        description="线段区域批次，每个区域由两个点组成。",  
        examples=["$inputs.line_zones"],  
    )  
    color: Union[str, Selector(kind=[STRING_KIND])] = Field(  
        title="区域颜色",
        description="区域的颜色。",  
        default="#5bb573",  
        examples=["WHITE", "$inputs.color"],  
    )  
    thickness: Union[int, Selector(kind=[INTEGER_KIND])] = Field(  
        title="线条粗细",
        description="线条的像素粗细。",  
        default=2,  
        examples=[2, "$inputs.thickness"],  
    )  
    text_thickness: Union[int, Selector(kind=[INTEGER_KIND])] = Field(  
        title="文本粗细",
        description="文本的像素粗细。",  
        default=1,  
        examples=[1, "$inputs.text_thickness"],  
    )  
    text_scale: Union[float, Selector(kind=[FLOAT_KIND])] = Field(  
        title="文本缩放",
        description="文本的缩放比例。",  
        default=1.0,  
        examples=[1.0, "$inputs.text_scale"],  
    )  
    count_ins: Selector(kind=[LIST_OF_VALUES_KIND]) = Field(  
        title="入线计数",
        description="来自线段计数器的入线计数值批次。",  
        examples=["$steps.batch_line_counter.count_in"],  
    )  
    count_outs: Selector(kind=[LIST_OF_VALUES_KIND]) = Field(  
        title="出线计数",
        description="来自线段计数器的出线计数值批次。",  
        examples=["$steps.batch_line_counter.count_out"],  
    )  
    opacity: Union[FloatZeroToOne, Selector(kind=[FLOAT_ZERO_TO_ONE_KIND])] = Field(  
        title="透明度",
        description="线段覆盖层的透明度。",  
        default=0.3,  
        examples=[0.3, "$inputs.opacity"],  
    )  
  
    @classmethod  
    def get_parameters_accepting_batches(cls) -> List[str]:  
        return ["images", "zones", "count_ins", "count_outs"]  
  
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
        zones: Batch[List[Tuple[int, int]]],  
        color: str,  
        copy_image: bool,  
        thickness: int,  
        text_thickness: int,  
        text_scale: float,  
        count_ins: Batch[int],  
        count_outs: Batch[int],  
        opacity: float,  
    ) -> BlockResult:  
        results = []  
          
        for image, zone, count_in, count_out in zip(images, zones, count_ins, count_outs):  
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