"""Stable launcher for source checkouts and clean company installations."""
from pathlib import Path
import sys


def main(argv=None):
    root=Path(__file__).resolve().parent
    runtime=root/'app' if (root/'app'/'FastmarketsCollector_v3_7.py').is_file() else root
    sys.path.insert(0,str(runtime))
    from FastmarketsCollector_v3_7 import main as run
    return run(argv)


if __name__=='__main__':
    raise SystemExit(main())
