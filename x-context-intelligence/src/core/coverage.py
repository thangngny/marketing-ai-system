from __future__ import annotations

from typing import List
from src.models.types import CoverageReport, ExternalLink, MediaItem, QuoteNode, ReplyNode, RootPost


class CoverageReporter:
    """
    Builds an honest coverage report assessing what was retrieved vs what was reported on X.
    """

    def compute_coverage(
        self,
        root: RootPost,
        author_followups: List[ReplyNode],
        top_replies: List[ReplyNode],
        quotes: List[QuoteNode],
        resolver_used: str,
        hit_limit: bool = False,
        limit_count: int = 25,
        truncation_notes: List[str] = None,
    ) -> CoverageReport:
        total_retrieved_replies = len(author_followups) + len(top_replies)
        reported_replies = root.replies_count
        
        reported_quotes = root.quotes_count
        retrieved_quotes = len(quotes)

        reported_media = len(root.media)
        retrieved_media = sum(1 for m in root.media if m.url or m.video_job_id)

        all_links: List[ExternalLink] = list(root.links)
        for r in author_followups + top_replies:
            all_links.extend(r.links)

        total_links = len(all_links)
        resolved_links = sum(1 for l in all_links if l.resolved)

        reasons = list(truncation_notes or [])
        if hit_limit and reported_replies > total_retrieved_replies:
            reasons.append(f"Capped at limit of {limit_count} replies to prevent context explosion")

        # Determine overall status
        if total_retrieved_replies == 0 and reported_replies > 0 and resolver_used != "BROWSER_WORKER":
            status = "PARTIAL"
            reasons.append("Conversation replies require browser authentication or extended scroll")
        elif reported_replies > total_retrieved_replies:
            status = "PARTIAL"
        else:
            status = "COMPLETE"

        notes = (
            f"Retrieved {total_retrieved_replies}/{reported_replies} replies "
            f"({len(author_followups)} author follow-ups). "
            f"{retrieved_media}/{reported_media} media items processed. "
            f"{resolved_links}/{total_links} external links resolved."
        )

        return CoverageReport(
            status=status,
            replies_reported=reported_replies,
            replies_retrieved=total_retrieved_replies,
            author_replies_retrieved=len(author_followups),
            quotes_reported=reported_quotes,
            quotes_retrieved=retrieved_quotes,
            media_reported=reported_media,
            media_retrieved=retrieved_media,
            external_links_count=total_links,
            external_links_resolved=resolved_links,
            resolver_used=resolver_used,
            truncation_reasons=reasons,
            notes=notes
        )
