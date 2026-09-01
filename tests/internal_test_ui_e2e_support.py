# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stdlib-only process, HTTP, HTML, and macOS helpers for UI acceptance."""

from __future__ import annotations

import os
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_READINESS_TIMEOUT_SECONDS = 10
_REQUEST_TIMEOUT_SECONDS = 5
_SHUTDOWN_TIMEOUT_SECONDS = 10
_APPLE_EVENT_TIMEOUT_SECONDS = 5
_APPLE_EVENT_ATTEMPTS = 40
_MAX_READINESS_BYTES = 256
_MAX_HTTP_BODY_BYTES = 1024 * 1024
_VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(frozen=True, slots=True)
class AccessibleElement:
    """One rendered element carrying a stable accessibility test identifier."""

    test_id: str
    tag: str
    attributes: tuple[tuple[str, str], ...]
    text: str
    definitions: tuple[tuple[str, str], ...]

    def attribute(self, name: str) -> str | None:
        return dict(self.attributes).get(name)

    def definition(self, term: str) -> str:
        try:
            return dict(self.definitions)[term]
        except KeyError:
            raise AssertionError(
                f"{self.test_id!r} does not expose definition {term!r}"
            ) from None


@dataclass(frozen=True, slots=True)
class AccessibleForm:
    """One server-rendered form and its explicit field values."""

    test_id: str | None
    method: str
    target: str
    fields: tuple[tuple[str, str], ...]

    @property
    def action(self) -> str | None:
        return self._validated_fields().get("action")

    def field(self, name: str) -> str:
        fields = self._validated_fields()
        try:
            return fields[name]
        except KeyError:
            raise AssertionError(f"form does not expose field {name!r}") from None

    def submission(
        self,
        overrides: dict[str, str] | None = None,
    ) -> tuple[tuple[str, str], ...]:
        fields = self._validated_fields()
        for name, value in ({} if overrides is None else overrides).items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise TypeError("form submission overrides must be text")
            fields[name] = value
        return tuple(fields.items())

    def _validated_fields(self) -> dict[str, str]:
        validated: dict[str, str] = {}
        for name, value in self.fields:
            if name in validated:
                raise AssertionError(f"form exposes duplicate field name {name!r}")
            validated[name] = value
        return validated


@dataclass(frozen=True, slots=True)
class AccessibleJob:
    """Rendered job state read only from public HTML attributes and cells."""

    job_id: int
    purpose: str
    state: str
    completed_units: int
    total_units: int
    cells: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AccessiblePage:
    """One complete HTTP or headless render parsed as accessible state."""

    status: int
    content_type: str
    payload: bytes
    elements: tuple[AccessibleElement, ...]
    forms: tuple[AccessibleForm, ...]
    jobs: tuple[AccessibleJob, ...]

    def element(self, test_id: str) -> AccessibleElement:
        matches = tuple(
            element for element in self.elements if element.test_id == test_id
        )
        if len(matches) != 1:
            raise AssertionError(
                f"expected one element {test_id!r}, found {len(matches)}"
            )
        return matches[0]

    def elements_with_prefix(self, prefix: str) -> tuple[AccessibleElement, ...]:
        return tuple(
            element
            for element in self.elements
            if element.test_id.startswith(prefix)
        )

    def form(self, test_id: str) -> AccessibleForm:
        matches = tuple(form for form in self.forms if form.test_id == test_id)
        if len(matches) != 1:
            raise AssertionError(
                f"expected one form {test_id!r}, found {len(matches)}"
            )
        return matches[0]

    def action_form(
        self,
        action: str,
        required_fields: dict[str, str] | None = None,
    ) -> AccessibleForm:
        expected = {} if required_fields is None else required_fields
        matches = []
        for form in self.forms:
            if form.action != action:
                continue
            try:
                if all(form.field(name) == value for name, value in expected.items()):
                    matches.append(form)
            except AssertionError:
                continue
        if len(matches) != 1:
            raise AssertionError(
                f"expected one action form {action!r}, found {len(matches)}"
            )
        return matches[0]

    def job(self, job_id: int) -> AccessibleJob:
        try:
            return next(job for job in self.jobs if job.job_id == job_id)
        except StopIteration:
            raise AssertionError(f"job {job_id} is not rendered") from None

    @property
    def latest_job(self) -> AccessibleJob:
        if not self.jobs:
            raise AssertionError("no rendered jobs")
        return max(self.jobs, key=lambda job: job.job_id)


