# Product Requirements Document (PRD)
## Product Name: IG Local Tracker (GhostTrack)
**Document Version:** 2.0
**Date:** June 29, 2026
**Author:** Shadwal
**Status:** Draft — Pre-Build

---

## 1. Executive Summary

**Objective:** Build a lightweight, 100% locally-executed Python application that tracks Instagram follower/following changes (unfollowers, new followers, non-mutual follows) for a single personal account, without ever risking that account's standing.

**Philosophy:** Safety > Speed > Features. Every design decision in this document is filtered through one question: *"Does this make the account look more or less like a bot?"* If a feature increases detection risk without a corresponding safety control, it is deferred to a later version or cut entirely.

**Non-Goals:** This is not a growth tool, not a mass-scraping tool, and not a SaaS product. It is a personal utility for one account, run occasionally, by hand.

---

## 2. Scope & Target Audience

| Item | Detail |
|---|---|
| **Target User** | The developer (personal use only) |
| **Target Account Size** | < 1,000 followers / following combined |
| **Run Frequency** | Manual, recommended max 2–4x per month |
| **Out of Scope** | Multi-account management, cloud deployment, cron/background jobs, story-viewer tracking, like/comment automation, DM access, UI/web frontend (CLI only for MVP) |
| **Explicitly Forbidden** | Using this tool on accounts you don't own, sharing session cookies, running on someone else's behalf, any auto-follow/unfollow action |

---

## 3. Core Architecture

**Pattern: Snapshot & Diff** — never real-time, never continuous.

```
[Browser Cookie] → [Auth Injection] → [Throttled Paginated Fetch]
       → [Local JSON Snapshot] → [Set-Based Diff vs Previous Snapshot]
       → [CLI Report]
```

This architecture is intentionally "slow and dumb" — it has no persistent connection, no polling, no daemon. Every run is a single, bounded, human-initiated event that starts and stops completely.

---

## 4. Functional Requirements

### 4.1 Authentication Module
- **Requirement:** No username/password automation, ever. Password-based programmatic login is the #1 trigger for Instagram's automated-login defenses (it pattern-matches against credential-stuffing behavior).
- **Implementation:**
  - User manually logs into Instagram via their normal browser (already-trusted device/session).
  - User manually extracts the `sessionid` cookie via browser DevTools and stores it in a local `.env` file (never committed to git — enforce via `.gitignore`).
  - Script injects `sessionid`, along with realistic `User-Agent`, `X-IG-App-ID`, and other headers matching a real browser/app session, into requests.
  - **Safety addition:** Validate session liveness with a single lightweight request *before* starting any bulk fetch. If invalid, fail immediately with a clear "re-extract your cookie" message rather than retrying repeatedly (repeated failed auth attempts are themselves a detection signal).

### 4.2 Data Extraction Engine
- **Requirement:** Fetch complete follower/following lists without behaving like a scraper.
- **Implementation:**
  - Primary approach: wrap **`instaloader`**, a maintained library that already absorbs most GraphQL endpoint churn, rather than hand-rolling raw GraphQL calls.
  - Fallback: modular raw-request layer, isolated behind an interface, so if `instaloader` breaks or lags behind an Instagram change, the underlying fetch method can be swapped without touching the diffing/storage/CLI layers.
  - **Pagination:** Respect Instagram's native page size (~50 users/page); never request a custom larger page size even if technically possible — non-standard request shapes are a fingerprinting vector.

### 4.3 Throttling & Human Mimicry (Critical — Core Safety Layer)

This is the most important section of the document. Treat every sub-point as a hard requirement, not a suggestion.

