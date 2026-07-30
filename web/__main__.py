"""Web page entry point.

    python -m web            # writes public/index.html from air.duckdb
"""

import argparse

from web import build as web


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="web",
        description="Render the static page from the DuckDB warehouse.",
    )
    parser.add_argument("--database", default=web.DEFAULT_DATABASE, help="DuckDB file")
    parser.add_argument(
        "--output-dir", default=web.DEFAULT_OUTPUT, help="directory to write into"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = web.build(args.database, args.output_dir)
    size = round(len(open(path, encoding="utf-8").read()) / 1024)
    print(f"{path} written ({size} KB, self-contained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
