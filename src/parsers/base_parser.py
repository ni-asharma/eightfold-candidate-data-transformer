import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from src.validation.schema_validator import (
    NormalizedCandidateProfile, Location, ExperienceItem, EducationItem, ProvenanceInfo
)
from src.normalizers.phone import normalize_phone
from src.normalizers.dates import normalize_date
from src.normalizers.country import normalize_country
from src.normalizers.company import normalize_company
from src.normalizers.skills import SkillNormalizer
from src.provenance.provenance_tracker import AuditTracker
from src.utils.constants import STAGE_NORMALIZATION, STAGE_VALIDATION

logger = logging.getLogger("pipeline.parsers.base")

def construct_safe_profile(
    args: Dict[str, Any],
    source_name: str,
    audit_tracker: Optional[AuditTracker] = None
) -> Optional[NormalizedCandidateProfile]:
    """
    Attempts to instantiate a NormalizedCandidateProfile.
    If validation errors occur, it identifies the invalid fields, nullifies them,
    logs warnings, and records the failure in the audit tracker before reconstructing.
    """
    try:
        return NormalizedCandidateProfile(**args)
    except ValidationError as e:
        sanitized_args = args.copy()
        for error in e.errors():
            loc = error.get("loc", ())
            msg = error.get("msg", "Validation failed")
            if loc:
                field_name = str(loc[0])
                if field_name in sanitized_args:
                    raw_val = sanitized_args[field_name]
                    logger.warning(
                        f"Field '{field_name}' in data from '{source_name}' "
                        f"failed validation: {msg}. Setting field to default/None."
                    )
                    
                    if audit_tracker:
                        audit_tracker.validation_failures += 1
                        audit_tracker.malformed_values_count += 1
                        audit_tracker.add_timeline_event(
                            stage=STAGE_VALIDATION,
                            source=source_name,
                            field=field_name,
                            raw_value=raw_val,
                            normalized_value=None,
                            validation_result=f"Fail: {msg}",
                            explanation=f"Pydantic schema validation error: {msg}"
                        )

                    if isinstance(sanitized_args[field_name], list):
                        sanitized_args[field_name] = []
                    elif field_name == "location":
                        sanitized_args[field_name] = None
                    else:
                        sanitized_args[field_name] = None
                    
                    if "provenance" in sanitized_args and field_name in sanitized_args["provenance"]:
                        del sanitized_args["provenance"][field_name]
        try:
            return NormalizedCandidateProfile(**sanitized_args)
        except Exception as retry_err:
            logger.error(f"Failed to reconstruct candidate profile after sanitization: {retry_err}")
            return None

