"""
GhostTrack v2.0 — Main CLI Entry Point

Orchestrates the full tracking pipeline:
  1. Authenticate via saved session cookie
  2. Enforce cooldown safety windows
  3. Fetch followers/following with throttled pagination
  4. Snapshot current state to local JSON
  5. Diff against previous snapshot
  6. Print color-coded change report

Usage:
  python tracker.py --check-auth
  python tracker.py --dry-run
  python tracker.py --run [--force]
  python tracker.py --check-deactivation
"""

import argparse
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src import auth, storage, diff, deactivation
from src.fetch import RequestsFetcher
from src.throttle import check_cooldown, check_deactivation_cooldown, CircuitBreakerTripped

console = Console()

BANNER = r"""
   _____ _               _  _____               _
  / ____| |             | ||_   _|             | |
 | |  __| |__   ___  ___| |_ | |_ __ __ _  ___| | __
 | | |_ | '_ \ / _ \/ __| __|| | '__/ _` |/ __| |/ /
 | |__| | | | | (_) \__ \ |_ | | | | (_| | (__|   <
  \_____|_| |_|\___/|___/\__||_|_|  \__,_|\___|_|\_\
   _____|_| |_|\___/|___/\__||_|_|  \__,_|\___|_|\_\
"""


def save_report_to_file(diff_result, current_snapshot):
    """Save a markdown version of the report to the reports/ directory."""
    from pathlib import Path
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = reports_dir / f"report_{timestamp}.md"
    
    lines = []
    lines.append(f"# GhostTrack Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if diff_result is None:
        lines.append("First snapshot saved. Run again later to see changes.\n")
    else:
        if diff_result.stale:
            lines.append("**Warning:** Previous snapshot is over 30 days old. Diff may have lower confidence.\n")
            
        lines.append("## Summary\n")
        lines.append(f"- **Unfollowers:** {len(diff_result.unfollowers)}")
        lines.append(f"- **New Followers:** {len(diff_result.new_followers)}")
        lines.append(f"- **Not Following Back:** {len(diff_result.not_following_back)}")
        lines.append(f"- **Suspicious Deactivations:** {len(diff_result.suspicious_deactivations)}\n")
        
        lines.append("## 🔴 Unfollowers")
        if diff_result.unfollowers:
            for u in sorted(diff_result.unfollowers):
                lines.append(f"- {u}")
        else:
            lines.append("None")
            
        lines.append("\n## 🟢 New Followers")
        if diff_result.new_followers:
            for u in sorted(diff_result.new_followers):
                lines.append(f"- {u}")
        else:
            lines.append("None")
            
        lines.append("\n## 🟡 Not Following Back")
        if diff_result.not_following_back:
            for u in sorted(diff_result.not_following_back):
                lines.append(f"- {u}")
        else:
            lines.append("None")
            
        lines.append("\n## 🔵 Suspicious Deactivations")
        if diff_result.suspicious_deactivations:
            lines.append("_These accounts disappeared from both your followers AND following. They may have deactivated._\n")
            for u in sorted(diff_result.suspicious_deactivations):
                lines.append(f"- {u}")
        else:
            lines.append("None")
            
    lines.append("\n## Totals")
    lines.append(f"- **Total Current Followers:** {len(current_snapshot['followers'])}")
    lines.append(f"- **Total Current Following:** {len(current_snapshot['following'])}")
    
    filepath.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]✓ Report saved to {filepath}[/green]")


def print_report(diff_result, current_snapshot):
    """Print a color-coded change report to the console.

    Args:
        diff_result: DiffResult from diff.compute_diff(). If None,
                     this is the first run (no previous snapshot).
        current_snapshot: The current snapshot dict (for context).
    """
    if diff_result is None:
        console.print(
            "\n[bold cyan]ℹ First snapshot saved. "
            "Run again later to see changes.[/bold cyan]\n"
        )
        return

    # Stale data warning
    if diff_result.stale:
        console.print(
            "\n[bold yellow]⚠ Warning: More than 30 days between snapshots. "
            "Changes may be incomplete or inaccurate.[/bold yellow]\n"
        )

    # Summary table
    summary = Table(title="📊 Change Summary", show_header=True, header_style="bold")
    summary.add_column("Category", style="bold")
    summary.add_column("Count", justify="right")

    summary.add_row("🔴 Unfollowers", str(len(diff_result.unfollowers)))
    summary.add_row("🟢 New Followers", str(len(diff_result.new_followers)))
    summary.add_row("🟡 Not Following Back", str(len(diff_result.not_following_back)))
    summary.add_row(
        "🔵 Suspicious Deactivations",
        str(len(diff_result.suspicious_deactivations)),
    )

    console.print()
    console.print(summary)

    # Detailed sections
    _print_section(
        "🔴 Unfollowers",
        diff_result.unfollowers,
        "bold red",
        "red",
    )
    _print_section(
        "🟢 New Followers",
        diff_result.new_followers,
        "bold green",
        "green",
    )
    _print_section(
        "🟡 Not Following Back",
        diff_result.not_following_back,
        "bold yellow",
        "yellow",
    )

    # Suspicious deactivations — with extra context note
    console.print(f"\n[bold blue]🔵 Suspicious Deactivations[/bold blue]")
    if diff_result.suspicious_deactivations:
        for username in sorted(diff_result.suspicious_deactivations):
            console.print(f"  [blue]• {username}[/blue]")
        console.print(
            "\n[dim]These accounts disappeared from both your followers AND "
            "following. They may have deactivated. Visit "
            "instagram.com/{username} to verify.[/dim]"
        )
    else:
        console.print("  [dim]None[/]")

    # Total counts panel
    total = (
        len(diff_result.unfollowers)
        + len(diff_result.new_followers)
        + len(diff_result.not_following_back)
        + len(diff_result.suspicious_deactivations)
    )
    console.print(
        Panel(
            f"[bold]Total changes detected: {total}[/bold]",
            title="Summary",
            border_style="cyan",
        )
    )


