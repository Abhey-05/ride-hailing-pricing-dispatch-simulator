"""
AI Marketplace Analyst -- a natural-language interface over the simulation's
results, built on LLM tool-calling.

Architecture (docs/PRD.md "AI guardrails" section has the full writeup):

    user question -> LLM -> picks a tool -> src.copilot_tools function
    runs (reads results/*.csv or runs a real simulation) -> tool result
    (numbers) fed back to the LLM -> LLM explains it in words.

The LLM NEVER computes a metric itself -- every number in its answer must
have come from a tool call. The system prompt enforces this, and every tool
result carries a `source` field the model is instructed to cite.

Provider-agnostic by design (this is a real architectural claim, not just
words -- see docs/INTERVIEW_GUIDE.md Q51): the tool-calling loop is
implemented once per provider's API shape (Anthropic's `tool_use`/
`tool_result` content blocks vs. Groq/OpenAI's `tool_calls`/`role:"tool"`
messages), both driving the exact same SYSTEM_PROMPT and the exact same
src.copilot_tools functions, so switching providers changes zero product
behavior or guardrails.

Provider selection (checked in this order):
    1. AI_PROVIDER env var ("anthropic" or "groq"), if set explicitly.
    2. ANTHROPIC_API_KEY present -> anthropic.
    3. GROQ_API_KEY present -> groq.
    4. Otherwise: raises a clear error telling the caller to set one.

Run interactively with:
    python ask_copilot.py "Which dispatch policy performs best during peak hours?"
"""
from __future__ import annotations

import json
import os

from src import copilot_tools

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM_PROMPT = """You are an AI Marketplace Analyst for a ride-hailing simulation project.

You answer questions about pricing policy, dispatch policy, and marketplace
experiment results for a Product Manager audience.

HARD RULES:
1. You must NEVER calculate, estimate, or guess a numerical metric yourself.
   Every number in your answer (wait times, percentages, revenue, p-values,
   confidence intervals, etc.) must come from a tool call result.
2. If a tool call does not give you the number you need, say so explicitly
   rather than approximating or inventing one.
3. Always cite which tool/source produced the numbers you quote (each tool
   result includes a `source` field -- mention it, e.g. "per
   results/core_comparisons.csv...").
4. Distinguish pre-computed experiment results (results/*.csv, from 1,080
   simulation runs) from a fresh live simulation you ran just now to answer
   a what-if question -- tell the user which kind of evidence you're using.
5. All data is synthetic simulation output, not real-world ride-hailing data.
   Never imply otherwise.
6. Keep answers concise and PM-friendly: lead with the answer, then the
   supporting numbers and their source, then a one-line caveat if relevant.
"""

