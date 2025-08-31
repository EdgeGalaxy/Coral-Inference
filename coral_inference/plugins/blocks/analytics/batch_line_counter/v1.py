from typing import Dict, List, Optional, Tuple, Union, Type  
import supervision as sv  
from pydantic import ConfigDict, Field  
from typing_extensions import Literal  
  
from inference.core.workflows.execution_engine.entities.base import (  
    OutputDefinition,  
    WorkflowImageData,  
    Batch,  
)  
from inference.core.workflows.execution_engine.entities.types import (  
    INSTANCE_SEGMENTATION_PREDICTION_KIND,  
    INTEGER_KIND,  
    LIST_OF_VALUES_KIND,  
    OBJECT_DETECTION_PREDICTION_KIND,  
    IMAGE_KIND,  
    STRING_KIND,
    Selector,  
)  
from inference.core.workflows.prototypes.block import (  
    BlockResult,  
    WorkflowBlock,  
    WorkflowBlockManifest,  
)  
  
class BatchLineCounterManifest(WorkflowBlockManifest):  
    model_config = ConfigDict(  
        json_schema_extra={  
            "name": "Batch Line Counter",  
            "version": "v1",  
            "short_description": "多视角模式下计算检测对象通过线段的数量。",  
            "long_description": "多视角版本的线段计数器，提供更好的性能表现。",  
            "license": "Apache-2.0",  
            "block_type": "analytics",  
        }  
    )  
    type: Literal["coral_core/batch_line_counter@v1"]  
      
    images: Selector(kind=[IMAGE_KIND]) = Field(  
        title="图像",
        description="待处理的图像批次",  
        examples=["$steps.preprocessing.images"],  
    )  
    detections: Selector(  
        kind=[  
            OBJECT_DETECTION_PREDICTION_KIND,  
            INSTANCE_SEGMENTATION_PREDICTION_KIND,  
        ]  
    ) = Field(  
        title="检测结果",
        description="用于统计线段穿越次数的检测结果批次。",  
        examples=["$steps.object_detection_model.predictions"],  
    )  
    line_segments: Selector(kind=[LIST_OF_VALUES_KIND]) = Field(  
        title="线段",
        description="线段批次，每个线段由两个点组成。",  
        examples=["$inputs.line_zones"],  
    )  
    triggering_anchor: Union[str, Selector(kind=[STRING_KIND])] = Field(  
        default="CENTER",  
        title="触发锚点",
        description="检测对象必须穿越线段才能被计数的锚点位置。",  
        examples=["CENTER"],  
    )  
  
    @classmethod  
    def describe_outputs(cls) -> List[OutputDefinition]:  
        return [  
            OutputDefinition(name="count_in", kind=[INTEGER_KIND]),  
            OutputDefinition(name="count_out", kind=[INTEGER_KIND]),  
            OutputDefinition(  
                name="detections_in",  
                kind=[  
                    OBJECT_DETECTION_PREDICTION_KIND,  
                    INSTANCE_SEGMENTATION_PREDICTION_KIND,  
                ],  
            ),  
            OutputDefinition(  
                name="detections_out",  
                kind=[  
                    OBJECT_DETECTION_PREDICTION_KIND,  
                    INSTANCE_SEGMENTATION_PREDICTION_KIND,  
                ],  
            ),  
        ]  
  
    @classmethod  
    def get_parameters_accepting_batches(cls) -> List[str]:  
        return ["images", "detections"]  
  
    @classmethod  
    def get_execution_engine_compatibility(cls) -> Optional[str]:  
        return ">=1.3.0,<2.0.0"


class BatchLineCounterBlockV1(WorkflowBlock):  
    def __init__(self):  
        self._batch_of_line_zones: Dict[str, sv.LineZone] = {}  
  
    @classmethod  
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:  
        return BatchLineCounterManifest  
  
    def run(  
        self,  
        images: Batch[WorkflowImageData],  
        detections: Batch[sv.Detections],  
        line_segments: Union[List[Tuple[int, int]], Batch[List[Tuple[int, int]]]],  
        triggering_anchor: str = "CENTER",  
    ) -> BlockResult:  
        results = []  
        
        # 检测输入类型，统一处理为批处理格式
        if isinstance(line_segments, list) and len(line_segments) > 0:
            # 检查是否为单个线段格式 [[x1,y1], [x2,y2]]
            if (len(line_segments) == 2 and 
                isinstance(line_segments[0], (list, tuple)) and 
                len(line_segments[0]) == 2 and 
                isinstance(line_segments[0][0], (int, float))):
                # 单个线段，复制给所有图像
                line_segments_batch = [line_segments] * len(images)
            else:
                # 已经是批处理格式
                line_segments_batch = line_segments
        else:
            # 空或无效输入，使用默认线段
            default_segment = [[0, 0], [100, 100]]
            line_segments_batch = [default_segment] * len(images)
          
        for image, detection, line_segment in zip(images, detections, line_segments_batch):  
            # 验证 tracker_id  
            if detection.tracker_id is None:  
                raise ValueError(  
                    f"tracker_id not initialized, {self.__class__.__name__} requires detections to be tracked"  
                )  
              
            # 验证 line_segment 格式  
            if not isinstance(line_segment, list) or len(line_segment) != 2:  
                raise ValueError(  
                    f"{self.__class__.__name__} requires line zone to be a list containing exactly 2 points"  
                )  
              
            # 获取或创建 LineZone  
            metadata = image.video_metadata  
            zone_key = f"{metadata.video_identifier}_{hash(str(line_segment))}"  
              
            if zone_key not in self._batch_of_line_zones:  
                self._batch_of_line_zones[zone_key] = sv.LineZone(  
                    start=sv.Point(*line_segment[0]),  
                    end=sv.Point(*line_segment[1]),  
                    triggering_anchors=[sv.Position(triggering_anchor)],  
                )  
              
            line_zone = self._batch_of_line_zones[zone_key]  
              
            # 触发检测  
            mask_in, mask_out = line_zone.trigger(detections=detection)  
            detections_in = detection[mask_in]  
            detections_out = detection[mask_out]  
              
            # 构建单个结果  
            result = {  
                "count_in": line_zone.in_count,  
                "count_out": line_zone.out_count,  
                "detections_in": detections_in,  
                "detections_out": detections_out,  
            }  
            results.append(result)  
          
        return results