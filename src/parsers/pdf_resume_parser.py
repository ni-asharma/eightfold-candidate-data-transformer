import logging
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import fitz  # PyMuPDF

from src.parsers.base_parser import BaseParser, construct_safe_profile
from src.validation.schema_validator import NormalizedCandidateProfile, ProvenanceInfo
from src.normalizers.skills import SkillNormalizer
from src.provenance.provenance_tracker import AuditTracker
from src.utils.constants import SOURCE_RESUME

logger = logging.getLogger("pipeline.parsers.pdf")

def parse_date_range(range_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Splits a date range string (e.g., '2020-01 to Present', '06/2021 - 12/2023')
    into start_date and end_date. Handles year-month boundaries robustly.
    """
    if not range_str:
        return None, None
        
    range_str = range_str.strip()
    
    # 1. Split on literal 'to' or 'until' (case-insensitive)
    for sep in [" to ", " until ", " to", "until"]:
        if sep in range_str.lower():
            parts = re.split(re.escape(sep), range_str, flags=re.IGNORECASE)
            if len(parts) >= 2:
                return parts[0].strip(), parts[1].strip()
                
    # 2. Check for ranges separated by hyphens/dashes with spaces around them
    parts = re.split(r"\s+[-–—]\s+", range_str)
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
        
    # 3. Check for tight YYYY-MM-YYYY-MM range
    match = re.match(
        r"^(\d{4}-\d{2}|\d{4})\s*[-–—]\s*(\d{4}-\d{2}|\d{4}|Present|Current)$",
        range_str,
        re.IGNORECASE
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()
        
    # Fallback to simple split on hyphen if exactly 2 parts (like 2020-2023)
    parts = range_str.split("-")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
        
    return range_str, None

class PDFResumeParser(BaseParser):
    """
    Ingests PDF Resumes using PyMuPDF (fitz) and extracts structured data using Regex
    and Heuristics. Features fallback skill extraction from raw text blocks.
    """
    def __init__(self, skill_normalizer: Optional[SkillNormalizer] = None) -> None:
        super().__init__(SOURCE_RESUME, skill_normalizer=skill_normalizer)

    def parse(
        self,
        file_path: str,
        audit_tracker: Optional[AuditTracker] = None
    ) -> List[NormalizedCandidateProfile]:
        profiles: List[NormalizedCandidateProfile] = []
        if not os.path.exists(file_path):
            logger.warning(f"PDF Resume file not found at path: {file_path}")
            return []

        text = ""
        try:
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text()
            doc.close()
        except Exception as e:
            logger.warning(f"Failed to read PDF file '{file_path}': {e}")
            return []

        if not text.strip():
            logger.warning(f"PDF Resume '{file_path}' is empty or has no extractable text.")
            return []

        timestamp = datetime.utcnow().isoformat() + "Z"
        
        email = None
        phone_raw = None
        first_name = None
        last_name = None
        city = None
        country = None
        skills: List[str] = []
        experience = []
        education = []
        urls = []

        # 1. Parse Name (look for Name: or use first short text line)
        name_match = re.search(r"Name:\s*(.*)", text, re.IGNORECASE)
        if name_match:
            full_name = name_match.group(1).strip()
        else:
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            full_name = None
            for line in lines[:3]:
                if "@" not in line and not any(char.isdigit() for char in line) and len(line) < 45:
                    full_name = line
                    break
        
        if full_name:
            parts = full_name.split()
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = " ".join(parts[1:])
            else:
                first_name = full_name
                last_name = ""

        # 2. Extract Email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        if email_match:
            email = email_match.group(0).strip()

        # 3. Extract Phone
        phone_match = re.search(r"(\+?\d{1,4}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,9}", text)
        if phone_match:
            phone_raw = phone_match.group(0).strip()

        # 4. Extract Location (Bug 3 Fix: Stop matching country group at newline or non-letters)
        loc_match = re.search(r"Location:\s*([A-Za-z ]+),\s*([A-Za-z]+)", text, re.IGNORECASE)
        if loc_match:
            city = loc_match.group(1).strip()
            country = loc_match.group(2).strip()
        else:
            addr_match = re.search(r"Address:\s*([A-Za-z ]+),\s*([A-Za-z]+)", text, re.IGNORECASE)
            if addr_match:
                city = addr_match.group(1).strip()
                country = addr_match.group(2).strip()

        # 5. Extract URLs
        url_matches = re.findall(r"https?://[a-zA-Z0-9-._~:/?#\[\]@!$&'()*+,;=]+", text)
        if url_matches:
            urls = list(dict.fromkeys([u.strip() for u in url_matches]))

        # 6. Extract Skills Section
        skills_match = re.search(r"Skills:\s*(.*)", text, re.IGNORECASE)
        if skills_match:
            skills_line = skills_match.group(1).split("\n")[0]
            skills = [s.strip() for s in skills_line.split(",") if s.strip()]
        
        # Heuristic search: Scan the text for known skills if skills list is empty
        if not skills:
            try:
                for syn, canonical in self.skill_normalizer.synonym_map.items():
                    pattern_str = rf"\b{re.escape(syn)}\b"
                    if "+" in syn or "#" in syn:
                        pattern_str = rf"(?:^|\s|\b){re.escape(syn)}(?:\s|\b|$)"
                    
                    if re.search(pattern_str, text, re.IGNORECASE):
                        if canonical not in skills:
                            skills.append(canonical)
            except Exception as e:
                logger.warning(f"Heuristic skill mapping error: {e}")

        # 7. Extract Work Experience as dictionaries
        exp_blocks = re.findall(
            r"Company:\s*(.*?)\nTitle:\s*(.*?)\nDates:\s*(.*?)\n(?:Description:\s*(.*?)\n)?(?=Company:|Education:|Institution:|School:|Skills:|$)",
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

        # 8. Extract Education as dictionaries
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

        # Verify contact identifiers
        if not email and not phone_raw:
            logger.warning(f"PDF Resume '{file_path}' has no email or phone. Skipping candidate.")
            if audit_tracker:
                audit_tracker.add_warning(f"PDF Resume '{file_path}' contains no contact details. Dropped.")
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
                    method="regex_heuristics",
                    timestamp=timestamp,
                    confidence=1.0
                )
        norm_args["provenance"] = provenance

        safe_profile = construct_safe_profile(norm_args, self.source_name, audit_tracker)
        if safe_profile:
            profiles.append(safe_profile)

        return profiles
