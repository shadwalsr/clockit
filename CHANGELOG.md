# Changelog

## [2.0.0] - 2026-06-29

### Added
- Initial release of GhostTrack
- Cookie-based authentication (no password automation)
- Throttled paginated fetch with human mimicry delays
- Circuit breaker — halts on any rate-limit or challenge signal
- 48-hour cooldown enforcement between runs
- Local JSON snapshot storage
- Set-based diff engine (unfollowers, new followers, not-following-back)
- Deactivation detection heuristic (suspicious mutual disappearances)
- Optional `--check-deactivation` for profile verification pings
- Color-coded CLI report via rich
- `--dry-run` and `--check-auth` modes
- File-based logging (never uploaded)
- Comprehensive safety documentation
