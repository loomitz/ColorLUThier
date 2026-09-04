# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wait for Job Object assignment before starting any child command on Windows."""

import subprocess
import sys


def main():
    if sys.stdin.buffer.read(1) != b"\x00":
        return 2
    try:
        # Stay alive under the assigned Job Object until the command terminates.
        # Windows CRT exec overlay does not preserve POSIX replacement semantics.
        # The supervising collector owns the deadline and subtree termination.
        return subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL, check=False).returncode
    except (OSError, IndexError):
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
