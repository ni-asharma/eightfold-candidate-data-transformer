import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd

from src.parsers.base_parser import BaseParser, construct_safe_profile
from src.validation.schema_validator import NormalizedCandidateProfile, ProvenanceInfo
from src.normalizers.skills import SkillNormalizer
from src.provenance.provenance_tracker import AuditTracker
from src.utils.constants import SOURCE_CSV

logger = logging.getLogger("pipeline.parsers.csv")

class CSVParser(BaseParser):
    """
    Parses Recruiter CSV files containing structured candidate data.
    Supports parsing of experience, education, and URLs, integrating
    centralized normalization and auditing.
    """
    def __init__(self, skill_normalizer: Optional[SkillNormalizer] = None) -> None:
        super().__init__(SOURCE_CSV, skill_normalizer=skill_normalizer)

    def parse(
        self,
        file_path: str,
        audit_tracker: Optional[AuditTracker] = None
    ) -> List[NormalizedCandidateProfile]:
        profiles: List[NormalizedCandidateProfile] = []
        if not os.path.exists(file_path):
            logger.warning(f"CSV file not found at path: {file_path}")
            return []

        try:
            df = pd.read_csv(file_path, dtype=str)
        except Exception as e:
            logger.warning(f"Failed to read CSV file '{file_path}': {e}")
            return []

        timestamp = datetime.utcnow().isoformat() + "Z"

        for idx, row in df.iterrows():
            try:
                def get_val(col: str) -> Optional[str]:
                    if col in row and pd.notna(row[col]):
                        cleaned = str(row[col]).strip()
                        return cleaned if cleaned else None
                    return None

                email = get_val("email")
                phone_raw = get_val("phone")
                
                # Check for critical identifier
                if not email and not phone_raw:
                    logger.warning(f"CSV row {idx} is missing both email and phone. Skipping candidate.")
                    if audit_tracker:
                        audit_tracker.add_warning(f"CSV row {idx} is missing both contact email and phone. Dropped.")
                    continue

                first_name = get_val("first_name")
                last_name = get_val("last_name")
                
                city = get_val("city")
                country = get_val("country")
                location = {"city": city, "country": country} if (city or country) else None

                # Parse raw skills
                skills_raw = get_val("skills")
                skills = [s.strip() for s in skills_raw.split(",")] if skills_raw else []

                # Parse experiences as dictionaries
                experience = []
                for i in [1, 2]:
                    company = get_val(f"company_{i}")
                    title = get_val(f"title_{i}")
                    if company or title:
                        experience.append({
                            "company": company or "Unknown Company",
                            "title": title or "Unknown Title",
                            "start_date": get_val(f"start_date_{i}"),
                            "end_date": get_val(f"end_date_{i}"),
                            "description": get_val(f"description_{i}")
                        })

                # Parse education as dictionaries
                education = []
                for i in [1, 2]:
                    institution = get_val(f"institution_{i}") or get_val(f"school_{i}")
                    degree = get_val(f"degree_{i}")
                    if institution:
                        education.append({
                            "institution": institution,
                            "degree": degree,
                            "field_of_study": get_val(f"field_of_study_{i}") or get_val(f"field_{i}"),
                            "start_date": get_val(f"start_date_edu_{i}"),
                            "end_date": get_val(f"end_date_edu_{i}")
                        })

                # Parse URLs
                urls = []
                urls_raw = get_val("urls")
                if urls_raw:
                    urls = [u.strip() for u in urls_raw.split(",") if u.strip()]
                else:
                    for col in ["linkedin", "github", "portfolio"]:
                        val = get_val(col)
                        if val:
                            urls.append(val)

                # Assemble raw arguments
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
                    "provenance": {}  # Populated after normalization
                }

                # Normalize arguments and record fixes
                norm_args = self.normalize_and_audit_args(profile_args, audit_tracker)

                # Build provenance for normalized fields
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
                            method="csv_column",
                            timestamp=timestamp,
                            confidence=1.0
                        )
                norm_args["provenance"] = provenance

                safe_profile = construct_safe_profile(norm_args, self.source_name, audit_tracker)
                if safe_profile:
                    profiles.append(safe_profile)

            except Exception as e:
                logger.warning(f"Failed to parse CSV row {idx}: {e}")

        return profiles
