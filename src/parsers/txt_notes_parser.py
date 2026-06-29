import logging
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.parsers.base_parser import BaseParser, construct_safe_profile
from src.validation.schema_validator import NormalizedCandidateProfile, ProvenanceInfo
from src.parsers.pdf_resume_parser import parse_date_range
from src.normalizers.skills import SkillNormalizer
from src.provenance.provenance_tracker import AuditTracker
from src.utils.constants import SOURCE_NOTES

logger = logging.getLogger("pipeline.parsers.txt")

class TXTNotesParser(BaseParser):
    """
    Parses unstructured Recruiter Notes TXT files using regular expression key-value extraction.
    Identifies candidate details, work history, and skills list.
    """
    def __init__(self, skill_normalizer: Optional[SkillNormalizer] = None) -> None:
        super().__init__(SOURCE_NOTES, skill_normalizer=skill_normalizer)

    def parse(
        self,
        file_path: str,
        audit_tracker: Optional[AuditTracker] = None
    ) -> List[NormalizedCandidateProfile]:
        profiles: List[NormalizedCandidateProfile] = []
        if not os.path.exists(file_path):
            logger.warning(f"Recruiter Notes file not found at path: {file_path}")
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            logger.warning(f"Failed to read TXT notes file '{file_path}': {e}")
            return []

        if not text.strip():
            logger.warning(f"Recruiter Notes file '{file_path}' is empty.")
            return []

        timestamp = datetime.utcnow().isoformat() + "Z"
        
        email = None
        phone_raw = None
        first_name = None
        last_name = None
        city = None
        country = None
        skills = []
        experience = []
        education = []
        urls = []

        # Helper extraction functions
        def search_field(patterns: List[str]) -> Optional[str]:
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            return None

        # 1. Parse Name
        full_name = search_field([r"\bName:\s*(.*)", r"\bCandidate:\s*(.*)"])
        if full_name:
            parts = full_name.split()
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = " ".join(parts[1:])
            else:
                first_name = full_name
                last_name = ""

        # 2. Parse Email
        email = search_field([r"\bEmail:\s*(.*)", r"[\w\.-]+@[\w\.-]+\.\w+"])
        if email and "@" in email:
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", email)
            if email_match:
                email = email_match.group(0).strip()

        # 3. Parse Phone
        phone_raw = search_field([
            r"\bPhone:\s*(.*)", 
            r"\bMobile:\s*(.*)", 
            r"\bTel:\s*(.*)"
        ])

        # 4. Parse Location
        location_raw = search_field([r"\bLocation:\s*(.*)", r"\bAddress:\s*(.*)"])
        if location_raw:
            parts = location_raw.split(",")
            if len(parts) >= 2:
                city = parts[0].strip()
                country = parts[1].strip()
            elif len(parts) == 1:
                city = parts[0].strip()

        # 5. Parse Skills
        skills_raw = search_field([r"\bSkills:\s*(.*)", r"\bKey\s+Skills:\s*(.*)"])
        if skills_raw:
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

        # 6. Parse Experience as dictionaries
        exp_blocks = re.findall(
            r"Company:\s*(.*?)\nTitle:\s*(.*?)\nDates:\s*(.*?)\n(?:Description:\s*(.*?)\n)?(?=Company:|Education:|School:|Skills:|Note:|$)",
            text,
            re.DOTALL | re.IGNORECASE
        )
        for comp, tit, dts, desc in exp_blocks:
            start_date, end_date = parse_date_range(dts)
            experience.append({
                "company": comp.strip(),
                "title": tit.strip(),
                "start_date": start_date,
                "end_date": end_date,
                "description": desc.strip() if desc else None
            })

        # 7. Parse Education as dictionaries
        edu_blocks = re.findall(
            r"(?:School|Institution):\s*(.*?)\nDegree:\s*(.*?)\nField:\s*(.*?)\nDates:\s*(.*?)\n",
            text,
            re.IGNORECASE
        )
        for inst, deg, fld, dts in edu_blocks:
            start_date, end_date = parse_date_range(dts)
            education.append({
                "institution": inst.strip(),
                "degree": deg.strip(),
                "field_of_study": fld.strip(),
                "start_date": start_date,
                "end_date": end_date
            })

        # 8. Parse URLs
        url_matches = re.findall(r"https?://[a-zA-Z0-9-._~:/?#\[\]@!$&'()*+,;=]+", text)
        if url_matches:
            urls = list(dict.fromkeys([u.strip() for u in url_matches]))

        # Validate identifiers
        if not email and not phone_raw:
            logger.warning(f"Recruiter Notes file '{file_path}' contains no email or phone. Skipping candidate.")
            if audit_tracker:
                audit_tracker.add_warning(f"Recruiter Notes '{file_path}' has no contact identifiers. Dropped.")
            return []

        profile_args = {
            "source_name": self.source_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone_raw,
            "location": {"city": city, "country": country} if (city or country) else None,
            "skills": skills,
            "experience": experience,
            "education": education,
            "urls": urls,
            "provenance": {}
        }

        # Normalize and audit
        norm_args = self.normalize_and_audit_args(profile_args, audit_tracker)

        # Build provenance
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
                    method="regex_key_value",
                    timestamp=timestamp,
                    confidence=1.0
                )
        norm_args["provenance"] = provenance

        safe_profile = construct_safe_profile(norm_args, self.source_name, audit_tracker)
        if safe_profile:
            profiles.append(safe_profile)

        return profiles
