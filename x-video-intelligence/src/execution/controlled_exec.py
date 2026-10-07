from __future__ import annotations

import subprocess
from typing import Dict, Any, Optional
from ..models import ExecutionMode, ReproductionPlan, ReproductionStep, RiskLevel


def execute_plan_step(
    plan: ReproductionPlan,
    step_id: int,
    approval_token: Optional[str] = None,
    timeout_sec: int = 120
) -> Dict[str, Any]:
    """Execute a single step from the reproduction plan under strict safety gates."""
    step = next((s for s in plan.steps if s.step_id == step_id), None)
    if not step:
        return {"status": "ERROR", "message": f"Step {step_id} not found in plan."}

    # Gate 1: Check Execution Mode
    if plan.mode in [ExecutionMode.ANALYZE_ONLY, ExecutionMode.PLAN_ONLY]:
        return {
            "status": "BLOCKED",
            "message": f"Execution is blocked because current mode is {plan.mode.value}. Switch to REPRODUCE_SAFE or REPRODUCE_FULL to execute."
        }

    # Gate 2: Check Approval Requirement
    if step.requires_approval:
        if not approval_token or approval_token.strip().lower() != "approved":
            step.execution_status = "BLOCKED_APPROVAL"
            return {
                "status": "BLOCKED_APPROVAL",
                "risk_level": step.risk_level.value,
                "command": step.command_or_action,
                "message": "This step requires explicit user approval before execution."
            }

    # Gate 3: Check Risk in Safe Mode
    if plan.mode == ExecutionMode.REPRODUCE_SAFE and step.risk_level in [RiskLevel.HIGH, RiskLevel.DESTRUCTIVE]:
        if not approval_token or approval_token.strip().lower() != "approved":
            step.execution_status = "BLOCKED_APPROVAL"
            return {
                "status": "BLOCKED_APPROVAL",
                "risk_level": step.risk_level.value,
                "message": f"Step has {step.risk_level.value} risk and cannot run automatically in REPRODUCE_SAFE mode without approval."
            }

    # Execute command safely in PowerShell
    cmd = step.translated_windows_command or step.command_or_action
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        if proc.returncode == 0:
            step.execution_status = "EXECUTED"
            step.actual_result = proc.stdout.strip() or "Executed successfully (returncode 0)"
            return {
                "status": "PASS",
                "exit_code": 0,
                "output": proc.stdout.strip(),
                "step_id": step_id
            }
        else:
            step.execution_status = "FAILED"
            step.actual_result = proc.stderr.strip() or f"Failed with code {proc.returncode}"
            return {
                "status": "FAIL",
                "exit_code": proc.returncode,
                "error": proc.stderr.strip(),
                "step_id": step_id
            }
    except subprocess.TimeoutExpired:
        step.execution_status = "FAILED"
        step.actual_result = f"Command timed out after {timeout_sec} seconds"
        return {"status": "TIMEOUT", "error": step.actual_result, "step_id": step_id}
    except Exception as e:
        step.execution_status = "FAILED"
        step.actual_result = f"Execution error: {str(e)}"
        return {"status": "ERROR", "error": str(e), "step_id": step_id}