class BaseParser(ABC):
    """
    Abstract base class for all candidate data source parsers.
    Defines a unified interface and provides centralized normalization & auditing logic.
    """
    def __init__(self, source_name: str, skill_normalizer: Optional[SkillNormalizer] = None) -> None:
        self.source_name = source_name
        self.skill_normalizer = skill_normalizer or SkillNormalizer()

    @abstractmethod
    def parse(self, file_path: str, audit_tracker: Optional[AuditTracker] = None) -> List[NormalizedCandidateProfile]:
        """
        Parses a file and returns a list of NormalizedCandidateProfile instances.
        """
        pass

    def normalize_and_audit_args(
        self,
        raw_args: Dict[str, Any],
        audit_tracker: Optional[AuditTracker] = None
    ) -> Dict[str, Any]:
        """
        Performs centralized normalization on raw profile arguments and records
        the changes in the audit timeline. Safe-casts submodel fields.
        """
        normalized_args = raw_args.copy()
        
        # 1. Normalize Phone
        phone_raw = raw_args.get("phone")
        if phone_raw:
            phone_norm = normalize_phone(phone_raw)
            normalized_args["phone"] = phone_norm
            if phone_norm != phone_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="phone",
                        raw_value=phone_raw,
                        normalized_value=phone_norm,
                        validation_result="Success",
                        explanation=f"Formatted phone '{phone_raw}' to E.164: '{phone_norm}'"
                    )

        # 2. Normalize Location
        loc_raw = raw_args.get("location")
        location_obj = None
        if loc_raw:
            if isinstance(loc_raw, dict):
                city_raw = loc_raw.get("city")
                country_raw = loc_raw.get("country")
            else:  # If already an object
                city_raw = loc_raw.city
                country_raw = loc_raw.country

            country_norm = normalize_country(country_raw) if country_raw else None
            if country_raw and country_norm != country_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="location.country",
                        raw_value=country_raw,
                        normalized_value=country_norm,
                        validation_result="Success",
                        explanation=f"Mapped country '{country_raw}' to ISO-2: '{country_norm}'"
                    )
            try:
                location_obj = Location(city=city_raw, country=country_norm)
            except ValidationError as e:
                logger.warning(f"Location validation failed for source '{self.source_name}': {e}")
                if audit_tracker:
                    audit_tracker.validation_failures += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_VALIDATION,
                        source=self.source_name,
                        field="location",
                        raw_value=loc_raw,
                        normalized_value=None,
                        validation_result="Fail",
                        explanation=f"Location parsing failed validation: {str(e)}"
                    )
        normalized_args["location"] = location_obj

        # 3. Normalize Skills
        skills_raw = raw_args.get("skills", [])
        if skills_raw:
            skills_norm = self.skill_normalizer.normalize_list(skills_raw)
            normalized_args["skills"] = skills_norm
            diff = set(skills_raw) != set(skills_norm)
            if diff:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="skills",
                        raw_value=skills_raw,
                        normalized_value=skills_norm,
                        validation_result="Success",
                        explanation="Standardized skill terms using synonym vocabulary dictionary."
                    )

        # 4. Normalize Experience details (Company & Dates)
        experience_raw = raw_args.get("experience", [])
        exp_norm = []
        for exp in experience_raw:
            if not isinstance(exp, dict):
                exp_dict = exp.model_dump() if hasattr(exp, "model_dump") else exp.__dict__
            else:
                exp_dict = exp

            comp_raw = exp_dict.get("company")
            comp_norm = normalize_company(comp_raw) if comp_raw else None
            if comp_raw and comp_norm != comp_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="experience.company",
                        raw_value=comp_raw,
                        normalized_value=comp_norm,
                        validation_result="Success",
                        explanation=f"Cleaned corporate suffix for '{comp_raw}' -> '{comp_norm}'"
                    )

            start_raw = exp_dict.get("start_date")
            start_norm = normalize_date(start_raw) if start_raw else None
            if start_raw and start_norm != start_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="experience.start_date",
                        raw_value=start_raw,
                        normalized_value=start_norm,
                        validation_result="Success",
                        explanation=f"Standardized start date: {start_raw} -> {start_norm}"
                    )

            end_raw = exp_dict.get("end_date")
            end_norm = normalize_date(end_raw) if end_raw else None
            if end_raw and end_norm != end_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="experience.end_date",
                        raw_value=end_raw,
                        normalized_value=end_norm,
                        validation_result="Success",
                        explanation=f"Standardized end date: {end_raw} -> {end_norm}"
                    )

            try:
                exp_norm.append(ExperienceItem(
                    company=comp_norm or "Unknown Company",
                    title=exp_dict.get("title") or "Unknown Title",
                    start_date=start_norm,
                    end_date=end_norm,
                    description=exp_dict.get("description")
                ))
            except ValidationError as e:
                logger.warning(f"Experience item validation failed: {e}")
                if audit_tracker:
                    audit_tracker.validation_failures += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_VALIDATION,
                        source=self.source_name,
                        field="experience.item",
                        raw_value=exp_dict,
                        normalized_value=None,
                        validation_result="Fail",
                        explanation=f"Experience item validation failed: {str(e)}"
                    )
        normalized_args["experience"] = exp_norm

        # 5. Normalize Education details (Dates)
        education_raw = raw_args.get("education", [])
        edu_norm = []
        for edu in education_raw:
            if not isinstance(edu, dict):
                edu_dict = edu.model_dump() if hasattr(edu, "model_dump") else edu.__dict__
            else:
                edu_dict = edu

            start_raw = edu_dict.get("start_date")
            start_norm = normalize_date(start_raw) if start_raw else None
            if start_raw and start_norm != start_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="education.start_date",
                        raw_value=start_raw,
                        normalized_value=start_norm,
                        validation_result="Success",
                        explanation=f"Standardized education start date: {start_raw} -> {start_norm}"
                    )

            end_raw = edu_dict.get("end_date")
            end_norm = normalize_date(end_raw) if end_raw else None
            if end_raw and end_norm != end_raw:
                if audit_tracker:
                    audit_tracker.normalization_fixes += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_NORMALIZATION,
                        source=self.source_name,
                        field="education.end_date",
                        raw_value=end_raw,
                        normalized_value=end_norm,
                        validation_result="Success",
                        explanation=f"Standardized education end date: {end_raw} -> {end_norm}"
                    )

            try:
                edu_norm.append(EducationItem(
                    institution=edu_dict.get("institution") or edu_dict.get("school") or "Unknown Institution",
                    degree=edu_dict.get("degree"),
                    field_of_study=edu_dict.get("field_of_study") or edu_dict.get("field"),
                    start_date=start_norm,
                    end_date=end_norm
                ))
            except ValidationError as e:
                logger.warning(f"Education item validation failed: {e}")
                if audit_tracker:
                    audit_tracker.validation_failures += 1
                    audit_tracker.add_timeline_event(
                        stage=STAGE_VALIDATION,
                        source=self.source_name,
                        field="education.item",
                        raw_value=edu_dict,
                        normalized_value=None,
                        validation_result="Fail",
                        explanation=f"Education item validation failed: {str(e)}"
                    )
        normalized_args["education"] = edu_norm

        return normalized_args
