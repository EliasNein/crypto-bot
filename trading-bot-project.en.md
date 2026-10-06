# Trading Bot Project: Planning, Progress Log and Technical Reference

> English translation of `trading-bot-projekt.md`, kept in sync with it
> (every change lands in both files in the same commit). If they ever
> differ, the German original is authoritative.
> The archive `trading-bot-projekt-archiv.md` exists in German only. Quoted
> titles of archive sections (e.g. 6g „Symbolbindung“) are left in German so
> they can be found there. Log tags and messages (e.g. `[ORDER-UNKLAR]`) are
> quoted exactly as the code emits them. Dates use the original DD.MM.YYYY
> format; decimal commas in amounts are kept as in the original.

**As of:** 29 September 2026
**Status:** Testnet operation, no live money. The security review (K1–K5, W1–W18, infrastructure) has been complete since 16.09. The home server has in fact been running as the complete system since 16.09.2026, with all four components and active allocator opt-in for DCA and Trend. The current trading status there was verified on 25.09.2026 (see 6h). The formal cutover (VPS shutdown, final snapshot) remains planned for 05.10.2026. Until the end of the contract on 12.10., the VPS keeps running in isolation, without the allocator. The test phase has been extended to approx. 2–3 months, i.e. until roughly mid-November to mid-December 2026. Since the review, several find-and-fix series have been completed: the improvement proposals (6i, 17.09.), the dry-run amounts (22.09.), the code review of 25.09. and the system check of 27.09. with K-A/K-B and W-A to W-G (all 6g). The technical reference for the current state is in section 7.

---

*Older, completed history (sections 1–6i: research, planning and the chronological log up to 28.09.2026) is in `trading-bot-projekt-archiv.md`, unchanged, and only needs to be read when required, e.g. for a question about the original choice of strategy. References such as „siehe 6g“ ("see 6g") in code and docs mean the sections there. What is still open from it today is summarised in the section "Current status and open items".*

---

## Current status and open items

*As of 29.09.2026. Like section 7, this section describes the current state and is corrected directly. The derivation is in the archive (`trading-bot-projekt-archiv.md`) in each case; section numbers and headings are unchanged there.*

### Operations

- **Home server** (complete system since 16.09.2026): all four bots as systemd services on the testnet. DCA, Grid and Trend trade with real testnet orders (`*_BOT_ENABLE_TRADING=true`, verified 25.09.), the allocator opt-in for DCA and Trend is active. `GRID_AMOUNT_PER_LEVEL` = 9,38, maximum capital commitment approx. 150,08. Details: archive 6e, 6h, 6g „W16 umgesetzt“.
- **VPS:** DCA with real testnet orders, Grid and Trend in dry run, no allocator. Contract ends 12.10.2026. Details: archive 6b, 6h.
- **Pair:** on the testnet BTCUSDT; all "€" amounts there are USDT. For real money, BTCEUR will be used (decision 28.09.2026). Details: archive 5b (note 28.09.), 6g „Symbolbindung“.

### Deploy status

- Both servers run `10ce096` (as of 28.09.2026). Committed but not deployed: W-C to W-G including the addendum (`a67e7dc` to `46ca7a7`) and the symbol binding (`e2a37bd` to `9ef7d60`). At the next deploy, after the pull and before the restart: `python -m dca_bot.symbol_guard --report`.
- From now on, deploys are recorded **here**, as `Deployed: <hash> auf Homeserver/VPS am <Datum>`. This replaces the note of 29.09.2026 in archive 6g. Details on rolling back to the old code: archive 6g „Symbolbindung“.

### Dates

- **05.10.2026, formal cutover:** final snapshot from the VPS (logs and `data/` of all bots), integrity check, shut down the VPS services via `systemctl stop`. This also ends the VPS vs. home server comparison. Details: archive 6e (schedule), 6c.
- **12.10.2026, end of VPS contract:** by then at the latest the final `data/` snapshot; also remove the Claude Code deploy key. Details: archive 6b, 6g „Sicherheitsreview vollständig abgearbeitet“.
- **Test phase** on the home server until roughly mid-November to mid-December 2026. Details: archive 6h.

### Preconditions for real capital (300 €: 150 € Grid, 150 € allocator pot)

1. **Position sizes:** still open are `DCA_QUOTE_AMOUNT`, `TREND_AMOUNT_PER_TRADE`, grid range and `GRID_SPACING_PCT`. When switching pairs, all amounts and the range must be set anew in euros. Details: archive 5b, 6d item 3.
2. **Data basis for `TREND_STOP_LIMIT_OFFSET_PCT`**, so far n = 2 simulated exits. **No calibration data is currently coming in:** the dry-run position of 15.09. occupies the only trend slot. What is needed is first its exit, then a real entry, then a stop order filled on the exchange. If it closes via the internal stop-loss, the latch blocks new entries until the manual reset. Details: archive 6f, 6h „Trend-Bot: Die Kalibrierungsdaten fließen noch nicht“.
3. **Final security review** shortly before going live. Details: archive 6d, 6h.
4. **Switching the pair to BTCEUR**, not yet planned: all four `*_SYMBOL`, grid range and amounts in euros, fresh ledgers or deliberately carried-over existing holdings. Also open are the dashboard app and the pilot. It is not verified whether Binance responds with −2013 to a query under the wrong symbol; this can only be checked in the pilot. Details: archive 6g „Symbolbindung“, 6h.
5. **"Pay fees with BNB" switched off.** Details: archive 6h.
6. **Sub-accounts per bot:** decide deliberately before going live, not a hard precondition. If the decision is in favour, code is needed (separate keys per bot, audit across several accounts) before going live. Details: archive 6h (addendum 29.09.), 6g „Systemcheck vom 27.09.2026“.

### Deliberately deferred or earmarked

- **W14, Grid without exchange-side stop-loss:** a separate architecture decision between one combined stop order and n individual stop orders. Until then, the trend-break stop only blocks purchases, and capital commitment is capped by levels × amount. Details: archive 6g „W14“.
- **Automatic stop-loss reset (item 16):** played through in the backtest, n = 1. The decision will be made with real data; until then the reset is manual. Details: archive 6i „Punkt 16 als Backtest-Experiment“.
- **Item 13 (shared bot runtime) and F2 (kill switch pauses instead of terminating):** touch all four entry points, only after the cutover. Details: archive 6i „Offen aus der Liste“, 6g „W-F“.
- **DCA portfolio stop-loss in the backtests:** is not modelled, so the DCA figures in 5a and 6 overestimate the capital deployed in a bear market. Details: archive 6g „W-G“.
- **Archiving the ledger files:** no acute need, only together with the dashboard app. Details: archive 6g „Vorgemerkt: langfristiges Datenwachstum“.
- **Retroactively correcting the fill price of old ledger entries:** earmarked for the tax export. Entries from before K2 have no `clientOrderId`. Details: archive 6g „Priorität 4“.
- **Item 15 (SQLite):** still years away at today's data volume. Details: archive 6i.

### For evaluating the test phase

- In the home server ledgers of DCA and Trend, dry-run and real entries sit side by side; the evaluation must separate them by `dry_run`. The grid ledger is real throughout. Details: archive 6h „Umstellung auf echte Orders“.
- The number of trades is not comparable between VPS and home server (allocator). What is compared is the return per euro deployed. Details: archive 6g „Beobachtung zur Allocator-Wirkung“, 5a.
- The dry-run values of the VPS grid were corrected on 22.09.; the `.pre-fix` copy stays in place until the evaluation. Details: archive 6g „Folgefund aus K3“.
- The position audit does not attribute dust (`dust_qty`) to any bot; it appears as a surplus. Details: archive 6g „Systemcheck vom 27.09.2026“.
- **Ticker outliers on the testnet:** testnet profits are distorted by them and are not suitable for return estimates. A thin order book is suspected as the cause; this was not measured. Example 02.10.2026: of the realised grid result of 8,65 USDT (evaluation of 06.10.), 6,31 USDT fall on this single day, of which 6,15 USDT on six levels (8 to 13). On 02.10. they were bought between 13:30:13 and 13:30:16 UTC at 77.809 to 79.480 USDT and sold between 13:35:17 and 13:35:30 UTC at 86.928 to 86.962 USDT, 0,82 to 1,09 USDT per level, whereas normal cycles yield 0,14 to 0,21 USDT. The mainnet hourly candle of 13:00 UTC had its low at 86.465,72, the testnet candle at 75.745,57; the mainnet daily low was 83.888 (hourly candles, 18:00 UTC). All six purchase prices are below the mainnet daily low. Approach for cleaning up: check the buy and sell times of the grid trades against the mainnet hourly candles. Statements about the strategy rest on the backtests (mainnet candles); the testnet mainly proves the technology. The trend dry-run position of 15.09. and the calibration of `TREND_STOP_LIMIT_OFFSET_PCT` also depend on the same ticker: there, an outlier could produce entries or stop-loss triggers that would not exist on the real market. Details: log 06.10.2026.

