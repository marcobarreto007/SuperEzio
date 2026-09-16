import sys

from core.heart.poller import ingest_cli

if __name__ == "__main__":
    raise SystemExit(ingest_cli(sys.argv[1:]))
