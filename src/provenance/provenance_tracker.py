import json
import logging
import os
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from src.validation.schema_validator import TimelineEvent, MergedField

logger = logging.getLogger("pipeline.provenance")

def to_jsonable(val: Any) -> Any:
    """Recursively converts Pydantic models and complex types into JSON-serializable structures."""
    if isinstance(val, BaseModel):
        return val.model_dump()
    if isinstance(val, list):
        return [to_jsonable(item) for item in val]
    if isinstance(val, dict):
        return {k: to_jsonable(v) for k, v in val.items()}
    return val

class AuditTracker:
    """
    Stateful tracker that captures data lineage, merge decisions,
    transformation timelines, data quality metrics, and performance counters
    throughout the candidate ingestion pipeline execution.
    """
    def __init__(self) -> None:
        self.start_time = time.time()
        self.timeline: List[TimelineEvent] = []
        self.decisions: Dict[str, Dict[str, Any]] = {}  # candidate_email/phone -> field -> decision_details
        self.warnings: List[str] = []
        self.errors: List[str] = []
        
        # Data Quality metrics
        self.duplicates_removed = 0
        self.conflicts_resolved = 0
        self.missing_fields_count = 0
        self.malformed_values_count = 0
        self.normalization_fixes = 0
        self.validation_failures = 0
        self.total_possible_fields = 0
        self.populated_fields = 0
        
        self.sources_processed: List[str] = []
        self.candidates_processed_count = 0

    def add_timeline_event(
        self,
        stage: str,
        source: Optional[str],
        field: Optional[str],
        raw_value: Any,
        normalized_value: Any,
        validation_result: Optional[str],
        merge_decision: Optional[str] = None,
        confidence: Optional[float] = None,
        final_value: Any = None,
        explanation: str = ""
    ) -> None:
        """Appends a new transformation audit event to the candidate timeline."""
        event = TimelineEvent(
            pipeline_stage=stage,
            source=source,
            field=field,
            raw_value=to_jsonable(raw_value),
            normalized_value=to_jsonable(normalized_value),
            validation_result=validation_result,
            merge_decision=merge_decision,
            confidence=confidence,
            final_value=to_jsonable(final_value),
            explanation=explanation
        )
        self.timeline.append(event)

    def add_warning(self, msg: str) -> None:
        """Records a warning string for summary logs."""
        self.warnings.append(msg)

    def add_error(self, msg: str) -> None:
        """Records an error string for summary logs."""
        self.errors.append(msg)

    def record_merge_decision(
        self,
        candidate_id: str,
        field_name: str,
        merged_field: MergedField
    ) -> None:
        """Logs details of a field-level merge action to the decision registry."""
        if candidate_id not in self.decisions:
            self.decisions[candidate_id] = {}
        
        self.decisions[candidate_id][field_name] = {
            "value": to_jsonable(merged_field.value),
            "winning_source": merged_field.winning_source,
            "competing_values": to_jsonable(merged_field.competing_values),
            "normalized_values": to_jsonable(merged_field.normalized_values),
            "merge_strategy": merged_field.merge_strategy,
            "confidence_score": merged_field.confidence_score,
            "reason": merged_field.reason
        }

    def generate_logs(self, output_dir: str) -> None:
        """
        Compiles and writes candidate_timeline.json, decision_log.json,
        quality_report.json, and pipeline_summary.json to the output folder.
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 1. Timeline
            timeline_path = os.path.join(output_dir, "candidate_timeline.json")
            with open(timeline_path, "w", encoding="utf-8") as f:
                json.dump([e.model_dump() for e in self.timeline], f, indent=2)
                
            # 2. Decision Log
            decision_path = os.path.join(output_dir, "decision_log.json")
            with open(decision_path, "w", encoding="utf-8") as f:
                json.dump(self.decisions, f, indent=2)

            # Completeness and Data Quality score calculations
            completeness_pct = 0.0
            if self.total_possible_fields > 0:
                completeness_pct = round((self.populated_fields / self.total_possible_fields) * 100, 2)
                
            # Quality score logic
            deductions = (self.validation_failures * 5.0) + (self.malformed_values_count * 5.0)
            completeness_penalty = (100.0 - completeness_pct) * 0.5
            quality_score = max(0.0, round(100.0 - deductions - completeness_penalty, 2))

            # 3. Quality Report
            quality_path = os.path.join(output_dir, "quality_report.json")
            quality_data = {
                "duplicates_removed": self.duplicates_removed,
                "conflicts_resolved": self.conflicts_resolved,
                "missing_fields": self.missing_fields_count,
                "malformed_values": self.malformed_values_count,
                "normalization_fixes": self.normalization_fixes,
                "validation_failures": self.validation_failures,
                "completeness_percentage": completeness_pct,
                "overall_data_quality_score": quality_score
            }
            with open(quality_path, "w", encoding="utf-8") as f:
                json.dump(quality_data, f, indent=2)

            # 4. Pipeline Summary
            summary_path = os.path.join(output_dir, "pipeline_summary.json")
            execution_time = round(time.time() - self.start_time, 4)
            
            # Average confidence score calculation
            confidences = []
            for cand in self.decisions.values():
                for field in cand.values():
                    if isinstance(field, dict) and "confidence_score" in field:
                        if field.get("winning_source") is not None:
                            confidences.append(field["confidence_score"])
            avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

            summary_data = {
                "execution_time_seconds": execution_time,
                "sources_processed": self.sources_processed,
                "candidates_processed": self.candidates_processed_count,
                "conflicts_resolved": self.conflicts_resolved,
                "fields_normalized": self.normalization_fixes,
                "warnings": self.warnings,
                "errors": self.errors,
                "overall_average_confidence": avg_confidence
            }
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2)
                
            logger.info(f"Audit log exports completed successfully in '{output_dir}'.")
            
        except Exception as e:
            logger.error(f"Failed to generate pipeline audit logs: {e}")
