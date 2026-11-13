"""
Outreach & Sales Handoff Staging Module for Minh Van Logistics & Buzz Marketing OS.
Safe, compliant drafting, reply intent classification, and BDM briefing dossier generation.
"""
from .templates import OutreachTemplateRegistry, OutreachTemplate
from .personalizer import OutreachPersonalizer, PersonalizedDraft
from .reply_classifier import ReplyClassifier, ReplyClassification
from .handoff import SalesHandoffEngine, SalesBriefingDossier

__all__ = [
    "OutreachTemplateRegistry",
    "OutreachTemplate",
    "OutreachPersonalizer",
    "PersonalizedDraft",
    "ReplyClassifier",
    "ReplyClassification",
    "SalesHandoffEngine",
    "SalesBriefingDossier",
]