TOOLS = [
    {
        "name": "get_policy_metrics",
        "description": "Get the mean metrics (across all seeds run) for one (pricing policy, dispatch policy, scenario) combination from the pre-computed 1,080-run experiment matrix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pricing_policy": {"type": "string", "enum": ["NO_SURGE", "BASIC_SURGE", "AGGRESSIVE_SURGE", "CAPPED_SMOOTHED_SURGE"]},
                "dispatch_policy": {"type": "string", "enum": ["NEAREST_DRIVER", "ETA_OPTIMIZED", "DRIVER_EARNINGS_AWARE", "MARKETPLACE_AWARE", "ADVANCED_HEURISTIC"]},
                "scenario": {"type": "string", "enum": ["NORMAL", "PEAK_DEMAND", "SUPPLY_SHORTAGE", "DEMAND_SHOCK", "LOW_DEMAND", "CONGESTED_PEAK"], "default": "NORMAL"},
            },
            "required": ["pricing_policy", "dispatch_policy"],
        },
    },
    {
        "name": "compare_dispatch_to_baseline",
        "description": "Get the statistically-tested paired comparison (mean difference, 95% bootstrap CI, Wilcoxon p-value, practical-significance verdict) of one dispatch policy vs. the NEAREST_DRIVER baseline, under one pricing policy, for one metric. This is the authoritative source for 'is X better than Y, and is it statistically real' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pricing_policy": {"type": "string", "enum": ["NO_SURGE", "BASIC_SURGE", "AGGRESSIVE_SURGE", "CAPPED_SMOOTHED_SURGE"]},
                "dispatch_policy": {"type": "string", "enum": ["ETA_OPTIMIZED", "DRIVER_EARNINGS_AWARE", "MARKETPLACE_AWARE", "ADVANCED_HEURISTIC"]},
                "metric": {"type": "string", "enum": ["p90_wait_min", "avg_wait_min", "completion_rate", "cancellation_rate", "earnings_per_online_hour_mean", "driver_utilization_mean", "platform_revenue"], "default": "p90_wait_min"},
            },
            "required": ["pricing_policy", "dispatch_policy"],
        },
    },
    {
        "name": "get_decision_table",
        "description": "Get the top-N policy combinations ranked by North Star metric (completed trips per online driver-hour), each annotated with whether it clears every guardrail vs. the baseline. This is the authoritative source for 'which strategy should we launch' questions.",
        "input_schema": {
            "type": "object",
            "properties": {"top_n": {"type": "integer", "default": 5}},
        },
    },
    {
        "name": "get_zone_supply_demand_ranking",
        "description": "Run a real simulation and return every zone's average supply/demand ratio over the simulated day, ranked worst (most undersupplied) first. Use this for 'which zone has the biggest supply shortage' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "enum": ["NORMAL", "PEAK_DEMAND", "SUPPLY_SHORTAGE", "DEMAND_SHOCK", "LOW_DEMAND", "CONGESTED_PEAK"], "default": "NORMAL"},
                "pricing_policy": {"type": "string", "default": "BASIC_SURGE"},
                "dispatch_policy": {"type": "string", "default": "NEAREST_DRIVER"},
                "seed": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "simulate_whatif",
        "description": "Run a fresh, real simulation with an optional override of a scenario's demand or supply multiplier (e.g. to answer 'what happens if demand increases by 20%?', pass demand_multiplier_override = current_scenario_demand_mult * 1.2). Returns the full real metric summary from that run -- not an estimate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pricing_policy": {"type": "string", "default": "BASIC_SURGE"},
                "dispatch_policy": {"type": "string", "default": "NEAREST_DRIVER"},
                "scenario": {"type": "string", "default": "NORMAL"},
                "demand_multiplier_override": {"type": "number"},
                "supply_multiplier_override": {"type": "number"},
                "seed": {"type": "integer", "default": 0},
            },
        },
    },
]


def _execute_tool(name: str, tool_input: dict) -> dict:
    fn = copilot_tools.TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return fn(**tool_input)
    except Exception as e:  # tool errors are returned to the model, not raised
        return {"error": str(e)}


def _openai_style_tools() -> list[dict]:
    """Groq's API (and OpenAI's) wants {"type": "function", "function": {...}}
    instead of Anthropic's flatter {"name", "description", "input_schema"} --
    same content, different envelope. Converted once here so TOOLS stays the
    single source of truth for what the copilot can do."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOLS
    ]


def resolve_provider() -> str:
    explicit = os.environ.get("AI_PROVIDER", "").strip().lower()
    if explicit in ("anthropic", "groq"):
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    raise RuntimeError(
        "No LLM API key found. Set ANTHROPIC_API_KEY or GROQ_API_KEY "
        "(optionally AI_PROVIDER=anthropic|groq to force one)."
    )


def _ask_anthropic(question: str, max_turns: int, verbose: bool) -> str:
    import anthropic  # imported lazily so the rest of the project works without the SDK/key

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": question}]

    for _ in range(max_turns):
        response = client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=1024, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"[tool call] {block.name}({block.input})")
            result = _execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})

    return "Reached max tool-call turns without a final answer -- the question may be too complex or ambiguous."


def _ask_groq(question: str, max_turns: int, verbose: bool) -> str:
    import groq  # imported lazily so the rest of the project works without the SDK/key

    client = groq.Groq()  # reads GROQ_API_KEY from the environment
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools = _openai_style_tools()

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=GROQ_MODEL, max_tokens=1024, tools=tools, tool_choice="auto", messages=messages,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            if verbose:
                print(f"[tool call] {tc.function.name}({args})")
            result = _execute_tool(tc.function.name, args)
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    return "Reached max tool-call turns without a final answer -- the question may be too complex or ambiguous."


def ask(question: str, max_turns: int = 6, verbose: bool = False) -> str:
    provider = resolve_provider()
    if verbose:
        print(f"[provider] {provider}")
    if provider == "groq":
        return _ask_groq(question, max_turns, verbose)
    return _ask_anthropic(question, max_turns, verbose)