def _print_section(title, items, title_style, item_style):
    """Print a single report section with a list of usernames.

    Args:
        title: Section heading text.
        items: Collection of usernames to list.
        title_style: Rich style string for the heading.
        item_style: Rich style string for each username.
    """
    console.print(f"\n[{title_style}]{title}[/{title_style}]")
    if items:
        for username in sorted(items):
            console.print(f"  [{item_style}]• {username}[/{item_style}]")
    else:
        console.print("  [dim]None[/]")


def main():
    """Main entry point — parse args and dispatch to the appropriate flow."""

    parser = argparse.ArgumentParser(
        description="GhostTrack v2.0 — Instagram Follower/Following Change Tracker",
    )

    # Mutually exclusive action group
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--run",
        action="store_true",
        help="Full pipeline: fetch, snapshot, diff, report",
    )
    action_group.add_argument(
        "--check-auth",
        action="store_true",
        help="Validate session cookie only",
    )
    action_group.add_argument(
        "--check-deactivation",
        action="store_true",
        help="Verify suspicious deactivations from last diff",
    )
    action_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate auth + cooldown without making bulk requests",
    )

    # Additional flags
    parser.add_argument(
        "--force",
        action="store_true",
        help="Override 48-hour cooldown (use with caution)",
    )

    args = parser.parse_args()

    # Banner
    console.print(Panel(BANNER, title="[bold cyan]GhostTrack v2.0[/bold cyan]", border_style="cyan"))

    # ── --check-auth ────────────────────────────────────────────────
    if args.check_auth:
        _check_auth_flow()
        return

    # ── --dry-run ───────────────────────────────────────────────────
    if args.dry_run:
        _dry_run_flow(args.force)
        return

    # ── --check-deactivation ────────────────────────────────────────
    if args.check_deactivation:
        _check_deactivation_flow()
        return

    # ── --run (full pipeline) ───────────────────────────────────────
    if args.run:
        _run_flow(args.force)
        return


def _check_auth_flow():
    """Validate session cookie and print result."""
    console.print("\n[bold]Validating session...[/bold]")

    credentials = auth.load_credentials()
    session = auth.get_session(credentials)
    user_id = auth.validate_session(session)

    if user_id:
        console.print(f"[bold green]✓ Session valid — user_id: {user_id}[/bold green]")
    else:
        console.print("[bold red]✗ Session invalid or expired.[/bold red]")
        sys.exit(1)


def _dry_run_flow(force: bool):
    """Validate auth and cooldown without making bulk requests.

    Args:
        force: If True, override cooldown check.
    """
    console.print("\n[bold]Dry run — validating auth + cooldown...[/bold]")

    credentials = auth.load_credentials()
    session = auth.get_session(credentials)
    user_id = auth.validate_session(session)

    if not user_id:
        console.print("[bold red]✗ Session invalid or expired.[/bold red]")
        sys.exit(1)

    check_cooldown(force=force)

    console.print(
        "[bold green]✓ Dry run complete — auth valid, cooldown clear.[/bold green]"
    )


