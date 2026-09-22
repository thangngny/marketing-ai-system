from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .constants import Environment
from .models import Account, Activity, ChannelPost, Contact, Deal, Lead, SourceReference, Task


def stable_id(source: str, entity_type: str, external_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{source}:{entity_type}:{external_id}"))


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_zoho_record(
    module: str,
    record: dict[str, Any],
    *,
    environment: Environment,
    correlation_id: str,
):
    external_id = str(record["id"])
    common = {
        "id": stable_id("zoho", module.lower(), external_id),
        "external_id": external_id,
        "source": "zoho",
        "environment": environment,
        "correlation_id": correlation_id,
        "synthetic": False,
        "status": str(record.get("Status") or record.get("Lead_Status") or "active"),
    }
    if module == "Leads":
        full_name = record.get("Full_Name") or " ".join(
            part for part in (record.get("First_Name"), record.get("Last_Name")) if part
        )
        return Lead(
            **common,
            full_name=full_name or "Unnamed lead",
            title=record.get("Designation"),
            email=record.get("Email"),
            score=int(record.get("Lead_Score") or 0),
            score_reason="Imported from Zoho CRM; no local score has been inferred.",
            qualification=str(record.get("Lead_Status") or "unqualified"),
            metadata={"company": record.get("Company"), "phone": record.get("Phone")},
        )
    if module == "Contacts":
        full_name = record.get("Full_Name") or " ".join(
            part for part in (record.get("First_Name"), record.get("Last_Name")) if part
        )
        account = record.get("Account_Name") if isinstance(record.get("Account_Name"), dict) else {}
        return Contact(
            **common,
            full_name=full_name or "Unnamed contact",
            title=record.get("Title"),
            email=record.get("Email"),
            company_id=str(account.get("id")) if account.get("id") else None,
            metadata={"account_name": account.get("name"), "phone": record.get("Phone")},
        )
    if module == "Accounts":
        return Account(
            **common,
            name=str(record.get("Account_Name") or "Unnamed account"),
            domain=record.get("Website"),
            industry=record.get("Industry"),
            country=record.get("Billing_Country"),
            relationship_status=str(record.get("Account_Type") or "active"),
            metadata={"phone": record.get("Phone")},
        )
    if module == "Deals":
        account = record.get("Account_Name") if isinstance(record.get("Account_Name"), dict) else {}
        return Deal(
            **common,
            account_id=str(account.get("id") or "unassigned"),
            name=str(record.get("Deal_Name") or "Unnamed deal"),
            stage=str(record.get("Stage") or "unknown"),
            amount=float(record["Amount"]) if record.get("Amount") is not None else None,
            currency=str(record.get("Currency") or "VND"),
            expected_close_date=_parse_datetime(record.get("Closing_Date")),
            metadata={"account_name": account.get("name")},
        )
    if module == "Tasks":
        return Task(
            **common,
            title=str(record.get("Subject") or "Untitled task"),
            due_at=_parse_datetime(record.get("Due_Date")),
            related_entity_id=(record.get("What_Id") or {}).get("id")
            if isinstance(record.get("What_Id"), dict)
            else None,
            metadata={"priority": record.get("Priority")},
        )
    raise ValueError(f"Unsupported Zoho module: {module}")


def normalize_graph_message(
    record: dict[str, Any], *, environment: Environment, correlation_id: str
) -> Activity:
    sender = record.get("from", {}).get("emailAddress", {})
    external_id = str(record["id"])
    return Activity(
        id=stable_id("m365", "message", external_id),
        external_id=external_id,
        source="m365",
        environment=environment,
        correlation_id=correlation_id,
        synthetic=False,
        activity_type="email_metadata",
        summary=str(record.get("subject") or "(no subject)"),
        created_at=_parse_datetime(record.get("receivedDateTime")) or datetime.now().astimezone(),
        metadata={
            "sender_name": sender.get("name"),
            "sender_address": sender.get("address"),
            "received_at": record.get("receivedDateTime"),
            "is_read": record.get("isRead"),
            "web_url": record.get("webLink"),
        },
    )


def normalize_youtube_video(
    record: dict[str, Any], *, environment: Environment, correlation_id: str
) -> ChannelPost:
    video_id = str(record["id"]["videoId"])
    snippet = record.get("snippet", {})
    return ChannelPost(
        id=stable_id("youtube", "video", video_id),
        external_id=video_id,
        source="youtube",
        environment=environment,
        correlation_id=correlation_id,
        synthetic=False,
        title=str(snippet.get("title") or "Untitled video"),
        channel="youtube",
        body=str(snippet.get("description") or ""),
        publication_state="published",
        channel_post_id=video_id,
        created_at=_parse_datetime(snippet.get("publishedAt")) or datetime.now().astimezone(),
        metadata={
            "channel_id": snippet.get("channelId"),
            "channel_title": snippet.get("channelTitle"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        },
    )


def normalize_website(
    url: str,
    *,
    title: str | None,
    environment: Environment,
    correlation_id: str,
    metadata: dict[str, Any] | None = None,
) -> SourceReference:
    return SourceReference(
        id=stable_id("website", "page", url),
        external_id=url,
        source="website",
        environment=environment,
        correlation_id=correlation_id,
        synthetic=False,
        url=url,
        title=title,
        metadata=metadata or {},
    )
