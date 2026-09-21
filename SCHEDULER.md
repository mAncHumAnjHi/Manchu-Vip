# Daily 9 AM IST scheduler

The alert is scheduled for **9:00 AM Asia/Kolkata** (`Asia/Kolkata` is used
instead of the ambiguous `IST` abbreviation).

## Linux/macOS cron

1. Make sure `.env` contains a newly generated Telegram bot token and chat ID.
2. Make the runner executable:

   ```bash
   chmod +x run_btc_alert.sh
   ```

3. Open your crontab:

   ```bash
   crontab -e
   ```

4. Add the two lines below, replacing `/absolute/path/to` with this
   directory's absolute path:

   ```cron
   CRON_TZ=Asia/Kolkata
   0 9 * * * /absolute/path/to/run_btc_alert.sh >> /absolute/path/to/btc_daily_alert.log 2>&1
   ```

The runner starts from the script's own directory, so `.env` and the Python
file are found even when cron starts with a different working directory.

## GitHub Actions

The repository includes a workflow at
`.github/workflows/btc-alert.yml`. GitHub Actions schedules use UTC, so the
workflow runs at `03:30 UTC`, equivalent to **9:00 AM Asia/Kolkata**.

Before enabling it:

1. Push these files to a GitHub repository.
2. Open **Settings → Secrets and variables → Actions**.
3. Add these repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Open the **Actions** tab and enable the workflow if GitHub prompts you.
5. Use **Run workflow** to test it manually.

GitHub may delay scheduled workflows by a few minutes during busy periods.
The workflow does not read `.env`; it receives both values only through
GitHub's encrypted secrets.

## Replit routine

Replit Routines can also express this schedule, but routine creation requires
a paid plan in the current workspace. If that becomes available, create a
daily routine with:

- **Schedule:** `0 9 * * *`
- **Timezone:** `Asia/Kolkata`
- **Action:** instruct the routine to execute `run_btc_alert.sh`

The routine may start slightly before or after the scheduled time. The
one-shot Python script remains independently testable with:

```bash
python3 Main.py
```