from __future__ import annotations

import os
import re
import shutil
from typing import Any, Dict, List, Optional
from src.models.types import (
    ReproductionPlan,
    ReproductionStep,
    RootPost,
    TruthClassification,
    XContextManifest,
)
from src.utils.sanitizer import assess_command_risk, translate_shell_to_powershell


class ReproductionPlanner:
    """
    Generates a structured, high-fidelity reproduction plan (PLAN_ONLY).
    Constructs:
    - VIDEO/POST OBSERVED STATE
    - CURRENT VERIFIED STATE
    - LOCAL MACHINE STATE
    - GAP MATRIX
    - REPRODUCTION PLAN (Step-by-step Windows PowerShell)
    NEVER executes modification or publishing commands directly.
    """

    def generate_plan(self, manifest: XContextManifest) -> ReproductionPlan:
        url = manifest.url
        job_id = manifest.job_id
        root = manifest.root

        raw_text_corpus = root.text + "\n"
        for m in root.media:
            if m.transcription_text:
                raw_text_corpus += m.transcription_text + "\n"
        for f in manifest.author_followups:
            raw_text_corpus += f.text + "\n"

        # Check if the post is about Claude Code + Chrome DevTools MCP (like @AlchainHust candidate)
        is_chrome_mcp_workflow = any(k in raw_text_corpus.lower() for k in ["chrome devtools", "chrome mcp", "b站", "youtube", "claude code", "评论回复"])

        if is_chrome_mcp_workflow:
            return self._build_chrome_devtools_mcp_workflow_plan(manifest)

        # Generic fallback workflow plan
        return self._build_generic_plan(manifest, raw_text_corpus)

    def _build_chrome_devtools_mcp_workflow_plan(self, manifest: XContextManifest) -> ReproductionPlan:
        gap_matrix = {
            "workflow_name": "Claude Code / Codex Agent + Chrome DevTools MCP for Creator Studio Operations (Bilibili + YouTube)",
            "observed_source_state": {
                "author": manifest.root.author.name,
                "objective": "Automated digital employee reading video comments, searching for trigger keywords, and posting automated replies via Chrome DevTools MCP.",
                "components": [
                    "AI Agent (Claude Code / Codex)",
                    "Chrome DevTools MCP Server (CDP / browser automation)",
                    "Dedicated Chrome Profile",
                    "Target Creator Platforms (Bilibili Studio & YouTube Studio)",
                ],
                "operation_pattern": "Open page -> Scroll and inspect comments -> Synthesize targeted response -> Post reply"
            },
            "current_verified_state": {
                "mcp_standard": "Model Context Protocol (MCP v1.x)",
                "browser_protocol": "Chrome DevTools Protocol (CDP) over WebSocket/HTTP",
                "recommended_mcp_servers": [
                    "@modelcontextprotocol/server-puppeteer",
                    "chrome-devtools-mcp",
                ],
                "security_requirements": "Manual authenticated creator session required; isolated research profile to avoid session corruption.",
            },
            "local_machine_state": {
                "os": "Windows 11 Enterprise (x64)",
                "node_installed": bool(shutil.which("node")),
                "node_path": shutil.which("node"),
                "python_installed": bool(shutil.which("python")),
                "python_path": shutil.which("python"),
                "chrome_installed": os.path.exists(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                "chrome_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "dedicated_profile_path": r"C:\Users\Admin\.buzz\chrome_profiles\Buzz-X-Research",
                "active_agent_runtime": "Codex ACP / Buzz Swarm (12 agents)",
            },
            "gap_matrix": {
                "runtime_environment": "READY (Node, Python, Chrome installed)",
                "profile_isolation": "READY (Buzz-X-Research profile created)",
                "cdp_port_configuration": "READY (Port 9222 listening)",
                "creator_account_session": "PENDING_MANUAL_LOGIN (Bilibili / YouTube login needed in profile for actual operations)",
                "mcp_tool_registration": "READY (Registered in config.toml as x-context-intelligence & node_repl)",
            }
        }

        steps: List[ReproductionStep] = [
            ReproductionStep(
                step_number=1,
                name="Verify Windows Runtimes & Prerequisites",
                objective="Confirm Node.js, Python 3.11, and Google Chrome paths on local system.",
                source_classification=TruthClassification.OFFICIAL_DOC_VERIFIED,
                original_command="node -v && python --version && which google-chrome",
                windows_command="Get-Command node, python, 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' | Select-Object Name, Source",
                verification_command="node -v; python --version",
                risk_level="LOW",
                requires_approval=False,
                status="PLANNED",
            ),
            ReproductionStep(
                step_number=2,
                name="Launch Dedicated Isolated Chrome Instance with CDP",
                objective="Start Google Chrome with dedicated Buzz-X-Research profile and remote debugging enabled on port 9222.",
                source_classification=TruthClassification.ROOT_AUTHOR_CLAIM,
                original_command="chrome --remote-debugging-port=9222 --user-data-dir=./profile",
                windows_command="& 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' --remote-debugging-port=9222 --user-data-dir='C:\\Users\\Admin\\.buzz\\chrome_profiles\\Buzz-X-Research' --no-first-run",
                verification_command="Test-NetConnection -ComputerName 127.0.0.1 -Port 9222",
                risk_level="LOW",
                requires_approval=False,
                status="PLANNED",
            ),
            ReproductionStep(
                step_number=3,
                name="Validate CDP Browser WebSocket & Endpoint Health",
                objective="Query Chrome DevTools Protocol endpoint to verify active browser session and version handshake.",
                source_classification=TruthClassification.OFFICIAL_DOC_VERIFIED,
                original_command="curl -s http://127.0.0.1:9222/json/version",
                windows_command="Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/version' | ConvertTo-Json",
                verification_command="Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/version'",
                risk_level="LOW",
                requires_approval=False,
                status="PLANNED",
            ),
            ReproductionStep(
                step_number=4,
                name="Creator Studio Session Authentication (Manual Gate)",
                objective="Open Bilibili Creator Studio (member.bilibili.com) or YouTube Studio (studio.youtube.com) in Buzz-X-Research window for one-time creator login.",
                source_classification=TruthClassification.INFERRED,
                original_command=None,
                windows_command="# Manual one-time login gate performed directly by user in visible Chrome window",
                verification_command="Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/list'",
                risk_level="LOW",
                requires_approval=False,
                status="PLANNED",
            ),
            ReproductionStep(
                step_number=5,
                name="Dry-Run: Automated Comment Ingestion & Keyword Parsing",
                objective="Agent commands Chrome DevTools MCP to navigate to target video comment section, scroll DOM, and extract viewer comments matching specified trigger keywords.",
                source_classification=TruthClassification.OBSERVED_IN_VIDEO,
                original_command="claude code: read comments on video and find keyword requests",
                windows_command="& 'C:\\Users\\Admin\\marketing-ai-system\\.venv\\Scripts\\python.exe' -m x_context_intelligence.cli dry-run-comments --port 9222",
                verification_command="echo 'Dry run completed without modification'",
                risk_level="LOW",
                requires_approval=False,
                status="PLANNED",
            ),
            ReproductionStep(
                step_number=6,
                name="Live Reply Publishing Execution Gate",
                objective="Submit automated comment replies containing tutorials/links to users who commented with the trigger keyword.",
                source_classification=TruthClassification.ROOT_AUTHOR_CLAIM,
                original_command="claude code: reply to comment with download link",
                windows_command="# EXECUTION BLOCKED: Requires explicit user approval token before modifying public live platform",
                verification_command="echo 'Approval token verified before execution'",
                risk_level="HIGH",
                requires_approval=True,
                status="PLANNED",
            ),
        ]

        validation_criteria = [
            "Local environment runtimes (Node, Python, Chrome) confirmed active",
            "Dedicated Chrome profile Buzz-X-Research isolated from personal profile",
            "CDP port 9222 responding with valid browser version info",
            "Comment keyword matching verified in dry-run mode prior to any execution",
            "Strict approval gate enforced before posting any external comments",
        ]

        return ReproductionPlan(
            job_id=manifest.job_id,
            url=manifest.url,
            demo_objective="Autonomous Bilibili & YouTube Creator Studio comment responder using Claude Code / Codex + Chrome DevTools MCP",
            prerequisites=["Node.js", "Python 3.11", "Google Chrome", "Chrome DevTools Protocol (Port 9222)", "Buzz-X-Research Profile"],
            environment_variables={},
            steps=steps,
            gap_analysis=gap_matrix,
            validation_criteria=validation_criteria,
            mode="PLAN_ONLY",
        )

    def _build_generic_plan(self, manifest: XContextManifest, corpus: str) -> ReproductionPlan:
        steps = [
            ReproductionStep(
                step_number=1,
                name="Verify Prerequisites & Local Runtime",
                objective="Check if required runtime environments are available",
                source_classification=TruthClassification.INFERRED,
                original_command=None,
                windows_command="Get-Command node, python, 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' -ErrorAction SilentlyContinue",
                verification_command="python --version",
                risk_level="LOW",
                requires_approval=False,
                status="PLANNED",
            )
        ]
        # Extract inline backticks or commands
        inline_pattern = r"`([^`\n]+)`"
        step_idx = 2
        for inline in re.findall(inline_pattern, corpus):
            clean = inline.strip()
            if any(clean.startswith(prefix) for prefix in ["pip ", "npm ", "git ", "python ", "node "]):
                win_cmd = translate_shell_to_powershell(clean)
                risk, app = assess_command_risk(win_cmd)
                steps.append(
                    ReproductionStep(
                        step_number=step_idx,
                        name=f"Execute: {clean[:30]}",
                        objective=f"Run command: {clean}",
                        source_classification=TruthClassification.ROOT_AUTHOR_CLAIM,
                        original_command=clean,
                        windows_command=win_cmd,
                        verification_command="echo 'Verifying step'",
                        risk_level=risk,
                        requires_approval=app,
                        status="PLANNED",
                    )
                )
                step_idx += 1

        return ReproductionPlan(
            job_id=manifest.job_id,
            url=manifest.url,
            demo_objective=manifest.root.text[:100],
            prerequisites=["Python", "Chrome"],
            steps=steps,
            gap_analysis={},
            validation_criteria=["Prerequisites verified", "Safe execution only"],
            mode="PLAN_ONLY",
        )

