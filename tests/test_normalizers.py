import os
import json
import pytest
from src.normalizers.phone import normalize_phone
from src.normalizers.dates import normalize_date
from src.normalizers.country import normalize_country
from src.normalizers.company import normalize_company
from src.normalizers.skills import SkillNormalizer

def test_normalize_phone() -> None:
    # Valid phone parsing (US and international)
    assert normalize_phone("1 (415) 555-0199") == "+14155550199"
    assert normalize_phone("+91 98765 43210") == "+919876543210"
    assert normalize_phone(" +1-415-555-2671 ") == "+14155552671"
    
    # Invalid phones should return None rather than crashing
    assert normalize_phone("not-a-number") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None

def test_normalize_date() -> None:
    # Standard date formats
    assert normalize_date("June 2024") == "2024-06"
    assert normalize_date("2024/06") == "2024-06"
    assert normalize_date("06-2024") == "2024-06"
    assert normalize_date("2024") == "2024-01"
    assert normalize_date("Present") == "Present"
    assert normalize_date("current") == "Present"
    
    # Invalid dates
    assert normalize_date("invalid-date") is None
    assert normalize_date("") is None
    assert normalize_date(None) is None

def test_normalize_country() -> None:
    # Country mappings
    assert normalize_country("United States") == "US"
    assert normalize_country("usa") == "US"
    assert normalize_country("India") == "IN"
    assert normalize_country("uk") == "GB"
    assert normalize_country("FR") == "FR"  # Valid ISO alpha-2 preserved
    
    # Unmapped country names
    assert normalize_country("Wakanda") is None
    assert normalize_country("") is None
    assert normalize_country(None) is None

def test_normalize_company() -> None:
    # Suffix removal and casing standardization
    assert normalize_company("Eightfold AI LLC") == "Eightfold AI"
    assert normalize_company("Google Inc.") == "Google"
    assert normalize_company("Microsoft Corporation") == "Microsoft"
    assert normalize_company("amazon.com, inc.") == "Amazon.com"
    assert normalize_company("ACME Pvt. Ltd.") == "Acme"
    
    # No suffix company
    assert normalize_company("Google") == "Google"
    assert normalize_company("") is None
    assert normalize_company(None) is None

def test_skill_normalizer(tmp_path) -> None:
    # Create temp skills config
    skills_config = {
        "C++": ["cpp", "c plus plus", "c++"],
        "JavaScript": ["js", "javascript"]
    }
    config_file = tmp_path / "skills.json"
    with open(config_file, "w") as f:
        json.dump(skills_config, f)
        
    normalizer = SkillNormalizer(synonym_config_path=str(config_file))
    
    # Synonym matches
    assert normalizer.normalize("cpp") == "C++"
    assert normalizer.normalize("c plus plus") == "C++"
    assert normalizer.normalize("javascript") == "JavaScript"
    assert normalizer.normalize("js") == "JavaScript"
    
    # Clean fallback for unmapped skill
    assert normalizer.normalize("python") == "python"
    
    # List normalization & deduplication
    raw_list = ["cpp", "c++", "js", "JavaScript", "python"]
    assert normalizer.normalize_list(raw_list) == ["C++", "JavaScript", "python"]
