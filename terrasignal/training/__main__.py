"""Training CLI.

  uv run python -m terrasignal.training risk          # train + gate + register
  uv run python -m terrasignal.training rent
  uv run python -m terrasignal.training approve --model <name> --approver <user>
  uv run python -m terrasignal.training score         # batch score (approved only)
  uv run python -m terrasignal.training drift         # PSI vs training baseline
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="terrasignal.training")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("risk")
    sub.add_parser("rent")
    p_approve = sub.add_parser("approve")
    p_approve.add_argument("--model", required=True)
    p_approve.add_argument("--version", type=int, default=None)
    p_approve.add_argument("--approver", default="demo.approver")
    sub.add_parser("score")
    sub.add_parser("drift")
    args = parser.parse_args()

    if args.cmd == "risk":
        from terrasignal.training.risk_scorer import train

        train()
    elif args.cmd == "rent":
        from terrasignal.training.rent_forecaster import train

        train()
    elif args.cmd == "approve":
        from terrasignal.training.registry import approve_model

        approve_model(args.model, args.version, args.approver)
    elif args.cmd == "score":
        from terrasignal.training.batch_score import main as score_main

        score_main()
    elif args.cmd == "drift":
        from terrasignal.training.drift import compute_drift

        compute_drift()
    return 0


if __name__ == "__main__":
    sys.exit(main())
