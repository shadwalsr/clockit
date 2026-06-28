"""
GhostTrack — Data Extraction Engine

Paginated fetch layer for Instagram follower/following data.
Implements safety controls: circuit breaker checks, smart delays,
and page-size capping to minimize detection risk.
"""

from abc import ABC, abstractmethod

from rich.console import Console

from src.throttle import smart_delay, check_circuit_breaker, CircuitBreakerTripped

console = Console()


class FetcherInterface(ABC):
    """Abstract base class for all fetch implementations.

    Any fetcher (requests-based, instaloader-based, or future alternatives)
    must implement these two methods to be swappable in the pipeline.
    """

    @abstractmethod
    def fetch_followers(self, user_id: str, username: str) -> list[str]:
        """Fetch all follower usernames for the given user.

        Args:
            user_id: Instagram numeric user ID.
            username: Instagram username (for logging/display).

        Returns:
            Sorted list of follower usernames.
        """
        ...

    @abstractmethod
    def fetch_following(self, user_id: str, username: str) -> list[str]:
        """Fetch all following usernames for the given user.

        Args:
            user_id: Instagram numeric user ID.
            username: Instagram username (for logging/display).

        Returns:
            Sorted list of following usernames.
        """
        ...


class RequestsFetcher(FetcherInterface):
    """Primary fetcher using requests.Session with cookie-based auth.

    Uses Instagram's private API endpoints with conservative pagination
    and built-in safety controls (circuit breaker, smart delays).
    """

    # Instagram's native page size — never request larger to avoid
    # triggering server-side anomaly detection.
    PAGE_SIZE = 50

    def __init__(self, session):
        """Initialize with an authenticated requests.Session.

        Args:
            session: A requests.Session pre-configured with Instagram
                     cookies and headers.
        """
        self.session = session
        self.request_count = 0

    def _paginated_fetch(self, url: str, label: str) -> list[str]:
        """Generic paginated fetch with safety controls.

        Iterates through paginated API responses, collecting usernames.
        Enforces circuit breaker checks and smart delays between pages.

        Args:
            url: Instagram API endpoint URL.
            label: Human-readable label for progress output (e.g. 'followers').

        Returns:
            Sorted list of collected usernames.

        Raises:
            CircuitBreakerTripped: If any response triggers the circuit breaker
                                   (rate-limit signals, challenge pages, etc.).
        """
        usernames = []
        max_id = None
        page = 0

        while True:
            page += 1
            params = {"count": self.PAGE_SIZE}
            if max_id is not None:
                params["max_id"] = max_id

            self.request_count += 1
            response = self.session.get(url, params=params, timeout=15)

            # Let CircuitBreakerTripped propagate — caller handles it
            check_circuit_breaker(response)

            data = response.json()
            users = data.get("users", [])

            for user in users:
                usernames.append(user["username"])

            console.print(
                f"Fetching {label} page {page} "
                f"({len(usernames)} users so far)..."
            )

            # Check for next page — stop if no next_max_id or big_list is False
            next_max_id = data.get("next_max_id")
            big_list = data.get("big_list", False)

            if not next_max_id or not big_list:
                break

            max_id = next_max_id
            smart_delay(self.request_count)

        return sorted(usernames)

    def fetch_followers(self, user_id: str, username: str) -> list[str]:
        """Fetch all followers for the given user.

        Args:
            user_id: Instagram numeric user ID.
            username: Instagram username (for logging context).

        Returns:
            Sorted list of follower usernames.
        """
        url = f"https://www.instagram.com/api/v1/friendships/{user_id}/followers/"
        console.print(f"\n[bold]Fetching followers for @{username}...[/bold]")
        return self._paginated_fetch(url, "followers")

    def fetch_following(self, user_id: str, username: str) -> list[str]:
        """Fetch all accounts the given user is following.

        Args:
            user_id: Instagram numeric user ID.
            username: Instagram username (for logging context).

        Returns:
            Sorted list of following usernames.
        """
        url = f"https://www.instagram.com/api/v1/friendships/{user_id}/following/"
        console.print(f"\n[bold]Fetching following for @{username}...[/bold]")
        return self._paginated_fetch(url, "following")


class InstaLoaderFetcher(FetcherInterface):
    """Placeholder for future instaloader-based fetch implementation.

    This stub exists to define the swap-in point. If the requests-based
    approach stops working (e.g. API changes), implement this class using
    instaloader's profile/follower iteration, or create a new
    FetcherInterface implementation.
    """

    def fetch_followers(self, user_id: str, username: str) -> list[str]:
        """Not yet implemented — use RequestsFetcher instead.

        Raises:
            NotImplementedError: Always. This is a placeholder.
        """
        raise NotImplementedError(
            "InstaLoaderFetcher is not yet implemented. "
            "Use RequestsFetcher for now. "
            "See README.md for instructions on implementing a custom fetcher."
        )

    def fetch_following(self, user_id: str, username: str) -> list[str]:
        """Not yet implemented — use RequestsFetcher instead.

        Raises:
            NotImplementedError: Always. This is a placeholder.
        """
        raise NotImplementedError(
            "InstaLoaderFetcher is not yet implemented. "
            "Use RequestsFetcher for now. "
            "See README.md for instructions on implementing a custom fetcher."
        )