| Control | Implementation |
|---|---|
| **Inter-request delay** | `random.uniform(3.5, 8.2)` seconds between paginated requests, using a non-uniform (e.g. triangular or log-normal) distribution rather than flat uniform where possible — flat uniform randomness is itself a detectable pattern over many samples. |
| **Batch "breaks"** | 30–45 second pause after every 10 sequential page requests, simulating a human getting distracted/scrolling away. |
| **Session-level cap** | Hard limit of one full followers+following fetch per run. No retry loops that silently re-fetch the same data. |
| **Jitter on jitter** | Occasionally (≈1 in 15 requests) insert a longer "distracted human" pause of 60–120 seconds — real humans don't have perfectly bounded delay ranges. |
| **Request fingerprint consistency** | Reuse the same `User-Agent` / header set for the entire run; never rotate user-agents mid-session (rotating mid-session looks more suspicious than using one consistent identity). |
| **No parallelism** | Strictly sequential requests. Concurrent/multi-threaded fetching is a top-tier bot signal and is explicitly forbidden in this architecture. |
| **Time-of-day awareness (V1.1)** | Optionally restrict runs to hours when the account is normally active, avoiding 3 AM scrape patterns. |
| **Circuit breaker** | If any response includes a rate-limit signal, CAPTCHA/challenge page, or unexpected HTML (vs JSON), the script must **halt immediately**, save partial progress, and exit — never retry through a soft block. Retrying through a challenge is the single most common cause of escalation to a full account lock. |
| **Cool-down enforcement** | Script tracks the timestamp of the last successful run (local file) and **refuses to run again** if invoked within a configurable minimum window (default: 48 hours), overridable only with an explicit `--force` flag plus a printed warning. |

### 4.4 Local Storage System
- **Requirement:** All data stays on-device. No cloud sync, no telemetry, no analytics SDKs.
- **Implementation:**
  - Snapshots saved to `/snapshots/snapshot_YYYYMMDD_HHMM.json`.
  - Structure:
    ```json
    {
      "timestamp": "2026-06-29T10:30:00",
      "account": "your_username",
      "followers": ["userA", "userB", "userC"],
      "following": ["userB", "userC", "userD"],
      "fetch_duration_seconds": 412,
      "tool_version": "2.0"
    }
    ```
  - `.env` and `/snapshots` both excluded from version control by default `.gitignore`.
  - **Safety addition:** Snapshot files contain no PII beyond usernames (no profile pics, bios, or emails fetched) — minimize data collected to exactly what the diff engine needs.

