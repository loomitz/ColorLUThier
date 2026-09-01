# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""One-command entry point for the disposable browser prototype."""

from __future__ import annotations

import argparse
import webbrowser
from collections.abc import Sequence

from ._application import PrototypeApplication
from ._http import create_server, server_url


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the disposable ColorLUThier Internal Test UI.",
    )
    parser.add_argument(
        "--port",
        default=0,
        type=int,
        help="loopback port; 0 selects an ephemeral port",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not open the default browser",
    )
    arguments = parser.parse_args(argv)

    application = PrototypeApplication()
    server = create_server(application, port=arguments.port)
    url = server_url(server)
    print(url, flush=True)
    if not arguments.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
