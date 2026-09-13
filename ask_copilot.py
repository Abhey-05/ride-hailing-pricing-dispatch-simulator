#!/usr/bin/env python3
"""
CLI for the AI Marketplace Analyst.

Requires ANTHROPIC_API_KEY or GROQ_API_KEY to be set in the environment
(if both are set, ANTHROPIC_API_KEY wins unless AI_PROVIDER is set explicitly
-- see src/ai_copilot.py::resolve_provider).

Usage:
    python ask_copilot.py "Which dispatch policy performs best during peak hours?"
    python ask_copilot.py "What happens if demand increases by 20%?"
    python ask_copilot.py --verbose "Which strategy should we launch?"

    # force a provider explicitly:
    AI_PROVIDER=groq python ask_copilot.py "..."
"""
from __future__ import annotations

import sys

from src.env_utils import load_dotenv  # noqa: E402

load_dotenv()

from src.ai_copilot import ask, resolve_provider  # noqa: E402


def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args
    args = [a for a in args if a != "--verbose"]
    if not args:
        print(__doc__)
        return 1
    question = " ".join(args)

    try:
        provider = resolve_provider()
    except RuntimeError as e:
        print(f"{e}\n\nExamples:\n"
              "  export ANTHROPIC_API_KEY=sk-ant-...\n"
              "  export GROQ_API_KEY=gsk_...\n"
              f'  python ask_copilot.py "{question}"')
        return 1

    print(f"[using {provider}]")
    print(f"Q: {question}\n")
    answer = ask(question, verbose=verbose)
    print(f"A: {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
