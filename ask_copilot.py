#!/usr/bin/env python3
"""
CLI for the AI Marketplace Analyst.

Requires ANTHROPIC_API_KEY to be set in the environment.

Usage:
    python ask_copilot.py "Which dispatch policy performs best during peak hours?"
    python ask_copilot.py "What happens if demand increases by 20%?"
    python ask_copilot.py --verbose "Which strategy should we launch?"
"""
from __future__ import annotations

import os
import sys

from src.ai_copilot import ask


def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args
    args = [a for a in args if a != "--verbose"]
    if not args:
        print(__doc__)
        return 1
    question = " ".join(args)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Export it and re-run, e.g.:\n"
              "  export ANTHROPIC_API_KEY=sk-ant-...\n"
              "  python ask_copilot.py \"" + question + "\"")
        return 1

    print(f"Q: {question}\n")
    answer = ask(question, verbose=verbose)
    print(f"A: {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
