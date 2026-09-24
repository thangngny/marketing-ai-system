"""Every AgentRuntime implementation must pass this same suite."""

import os
import sys
from pathlib import Path

import pytest

from marketing_system.runtime import (
    AgentRuntime, ClaudeRuntime, CodexRuntime, ConversationInput, HermesRuntime, MockRuntime, get_runtime,
)
from marketing_system.specialists import SPECIALISTS

FAKE = [sys.executable, str(Path(__file__).with_name("fake_cli.py"))]


def make(name: str, **kwargs) -> AgentRuntime:
    if name == "mock":
        return MockRuntime(**kwargs)
    cls = {"hermes": HermesRuntime, "claude": ClaudeRuntime, "codex": CodexRuntime}[name]
    return cls(executable=[*FAKE, name], timeout=kwargs.get("timeout", 30))


RUNTIMES = ["mock", "hermes", "claude", "codex"]


def req(text="xin chào", **kw) -> ConversationInput:
    return ConversationInput(text=text, correlation_id="corr-123", source="test", **kw)


@pytest.fixture(autouse=True)
def _fake_mode(monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "ok")


@pytest.mark.parametrize("name", RUNTIMES)
def test_accepts_normalized_input_and_returns_result(name):
    result = make(name).run(req())
    assert result.ok and result.text
    assert result.runtime == name
    assert result.correlation_id == "corr-123"


@pytest.mark.parametrize("name", RUNTIMES)
def test_invokes_specialist_with_its_instructions(name):
    runtime = make(name)
    result = runtime.invoke_specialist(SPECIALISTS["04_content"], req("Viết bài LinkedIn"))
    assert result.ok
    assert result.specialist == "04_content"
    if name == "mock":
        assert "04_content" in runtime.calls[-1].text
        assert "Marketing Content Skill" in runtime.calls[-1].text


@pytest.mark.parametrize("name", RUNTIMES)
def test_returns_structured_output_when_asked(name):
    result = make(name).run(req("Return JSON please", expect_json=True))
    assert isinstance(result.structured, dict)


@pytest.mark.parametrize("name", ["hermes", "claude", "codex"])
def test_propagates_correlation_id_to_child_process(name):
    result = make(name).run(req("[correlation_id=corr-123] check"))
    assert "corr=corr-123" in result.text
    assert "prompt_has_corr=True" in result.text


@pytest.mark.parametrize("name", RUNTIMES)
def test_fails_safely_without_raising(name, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    runtime = MockRuntime(fail_with="PROVIDER_DOWN") if name == "mock" else make(name)
    result = runtime.run(req())
    assert result.ok is False
    assert result.error_code


@pytest.mark.parametrize("name", ["hermes", "claude", "codex"])
def test_timeout_is_reported_not_raised(name, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "sleep")
    runtime = make(name)
    runtime.timeout = 1
    result = runtime.run(req())
    assert result.ok is False and result.error_code == "TIMEOUT"


@pytest.mark.parametrize("name", ["hermes", "claude", "codex"])
def test_empty_output_is_not_success(name, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "empty")
    result = make(name).run(req())
    assert result.ok is False and result.error_code == "EMPTY_OUTPUT"


@pytest.mark.parametrize("name", RUNTIMES)
def test_resume_session_or_declares_unsupported(name):
    runtime = make(name)
    if runtime.capabilities().sessions:
        first = runtime.run(req())
        second = runtime.continue_session(first.session_id, req("tiếp"))
        assert second.ok and second.session_id == first.session_id
    else:
        result = runtime.continue_session("any", req())
        assert result.ok is False and result.error_code == "SESSIONS_UNSUPPORTED"


@pytest.mark.parametrize("name", RUNTIMES)
def test_health_and_capabilities_are_typed(name):
    runtime = make(name)
    assert runtime.capabilities().one_shot is True
    health = runtime.health()
    assert health.runtime == name
    assert health.state in {"READY", "NEEDS_AUTH", "NOT_INSTALLED", "DEGRADED", "ERROR"}


def test_missing_executable_is_not_installed(monkeypatch):
    runtime = HermesRuntime()
    monkeypatch.setattr(runtime, "locate", lambda: None)
    assert runtime.run(req()).error_code == "NOT_INSTALLED"


def test_factory_defaults_to_mock_in_mock_environment(monkeypatch):
    monkeypatch.delenv("MARKETING_RUNTIME", raising=False)
    assert get_runtime(environment="mock").name == "mock"
    assert get_runtime(environment="production").name == "hermes"
    with pytest.raises(ValueError):
        get_runtime("nope")


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_RUNTIME_TESTS") != "1", reason="SKIPPED: set RUN_LIVE_RUNTIME_TESTS=1")
def test_live_hermes_marketing_profile_round_trip():
    runtime = HermesRuntime()
    assert runtime.health().state == "READY"
    result = runtime.run(req("Reply with exactly: HERMES_RUNTIME_OK"))
    assert result.ok and "HERMES_RUNTIME_OK" in result.text


def test_hermes_language_only_disables_rules_and_tools():
    from marketing_system.runtime.adapters import HermesRuntime

    args = HermesRuntime(executable=["hermes"]).build_args(
        ConversationInput(text="x", correlation_id="c", metadata={"language_only": True}))
    assert "--ignore-rules" in args and args[args.index("-t") + 1] == "todo"


def test_child_processes_are_marked_nested(monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "ok")
    import subprocess as sp

    seen = {}
    real = sp.run

    def spy(*a, **k):
        seen["env"] = k.get("env", {})
        return real(*a, **k)

    monkeypatch.setattr(sp, "run", spy)
    make("hermes").run(req())
    assert seen["env"].get("MARKETING_NESTED") == "1"
