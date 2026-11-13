"""
Lead Intelligence Engine for Minh Van Logistics & Buzz Marketing OS.
Provides dynamic multi-source discovery, fact-vs-inference verification,
and two-axis commercial scoring.
"""
from .discovery import DynamicDiscoveryEngine, DiscoveryFilter, DiscoveryResult
from .verifier import LeadVerifier, VerificationReport
from .scorer import TwoAxisScorer, ScoreCard

__all__ = [
    "DynamicDiscoveryEngine",
    "DiscoveryFilter",
    "DiscoveryResult",
    "LeadVerifier",
    "VerificationReport",
    "TwoAxisScorer",
    "ScoreCard",
]
