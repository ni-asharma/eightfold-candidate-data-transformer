import pytest
from src.validation.schema_validator import NormalizedCandidateProfile, Location, ExperienceItem, ProvenanceInfo
from src.merger.confidence_engine import ConfidenceEngine
from src.merger.conflict_resolver import ConflictResolver
from src.merger.entity_resolver import EntityResolver
from src.provenance.provenance_tracker import AuditTracker

def test_confidence_engine() -> None:
    engine = ConfidenceEngine()
    
    # Check default reliability weights loaded
    assert engine.get_source_weight("Recruiter CSV") == 0.95
    assert engine.get_source_weight("ATS JSON") == 0.90
    assert engine.get_source_weight("Resume PDF") == 0.80
    assert engine.get_source_weight("Recruiter Notes TXT") == 0.60
    assert engine.get_source_weight("Unknown Source") == 0.50

    # Test confidence calculation math
    # C = R_s * N_s * V_s * A
    # CSV (0.95) with normalization/validation success and 1 source: 0.95 * 1 * 1 * 1.0 = 0.95
    assert engine.calculate_confidence("Recruiter CSV", True, True, 1) == 0.95
    
    # CSV (0.95) with normalization fail: 0.95 * 0.7 * 1 * 1.0 = 0.665
    assert engine.calculate_confidence("Recruiter CSV", False, True, 1) == 0.665
    
    # Resume (0.80) with 2 agreeing sources: 0.80 * 1 * 1 * (1.0 + 0.05 * 1) = 0.84
    assert engine.calculate_confidence("Resume PDF", True, True, 2) == 0.84

def test_conflict_resolver() -> None:
    engine = ConfidenceEngine()
    resolver = ConflictResolver(engine)
    
    # Inputs
    raw_names = {"Recruiter CSV": "John", "ATS JSON": "Jonathan", "Resume PDF": "John"}
    norm_names = {"Recruiter CSV": "John", "ATS JSON": "Jonathan", "Resume PDF": "John"}
    provenances = {
        "Recruiter CSV": ProvenanceInfo(source="Recruiter CSV", method="col", timestamp="", confidence=1.0),
        "ATS JSON": ProvenanceInfo(source="ATS JSON", method="json", timestamp="", confidence=1.0),
        "Resume PDF": ProvenanceInfo(source="Resume PDF", method="pdf", timestamp="", confidence=1.0)
    }
    latest_dates = {"Recruiter CSV": "2023-12", "ATS JSON": "Present", "Resume PDF": "2023-12"}
    
    # Resolve
    merged = resolver.resolve_scalar("first_name", raw_names, norm_names, provenances, latest_dates)
    
    # Since Recruiter CSV has weight 0.95, it should win!
    assert merged.value == "John"
    assert merged.winning_source == "Recruiter CSV"
    assert merged.merge_strategy == "higher_source_reliability"
    assert merged.confidence_score == 0.9975  # 0.95 * 1 * 1 * (1.0 + 0.05 * 1) [since Resume also has 'John']

def test_entity_resolver_and_merge() -> None:
    engine = ConfidenceEngine()
    resolver = ConflictResolver(engine)
    tracker = AuditTracker()
    entity_resolver = EntityResolver(resolver, tracker)
    
    # Create two profiles for same candidate (by shared email)
    p1 = NormalizedCandidateProfile(
        source_name="Recruiter CSV",
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="+14155550100",
        location=Location(city="San Francisco", country="US"),
        skills=["Python"],
        experience=[
            ExperienceItem(company="Google", title="Software Engineer", start_date="2022-01", end_date="2023-12")
        ]
    )
    p2 = NormalizedCandidateProfile(
        source_name="ATS JSON",
        first_name="Jonathan",
        last_name="Doe",
        email="john@example.com",
        location=Location(city="San Francisco", country="US"),
        skills=["C++"],
        experience=[
            ExperienceItem(company="Google Inc.", title="Senior Software Engineer", start_date="2024-01", end_date="Present")
        ]
    )
    
    canonical_profiles = entity_resolver.resolve_and_merge([p1, p2])
    
    assert len(canonical_profiles) == 1
    cp = canonical_profiles[0]
    
    # First name should resolve to CSV winner "John"
    assert cp.first_name.value == "John"
    
    # Skills should merge to union
    assert "Python" in cp.skills.value
    assert "C++" in cp.skills.value
    
    # Experiences should group by company Google (suffix stripped)
    # The merged experience list should have two items:
    # 1. Senior Software Engineer at Google Inc. (Present)
    # 2. Software Engineer at Google (2023-12)
    # Sorted by end_date descending
    assert len(cp.experience.value) == 2
    assert cp.experience.value[0].title == "Senior Software Engineer"
    assert cp.experience.value[0].end_date == "Present"
    assert cp.experience.value[1].title == "Software Engineer"
    assert cp.experience.value[1].end_date == "2023-12"
