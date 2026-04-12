from __future__ import annotations

import argparse
import sys

from otto.logging_utils import get_logger
from otto.orchestration.brain import (
    run_brain_self_model,
    run_brain_predictions,
    run_brain_ritual_cycle,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="otto brain", description="Otto Brain operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("self-model", help="Build Otto self-model from vault scan")
    sub.add_parser("predictions", help="Generate Otto predictions from profile")
    sub.add_parser("ritual", help="Run full scan/reflect/dream/act cycle")
    sub.add_parser("all", help="Run self-model + predictions + ritual cycle")

    args = parser.parse_args()

    if args.command == "self-model":
        result = run_brain_self_model()
        print(f"Self-model: {result}")
        return 0 if result.get("status") == "ok" else 1
    elif args.command == "predictions":
        result = run_brain_predictions()
        print(f"Predictions: {result}")
        return 0 if result.get("status") == "ok" else 1
    elif args.command == "ritual":
        result = run_brain_ritual_cycle()
        print(f"Ritual cycle: {result}")
        return 0 if result.get("status") == "ok" else 1
    elif args.command == "all":
        sm = run_brain_self_model()
        pred = run_brain_predictions()
        ritual = run_brain_ritual_cycle()
        print("=== Otto Brain All ===")
        print(f"Self-model: {sm}")
        print(f"Predictions: {pred}")
        print(f"Ritual: {ritual}")
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
