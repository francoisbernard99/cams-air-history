"""Collector entry point.

    python -m collector                        # current day
    python -m collector --past-days 7          # the last 7 days
    python -m collector --start 2013-01-01 --end 2013-12-31   # the archive
"""

import argparse
import sys
from datetime import datetime, timezone

from collector import api, config, storage


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="collector",
        description="Collect CAMS air quality data through Open-Meteo.",
    )
    parser.add_argument("--past-days", type=int, help="number of past days to include")
    parser.add_argument("--start", help="range start, YYYY-MM-DD")
    parser.add_argument("--end", help="range end, YYYY-MM-DD")
    parser.add_argument("--output-dir", default="data", help="output directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the built URL without calling the API",
    )
    args = parser.parse_args(argv)

    if bool(args.start) != bool(args.end):
        parser.error("--start and --end go together")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    url = api.build_url(
        sites=config.SITES,
        species=config.SPECIES,
        start_date=args.start,
        end_date=args.end,
        past_days=args.past_days,
    )

    if args.dry_run:
        print(url)
        return 0

    print(f"{len(config.SITES)} sites, {len(config.SPECIES)} species")

    try:
        payloads = api.fetch(url)
    except api.SourceUnavailable as error:
        # TODO week 2: do not fail hard. Keep the last valid collection, report
        # the outage, and leave the site up.
        print(f"source unavailable: {error}", file=sys.stderr)
        return 1

    stamp = args.start or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = storage.output_path(args.output_dir, stamp)
    written = storage.write_rows(api.to_rows(payloads, config.SITES), path)

    print(f"{written} rows written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