### Not in the repository

- The research report for section 5 and the review output of 15.09. exist only in the claude.ai chat. If exportable, they belong in `docs/research/` and `docs/reviews/` respectively; check the review output for IP addresses and paths beforehand. Details: archive 5, 6g (introduction).

---

## Log from 29.09.2026

Chronological log since the document was split, continuation of section 6 in the archive. Entries stay in place; later findings are added as dated notes. Older entries will later be moved to the archive in bulk.

### Project document split (29.09.2026)

`trading-bot-projekt.md` had grown to over 2,500 lines (350 KB) and was read in full in many sessions, although most of it is completed. Sections 1–6i are now in `trading-bot-projekt-archiv.md`, unchanged. What remains here is the header, the new section "Current status and open items", this log and section 7. Nothing has been deleted or reworded. After the move, a check script confirmed that the archive part is byte-identical to the original lines and that every original line is in exactly one of the two files. Only the "Stand:" line, the introductory paragraph of section 7 and the footer were changed.

Deliberately **not** adjusted are the references in code comments and tests („siehe trading-bot-projekt.md 6g“ and the like). The sections have the same numbers in the archive, and the reference paragraph above leads there. Adjusted were the README (sections 8.2, 8.3, 9 and 10) and `CLAUDE.md`.

### Grid result of 02.10.2026 is a testnet artefact (06.10.2026)

In the evaluation of the home server data on 06.10.2026, the realised grid result was 8,65 USDT, of which 6,31 USDT on 02.10.2026 alone. The cause is a testnet artefact: the bot correctly bought and sold at the prices the testnet ticker reported; on the real market these prices would not have existed.

**Evidence:**

- On 02.10., six grid levels (8 to 13) were bought at purchase prices of 77.809 to 79.480 USDT between 13:30:13 and 13:30:16 UTC. Between 13:35:17 and 13:35:30 UTC, all six were sold at 86.928 to 86.962, together +6,15 USDT. Levels 8 to 13 account for 0,82 to 1,09 USDT each, normal cycles yield 0,14 to 0,21 USDT.
- The public hourly candles (BTCUSDT, 1h) show the following lows for 02.10., testnet versus mainnet: 05:00 UTC 66.745,57 vs 85.893,27; 13:00 UTC 75.745,57 vs 86.465,72; 15:00 UTC 75.000,00 vs 85.162,90. In all other hours the two sources are close together. The mainnet daily low was 83.888 (hourly candles, 18:00 UTC); all six purchase prices are below it.
- The testnet low of 75.745 in the 13:00 hour matches the purchases at 13:30.

**Limits of the statement:**

- The 05:00 and 15:00 hours also had testnet outliers. Whether the bot bought anything in those hours was not checked.
- A thin order book is only suspected as the cause of the deviation of the testnet from the mainnet candles, not measured.
- The remainder of about 2,5 USDT from normal operation is an approximation (8,65 minus 6,15) and not individually substantiated. Whether this remainder is free of outliers was not checked.

**Conclusion:** Testnet profits are not suitable for return estimates; the rules for the evaluation are in the section "Current status and open items" under "For evaluating the test phase". The trend dry-run position of 15.09. and the stop-offset calibration depend on the same ticker; an outlier could produce entries or stop-loss triggers there that would not exist on the real market. Whether this happened was not checked.

---

## 7. Technical reference (moved here from the README, 25.09.2026)

