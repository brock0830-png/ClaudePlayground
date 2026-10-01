# Live collector: install it on your own computer

The collector is the ground truth for the study. Every 5 minutes from 09:35 to 16:00 US/Eastern on NYSE
trading days it saves Unusual Whales' own 0DTE strike profile for SPX and XSP, the SPX GEX levels (volume
and open interest) and the SPX price, as raw JSON, into the Google Drive folder. The history endpoints
only return a day's final state, so **a day that isn't collected live can never be recovered**. Install
it before 09:35 ET on the next trading day.

It must run on your computer, not in Claude Code's cloud container, because that container is deleted when
a session ends.

What it writes, under `DATA_ROOT/live/YYYY-MM-DD/`:

| file | content |
|---|---|
| `HHMM_spx_expiry_strike_pN.json` | `/api/stock/SPX/spot-exposures/expiry-strike?expirations[]=<today>`, page N (walked until an empty page) |
| `HHMM_xsp_expiry_strike_pN.json` | the same for XSP |
| `HHMM_spx_gex_levels_vol.json` / `_oi.json` | `/api/stock/SPX/gex-levels?source=vol` and `source=oi` |
| `HHMM_spx_quote.json` | `/api/stock/SPX/quote` |
| `HHMM_spx_spot_1m.json` | `/api/stock/SPX/spot-exposures?date=<today>`: per-minute price and totals; backup price source |
| `_requests.csv` | one row per request: UTC time, URL, HTTP status, bytes, SHA-256, file written |
| `_GAPS_*.txt` | written after the 16:00 slot if any slot is incomplete |

Files are never overwritten or deleted. If a slot already has files, a re-run does nothing. Each body is
saved exactly as Unusual Whales sent it. A local run log is kept in `collector/collector.log`.

Each slot makes about 8 API requests, so roughly 630 a day.

---

## 1. One-time setup (both systems)

