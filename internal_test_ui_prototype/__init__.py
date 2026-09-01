# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Disposable, dependency-free browser surface for adapter testing."""

from ._application import PrototypeApplication, UiNotice
from ._executor import ManualExecutor
from ._http import create_server, render_page, server_url

__all__ = (
    "ManualExecutor",
    "PrototypeApplication",
    "UiNotice",
    "create_server",
    "render_page",
    "server_url",
)
