from __future__ import annotations

import sys

from .bridge import main as bridge_main


def main() -> None:
    raise SystemExit(bridge_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
