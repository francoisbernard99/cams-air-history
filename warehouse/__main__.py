"""Warehouse entry point.

    python -m warehouse build            # (re)build the database from the CSVs
    python -m warehouse list             # list the questions available
    python -m warehouse ask worst-days   # answer one of them
"""

import argparse
import sys

import duckdb

from warehouse import build as warehouse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    # The shared options live on a parent parser so they are accepted on either
    # side of the subcommand. Argparse otherwise only takes them *before* it,
    # and `warehouse build --data-dir X` failing is a trap not worth setting.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir",
        default=warehouse.DEFAULT_DATA_DIR,
        help="directory holding the daily CSV files",
    )
    common.add_argument(
        "--database", default=warehouse.DEFAULT_DATABASE, help="DuckDB file"
    )

    parser = argparse.ArgumentParser(
        prog="warehouse",
        parents=[common],
        description="Query the archive of collected air quality data.",
    )

    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", parents=[common],
                        help="rebuild the database from the CSV files")
    commands.add_parser("list", parents=[common],
                        help="list the questions available")

    ask = commands.add_parser("ask", parents=[common], help="answer one question")
    ask.add_argument("name", help="query name, as listed by `list`")
    ask.add_argument("--limit", type=int, default=20, help="rows to display")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "list":
        for name in warehouse.available_queries():
            print(name)
        return 0

    if args.command == "build":
        summary = warehouse.build(args.data_dir, args.database)
        print(f"{summary['rows']} rows, {summary['days']} days, "
              f"{summary['sites']} sites, {summary['species']} species")
        print(f"{summary['first_hour']} -> {summary['last_hour']}")
        if summary["gaps"]:
            print(f"warning: {summary['gaps']} incomplete day(s), "
                  f"ask archive-health for details")
        if summary["outages"]:
            print(f"warning: {summary['outages']} run(s) reported an outage")
        print(f"database written to {args.database}")
        return 0

    try:
        sql = warehouse.query_text(args.name)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1

    connection = duckdb.connect(args.database, read_only=True)
    try:
        print(connection.sql(sql).limit(args.limit))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
