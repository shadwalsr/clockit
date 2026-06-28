# GhostTrack — Phase-Wise Build Plan
### Companion to PRD v2.0

This is the execution checklist. Each phase has a goal, concrete steps, and an exit condition — don't move to the next phase until the exit condition is met.

---

## Phase 0: Setup & Safety Scaffolding (Day 1)

**Goal:** Get the project skeleton in place with safety defaults baked in from line one — not bolted on later.

- [ ] Create repo structure:
  ```
  ghosttrack/
  ├── tracker.py
  ├── .env.example
  ├── .gitignore
  ├── /snapshots
  ├── /src
  │   ├── auth.py
  │   ├── fetch.py
  │   ├── throttle.py
  │   ├── storage.py
  │   └── diff.py
  └── README.md
  ```
- [ ] `.gitignore` includes `.env`, `/snapshots/`, `*.log` — commit this before anything else.
- [ ] Set up `python-dotenv`, `instaloader`, `rich` (or `colorama`) in a virtualenv.
- [ ] Write `.env.example` showing the expected `SESSIONID=` key (no real value).
- [ ] Create a `last_run.json` tracker file (timestamp of last successful run — needed for cool-down logic in Phase 2).

**Exit condition:** Project installs cleanly in a fresh venv; `.env` is confirmed git-ignored.

---

## Phase 1: Authentication Module (Day 1–2)

**Goal:** Inject the session cookie safely and validate it before doing anything else.

- [ ] Build `auth.py`: loads `SESSIONID` from `.env`.
- [ ] Construct a realistic header set (User-Agent, X-IG-App-ID, etc.) matching a real browser/app session — reuse the same set for the entire run.
- [ ] Write a single lightweight "am I logged in" check (e.g. fetch your own profile info) — this is the *only* request allowed before the cool-down/circuit-breaker checks pass.
- [ ] On invalid/expired session → print a clear message ("Cookie expired — re-extract from browser") and exit. **Do not retry auth automatically.**

**Exit condition:** Running `python tracker.py --check-auth` correctly confirms a valid session or fails clearly on an invalid one.

---

## Phase 2: Throttling & Circuit Breaker Layer (Day 2–3)

**Goal:** Build the safety engine *before* the fetch engine — fetch will call into this, not the other way around.

- [ ] `throttle.py`: implement `random.uniform(3.5, 8.2)` delay function, called between every paginated request.
- [ ] Implement the "long pause" — 30–45s after every 10 sequential requests.
- [ ] Implement occasional longer jitter (60–120s, ~1 in 15 requests).
- [ ] Implement the **circuit breaker**: a function that inspects each response and raises an immediate halt if it sees a non-JSON response, a challenge/checkpoint URL, or an explicit rate-limit header.
- [ ] Implement the **cool-down check**: read `last_run.json`, compare against `now()`, refuse to proceed if <48 hours unless `--force` is passed (print a visible warning if forced).
- [ ] Unit test the throttle/circuit-breaker logic in isolation (mock responses) — this is the part you most need to trust later, so test it now while it's cheap.

**Exit condition:** You can simulate a "blocked" response and confirm the script halts immediately and saves partial state instead of retrying.

---

## Phase 3: Data Extraction Engine (Day 3–5)

**Goal:** Fetch followers/following through `instaloader`, wrapped so the safety layer governs every call.

- [ ] `fetch.py`: wrap `instaloader`'s follower/following iterators.
- [ ] Insert a call to `throttle.py`'s delay function between every page/batch.
- [ ] Insert a call to the circuit breaker after every response before continuing.
- [ ] Print live progress per page ("Fetching page 4/12... sleeping 6.1s") via `rich`/`colorama`.
- [ ] Handle `Ctrl+C` gracefully — save whatever has been fetched so far rather than losing it.
- [ ] Keep the fallback raw-request interface stubbed (not built yet) but define the interface shape now, so swapping later doesn't touch other modules.

**Exit condition:** Running the script against your real account on a single throttled run completes successfully and prints progress without errors or warnings from Instagram.

---

## Phase 4: Local Storage System (Day 5)

**Goal:** Persist exactly what's needed, nothing more.

- [ ] `storage.py`: save snapshot to `/snapshots/snapshot_YYYYMMDD_HHMM.json` with the defined schema (timestamp, account, followers, following, fetch_duration_seconds, tool_version).
- [ ] On successful save, update `last_run.json` with the new timestamp (this is what the cool-down check in Phase 2 reads).
- [ ] Add a loader function that finds and reads the *previous* snapshot (second-most-recent file) for the diff engine.
- [ ] Add a staleness check — if the previous snapshot is >30 days old, flag it in the eventual report as "lower confidence diff."

