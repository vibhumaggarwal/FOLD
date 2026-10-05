"""
Command-line interface:

    fold encode report.pdf                  # -> report.pdf.avi (lossless)
    fold encode report.pdf --robust         # -> report.pdf.mp4 (survives re-encoding)
    fold decode report.pdf.mp4              # -> report.pdf
    fold info report.pdf.mp4
"""

import argparse
import logging
import os
import sys

from fold import retrieve_file, store
from fold.exceptions import FOLDException


def _encode(args):
    ext = ".mp4" if args.robust else ".avi"
    out = args.output or os.path.basename(args.input) + ext
    store(args.input, out, mode="robust" if args.robust else "lossless", fps=args.fps)
    print(f"{args.input} -> {out} ({os.path.getsize(out):,} bytes)")


def _decode(args):
    name, data = retrieve_file(args.video)
    out = args.output or name or "decoded_file.bin"
    if os.path.exists(out) and not args.force:
        sys.exit(f"{out} already exists (use -o to pick another name or -f to overwrite)")
    with open(out, "wb") as f:
        f.write(data)
    print(f"{args.video} -> {out} ({len(data):,} bytes, checksum OK)")


def _info(args):
    name, data = retrieve_file(args.video)
    print(f"File:     {name or '(no name stored)'}")
    print(f"Size:     {len(data):,} bytes")
    print("Checksum: OK")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fold", description="Store any file inside a video and get it back.")
    parser.add_argument("-v", "--verbose", action="store_true", help="show progress logs")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("encode", help="turn a file into a video")
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--robust", action="store_true",
                   help="MP4 that survives compression and re-uploads (larger, slower)")
    p.add_argument("--fps", type=int, default=30)
    p.set_defaults(func=_encode)

    p = sub.add_parser("decode", help="get the original file back from a video")
    p.add_argument("video")
    p.add_argument("-o", "--output")
    p.add_argument("-f", "--force", action="store_true", help="overwrite an existing file")
    p.set_defaults(func=_decode)

    p = sub.add_parser("info", help="show what's stored in a video")
    p.add_argument("video")
    p.set_defaults(func=_info)

    args = parser.parse_args(argv)
    if not args.verbose:
        logging.getLogger("fold").setLevel(logging.WARNING)
        for name in ("fold.encoder", "fold.decoder"):
            logging.getLogger(name).setLevel(logging.WARNING)

    try:
        args.func(args)
    except (FOLDException, FileNotFoundError, ValueError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
