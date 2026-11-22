"""Telegram CRM Lead Bot, classifier, memory feedback loop, and lead sync services."""
from __future__ import annotations

from .classifier import CrmBotConfigError, LeadClassificationResult, classify_lead_message
from .lead_sync import sync_telegram_lead
from .macros_loader import load_macros_from_docs, render_macro_text, seed_reply_templates
from .memory import get_few_shot_examples, record_reply_feedback, sync_learned_rules_from_feedback

__all__ = [
    "CrmBotConfigError",
    "LeadClassificationResult",
    "classify_lead_message",
    "get_few_shot_examples",
    "load_macros_from_docs",
    "record_reply_feedback",
    "render_macro_text",
    "seed_reply_templates",
    "sync_learned_rules_from_feedback",
    "sync_telegram_lead",
]
