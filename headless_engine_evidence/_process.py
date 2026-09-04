# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bounded subprocess capture; raw child data never enters public diagnostics."""

from __future__ import annotations

import os
import queue
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import EvidenceError, require

STREAM_LIMIT = 1024 * 1024
FILE_LIMIT = 64 * 1024 * 1024
TREE_LIMIT = 128 * 1024 * 1024
TREE_ENTRIES = 4096
COMMAND_TIMEOUT = 120
SUITE_TIMEOUT = 600
CLEANUP_TIMEOUT = 10


class _WindowsJob:
    """Use native kill-on-close containment without an external executable."""

    def __init__(self, stage):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                        ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self.stage = stage
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ("SetInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.api, name)
            function.argtypes = arguments
            function.restype = result
        self.handle = self.api.CreateJobObjectW(None, None)
        require(bool(self.handle), stage, "COMMAND_FAILED")
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise EvidenceError("COMMAND_FAILED", stage)

    def assign(self, pid):
        handle = self.api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        require(bool(handle), self.stage, "COMMAND_FAILED")
        try:
            require(bool(self.api.AssignProcessToJobObject(self.handle, handle)), self.stage, "COMMAND_FAILED")
        finally:
            self.api.CloseHandle(handle)

    def close(self):
        if self.handle:
            closed = self.api.CloseHandle(self.handle)
            self.handle = None
            require(bool(closed), self.stage, "COMMAND_CLEANUP_FAILED")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def read_file(path: Path, stage: str, limit: int = FILE_LIMIT) -> bytes:
    """Reject nonregular files and bound both the observed size and actual read."""
    payload = None
    try:
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode) and metadata.st_size <= limit:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if stat.S_ISREG(opened.st_mode) and (opened.st_dev, opened.st_ino) == (metadata.st_dev, metadata.st_ino):
                    payload = stream.read(limit + 1)
    except OSError:
        pass
    require(payload is not None, stage, "FILE_INVALID")
    require(len(payload) <= limit, stage, "FILE_LIMIT")
    return payload


def check_tree(root: Path, stage: str, *, file_limit: int = FILE_LIMIT,
               tree_limit: int = TREE_LIMIT, entry_limit: int = TREE_ENTRIES) -> None:
    """Observe temporary file budgets without following links made by negative tests."""
    total = 0
    entries = 0
    pending = [root]
    try:
        while pending:
            with os.scandir(pending.pop()) as children:
                for child in children:
                    entries += 1
                    require(entries <= entry_limit, stage, "FILE_LIMIT")
                    try:
                        metadata = child.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue  # Public tests may delete their own temporary files.
                    if stat.S_ISDIR(metadata.st_mode):
                        pending.append(Path(child.path))
                    elif stat.S_ISREG(metadata.st_mode):
                        require(metadata.st_size <= file_limit, stage, "FILE_LIMIT")
                        total += metadata.st_size
                        require(total <= tree_limit, stage, "FILE_LIMIT")
    except FileNotFoundError:
        # A concurrently removed test directory will be absent at the next check.
        return
    except OSError:
        raise EvidenceError("FILE_INVALID", stage) from None


def command_environment(temporary_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "PYTHONPYCACHEPREFIX", "PYTHONINSPECT",
                 "COLORLUTHIER_RUN_REAL_SURFACE_SMOKE", "DISPLAY", "WAYLAND_DISPLAY", "BROWSER"):
        env.pop(name, None)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
                "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                "TMPDIR": str(temporary_root), "TMP": str(temporary_root), "TEMP": str(temporary_root)})
    return env


def run_command(arguments: list[str], *, cwd: Path, env: dict[str, str], stage: str,
                temporary_root: Path, timeout: float = COMMAND_TIMEOUT,
                stream_limit: int = STREAM_LIMIT) -> CommandResult:
    """Drain both pipes concurrently; deadlines and caps apply even to silent children.

    The queue wait supplies event-driven completion and a finite resource-budget
    observation interval. There are no readiness sleeps. Size monitoring is not
    an OS quota: a failing child can exceed a disk budget between observations.
    Every artifact is bounded again before it can enter a successful record.
    """
    require(timeout > 0 and stream_limit > 0, stage)
    # Commands use the selected absolute interpreter; no PATH search or shell.
    require(bool(arguments) and Path(arguments[0]).is_file(), stage, "COMMAND_FAILED")
    check_tree(temporary_root, stage)
    child = None
    job = _WindowsJob(stage) if os.name == "nt" else None
    launch_error = False
    try:
        launch = ([sys.executable, "-B", "-m", "headless_engine_evidence._windows_launch", *arguments]
                  if job is not None else arguments)
        child = subprocess.Popen(launch, cwd=cwd, env=env,
                                 stdin=subprocess.PIPE if job is not None else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=(os.name == "posix"))
        if job is not None:
            job.assign(child.pid)
            child.stdin.write(b"\x00")
            child.stdin.close()
    except (OSError, EvidenceError):
        launch_error = True
    if launch_error:
        if job is not None:
            job.close()
        if child is not None:
            try:
                child.kill()
            except OSError:
                pass
            try:
                child.wait(timeout=CLEANUP_TIMEOUT)
            except subprocess.TimeoutExpired:
                raise EvidenceError("COMMAND_CLEANUP_FAILED", stage) from None
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    stream.close()
        raise EvidenceError("COMMAND_FAILED", stage)
    require(child is not None, stage, "COMMAND_FAILED")
    events = queue.Queue(maxsize=4)
    captured = [bytearray(), bytearray()]

    def drain(index, stream):
        try:
            while chunk := stream.read1(min(65536, stream_limit + 1)):
                if len(captured[index]) + len(chunk) > stream_limit:
                    events.put((index, "COMMAND_OUTPUT_LIMIT"))
                    return
                captured[index].extend(chunk)
            events.put((index, None))
        except OSError:
            events.put((index, "COMMAND_FAILED"))

    readers = [threading.Thread(target=drain, args=(index, stream), daemon=True)
               for index, stream in enumerate((child.stdout, child.stderr))]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    finished = 0
    failure = None
    try:
        while finished < 2:
            remaining = deadline - time.monotonic()
            require(remaining > 0, stage, "COMMAND_TIMEOUT")
            try:
                _, error = events.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                check_tree(temporary_root, stage)
                continue
            if error:
                raise EvidenceError(error, stage)
            finished += 1
        child.wait(timeout=max(0.001, deadline - time.monotonic()))
        check_tree(temporary_root, stage)
    except subprocess.TimeoutExpired:
        failure = EvidenceError("COMMAND_TIMEOUT", stage)
    except EvidenceError as error:
        failure = error
    finally:
        if job is not None:
            try:
                job.close()  # Also kills grandchildren before joining the pipe readers.
            except EvidenceError as error:
                failure = error
        if child.poll() is None or failure is not None:
            try:
                if os.name == "posix":
                    os.killpg(child.pid, signal.SIGKILL)
                else:
                    child.kill()
            except (ProcessLookupError, OSError):
                pass
            try:
                child.wait(timeout=CLEANUP_TIMEOUT)
            except subprocess.TimeoutExpired:
                failure = EvidenceError("COMMAND_CLEANUP_FAILED", stage)
        for reader in readers:
            reader.join(timeout=CLEANUP_TIMEOUT)
        if any(reader.is_alive() for reader in readers):
            failure = EvidenceError("COMMAND_CLEANUP_FAILED", stage)
        else:
            child.stdout.close()
            child.stderr.close()
    if failure is not None:
        raise failure from None
    return CommandResult(child.returncode, bytes(captured[0]), bytes(captured[1]))
