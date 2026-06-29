import re
from typing import Dict, Any, List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field, field_validator, ValidationInfo

T = TypeVar('T')

# Regex constants for validation
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")
DATE_YYYY_MM_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
URL_HTTPS_REGEX = re.compile(r"^https://[a-zA-Z0-9-._~:/?#\[\]@!$&'()*+,;=]+$")
COUNTRY_ISO2_REGEX = re.compile(r"^[A-Z]{2}$")

class ProvenanceInfo(BaseModel):
    source: str
    method: str
    timestamp: str
    normalization_applied: List[str] = Field(default_factory=list)
    confidence: float

class MergedField(BaseModel, Generic[T]):
    value: Optional[T] = None
    winning_source: Optional[str] = None
    competing_values: Dict[str, Any] = Field(default_factory=dict)     # source_name -> raw_value
    normalized_values: Dict[str, Any] = Field(default_factory=dict)    # source_name -> normalized_value
    merge_strategy: Optional[str] = None
    confidence_score: float = 0.0
    reason: Optional[str] = None
    provenance: Optional[ProvenanceInfo] = None

class Location(BaseModel):
    city: Optional[str] = None
    country: Optional[str] = None

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        val = v.strip().upper()
        if not val:
            return None
        if not COUNTRY_ISO2_REGEX.match(val):
            raise ValueError(f"Country must be ISO Alpha-2 code (2 capital letters), got '{v}'")
        return val

class ExperienceItem(BaseModel):
    company: str
    title: str
    start_date: Optional[str] = None  # YYYY-MM
    end_date: Optional[str] = None    # YYYY-MM or Present
    description: Optional[str] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        if v is None:
            return v
        val = v.strip()
        if not val:
            return None
        if val.lower() == "present" and info.field_name == "end_date":
            return "Present"
        if not DATE_YYYY_MM_REGEX.match(val):
            raise ValueError(f"{info.field_name} must follow YYYY-MM format, got '{v}'")
        return val

class EducationItem(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        if v is None:
            return v
        val = v.strip()
        if not val:
            return None
        if not DATE_YYYY_MM_REGEX.match(val):
            raise ValueError(f"{info.field_name} must follow YYYY-MM format, got '{v}'")
        return val

class NormalizedCandidateProfile(BaseModel):
    source_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[Location] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)
    provenance: Dict[str, ProvenanceInfo] = Field(default_factory=dict)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        val = v.strip()
        if not val:
            return None
        if not EMAIL_REGEX.match(val):
            raise ValueError(f"Email must be RFC-compliant, got '{v}'")
        return val

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        val = v.strip()
        if not val:
            return None
        if not PHONE_E164_REGEX.match(val):
            raise ValueError(f"Phone must be E.164 compliant (e.g. +14155552671), got '{v}'")
        return val

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: List[str]) -> List[str]:
        validated = []
        for url in v:
            val = url.strip()
            if not val:
                continue
            if not URL_HTTPS_REGEX.match(val):
                raise ValueError(f"URLs must be valid HTTPS links, got '{url}'")
            validated.append(val)
        return validated

class CanonicalCandidateProfile(BaseModel):
    first_name: MergedField[str] = Field(default_factory=MergedField)
    last_name: MergedField[str] = Field(default_factory=MergedField)
    email: MergedField[str] = Field(default_factory=MergedField)
    phone: MergedField[str] = Field(default_factory=MergedField)
    location: MergedField[Location] = Field(default_factory=MergedField)
    skills: MergedField[List[str]] = Field(default_factory=MergedField)
    experience: MergedField[List[ExperienceItem]] = Field(default_factory=MergedField)
    education: MergedField[List[EducationItem]] = Field(default_factory=MergedField)
    urls: MergedField[List[str]] = Field(default_factory=MergedField)

class TimelineEvent(BaseModel):
    pipeline_stage: str
    source: Optional[str] = None
    field: Optional[str] = None
    raw_value: Optional[Any] = None
    normalized_value: Optional[Any] = None
    validation_result: Optional[str] = None
    merge_decision: Optional[str] = None
    confidence: Optional[float] = None
    final_value: Optional[Any] = None
    explanation: str
