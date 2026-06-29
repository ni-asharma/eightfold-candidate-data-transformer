import json
import logging
import os
from typing import Dict, Optional
from src.utils.constants import DEFAULT_WEIGHTS_PATH

logger = logging.getLogger("pipeline.merger.confidence_engine")

class ConfidenceEngine:
    """
    Computes confidence scores for candidate fields dynamically based on:
    1. Source Reliability (loaded from JSON config)
    2. Normalization Success
    3. Validation Success
    4. Cross-Source Agreement
    """
    def __init__(self, weights_config_path: Optional[str] = None) -> None:
        # Default fallback weights if file not present
        self.weights: Dict[str, float] = {
            "Recruiter CSV": 0.95,
            "ATS JSON": 0.90,
            "Resume PDF": 0.80,
            "Recruiter Notes TXT": 0.60
        }
        
        config_path = weights_config_path or DEFAULT_WEIGHTS_PATH
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    custom_weights = json.load(f)
                if isinstance(custom_weights, dict):
                    self.weights.update({str(k): float(v) for k, v in custom_weights.items()})
                    logger.info(f"Dynamically loaded source weights: {self.weights}")
                else:
                    logger.warning(f"Invalid format in source weights config: {config_path}")
            except Exception as e:
                logger.warning(f"Error loading source weights from '{config_path}': {e}. Using defaults.")
        else:
            logger.info(f"Source weights config not found at '{config_path}'. Using default reliability weights.")

    def get_source_weight(self, source_name: str) -> float:
        """Returns the reliability weight of a given source, or a default fallback weight."""
        return self.weights.get(source_name, 0.50)

    def calculate_confidence(
        self,
        source: str,
        normalization_success: bool = True,
        validation_success: bool = True,
        agreement_count: int = 1
    ) -> float:
        """
        Calculates field confidence score using the formula:
        C = min(R_s * N_s * V_s * A, 1.0)
        Where:
        - R_s: Source Reliability
        - N_s: Normalization Success (1.0 if success, 0.7 if failed/defaulted)
        - V_s: Validation Success (1.0 if success, 0.5 if failed/defaulted)
        - A: Agreement Factor (1.0 + 0.05 * (k - 1))
        """
        r_s = self.get_source_weight(source)
        n_s = 1.0 if normalization_success else 0.7
        v_s = 1.0 if validation_success else 0.5
        
        # Agreement factor: increases score if other sources agree on this value
        agreement_factor = 1.0 + 0.05 * (agreement_count - 1)
        
        score = r_s * n_s * v_s * agreement_factor
        return min(round(score, 4), 1.0)
