"""CLI: generate a seeded synthetic portfolio, inject dirt, load to Postgres.

  uv run python -m terrasignal.synth --seed 42 --dirty-rate 0.006
  uv run python -m terrasignal.synth --dirty-rate 0.04   # trips the DQ halt (demo)
"""

from __future__ import annotations

import argparse
import json

import structlog

from terrasignal.settings import get_settings
from terrasignal.synth.dirt import inject
from terrasignal.synth.generator import generate, summarize
from terrasignal.synth.load import load

log = structlog.get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="TerraSignal synthetic data generator")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dirty-rate", type=float, default=0.006)
    parser.add_argument("--no-load", action="store_true", help="generate only, skip Postgres")
    args = parser.parse_args()

    portfolio = generate(seed=args.seed)
    log.info("generated", summary=summarize(portfolio))
    manifest = inject(portfolio, rate=args.dirty_rate, seed=args.seed + 1295)
    log.info(
        "dirt_injected",
        rate=args.dirty_rate,
        counts={k: len(v) for k, v in manifest.model_dump().items()},
    )

    settings = get_settings()
    manifest_dir = settings.data_dir / "synth"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "dirt_manifest.json").write_text(
        json.dumps(manifest.model_dump(), indent=2), encoding="utf-8"
    )
    (manifest_dir / "default_events.json").write_text(
        json.dumps({k: v.isoformat() for k, v in portfolio.default_events.items()}, indent=2),
        encoding="utf-8",
    )

    if not args.no_load:
        load(portfolio)
        log.info("loaded_to_postgres")


if __name__ == "__main__":
    main()