def _check_deactivation_flow():
    """Verify suspicious deactivations from the last diff."""
    console.print("\n[bold]Checking deactivations...[/bold]")

    credentials = auth.load_credentials()
    session = auth.get_session(credentials)
    user_id = auth.validate_session(session)

    if not user_id:
        console.print("[bold red]✗ Session invalid or expired.[/bold red]")
        sys.exit(1)

    # Check deactivation cooldown
    if not check_deactivation_cooldown():
        console.print(
            "[bold yellow]⚠ Deactivation check cooldown is still active. "
            "Please wait before checking again.[/bold yellow]"
        )
        sys.exit(1)

    # Load snapshots and compute diff
    latest_snapshot = storage.load_latest_snapshot()
    previous_snapshot = storage.load_previous_snapshot()

    if not latest_snapshot or not previous_snapshot:
        console.print("[yellow]Not enough snapshots to check deactivations.[/yellow]")
        sys.exit(0)

    diff_result = diff.compute_diff(latest_snapshot, previous_snapshot)
    suspicious = diff_result.suspicious_deactivations

    if not suspicious:
        console.print("[green]No suspicious deactivations to verify.[/green]")
        sys.exit(0)

    console.print(
        f"[bold]Verifying {len(suspicious)} suspicious account(s)...[/bold]"
    )

    results = deactivation.verify_deactivations(suspicious, session)
    storage.update_deactivation_check_timestamp()

    # Print results
    console.print("\n[bold]Deactivation Verification Results:[/bold]")

    confirmed = [u for u, status in results.items() if status == "deactivated"]
    still_active = [u for u, status in results.items() if status == "active"]

    if confirmed:
        console.print("\n[dim]Confirmed deactivations:[/dim]")
        for username in sorted(confirmed):
            console.print(f"  [dim]☐ {username} — deactivated/deleted[/dim]")

    if still_active:
        console.print("\n[bold]Still active (unfollowed you):[/bold]")
        for username in sorted(still_active):
            console.print(f"  [bold]• {username} — still active[/bold]")


def _run_flow(force: bool):
    """Full pipeline: fetch, snapshot, diff, report.

    Args:
        force: If True, override 48-hour cooldown.
    """
    # Step 1: Load credentials
    console.print("\n[bold]Loading credentials...[/bold]")
    credentials = auth.load_credentials()

    # Step 2: Create session
    session = auth.get_session(credentials)

    # Step 3: Validate session
    console.print("[bold]Validating session...[/bold]")
    user_id = auth.validate_session(session)
    if not user_id:
        console.print("[bold red]✗ Session invalid or expired.[/bold red]")
        sys.exit(1)
    console.print(f"[green]✓ Session valid — user_id: {user_id}[/green]")

    # Step 4: Check cooldown
    check_cooldown(force=force)
    console.print("[green]✓ Cooldown check passed.[/green]")

    # Step 5: Setup logger
    logger = storage.setup_logger()

    # Step 6: Record start time
    start_time = time.time()

    followers = None
    following = None
    username = credentials.get("username", "unknown")

    try:
        # Step 7-8: Fetch followers
        console.print("\n[bold cyan]Fetching followers...[/bold cyan]")
        fetcher = RequestsFetcher(session)
        followers = fetcher.fetch_followers(user_id, username)
        console.print(f"[green]✓ Fetched {len(followers)} followers.[/green]")

        # Step 9-10: Fetch following
        console.print("\n[bold cyan]Fetching following...[/bold cyan]")
        following = fetcher.fetch_following(user_id, username)
        console.print(f"[green]✓ Fetched {len(following)} following.[/green]")

    except CircuitBreakerTripped as e:
        console.print(
            f"\n[bold red]🚨 CIRCUIT BREAKER TRIPPED: {e}[/bold red]\n"
            "[bold red]Halting all requests immediately. "
            "Do NOT retry for at least 24 hours.[/bold red]"
        )
        # Save partial data if available
        if followers is not None or following is not None:
            console.print("[yellow]Saving partial data...[/yellow]")
            storage.save_snapshot(
                followers=followers or [],
                following=following or [],
                partial=True,
            )
        logger.error(f"Circuit breaker tripped: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        console.print(
            "\n[bold yellow]⚠ Interrupted by user. "
            "Saving partial data...[/bold yellow]"
        )
        if followers is not None or following is not None:
            storage.save_snapshot(
                followers=followers or [],
                following=following or [],
                partial=True,
            )
        sys.exit(0)

    # Step 11: Calculate duration
    fetch_duration = time.time() - start_time
    console.print(f"\n[dim]Fetch completed in {fetch_duration:.1f}s[/dim]")

    # Step 12: Save snapshot
    storage.save_snapshot(followers=followers, following=following)
    console.print("[green]✓ Snapshot saved.[/green]")

    # Step 13: Update last run timestamp
    storage.update_last_run()

    # Step 14: Load previous snapshot
    previous_snapshot = storage.load_previous_snapshot()

    # Step 15: Compute diff
    current_snapshot = {"followers": followers, "following": following}
    diff_result = diff.compute_diff(current_snapshot, previous_snapshot)

    # Step 16: Print and save report
    print_report(diff_result, current_snapshot)
    save_report_to_file(diff_result, current_snapshot)


def main_wrapper():
    """Top-level wrapper with global error handling."""
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — exiting gracefully.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error: {e}[/bold red]")
        # Log if logger is available
        try:
            logger = storage.setup_logger()
            logger.error(f"Fatal error: {e}", exc_info=True)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main_wrapper()
