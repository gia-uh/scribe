from __future__ import annotations

import argparse
import sys

from .api import from_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="scribe", description="Convert documents to Markdown (no LLM)."
    )
    ap.add_argument("input", help="path to a document")
    ap.add_argument("-o", "--output", help="write Markdown here (default: stdout)")
    args = ap.parse_args(argv)
    try:
        result = from_path(args.input)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result.markdown)
    else:
        sys.stdout.write(result.markdown)
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0
