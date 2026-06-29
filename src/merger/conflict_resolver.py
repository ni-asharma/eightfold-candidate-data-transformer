import logging
from typing import Dict, Any, List, Optional, Tuple
from src.validation.schema_validator import MergedField, ProvenanceInfo, Location, ExperienceItem, EducationItem
from src.merger.confidence_engine import ConfidenceEngine
from src.utils.constants import (
    STRATEGY_EXACT, STRATEGY_NORMALIZED, STRATEGY_RELIABILITY, 
    STRATEGY_COMPLETENESS, STRATEGY_LATEST_DATE, STRATEGY_FALLBACK_MULTI, STRATEGY_DEFAULT
)

logger = logging.getLogger("pipeline.merger.conflict_resolver")

class ConflictResolver:
    """
    Implements the deterministic conflict resolution rules:
    1. Exact Match
    2. Normalized Match
    3. Higher Source Reliability Weight
    4. Higher Completeness (e.g. value length)
    5. Latest Employment End Date
    6. Default / Multi-value fallback
    """
    def __init__(self, confidence_engine: ConfidenceEngine) -> None:
        self.confidence_engine = confidence_engine

    def resolve_scalar(
        self,
        field_name: str,
        raw_values: Dict[str, Any],
        normalized_values: Dict[str, Any],
        provenances: Dict[str, ProvenanceInfo],
        latest_end_dates: Dict[str, str]
    ) -> MergedField:
        """
        Resolves conflicts for a single scalar field using the deterministic priority rules.
        """
        # Filter sources that provided non-null, non-empty values
        active_sources = [
            s for s, v in normalized_values.items() 
            if v is not None and str(v).strip() != ""
        ]

        if not active_sources:
            return MergedField(
                value=None,
                winning_source=None,
                competing_values={},
                normalized_values={},
                merge_strategy=STRATEGY_DEFAULT,
                confidence_score=0.0,
                reason="No values provided by any source.",
                provenance=None
            )

        # Base case: Only one source has a value
        if len(active_sources) == 1:
            winner = active_sources[0]
            val = normalized_values[winner]
            conf = self.confidence_engine.calculate_confidence(
                winner,
                normalization_success=True,
                validation_success=True,
                agreement_count=1
            )
            return MergedField(
                value=val,
                winning_source=winner,
                competing_values={s: raw_values.get(s) for s in raw_values if raw_values.get(s) is not None},
                normalized_values={s: normalized_values.get(s) for s in normalized_values if normalized_values.get(s) is not None},
                merge_strategy=STRATEGY_RELIABILITY,
                confidence_score=conf,
                reason=f"Only source '{winner}' provided a value.",
                provenance=provenances.get(winner)
            )

        # 1. Exact Match Check (including raw comparison)
        first_source = active_sources[0]
        first_raw = raw_values.get(first_source)
        all_raw_identical = True
        for s in active_sources[1:]:
            if raw_values.get(s) != first_raw:
                all_raw_identical = False
                break
        
        if all_raw_identical:
            winner = max(active_sources, key=lambda s: self.confidence_engine.get_source_weight(s))
            conf = self.confidence_engine.calculate_confidence(
                winner,
                normalization_success=True,
                validation_success=True,
                agreement_count=len(active_sources)
            )
            return MergedField(
                value=first_raw,
                winning_source=winner,
                competing_values={s: raw_values.get(s) for s in raw_values if raw_values.get(s) is not None},
                normalized_values={s: normalized_values.get(s) for s in normalized_values if normalized_values.get(s) is not None},
                merge_strategy=STRATEGY_EXACT,
                confidence_score=conf,
                reason=f"All sources ({', '.join(active_sources)}) agree on exact raw value.",
                provenance=provenances.get(winner)
            )

        # 2. Normalized Match Check
        first_norm = normalized_values.get(first_source)
        all_norm_identical = True
        for s in active_sources[1:]:
            if str(normalized_values.get(s)).lower() != str(first_norm).lower():
                all_norm_identical = False
                break
        
        if all_norm_identical:
            winner = max(active_sources, key=lambda s: self.confidence_engine.get_source_weight(s))
            conf = self.confidence_engine.calculate_confidence(
                winner,
                normalization_success=True,
                validation_success=True,
                agreement_count=len(active_sources)
            )
            return MergedField(
                value=first_norm,
                winning_source=winner,
                competing_values={s: raw_values.get(s) for s in raw_values if raw_values.get(s) is not None},
                normalized_values={s: normalized_values.get(s) for s in normalized_values if normalized_values.get(s) is not None},
                merge_strategy=STRATEGY_NORMALIZED,
                confidence_score=conf,
                reason=f"All sources ({', '.join(active_sources)}) agree after field normalization.",
                provenance=provenances.get(winner)
            )

        # 3, 4, 5. Priority Sorting Key Function
        def get_priority_tuple(source: str) -> Tuple[float, int, str]:
            # Weight (Higher reliability = higher priority)
            weight = self.confidence_engine.get_source_weight(source)
            # Completeness (Longer string length = higher priority)
            val = str(normalized_values.get(source, ""))
            completeness = len(val)
            # Latest employment date (Latest timeline = higher priority)
            latest_date = latest_end_dates.get(source, "0000-00")
            if latest_date == "Present":
                latest_date = "9999-12"  # Ensure Present sorts highest
            
            return (weight, completeness, latest_date)

        # Sort sources descending based on priority rules
        sorted_sources = sorted(active_sources, key=get_priority_tuple, reverse=True)
        winner = sorted_sources[0]
        winning_val = normalized_values[winner]

        # Calculate agreement count for the winner value
        agreeing_sources = []
        for s in active_sources:
            if str(normalized_values.get(s)).lower() == str(winning_val).lower():
                agreeing_sources.append(s)
        agreement_count = len(agreeing_sources)

        # Calculate confidence score
        conf = self.confidence_engine.calculate_confidence(
            winner,
            normalization_success=True,
            validation_success=True,
            agreement_count=agreement_count
        )

        # Determine winning strategy and build description
        runner_up = sorted_sources[1]
        w_weight = self.confidence_engine.get_source_weight(winner)
        r_weight = self.confidence_engine.get_source_weight(runner_up)

        if w_weight > r_weight:
            strategy = STRATEGY_RELIABILITY
            reason = (
                f"Value from '{winner}' selected due to higher source weight ({w_weight}) "
                f"compared to '{runner_up}' ({r_weight})."
            )
        else:
            w_len = len(str(normalized_values[winner]))
            r_len = len(str(normalized_values[runner_up]))
            if w_len > r_len:
                strategy = STRATEGY_COMPLETENESS
                reason = (
                    f"Weights are equal. Value from '{winner}' selected due to higher "
                    f"completeness/length ({w_len} chars) compared to '{runner_up}' ({r_len} chars)."
                )
            else:
                strategy = STRATEGY_LATEST_DATE
                w_date = latest_end_dates.get(winner, "0000-00")
                r_date = latest_end_dates.get(runner_up, "0000-00")
                reason = (
                    f"Weights and completeness are equal. Value from '{winner}' selected "
                    f"due to latest associated employment end date ({w_date}) compared to "
                    f"'{runner_up}' ({r_date})."
                )

        if agreement_count > 1:
            reason += f" Value agreed upon by {agreement_count} source(s): {', '.join(agreeing_sources)}."

        return MergedField(
            value=winning_val,
            winning_source=winner,
            competing_values={s: raw_values.get(s) for s in raw_values if raw_values.get(s) is not None},
            normalized_values={s: normalized_values.get(s) for s in normalized_values if normalized_values.get(s) is not None},
            merge_strategy=strategy,
            confidence_score=conf,
            reason=reason,
            provenance=provenances.get(winner)
        )
