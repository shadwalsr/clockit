# 👻 GhostTrack — IG Local Tracker

A lightweight, **100% local** Python CLI tool for tracking Instagram follower/following changes. No cloud services, no third-party APIs, no data leaves your machine.

---

## 🛡️ Safety Philosophy

GhostTrack is built with a **safety-first** architecture. Every design decision prioritizes account protection over convenience:

- **Cookie-based auth only** — no password automation, no login flow, no credential storage beyond your session cookie.
- **Aggressive throttling** — human-mimicry delays between requests with randomized jitter. Requests are paced to look like normal browsing.
- **Circuit breaker** — instantly halts all requests if any rate-limit signal, checkpoint challenge, or anomalous response is detected. No retries, no workarounds.
- **48-hour cooldown** — enforces a minimum gap between full runs to prevent excessive API usage.
- **Local-only storage** — all data is saved as JSON files on your machine. Nothing is uploaded, transmitted, or shared. Logs are file-based and never leave your system.
- **Conservative page sizes** — uses Instagram's native page size (50) and never requests more, avoiding server-side anomaly detection.

---

## 📋 Prerequisites

- **Python 3.11+**
- A valid Instagram session cookie (extracted from your browser)

---

## 🚀 Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ghosttrack.git
cd ghosttrack
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

- **Windows (PowerShell):**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- **Windows (CMD):**
  ```cmd
  .\.venv\Scripts\activate.bat
  ```
- **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

### 5. Extract your Instagram session cookie

This is the only credential GhostTrack needs. Follow these steps carefully:

1. Open **[instagram.com](https://instagram.com)** in your browser and log in.
2. Press **F12** (or right-click → Inspect) to open **Developer Tools**.
3. Go to the **Application** tab (Chrome/Edge) or **Storage** tab (Firefox).
4. In the left sidebar, expand **Cookies** → click on `https://www.instagram.com`.
5. Find the cookie named **`sessionid`**.
6. **Copy its value** (the long alphanumeric string).
7. Open your `.env` file and paste it:
   ```
   INSTAGRAM_SESSION_ID=your_session_id_value_here
   ```

> ⚠️ **Session cookies expire.** If GhostTrack reports an invalid session, repeat this process to get a fresh cookie.

### 6. Set your Instagram username

In your `.env` file, also set:

```
INSTAGRAM_USERNAME=your_username
```

---

## 💻 Usage

### Validate your session

```bash
python tracker.py --check-auth
```

Checks that your session cookie is valid and can authenticate with Instagram.

### Dry run (validate auth + cooldown)

```bash
python tracker.py --dry-run
```

Validates authentication and checks that the 48-hour cooldown has elapsed, without making any bulk data requests.

### Full tracker run

```bash
python tracker.py --run
```

Runs the complete pipeline:
1. Authenticates your session
2. Checks cooldown window
3. Fetches current followers and following
4. Saves a timestamped snapshot
5. Compares against the previous snapshot
6. Prints a color-coded change report

### Override cooldown

```bash
python tracker.py --run --force
```

Bypasses the 48-hour cooldown. **Use with extreme caution** — frequent runs increase detection risk.

### Check deactivated accounts

```bash
python tracker.py --check-deactivation
```

Verifies accounts flagged as "suspicious deactivations" by sending lightweight profile pings. Reports which accounts are confirmed deactivated vs. still active (meaning they unfollowed you).

---

## ⚠️ Safety Warnings

> **READ THESE CAREFULLY. Ignoring them may result in account restrictions.**

- **🔴 NEVER commit your `.env` file.** It contains your session cookie. The `.gitignore` already excludes it — do not override this.
- **🔴 NEVER share your `sessionid` with anyone.** It grants full access to your Instagram account.
- **🔴 NEVER run GhostTrack on accounts you don't own.** This tool is for personal use only.
- **🟡 Recommended: max 2–4 runs per month.** The 48-hour cooldown is a minimum; spacing runs further apart is safer.
- **🔴 If you receive ANY checkpoint, challenge, or "suspicious activity" notice from Instagram — STOP using GhostTrack for at least 2–4 weeks.** Do not attempt to bypass challenges.

---

## 🔍 How It Works

### Snapshot & Diff Architecture

GhostTrack uses a simple but effective approach:

```
Run N                          Run N+1
┌─────────────────┐            ┌─────────────────┐
│  Fetch current   │            │  Fetch current   │
│  followers &     │            │  followers &     │
│  following       │            │  following       │
└────────┬────────┘            └────────┬────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐            ┌─────────────────┐
│  Save snapshot   │            │  Save snapshot   │
│  (JSON file)     │            │  (JSON file)     │
└─────────────────┘            └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │  Load previous   │
                               │  snapshot (Run N) │
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │  Set-based diff  │
                               │  computation     │
                               └────────┬────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │  Color-coded     │
                               │  CLI report      │
                               └─────────────────┘
```

**Diff categories:**

| Category | Meaning |
|---|---|
| 🔴 **Unfollowers** | Were following you last run, no longer following you now |
| 🟢 **New Followers** | Were not following you last run, now following you |
| 🟡 **Not Following Back** | You follow them, but they don't follow you |
| 🔵 **Suspicious Deactivations** | Disappeared from BOTH followers and following — may have deactivated their account |

---

## 📁 Project Structure

```
ghosttrack/
├── tracker.py              # Main CLI entry point
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── .env                    # Your credentials (git-ignored)
├── .gitignore              # Git ignore rules
├── README.md               # This file
├── CHANGELOG.md            # Version history
├── src/
│   ├── __init__.py         # Package init
│   ├── auth.py             # Cookie-based authentication
│   ├── fetch.py            # Data extraction engine
│   ├── throttle.py         # Rate limiting & circuit breaker
│   ├── storage.py          # JSON snapshot storage
│   ├── diff.py             # Set-based diff computation
│   └── deactivation.py     # Profile verification pings
├── data/
│   ├── snapshots/          # Timestamped JSON snapshots
│   └── logs/               # Run logs (never uploaded)
└── Docs/
    ├── GhostTrack_Build_Plan.md
    └── IG_Local_Tracker_PRD_v2.md
```

---

## 🔄 Fallback Fetch Layer

GhostTrack's fetch layer is designed to be swappable. If the current `RequestsFetcher` (cookie-based requests) stops working due to API changes:

1. **Option A:** Implement the `InstaLoaderFetcher` class in `src/fetch.py`. It already has stub methods — fill in the implementation using [instaloader](https://instaloader.github.io/).

2. **Option B:** Create a new class that extends `FetcherInterface`:

   ```python
   from src.fetch import FetcherInterface

   class MyCustomFetcher(FetcherInterface):
       def fetch_followers(self, user_id, username):
           # Your implementation here
           return sorted_usernames

       def fetch_following(self, user_id, username):
           # Your implementation here
           return sorted_usernames
   ```

3. Update `tracker.py` to use your new fetcher instead of `RequestsFetcher`.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## ⚖️ Disclaimer

GhostTrack is an independent, open-source project. It is **not affiliated with, endorsed by, or associated with Instagram or Meta** in any way.

This tool accesses publicly available data through your own authenticated session. Use it responsibly and in compliance with Instagram's Terms of Service. The authors are not responsible for any account restrictions, bans, or other consequences resulting from the use of this tool.

**You use GhostTrack at your own risk.** The tool includes extensive safety controls, but no automated tool can guarantee zero risk of detection.
