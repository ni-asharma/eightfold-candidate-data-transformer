import os
import pytest
from src.parsers.csv_parser import CSVParser
from src.parsers.ats_parser import ATSParser
from src.parsers.pdf_resume_parser import PDFResumeParser
from src.provenance.provenance_tracker import AuditTracker

def test_missing_files_graceful_handling() -> None:
    tracker = AuditTracker()
    
    # Ingesting missing CSV
    csv_parser = CSVParser()
    profiles_csv = csv_parser.parse("nonexistent_file.csv", audit_tracker=tracker)
    assert profiles_csv == []  # Return empty list rather than throwing error
    assert len(tracker.warnings) == 0  # logged through standard logger, tracker handles CLI warnings

def test_corrupted_json_handling(tmp_path) -> None:
    # Invalid JSON syntax
    bad_json = tmp_path / "corrupted_ats.json"
    with open(bad_json, "w", encoding="utf-8") as f:
        f.write("{invalid-json-content")
        
    ats_parser = ATSParser()
    tracker = AuditTracker()
    profiles = ats_parser.parse(str(bad_json), audit_tracker=tracker)
    
    assert profiles == []  # Gracefully returned empty list
    # Standard logger prints warnings

def test_validation_error_field_nullification(tmp_path) -> None:
    # CSV candidate with an invalid phone format and invalid email format
    csv_content = """first_name,last_name,email,phone
John,Doe,not-an-email,1234
"""
    csv_file = tmp_path / "invalid_candidate.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write(csv_content)
        
    parser = CSVParser()
    tracker = AuditTracker()
    profiles = parser.parse(str(csv_file), audit_tracker=tracker)
    
    # The profile should still be parsed because first_name and last_name are present!
    # But invalid email and phone should be set to None in the final profile.
    assert len(profiles) == 1
    p = profiles[0]
    assert p.first_name == "John"
    assert p.last_name == "Doe"
    assert p.email is None
    assert p.phone is None
    
    # Validate that tracker caught validation failures
    assert tracker.validation_failures == 1
    assert tracker.malformed_values_count == 1
    
    # Check that timeline event lists the failure
    assert len(tracker.timeline) >= 2
    stages = [event.pipeline_stage for event in tracker.timeline]
    assert "validation" in stages
