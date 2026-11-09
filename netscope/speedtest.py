# Copyright (c) 2026 miro (hoba101)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Latency and download speed tests (GTK-free; progress reported via callbacks)."""

from __future__ import annotations

import subprocess
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from . import __version__
from .netinfo import parse_default_route, run

DEFAULT_DOWNLOAD_BYTES = 25_000_000
DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes={size}"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
DEFAULT_UPLOAD_BYTES = 10_000_000
PUBLIC_TARGETS = (("cloudflare", "1.1.1.1"), ("google", "8.8.8.8"))


@dataclass
class PingResult:
    name: str
    host: str
    summary: str  # "min/avg/max/mdev = ..." text, or an error message
    ok: bool


@dataclass
class DownloadResult:
    total_bytes: int
    seconds: float

    @property
    def mbit_per_s(self) -> float:
        return self.total_bytes * 8 / (max(self.seconds, 0.001) * 1_000_000)

    @property
    def mbyte_per_s(self) -> float:
        return self.total_bytes / (max(self.seconds, 0.001) * 1_000_000)


def parse_ping_summary(output: str) -> str | None:
    """Extract the rtt summary (``min/avg/max/mdev``) from ping output."""
    for line in output.splitlines():
        if line.startswith(("rtt", "round-trip")) and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def parse_ping_avg(summary: str | None) -> float | None:
    """Average RTT in ms from a ``min/avg/max/mdev = a/b/c/d ms`` summary."""
    try:
        return float(summary.split("/")[1])  # type: ignore[union-attr]
    except (AttributeError, IndexError, ValueError):
        return None


def ping_targets() -> list[tuple[str, str]]:
    gateway, _ = parse_default_route(run(["ip", "-4", "route", "show", "default"], timeout=3))
    targets = list(PUBLIC_TARGETS)
    if gateway:
        targets.insert(0, ("gateway", gateway))
    return targets


def ping(name: str, host: str, count: int = 3) -> PingResult:
    try:
        proc = subprocess.run(
            ["ping", "-c", str(count), "-W", "1", host],
            capture_output=True,
            text=True,
            timeout=count * 2 + 2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return PingResult(name, host, str(exc), False)
    summary = parse_ping_summary(proc.stdout)
    if summary:
        return PingResult(name, host, summary, True)
    return PingResult(name, host, "no reply", False)


def run_latency(progress: Callable[[float], None] | None = None) -> list[PingResult]:
    targets = ping_targets()
    results = []
    for i, (name, host) in enumerate(targets, start=1):
        results.append(ping(name, host))
        if progress:
            progress(i / len(targets))
    return results


def run_download(
    size: int = DEFAULT_DOWNLOAD_BYTES,
    progress: Callable[[int, float], None] | None = None,
    chunk: int = 64 * 1024,
    timeout: float = 60,
) -> DownloadResult:
    """Download ``size`` bytes from the test endpoint and measure throughput.

    ``progress(bytes_so_far, mbit_per_s)`` is called after every chunk.
    """
    req = urllib.request.Request(
        DOWNLOAD_URL.format(size=size), headers={"User-Agent": f"NetScope/{__version__}"}
    )
    start = time.monotonic()
    total = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        while block := resp.read(chunk):
            total += len(block)
            if progress:
                progress(total, DownloadResult(total, time.monotonic() - start).mbit_per_s)
    return DownloadResult(total, time.monotonic() - start)


def run_upload(
    size: int = DEFAULT_UPLOAD_BYTES,
    progress: Callable[[int, float], None] | None = None,
    chunk: int = 64 * 1024,
    timeout: float = 60,
) -> DownloadResult:
    """Upload ``size`` bytes to the test endpoint and measure throughput."""
    start = time.monotonic()
    sent = 0

    def body():
        nonlocal sent
        block = b"0" * chunk
        while sent < size:
            piece = block[: min(chunk, size - sent)]
            sent += len(piece)
            if progress:
                progress(sent, DownloadResult(sent, time.monotonic() - start).mbit_per_s)
            yield piece

    req = urllib.request.Request(
        UPLOAD_URL,
        data=body(),
        method="POST",
        headers={
            "User-Agent": f"NetScope/{__version__}",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(size),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()
    return DownloadResult(sent, time.monotonic() - start)
