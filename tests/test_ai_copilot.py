import pytest

from src import ai_copilot


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("AI_PROVIDER", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_resolve_provider_no_key_raises():
    with pytest.raises(RuntimeError):
        ai_copilot.resolve_provider()


def test_resolve_provider_anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    assert ai_copilot.resolve_provider() == "anthropic"


def test_resolve_provider_groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-fake")
    assert ai_copilot.resolve_provider() == "groq"


def test_resolve_provider_explicit_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-fake")
    monkeypatch.setenv("AI_PROVIDER", "groq")
    assert ai_copilot.resolve_provider() == "groq"


def test_openai_style_tools_matches_anthropic_tools():
    openai_tools = ai_copilot._openai_style_tools()
    assert len(openai_tools) == len(ai_copilot.TOOLS)
    for anthropic_tool, openai_tool in zip(ai_copilot.TOOLS, openai_tools):
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == anthropic_tool["name"]
        assert openai_tool["function"]["parameters"] == anthropic_tool["input_schema"]


def test_all_tool_names_exist_in_registry():
    from src import copilot_tools
    for tool in ai_copilot.TOOLS:
        assert tool["name"] in copilot_tools.TOOL_REGISTRY
