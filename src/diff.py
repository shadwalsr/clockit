"""
GhostTrack Diff Module
Diffing & Analysis Engine — pure set math, no network calls.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DiffResult:
    """Result of diffing two snapshots."""
    unfollowers: List[str] = field(default_factory=list)
    new_followers: List[str] = field(default_factory=list)
    not_following_back: List[str] = field(default_factory=list)
    suspicious_deactivations: List[str] = field(default_factory=list)
    is_first_run: bool = False
    is_stale: bool = False
    previous_timestamp: Optional[str] = None


def compute_diff(current_snapshot: dict, previous_snapshot: Optional[dict], is_stale: bool = False) -> DiffResult:
    """
    Compute the diff between two snapshots using pure set operations.

    Args:
        current_snapshot: The most recent snapshot dict with 'followers' and 'following' keys.
        previous_snapshot: The previous snapshot dict, or None for first-run.
        is_stale: Whether the previous snapshot is older than 30 days.

    Returns:
        A DiffResult with computed lists and metadata.

    Logic:
        - unfollowers = previous_followers - current_followers
        - new_followers = current_followers - previous_followers
        - not_following_back = current_following - current_followers
        - suspicious_deactivations = accounts in BOTH previous_followers AND previous_following,
          but absent from BOTH current_followers AND current_following
        - suspicious_deactivations are removed from unfollowers to avoid double-counting
        - All lists are sorted alphabetically
    """
    if previous_snapshot is None:
        return DiffResult(is_first_run=True)

    try:
        current_followers = set(current_snapshot['followers'])
        current_following = set(current_snapshot['following'])
        previous_followers = set(previous_snapshot['followers'])
        previous_following = set(previous_snapshot['following'])
    except (TypeError, AttributeError, KeyError):
        # Corrupted snapshot data — treat as first run
        return DiffResult(is_first_run=True)

    # Core set operations
    unfollowers = previous_followers - current_followers
    new_followers = current_followers - previous_followers
    not_following_back = current_following - current_followers

    # Suspicious deactivations: accounts that were in BOTH previous followers AND
    # previous following, but are now absent from BOTH current followers AND current following.
    previously_in_both = previous_followers & previous_following
    currently_in_neither = previously_in_both - (current_followers | current_following)
    suspicious_deactivations = currently_in_neither

    # Remove suspicious deactivations from unfollowers to avoid double-counting
    unfollowers = unfollowers - suspicious_deactivations

    # Extract previous timestamp
    previous_timestamp = previous_snapshot.get('timestamp')

    return DiffResult(
        unfollowers=sorted(unfollowers),
        new_followers=sorted(new_followers),
        not_following_back=sorted(not_following_back),
        suspicious_deactivations=sorted(suspicious_deactivations),
        is_first_run=False,
        is_stale=is_stale,
        previous_timestamp=previous_timestamp,
    )
