from __future__ import annotations

import re
from typing import List, Tuple
from src.models.types import ReplyCategory, ReplyNode


def classify_reply(text: str, is_author: bool) -> Tuple[ReplyCategory, int]:
    """
    Classifies a reply and assigns an informational value rank (supports English and multilingual/Chinese).
    """
    if is_author:
        return ReplyCategory.AUTHOR_FOLLOWUP, 100

    clean_text = text.strip()
    if len(clean_text) < 5 and not any(k in clean_text.lower() for k in ["how", "why", "code", "mcp"]):
        return ReplyCategory.LOW_INFORMATION, 0

    lower = clean_text.lower()

    # Technical implementation keywords
    tech_keywords = [
        "code", "github", "git clone", "mcp", "config", "prompt", "api", "token", "model",
        "python", "node", "install", "pip", "npm", "docker", "endpoint", "extension", "chrome",
        "devtools", "script", "tool", "workflow", "agent", "claude", "curl", "repo",
        "自动", "过滤", "初筛", "招聘", "回复", "沟通", "脚本", "工具", "自动化"
    ]
    has_tech = any(k in lower for k in tech_keywords) or "`" in text or "http" in text

    # Bug / correction / critique keywords
    correction_keywords = [
        "error", "bug", "fail", "broken", "issue", "wrong", "fake", "deprecated",
        "not working", "doesn't work", "limitation", "instead of", "problem",
        "成了屁", "木啥感觉", "没感觉", "看个热闹", "缺点", "失效", "问题"
    ]
    has_correction = any(k in lower for k in correction_keywords)

    # Question keywords
    question_keywords = ["how", "why", "what", "can we", "does it", "where", "怎么", "如何", "怎样", "吗", "？", "?"]
    is_question = any(k in lower for k in question_keywords)

    if has_correction:
        return ReplyCategory.CORRECTION_OR_DEBUNK, 55
    elif has_tech:
        rank = 50 + (20 if "`" in text else 0) + (15 if "github.com" in lower else 0)
        return ReplyCategory.TECHNICAL_IMPLEMENTATION, rank
    elif is_question:
        return ReplyCategory.QUESTION_ANSWER, 40
    else:
        return ReplyCategory.FEEDBACK, 15


def process_replies(
    replies: List[ReplyNode],
    root_author_handle: str,
    min_rank: int = 0,
    filter_author_only: bool = False,
) -> Tuple[List[ReplyNode], List[ReplyNode]]:
    """
    Processes replies into (author_followups, top_replies).
    """
    author_followups: List[ReplyNode] = []
    top_replies: List[ReplyNode] = []

    norm_root_handle = root_author_handle.lower().lstrip("@")

    for r in replies:
        is_author = r.author.handle.lower().lstrip("@") == norm_root_handle
        r.is_author_reply = is_author
        category, rank = classify_reply(r.text, is_author)
        r.category = category
        r.rank = rank

        if is_author:
            author_followups.append(r)
        else:
            if not filter_author_only and r.rank >= min_rank:
                top_replies.append(r)

    # Sort top replies by rank descending
    top_replies.sort(key=lambda x: (x.rank, x.likes), reverse=True)
    author_followups.sort(key=lambda x: x.created_at or "", reverse=False)

    return author_followups, top_replies
