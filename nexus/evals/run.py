"""
Eval runner CLI:  python -m nexus.evals.run [--live] [--json]

Runs the metric suite over the golden dataset and prints a report. Exit code is
non-zero if any metric fails (usable as a CI gate).
"""
from __future__ import annotations

import argparse
import json
import sys

from . import GOLDEN_CASES, EvalHarness, default_metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="nexus-evals")
    parser.add_argument("--live", action="store_true", help="also run metrics that need a live model")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    harness = EvalHarness(GOLDEN_CASES)
    report = harness.run(default_metrics(), include_live=args.live)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.render())

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
