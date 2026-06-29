import json
import logging
import os
from typing import List, Dict, Optional
from src.utils.constants import DEFAULT_SKILLS_PATH

logger = logging.getLogger("pipeline.normalizers.skills")

class SkillNormalizer:
    """
    Normalizes candidate skills using a configurable synonym dictionary.
    Maps variant spellings (e.g., 'js', 'javascript') to a single canonical skill ('JavaScript').
    """
    def __init__(self, synonym_config_path: Optional[str] = None) -> None:
        self.synonym_map: Dict[str, str] = {}
        config_path = synonym_config_path or DEFAULT_SKILLS_PATH
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                # Reverse-map the config for O(1) lookups
                # Config format: { "Canonical": ["synonym1", "synonym2"] }
                for canonical, synonyms in config.items():
                    # Map canonical itself
                    self.synonym_map[canonical.lower().strip()] = canonical
                    for syn in synonyms:
                        self.synonym_map[syn.lower().strip()] = canonical
            except Exception as e:
                logger.warning(f"Failed to load skill synonyms from {config_path}: {e}")
        else:
            logger.warning(f"Skill synonym config not found at {config_path}. No canonical mapping will be applied.")

    def normalize(self, skill: str) -> str:
        """
        Normalizes a single skill. If it is recognized as a synonym,
        returns the canonical name. Otherwise, returns the cleaned original name.
        """
        if not skill:
            return ""
        clean_skill = skill.strip()
        key = clean_skill.lower()
        
        if key in self.synonym_map:
            return self.synonym_map[key]
        
        # If no synonym matches, return the cleaned skill title-cased or cleaned
        # To avoid making bad assumptions (e.g., URL or unique spelling), keep clean spelling.
        return clean_skill

    def normalize_list(self, skills: List[str]) -> List[str]:
        """
        Normalizes a list of skills, deduplicating the results.
        """
        normalized_set = []
        for s in skills:
            if not s:
                continue
            norm = self.normalize(s)
            if norm and norm not in normalized_set:
                normalized_set.append(norm)
        return normalized_set
