import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pydantic import ValidationError

from src.validation.schema_validator import (
    NormalizedCandidateProfile, CanonicalCandidateProfile, Location,
    ExperienceItem, EducationItem, MergedField, ProvenanceInfo
)
from src.merger.conflict_resolver import ConflictResolver
from src.normalizers.company import normalize_company
from src.provenance.provenance_tracker import AuditTracker
from src.utils.constants import (
    STRATEGY_RELIABILITY, STRATEGY_COMPLETENESS, STRATEGY_LATEST_DATE, 
    STAGE_MERGING, STAGE_ENTITY_RESOLUTION
)

logger = logging.getLogger("pipeline.merger.entity_resolver")

def get_latest_employment_end_date(profile: NormalizedCandidateProfile) -> str:
    """Returns the latest employment end date (YYYY-MM or Present) in a profile's history."""
    latest = "0000-00"
    for exp in profile.experience:
        end_date = exp.end_date
        if not end_date:
            continue
        if end_date == "Present":
            return "Present"
        if end_date > latest:
            latest = end_date
    return latest

class EntityResolver:
    """
    Groups raw profiles representing the same physical candidate (Entity Resolution)
    and merges each group into a single CanonicalCandidateProfile.
    """
    def __init__(self, conflict_resolver: ConflictResolver, audit_tracker: AuditTracker) -> None:
        self.conflict_resolver = conflict_resolver
        self.audit_tracker = audit_tracker

    def resolve_and_merge(
        self,
        profiles: List[NormalizedCandidateProfile]
    ) -> List[CanonicalCandidateProfile]:
        """
        Main entry point for resolving candidate duplicates and merging profiles.
        """
        # 1. Group candidate profiles by shared identifiers (email or phone)
        groups = self._group_profiles(profiles)
        
        self.audit_tracker.candidates_processed_count = len(groups)
        self.audit_tracker.duplicates_removed = len(profiles) - len(groups)
        
        logger.info(
            f"Entity resolution complete: grouped {len(profiles)} inputs "
            f"into {len(groups)} unique candidates ({self.audit_tracker.duplicates_removed} duplicates removed)."
        )

        canonical_profiles = []
        for idx, group in enumerate(groups):
            candidate_id = next((p.email for p in group if p.email), None)
            if not candidate_id:
                candidate_id = next((p.phone for p in group if p.phone), f"candidate_{idx}")
                
            canonical_profile = self._merge_profile_group(candidate_id, group)
            canonical_profiles.append(canonical_profile)
            
        return canonical_profiles

    def _group_profiles(
        self,
        profiles: List[NormalizedCandidateProfile]
    ) -> List[List[NormalizedCandidateProfile]]:
        """
        Groups profiles using a connected-component union heuristic:
        If two profiles share a non-null email or phone, they represent the same candidate.
        """
        groups: List[List[NormalizedCandidateProfile]] = []
        
        for profile in profiles:
            matching_indices = []
            for i, group in enumerate(groups):
                shares_identifier = False
                for member in group:
                    if profile.email and member.email:
                        if profile.email.strip().lower() == member.email.strip().lower():
                            shares_identifier = True
                            break
                    if profile.phone and member.phone:
                        if profile.phone.strip() == member.phone.strip():
                            shares_identifier = True
                            break
                if shares_identifier:
                    matching_indices.append(i)

            if not matching_indices:
                groups.append([profile])
            elif len(matching_indices) == 1:
                groups[matching_indices[0]].append(profile)
            else:
                merged_group = [profile]
                for idx in sorted(matching_indices, reverse=True):
                    merged_group.extend(groups.pop(idx))
                groups.append(merged_group)
                
            self.audit_tracker.add_timeline_event(
                stage=STAGE_ENTITY_RESOLUTION,
                source=profile.source_name,
                field="candidate_group",
                raw_value=profile.email or profile.phone,
                normalized_value=profile.email or profile.phone,
                validation_result="Success",
                explanation=f"Linked parsed profile from {profile.source_name} to matching candidate record."
            )

        return groups

    def _merge_profile_group(
        self,
        candidate_id: str,
        group: List[NormalizedCandidateProfile]
    ) -> CanonicalCandidateProfile:
        """
        Merges a list of normalized profiles for a single candidate into a Canonical profile.
        """
        latest_end_dates = {p.source_name: get_latest_employment_end_date(p) for p in group}

        # Gather scalar fields
        raw_first_names = {}
        norm_first_names = {}
        first_name_provs = {}

        raw_last_names = {}
        norm_last_names = {}
        last_name_provs = {}

        raw_emails = {}
        norm_emails = {}
        email_provs = {}

        raw_phones = {}
        norm_phones = {}
        phone_provs = {}

        raw_cities = {}
        norm_cities = {}
        city_provs = {}

        raw_countries = {}
        norm_countries = {}
        country_provs = {}

        for p in group:
            src = p.source_name
            if p.first_name:
                raw_first_names[src] = p.first_name
                norm_first_names[src] = p.first_name
                if "first_name" in p.provenance:
                    first_name_provs[src] = p.provenance["first_name"]
            if p.last_name:
                raw_last_names[src] = p.last_name
                norm_last_names[src] = p.last_name
                if "last_name" in p.provenance:
                    last_name_provs[src] = p.provenance["last_name"]
            if p.email:
                raw_emails[src] = p.email
                norm_emails[src] = p.email
                if "email" in p.provenance:
                    email_provs[src] = p.provenance["email"]
            if p.phone:
                raw_phones[src] = p.phone
                norm_phones[src] = p.phone
                if "phone" in p.provenance:
                    phone_provs[src] = p.provenance["phone"]
            if p.location:
                if p.location.city:
                    raw_cities[src] = p.location.city
                    norm_cities[src] = p.location.city
                    if "location" in p.provenance:
                        city_provs[src] = p.provenance["location"]
                if p.location.country:
                    raw_countries[src] = p.location.country
                    norm_countries[src] = p.location.country
                    if "location" in p.provenance:
                        country_provs[src] = p.provenance["location"]

        # Resolve scalar fields
        m_first_name = self.conflict_resolver.resolve_scalar(
            "first_name", raw_first_names, norm_first_names, first_name_provs, latest_end_dates
        )
        m_last_name = self.conflict_resolver.resolve_scalar(
            "last_name", raw_last_names, norm_last_names, last_name_provs, latest_end_dates
        )
        m_email = self.conflict_resolver.resolve_scalar(
            "email", raw_emails, norm_emails, email_provs, latest_end_dates
        )
        m_phone = self.conflict_resolver.resolve_scalar(
            "phone", raw_phones, norm_phones, phone_provs, latest_end_dates
        )

        m_city = self.conflict_resolver.resolve_scalar(
            "location.city", raw_cities, norm_cities, city_provs, latest_end_dates
        )
        m_country = self.conflict_resolver.resolve_scalar(
            "location.country", raw_countries, norm_countries, country_provs, latest_end_dates
        )

        # Build Location
        has_location = m_city.value is not None or m_country.value is not None
        location_value = Location(city=m_city.value, country=m_country.value) if has_location else None
        
        loc_winning_source = m_city.winning_source or m_country.winning_source
        loc_confidence = max(m_city.confidence_score, m_country.confidence_score)
        
        def get_loc_str(s: str, dct_c: Dict[str, str], dct_co: Dict[str, str]) -> Optional[str]:
            c_val = dct_c.get(s)
            co_val = dct_co.get(s)
            if c_val and co_val:
                return f"{c_val}, {co_val}"
            return c_val or co_val

        m_location = MergedField[Location](
            value=location_value,
            winning_source=loc_winning_source,
            competing_values={
                s: get_loc_str(s, raw_cities, raw_countries)
                for s in set(raw_cities.keys()).union(raw_countries.keys())
            },
            normalized_values={
                s: get_loc_str(s, norm_cities, norm_countries)
                for s in set(norm_cities.keys()).union(norm_countries.keys())
            },
            merge_strategy=m_city.merge_strategy or m_country.merge_strategy,
            confidence_score=loc_confidence,
            reason=f"City Winner: ({m_city.reason}). Country Winner: ({m_country.reason}).",
            provenance=m_city.provenance or m_country.provenance
        )

        # Merge Skill list
        all_skills = []
        skills_competing = {}
        skills_normalized = {}
        skill_winning_source = None
        highest_skill_weight = 0.0
        
        for p in group:
            if p.skills:
                skills_competing[p.source_name] = p.skills
                skills_normalized[p.source_name] = p.skills
                weight = self.conflict_resolver.confidence_engine.get_source_weight(p.source_name)
                if weight > highest_skill_weight:
                    highest_skill_weight = weight
                    skill_winning_source = p.source_name
                for s in p.skills:
                    if s not in all_skills:
                        all_skills.append(s)

        skills_conf = self.conflict_resolver.confidence_engine.calculate_confidence(
            skill_winning_source if skill_winning_source else "Default",
            agreement_count=len(skills_competing)
        ) if skill_winning_source else 0.0

        m_skills = MergedField[List[str]](
            value=all_skills,
            winning_source=skill_winning_source,
            competing_values=skills_competing,
            normalized_values=skills_normalized,
            merge_strategy="union_deduplicate",
            confidence_score=skills_conf,
            reason=f"Union of skills from sources: {', '.join(skills_competing.keys())}.",
            provenance=ProvenanceInfo(
                source=skill_winning_source or "System",
                method="list_union",
                timestamp=datetime_utcnow_str(),
                confidence=skills_conf
            ) if skill_winning_source else None
        )

        # Merge URLs list
        all_urls = []
        urls_competing = {}
        urls_normalized = {}
        url_winning_source = None
        highest_url_weight = 0.0
        
        for p in group:
            if p.urls:
                urls_competing[p.source_name] = p.urls
                urls_normalized[p.source_name] = p.urls
                weight = self.conflict_resolver.confidence_engine.get_source_weight(p.source_name)
                if weight > highest_url_weight:
                    highest_url_weight = weight
                    url_winning_source = p.source_name
                for u in p.urls:
                    if u not in all_urls:
                        all_urls.append(u)

        url_conf = self.conflict_resolver.confidence_engine.calculate_confidence(
            url_winning_source if url_winning_source else "Default",
            agreement_count=len(urls_competing)
        ) if url_winning_source else 0.0

        m_urls = MergedField[List[str]](
            value=all_urls,
            winning_source=url_winning_source,
            competing_values=urls_competing,
            normalized_values=urls_normalized,
            merge_strategy="union_deduplicate",
            confidence_score=url_conf,
            reason=f"Union of URLs from sources: {', '.join(urls_competing.keys())}.",
            provenance=ProvenanceInfo(
                source=url_winning_source or "System",
                method="list_union",
                timestamp=datetime_utcnow_str(),
                confidence=url_conf
            ) if url_winning_source else None
        )

        # Merge Experience lists
        exp_competing = {p.source_name: [item.model_dump() for item in p.experience] for p in group if p.experience}
        merged_exp = self._merge_experience_lists(group)
        exp_conf = highest_skill_weight
        m_experience = MergedField[List[ExperienceItem]](
            value=merged_exp,
            winning_source=max(group, key=lambda p: self.conflict_resolver.confidence_engine.get_source_weight(p.source_name)).source_name,
            competing_values=exp_competing,
            normalized_values=exp_competing,
            merge_strategy="company_match_merge",
            confidence_score=exp_conf,
            reason="Grouped and merged experience records based on identical company, title, and dates.",
            provenance=ProvenanceInfo(
                source="System",
                method="list_merge",
                timestamp=datetime_utcnow_str(),
                confidence=exp_conf
            )
        )

        # Merge Education lists
        edu_competing = {p.source_name: [item.model_dump() for item in p.education] for p in group if p.education}
        merged_edu = self._merge_education_lists(group)
        edu_conf = highest_skill_weight
        m_education = MergedField[List[EducationItem]](
            value=merged_edu,
            winning_source=max(group, key=lambda p: self.conflict_resolver.confidence_engine.get_source_weight(p.source_name)).source_name,
            competing_values=edu_competing,
            normalized_values=edu_competing,
            merge_strategy="institution_match_merge",
            confidence_score=edu_conf,
            reason="Grouped and merged education records based on institution names.",
            provenance=ProvenanceInfo(
                source="System",
                method="list_merge",
                timestamp=datetime_utcnow_str(),
                confidence=edu_conf
            )
        )

        # Record conflicts resolved metrics for Quality report
        for mf in [m_first_name, m_last_name, m_email, m_phone, m_city, m_country]:
            if len(mf.competing_values) > 1:
                vals = set(str(v).strip().lower() for v in mf.normalized_values.values() if v)
                if len(vals) > 1:
                    self.audit_tracker.conflicts_resolved += 1

        # Track audit logs for merge decisions
        profile_decisions = {
            "first_name": m_first_name,
            "last_name": m_last_name,
            "email": m_email,
            "phone": m_phone,
            "location": m_location,
            "skills": m_skills,
            "experience": m_experience,
            "education": m_education,
            "urls": m_urls
        }
        for field, merged in profile_decisions.items():
            self.audit_tracker.record_merge_decision(candidate_id, field, merged)
            
            if merged.value is None or (isinstance(merged.value, list) and not merged.value):
                self.audit_tracker.missing_fields_count += 1
            else:
                self.audit_tracker.populated_fields += 1
            self.audit_tracker.total_possible_fields += 1

            self.audit_tracker.add_timeline_event(
                stage=STAGE_MERGING,
                source=merged.winning_source,
                field=field,
                raw_value=merged.competing_values,
                normalized_value=merged.normalized_values,
                validation_result="Success",
                merge_decision=merged.merge_strategy,
                confidence=merged.confidence_score,
                final_value=str(merged.value),
                explanation=merged.reason if merged.reason else "Merged successfully."
            )

        return CanonicalCandidateProfile(
            first_name=m_first_name,
            last_name=m_last_name,
            email=m_email,
            phone=m_phone,
            location=m_location,
            skills=m_skills,
            experience=m_experience,
            education=m_education,
            urls=m_urls
        )

    def _merge_experience_lists(
        self,
        group: List[NormalizedCandidateProfile]
    ) -> List[ExperienceItem]:
        """
        Groups experience list items by identical company, title, start date, and end date,
        merging descriptions and sorting descending by latest end date.
        """
        # Map structured key -> list of (source, ExperienceItem)
        # Key: (normalized_company, title, start_date, end_date)
        exp_groups: Dict[Tuple[str, str, str, str], List[Tuple[str, ExperienceItem]]] = {}

        for p in group:
            for exp in p.experience:
                norm_company = normalize_company(exp.company) or "Unknown Company"
                company_key = norm_company.lower().strip()
                title_key = exp.title.lower().strip()
                start_key = (exp.start_date or "").strip()
                end_key = (exp.end_date or "").strip()
                
                key = (company_key, title_key, start_key, end_key)
                if key not in exp_groups:
                    exp_groups[key] = []
                exp_groups[key].append((p.source_name, exp))

        merged_list = []
        for key, items in exp_groups.items():
            if len(items) == 1:
                merged_list.append(items[0][1])
                continue

            # Merge matching experiences
            best_tuple = max(
                items,
                key=lambda t: self.conflict_resolver.confidence_engine.get_source_weight(t[0])
            )
            winner_exp = best_tuple[1]

            # Choose longest description (completeness)
            longest_desc = None
            max_desc_len = 0
            for src, item in items:
                if item.description and len(item.description) > max_desc_len:
                    longest_desc = item.description
                    max_desc_len = len(item.description)

            merged_list.append(ExperienceItem(
                company=winner_exp.company,
                title=winner_exp.title,
                start_date=winner_exp.start_date,
                end_date=winner_exp.end_date,
                description=longest_desc if longest_desc else winner_exp.description
            ))

        # Sort experiences descending by end date (Present first)
        def exp_sort_key(exp: ExperienceItem) -> str:
            d = exp.end_date
            if not d:
                return "0000-00"
            if d == "Present":
                return "9999-12"
            return d

        return sorted(merged_list, key=exp_sort_key, reverse=True)

    def _merge_education_lists(
        self,
        group: List[NormalizedCandidateProfile]
    ) -> List[EducationItem]:
        """
        Groups education items by institution and merges them.
        """
        school_groups: Dict[str, Dict[str, EducationItem]] = {}
        for p in group:
            for edu in p.education:
                key = edu.institution.strip().lower()
                if key not in school_groups:
                    school_groups[key] = {}
                school_groups[key][p.source_name] = edu

        merged_list = []
        for key, source_items in school_groups.items():
            if len(source_items) == 1:
                merged_list.append(list(source_items.values())[0])
                continue

            best_source = max(
                source_items.keys(),
                key=lambda s: self.conflict_resolver.confidence_engine.get_source_weight(s)
            )
            winner_edu = source_items[best_source]

            degree = winner_edu.degree
            field = winner_edu.field_of_study
            start = winner_edu.start_date
            end = winner_edu.end_date

            for item in source_items.values():
                if not degree and item.degree:
                    degree = item.degree
                if not field and item.field_of_study:
                    field = item.field_of_study
                if not start and item.start_date:
                    start = item.start_date
                if not end and item.end_date:
                    end = item.end_date

            merged_list.append(EducationItem(
                institution=winner_edu.institution,
                degree=degree,
                field_of_study=field,
                start_date=start,
                end_date=end
            ))

        def edu_sort_key(edu: EducationItem) -> str:
            d = edu.end_date
            if not d:
                return "0000-00"
            return d

        return sorted(merged_list, key=edu_sort_key, reverse=True)

def datetime_utcnow_str() -> str:
    return datetime.utcnow().isoformat() + "Z"
