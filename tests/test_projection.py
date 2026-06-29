import pytest
from src.validation.schema_validator import (
    CanonicalCandidateProfile, Location, MergedField, ProvenanceInfo
)
from src.projection.config_projection import ConfigProjection

def test_projection_filtering_and_renaming() -> None:
    # Create a canonical profile
    cp = CanonicalCandidateProfile(
        first_name=MergedField(value="John", winning_source="CSV", confidence_score=0.95),
        last_name=MergedField(value="Doe", winning_source="CSV", confidence_score=0.95),
        email=MergedField(value="JOHN@Example.com", winning_source="ATS", confidence_score=0.90),
        phone=MergedField(value=None, winning_source=None, confidence_score=0.0)
    )

    # Setup custom projection config
    projector = ConfigProjection()
    projector.config = {
        "field_selection": ["first_name", "last_name", "email", "phone"],
        "renaming": {
            "first_name": "given_name",
            "last_name": "family_name"
        },
        "normalization": {
            "email": "lowercase"
        },
        "missing_policy": "fill_null",
        "confidence_toggle": False,
        "provenance_toggle": False
    }

    projected = projector.project(cp)
    
    # Assert fields are renamed and filtered (toggles are off, so values are scalar)
    assert projected.get("given_name") == "John"
    assert projected.get("family_name") == "Doe"
    assert "first_name" not in projected
    
    # Assert post-normalization lowercase email
    assert projected.get("email") == "john@example.com"
    
    # Assert missing policy (fill_null)
    assert projected.get("phone") is None
    assert "skills" not in projected

def test_projection_metadata_toggles() -> None:
    prov = ProvenanceInfo(source="CSV", method="col", timestamp="2026-06-29T22:00:00Z", confidence=0.95)
    cp = CanonicalCandidateProfile(
        first_name=MergedField(
            value="John",
            winning_source="CSV",
            confidence_score=0.95,
            provenance=prov
        )
    )

    projector = ConfigProjection()
    projector.config = {
        "field_selection": ["first_name"],
        "renaming": {},
        "normalization": {},
        "missing_policy": "fill_null",
        "confidence_toggle": True,
        "provenance_toggle": True
    }

    projected = projector.project(cp)
    
    # Assert metadata dictionary wrapped
    field_data = projected.get("first_name")
    assert isinstance(field_data, dict)
    assert field_data.get("value") == "John"
    assert field_data.get("confidence_score") == 0.95
    assert field_data.get("provenance") is not None
    assert field_data["provenance"]["source"] == "CSV"