### 4.5 Diffing & Analysis Engine
- **Requirement:** Calculate unfollowers, new followers, and non-mutual follows.
- **Implementation (set mathematics):**
  - `Unfollowers = Previous Followers − Current Followers`
  - `New Followers = Current Followers − Previous Followers`
  - `Not Following Back = Current Following − Current Followers`
  - Handle first-run gracefully (no previous snapshot → skip diff, just confirm save).
  - Handle corrupted/incomplete previous snapshot gracefully (warn, don't crash).

### 4.6 Deactivation Detection (Optional, Low-Risk)

**Requirement:** Distinguish between "unfollowed" and "account deactivated/deleted" by detecting mutual simultaneous disappearances.

**Heuristic:** If an account appears in both `previous_followers` AND `previous_following`, but is absent from *both* `current_followers` AND `current_following`, flag it as a "suspicious_deactivation" (the account likely deactivated or was deleted, rather than a standard unfollow).

**Implementation:**

- **Default behavior (no extra API calls):** Report accounts flagged as "suspicious_deactivations" with a note: *"This account disappeared from both your followers and following lists. It may have been deactivated/deleted, or you and they unfollowed each other simultaneously. Visit instagram.com/username to confirm."*
- **Optional enhancement:** `--check-deactivation` flag allows users to opt-in to automated verification pings on flagged accounts (higher risk, explicit warning printed).

**If `--check-deactivation` flag is used:**
- Insert a 5-minute buffer after the main follower/following fetch completes (breaks the timing linkage with the primary fetch).
- Ping each flagged account's profile individually.
- Throttle these profile checks with `random.uniform(2, 4)` second delays between them.
- Print a visible warning: *"[WARNING] --check-deactivation creates additional API calls. Use sparingly (max once per month). This increases detection risk. Use at your own risk."*
- If any profile check triggers a rate-limit or challenge, halt immediately (circuit breaker applies here too).
- Report confirmed deactivations separately in the output: `confirmed_deactivations: [username1, username2]`.

**Safety guardrails:**
- Deactivation checks are disabled by default.
- Only run if explicitly enabled by user with the flag.
- Cap checks to maximum 10 accounts per run (rare to have more mutual simultaneous unfollows anyway).
- If deactivation checks are enabled, add an extra 48-hour cool-down window beyond the primary tracker cool-down (prevents the deactivation feature from being run frequently).

### 4.7 User Interface / Output
- CLI output, color-coded:
  - 🔴 Red = unfollowers
  - 🟢 Green = new followers
  - 🟡 Yellow = not-following-back
  - 🔵 Blue = suspicious_deactivations (default report, no pinging)
  - ⚫ Black = confirmed_deactivations (only if `--check-deactivation` was used)
- Print live progress during fetch ("Fetching page 3/12... sleeping 6.1s") so the user can monitor and abort (`Ctrl+C`) safely at any point.
- If `--check-deactivation` is used, print a 5-minute countdown before starting deactivation checks ("Starting deactivation verification in 5 minutes... [cancel with Ctrl+C]").
- (V2, optional) Static local HTML report — no server, just a generated file opened in browser.

---

## 5. User Flow

**Default flow (no deactivation detection):**
1. User logs into Instagram normally via browser.
2. User extracts `sessionid` cookie, pastes into local `.env`.
3. User runs `python tracker.py --run` manually from terminal.
4. Script validates the cookie with a single lightweight check.
5. Script checks cool-down timer — refuses to run if last run was <48h ago (unless `--force`).
6. Script fetches followers/following with full throttling, printing live progress.
7. On any block/challenge signal, script halts immediately and saves partial state.
8. On success, script saves the new snapshot, diffs against the previous one, prints the color-coded report (including suspicious_deactivations flagged but not pinged).

**Optional flow (with deactivation verification):**
1–8. (As above)
9. User optionally runs `python tracker.py --check-deactivation` to verify flagged accounts (separate, manual invocation).
10. Script prints a warning: *"[WARNING] This will ping individual profiles. Max 1x per month recommended. Use at your own risk."*
11. Script waits 5 minutes (countdown displayed), allowing user to cancel with Ctrl+C.
12. Script pings each suspicious account with 2–4 second delays between pings.
13. If any profile check hits a rate limit, script halts immediately.
14. On success, script reports confirmed_deactivations separately from suspicious_deactivations.

---

## 6. Risk Management & Safety Matrix

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Account flagged/soft-blocked** | Medium (cumulative over many runs) | Strict cool-down enforcement, circuit breaker on first warning sign, no retries through challenges |
| **Account permanently banned** | Low, if mitigations followed | Never automate login; never run on someone else's account; never use on accounts >1,000 followers without explicit awareness of increased risk |
| **IP-level rate limiting** | Medium | Randomized delays, sequential-only requests, hard per-session caps |
| **Session cookie leak** | Low (user error) | `.env` gitignored, README warns explicitly never to commit or share it |
| **GraphQL/endpoint breakage** | High (Instagram changes endpoints often) | Modular fetch layer behind an interface; `instaloader` absorbs most churn; monthly manual test recommended |
| **Data privacy exposure** | Very Low | 100% local storage, no third-party servers, minimal field collection |
| **Tool used against someone else's account** | N/A (policy, not code) | Explicitly documented as forbidden in Section 2; not a code-level enforceable control, but stated clearly |
| **False positive on diff (stale snapshot)** | Low | Timestamp every snapshot; warn user if previous snapshot is >30 days old (lower confidence diff) |
| **Detection risk from deactivation checks** | Low–Medium (if `--check-deactivation` used) | Feature disabled by default; explicit warning printed if enabled; 5-min buffer breaks timing linkage; capped at 10 checks/run; extra 48-hr cool-down enforced |
| **Deactivation heuristic false positive** | Very Low | Mutual simultaneous disappearance is specific enough to be reliable; rare enough (1–3 accounts/month) to not create patterns |

---

## 7. Explicit Safety Commitments (Read Before Building)

These are the non-negotiable rules that should be hard-coded as defaults, not configurable away by accident:

1. **No password automation** — cookie-only, always.
2. **No concurrency** — one request at a time, no exceptions.
3. **No retry-through-block** — any sign of a challenge halts the run entirely.
4. **No sub-48-hour reruns** without explicit `--force` + warning.
5. **No background scheduling** — this tool will never ship with cron/task-scheduler integration.
6. **No write actions** — this tool only ever reads (GET) data; it will never follow, unfollow, like, or comment.
7. **No telemetry** — the tool will never phone home, log usage, or call any third-party API beyond Instagram itself.
8. **Deactivation detection disabled by default** — the `--check-deactivation` flag must be explicitly passed to enable profile pinging; feature does not activate on its own.
9. **Deactivation checks are throttled independently** — the 5-minute buffer and per-account delays apply even if this feature is enabled.
10. **Deactivation checks respect circuit breaker** — if any profile check encounters a rate limit or challenge, halt immediately.

---

## 8. Out-of-Scope / Explicitly Rejected Features

To keep this tool safe long-term, these are deliberately excluded — even though they're commonly requested in similar "unfollower tracker" projects:

- ❌ Auto-unfollow-back / auto-follow-back actions
- ❌ Story viewer tracking (requires near-continuous polling, high detection risk)
- ❌ Multi-account dashboards
- ❌ Scheduled/cron execution
- ❌ Any write/mutate endpoint usage
- ❌ Bulk export or sharing of scraped data
- ❌ Continuous profile pinging without heuristic filtering (deactivation detection is in-scope only because it's gated by a specific heuristic: mutual simultaneous disappearance, and optionally disabled by default)

---

## 9. Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Extraction | `instaloader` (primary), modular raw-request fallback |
| Storage | Local JSON, filesystem only |
| CLI/Output | `rich` or `colorama` for colored terminal output |
| Config | `.env` via `python-dotenv` |
| Diff Engine | Native Python `set` operations |

---

## 10. Build Plan (Suggested Phasing)

**Phase 1 — MVP (1–2 weeks)**
- `instaloader`-based fetch wrapper
- Throttling layer (delays, breaks, circuit breaker)
- Snapshot save/load
- Diff engine
- CLI report

**Phase 2 — Hardening (1 week)**
- Cool-down enforcement
- Cookie validation + clear error messaging
- Partial-failure recovery (resume-safe snapshot saving)
- Logging for debugging (local only, never uploaded)

**Phase 3 — Maintenance Mode (ongoing)**
- Monthly manual test run against your own account
- Track Instagram endpoint changes in an internal changelog
- Re-evaluate throttling parameters if any soft-block is observed

---

## 11. Success Metrics (Personal Tool — Informal)

- Tool runs successfully without triggering a challenge/checkpoint across at least 10 consecutive manual runs.
- Diff output is accurate against manual spot-checks.
- Zero account warnings, checkpoints, or temporary blocks over a 3-month usage window.
- Maintenance time stays under ~2 hours/month.

---

## 12. Disclaimer

This tool interacts with Instagram in a manner consistent with personal account introspection (read-only access to your own follower/following lists using your own authenticated session). It is not designed or intended for scraping other users' accounts, mass data collection, or any automated engagement. Instagram's Terms of Service prohibit certain forms of automated access; this PRD's safety controls are designed to minimize technical detection risk, but they do not eliminate ToS risk. Use is at the account owner's own discretion and risk.
