"""GhostTrack — Throttling & Circuit Breaker (core safety module)."""

import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console

console = Console()

LAST_RUN_FILE = Path("last_run.json")

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class CircuitBreakerTripped(Exception):
    """Raised when Instagram signals rate-limiting, challenges, or blocks."""


# ---------------------------------------------------------------------------
# Delay primitives
# ---------------------------------------------------------------------------


def inter_request_delay() -> float:
    """Return a random delay using a triangular distribution.

    Triangular(3.5, 8.2, 5.0) clusters around 5s with natural variance,
    unlike a flat uniform which produces obviously synthetic patterns.
    """
    return random.triangular(3.5, 8.2, 5.0)


def batch_break() -> float:
    """Pause for 30–45 seconds between request batches.

    Returns the actual delay used.
    """
    delay = random.uniform(30, 45)
    console.print(
        f"[yellow]⏸  Batch break — cooling off for {delay:.1f}s[/yellow]"
    )
    time.sleep(delay)
    return delay


def jitter_pause() -> bool:
    """1-in-15 chance of a long random pause (60–120 s).

    Returns True if a pause was triggered, False otherwise.
    """
    if random.randint(1, 15) == 1:
        delay = random.uniform(60, 120)
        console.print(
            f"[yellow]🎲 Jitter pause triggered — waiting {delay:.1f}s[/yellow]"
        )
        time.sleep(delay)
        return True
    return False


def smart_delay(request_count: int) -> None:
    """Orchestrate delays based on how many requests have been made.

    • Every 10 requests → batch_break()
    • Otherwise → check jitter, then normal inter_request_delay()
    • Always prints the chosen delay time.
    """
    if request_count > 0 and request_count % 10 == 0:
        batch_break()
        return

    if jitter_pause():
        return  # jitter_pause already slept & printed

    delay = inter_request_delay()
    console.print(f"[dim]⏳ Waiting {delay:.1f}s before next request…[/dim]")
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Circuit breaker — inspects every HTTP response
# ---------------------------------------------------------------------------


def check_circuit_breaker(response) -> None:
    """Inspect an HTTP response for signs of rate-limiting or blocking.

    Raises CircuitBreakerTripped on ANY of:
      • HTTP 429 (Too Many Requests)
      • HTTP 401 / 403 (authentication failure / forbidden)
      • HTML content-type when we expect JSON
      • Response body contains checkpoint_url, challenge, require_login, or spam
      • JSON body has status='fail'
    """
    # --- Status code checks ---
    if response.status_code == 429:
        raise CircuitBreakerTripped(
            f"HTTP 429 — Rate limited. Stop immediately. "
            f"(url={response.url})"
        )

    if response.status_code in (401, 403):
        raise CircuitBreakerTripped(
            f"HTTP {response.status_code} — Session invalid or blocked. "
            f"Cookie may be expired. (url={response.url})"
        )

    # --- Content-type check (HTML when expecting JSON) ---
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        raise CircuitBreakerTripped(
            "Received HTML instead of JSON — likely a login/challenge page. "
            f"(url={response.url})"
        )

    # --- Body keyword checks ---
    try:
        body_text = response.text
    except Exception:
        body_text = ""

    danger_keywords = ["checkpoint_url", "challenge", "require_login", "spam"]
    for keyword in danger_keywords:
        if keyword in body_text:
            raise CircuitBreakerTripped(
                f"Response body contains '{keyword}' — Instagram is flagging "
                f"this session. (url={response.url})"
            )

    # --- JSON status='fail' check ---
    try:
        data = response.json()
        if isinstance(data, dict) and data.get("status") == "fail":
            message = data.get("message", "no message")
            raise CircuitBreakerTripped(
                f"API returned status='fail': {message} (url={response.url})"
            )
    except (ValueError, TypeError):
        pass  # Not JSON — already handled by content-type check above


# ---------------------------------------------------------------------------
# Run cooldown — 48-hour minimum between runs
# ---------------------------------------------------------------------------


def _read_last_run() -> dict:
    """Read last_run.json, returning defaults if missing or corrupt."""
    try:
        return json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_run": None, "last_deactivation_check": None}


def _write_last_run(data: dict) -> None:
    """Persist run-tracking state to last_run.json."""
    LAST_RUN_FILE.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def check_cooldown(force: bool = False) -> None:
    """Refuse to run if fewer than 48 hours since the last run.

    If *force* is True, prints a warning but does NOT exit.
    Exits via sys.exit(1) when the cooldown is still active and force is False.
    """
    data = _read_last_run()
    last_run = data.get("last_run")

    if last_run is None:
        return  # First run ever — no cooldown needed

    last_run_dt = datetime.fromisoformat(last_run)
    elapsed = datetime.now(timezone.utc) - last_run_dt
    remaining = timedelta(hours=48) - elapsed

    if remaining.total_seconds() > 0:
        hours_left = remaining.total_seconds() / 3600
        if force:
            console.print(
                f"[bold yellow]⚠  Cooldown override — {hours_left:.1f}h remaining. "
                f"Proceeding at your own risk.[/bold yellow]"
            )
            return
        console.print(
            f"[bold red]✖ Cooldown active — {hours_left:.1f}h remaining "
            f"(48h minimum between runs).[/bold red]\n"
            f"  Last run: {last_run}\n"
            f"  Use --force to override (not recommended)."
        )
        sys.exit(1)


def check_deactivation_cooldown() -> bool:
    """Check 48-hour cooldown for the deactivation-check feature.

    Returns True if enough time has passed (OK to proceed).
    Returns False if cooldown is still active (does NOT sys.exit).
    """
    data = _read_last_run()
    last_check = data.get("last_deactivation_check")

    if last_check is None:
        return True  # Never checked before — OK to proceed

    last_check_dt = datetime.fromisoformat(last_check)
    elapsed = datetime.now(timezone.utc) - last_check_dt
    remaining = timedelta(hours=48) - elapsed

    if remaining.total_seconds() > 0:
        hours_left = remaining.total_seconds() / 3600
        console.print(
            f"[yellow]⏸  Deactivation-check cooldown active — "
            f"{hours_left:.1f}h remaining. Skipping.[/yellow]"
        )
        return False

    return True
