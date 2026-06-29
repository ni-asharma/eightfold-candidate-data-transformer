import os
import json
import pytest
from src.parsers.csv_parser import CSVParser
from src.parsers.ats_parser import ATSParser
from src.parsers.pdf_resume_parser import PDFResumeParser
from src.parsers.txt_notes_parser import TXTNotesParser
from src.provenance.provenance_tracker import AuditTracker

def test_csv_parser(tmp_path) -> None:
    csv_content = """first_name,last_name,email,phone,city,country,skills,company_1,title_1,start_date_1,end_date_1,description_1
John,Doe,john.doe@example.com,+1 415 555 0100,San Francisco,US,Python,Google,Software Engineer,2022-01,2023-12,Backend Developer
"""
    csv_file = tmp_path / "recruiter.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write(csv_content)
        
    parser = CSVParser()
    tracker = AuditTracker()
    profiles = parser.parse(str(csv_file), audit_tracker=tracker)
    
    assert len(profiles) == 1
    p = profiles[0]
    assert p.first_name == "John"
    assert p.last_name == "Doe"
    assert p.email == "john.doe@example.com"
    # phone number is normalized during parsing
    assert p.phone == "+14155550100"
    assert p.location is not None
    assert p.location.city == "San Francisco"
    assert p.location.country == "US"
    assert p.skills == ["Python"]
    assert len(p.experience) == 1
    assert p.experience[0].company == "Google"
    assert p.experience[0].start_date == "2022-01"

def test_ats_parser(tmp_path) -> None:
    ats_content = {
        "first_name": "Jonathan",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone": "+14155550100",
        "location": {
            "city": "San Francisco",
            "country": "United States"
        },
        "skills": ["Python", "c plus plus"],
        "experience": [
            {
                "company": "Google Inc.",
                "title": "Senior Software Engineer",
                "start_date": "2024-01",
                "end_date": "Present",
                "description": "Tech lead"
            }
        ]
    }
    json_file = tmp_path / "ats.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(ats_content, f)
        
    parser = ATSParser()
    tracker = AuditTracker()
    profiles = parser.parse(str(json_file), audit_tracker=tracker)
    
    assert len(profiles) == 1
    p = profiles[0]
    assert p.first_name == "Jonathan"
    assert p.email == "john.doe@example.com"
    # Country gets normalized in BaseParser
    assert p.location.country == "US"
    assert p.skills == ["Python", "C++"]
    assert len(p.experience) == 1
    assert p.experience[0].company == "Google"  # Suffix stripped during parsing normalization

def test_txt_notes_parser(tmp_path) -> None:
    txt_content = """Candidate: Johnathan Doe
Email: john.doe@example.com
Phone: +1 415-555-0100
Location: San Francisco, USA
Skills: Python, C++

Company: Eightfold AI
Title: Senior Staff Engineer
Dates: 2026-01 to Present
Description: Leads ingestion data pipeline architectural designs.
"""
    txt_file = tmp_path / "notes.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(txt_content)
        
    parser = TXTNotesParser()
    tracker = AuditTracker()
    profiles = parser.parse(str(txt_file), audit_tracker=tracker)
    
    assert len(profiles) == 1
    p = profiles[0]
    assert p.first_name == "Johnathan"
    assert p.email == "john.doe@example.com"
    assert p.phone == "+14155550100"
    assert p.location.city == "San Francisco"
    assert p.location.country == "US"
    assert p.skills == ["Python", "C++"]
    assert len(p.experience) == 1
    assert p.experience[0].company == "Eightfold AI"

def test_pdf_resume_parser() -> None:
    # Use the pre-generated resume.pdf from sample_inputs
    pdf_path = "sample_inputs/resume.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip("resume.pdf not generated, skipping PDF parser test.")
        
    parser = PDFResumeParser()
    tracker = AuditTracker()
    profiles = parser.parse(pdf_path, audit_tracker=tracker)
    
    assert len(profiles) == 1
    p = profiles[0]
    assert p.first_name == "John"
    assert p.last_name == "Doe"
    assert p.email == "john.doe@example.com"
    assert p.phone == "+14155550100"
    assert p.location.city == "San Francisco"
    assert p.location.country == "US"
    assert "Python" in p.skills
    assert len(p.experience) == 1
    assert p.experience[0].company == "Google"
    assert p.experience[0].end_date == "2023-12"
