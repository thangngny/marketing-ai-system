from __future__ import annotations

import re
import shutil
import subprocess
from typing import List, Tuple
from ..models import (
    ExecutionMode,
    ExtractedStep,
    JobManifest,
    ReproductionPlan,
    ReproductionStep,
    RiskLevel,
    TruthClassification,
    VerificationItem,
)
from ..security.policy import assess_command_risk


def translate_command_to_windows(command: str) -> str:
    """Translate common Unix/macOS commands to PowerShell / Windows equivalents."""
    cmd = command.strip()

    # Environment variables: export FOO=bar -> $env:FOO = "bar"
    m_export = re.match(r"^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$", cmd)
    if m_export:
        var_name = m_export.group(1)
        val = m_export.group(2).strip("\"'")
        return f'$env:{var_name} = "{val}"'

    # Package managers: brew install foo -> winget install foo
    if cmd.startswith("brew install "):
        pkg = cmd[len("brew install "):].strip()
        return f"winget install {pkg}"

    # Virtual environment activation: source .venv/bin/activate -> .\.venv\Scripts\Activate.ps1
    if "source " in cmd and "activate" in cmd:
        return r".\.venv\Scripts\Activate.ps1"

    # python3 -> python
    if cmd.startswith("python3 "):
        return "python " + cmd[len("python3 "):]

    return cmd


def verify_installed_tool(tool_name: str) -> Tuple[bool, str]:
    """Check if a tool exists in PATH and report its version."""
    path = shutil.which(tool_name)
    if not path:
        return False, "NOT_INSTALLED"
    try:
        proc = subprocess.run([tool_name, "--version"], capture_output=True, text=True, timeout=5)
        ver = (proc.stdout or proc.stderr).splitlines()[0].strip()
        return True, ver
    except Exception:
        return True, "INSTALLED"


def build_reproduction_plan(
    manifest: JobManifest,
    target_os: str = "windows",
    mode: ExecutionMode = ExecutionMode.PLAN_ONLY
) -> ReproductionPlan:
    """Generate safe, validated reproduction plan with OS translations and risk gating."""
    demo_objective = f"Reproduce demo from {manifest.source_url}"
    if manifest.post_text:
        first_line = manifest.post_text.splitlines()[0].strip()
        if len(first_line) > 10:
            demo_objective = first_line[:120]

    plan_steps: List[ReproductionStep] = []
    verifications: List[VerificationItem] = []

    # Verify standard platform baseline
    baseline_tools = ["git", "node", "python", "ffmpeg", "yt-dlp"]
    for tool in baseline_tools:
        installed, ver = verify_installed_tool(tool)
        verifications.append(VerificationItem(
            component=tool,
            video_version="assumed_latest",
            current_version=ver,
            is_compatible=installed,
            is_outdated=False,
            notes=f"Local system tool check: {ver}",
            action_recommendation="Use existing system installation" if installed else f"Install {tool} on Windows"
        ))

    step_id = 1
    has_approval_required = False

    for extracted in manifest.extracted_steps:
        cmd = extracted.command_candidate
        if not cmd:
            continue

        # Assess risk
        risk, req_approval, reasons = assess_command_risk(cmd)
        if req_approval:
            has_approval_required = True

        # Translate command if target OS is Windows
        win_cmd = translate_command_to_windows(cmd) if target_os.lower() == "windows" else cmd

        # Create rollback plan
        rollback = ""
        if win_cmd.startswith("git clone "):
            repo_name = win_cmd.split("/")[-1].replace(".git", "").strip()
            rollback = f"Remove-Item -Recurse -Force {repo_name} -ErrorAction SilentlyContinue"
        elif "install" in win_cmd:
            rollback = "Revert installed package or discard virtualenv changes"

        plan_steps.append(ReproductionStep(
            step_id=step_id,
            observed_video_step=extracted.observed_action,
            verified_current_step=f"Execute: {win_cmd}" + (f" ({', '.join(reasons)})" if reasons else ""),
            command_or_action=win_cmd,
            translated_windows_command=win_cmd,
            files_changed=[],
            risk_level=risk,
            requires_approval=req_approval,
            rollback_plan=rollback,
            expected_result="Command executes with exit code 0",
            execution_status="PENDING",
            actual_result=""
        ))
        step_id += 1

    return ReproductionPlan(
        job_id=manifest.job_id,
        source_url=manifest.source_url,
        demo_objective=demo_objective,
        demo_architecture="Local-first Codex execution",
        target_os=target_os,
        mode=mode,
        steps=plan_steps,
        verifications=verifications,
        approval_state="PENDING" if has_approval_required else "NOT_REQUIRED",
        overall_status="PLAN_READY"
    )
