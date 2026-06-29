import json
import logging
import os
from typing import Dict, Any, List, Optional
from src.validation.schema_validator import (
    CanonicalCandidateProfile, Location, ExperienceItem, EducationItem, MergedField
)
from src.utils.constants import DEFAULT_PROJECTION_PATH

logger = logging.getLogger("pipeline.projection")

class ConfigProjection:
    """
    Transforms the unified CanonicalCandidateProfile into the desired target schema
    without modifying the underlying canonical record.
    Supports field filtering, renaming, missing value policy, and audit toggles.
    """
    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config: Dict[str, Any] = {
            "field_selection": "*",
            "renaming": {},
            "normalization": {},
            "missing_policy": "fill_null",
            "confidence_toggle": True,
            "provenance_toggle": True
        }
        
        path = config_path or DEFAULT_PROJECTION_PATH
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    custom_config = json.load(f)
                self.config.update(custom_config)
                logger.info(f"Loaded projection configuration from {path}")
            except Exception as e:
                logger.warning(f"Failed to load projection config from '{path}': {e}. Using defaults.")
        else:
            logger.info(f"Projection config not found at '{path}'. Using default projection options.")

    def project(self, candidate: CanonicalCandidateProfile) -> Dict[str, Any]:
        """
        Projects a single CanonicalCandidateProfile using the loaded configuration.
        """
        field_selection = self.config.get("field_selection", "*")
        renaming = self.config.get("renaming", {})
        normalization = self.config.get("normalization", {})
        missing_policy = self.config.get("missing_policy", "fill_null")
        confidence_toggle = self.config.get("confidence_toggle", False)
        provenance_toggle = self.config.get("provenance_toggle", False)

        all_fields = [
            "first_name", "last_name", "email", "phone", 
            "location", "skills", "experience", "education", "urls"
        ]

        # Determine fields to select
        if isinstance(field_selection, list):
            selected_fields = [f for f in field_selection if f in all_fields]
        else:
            selected_fields = all_fields

        projected = {}

        for field_name in selected_fields:
            merged_field: MergedField = getattr(candidate, field_name)
            val = merged_field.value

            # 1. Apply Missing Policy
            is_empty_list = isinstance(val, list) and not val
            if val is None or is_empty_list:
                if missing_policy == "ignore":
                    continue
                elif missing_policy == "default_value":
                    if isinstance(val, list) or field_name in ["skills", "experience", "education", "urls"]:
                        val = []
                    elif field_name == "location":
                        val = Location(city="", country="")
                    else:
                        val = ""
                # for "fill_null", keep None or empty list as is

            # 2. Apply Custom Post-Normalization
            norm_rule = normalization.get(field_name)
            if val is not None and norm_rule:
                if norm_rule == "lowercase" and isinstance(val, str):
                    val = val.lower()
                elif norm_rule == "uppercase" and isinstance(val, str):
                    val = val.upper()
                elif norm_rule == "uppercase" and isinstance(val, list):
                    val = [str(x).upper() for x in val]

            # Convert Location or list items to dict format for final serialization
            serializable_value = val
            if isinstance(val, Location):
                serializable_value = val.model_dump()
            elif isinstance(val, list) and val:
                if isinstance(val[0], (ExperienceItem, EducationItem)):
                    serializable_value = [item.model_dump() for item in val]

            # 3. Handle Metadata Toggles
            if confidence_toggle or provenance_toggle:
                field_data = {"value": serializable_value}
                if confidence_toggle:
                    field_data["confidence_score"] = merged_field.confidence_score
                if provenance_toggle:
                    field_data["provenance"] = (
                        merged_field.provenance.model_dump() 
                        if merged_field.provenance else None
                    )
                output_value = field_data
            else:
                output_value = serializable_value

            # 4. Handle Renaming
            output_key = renaming.get(field_name, field_name)
            projected[output_key] = output_value

        return projected

    def project_list(self, candidates: List[CanonicalCandidateProfile]) -> List[Dict[str, Any]]:
        """Projects a list of canonical candidate profiles."""
        return [self.project(c) for c in candidates]
