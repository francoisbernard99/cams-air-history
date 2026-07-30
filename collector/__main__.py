"""Collector entry point.

    python -m collector                          # today
    python -m collector --catch-up 7             # today plus the last 7 days
    python -m collector --start 2013-01-01 --end 2013-12-31   # backfill a year

Exit codes are meaningful, because automation reads them:

    0   collection succeeded
    1   unexpected failure -- a bug, the run must go red
    2   source unavailable -- an outage, the last valid data is kept
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from collector import api, config, runlog, storage

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SOURCE_UNAVAILABLE = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="collector",
        description="Collect CAMS air quality data through Open-Meteo.",
    )
    parser.add_argument(
        "--catch-up",
        type=int,
        default=0,
        metavar="N",
        help="also refetch the last N days, closing any gap left by an outage",
    )
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
    if args.catch_up < 0:
        parser.error("--catch-up expects a positive number of days")
    return args


def resolve_range(args: argparse.Namespace, today: str) -> tuple[str, str]:
    """Decide which day range to request.

    An explicit range wins. Otherwise the window ends today and reaches back
    `--catch-up` days, which is what makes the collector repair its own gaps.
    """
    if args.start and args.end:
        return args.start, args.end

    end = datetime.strptime(today, "%Y-%m-%d")
    start = end - timedelta(days=args.catch_up)
    return start.strftime("%Y-%m-%d"), today


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date, end_date = resolve_range(args, today)

    url = api.build_url(
        sites=config.SITES,
        species=config.SPECIES,
        start_date=start_date,
        end_date=end_date,
    )

    if args.dry_run:
        print(url)
        return EXIT_OK

    log_path = f"{args.output_dir}/{config.RUN_LOG_NAME}"
    entry = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "range": f"{start_date}..{end_date}",
        "sites": len(config.SITES),
        "species": len(config.SPECIES),
    }

    print(f"{start_date}..{end_date} - {len(config.SITES)} sites, "
          f"{len(config.SPECIES)} species")

    try:
        payloads = api.fetch(url)
    except api.SourceUnavailable as error:
        # An outage is not a bug. The previous files stay untouched, the run is
        # recorded, and the next run refetches this window anyway.
        entry.update(outcome="outage", error=str(error), days=0, rows=0)
        entry["duration_s"] = round(time.monotonic() - started, 2)
        runlog.append(log_path, entry)
        print(f"source unavailable: {error}", file=sys.stderr)
        print("last valid data kept", file=sys.stderr)
        return EXIT_SOURCE_UNAVAILABLE

    written = storage.write_daily(api.to_rows(payloads, config.SITES), args.output_dir)

    entry.update(
        outcome="ok",
        days=len(written),
        rows=sum(written.values()),
        duration_s=round(time.monotonic() - started, 2),
    )
    runlog.append(log_path, entry)

    for date, count in written.items():
        print(f"  {date}  {count} rows")
    print(f"{entry['rows']} rows across {entry['days']} day(s) in {args.output_dir}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
