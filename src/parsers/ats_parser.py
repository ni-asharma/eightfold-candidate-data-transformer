import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.parsers.base_parser import BaseParser, construct_safe_profile
from src.validation.schema_validator import NormalizedCandidateProfile, ProvenanceInfo
from src.normalizers.skills import SkillNormalizer
from src.provenance.provenance_tracker import AuditTracker
from src.utils.constants import SOURCE_ATS

logger = logging.getLogger("pipeline.parsers.ats")

class ATSParser(BaseParser):
    """
    Parses ATS JSON files containing structured candidate profiles.
    Supports parsing lists of candidate objects or single candidate records.
    """
    def __init__(self, skill_normalizer: Optional[SkillNormalizer] = None) -> None:
        super().__init__(SOURCE_ATS, skill_normalizer=skill_normalizer)

    def parse(
        self,
        file_path: str,
        audit_tracker: Optional[AuditTracker] = None
    ) -> List[NormalizedCandidateProfile]:
        profiles: List[NormalizedCandidateProfile] = []
        if not os.path.exists(file_path):
            logger.warning(f"ATS JSON file not found at path: {file_path}")
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read or parse ATS JSON file '{file_path}': {e}")
            return []

        if isinstance(data, dict):
            records = [data]
        elif isinstance(data, list):
            records = data
        else:
            logger.warning(f"ATS JSON content in {file_path} is neither an object nor a list of objects.")
            return []

        timestamp = datetime.utcnow().isoformat() + "Z"

        for idx, item in enumerate(records):
            try:
                def get_str(k: str) -> Optional[str]:
                    v = item.get(k)
                    return str(v).strip() if v is not None else None

                email = get_str("email")
                phone_raw = get_str("phone")
                
                if not email and not phone_raw:
                    logger.warning(f"ATS candidate record at index {idx} lacks both email and phone. Skipping.")
                    if audit_tracker:
                        audit_tracker.add_warning(f"ATS candidate at index {idx} lacks email and phone. Dropped.")
                    continue

                first_name = get_str("first_name")
                last_name = get_str("last_name")

                # Parse location block as a dictionary
                location = None
                loc_data = item.get("location")
                if isinstance(loc_data, dict):
                    location = {
                        "city": loc_data.get("city"),
                        "country": loc_data.get("country")
                    }
                elif isinstance(loc_data, str):
                    parts = loc_data.split(",")
                    if len(parts) >= 2:
                        location = {"city": parts[0].strip(), "country": parts[1].strip()}
                    elif len(parts) == 1:
                        location = {"city": parts[0].strip()}

                # Parse skills list
                skills_data = item.get("skills", [])
                skills = []
                if isinstance(skills_data, list):
                    skills = [str(s).strip() for s in skills_data if s]
                elif isinstance(skills_data, str):
                    skills = [s.strip() for s in skills_data.split(",") if s.strip()]

                # Parse experience list as dictionaries
                experience = []
                exp_data = item.get("experience", [])
                if isinstance(exp_data, list):
                    for exp in exp_data:
                        if isinstance(exp, dict):
                            company = exp.get("company")
                            title = exp.get("title")
                            if company or title:
                                experience.append({
                                    "company": company,
                                    "title": title,
                                    "start_date": exp.get("start_date"),
                                    "end_date": exp.get("end_date"),
                                    "description": exp.get("description")
                                })

                # Parse education list as dictionaries
                education = []
                edu_data = item.get("education", [])
                if isinstance(edu_data, list):
                    for edu in edu_data:
                        if isinstance(edu, dict):
                            school = edu.get("institution") or edu.get("school")
                            degree = edu.get("degree")
                            if school:
                                education.append({
                                    "institution": school,
                                    "degree": degree,
                                    "field_of_study": edu.get("field_of_study") or edu.get("field"),
                                    "start_date": edu.get("start_date"),
                                    "end_date": edu.get("end_date")
                                })

                # Parse URLs list
                urls_data = item.get("urls", [])
                urls = []
                if isinstance(urls_data, list):
                    urls = [str(u).strip() for u in urls_data if u]
                elif isinstance(urls_data, str):
                    urls = [u.strip() for u in urls_data.split(",") if u.strip()]

                profile_args = {
                    "source_name": self.source_name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "phone": phone_raw,
                    "location": location,
                    "skills": skills,
                    "experience": experience,
                    "education": education,
                    "urls": urls,
                    "provenance": {}
                }

                # Normalize arguments (BaseParser will instantiate submodels)
                norm_args = self.normalize_and_audit_args(profile_args, audit_tracker)

                # Build provenance mapping for populated fields
                provenance = {}
                profile_fields = {
                    "first_name": norm_args["first_name"],
                    "last_name": norm_args["last_name"],
                    "email": norm_args["email"],
                    "phone": norm_args["phone"],
                    "location": norm_args["location"],
                    "skills": norm_args["skills"] if norm_args["skills"] else None,
                    "experience": norm_args["experience"] if norm_args["experience"] else None,
                    "education": norm_args["education"] if norm_args["education"] else None,
                    "urls": norm_args["urls"] if norm_args["urls"] else None
                }
                
                for f_name, f_val in profile_fields.items():
                    if f_val is not None:
                        provenance[f_name] = ProvenanceInfo(
                            source=self.source_name,
                            method="json_parser",
                            timestamp=timestamp,
                            confidence=1.0
                        )
                norm_args["provenance"] = provenance

                safe_profile = construct_safe_profile(norm_args, self.source_name, audit_tracker)
                if safe_profile:
                    profiles.append(safe_profile)

            except Exception as e:
                logger.warning(f"Failed to parse ATS candidate at index {idx}: {e}")

        return profiles