**Exit condition:** Two consecutive runs produce two distinct, correctly-named snapshot files, and the loader correctly identifies "current" vs "previous."

---

## Phase 5: Diffing & Analysis Engine (Day 6)

**Goal:** Pure logic, no network — should be the easiest, most testable phase.

- [ ] `diff.py`: implement the three set operations (Unfollowers, New Followers, Not Following Back).
- [ ] Implement deactivation detection heuristic: flag accounts missing from both followers *and* following lists as `suspicious_deactivations`.
- [ ] Handle the first-run case (no previous snapshot) — skip diff, just confirm the save.
- [ ] Handle a corrupted/incomplete previous snapshot — warn, don't crash.
- [ ] Unit test with hand-crafted fake snapshot pairs (no live data needed) to confirm set math is correct.
- [ ] Unit test deactivation heuristic with mock data (e.g., 5 accounts in previous but 0 in current for both lists).

**Exit condition:** Feeding two fake JSON snapshots into the diff engine produces correct output for all three categories + deactivation flags.

---

## Phase 6: CLI Output & Report (Day 6–7)

**Goal:** Make the result legible at a glance, and add optional deactivation verification flow.

- [ ] Color-code: red = unfollowers, green = new followers, yellow = not-following-back, blue = suspicious_deactivations.
- [ ] Print a clean summary block (counts + usernames) at the end of the run.
- [ ] Add `suspicious_deactivations` section in output with manual verification note.
- [ ] Implement optional `--check-deactivation` flag handling:
  - [ ] Parse the flag from CLI arguments.
  - [ ] On invocation, print warning message and 5-minute countdown (allow Ctrl+C to cancel).
  - [ ] Call into a new `deactivation_verify.py` module that pings flagged accounts with delays.
  - [ ] Report `confirmed_deactivations` separately from `suspicious_deactivations`.
  - [ ] Track deactivation-check timestamp separately (extra 48-hr cool-down for this feature).
- [ ] Tie together `tracker.py --run` as the single entry point: auth check → cool-down check → fetch → save → diff → report.
- [ ] Tie together `tracker.py --check-deactivation` as the optional entry point: load suspicious accounts → validate previous run <30 days → 5-min buffer → ping with throttle → report confirmed.
- [ ] (Optional, V2) Static HTML report generator — only after CLI is solid.

**Exit condition:** `python tracker.py --run` produces a correct report with suspicious_deactivations flagged. Running `python tracker.py --check-deactivation` correctly pings flagged accounts and reports confirmed deactivations (or gracefully halts if circuit breaker triggers).

---

## Phase 7: Hardening Pass (Day 8–10)

**Goal:** Make it resilient to the things that *will* go wrong over months of use.

- [ ] Add local logging (file-based, never uploaded) for debugging failed runs.
- [ ] Add a `--dry-run` mode that validates auth and cool-down without making bulk requests.
- [ ] Improve error messages for every failure mode identified in Phases 1–3 (expired cookie, mid-fetch block, corrupted snapshot).
- [ ] Write the README with explicit safety warnings: never commit `.env`, never share `sessionid`, never run on someone else's account, recommended run frequency.
- [ ] Document the fallback-fetch-layer swap procedure for when `instaloader` lags behind an Instagram change.

**Exit condition:** You could hand this repo to your future self in 6 months and rebuild context purely from the README + code comments.

---

## Phase 8: Maintenance Mode (Ongoing, post-launch)

**Goal:** Keep it working without it becoming a second job.

- [ ] Calendar reminder: run the tool once a month against your own account as a health check, even if you don't need the data.
- [ ] Keep a simple `CHANGELOG.md` entry whenever Instagram breaks something and you patch around it.
- [ ] If you ever observe a checkpoint/warning on your account, immediately stop using the tool for at least 2–4 weeks and re-review the throttling parameters before resuming.

---

## Suggested Calendar (11 working days total)

| Days | Phase |
|---|---|
| 1 | Phase 0 + 1 |
| 2–3 | Phase 2 |
| 3–5 | Phase 3 |
| 5 | Phase 4 |
| 6 | Phase 5 |
| 6–8 | Phase 6 (includes deactivation detection optional flag) |
| 8–11 | Phase 7 |
| Ongoing | Phase 8 |

**Key sequencing rule:** Safety layer (Phase 2) is built *before* the fetch engine (Phase 3) calls into it — never the reverse. This way the fetch engine is never able to run unthrottled, even accidentally, during development. Deactivation detection is added in Phase 5–6, *after* the core safe pipeline is solid, ensuring the heuristic and optional flag are built on top of a proven-safe foundation.
