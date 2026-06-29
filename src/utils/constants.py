import os

# Project structure directories
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Configuration Paths
CONFIG_DIR = os.path.join(PROJECT_ROOT, "configs")
DEFAULT_SKILLS_PATH = os.path.join(CONFIG_DIR, "canonical_skills.json")
DEFAULT_PROJECTION_PATH = os.path.join(CONFIG_DIR, "projection_config.json")
DEFAULT_WEIGHTS_PATH = os.path.join(CONFIG_DIR, "source_weights.json")

# Data Sources
SOURCE_CSV = "Recruiter CSV"
SOURCE_ATS = "ATS JSON"
SOURCE_RESUME = "Resume PDF"
SOURCE_NOTES = "Recruiter Notes TXT"

# Merge Resolution Strategies
STRATEGY_EXACT = "exact_match"
STRATEGY_NORMALIZED = "normalized_match"
STRATEGY_RELIABILITY = "higher_source_reliability"
STRATEGY_COMPLETENESS = "higher_completeness"
STRATEGY_LATEST_DATE = "latest_employment_end_date"
STRATEGY_FALLBACK_MULTI = "fallback_multi_value"
STRATEGY_DEFAULT = "default_fallback"

# Audit Pipeline Stages
STAGE_PARSING = "parsing"
STAGE_NORMALIZATION = "normalization"
STAGE_VALIDATION = "validation"
STAGE_ENTITY_RESOLUTION = "entity_resolution"
STAGE_MERGING = "merging"
STAGE_PROJECTION = "projection"
