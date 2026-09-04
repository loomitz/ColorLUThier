# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private worker using public unittest APIs and the existing acceptance suites."""

import re
import unittest
from pathlib import Path

from . import canonical_json, digest, require

FOCUSED_MODULES = (
    "test_color_context_declaration.py", "test_color_context_scaffold.py",
    "test_color_document.py", "test_engine_portable_cube_conformance.py",
    "test_full_resolution_evaluation.py", "test_image_source_port.py",
    "test_preview_full_resolution_parity.py",
)
SAFARI_SKIP = (
    "test_internal_test_ui_e2e.InternalTestUiMacOsSurfaceAcceptanceTest."
    "test_documented_command_opens_and_closes_only_its_real_surface"
)


class SummaryResult(unittest.TestResult):
    """Count outcomes without storing traceback, skip reason, or test payloads."""

    def __init__(self):
        super().__init__()
        self.counts = dict.fromkeys(("passed", "skipped", "failures", "errors",
                                    "expected_failures", "unexpected_successes", "unexpected_skips"), 0)

    def addSuccess(self, test):
        self.counts["passed"] += 1

    def addError(self, test, err):
        self.counts["errors"] += 1

    def addFailure(self, test, err):
        self.counts["failures"] += 1

    def addSkip(self, test, reason):
        self.counts["skipped"] += 1
        self.counts["unexpected_skips"] += int(test.id() != SAFARI_SKIP)

    def addExpectedFailure(self, test, err):
        self.counts["expected_failures"] += 1

    def addUnexpectedSuccess(self, test):
        self.counts["unexpected_successes"] += 1

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.counts["failures" if issubclass(err[0], test.failureException) else "errors"] += 1

    def wasSuccessful(self):
        return not any(self.counts[name] for name in ("failures", "errors", "expected_failures",
                                                     "unexpected_successes", "unexpected_skips"))


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def run_suite(scope: str, root: Path) -> tuple[dict, int]:
    require(scope in ("focused", "full", "parity"), "arguments", "ARGUMENT_INVALID")
    loader = unittest.TestLoader()
    patterns = ("test_*.py",) if scope == "full" else (
        ("test_preview_full_resolution_parity.py",) if scope == "parity" else FOCUSED_MODULES)
    suite = unittest.TestSuite(loader.discover(str(root / "tests"), pattern=pattern) for pattern in patterns)
    identifiers = sorted(test_ids(suite))
    require(0 < len(identifiers) <= 10000 and len(set(identifiers)) == len(identifiers), scope + "_tests")
    require(all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,255}", name) for name in identifiers), scope + "_tests")
    result = SummaryResult()
    suite.run(result)
    require(result.testsRun == len(identifiers), scope + "_tests")
    record = {"run": result.testsRun, **result.counts,
              "test_inventory_sha256": digest(canonical_json(identifiers))}
    return record, 0 if result.wasSuccessful() else 1
