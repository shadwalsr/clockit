"""GhostTrack — Authentication & session management."""

import sys

import requests
from dotenv import load_dotenv
from rich.console import Console

import os

console = Console()

# Realistic browser headers — Chrome 124 on Windows 10.
# Constructed once and reused for the entire session run; never rotated mid-session.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


def load_credentials() -> tuple[str, str]:
    """Load SESSIONID and INSTAGRAM_USERNAME from .env.

    Exits with a clear message if either value is missing or still set
    to the placeholder default.
    """
    load_dotenv()

    session_id = os.getenv("SESSIONID", "").strip()
    username = os.getenv("INSTAGRAM_USERNAME", "").strip()

    if not session_id or session_id == "your_session_id_here":
        console.print(
            "[bold red]✖ SESSIONID not found in .env[/bold red]\n"
            "  Copy .env.example → .env and paste your Instagram sessionid cookie.\n"
            "  (DevTools → Application → Cookies → instagram.com → sessionid)"
        )
        sys.exit(1)

    if not username or username == "your_username_here":
        console.print(
            "[bold red]✖ INSTAGRAM_USERNAME not found in .env[/bold red]\n"
            "  Add your Instagram username to .env so we can validate the session."
        )
        sys.exit(1)

    console.print(f"[green]✔ Credentials loaded for[/green] [bold]@{username}[/bold]")
    return session_id, username


def get_session(session_id: str) -> requests.Session:
    """Create a requests.Session with the sessionid cookie and realistic headers.

    The cookie is set on the .instagram.com domain so it is sent with every
    request to Instagram's API endpoints.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.set("sessionid", session_id, domain=".instagram.com")
    return session


def validate_session(session: requests.Session, username: str) -> str:
    """Validate the session cookie with a single lightweight profile fetch.

    Hits the web_profile_info endpoint for the authenticated user.
    Returns the user_id string on success.
    On 401/403 (expired or invalid cookie) prints a clear message and exits.
    NO retries — if it fails, the cookie needs to be refreshed by the user.
    """
    url = (
        f"https://www.instagram.com/api/v1/users/web_profile_info/"
        f"?username={username}"
    )

    console.print(f"[dim]Validating session for @{username}…[/dim]")

    try:
        resp = session.get(url, timeout=15)
    except requests.RequestException as exc:
        console.print(f"[bold red]✖ Network error during validation:[/bold red] {exc}")
        sys.exit(1)

    if resp.status_code in (401, 403):
        console.print(
            "[bold red]✖ Cookie expired or invalid — re-extract from browser.[/bold red]\n"
            "  DevTools → Application → Cookies → instagram.com → sessionid\n"
            "  Paste the new value into your .env file."
        )
        sys.exit(1)

    if resp.status_code != 200:
        console.print(
            f"[bold red]✖ Unexpected status {resp.status_code} during validation.[/bold red]"
        )
        sys.exit(1)

    try:
        data = resp.json()
        user_id = data["data"]["user"]["id"]
    except (ValueError, KeyError, TypeError) as exc:
        console.print(
            f"[bold red]✖ Failed to parse validation response:[/bold red] {exc}"
        )
        sys.exit(1)

    console.print(
        f"[green]✔ Session valid[/green] — user_id [bold]{user_id}[/bold]"
    )
    return user_id
