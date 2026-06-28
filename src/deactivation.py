"""
GhostTrack Deactivation Module
Optional deactivation verification — higher-risk feature.
Pings Instagram to check if suspicious accounts are truly deactivated.
"""

import random
import sys
import time
from typing import List, Tuple

from rich.console import Console

from src.throttle import CircuitBreakerTripped, check_circuit_breaker

console = Console()

MAX_CHECKS = 10


def verify_deactivations(suspicious_accounts: List[str], session) -> Tuple[List[str], List[str]]:
    """
    Verify whether suspicious accounts are truly deactivated or still active.

    This is a higher-risk feature that makes direct requests to Instagram's
    web profile API. A 5-minute cooldown is enforced before checks begin,
    and a circuit breaker is checked after each request.

    Args:
        suspicious_accounts: List of usernames to verify.
        session: An authenticated requests session (or similar) for making HTTP calls.

    Returns:
        A tuple of (confirmed_deactivations, still_active) username lists.
    """
    if not suspicious_accounts:
        return ([], [])

    # Cap to MAX_CHECKS with warning
    if len(suspicious_accounts) > MAX_CHECKS:
        console.print(
            f"[yellow]Warning:[/yellow] {len(suspicious_accounts)} suspicious accounts found, "
            f"but only the first {MAX_CHECKS} will be checked."
        )
        suspicious_accounts = suspicious_accounts[:MAX_CHECKS]

    # Risk warning
    console.print()
    console.print(
        "[bold yellow]⚠ WARNING:[/bold yellow] Deactivation verification makes direct requests "
        "to Instagram and increases detection risk. It is recommended to run this "
        "[bold]at most once per month[/bold]."
    )
    console.print()

    # 5-minute countdown (300 seconds)
    console.print("[bold]Starting 5-minute cooldown before verification...[/bold]")
    console.print("[dim]Press Ctrl+C to cancel.[/dim]")
    try:
        total_seconds = 300
        for remaining in range(total_seconds, 0, -1):
            minutes, seconds = divmod(remaining, 60)
            print(f"\r  Cooldown: {minutes:02d}:{seconds:02d} remaining", end="", flush=True)
            time.sleep(1)
        print("\r  Cooldown complete!              ")
    except KeyboardInterrupt:
        print("\r  Cooldown cancelled by user.     ")
        console.print("[yellow]Deactivation check cancelled.[/yellow]")
        return ([], [])

    console.print()
    console.print(f"[bold]Checking {len(suspicious_accounts)} account(s)...[/bold]")

    confirmed_deactivations = []
    still_active = []

    for i, username in enumerate(suspicious_accounts, start=1):
        console.print(f"  [{i}/{len(suspicious_accounts)}] Checking [cyan]{username}[/cyan]...", end=" ")

        try:
            url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            response = session.get(url, timeout=15)

            # Check circuit breaker
            try:
                check_circuit_breaker(response)
            except CircuitBreakerTripped:
                console.print("[bold red]Circuit breaker tripped! Halting checks.[/bold red]")
                return (confirmed_deactivations, still_active)

            data = response.json()
            user_data = data.get('data', {}).get('user')

            if user_data is None:
                confirmed_deactivations.append(username)
                console.print("[red]Deactivated/Deleted[/red]")
            else:
                still_active.append(username)
                console.print("[green]Still active (unfollowed you)[/green]")

        except Exception as e:
            console.print(f"[yellow]Error: {e}[/yellow]")

        # Delay between checks (except after the last one)
        if i < len(suspicious_accounts):
            delay = random.uniform(2, 4)
            time.sleep(delay)

    return (confirmed_deactivations, still_active)
