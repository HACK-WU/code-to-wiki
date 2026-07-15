# -*- coding: utf-8 -*-
"""Utilities for incremental wiki updates (reference index only)."""

from .change_detection import (
    ChangeReport,
    FeatureCluster,
    MatchResult,
    detect_changes,
    format_lookup,
    format_report,
    lookup_wikis,
)
from .citation_cleanup import cleanup_dead_citations
from .format_validation import Violation, validate_and_fix
from .incremental_index import (
    incremental_index_update,
    safe_index_update,
    save_metadata,
)
from .index_builder import Citation, build_index, build_indexes, parse_citations
from .json_utils import atomic_save_json, load_json
