"""Shared subprocess plumbing for CLI-based runtimes (Hermes, Claude, Codex)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from abc import abstractmethod

from .base import AgentRuntime, ConversationInput, RuntimeResult, extract_json


class CliRuntime(AgentRuntime):
    default_timeout = 240

    def __init__(self, executable: list[str] | None = None, timeout: int | None = None, model: str | None = None):
        self._executable = executable
        self.timeout = timeout or self.default_timeout
        self.model = model

    # -- adapter hooks -------------------------------------------------
    @abstractmethod
    def locate(self) -> list[str] | None:
        """Return the argv prefix for the installed CLI, or None if missing."""

    @abstractmethod
    def build_args(self, request: ConversationInput) -> list[str]: ...

    def stdin_prompt(self, request: ConversationInput) -> str | None:
        """Return the prompt to send on stdin instead of argv (for .cmd shims), or None."""
        return None

    def parse(self, stdout: str) -> tuple[str, str | None]:
        """Return (text, session_id)."""
        return stdout.strip(), None

    # -- contract --------------------------------------------------------
    def executable(self) -> list[str] | None:
        return self._executable or self.locate()

    def run(self, request: ConversationInput) -> RuntimeResult:
        started = time.perf_counter()
        exe = self.executable()
        if not exe:
            return self._fail(request, started, "NOT_INSTALLED")
        # MARKETING_NESTED marks every child: a nested MCP server must never start or recover workflows.
        env = {**os.environ, "MARKETING_CORRELATION_ID": request.correlation_id, "MARKETING_NESTED": "1"}
        if request.workflow_id:
            env["MARKETING_WORKFLOW_ID"] = request.workflow_id
        piped = self.stdin_prompt(request)
        io = {"input": piped.encode("utf-8")} if piped is not None else {"stdin": subprocess.DEVNULL}
        try:
            completed = subprocess.run(
                [*exe, *self.build_args(request)],
                capture_output=True,
                timeout=self.timeout,
                env=env,
                check=False,
                **io,
            )
        except subprocess.TimeoutExpired:
            return self._fail(request, started, "TIMEOUT")
        except OSError as exc:
            return self._fail(request, started, type(exc).__name__)
        stdout = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode != 0:
            return self._fail(request, started, f"EXIT_{completed.returncode}")
        text, session_id = self.parse(stdout)
        return RuntimeResult(
            runtime=self.name,
            ok=bool(text),
            text=text,
            structured=extract_json(text) if request.expect_json else None,
            session_id=session_id or request.session_id,
            model=self.model,
            correlation_id=request.correlation_id,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error_code=None if text else "EMPTY_OUTPUT",
        )

    def _fail(self, request: ConversationInput, started: float, code: str) -> RuntimeResult:
        return RuntimeResult(
            runtime=self.name,
            ok=False,
            correlation_id=request.correlation_id,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error_code=code,
        )


def which(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def quick(argv: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, type(exc).__name__
    return done.returncode, (done.stdout + b"\n" + done.stderr).decode("utf-8", errors="replace")
