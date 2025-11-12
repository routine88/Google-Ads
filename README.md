# Google Ads AI Agent — GUI Edition

This project provides a read-only, OAuth-based Google Ads analysis GUI that:

- Launches a browser OAuth flow (no manual token editing) and stores refresh tokens securely in `token.json`.
- Pulls hourly performance, search terms, placements, and campaign stats via the Google Ads API.
- Flags first-hour click spikes (e.g., every click at 8 AM) and shares mitigation tips.
- Highlights wasteful search terms and placements so you can add negatives/exclusions.
- Offers a visually rich dashboard plus logs, while remaining read-only by default.

Use this tool to investigate suspicious click activity (like bot clusters at campaign launch) before enabling any automated account changes.

---

## 1. One-Time Prerequisites

1. **Python 3.10+** with Tk support (`python3-tk` on Linux if not already installed).
2. **Google Ads API access**
   - Developer Token (start in test mode if needed).
   - Google Cloud OAuth client (Desktop App). Download the JSON and keep it handy.
3. **Git** (to pull updates automatically via `launch.sh`).

---

## 2. First Launch

1. Place the OAuth client file (from Google Cloud) in this folder and name it `client_secret.json`, or be ready to browse to it from the GUI.
2. Run the launcher (it fetches GitHub updates, installs dependencies inside `.venv`, then opens the GUI):

```bash
./launch.sh
```

The first run may take a moment while the virtual environment is created and dependencies are installed.

---

## 3. Using the GUI

1. **Fill account details**
   - Developer Token (required).
   - Login Customer ID (MCC) if applicable.
   - Customer ID to analyze (e.g., `488-455-0863`).
   - Lookback window (default 7 days) and spike detection thresholds.
2. **Sign in with Google**
   - Click **“Sign in with Google”**. A browser window opens for OAuth.
   - On success, a `token.json` file stores the refresh token for reuse.
3. **Run analysis**
   - Click **“Run Analysis.”**
   - The Summary tab shows hour-of-day spikes, median comparisons, and recommended mitigations.
   - Search/Placement tabs list candidate negatives and exclusions with estimated wasted spend.
   - Campaigns tab ranks top spenders for quick triage.
   - Logs tab records each step (OAuth, API calls, errors).

> Everything remains read-only: no pauses, no bid edits, no negatives applied automatically. You can later extend the code to add write paths guarded by a `DRY_RUN` flag.

---

## 4. Credentials & Security

- OAuth tokens live in `token.json` (ignored by git). Delete it anytime to force a new sign-in.
- Developer tokens and customer IDs stay in-memory; nothing is written to disk except the OAuth token.
- If you prefer a different OAuth file name, use the **Browse…** button in the GUI.

---

## 5. Included Extras

- `scripts/hourly_spike_alert.js` — A lightweight Google Ads Script you can paste into the in-account Scripts UI to email yourself whenever hour-0 clicks spike vs. the median of other hours.

---

## 6. Troubleshooting

- **“Sign in with Google” button fails immediately** → Ensure `client_secret.json` exists or browse to the correct file.
- **Empty results** → Verify the lookback window contains data and that the account has API access.
- **GUI won’t open** → Ensure Tk is installed (`sudo apt install python3-tk` on Debian/Ubuntu).
- **Launch script skipped git pull** → Commit or stash local changes, then rerun `./launch.sh`.

---

## 7. Next Steps

1. Schedule `launch.sh` via cron/Task Scheduler to open the dashboard daily (or convert `gui_app.py` into a background job if you prefer automated exports).
2. Extend `gui_app.py` with guarded write paths to apply negatives, exclusions, or scheduling changes once you’re confident.
3. Pair the GUI insights with the in-account script for proactive email alerts.

Need help enabling write access or layering in BI exports? Open an issue or extend the core analytics in `ads_agent.py`.
