"""Concrete runtimes. Each is a thin CLI adapter; none holds business logic."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .base import ConversationInput, RuntimeCapabilities, RuntimeHealth
from .cli import CliRuntime, quick, which


class HermesRuntime(CliRuntime):
    """Production runtime today: Hermes profile `marketing` (openai-codex OAuth).

    One-shot `-z` prints only the final text and no session id, so conversational
    continuity stays with the Hermes Buzz gateway; durable continuity lives in the
    workflow store, not in a Hermes session.
    """

    name = "hermes"

    def __init__(self, profile: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.profile = profile or os.getenv("MARKETING_HERMES_PROFILE", "marketing")

    def locate(self) -> list[str] | None:
        explicit = os.getenv("HERMES_BIN")
        if explicit and Path(explicit).exists():
            return [explicit]
        found = which("hermes")
        if found:
            return [found]
        candidate = Path(os.getenv("LOCALAPPDATA", "")) / "hermes" / "bin" / "hermes.exe"
        return [str(candidate)] if candidate.exists() else None

    def build_args(self, request: ConversationInput) -> list[str]:
        args = ["-p", self.profile]
        if self.model:
            args += ["-m", self.model]
        return [*args, "-z", request.text]

    def health(self) -> RuntimeHealth:
        exe = self.executable()
        if not exe:
            return RuntimeHealth(runtime=self.name, state="NOT_INSTALLED")
        code, out = quick([*exe, "-p", self.profile, "config", "get", "model"])
        model = provider = None
        for line in out.splitlines():
            key, _, value = line.strip().partition(":")
            if key == "default":
                model = value.strip()
            elif key == "provider":
                provider = value.strip()
        code_gw, gw = quick([*exe, "-p", self.profile, "gateway", "status"])
        # Truth comes from the process check, never from gateway_state.json (it goes stale).
        transport = "CONNECTED" if code_gw == 0 and "process running" in gw.lower() else "STOPPED"
        auth_file = Path(os.getenv("LOCALAPPDATA", "")) / "hermes" / "profiles" / self.profile / "auth.json"
        authed = code == 0 and provider is not None and auth_file.is_file() and auth_file.stat().st_size > 2
        return RuntimeHealth(
            runtime=self.name,
            state="READY" if authed else "NEEDS_AUTH",
            model=model,
            provider=provider,
            buzz_transport=transport,
            detail=f"profile={self.profile}",
        )

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(one_shot=True, sessions=False, mcp_tools=True, buzz_transport=True, production_enabled=True)


class ClaudeRuntime(CliRuntime):
    """Claude Code headless (`claude -p`). Also the Buzz Desktop ACP harness for the `Claude` agent."""

    name = "claude"

    def locate(self) -> list[str] | None:
        found = which("claude.cmd", "claude.exe", "claude")
        return [found] if found else None

    def build_args(self, request: ConversationInput) -> list[str]:
        args = ["-p", request.text, "--output-format", "json"]
        if request.session_id:
            args += ["--resume", request.session_id]
        if self.model:
            args += ["--model", self.model]
        return args

    def parse(self, stdout: str) -> tuple[str, str | None]:
        try:
            body = json.loads(stdout)
        except ValueError:
            return stdout.strip(), None
        return str(body.get("result") or "").strip(), body.get("session_id")

    def health(self) -> RuntimeHealth:
        exe = self.executable()
        if not exe:
            return RuntimeHealth(runtime=self.name, state="NOT_INSTALLED")
        code, out = quick([*exe, "--version"])
        return RuntimeHealth(runtime=self.name, state="READY" if code == 0 else "ERROR",
                             model=self.model, buzz_transport="NOT_APPLICABLE", detail=out.strip().splitlines()[0] if out.strip() else "")

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(one_shot=True, sessions=True, mcp_tools=True, buzz_transport=False, production_enabled=False)


class CodexRuntime(CliRuntime):
    """Codex CLI (`codex exec`). Final message is read from --output-last-message."""

    name = "codex"

    def locate(self) -> list[str] | None:
        found = which("codex.exe", "codex")
        return [found] if found else None

    def build_args(self, request: ConversationInput) -> list[str]:
        self._last_message = Path(tempfile.gettempdir()) / f"codex-last-{request.correlation_id}.txt"
        args = ["exec", "--skip-git-repo-check", "--output-last-message", str(self._last_message)]
        if self.model:
            args += ["-m", self.model]
        return [*args, request.text]

    def parse(self, stdout: str) -> tuple[str, str | None]:
        path = getattr(self, "_last_message", None)
        if path and path.exists():
            try:
                return path.read_text(encoding="utf-8").strip(), None
            finally:
                path.unlink(missing_ok=True)
        return stdout.strip(), None

    def health(self) -> RuntimeHealth:
        exe = self.executable()
        if not exe:
            return RuntimeHealth(runtime=self.name, state="NOT_INSTALLED")
        code, out = quick([*exe, "--version"])
        return RuntimeHealth(runtime=self.name, state="READY" if code == 0 else "ERROR",
                             model=self.model, buzz_transport="NOT_APPLICABLE", detail=out.strip().splitlines()[0] if out.strip() else "")

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(one_shot=True, sessions=False, mcp_tools=True, buzz_transport=False, production_enabled=False)
