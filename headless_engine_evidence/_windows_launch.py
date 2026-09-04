# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wait for Job Object assignment before starting any child command on Windows."""

import os
import sys


def main():
    if sys.stdin.buffer.read(1) != b"\x00":
        return 2
    try:
        os.execv(sys.argv[1], sys.argv[1:])
    except (OSError, IndexError):
        return 3
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