@dataclass(slots=True)
class _ElementCapture:
    test_id: str
    tag: str
    depth: int
    attributes: tuple[tuple[str, str], ...]
    chunks: list[str]
    definitions: list[tuple[str, str]]


@dataclass(slots=True)
class _FormCapture:
    test_id: str | None
    depth: int
    method: str
    target: str
    fields: list[tuple[str, str]]


@dataclass(slots=True)
class _DefinitionCapture:
    tag: str
    depth: int
    element: _ElementCapture
    chunks: list[str]


@dataclass(slots=True)
class _SelectCapture:
    depth: int
    name: str
    multiple: bool
    options: list[tuple[str, bool]]


@dataclass(slots=True)
class _OptionCapture:
    depth: int
    value: str | None
    selected: bool
    chunks: list[str]


@dataclass(slots=True)
class _JobCapture:
    depth: int
    attributes: dict[str, str]
    cells: list[str]


@dataclass(slots=True)
class _CellCapture:
    depth: int
    chunks: list[str]


class _AccessiblePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.elements: list[AccessibleElement] = []
        self.forms: list[AccessibleForm] = []
        self.jobs: list[AccessibleJob] = []
        self._element_captures: list[_ElementCapture] = []
        self._form_capture: _FormCapture | None = None
        self._definition_capture: _DefinitionCapture | None = None
        self._pending_definition_term: tuple[_ElementCapture, str] | None = None
        self._select_capture: _SelectCapture | None = None
        self._option_capture: _OptionCapture | None = None
        self._job_capture: _JobCapture | None = None
        self._cell_capture: _CellCapture | None = None

    def handle_starttag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        self.depth += 1
        normalized = tuple((name, "" if value is None else value) for name, value in attributes)
        values = dict(normalized)
        test_id = values.get("data-testid")

        if test_id is not None:
            self._element_captures.append(
                _ElementCapture(
                    test_id=test_id,
                    tag=tag,
                    depth=self.depth,
                    attributes=normalized,
                    chunks=[],
                    definitions=[],
                )
            )

        if tag == "form":
            self._form_capture = _FormCapture(
                test_id=test_id,
                depth=self.depth,
                method=values.get("method", "get").lower(),
                target=values.get("action", ""),
                fields=[],
            )
        elif tag == "input" and self._form_capture is not None:
            name = values.get("name")
            input_type = values.get("type", "text").lower()
            successful = input_type not in {"checkbox", "radio"} or "checked" in values
            if name is not None and successful:
                default_value = "on" if input_type in {"checkbox", "radio"} else ""
                self._form_capture.fields.append((name, values.get("value", "")))
                if self._form_capture.fields[-1][1] == "" and default_value:
                    self._form_capture.fields[-1] = (name, default_value)
        elif tag == "select" and self._form_capture is not None:
            name = values.get("name")
            if name is not None:
                self._select_capture = _SelectCapture(
                    depth=self.depth,
                    name=name,
                    multiple="multiple" in values,
                    options=[],
                )
        elif tag == "option" and self._select_capture is not None:
            self._option_capture = _OptionCapture(
                depth=self.depth,
                value=values.get("value"),
                selected="selected" in values,
                chunks=[],
            )

        if tag in {"dt", "dd"} and self._element_captures:
            self._definition_capture = _DefinitionCapture(
                tag=tag,
                depth=self.depth,
                element=self._element_captures[-1],
                chunks=[],
            )

        if tag == "tr" and test_id is not None and test_id.startswith("job-"):
            self._job_capture = _JobCapture(
                depth=self.depth,
                attributes=values,
                cells=[],
            )
        elif tag == "td" and self._job_capture is not None:
            self._cell_capture = _CellCapture(depth=self.depth, chunks=[])

        if tag in _VOID_ELEMENTS:
            self.depth -= 1

    def handle_startendtag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attributes)
        if tag not in _VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for capture in self._element_captures:
            capture.chunks.append(data)
        if self._definition_capture is not None:
            self._definition_capture.chunks.append(data)
        if self._option_capture is not None:
            self._option_capture.chunks.append(data)
        if self._cell_capture is not None:
            self._cell_capture.chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if (
            self._option_capture is not None
            and tag == "option"
            and self._option_capture.depth == self.depth
        ):
            option = self._option_capture
            value = _normalize(option.chunks) if option.value is None else option.value
            if self._select_capture is not None:
                self._select_capture.options.append((value, option.selected))
            self._option_capture = None

        if (
            self._select_capture is not None
            and tag == "select"
            and self._select_capture.depth == self.depth
        ):
            select = self._select_capture
            selected = tuple(value for value, is_selected in select.options if is_selected)
            if select.multiple:
                chosen = selected
            elif selected:
                chosen = selected[-1:]
            else:
                chosen = tuple(value for value, _ in select.options[:1])
            if self._form_capture is not None:
                self._form_capture.fields.extend((select.name, value) for value in chosen)
            self._select_capture = None

        if (
            self._cell_capture is not None
            and tag == "td"
            and self._cell_capture.depth == self.depth
        ):
            if self._job_capture is not None:
                self._job_capture.cells.append(_normalize(self._cell_capture.chunks))
            self._cell_capture = None

        if (
            self._definition_capture is not None
            and tag == self._definition_capture.tag
            and self._definition_capture.depth == self.depth
        ):
            value = _normalize(self._definition_capture.chunks)
            if tag == "dt":
                self._pending_definition_term = (
                    self._definition_capture.element,
                    value,
                )
            elif self._pending_definition_term is not None:
                element, term = self._pending_definition_term
                if element is self._definition_capture.element:
                    element.definitions.append((term, value))
                self._pending_definition_term = None
            self._definition_capture = None

        if (
            self._job_capture is not None
            and tag == "tr"
            and self._job_capture.depth == self.depth
        ):
            values = self._job_capture.attributes
            cells = tuple(self._job_capture.cells)
            test_id = values["data-testid"]
            self.jobs.append(
                AccessibleJob(
                    job_id=int(test_id.removeprefix("job-")),
                    purpose=cells[1],
                    state=values["data-job-state"],
                    completed_units=int(values["data-progress-completed"]),
                    total_units=int(values["data-progress-total"]),
                    cells=cells,
                )
            )
            self._job_capture = None

        if (
            self._form_capture is not None
            and tag == "form"
            and self._form_capture.depth == self.depth
        ):
            form = self._form_capture
            self.forms.append(
                AccessibleForm(
                    test_id=form.test_id,
                    method=form.method,
                    target=form.target,
                    fields=tuple(form.fields),
                )
            )
            self._form_capture = None

        if self._element_captures:
            capture = self._element_captures[-1]
            if tag == capture.tag and capture.depth == self.depth:
                self.elements.append(
                    AccessibleElement(
                        test_id=capture.test_id,
                        tag=capture.tag,
                        attributes=capture.attributes,
                        text=_normalize(capture.chunks),
                        definitions=tuple(capture.definitions),
                    )
                )
                self._element_captures.pop()

        self.depth -= 1