1. **Install Google Drive for desktop** (<https://www.google.com/drive/download/>) and sign in. In
   Google Drive, create the folder `My Drive/uw_gamma_data`. It then appears on your computer at:
   - Windows: `G:\My Drive\uw_gamma_data` (the drive letter may differ; check File Explorer)
   - macOS: `~/Library/CloudStorage/GoogleDrive-<your email>/My Drive/uw_gamma_data`
2. **Install Python 3.9 or newer.** On Windows use the python.org installer and tick "Add python.exe to
   PATH". On macOS use python.org or Homebrew (`brew install python`).
3. **Get the code:**
   ```
   git clone https://github.com/brock0830-png/ClaudePlayground.git
   cd ClaudePlayground
   git checkout claude/new-session-9iepkd
   ```
   (Or download the branch as a ZIP from GitHub and unzip it.)
4. **Create `gamma_nodes/.env`** by copying `gamma_nodes/.env.example`, then fill in `UW_API_KEY` (from
   <https://unusualwhales.com/settings>) and `DATA_ROOT` (the folder from step 1). Never commit this
   file; `.gitignore` already excludes it.
5. **Windows only:** `py -m pip install tzdata`. Windows Python has no time zone database. The script
   has a built-in US daylight-saving rule as a fallback, but tzdata is the reliable source.
6. **Test it:**
   ```
   cd gamma_nodes
   python collector/collect.py --selftest      # offline, should print "23/23 checks passed"
   python collector/collect.py --force         # one real collection into DATA_ROOT/live/_test/
   ```
   Then open `DATA_ROOT/live/_test/<today>/`. It should contain about 8 `.json` files and a
   `_requests.csv` whose `http_status` column is all `200`. `spx_quote` may be a 404 if the quote
   endpoint doesn't cover the SPX index; that's fine as long as `spx_spot_1m` is 200. If anything else
   failed, the last column of `_requests.csv` says why.

## 2a. Windows: Task Scheduler

The task fires every 5 minutes, all day. The script ignores every run that isn't within 90 seconds of a
5-minute mark between 09:35 and 16:00 ET on a trading day. Because of that the schedule works in any
time zone and handles daylight-saving changes on its own.

Open **PowerShell** (no admin needed) and paste this, changing `$repo` if you cloned somewhere else:

```powershell
$repo = "$HOME\ClaudePlayground"
$py   = py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
$action   = New-ScheduledTaskAction -Execute $py `
              -Argument "`"$repo\gamma_nodes\collector\collect.py`"" `
              -WorkingDirectory "$repo\gamma_nodes"
$trigger  = New-ScheduledTaskTrigger -Daily -At 00:00
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 00:00 `
              -RepetitionInterval (New-TimeSpan -Minutes 5) `
              -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
Register-ScheduledTask -TaskName "UW gamma collector" -Action $action -Trigger $trigger `
  -Settings $settings -Description "0DTE gamma-node live collector (self-gates to 09:35-16:00 ET)"
```

`pythonw.exe` runs without opening a console window every 5 minutes.

Check that it's working:
```powershell
Start-ScheduledTask -TaskName "UW gamma collector"
Get-ScheduledTaskInfo -TaskName "UW gamma collector"   # LastTaskResult 0 = ran fine
Get-Content "$HOME\ClaudePlayground\gamma_nodes\collector\collector.log" -Tail 5
```
Outside market hours the log says `... is not a collection slot; nothing to do`, which is correct.

**Keep the computer collecting:**
- Stay **logged in**. Locking the screen is fine, but signing out or restarting without logging back in
  stops Google Drive for desktop, so the `G:` drive disappears.
- Stop it sleeping during market hours: Settings → System → Power → "When plugged in, put my device to
  sleep after" → **Never**. Or run `powercfg /change standby-timeout-ac 0`.
- Leave Google Drive for desktop running. It uploads the files as they appear.

To remove it: `Unregister-ScheduledTask -TaskName "UW gamma collector"`.

## 2b. macOS: launchd

1. Find your Python: `which python3` (for example `/usr/local/bin/python3` or `/opt/homebrew/bin/python3`).
2. Edit `gamma_nodes/collector/com.gammanodes.collector.plist`. Set the Python path and replace
   `/Users/YOU/ClaudePlayground` with where you cloned the repo (`echo $HOME` shows your `/Users/...`).
3. Install and load it:
   ```
   cp gamma_nodes/collector/com.gammanodes.collector.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.gammanodes.collector.plist
   launchctl start com.gammanodes.collector
   tail -5 gamma_nodes/collector/collector.log
   ```
4. **Give Python access to the Google Drive folder.** macOS blocks background programs from
   `~/Library/CloudStorage` until you allow it. Go to System Settings → Privacy & Security → Full Disk
   Access → `+`, press Cmd-Shift-G, and paste the real path of the Python binary (the output of
   `python3 -c "import sys, os; print(os.path.realpath(sys.executable))"`). If the log shows
   `Operation not permitted`, this step is the cause.
5. **Keep it awake on weekdays:** System Settings → Battery/Energy → prevent automatic sleeping when the
   display is off (on power adapter). Or schedule a wake with
   `sudo pmset repeat wakeorpoweron MTWRF 09:20:00`.

It fires at every 5-minute mark. As on Windows, the script ignores everything outside 09:35-16:00 ET on
trading days.

To remove it: `launchctl unload ~/Library/LaunchAgents/com.gammanodes.collector.plist` and delete the file.

## 3. Gap check

After the 16:00 slot (13:00 on early-close days) the collector checks the whole day. Each of the 78 slots
(42 on early-close days) must have the SPX and XSP strike profiles, both GEX levels, and a price. If any
slot is incomplete, it writes `_GAPS_<time>.txt` in that day's folder and a `WARNING` line to
`collector.log`, and on macOS it also shows a notification.

You can run the check yourself at any time:
```
python collector/collect.py --check              # today
python collector/collect.py --check 2026-10-02   # one day
python collector/collect.py --check-all          # every collected day
```
Gaps can't be back-filled, because Unusual Whales only keeps a day's final snapshot. The analysis records
them and uses only the slots that exist.

## 4. Year-end maintenance

The NYSE holiday table in `collect.py` covers 2025-2027. Before January 2028, add the 2028 holidays from
<https://www.nyse.com/markets/hours-calendars>. If the year is missing, the collector logs an error
instead of guessing.
