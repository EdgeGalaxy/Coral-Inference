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
            "short_description": "Count detections passing lines in batch mode.",  
            "long_description": "Batch processing version of LineCounter for improved performance.",  
            "license": "Apache-2.0",  
            "block_type": "analytics",  
        }  
    )  
    type: Literal["coral_core/batch_line_counter@v1"]  
      
    images: Selector(kind=[IMAGE_KIND]) = Field(  
        description="Batch of images to process",  
        examples=["$steps.preprocessing.images"],  
    )  
    detections: Selector(  
        kind=[  
            OBJECT_DETECTION_PREDICTION_KIND,  
            INSTANCE_SEGMENTATION_PREDICTION_KIND,  
        ]  
    ) = Field(  
        description="Batch of detections to count line crossings for.",  
        examples=["$steps.object_detection_model.predictions"],  
    )  
    line_segments: Selector(kind=[LIST_OF_VALUES_KIND]) = Field(  
        description="Batch of line segments, each consisting of exactly two points.",  
        examples=["$inputs.line_zones"],  
    )  
    triggering_anchor: Union[str, Selector(kind=[STRING_KIND])] = Field(  
        default="CENTER",  
        description="The point on the detection that must cross the line to be counted.",  
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
        return ["images", "detections", "line_segments"]  
  
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
        line_segments: Batch[List[Tuple[int, int]]],  
        triggering_anchor: str = "CENTER",  
    ) -> BlockResult:  
        results = []  
          
        for image, detection, line_segment in zip(images, detections, line_segments):  
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