def _normalize(chunks: list[str]) -> str:
    return " ".join("".join(chunks).split())


def parse_accessible_page(
    payload: bytes,
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
) -> AccessiblePage:
    parser = _AccessiblePageParser()
    parser.feed(payload.decode("utf-8"))
    parser.close()
    return AccessiblePage(
        status=status,
        content_type=content_type,
        payload=payload,
        elements=tuple(parser.elements),
        forms=tuple(parser.forms),
        jobs=tuple(parser.jobs),
    )


def read_bounded_readiness(
    stream: BinaryIO,
    *,
    timeout_seconds: float = _READINESS_TIMEOUT_SECONDS,
    maximum_bytes: int = _MAX_READINESS_BYTES,
) -> bytes:
    """Read exactly one LF-terminated readiness record without unbounded reads."""

    if timeout_seconds <= 0:
        raise ValueError("readiness timeout must be positive")
    if maximum_bytes <= 0:
        raise ValueError("readiness byte limit must be positive")
    deadline = time.monotonic() + timeout_seconds
    collected = bytearray()
    selector = selectors.DefaultSelector()
    try:
        selector.register(stream, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise RuntimeError("prototype readiness timed out")
            byte = os.read(stream.fileno(), 1)
            if not byte:
                if collected:
                    raise RuntimeError("prototype emitted an unterminated readiness record")
                raise RuntimeError("prototype stream ended before readiness")
            if byte == b"\n":
                return bytes(collected)
            collected.extend(byte)
            if len(collected) > maximum_bytes:
                raise RuntimeError("prototype exceeded the readiness byte limit")
    finally:
        selector.close()


def read_bounded_http_body(
    response: object,
    *,
    maximum_bytes: int = _MAX_HTTP_BODY_BYTES,
) -> bytes:
    """Read a response body only when its declared length is exact and bounded."""

    if maximum_bytes < 0:
        raise ValueError("HTTP body byte limit must not be negative")
    headers = getattr(response, "headers")
    raw_length = headers.get("Content-Length")
    if raw_length is None:
        raise RuntimeError("HTTP Content-Length is missing")
    try:
        content_length = int(raw_length)
    except (TypeError, ValueError):
        raise RuntimeError("HTTP Content-Length is invalid") from None
    if content_length < 0:
        raise RuntimeError("HTTP Content-Length is invalid")
    if content_length > maximum_bytes:
        raise RuntimeError("HTTP response exceeds the byte limit")
    read = getattr(response, "read")
    payload = read(content_length + 1)
    if len(payload) != content_length:
        raise RuntimeError("HTTP body length is not exact")
    return payload


class PrototypeServerProcess:
    """Start the documented prototype command and drive it over loopback HTTP."""

    def __init__(
        self,
        *,
        open_browser: bool = False,
        extra_environment: dict[str, str] | None = None,
    ) -> None:
        self._open_browser = open_browser
        self._extra_environment = {} if extra_environment is None else extra_environment
        self._temporary_directory: TemporaryDirectory[str] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self.url: str | None = None
        self.stderr = b""

    @property
    def command(self) -> tuple[str, ...]:
        arguments = ["python3.12", "-m", "internal_test_ui_prototype"]
        if not self._open_browser:
            arguments.append("--no-open")
        return tuple(arguments)

    def __enter__(self) -> PrototypeServerProcess:
        self.start()
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self.stop(check=exception_type is None)

    def start(self) -> str:
        if self._process is not None:
            raise RuntimeError("prototype process is already started")
        python = shutil.which("python3.12")
        if python is None:
            raise RuntimeError("python3.12 is required for prototype acceptance")
        self._temporary_directory = TemporaryDirectory(prefix="colorluthier-ui-e2e-")
        temporary_root = Path(self._temporary_directory.name)
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(temporary_root / "pycache"),
                "TMPDIR": str(temporary_root),
            }
        )
        environment.update(self._extra_environment)
        command = (python, "-m", "internal_test_ui_prototype")
        if not self._open_browser:
            command += ("--no-open",)
        self._process = subprocess.Popen(
            command,
            cwd=_REPOSITORY_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self._process.stdout is not None
        try:
            line = read_bounded_readiness(self._process.stdout)
        except Exception:
            self.stop(check=False)
            raise
        try:
            candidate = line.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError:
            self.stop(check=False)
            raise RuntimeError("prototype printed non-ASCII readiness URL") from None
        if not candidate.startswith("http://127.0.0.1:") or not candidate.endswith("/"):
            self.stop(check=False)
            raise RuntimeError(f"prototype printed invalid readiness URL {candidate!r}")
        self.url = candidate
        return candidate

    def get(self) -> AccessiblePage:
        if self.url is None:
            raise RuntimeError("prototype process is not started")
        with urlopen(self.url, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = read_bounded_http_body(response)
            return parse_accessible_page(
                payload,
                status=response.status,
                content_type=response.headers.get("Content-Type", ""),
            )

    def submit(
        self,
        form: AccessibleForm,
        overrides: dict[str, str] | None = None,
    ) -> AccessiblePage:
        if self.url is None:
            raise RuntimeError("prototype process is not started")
        if not isinstance(form, AccessibleForm):
            raise TypeError("submission requires an AccessibleForm")
        if form.method != "post" or form.target != "/action":
            raise AssertionError("form submission must be POST /action")
        submitted = form.submission(overrides)
        if not any(name == "action" and value for name, value in submitted):
            raise AssertionError("form submission requires an action field")
        request = Request(
            self.url + "action",
            data=urlencode(submitted).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = read_bounded_http_body(response)
            return parse_accessible_page(
                payload,
                status=response.status,
                content_type=response.headers.get("Content-Type", ""),
            )

    def stop(self, *, check: bool = True) -> int | None:
        process = self._process
        if process is None:
            return None
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            remaining_stdout, self.stderr = process.communicate(
                timeout=_SHUTDOWN_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            process.kill()
            remaining_stdout, self.stderr = process.communicate()
            return_code = process.returncode
            self._cleanup()
            if check:
                raise AssertionError("prototype did not stop after SIGINT")
            return return_code
        return_code = process.returncode
        self._cleanup()
        if check:
            if return_code != 0:
                raise AssertionError(
                    f"prototype exited {return_code}: {self.stderr.decode(errors='replace')}"
                )
            if remaining_stdout:
                raise AssertionError(
                    f"prototype printed unexpected stdout after readiness: {remaining_stdout!r}"
                )
            if self.stderr:
                raise AssertionError(
                    f"prototype printed unexpected stderr: {self.stderr!r}"
                )
        return return_code

    def _cleanup(self) -> None:
        self._process = None
        self.url = None
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None


class BrowserSurfaceUnavailable(RuntimeError):
    """The host cannot control the exact macOS browser surface for acceptance."""


class SafariSurfaceController:
    """Create, inventory, and close one isolated Safari document by exact URL."""

    _INVENTORY_SCRIPT = """
on run
    set separator to character id 30
    set previousDelimiters to AppleScript's text item delimiters
    set documentUrls to {}
    tell application "Safari"
        repeat with candidate in documents
            set candidateUrl to "<missing-url>"
            try
                set rawUrl to URL of candidate
                if rawUrl is not missing value then
                    set candidateUrl to rawUrl as text
                end if
            end try
            copy candidateUrl to end of documentUrls
        end repeat
    end tell
    set AppleScript's text item delimiters to separator
    set serializedUrls to documentUrls as text
    set AppleScript's text item delimiters to previousDelimiters
    return serializedUrls
end run
"""
    _CLOSE_SCRIPT = """
on run argv
    set targetUrl to item 1 of argv
    set closedCount to 0
    tell application "Safari"
        repeat with indexNumber from (count documents) to 1 by -1
            set candidate to document indexNumber
            try
                if (URL of candidate as text) is targetUrl then
                    close candidate
                    set closedCount to closedCount + 1
                    exit repeat
                end if
            end try
        end repeat
    end tell
    return closedCount as text
end run
"""
    _OPEN_NEW_DOCUMENT_SCRIPT = """
on run argv
    set targetUrl to item 1 of argv
    tell application "Safari"
        make new document with properties {URL:targetUrl}
    end tell
    return ""
end run
"""

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise BrowserSurfaceUnavailable("macOS is required for the real-surface smoke")
        if not Path("/Applications/Safari.app").exists():
            raise BrowserSurfaceUnavailable("Safari.app is unavailable")
        if not Path("/usr/bin/osascript").exists():
            raise BrowserSurfaceUnavailable("required macOS scripting tool is unavailable")
        self._temporary_directory: TemporaryDirectory[str] | None = None
        self._wrapper_path: Path | None = None

    def __enter__(self) -> SafariSurfaceController:
        self._temporary_directory = TemporaryDirectory(
            prefix="colorluthier-safari-surface-"
        )
        wrapper = Path(self._temporary_directory.name) / "open-new-safari-document"
        wrapper.write_text(
            f"""#!{sys.executable}
import subprocess
import sys

SCRIPT = {self._OPEN_NEW_DOCUMENT_SCRIPT!r}

if len(sys.argv) != 2:
    raise SystemExit(2)
try:
    completed = subprocess.run(
        ("/usr/bin/osascript", "-e", SCRIPT, sys.argv[1]),
        check=False,
        capture_output=True,
        timeout={_APPLE_EVENT_TIMEOUT_SECONDS!r},
    )
except subprocess.TimeoutExpired:
    raise SystemExit(3)
raise SystemExit(completed.returncode)
""",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        self._wrapper_path = wrapper
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self._wrapper_path = None
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None

    @property
    def wrapper_path(self) -> Path:
        if self._wrapper_path is None:
            raise RuntimeError("Safari surface controller is not active")
        return self._wrapper_path

    @property
    def browser_environment(self) -> dict[str, str]:
        return {"BROWSER": f"{shlex.quote(str(self.wrapper_path))} %s"}

    def inventory(self) -> tuple[str, ...]:
        serialized = self._run_script(self._INVENTORY_SCRIPT)
        if not serialized:
            return ()
        return tuple(sorted(serialized.split(chr(30))))

    def wait_for_added_document(
        self,
        before: tuple[str, ...],
        url: str,
    ) -> tuple[str, ...]:
        expected = tuple(sorted((*before, url)))
        last_inventory: tuple[str, ...] = ()
        for _ in range(_APPLE_EVENT_ATTEMPTS):
            try:
                last_inventory = self.inventory()
            except BrowserSurfaceUnavailable as error:
                raise BrowserSurfaceUnavailable(
                    f"Safari inventory failed; residual URL {url}"
                ) from error
            if last_inventory == expected:
                return last_inventory
        raise BrowserSurfaceUnavailable(
            "Safari did not add exactly one isolated document; "
            f"residual URL {url}; before={before!r}; current={last_inventory!r}"
        )

    def wait_for_inventory(
        self,
        expected: tuple[str, ...],
        *,
        residual_url: str,
    ) -> None:
        last_inventory: tuple[str, ...] = ()
        for _ in range(_APPLE_EVENT_ATTEMPTS):
            try:
                last_inventory = self.inventory()
            except BrowserSurfaceUnavailable as error:
                raise BrowserSurfaceUnavailable(
                    f"Safari inventory failed; residual URL {residual_url}"
                ) from error
            if last_inventory == expected:
                return
        raise BrowserSurfaceUnavailable(
            "Safari did not restore the original document multiset; "
            f"residual URL {residual_url}; "
            f"expected={expected!r}; current={last_inventory!r}"
        )

    def close_exact_url(self, url: str) -> int:
        return int(self._run_script(self._CLOSE_SCRIPT, url))

    @staticmethod
    def _run_script(script: str, *arguments: str) -> str:
        try:
            completed = subprocess.run(
                ("/usr/bin/osascript", "-e", script, *arguments),
                check=False,
                capture_output=True,
                text=True,
                timeout=_APPLE_EVENT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise BrowserSurfaceUnavailable("Safari Apple Event timed out") from error
        if completed.returncode != 0:
            diagnostic = completed.stderr.strip()[:400]
            raise BrowserSurfaceUnavailable(
                f"Safari Apple Event failed ({completed.returncode}): {diagnostic}"
            )
        return completed.stdout.strip()
