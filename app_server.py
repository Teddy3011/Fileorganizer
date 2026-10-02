#!/usr/bin/env python3
"""Start StudySort: watch a Downloads folder and serve the dashboard on 127.0.0.1.

    python app_server.py                          # watches ~/Downloads
    python app_server.py --watch "D:\\Downloads"   # any other folder
"""

import argparse
import ipaddress
import os
import sys
from pathlib import Path

from studysort.server import create_app
from studysort.service import StudySortService
from studysort.store import Store


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--watch", default=str(Path.home() / "Downloads"),
                   help="folder to watch (default: your Downloads folder)")
    p.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=4173)
    p.add_argument("--auto-organize", action="store_true",
                   help="copy new files without waiting for approval in the dashboard")
    p.add_argument("--move", action="store_true",
                   help="move instead of copy (the original is deleted after a verified copy)")
    p.add_argument("--data-dir", default=str(Path(__file__).resolve().parent / "data"),
                   help="where history.sqlite3 is kept (default: ./data)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    watch = os.path.abspath(os.path.expanduser(args.watch))
    if not os.path.isdir(watch):
        sys.exit(f"Error: watched folder does not exist: {watch}")
    try:
        loopback = args.host == "localhost" or ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        print(f"Warning: binding to {args.host} exposes your file history to the network.")

    os.makedirs(args.data_dir, exist_ok=True)
    service = StudySortService(watch, Store(os.path.join(args.data_dir, "history.sqlite3")),
                               auto_organize=args.auto_organize, move=args.move)
    service.start()
    mode = "move" if args.move else "copy"
    print(f"Watching {watch}  ({mode} mode, {'auto-organize' if args.auto_organize else 'approval required'})")
    print(f"Dashboard: http://{args.host}:{args.port}")

    import uvicorn

    try:
        uvicorn.run(create_app(service), host=args.host, port=args.port, log_level="warning",
                    timeout_graceful_shutdown=1)
    finally:
        service.stop()


if __name__ == "__main__":
    main()