This section describes the **current state** of the bots and their
safety mechanisms – unlike the chronological log (section 6 in the
archive `trading-bot-projekt-archiv.md`, since 29.09.2026 "Log from
29.09.2026" above). References to sections 5, 6 and 6a–6i mean the
archive. Until 25.09.2026 it was in the README, which had grown to over
1,200 lines as a result. Since then the README has been the lean entry and
setup documentation with a short overview of the safety mechanisms; the
detailed texts are here. They were **taken over verbatim** – only
references to section numbers that changed due to the move were adjusted.
Since then the section has been maintained as the reference for the
current state: whatever is no longer correct here is corrected directly,
without a note as in the log sections. Where a log entry and this section
describe the same thing (e.g. W9 in archive 6g and 7.4), the overlap is
intended: the log entry records what was decided at the time, this section
the current state. In case of discrepancies, section 7 applies.
Configuration, startup and tools: README.

### 7.1 Cross-bot safety mechanisms

- **Dry run by default**: no real orders without explicit opt-in.
- **Daily limit** (`max_daily_spend` in `config.py`): prevents a bug (e.g.
  an infinite loop) from triggering an unlimited number of purchases. It
  is calculated from the persistent trade history
  (`data/trade_ledger.json`), so it also continues to apply after a
  restart of the bot. The daily window runs consistently in **UTC**,
  matching the timestamps in the ledger – with local server time the
  boundary shifted by hours relative to the data, depending on the time
  zone. The daily summary follows the same boundary (UTC midnight).
- **Kill switch**: if the file `STOP` (path configurable via
  `DCA_BOT_KILL_SWITCH_FILE`) exists in the project directory, or
  `DCA_BOT_HALT=true` is set, the bot stops immediately and cleanly – even
  in the middle of a running buy cycle, not only at the next interval.
  Three sources are checked: the kill-switch file, the process
  environment (e.g. from the systemd unit) and the **current** `.env`. The
  latter is re-read on every check – writing `DCA_BOT_HALT=true` into
  `.env` later therefore takes effect immediately, without a restart, just
  like creating the STOP file. The three paths are combined with OR,
  deliberately asymmetric: triggering should be easy, accidentally
  lifting it hard – to restart, all three sources must be clean.
  **The kill switch terminates the process** (normally, exit code 0,
  pinned down by test for all four bots). `Restart=on-failure` therefore
  does not restart it: restarting means first clearing all sources and
  then starting the service by hand (`sudo systemctl start <service>`).
  If a source is still present at startup, it exits again immediately
  after the startup checks. Until then no cycle runs and no heartbeat
  arrives; open grid positions are unprotected (W14).
  For the grid bot, the kill switch is additionally checked **between
  every single purchase** of a cycle, not just once before it: if the
  price crosses several levels within one interval, the loop buys several
  positions in a row – and that is exactly when someone pulls the kill
  switch.
- **Global kill switch `STOP_ALL`**: a file `STOP_ALL` in the project
  directory **or** `STOP_ALL=true` (process environment or `.env`) stops
  **all four bots at once** – in addition to their own switches, not
  instead of them. Stopping a single bot therefore remains possible.

  ```bash
  touch STOP_ALL     # stops DCA, Grid, Trend and Allocator
  # Restarting: first remove the file, then start the services
  rm STOP_ALL
  sudo systemctl start dca-bot grid-bot trend-bot allocator
  ```

  Previously it took four files or four variables – and in an emergency,
  "did I really get all four?" is exactly the question you don't want to
  have to ask yourself. The file name is therefore deliberately **not**
  configurable (unlike the bot-specific `*_KILL_SWITCH_FILE`): a global
  kill switch whose path you first have to look up misses its purpose.
  The triggered message also names **which** source took effect – with
  four bots stopping at once, that is the first question.
- **Portfolio stop-loss** (`DCA_BOT_STOP_LOSS_PCT`, default 25%): if the
  current value of the position bought so far falls more than X% below
  the sum of the purchase prices, the bot pauses further purchases and
  logs this clearly. It does **not sell automatically** – that is
  deliberately a separate, later decision. The pause also does **not lift
  by itself** when the price recovers (whipsaw risk, see comment in
  `dca_bot/risk.py`) – a manual reset is required, either with
  `python -m dca_bot.reset_stop_loss` or by deleting the file under
  `DCA_BOT_STOP_LOSS_STATE_FILE` (default `data/stop_loss_paused.json`).
- **Error handling per cycle**: a single error (e.g. API timeout) does
  not terminate the whole bot but is logged; the next cycle continues
  normally.
- **No order without a ledger entry** (`dca_bot/pending_orders.py`):
  every real order is given a self-assigned `newClientOrderId` in
  advance, which is written to a small, separate file
  (`data/pending_orders_<bot>.json`) **before** the network call. If the
  connection then drops (`requests` timeout, `BinanceRequestException`),
  the bot does **not** simply return "no trade" but asks the exchange via
  `get_order()` for this ID what actually happened. The same applies to a
  response from Binance whose outcome is unknown according to the Binance
  docs (HTTP 5xx, error codes −1006/−1007) – it is not a rejection, even
  if python-binance reports it as `BinanceAPIException`:
  executed → the real order data is returned and booked normally; never
  accepted (error code −2013) → counted as "no trade" for this cycle, but
  the entry stays in place (the query comes immediately after the
  timeout, an order still in flight would only become visible
  afterwards) and is only considered definitively unknown from an age of
  60 s; unclear → **no guessing**, but `ERROR` + Telegram
  (`[ORDER-UNKLAR]`, with the ready-made command
  `python -m dca_bot.check_orders --client-order-id <id>` for looking it
  up), and the entry stays in place. Even after a successful order, the
  entry is only removed **after** the strategy has the trade in the ledger
  (`confirm_booked()`). At the start of **every cycle** and at bot
  startup, each bot works through remaining entries and records missing
  ledger entries as `[REKONZILIATION]` (at runtime via Telegram only once
  per order and process run). This also closes the window that arose,
  without any network error, from a process kill between order and ledger
  entry.
- **No second sale while the first is unresolved** (since 27.09.2026): if
  a sale or a stop order for a position is still in the pending file, the
  bot does not sell it again and places no further stop order. Without
  this lock, a second sale went through on the shared account, covered by
  another bot's holdings. The sale ID is in the ledger
  (`sell_client_order_id`/`exit_client_order_id`), which makes the
  catch-up idempotent. A sale for a position that was closed with a
  different order is reported as `[GRID-DOPPELVERKAUF]`/
  `[TREND-DOPPELVERKAUF]` (double sale) and stays in the pending file
  until resolved manually.
- **A corrupted ledger stops the bot instead of silently resetting**: the
  daily limit and the stop-loss cost basis are calculated from the ledger
  file on every cycle. Reading an existing but unparseable file as "empty
  history" would set both to zero – the bot would keep buying although
  capital is in fact committed. Therefore: a clear `ERROR` + Telegram,
  and the bot **does not start** (or the running cycle aborts). A
  **missing** file explicitly remains the normal case "fresh deployment,
  very first start". So that this does not mean a loss of availability,
  all three ledgers are now written **atomically** (temporary file +
  `os.replace`) – a crash in the middle of writing can no longer leave a
  half-written file.
- **No immediate purchase on every restart** (DCA): at startup the bot
  checks from the ledger how long ago the last cycle was and waits until
  the next due time. Previously **every** process start immediately
  triggered a real purchase – in a restart loop, as many as the daily
  limit still allowed. With an empty ledger (very first start) it buys
  immediately as before.
- **Sign of life** (`dca_bot/heartbeat.py`, `HEARTBEAT_INTERVAL_HOURS`,
  default 24 h): each of the four bots reports once per interval via
  Telegram (`[HEARTBEAT] <Bot> läuft, Version <hash>, letzter
  erfolgreicher Zyklus <Zeitpunkt>` – "<bot> running, version <hash>,
  last successful cycle <time>"), even if nothing has happened. Without
  this, a crashed bot is only noticed through *missing* messages – and a
  silent grid bot can mean "no level crossed" or "dead since Tuesday".
  The cycle timestamp sent along additionally distinguishes "process is
  running" from "process is working": it is only set after a
  **successful** cycle; a cycle that aborts with an error leaves it
  unchanged (since 25.09.2026, previously every run counted).
  Deliberately **no** heartbeat at startup: a bot in a restart loop would
  otherwise report "I'm alive" every minute.
- **Heartbeat status files for external observers**
  (`dca_bot/heartbeat_status.py`, since 25.09.2026): each of the four
  bots writes its own small JSON file after every cycle,
  `data/heartbeat_dca.json`, `data/heartbeat_grid.json`,
  `data/heartbeat_trend.json` and `data/heartbeat_allocator.json`
  (paths via `DCA_`/`GRID_`/`TREND_`/`ALLOCATOR_HEARTBEAT_STATUS_FILE`).
  Content: `last_successful_cycle` (ISO timestamp in UTC or `null`),
  `last_cycle_attempt` (last attempt, successful or not) and
  `consecutive_failures`. What counts as success is the same as for the
  sign of life above; the writer receives exactly this timestamp. Nothing
  is written on a kill switch. The files are **pure output** for the
  dashboard app: no bot reads its own or another bot's heartbeat file, so
  no coupling arises between the processes. One file per bot instead of a
  shared one, because four independent processes could otherwise
  overwrite each other. Writing is atomic (temporary file, fsync,
  `os.replace`) as with the ledgers. A write error is caught and logged
  once per error series; it has no effect on trading, kill switch or
  Telegram. The values apply **per process run**: after a restart
  everything starts again at `null`/0, and until the first cycle the file
  still shows the state of the previous process (for DCA and Trend up to
  24 h because of the startup wait).
- **No duplicate bot start** (`dca_bot/process_lock.py`): each of the
  four processes holds an exclusive lock on its own `.lock` file at
  startup (`fcntl`/`msvcrt`). A second start of the same bot (e.g. a
  manual invocation alongside the running systemd service) is rejected
  with a clear message, instead of both reading and writing the same
  ledger and overwriting each other's entries. Deliberately a lock on the
  file descriptor and not a PID file: the operating system releases it
  even on `kill -9`, so a leftover `.lock` file does not block a restart.
- **Live switch with a safety threshold** (`USE_TESTNET`, default
  `true`): whether the bots trade against the testnet or the real exchange
  is a setting in `.env` and no longer a code edit. Only the values
  `true`/`false` are allowed – a typo aborts instead of silently falling
  back to `false` (i.e. **live**). With `false`, each of the four
  processes outputs an unmistakable block in the log at startup
  (`ACHTUNG: LIVE-MODUS MIT ECHTEM GELD AKTIV` – "WARNING: LIVE MODE WITH
  REAL MONEY ACTIVE") **and** a Telegram message. Three states are
  distinguished: testnet (one quiet line), live with active trading
  (`CRITICAL`), and live with trading disabled – the latter is explicitly
  a case of its own and not a harmless dry run, because the account data
  is real and flipping a single variable is then enough for real money.
- **Mandatory variable check at startup** (`dca_bot/config_guard.py`):
  every value is checked on loading instead of carrying on with a default
  or only being noticed during operation. Covered are, among others, empty
  values (`GRID_SYMBOL=` is a value, not a missing line – the default
  does not replace it), intervals of 0 (a busy loop against the API),
  nonsensical percentages (a `GRID_STOP_LOSS_PCT=150` would result in a
  negative threshold and thus a silently ineffective stop-loss),
  unreadable numbers (the message now names the affected variable),
  placeholders copied from `.env.example` and an empty pending-orders
  path, which would switch off the K2 protection. Where `0` has a
  documented meaning (stop-loss off for DCA/Grid, heartbeat off), it
  remains explicitly allowed – not so for the trend bot, where a
  stop-loss of 0 % would close every position again immediately. The
  `*_HALT` variables are also checked at startup: at runtime the kill
  switch deliberately continues to read them tolerantly (an exception
  every five seconds would be worse than the problem), but
  `GRID_BOT_HALT=ture` means "no kill switch" there – and startup is the
  only moment to notice this safely.
- **Additionally mandatory in live mode**: Telegram credentials (without
  a channel, precisely `[ORDER-UNKLAR]`, `[STOP-LOSS]` and `[HEARTBEAT]`
  would arrive nowhere) as well as all values that determine the position
  size – `DCA_QUOTE_AMOUNT`, `DCA_MAX_DAILY_SPEND`, `GRID_LOWER_LIMIT`,
  `GRID_UPPER_LIMIT`, `GRID_SPACING_PCT`, `GRID_AMOUNT_PER_LEVEL`,
  `TREND_AMOUNT_PER_TRADE` – as well as `TREND_STOP_LIMIT_OFFSET_PCT`.
  They must be set explicitly in `.env` and must not fall back to the
  testnet defaults: live, it is precisely these that control the actual
  capital commitment, and a forgotten entry would look in the log like a
  deliberately chosen value. Since 27.09.2026 (W-C), "set" is not enough:
  if the test value from `.env.example` is still there
  (`LIVE_PLACEHOLDER_VALUES` in `config_guard.py`, compared numerically),
  the bot does not start. A test value that is meant to apply deliberately
  after calibration is confirmed via `LIVE_CONFIRMED_VALUES=NAME=VALUE,…`;
  the confirmation applies only to exactly this value, unknown or
  duplicate names abort. On the testnet, neither is checked.
- **Misconfiguration does not cause a restart loop**: the check
  necessarily runs before the logging setup. Instead of a bare traceback
  with exit code 1 (which `Restart=on-failure` would repeat endlessly
  without ever succeeding), there is a clear message on stderr, a
  Telegram message where possible, and a clean exit. Same pattern as for
  an already running bot.
- **No start on another pair's files** (`dca_bot/symbol_guard.py`, since
  28.09.2026, background in 6g „Symbolbindung“): at startup, even before
  reconciliation, each of the four processes checks whether its files
  belong to the pair from `*_SYMBOL`. The bot checks its ledger (all
  entries, open and closed), its pending file, its stop-loss lock and,
  with active opt-in, the allocator state. The allocator checks its own
  state. Entries without a `symbol` field date from before and are
  treated as BTCUSDT (`LEGACY_SYMBOL`). The rule applies on reading; the
  files are not rewritten for it. If something belongs to another pair,
  the bot does not start. It writes an `ERROR` line listing what is
  where, sends `[SYMBOL-KONFLIKT]` (symbol conflict) including the
  solution via Telegram and exits with exit code 0 as with a
  misconfiguration. The only exception is a lock file with unreadable
  content: it results in a warning in the log and once per start via
  Telegram (`[SYMBOL-WARNUNG]`, symbol warning), not an abort, and the
  lock remains in effect. In addition, `config_guard.py` checks the pairs
  against each other: the allocator requires `DCA_SYMBOL` and
  `TREND_SYMBOL` to match its `ALLOCATOR_SYMBOL`. DCA and Trend only
  check this when the opt-in is set (`*_ALLOCATOR_STATE_FILE`). At
  runtime, an allocation calculated for a different pair is treated like
  a stale one: 0,0, i.e. 100 % DCA and no trend entry.

  **Before every restart:** `python -m dca_bot.symbol_guard --report`
  shows what the startup would do. A startup abort silently leaves the
  service off: no heartbeat, and open grid positions are then
  unprotected. The report lists, per bot and file, whether the field is
  present and whether the pair matches, and says „würde starten“ (would
  start), „würde starten, mit Warnung“ (would start, with warning) or
  „würde NICHT starten“ (would NOT start) with the reason. Exit code 0
  only if every bot would start, otherwise 1. It only reads, needs
  neither lock nor credentials, creates no file and uses the same check
  functions as the startup.
- **Consistency check before every sale** (`dca_bot/balance_guard.py`):
  DCA, Grid and Trend share one account and trade the same symbol, but
  each keeps its own ledger – the attribution "this BTC belongs to the
  grid bot" exists only in the books. Before every real sale, a check
  against the actual account balance is therefore made, in two stages: if
  the **free** balance is not sufficient for exactly this sale, no sale
  is attempted at all (the exchange would reject it, and the failure
  would look like a network problem in the log). If, beyond that, the
  account does not cover what the bot's own ledger carries as open in
  total, there is a clear warning including Telegram – but the single,
  covered sale goes through **anyway**: it reduces risk and capital
  commitment; blocking it would only leave assets stranded (the same
  trade-off as with the grid stop-loss, which also lets sales through).
  Which committed quantity belongs to which bot can be answered without
  access to other ledgers – since the K2 fix, every order carries a bot
  prefix in its `clientOrderId`. The check is deliberately built so that
  it cannot produce false alarms and in return does not detect every
  case. **What it cannot do:** know who the free balance belongs to. Free
  BTC of the DCA bot covers an oversale by Grid or Trend. Protection
  against a double sale therefore comes not from this check but from the
  lock via the pending file (above).
  A balance that **cannot be retrieved** allows the sale: a network error
  says nothing about the account, and refusing a stop-loss exit because
  of it would be the more dangerous direction.
- **Consistency check at bot startup too** (`dca_bot/startup_checks.py`):
  the same reconciliation additionally runs once at every startup – in
  **all three** bots, including the DCA bot. This closes two gaps. First:
  the DCA bot never sells, so it had no sell path at all and therefore no
  moment at which its bookkeeping was ever held up against reality –
  although its ledger is the cost basis of the portfolio stop-loss, and a
  quantity that is too large overestimates the portfolio value, so the
  stop-loss triggers too late. Second: for Grid and Trend, the check only
  ran at the moment of sale, and weeks can pass between two sales, for
  the trend bot even months. Startup is the natural second point in time
  – it comes after every downtime, every deployment and every manual
  change to the ledger files, i.e. after precisely the events that
  produce a discrepancy in the first place. As in the sell path, it is
  reported **loudly but non-blocking** (`[BESTAND-DISKREPANZ]`,
  `[GRID-BESTAND-DISKREPANZ]`, `[TREND-BESTAND-DISKREPANZ]` – holdings
  discrepancy): a bot that does not even start because of a suspected
  bookkeeping problem solves nothing – it only additionally takes away
  the ability to protect and close open positions. The gate is
  deliberately the **quantity** and not `*_BOT_ENABLE_TRADING`: if the
  ledger carries no real open quantities, nothing happens at all and not
  a single API call is used; if it carries some, the check runs – even in
  dry run, because a deferred bot with real existing holdings is exactly
  the interesting case. The call sits in the same encapsulated startup
  sequence as the reconciliation, so a failure cannot prevent the
  startup.

- **Real trading rules instead of assumptions** (`dca_bot/order_utils.py`,
  `binance_client.get_symbol_trading_rules`): before every order, quantity
  and prices are quantised against the symbol's actual filters
  (`LOT_SIZE`/`stepSize`, `PRICE_FILTER`/`tickSize`), and the purchase
  amount is checked against the minimum volume (`NOTIONAL`/`minNotional`).
  The rules are fetched from the exchange once per bot process and cached
  afterwards – not re-fetched every cycle. If the fetch fails, the error
  is **passed on** instead of falling back to default values: a silently
  mis-rounded order would be worse than an aborted cycle. All bots
  therefore fetch the rules **before** placing an order – a failure then
  aborts without consequences, instead of leaving an already executed
  order unbooked.
- **Fee-adjusted quantities**: on a spot purchase, Binance deducts the
  trading fee from the base asset received (for BTCUSDT, in BTC).
  `executedQty` is the amount **before** this deduction – so the ledger
  receives the quantity actually available (`executedQty` minus the fee
  charged in BTC from `fills[]`, rounded down to the `stepSize`). Without
  this, every later sale and every stop-loss order would be for a
  quantity that no longer exists. Conversely, on a sale the fee charged
  in USDT is deducted from the proceeds so that the realised profit is
  not systematically too optimistic. In dry run there is no fill and
  therefore no known fee – it is deliberately **not** estimated, but the
  quantity is still quantised so that simulated and real values remain
  comparable.
- **Fill price instead of ticker price** (DCA, Grid, Trend, since
  25.09.2026): the price a bot writes to the ledger for a real order is
  the actual average fill price from the order response
  (`cummulativeQuoteQty / executedQty`), not the ticker queried shortly
  before. This is the same source the reconciliation has always used. For
  the trend bot, the stop-loss threshold depends on it (see 7.3); for DCA
  and Grid, the display in the dashboard and tax export. In dry run, the
  observed price is the simulated fill. Entries written earlier are
  unchanged.

### 7.2 Grid bot

Buys at fixed price levels ("grid levels") within a configured price
range and sells each individual position again as soon as the price rises
to the next higher level – spot only, no leverage, no liquidation risk.
See section 5 for the research on this: before fees, the expected value is
academically/mathematically zero; the point of this strategy lies in the
simple, latency-insensitive implementation, not in superior returns. The
main risk is a trend break.

**Backtest available** (`python -m dca_bot.grid_backtest`, code in
`grid_backtest.py`) – see "Backtest" below and section 6 for the results
and an important caveat on the price range.

#### Core logic

- The grid levels are calculated geometrically (`level[i+1] = level[i] * (1 +
  GRID_SPACING_PCT/100)`), not linearly.
- At most one position per level can be open at the same time. Each
  position remembers its buy level and its individual sell target (the
  next higher level) – sales are therefore always unambiguously assigned
  to a specific buy level, never to "any" position.
- Purchases are triggered by crossing detection (comparison with the last
  observed price), not by a simple comparison with the current price –
  otherwise a cold start in the middle of the grid would immediately buy
  every level above the starting price at once. If the price falls
  through several levels at once within one interval (e.g. in a crash),
  all levels actually crossed are bought.
- The buy and sell price of a real position in the ledger are the actual
  fill price from the order response (`cummulativeQuoteQty /
  executedQty`), not the ticker queried shortly before – the same source
  as for catching up via the reconciliation. In dry run, the observed
  price is the simulated fill. Independently of this, the sell target
  remains the next higher grid level.
- Maximum capital commitment is inherently limited by the design: number
  of buy levels (levels − 1) × `GRID_AMOUNT_PER_LEVEL` – no additional
  daily limit needed.
- **The same decision logic** (`compute_grid_levels`,
  `find_triggered_buy_levels`, `is_sell_target_hit`,
  `is_trend_break_stop_loss_hit` from `grid_signals.py`) is imported by
  the backtest AND the live strategy – no duplicate implementation that
  could drift apart unnoticed (same principle as for the trend bot, see
  7.3).

#### Safety mechanisms (independent of the DCA bot)

- **Dry run by default**, analogous to the DCA bot.
- **Kill switch**: own file (`GRID_KILL_SWITCH_FILE`, default
  `STOP_GRID`) and own env variable (`GRID_BOT_HALT`) – independent of the
  DCA kill switch.
- **Trend-break stop-loss** (`GRID_STOP_LOSS_PCT`, default 15%): if the
  market price falls more than X% below `GRID_LOWER_LIMIT`, the bot pauses
  new purchases. Positions already open continue to be sold normally when
  their target is reached (sales reduce risk rather than increase it).
  Latched like the DCA stop-loss: no automatic reset; manually with
  `python -m dca_bot.reset_grid_stop_loss` or by deleting the file under
  `GRID_STOP_LOSS_STATE_FILE`.
- **Dry-run positions are never really sold:** before every sale, the bot
  checks the `dry_run` flag of the respective position in the ledger, not
  just the current trading mode. A position "bought" in dry run does not
  exist on the exchange at all – it therefore remains simulated even
  after switching to `GRID_BOT_ENABLE_TRADING=true` and is explicitly
  logged as `[DRY-RUN-POSITION]`. Without this check, the bot would try to
  sell assets that were never bought.
- **Real positions are never closed in simulation during dry run:** the
  mirror image of the above. If the bot runs with
  `GRID_BOT_ENABLE_TRADING=false` while real positions (`dry_run: false`)
  are open in the ledger, such a position is neither sold nor booked as
  sold when its target is reached. It stays open, its level stays
  occupied, and the bot reports `[GRID-VERKAUF-GESPERRT]` (Telegram once
  per position and process run). Until 25.09.2026, proceeds were invented
  here from `quantity * price` and the position was closed, although the
  BTC was still on the exchange.
- **A failed real sale does not close the position:**
  `place_market_sell()` returns `None` in two completely different cases
  – in dry run AND on a real API error. The two are distinguished: on a
  real error, **no** proceeds are invented from `quantity * price`; the
  position stays **open** in the ledger (`[GRID-VERKAUF-FEHLGESCHLAGEN]`
  in the log and via Telegram). After an **unambiguous** rejection, the
  next cycle automatically retries the sale, since its sell target is
  still reached. If the outcome is **unclear** (pending entry still
  present), no new sale is made (`[GRID-VERKAUF-UNGEKLAERT]`, sale
  unresolved) until the reconciliation at the start of a cycle has
  resolved it: executed → position closed with exactly this order; no
  effect → regular sale. Likewise, a level with an unresolved purchase
  counts as occupied. Unlike with the trend bot, no protection has to be
  restored here – the grid bot never places an exchange-side stop order
  and accordingly does not cancel one before a sale either. The Telegram
  message comes only once per position per process run (otherwise every
  5 minutes); every failure goes to the log.
- **Telegram notifications** (if configured, see README section 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (with the
  realised profit/loss of this position), `[GRID-VERKAUF-FEHLGESCHLAGEN]`,
  `[GRID-VERKAUF-GESPERRT]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`,
  `[GRID-DOPPELVERKAUF]` (since 27.09.2026, see 7.1).
- **Rate limit for cycle errors:** a failed cycle reports `[GRID-FEHLER]`
  via Telegram only on the first occurrence of its error type (exception
  class). Further failures of the same kind only go to the log until a
  cycle has succeeded again – then the block is lifted. A new error type
  in the middle of a disruption is reported immediately. Previously, a
  longer disruption produced twelve identical messages per hour.

#### Backtest

```bash
python -m dca_bot.grid_backtest
```

Runs over the same three reference periods as the trend backtest (2022
bear market, 2023 recovery, 2021 sideways/consolidation), on hourly
candles (a compromise – the live bot checks every few minutes, but daily
candles would make most grid crossings invisible).

**Parameters** (since 28.09.2026, E6 in 6g „Symbolbindung“): pair, range,
spacing and amount come from the same variables as for the bot, i.e.
`GRID_SYMBOL`, `GRID_LOWER_LIMIT`, `GRID_UPPER_LIMIT`, `GRID_SPACING_PCT`
and `GRID_AMOUNT_PER_LEVEL` from the environment or `.env`.
`GRID_STOP_LOSS_PCT` is deliberately not read; `--stop-loss-pct` (default
15) continues to apply instead. Precedence: command line, variable,
standard. An empty variable counts as not set. The standard is the values
section 6 was calculated with (BTCUSDT, 70.000 to 90.000, 1,5 %, 15). It is
deliberately kept in a constant of its own (`DOCUMENTED_SYMBOL`) and is
not tied to the bots' default. The report begins with „Verwendete Werte“
(values used) and names the origin of each value („aus GRID_LOWER_LIMIT“
– from GRID_LOWER_LIMIT, „Standard, GRID_LOWER_LIMIT nicht gesetzt“ –
standard, GRID_LOWER_LIMIT not set, or „Kommandozeile“ – command line).
**Caution:** on a machine with a `.env` containing grid values, the
backtest calculates with those values. Anyone wanting to reproduce the
figures from section 6 should pass the values on the command line. The
other three backtests take, in the same way, only their bot's pair
(`DCA_SYMBOL`, `TREND_SYMBOL`, `ALLOCATOR_SYMBOL`).

If candles are missing from the fetched data, or the data only starts
after the requested beginning (pair listed later),
`fetch_historical_klines()` warns with `[KERZEN-LUECKE]` (candle gap, E7).
This is only a warning; the calculation runs across the gap as if the
period had not existed. The same function feeds the live warm-up of the
trend bot and the allocator, so the warning can also appear during
operation there.

**Important difference from DCA/Trend:** `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT`
are not a scale-invariant value but an absolute price range, coupled to
today's price level. Tested against the historical test periods (BTC much
lower back then), the unchanged live range would immediately lie outside
the price -> 0 trades, immediate trend-break stop-loss. The backtest
therefore shows two results per period by default: the literal one (with
the values used, see above) and a second run, clearly marked as
"ANALYSE, NICHT Live-Verhalten" (analysis, NOT live behaviour), in which
the range is scaled symmetrically around the actual starting price of the
respective period (same width ratio/spacing as live). See section 6 for
the full results.

### 7.3 Trend-following bot

EMA crossover strategy on daily candles with a trend-strength filter,
long-only (spot, no shorting). See section 5 for the research:
trend following is the academically best-supported alpha strategy (Liu &
Tsyvinski, Gbadebo); the main risks are overfitting and momentum crashes.

**Before the first dry run, the strategy was validated by backtest across
three historical market phases** (`python -m dca_bot.trend_backtest`,
code in `trend_backtest.py`) – see section 6 for the results and their
honest interpretation (protects in a bear market; without a periodic
manual stop-loss reset it misses part of the return in a bull market).

#### Core logic

- **Signal**: an EMA crossover alone is not enough – the gap between the
  fast and slow EMA must grow to at least `TREND_MIN_GAP_PCT` before the
  signal counts as confirmed (confirmation logic instead of ADX – simpler
  and more robust to verify, see `trend_signals.py`). This filters out
  whipsaws where the price crosses back shortly after the crossover.
- **Entry/exit**: long on a confirmed upward signal; exit on a confirmed
  signal reversal OR when the stop-loss is reached, whichever comes first
  (the stop-loss has priority if both occur at once). No shorting – on a
  confirmed downward signal without an open position, nothing happens.
- **The same decision logic** (`TrendSignalGenerator`, `decide_action`,
  `is_stop_loss_hit` from `trend_signals.py`) is imported by the backtest
  AND the live strategy – no duplicate implementation that could drift
  apart unnoticed.

#### Safety mechanisms (independent of DCA/Grid)

- **Dry run by default**, analogous to DCA/Grid.
- **Kill switch**: own file (`TREND_KILL_SWITCH_FILE`, default
  `STOP_TREND`) and own env variable (`TREND_BOT_HALT`) – independent of
  DCA/Grid.
- **Fixed stop-loss per trade** (`TREND_STOP_LOSS_PCT`, default 10% below
  the entry price): closes the position and then pauses new entries.
  Latched as with DCA/Grid: no automatic reset; manually with
  `python -m dca_bot.reset_trend_stop_loss` or by deleting the file under
  `TREND_STOP_LOSS_STATE_FILE`. The backtest clearly shows the price of
  this – without a periodic manual reset, the strategy may miss a large
  part of a subsequent recovery.
  An **automatic** reset (recovery threshold + cooldown) was played
  through on 17.09.2026 as a pure backtest experiment
  (`python -m dca_bot.trend_backtest --analyze-auto-reset`, results in
  section 6i) and deliberately **not** implemented: across all three
  reference periods and 27 parameter combinations there was exactly one
  evaluable event, and no choice of parameters for a safety lock can be
  derived from n=1. The decision will be made with real data from the
  paper-trading phase – the same approach as for
  `TREND_STOP_LIMIT_OFFSET_PCT` (see "Real, exchange-side stop-loss"
  below).
- **Telegram notifications** (if configured, see README section 7):
  `[TREND-EINSTIEG]`/`[TREND-EINSTIEG DRY-RUN]`, `[TREND-AUSSTIEG]` (with
  realised profit/loss and exit reason),
  `[TREND-VERKAUF-FEHLGESCHLAGEN]`, `[TREND-AUSSTIEG-GESPERRT]`, `[TREND-STOP-LOSS]`,
  `[TREND-WARNUNG]`, `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`,
  `[TREND-NOTAUS]`, `[TREND-FEHLER]`, since 27.09.2026 also
  `[TREND-TEILFUELLUNG]` and `[TREND-DOPPELVERKAUF]`.

#### Real, exchange-side stop-loss

In addition to the software-internal stop-loss (see above), the bot
places a real `STOP_LOSS_LIMIT` sell order directly on the exchange with
every entry (`place_stop_loss_limit_sell` in `binance_client.py`). The
reason: the software-internal stop-loss only works as long as the bot
process is running – if the bot fails (crash, internet/power outage), an
open position without this mechanism is completely unprotected, however
far the price falls. The exchange-side order takes over the monitoring on
the exchange itself and works independently of the bot process.

- **Stop/limit price:** `stop_price = entry_price * (1 -
  TREND_STOP_LOSS_PCT/100)` (identical to the threshold of the internal
  stop-loss), `limit_price = stop_price * (1 -
  TREND_STOP_LIMIT_OFFSET_PCT/100)` (default 0,5%) – the gap prevents the
  order from being left unfilled in the order book during a fast price
  drop. For a real order, `entry_price` is the actual fill price of the
  purchase (`cummulativeQuoteQty / executedQty`), not the ticker queried
  shortly before – the same basis thus applies to the order on the
  exchange, the internal stop-loss and every later replacement order.
  Likewise, the stored exit price is the fill price of the sale.
- **Exit order on signal reversal or internal stop-loss trigger:** the bot
  ALWAYS first cancels the still-open stop-loss order before selling
  itself via market order – otherwise an orphaned sell order would remain
  on the exchange. A cancellation error (e.g. the order had already been
  filled in the meantime) is only logged, not treated as an error. The
  cancel response is evaluated for `executedQty`: if the order has
  already partially sold, this is booked and only the remainder is sold
  (see "Partially filled stop order" below).
- **Detection of an already filled stop order:** before every normal
  cycle decision, the bot queries the order status of the stored
  stop-loss order. If it is already `FILLED` (i.e. the exchange has
  already sold, e.g. during a downtime), the bot marks the position in the
  ledger as closed based on the actual order fill data, WITHOUT selling
  again itself. The stop-loss latch is set in the exit path itself and
  does **not** depend on whether the `[STOP-FILL-ANALYSE]` line can be
  written – otherwise an exit without a stored limit price would remain
  without a lock, and the bot could re-enter immediately.
- **A vanished stop order is detected and replaced:** if, according to the
  exchange, the order has ended without selling (`CANCELED`/`EXPIRED`/
  `REJECTED` without an executed quantity – e.g. cancelled manually), it
  no longer protects anything. The bot releases the assignment in the
  ledger and places a replacement within the same run. Without this, the
  dead order ID would have permanently blocked
  `_ensure_stop_loss_protection()`, which exits immediately for any
  existing ID – the position would have remained unprotected
  indefinitely. A **failed** status query explicitly does not count as
  "order gone": it says nothing about the order, and a network hang would
  otherwise trigger a second order for the same quantity.
- **Partially filled stop order** (`PARTIALLY_FILLED`): as long as it is
  alive, it is reported (log + Telegram), but deliberately **not**
  corrected – it can still fill completely, and any partial quantity
  recorded now would be wrong the next moment. With a 24-hour cycle, this
  is at most one reminder per day. If it **ends** with a partial fill
  (cancelled by the bot's own exit, expired, cancelled manually), the
  partial fill is booked and then only the **remainder** is sold, as a
  stop-loss exit with latch, even if the exit came from the signal
  (`[TREND-TEILFUELLUNG]`). The booking is purely additive:
  `partial_exit_qty`, `partial_exit_quote` (gross),
  `partial_exit_proceeds` (net) and `partial_exit_order_ids`, atomic and
  idempotent via the orderId. `quantity` and `quote_spent` remain the
  values of the entry; what is sold, protected and reconciled is the open
  quantity `open_quantity()` = `quantity − partial_exit_qty`.
  `realized_pnl` contains both parts, `exit_price` is the
  quantity-weighted average. Whether an ended order closed the position is
  decided by the quantity (tolerance one `stepSize`), not by the status
  `FILLED`. If the remainder is below the minimum volume, the position is
  closed and the remainder is reported as `dust_qty` (`[TREND-STAUB]`,
  trend dust, Telegram; quantity in the base asset, value and result in
  the quote asset of the pair from `exchangeInfo` – until 28.09.2026 this
  was hard-coded as "USDT"). Until 27.09.2026, the exit here sold the full
  quantity, on the shared account using another bot's holdings, and an
  ended order with a partial fill closed the whole position with the
  partial proceeds.
- **One single rule for order status:** the assessment of whether an order
  is filled, still active, ended or unreadable exists exactly once in the
  project (`order_lifecycle_state()` in `pending_orders.py`) and is used
  both by the cycle check and by the pending-orders path (7.1).
  Previously, both had their own, slightly different rules.
- **Reconciliation at bot startup:** before the first regular cycle runs,
  the bot reconciles a position open in the ledger against the actual
  order status at Binance and corrects the ledger immediately if the stop
  order was filled during the downtime – clearly logged as
  `[REKONZILIATION]`. Since the K2 fix, `reconcile_pending_orders()` (see
  7.1) runs before this, and this order is deliberate: an entry caught up
  there creates an open position **without** a stop-loss order, which
  this step immediately afterwards protects via
  `_ensure_stop_loss_protection()`. The other way round it would come to
  nothing – the position would not yet exist at its point in time.
- **Race condition between status check and cancellation:** if the stop
  order fills exactly between the last status query and the cancel call,
  the cancellation fails. The bot then does NOT rely on the cancel error
  code but queries the order status again: if it is actually `FILLED`,
  the position is closed based on the real fill data (no second sell
  attempt); if the status remains unclear despite the cancel failure
  (e.g. a real network error), the bot deliberately does NOT sell in this
  cycle (risk of a double order) and does not mark the position as closed
  either – a counter (`uncertain_cycles`) triggers a `[TREND-WARNUNG]`
  Telegram message after 3 consecutive unclear cycles (manual check
  recommended).
- **Fill analysis logging:** on every exit via a filled exchange stop
  order, the bot logs a separate, easy-to-find line
  `[STOP-FILL-ANALYSE] Limit: X, gefüllt bei: Y, Differenz: Z%` (limit X,
  filled at Y, difference Z%) – automatically collects real data on the
  reliability of `TREND_STOP_LIMIT_OFFSET_PCT` over the paper-trading
  phase, without this having to be tracked manually (see limitation
  below).
- **Dry-run positions are never really sold:** before every sale, the bot
  checks the `dry_run` flag of the ledger entry, not just the current
  trading mode. A position "bought" in dry run does not exist on the
  exchange at all – it therefore remains simulated even after switching
  to `TREND_BOT_ENABLE_TRADING=true` and is explicitly logged as
  `[DRY-RUN-POSITION]`.
- **Real positions are not touched in dry run:** the mirror image of the
  above. If the bot runs with `TREND_BOT_ENABLE_TRADING=false` while a
  real position is open, it does not execute a due exit (signal or
  internal stop-loss). It cancels no stop order, does not sell, books
  nothing and sets no latch. The position stays open, the stop order on
  the exchange continues to protect it, and the bot reports
  `[TREND-AUSSTIEG-GESPERRT]`. Until 25.09.2026, in this case it cancelled
  the real stop order and closed the position with invented proceeds. In
  addition, `cancel_order()` in the `TradingClient` raises an exception
  instead of cancelling while trading is disabled – a second safeguard in
  case a future caller forgets the check.
- **A failed real sale does not close the position:**
  `place_market_sell()` returns `None` in two completely different cases
  – in dry run AND on a real API error. The two are distinguished: on a
  real error, **no** proceeds are invented from `quantity * price`, the
  position stays **open** in the ledger and **no** stop-loss latch is set
  (after all, no exit took place). Logged as
  `[TREND-VERKAUF-FEHLGESCHLAGEN]`, additionally via Telegram. Since the
  exchange-side stop order has already been cancelled at this point (see
  exit order above), the still-open position would otherwise be
  unprotected – the bot therefore immediately places a **new** stop-loss
  order with the same threshold
  (`entry_price * (1 - TREND_STOP_LOSS_PCT/100)`) and stores it in the
  ledger. If that also fails, the doubly critical state (neither sold nor
  protected on the exchange) is logged as `ERROR` and reported via
  Telegram; the cancelled order ID is removed from the ledger instead of
  presenting a dead order as protection. This applies after an
  **unambiguous** rejection. If the outcome of the sale is **unclear**
  (pending entry still present), the bot polls up to three times at
  intervals of 20 s (`UNCLEAR_SELL_RECHECKS`,
  `UNCLEAR_SELL_RECHECK_SECONDS`): executed → book the exit; no effect or
  still unknown after 60 s → new stop order as above; still unclear →
  **no** new stop order (if the sale went through, it would be covered by
  another bot's holdings), instead `[TREND-WARNUNG]`
  „möglicherweise ungeschützt“ (possibly unprotected). Until the entry is
  resolved, there is no renewed exit for this trade
  (`[TREND-AUSSTIEG-UNGEKLAERT]`, exit unresolved) and no new stop order;
  the missing protection is counted and reported from 3 cycles on. An
  unresolved purchase blocks new entries.
- **Self-healing protection:** in every cycle in which an open, real
  position is NOT closed, as well as in the reconciliation step at bot
  startup, the bot checks whether a stop-loss order is stored at all –
  and otherwise places a new one (threshold as at entry, from
  `entry_price`). This closes both ways in which a position could
  otherwise remain permanently unprotected: the stop order already failed
  at entry, or a failed sale could not replace its previously cancelled
  protection and the exit reason then disappeared again (trend turns back
  to "up") – in both cases nothing would ever have placed an order again
  before. Success is logged as `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`;
  if it keeps failing, `unprotected_cycles` counts up and triggers a
  `[TREND-WARNUNG]` via Telegram after 3 consecutive cycles (same pattern
  as `uncertain_cycles`), with an all-clear as soon as the protection is
  back in place. Deliberately only AFTER the cycle's exit decisions: if
  the position is being closed anyway, a new order would have to be
  cancelled again immediately, and with a triggered stop-loss the price
  would already be below the stop threshold (the exchange would reject
  the order).
  **While trading is disabled**, no order is placed for a real position,
  but the missing protection is still counted and reported from 3 cycles
  on. The message about a vanished stop order then explicitly says that
  no replacement is possible. A position without a `dry_run` field gets no
  order, but `[TREND-POSITION-UNKLAR]` (position unclear).
- **Dry run** (`TREND_BOT_ENABLE_TRADING=false`): NO real stop order is
  placed, it is only logged ("[DRY-RUN] Würde Stop-Loss-Order
  platzieren..." – would place stop-loss order). The position then
  remains, as before, monitored exclusively software-internally – the same
  safety principle as for the entry order (no trading without opt-in).
- **Done (was: TODO before real money):** stop/limit prices used to be
  rounded only to 2 decimal places, not validated against the symbol's
  real `PRICE_FILTER` tick size. Since the K3 fix, both prices and the
  quantity are quantised against the actual `exchangeInfo` filters (see
  7.1) – the quantity additionally adjusted for the trading fee deducted
  on purchase; otherwise the stop order would be for a quantity that no
  longer exists and would be rejected by the exchange.
- **Known limitation: the `TREND_STOP_LIMIT_OFFSET_PCT` default (0,5%)
  is based on too small a historical sample** (backtest analysis across
  the three reference periods yielded only 2 simulated stop-loss exits
  in total, see 6f) – it will be checked during the months-long
  paper-trading phase using real fill data (see fill analysis logging
  above) before the value is finally confirmed for going live.

### 7.4 Capital allocator

Continuous shifting of capital between the DCA bot and the
trend-following bot depending on the current trend strength (EMA gap) –
**not** a trading bot of its own but a controlling auxiliary process. The
grid bot remains unaffected (it already has its own trend-break
stop-loss, see 7.2). The allocator **never** places orders itself – it
only calculates one number (the trend-following share between 0% and
100%) and writes it to its state file.

Configuration and startup: README sections 3.3 and 4.

#### Core logic

- **Trend strength**: reuses `TrendSignalGenerator` from
  `trend_signals.py` (with `min_gap_pct=0`, since the confirmation logic
  there is intended for binary entry/exit decisions – the allocator needs
  the raw, continuous EMA gap). Only a confirmed UPWARD direction counts
  as strength – the trend bot is long-only and would not be allocated any
  capital in a downtrend anyway.
- **Two cadences, deliberately decoupled** (security review item W9): the
  EMAs are fed with **exactly one daily closing price per calendar day** –
  identical to the backtest. `ALLOCATOR_INTERVAL_MINUTES`, on the other
  hand, only determines how often the process wakes up, republishes the
  state with a fresh timestamp and checks the kill switch. Background:
  `TrendSignalGenerator` is event-driven; every `feed()` advances the EMAs
  by **one period**. Previously, every 60-minute cycle fed in a spot
  ticker, i.e. 24 values per day into a calculation designed for 20/50
  **days** – the result was in effect an EMA(20h)/EMA(50h), a different
  indicator from the backtested one. The hourly cadence remains
  nonetheless: it is the sign of life on which the freshness check below
  depends. A daily interval would have stretched its threshold from three
  hours to three days.
- **Smoothing in days**: accordingly, `ALLOCATOR_SMOOTHING_PERIOD` only
  advances with the daily feed and is thus directly comparable with
  `--smoothing-period-days` in the backtest (default 3.0 there). After a
  downtime, missed days are caught up one by one, each against its own
  daily target – the result is the same as if the process had kept
  running.
- **Linear interpolation** between `ALLOCATOR_ZERO_ANCHOR_PCT` and
  `ALLOCATOR_FULL_ANCHOR_PCT`, clamped outside the anchors (no
  extrapolation).
- **Whipsaw protection through EMA smoothing of the allocation itself**
  (same formula as the price EMAs in `trend_signals.py`, applied here to
  the allocation percentage) – since with a continuous curve there is no
  fixed level to "confirm" as with discrete signals.
- **Additive integration, disabled by default**: DCA/Trend read the
  allocation only with explicit opt-in (see README 3.3) immediately before
  a NEW order; below 5 USDT the order is skipped instead of placing an
  economically meaningless mini order.
- **Freshness check of the allocation**: if the allocator process dies,
  the last calculated value would otherwise remain valid forever – with a
  frozen 100% Trend, the DCA bot would permanently have stopped buying
  altogether, without anything pointing to it. If `updated_at` is older
  than three times the allocator interval, DCA/Trend fall back to **100%
  DCA / 0% Trend** (the more conservative direction) and log a warning.
  The threshold comes from the state file itself: the allocator writes
  its `interval_minutes` along with it, instead of configuring the same
  number a second time on the consumer side.
- **Telegram notification** (if configured) only on a shift of at least
  `ALLOCATOR_NOTIFY_THRESHOLD_PP` percentage points since the last
  message – prevents spam from small, continuous fluctuations.

#### Safety mechanisms (independent of DCA/Grid/Trend)

- **Kill switch**: own file (`ALLOCATOR_KILL_SWITCH_FILE`, default
  `STOP_ALLOCATOR`) and own env variable (`ALLOCATOR_HALT`) – independent
  of DCA/Grid/Trend. The allocator never places orders anyway; here the
  kill switch only stops the calculation/state update.
- **Telegram notifications**: `[ALLOCATION-UPDATE]` (on a significant
  shift), `[ALLOCATOR-NOTAUS]`, `[ALLOCATOR-FEHLER]`. For
  `[ALLOCATOR-FEHLER]` the same rate limit applies as for the grid bot
  (see 7.2): one message per error type until a cycle has succeeded
  again.

### 7.5 Position audit

Invocation: `python -m dca_bot.audit_positions` (see README section 8.1).

Intended as an overview before a paused bot is re-enabled or
`*_BOT_ENABLE_TRADING` is changed – then it is visible at a glance which
open positions actually exist on the exchange (`ECHT`, real) and which
were only simulated (`DRY-RUN`, never really sold, see 7.2/7.3). The DCA
section additionally shows quantity, capital invested and average entry
price – the bot never sells, so the sum of all its real purchases *is*
its holdings.

Paths come from `DCA_BOT_STATE_FILE`/`GRID_STATE_FILE`/
`TREND_STATE_FILE` or the usual defaults, alternatively via
`--dca-file` / `--grid-file` / `--trend-file`.

For each ledger, the script names the pairs occurring in it, e.g.
`Paare im Ledger: BTCUSDT: 12 (davon 12 ohne Feld, gelten als BTCUSDT)`
(pairs in the ledger: BTCUSDT: 12, of which 12 without field, treated as
BTCUSDT). Entries without a `symbol` field date from before the symbol
binding and are treated as BTCUSDT (7.1). If a ledger contains a pair
other than the configured one, an `ACHTUNG` (warning) appears below it
with a pointer to `python -m dca_bot.symbol_guard --report`, because the
bot will not start like this.

#### Cross-bot account reconciliation

If Binance credentials are present, the script appends a second part: it
queries the **actual** account balance and the open orders and compares
them with the **sum** of what all three ledgers carry as open, per base
asset and across all pairs.

```
==============================================================================
KONTOABGLEICH BTC (BTCUSDT: dca, grid, trend) - alle Bots gegen den Bestand
==============================================================================

Bot      Paar          laut Ledger offen  Hinweis
------------------------------------------------------------------------------
dca      BTCUSDT              0.00780000
grid     BTCUSDT              0.00116000  2 Dry-Run (zählt nicht)
trend    BTCUSDT              0.00019505
------------------------------------------------------------------------------
SUMME                         0.00915505
```

(Program output, shown as emitted: account reconciliation BTC – all bots
against the holdings; columns bot, pair, open according to ledger, note;
"2 Dry-Run (zählt nicht)" = 2 dry run, not counted; SUMME = total.)

This is deliberately **not** a feature of any bot but only of this tool.
Each bot keeps its own ledger and must not read anyone else's – this
separation is a fundamental principle of the project. But it also means
that none of them can answer the decisive question: does the sum of all
three actually fit on the one shared account? In each bot, the
`balance_guard` only checks whether that bot's *own* claim would still be
covered on its own – a check without false alarms which, in return, does
not see exactly the case in which only the sum becomes too large. A purely
reading tool may look at everything and is therefore the right place for
this.

Further properties:

- **Without API keys, only this second part is skipped**, with a message
  saying what is missing – the ledger part keeps running. The previous
  promise "needs no API keys" therefore still holds. With `--offline` the
  reconciliation can be switched off even when keys are present.
- **The client structurally cannot place orders:** it is built without a
  pending-orders file, and the `place_*` methods actively reject exactly
  this state (see `binance_client.py`). The read-only promise therefore
  does not depend on programming discipline.
- **The comparison is against `free + locked`**, not just the free
  balance: a quantity in an open sell order still exists, it just isn't
  sellable at the moment. The locked quantity is additionally broken down
  by originator (via the clientOrderId prefix from the K2 fix), including
  a separate entry for foreign orders or orders placed manually via the
  exchange interface.
- **Grouped by base asset, not by symbol** (since 28.09.2026, symbol
  binding in 6g). Each ledger yields one claim per pair that occurs open
  in it; which pair an entry has is stated in the entry itself. The
  claims are then aggregated by the base asset of their pair from
  `exchangeInfo`. Reason: BTCUSDT and BTCEUR trade the same BTC on the
  same account. Separated by symbol, DCA on BTCUSDT (0,3 BTC) and Grid on
  BTCEUR (0,2 BTC) with 0,4 BTC in the account would each have looked
  covered; the shortfall of 0,1 BTC would have remained invisible. The
  balance is queried once per base asset, the open orders from all pairs
  in the group. Different base assets remain separate; a sum across them
  would be meaningless. In the normal case (all three on the same pair)
  there is exactly one group.
- **An incomplete reconciliation says so.** If the trading rules of a
  pair cannot be retrieved, its claims are missing from the sum. This is
  then shown as `ACHTUNG: … er ist UNVOLLSTÄNDIG` (warning: … it is
  INCOMPLETE) above the reconciliation, so that an „In Ordnung“ (OK) is
  not based on a sum that is too small.
- **A surplus is not a finding.** If the account holds more than the
  ledgers claim, this can be manual holdings or a legacy. Only the other
  direction is reported as a problem – and then with the explicit advice
  **not** to adjust the ledger files blindly before it has been clarified
  which side is right.
- The tolerance comes from the same `balance_guard` that the bots also
  use for their decisions – two separate tolerances for the same question
  would be the sure way to an audit that contradicts a bot.

#### Looking up orders (`check_orders.py`, since 27.09.2026)

The counterpart to the audit for a single order: `python -m
dca_bot.check_orders --client-order-id <id>` (README 8.4). Binance only
finds an order under the symbol under which it was placed; under any
other it responds with −2013, as if it did not exist. The search
therefore runs in this order (since 28.09.2026, symbol binding in 6g):
first under the pair under which the bot's own bookkeeping carries the
order (pending entry or ledger entry, legacy entries without the field as
BTCUSDT), then under the bot's configured pair, revealed by the prefix of
the clientOrderId, then under all other configured pairs. With
`--symbol <pair>` only that pair is searched. Until 28.09.2026, with a
known prefix only the bot's current pair was searched, so an order from
before a pair switch counted as "never accepted".

The lookup uses `get_order_by_client_id()` and the assessment
`order_lifecycle_state()`, i.e. the same rules by which the bot itself
decides. A hit is decisive. If one of the queries failed, the result is
„keine Aussage“ (no statement). The script only says „nie angenommen“
(never accepted) if every query returned −2013 **and** the authoritative
pair was among them, i.e. the one from `--symbol` or from the bot's own
bookkeeping. Without such a pair, −2013 only means "not found under these
pairs", with the advice to search again with `--symbol` if necessary.
In addition, the reconciliation with the bot's own bookkeeping: is the ID
in the bot's pending file, is it in the ledger (`client_order_id`,
`sell_client_order_id`, `exit_client_order_id`, for the trend stop order
`stop_loss_order_id` via the orderId)? Without arguments, the script
shows, per symbol, the price, balance (base and quote asset from
`exchangeInfo`) and the latest orders with clientOrderId and bot; this is
also the connection test. It uses the audit's client
(`_build_read_only_client()`) and thus structurally cannot place orders.

### 7.6 Tests

What the individual test files check is described with the respective
fixes in 6f, 6g and 6i. Only what is missing there is described here:

`test_startup_balance_check.py` and `test_audit_positions.py` cover the
second stage of the improvement proposals: the consistency check at bot
startup for all three bots (including the proof that no API call at all
is made without a real open quantity, and that the trend bot's own
stop-loss order does not trigger a false alarm – with a counter-check
using the same order without a bot prefix), as well as the cross-bot
account reconciliation in the position audit. The wiring in all three
`main*.py` has its own test; it reads the source code of the respective
`main()` instead of executing it, and thereby covers exactly the error
that is realistic here – three almost identical call sites, one of which
gets forgotten later.

`test_shared_account.py` (since 27.09.2026) is the only test file that
models the **shared account**: a real `TradingClient` and real strategies
on top of a `FakeExchange`, which replaces the raw python-binance client
and handles coverage, cancel semantics, minimum volume and network errors
like Binance. An ownership invariant per bot is checked, independently of
the code path (details in 6g, „Systemcheck vom 27.09.2026“). The other
fakes still start with plenty of free balance – new sell paths should
therefore also be tested here.

The whole suite: `python -m unittest discover -s tests -t .`

---

*Living project document, in two files since 29.09.2026. Here: the current state with the open items and section 7 (technical reference), both corrected directly, as well as the log from 29.09.2026, which, like every log, only receives dated notes. In `trading-bot-projekt-archiv.md`: research, planning and the chronological log up to 28.09.2026 (sections 1–6i), moved unchanged. Created on 13.09.2026 by merging two versions maintained in parallel (chat artifact + local Claude Code continuation).*
