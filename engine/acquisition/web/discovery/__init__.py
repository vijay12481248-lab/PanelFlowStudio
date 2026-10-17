"""
Discovery package for web acquisition.
"""
from engine.acquisition.web.discovery.page_classifier import PageClassifier
from engine.acquisition.web.discovery.reader_classifier import ReaderClassifier
from engine.acquisition.web.discovery.container_detector import ContainerDetector
from engine.acquisition.web.discovery.candidate_collector import (
    CandidateCollector,
    normalize_image_url,
    parse_srcset_best_url,
)
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer
from engine.acquisition.web.discovery.sequence_resolver import SequenceResolver, natural_sort_key

__all__ = [
    "PageClassifier",
    "ReaderClassifier",
    "ContainerDetector",
    "CandidateCollector",
    "normalize_image_url",
    "parse_srcset_best_url",
    "CandidateClusterer",
    "CandidateScorer",
    "SequenceResolver",
    "natural_sort_key",
]
