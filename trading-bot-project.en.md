# Trading Bot Project: Planning, Progress Log and Technical Reference

> English translation of `trading-bot-projekt.md`, kept in sync with it
> (every change lands in both files in the same commit). If they ever
> differ, the German original is authoritative.
> The archive `trading-bot-projekt-archiv.md` exists in German only. Quoted
> titles of archive sections (e.g. 6g „Symbolbindung“) are left in German so
> they can be found there. Log tags and messages (e.g. `[ORDER-UNKLAR]`) are
> quoted exactly as the code emits them. Dates use the original DD.MM.YYYY
> format; decimal commas in amounts are kept as in the original.

**As of:** 17 October 2026
**Status:** Testnet operation, no live money. The security review (K1–K5, W1–W18, infrastructure) has been complete since 16.09. The home server has in fact been running as the complete system since 16.09.2026, with all four components and active allocator opt-in for DCA and Trend. The current trading status there was verified on 25.09.2026 (see 6h). The VPS has been closed since 07.10.2026 (services stopped, access removed, contract cancelled for 12.10.), the VPS data will not be evaluated, and the formal cutover on 05.10. with a snapshot step is dropped (see log 07.10.2026). The test phase has been extended to approx. 2–3 months, i.e. until roughly mid-November to mid-December 2026. Since the review, several find-and-fix series have been completed: the improvement proposals (6i, 17.09.), the dry-run amounts (22.09.), the code review of 25.09. and the system check of 27.09. with K-A/K-B and W-A to W-G (all 6g). On 16.10. a finding from operations was added: market orders that the exchange had ended without execution were in the grid ledger as positions with quantity 0 (fix round 1, see log 16.10.2026). On 17.10. the dry-run trend position of 15.09. was closed; since then the first real trend position has been running with a stop order on the exchange (see log 17.10.2026). The technical reference for the current state is in section 7.

---

*Older, completed history (sections 1–6i: research, planning and the chronological log up to 28.09.2026) is in `trading-bot-projekt-archiv.md`, unchanged, and only needs to be read when required, e.g. for a question about the original choice of strategy. References such as „siehe 6g“ ("see 6g") in code and docs mean the sections there. What is still open from it today is summarised in the section "Current status and open items".*

---

## Current status and open items

*As of 17.10.2026 for deploy status, preconditions, evaluation of the test phase and the forced disconnection (operations), 07.10.2026 for VPS and dates, other details as of 29.09.2026. Like section 7, this section describes the current state and is corrected directly. The derivation is in the archive (`trading-bot-projekt-archiv.md`) in each case; section numbers and headings are unchanged there.*

### Operations

- **Home server** (complete system since 16.09.2026): all four bots as systemd services on the testnet. DCA, Grid and Trend trade with real testnet orders (`*_BOT_ENABLE_TRADING=true`, verified 25.09.), the allocator opt-in for DCA and Trend is active. `GRID_AMOUNT_PER_LEVEL` = 9,38, maximum capital commitment approx. 150,08. Details: archive 6e, 6h, 6g „W16 umgesetzt“.
- **VPS:** closed since 07.10.2026. The three bot services (dca-bot, grid-bot, trend-bot) are stopped and disabled, `.env` and archive file on the VPS are deleted, the Claude Code deploy key (claude-code-vps-deploy) is removed from `authorized_keys`, and so is the VPS entry from `known_hosts` on the local machine. There is no evaluation of the VPS data and no snapshot was kept. Details: log 07.10.2026.
- **Pair:** on the testnet BTCUSDT; all "€" amounts there are USDT. For real money, BTCEUR will be used (decision 28.09.2026). Details: archive 5b (note 28.09.), 6g „Symbolbindung“.
- **Forced disconnection:** measured from the log lines „Unerwarteter Fehler im Grid-Zyklus“ (unexpected error in the grid cycle) (UTC): 26.09. 00:38, 30.09. 00:33, 02.10. 00:31, 03.10. 00:31, 04.10. 00:29, 05.10. 00:27:02, 07.10. 00:26:52, 08.10. 00:24:25, 09.10. 00:21:52, 10.10. 00:22:50, 12.10. 00:19:06, 13.10. 00:20:09, 14.10. 00:16:22, 15.10. 00:18:10, 16.10. 00:14:31, 17.10. 00:13:36. From 05.10. on, each value is the first such line of the night, up to 16.10. queried by Elias on 16.10.2026. The value of 17.10. comes from the night check of 17.10.2026 (only such line of the night, first night under `76f261b`). On 06.10. and 11.10. there was no such line (reason not checked). Measured drift roughly 1,1 minutes per day forward (00:27 on 05.10. to 00:14 on 16.10.). The line shows the first affected cycle; the disconnection itself began up to five minutes earlier. There is only one line per night, so the disconnection presumably lasts less than about five minutes (inferred from the number of lines, not measured). Blocked window for interventions on the server: uniformly 23:50 to 00:30 UTC. Rationale: with a drift of 1,1 minutes per day, the error line reaches 00:05 UTC around 25.10., the start of the disconnection (up to five minutes earlier) already around 20.10. The window covers the line until about early November. This is an extrapolation of the measured drift, not a measurement. Measure again by 25.10.2026 at the latest (command: `journalctl -u grid-bot --since <date> | grep 'Unerwarteter Fehler im Grid-Zyklus'`) and then set the window according to the actual situation.

### Deploy status

- Deployed: `76f261b` on the home server on 16.10.2026. Grid bot restarted at 14:32 UTC, DCA, Trend and allocator at 14:40 UTC, all four with „Code-Version: 76f261b“, symbol checks „passt“ (matches), holdings reconciliation OK. Compared with the previous state `980f3c3` (deployed 29.09.2026, with W-C to W-G including the addendum and the symbol binding), the tool `close_dry_run_trend` (applied on 17.10.2026) and the fix of 16.10.2026 for market orders without execution, including the tool `remove_unfilled_grid_positions` (applied on 16.10.2026), now also run there. Procedure and result: log 16.10.2026, "Cleanup and deploy"; rollback to `980f3c3` there under "Rollback". On master since then only docs. At every deploy, after the pull and before the restart: `python -m dca_bot.symbol_guard --report`.
- From now on, deploys are recorded **here**, as `Deployed: <hash> auf Homeserver am <Datum>`. This replaces the note of 29.09.2026 in archive 6g. Details on rolling back to the old code: archive 6g „Symbolbindung“.

### Dates

- **12.10.2026, end of VPS contract** (Contabo Cloud VPS 4 (2026), cancelled for 12.10.2026, according to the customer area billed until then, no additional items): no action needed any more.
- **Test phase** on the home server until roughly mid-November to mid-December 2026. Details: archive 6h.

### Preconditions for real capital (300 €: 150 € Grid, 150 € allocator pot)

1. **Position sizes:** still open are `DCA_QUOTE_AMOUNT`, `TREND_AMOUNT_PER_TRADE`, grid range and `GRID_SPACING_PCT`. When switching pairs, all amounts and the range must be set anew in euros. Details: archive 5b, 6d item 3.
2. **Data basis for `TREND_STOP_LIMIT_OFFSET_PCT`**, so far n = 2 simulated exits. **Status: trend procedure carried out on 17.10.2026, real entry with stop order, no fill data yet.** The dry-run position of 15.09. has been closed with `python -m dca_bot.close_dry_run_trend` as `manual_close`, without the latch. Since then the first real trend position (`bd1c3457-…`, entry 81.726,36, quantity 0.00018 BTC) has been running with a stop order on the exchange (orderId 3807835, stop 73.553,72, limit 73.185,95, status `NEW`). Calibration data only arises once this stop order is filled on the exchange (line `[STOP-FILL-ANALYSE]`). If the position closes via the stop-loss, the latch blocks new entries until the manual reset (`python -m dca_bot.reset_trend_stop_loss`). Details: archive 6f, 6h „Trend-Bot: Die Kalibrierungsdaten fließen noch nicht“, log 17.10.2026.
   Trend procedure (procedure: log 07.10.2026 with addendum of 16.10.2026): carried out on 17.10.2026, result in log 17.10.2026. As a data basis for the offset, however, the testnet is of little use: according to the evaluation of the public candles, in about 4 % of hours it shows a low more than 10 % below the mainnet. A real stop order there will probably be triggered by an outlier, not by the market. If an outlier triggers the stop order, that is a technology test of the chain (stop fill, booking, latch, manual reset), not a calibration value. Filled stop orders on the testnet prove the technology, not the offset.
3. **Final security review** shortly before going live. Details: archive 6d, 6h.
4. **Switching the pair to BTCEUR**, not yet planned: all four `*_SYMBOL`, grid range and amounts in euros, fresh ledgers or deliberately carried-over existing holdings. Also open are the dashboard app and the pilot. It is not verified whether Binance responds with −2013 to a query under the wrong symbol; this can only be checked in the pilot. Details: archive 6g „Symbolbindung“, 6h.
5. **"Pay fees with BNB" switched off.** Details: archive 6h.
6. **Sub-accounts per bot:** decide deliberately before going live, not a hard precondition. If the decision is in favour, code is needed (separate keys per bot, audit across several accounts) before going live. Details: archive 6h (addendum 29.09.), 6g „Systemcheck vom 27.09.2026“.
7. **The buy path checks the execution status:** the response to every market order is assessed against status and `executedQty` before booking, and the ledgers reject real entries without quantity or spend (A1/A3, deployed on the home server since 16.10.2026). Open: fulfilled only once it is proven on the server that an order without execution appears in the journal as `[ORDER-OHNE-AUSFUEHRUNG]` and not as a purchase. The proof in live operation arises as soon as the testnet again delivers a market order without execution. In the trend entry of 17.10.2026 the buy path assessed the status `FILLED` correctly; a case without execution has still not occurred. Details: log 16.10.2026, log 17.10.2026.
8. **A partial fill on a sale is booked correctly (round 2):** until then, the bot books a market sale that was only partially executed over the full quantity and only reports it loudly (`[GRID-TEILFUELLUNG-UNGEBUCHT]`/`[TREND-TEILFUELLUNG-UNGEBUCHT]`). Details: log 16.10.2026.

### Deliberately deferred or earmarked

- **W14, Grid without exchange-side stop-loss:** a separate architecture decision between one combined stop order and n individual stop orders. Until then, the trend-break stop only blocks purchases, and capital commitment is capped by levels × amount. Details: archive 6g „W14“.
- **Automatic stop-loss reset (item 16):** played through in the backtest, n = 1. The decision will be made with real data; until then the reset is manual. Details: archive 6i „Punkt 16 als Backtest-Experiment“.
- **Item 13 (shared bot runtime) and F2 (kill switch pauses instead of terminating):** deferred, no fixed date (the original cutover on 05.10. is dropped). Precondition: no open deploys and a quiet week, because both items touch all four entry points. Details: archive 6i „Offen aus der Liste“, 6g „W-F“.
- **DCA portfolio stop-loss in the backtests:** is not modelled, so the DCA figures in 5a and 6 overestimate the capital deployed in a bear market. Details: archive 6g „W-G“.
- **Archiving the ledger files:** no acute need, only together with the dashboard app. Details: archive 6g „Vorgemerkt: langfristiges Datenwachstum“.
- **Retroactively correcting the fill price of old ledger entries:** earmarked for the tax export. Entries from before K2 have no `clientOrderId`. Details: archive 6g „Priorität 4“.
- **Item 15 (SQLite):** still years away at today's data volume. Details: archive 6i.
- **Idea (Elias, 16.10.2026): capital budget as a fixed share of the account value, tested on the testnet.** Explicitly a test phase on the Binance testnet with test funds, not real money (quote currency there USDT). Instead of a fixed amount per order, the bots are assigned a fixed share of the account value (example from Elias: 30 %; at 10.000 that would be 3.000, at 11.000 correspondingly 3.300). If the account grows through monthly deposits, the bots' budget grows with it. This is to be tested for roughly half a year with simulated monthly top-ups of 1.000. This would be a new feature (today the amounts are fixed values in the `.env`), not merely raising settings. Status: only recorded, not decided, not planned, no assignment. Open:
  - What counts as account value is open: on 16.10.2026, according to `check_orders`, the testnet account held 9.999,10 USDT and 1,00011 BTC (roughly 92.000 USDT in total; the BTC does not belong to the bots).
  - There are no deposits on the testnet; the top-up would have to be simulated.
  - Open beforehand is round 2 (booking a partial fill on sale, precondition 8). The trend procedure was carried out on 17.10.2026.
  - The returns from the testnet remain meaningless because of the ticker outliers; it would be about the mechanics.

### For evaluating the test phase

- In the home server ledgers of DCA and Trend, dry-run and real entries sit side by side; the evaluation must separate them by `dry_run`. The grid ledger is real throughout. Details: archive 6h „Umstellung auf echte Orders“.
- The trend dry-run position of 15.09. has been closed as `manual_close` since 17.10.2026. Its simulated `realized_pnl` (+0,93062751) never counts as a result. The trend card of the dashboard app counts the entry as a closed trade, not as a result (analysis of 07.10.2026). Details: log 07.10.2026, log 17.10.2026.
- There is no VPS vs. home server comparison: the VPS data will not be evaluated (decision 07.10.2026, reasons in the log). Details: archive 6g „Beobachtung zur Allocator-Wirkung“, 5a.
- The dry-run values of the VPS grid were corrected on 22.09. The `.pre-fix` copy is no longer needed, because the VPS data will not be evaluated. Details: archive 6g „Folgefund aus K3“.
- The position audit does not attribute dust (`dust_qty`) to any bot; it appears as a surplus. This applies to the trend bot since K-A and to dust on purchase (Grid and Trend) since 16.10.2026. Details: archive 6g „Systemcheck vom 27.09.2026“, log 16.10.2026.
- **Entries without holdings in the grid ledger:** eleven open positions with quantity 0 (levels 0 to 3 since 09.10., 4 to 10 since 11.10.2026) occupied their levels until the cleanup on 16.10.2026. The grid bot did not buy there, which additionally distorts the grid result from 09.10. to 16.10. The copy `grid_positions.json.pre-remove-20261016T143039Z` on the server still contains them. A CSV export created before the cleanup lists them as BUY rows with quantity 0 and should be generated again. Details: log 16.10.2026.
- **Ticker outliers on the testnet:** testnet profits are distorted by them and are not suitable for return estimates. A thin order book is suspected as the cause; this was not measured. Example 02.10.2026: of the realised grid result of 8,65 USDT (evaluation of 06.10.), 6,31 USDT fall on this single day, of which 6,15 USDT on six levels (8 to 13). On 02.10. they were bought between 13:30:13 and 13:30:16 UTC at 77.809 to 79.480 USDT and sold between 13:35:17 and 13:35:30 UTC at 86.928 to 86.962 USDT, 0,82 to 1,09 USDT per level, whereas normal cycles yield 0,14 to 0,21 USDT. The mainnet hourly candle of 13:00 UTC had its low at 86.465,72, the testnet candle at 75.745,57; the mainnet daily low was 83.888 (hourly candles, 18:00 UTC). All six purchase prices are below the mainnet daily low. The check of all grid trades against the mainnet hourly candles was done on 16.10.2026 (Elias, purchase price more than 3 % below the low of the purchase hour, only sold real positions, approx. 41 days): of the realised grid result of **16,82 USDT**, **13,93 USDT** come from three outlier events (02.10. 13:30 UTC, levels 8 to 13, 6,15; 09.10. 05:17 UTC, levels 4 and 5, 3,56; 09.10. 07:03 UTC, levels 7 to 10, 4,23; the rounded event sums add up to 13,94, the exact sum is 13,93), roughly 2,9 USDT from normal operation (approximation: 16,82 minus 13,93). For comparison, the status of 06.10.: 6,15 of 8,65 USDT. Details: log 16.10.2026. Statements about the strategy rest on the backtests (mainnet candles); the testnet mainly proves the technology. The real trend position of 17.10.2026 (stop order 3807835) and the stop-offset calibration also depend on the same ticker: there, an outlier could produce entries or stop-loss triggers that would not exist on the real market. Details: log 06.10.2026.

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

**Addendum 16.10.2026:** The 6,15 of 8,65 USDT stated above were incomplete. On 16.10.2026 Elias checked all sold real grid positions of the last approx. 41 days by script against the mainnet hourly candles (purchase price more than 3 % below the mainnet low of the purchase hour). Two further events on 09.10.2026 (05:17 and 07:03 UTC) are proven. Together, 13,93 of the meanwhile 16,82 USDT realised come from outlier purchases; as above, 6,15 USDT of this fall on 02.10. Details: entry of 16.10.2026.

### VPS closed, no evaluation of the VPS data (07.10.2026)

The VPS was shut down on 07.10.2026. The three bot services (dca-bot, grid-bot, trend-bot) are stopped and disabled. On the VPS, `.env` and archive file were deleted, the Claude Code deploy key (claude-code-vps-deploy) was removed from `authorized_keys`, and the VPS entry was removed from `known_hosts` on the local machine. The contract (Contabo Cloud VPS 4 (2026)) is cancelled for 12.10.2026 and, according to the customer area, billed until 12.10.2026; there are no additional items.

**Decision:** There is no evaluation of the VPS data, and deliberately no snapshot was kept (pure testnet data). Reasons:

- Grid and Trend ran there in dry run. Their results depend on the testnet ticker, which had outliers on 02.10. (see the entry of 06.10.2026).
- There was no allocator on the VPS.
- The code version was `10ce096`.
- DCA never sells.

The stability test of 09.09. remains in `docs/test-reports/`.

**Consequences:** The formal cutover on 05.10. with a separate snapshot step is dropped. There is therefore also no VPS vs. home server comparison any more. The steps planned for it in the archive (cutover with snapshot, final `data/` snapshot at the end of the contract) are no longer intended. The section "Current status and open items" has been adjusted accordingly.

### Tool for closing the dry-run trend position (07.10.2026)

**Rationale:** The dry-run position of 15.09.2026 (`c0e153c1-…`, entry 76.960,01, `quote_spent` 15,0, `dry_run: true`, no `symbol` field, no stop order) occupies the only trend slot. As a result, there has never been a real trend entry, a real stop order or a real exit on the testnet. There is no take-profit; the position only closes on a confirmed downward signal or 10 % below the entry. According to the evaluation of the public candles, in about 4 % of hours the testnet shows a low more than 10 % below the mainnet. A real position will therefore probably soon be triggered by an outlier. This is intended as a technology test, not as calibration.

**Tool:** `python -m dca_bot.close_dry_run_trend`, report by default. `--apply` requires `--trade-id` and `--exit-price` and only writes when the trend bot is stopped (process lock, acquired before reading). Before writing, the copy `trend_ledger.json.pre-close-<timestamp>` is made; writing is atomic via `TrendLedger.record_exit()`, afterwards it is checked that only this one entry has changed. A second run changes nothing. Decisions:

- Exit price: mandatory argument `--exit-price` (mainnet price), no network access in the tool.
- `exit_reason`: new value `manual_close`. The field is not read in the bot (only `trend_strategy` writes it), nor in the position audit, the allocator, `check_orders` or the dashboard app; the backtests only evaluate their own trade log.
- `record_exit()` instead of raw dicts. The stop-loss latch is only created in `trend_strategy` and only on `stop_loss`; the tool imports neither the strategy nor `TrendStopLoss`.
- The simulated `realized_pnl` (quantity × exit price − `quote_spent`) never counts as a result: dashboard sums, PnL history and CSV export filter on `dry_run: false`, the position audit does not count dry run towards holdings. The only visible consequence: the trend card of the app counts one more closed trade, because it counts by status there.
- Refusal without writing if: the ledger is missing or unreadable, there is not exactly one open position, the position is not `dry_run: true`, one of the fields `client_order_id`, `stop_loss_order_id`, `exit_client_order_id` is set or partial fills are booked, `--trade-id` does not match, the pending file has entries or is unreadable, the stop-loss latch is active or the symbol check reports anything other than „passt“ (for the pending file, latch and allocator state, „nicht vorhanden“ is fine).

**What the bot does afterwards (checked in the code):** The first cycle runs directly at start. The EMAs are built from mainnet daily candles up to yesterday, plus the current testnet price. "up" means EMA20 above EMA50 with at least 1 % gap; a fresh crossover is not required. There is no cooldown and no rule against an entry on the same day. The amount is `TREND_AMOUNT_PER_TRADE` × the allocator's `trend_fraction`; below 5 USDT the entry is skipped. The stop order is at entry × 0,90, limit × 0,995. Its minimum notional is not checked beforehand: at prices around 85.000 it needs at least 7·10⁻⁵ BTC, i.e. about 6 USDT entry amount (`trend_fraction` from about 0,40 at 15 USDT). This is calculated, not verified on the testnet. Free USDT is not checked before the purchase.

**Deploy:** Since `980f3c3` only docs have changed on master, code only with this tool. Only the trend bot is restarted; DCA, Grid and allocator keep running.

**Tests:** `tests/test_close_dry_run_trend.py` with 40 tests (all refusals, normal case, report writes nothing, no latch, real position stays unchanged, lock, check after writing, end-to-end: after closing, the bot enters for real on "up" and places the stop order). Mutation probe: 31 mutations, all detected. The tests only ran on Windows; there `process_lock.py` locks with `msvcrt.locking`, on Linux with `fcntl.flock`. Step 6 of the procedure therefore proves the lock on the server.

**Procedure on the home server:**

1. Choose the time: not 00:20–00:35 UTC (forced disconnection), not 06:40–07:00 UTC (apt restarts).
2. `git status` clean, `git log -1` shows `980f3c3`, then `git pull`.
3. `python -m dca_bot.symbol_guard --report`: the trend bot must report „würde starten“.
4. `python -m dca_bot.close_dry_run_trend` (report): exactly one open position `c0e153c1-…`, dry run, no stop order, pending file empty, no latch, symbol check passes.
5. Look at `trend_fraction` and the timestamp in `data/allocator_state.json` (see minimum notional above), note the mainnet price.
6. Lock probe while the trend bot is still running, in the repo directory (same `.env` and thus the same lock file as the service): `python -m dca_bot.close_dry_run_trend --apply --trade-id <full ID> --exit-price <mainnet price>`. Expected: exit code 2 (`echo $?`), message „ABGEBROCHEN“, nothing written, no backup copy `trend_ledger.json.pre-close-*`.
7. `sudo systemctl stop trend-bot`
8. `python -m dca_bot.close_dry_run_trend --apply --trade-id <full ID> --exit-price <mainnet price>`
9. `python -m dca_bot.audit_positions`: trend without open position, no new discrepancy.
10. `python -m dca_bot.check_orders`: free USDT at least about 15.
11. `sudo systemctl start trend-bot`, then `journalctl -u trend-bot -f`: symbol check, price, allocator share and effective amount, then either `[TREND-EINSTIEG]` with the stop order placed and no `[TREND-FEHLER]`, or no entry because the signal is not "up".
12. After the first cycle, run `python -m dca_bot.audit_positions` again. Application and deploy are recorded here and under "Deploy status".

If an outlier then triggers the stop order, the bot closes with `stop_loss` and the latch takes effect. The next entry then requires `python -m dca_bot.reset_trend_stop_loss`.

**Addendum (16.10.2026): procedure checked against the current state.** The entry above stays unchanged. Since 16.10.2026, `76f261b` runs on the home server, and the tool (`2cd70f0`) is contained in it. `close_dry_run_trend.py`, `tests/test_close_dry_run_trend.py` (40 tests) and `TrendLedger.record_exit()` are unchanged since then. What has changed:

- **Paragraph "Deploy":** no longer applies. The tool is already on the server, a separate deploy is not needed. The trend bot is only stopped in step 7 and started in step 11.
- **Step 1:** blocked window now 00:05 to 00:35 UTC instead of 00:20–00:35 UTC (forced disconnection, see "Current status", "Operations"). The window 06:40–07:00 UTC (apt restarts) is carried over unchanged, but not re-checked.
- **Step 2:** `git log -1` shows `76f261b`, `git pull` only brings newer docs.
- **Step 10:** the threshold stays. Since the cleanup of 16.10.2026, grid levels 0 to 10 are free again, so the grid bot can buy there and commits USDT doing so. How much free USDT remains at the time of application is open; step 10 shows it.
- **Step 11:** with the fix of 16.10.2026, further possible outcomes are added: `[TREND-EINSTIEG]` with the addition „Teilfüllung“ (partial fill); `[TREND-STAUB]` if a partial fill is below the minimum notional (no stop order, no latch); `[ORDER-OHNE-AUSFUEHRUNG]` with `[TREND-FEHLER]` „nicht verbucht“ (not booked) for an entry without execution (slot stays free; this would at the same time be the proof for precondition 7); `[ORDER-UNKLAR]` and `[TREND-EINSTIEG-UNGEKLAERT]` for an unclear status (slot occupied until the next daily cycle). Details: log 16.10.2026, "Implemented, round 1".
- **Step 12:** only the application is recorded, in the log. A note under "Deploy status" is not needed, because no deploy takes place.
- **Paused status:** the pause (precondition 2, step 13 of the procedure of 16.10.2026) depended on the deploy of the fix and is therefore no longer needed. The procedure stays suspended until Elias releases it. Status: ready for release, not yet carried out.

Unchanged: steps 3, 6, 7, 8 and 9. Step 6 is still needed. The lock test of 16.10.2026 proves the lock on Linux only for the grid tool and the grid bot. The rule on the minimum notional still applies to a fully executed entry: the new dust rule (T2) only takes effect on a partial fill.

Not reliably assessed:
- **Step 4:** whether the dry-run position `c0e153c1-…` is still the only open trend position, without latch and with an empty pending file, has not been checked from here. Only the report shows this.
- **Step 5:** the minimum notional calculation (7·10⁻⁵ BTC, about 6 USDT at prices around 85.000) depends on the price and has not been recalculated.

**Note (16.10.2026, after measuring the forced disconnection):** for step 1, the blocked window is now 23:50 to 00:30 UTC instead of 00:05 to 00:35 UTC as in the addendum above. Measurements and rationale: "Current status", "Operations".

**Note (17.10.2026):** The procedure was carried out on 17.10.2026; the status "ready for release, not yet carried out" in the addendum above is therefore outdated. Result: entry of 17.10.2026.

### Market orders without execution booked as positions (16.10.2026)

**Finding from the home server.** The grid ledger contained eleven open, real entries without holdings: `quantity` 0, `quote_spent` 0, and the ticker of the cycle as purchase price (70.192,26 for all seven on 11.10.). Output of the query on the home server of 16.10.2026, supplemented by the order quantity according to the exchange:

| Level | `bought_at` (UTC) | Ledger `id` | `client_order_id` | Order quantity (BTC) |
|---|---|---|---|---|
| 0 | 2026-10-09T05:17:31 | `14f6af94-198f-47d0-91d0-33baf809d1d0` | `grid-33b3641be36f4e139d6c5fd3` | 0.00014000 |
| 1 | 2026-10-09T05:17:31 | `54918462-99c6-46dc-a0c9-10478d687e32` | `grid-21918cc10b2c4d7fa859380c` | 0.00014000 |
| 2 | 2026-10-09T05:17:32 | `c6564874-7359-4875-b4f2-8909599db89e` | `grid-1be308d2e7d14b0791bd1445` | 0.00014000 |
| 3 | 2026-10-09T05:17:33 | `f29b06f6-e113-47c8-b03c-8f4a9b0aa756` | `grid-4bdc0b39c3aa43088c0e82c2` | 0.00014000 |
| 4 | 2026-10-11T16:01:35 | `10418ef5-a18c-4241-adc5-8c9b8cdf3453` | `grid-f0f245ee4ac64a08bf933fae` | 0.00013000 |
| 5 | 2026-10-11T16:01:36 | `19a4550e-ecc1-45fb-834a-dc7a4cce1787` | `grid-752a27dc70224a708070cb37` | 0.00013000 |
| 6 | 2026-10-11T16:01:37 | `ed8c55fb-7c27-41f2-a7a8-1b7332014675` | `grid-d6a7e35b0665427bbd118d85` | 0.00013000 |
| 7 | 2026-10-11T16:01:38 | `7aab14a6-6bf3-48e0-8eeb-34d729fdc684` | `grid-5ac7a25d606446e4ba972cf8` | 0.00013000 |
| 8 | 2026-10-11T16:01:39 | `13f0fdee-b44c-4c7d-9f3b-17ec6d5ba9b3` | `grid-3932c321ec4f4907b6229765` | 0.00013000 |
| 9 | 2026-10-11T16:01:39 | `1a5f6c8a-88ee-4466-87f3-dd46b4bd870e` | `grid-c67242e66b0d440e8d20d89a` | 0.00013000 |
| 10 | 2026-10-11T16:01:40 | `c98bc132-506b-46db-a816-8d9b522a2019` | `grid-1fe9e148bbb041e5b74fa824` | 0.00013000 |

**Exchange check, done by hand** (Elias, 16.10.2026, `python -m dca_bot.check_orders --client-order-id <ID>` individually for all eleven IDs): status `EXPIRED`, executed 0.00000000 for all eleven. The four of 09.10.2026 were for 0.00014000 BTC each, the seven of 11.10.2026 for 0.00013000 BTC each. The exchange time of the orders of 11.10. is 16:01:35 to 16:01:40 UTC. For the four of 09.10., only `bought_at` from the ledger is available (05:17 UTC).

**Delimitation.** The real purchases of levels 4 to 10 **with** holdings come from the same minute on 09.10.2026 (05:17:43 to 05:17:57 UTC, quantity 0.00011 to 0.00014, spend 9,07 to 9,38, all `closed` by now). They do not belong to this group. On the server, the filter `status open, dry_run false, quantity 0, quote_spent 0` hits exactly the eleven: query (a) 11 rows, (b) both minutes 18 rows (11 without and 7 with holdings), (c) half-empty entries none. The journal of 11.10. matches: `[GRID-VERKAUF-FEHLGESCHLAGEN]` after „Verkaufsmenge … 0“ (sell quantity … 0) for the positions of levels 0 to 9 (`14f6af94` to `1a5f6c8a`). Level 10 (`c98bc132`) is missing there because its sell target had not been reached.

**Consequences until the cleanup** (derived from the code): levels 0 to 10 count as occupied, the grid bot does not buy there. Every 5-minute cycle attempts, for each of these positions whose target is reached, a sale over quantity 0, which aborts before reaching the exchange: per position one ERROR „Verkaufsmenge … 0“ and one WARNING `[GRID-VERKAUF-FEHLGESCHLAGEN]`, Telegram once per position and process run. With ten positions that is roughly 5.800 log lines per day. Position audit, holdings reconciliation and startup check see no error, because quantity 0 claims nothing. In the dashboard app the entries count as open, and the CSV export lists them as BUY rows with quantity 0.

**Cause.** `_place_order()` returned every response without an exception as an executed trade. Status and `executedQty` were only assessed after a connection or server error (query, reconciliation), not in the regular response path. With `EXPIRED` and 0, `average_fill_price()` took the ticker as a substitute, `net_executed_quantity()` yielded 0, `cummulativeQuoteQty` was 0, and all three bots booked this as a purchase, including `[GRID-KAUF]`. The reconciliation correctly assesses `EXPIRED` with 0 as "without effect", but never saw these entries: the pending entry had already been removed after `confirm_booked()`. No test modelled a market order without execution; all fakes filled completely.

**Source.** That a market order filled only partially ends with status `EXPIRED` applies according to the Binance Spot API Enums, checked on 16.10.2026 (Elias): https://developers.binance.com/docs/binance-spot-api-docs/enums (order status `EXPIRED`). The rule therefore applies to the Spot API in general, not only to the testnet. That a market order also ends this way with execution 0 has **only been observed on the testnet** (09.10. and 11.10.2026), **not documented** in the docs. For BTCEUR with real money, the fix is therefore precondition 7.

**Implemented, round 1** (plan and decisions of 16.10.2026):

- **A1, execution status in the regular response path** (`binance_client._settle_market_response`): the response to a market order is assessed before booking with the same rule as in the reconciliation (`classify_order_status`, i.e. `order_lifecycle_state`). Ended with execution, including `EXPIRED` with a partial quantity: as before, the pending entry stays until `confirm_booked()`. Ended without execution: pending entry removed, ERROR `[ORDER-OHNE-AUSFUEHRUNG] … Boerse meldet Status EXPIRED, ausgefuehrt 0 - kein Trade, nichts gebucht` (order without execution … exchange reports status EXPIRED, executed 0 – no trade, nothing booked), `None` to the strategy. The strategy reports once via Telegram (`[GRID-FEHLER]`, `[TREND-FEHLER]` or `[FEHLER]` with „nicht verbucht“, not booked), there is no `[GRID-KAUF]`, and the level or the trend slot stays free. Still active, no or unknown status: unclear, the entry stays, `[ORDER-UNKLAR]` with „Boerse meldet Status …“, and the locks from K-B apply until the reconciliation. It runs at the start of every cycle and at every startup, i.e. every 5 minutes for Grid and once a day for Trend. A trend entry with an unclear outcome therefore occupies the slot until the next daily cycle (`[TREND-EINSTIEG-UNGEKLAERT]`, no second purchase), and correspondingly longer if the order is still unresolved at the exchange then. The log texts explicitly separate this path from the path after a connection error. Stop orders do not go through this check (E1); a market response without a status field counts as unclear (E2). Evidence that market responses carry the field: `docs/test-reports/2026-09-09_dca-3tage-stabilitaetstest.log` (`'status': 'FILLED'`). The preliminary check in the procedure remains mandatory nonetheless.
- **A3, ledger guard** (`risk.require_plausible_entry`): `GridLedger.record_buy`, `TrendLedger.record_entry` and `TradeLedger.record` reject an entry not marked as dry run with quantity ≤ 0 or spend ≤ 0 (`ImplausibleLedgerEntry`, also for NaN). Only the new entry is checked; the eleven old ones block nothing until the cleanup. The exception is raised before `confirm_booked()`. The pending entry therefore stays, and the reconciliation queries again in the next cycle.
- **T2, partial fill on purchase:** the executed quantity is booked with the real spend, as before, now with the addition „Teilfüllung“ (partial fill) in `[GRID-KAUF]`, `[TREND-EINSTIEG]` and `[KAUF]`. If the purchased quantity is below the minimum volume (`order_utils.is_dust`, for Grid at the fill price, for Trend at the limit price of the stop order), it is closed immediately as dust. For Grid this uses the new fields `dust_qty` and `close_reason: "dust"` (`[GRID-STAUB]`, grid dust, level free, no latch); for Trend `exit_reason: "dust_on_entry"` and the existing `dust_qty` (`[TREND-STAUB]`, no stop order, no latch). `realized_pnl` is −`quote_spent` as in K-A. This is a cautious valuation, since the dust has a residual value below the minimum volume. The dust quantity is the quantity actually received, not rounded to the `stepSize`; otherwise it could be 0 and A3 would reject it. The same rule applies when recording via the reconciliation. DCA never sells and only books the executed quantity. Decision: for Grid, `dust_qty` and `close_reason` already come in round 1, only for dust on purchase.
- **Partial fill on sale, safeguard only:** if the exchange reports less executed than ordered for a market sale (ended, executed > 0, not `FILLED`), `[GRID-TEILFUELLUNG-UNGEBUCHT]` or `[TREND-TEILFUELLUNG-UNGEBUCHT]` (partial fill not booked) is sent to log and Telegram, directly in `place_market_sell()` and when recording in `reconcile_pending_orders()`. The full quantity is booked as before; this needs no new fields. It is only booked correctly in round 2 (precondition 8). A sale with execution 0 falls under A1: the position stays open, and for Trend the stop order is placed again. For Grid, a sale that ends as `EXPIRED` with 0 is attempted again in every 5-minute cycle as long as the target is reached: per cycle and position one ERROR `[ORDER-OHNE-AUSFUEHRUNG]` and one WARNING `[GRID-VERKAUF-FEHLGESCHLAGEN]`, via Telegram once per position and process run.
- **Tool** `python -m dca_bot.remove_unfilled_grid_positions` (decision B1): it removes open, real grid positions whose quantity **and** spend are exactly 0 as numbers. Each `client_order_id` is first looked up at Binance (read-only client as in the position audit); only what ended without execution is removed. Refused individually: not found (−2013), query failed, still active, executed > 0 (loudly, with „Bestand existiert“, holdings exist), status unreadable, order side not BUY, no `client_order_id`, foreign symbol, sell fields set, partial sale or dust booked. A refused entry stays. Refused as a whole for a missing or unreadable ledger, entries in the pending file or an unreadable pending file, a non-matching symbol check, missing Binance access, and a real open entry where only the quantity or only the spend is 0 or the values are not numbers. Report is the default. `--apply` needs `--expect N`, takes the grid bot's lock before reading, re-checks everything under the lock, writes only with exactly N proven entries, first makes the copy `grid_positions.json.pre-remove-<timestamp>`, removes atomically via `GridLedger.remove_unfilled_positions()` (which itself removes nothing other than entries without holdings) and afterwards verifies that exactly these entries are missing and all others are unchanged. Exit codes: 0, 1 refusal, 2 bot running, 3 verification failed.

**Tests:** 62 new; the suite now has 981 tests (previously 919), all green. `tests/test_unfilled_market_orders.py` (32): A1 in the real `TradingClient` for purchase and sale with `EXPIRED`, `CANCELED`, `REJECTED` and `EXPIRED_IN_MATCH` each with 0, partial fill, `FILLED`, unclear and missing status, stop orders unchanged. In addition the loud report on a partial sale (directly and when recording), A3 for all three ledgers, and end to end on the shared account for Grid, Trend and DCA: purchase and sale with execution 0, partial fill, dust including its reference price (Grid fill price, Trend limit price), dust when recording, and A3 on its own when A1 is bypassed. For this, `FakeExchange` in `test_shared_account.py` has an adjustable liquidity per market order, and the ownership invariant counts grid dust. `tests/test_remove_unfilled_grid_positions.py` (30) models the situation on the server, with the eleven IDs and the seven filled purchases of 09.10. (also as an open variant): filter hits exactly the eleven, report writes nothing, one test per refusal, lock, copy, verification and re-check under the lock, plus filter and removal at ledger level (`is_unfilled_position`, `GridLedger.remove_unfilled_positions`). The fakes in `test_grid_sell_safety.py`, `test_trend_stop_loss.py` and `test_dca_fee_adjustment.py` now return a status field. `test_rollback_compat.py` additionally checks the state `980f3c3` and files with grid and trend dust.

**Mutation test:** 59 mutations against the new checks (A1, report on a partial sale, A3, T2/dust, filter and tool). The first run had 58, of which 57 were detected. The surviving one was dropping the mandatory check of `--expect`: the later check "exactly N proven" caught the case, but only after the lock and the exchange query. The test now requires the refusal before that; detected afterwards. Added later: mutation 59 (grid dust at the sell target instead of the fill price) with its own test on level 1, detected. That makes 59 of 59 detected. The tests ran only on Windows; step 8 of the procedure proves the lock on Linux.

**Rollback:** `git checkout 980f3c3` and restart the services. The rollback test proves for `980f3c3`, `46ca7a7` and `10ce096`: the old code reads the new files, continues working and does not lose `dust_qty`/`close_reason` when writing. Partial sales are not booked in round 1, so open positions have no new fields. After a rollback, A1 and A3 are missing, and entries without holdings can arise again. The cleanup can be undone with the copy `.pre-remove-*`, but that would bring back the eleven entries.

**Procedure on the home server** (`jq` is not confirmed there, so the checks run as Python scripts):

1. Choose the time: not 00:20–00:35 UTC (forced disconnection), not 06:40–07:00 UTC (apt restarts).
2. Preliminary check, mandatory: `journalctl -u grid-bot --since "2026-10-11 16:01" --until "2026-10-11 16:02" | grep "erfolgreich platziert"` must show `'status': 'EXPIRED'` in the response, and a normal purchase line `'status': 'FILLED'`. If the field is missing, stop: A1 would then treat every market order as unclear.
3. `cp -a data data.bak-<date>`
4. `git status` clean, `git log -1` shows `980f3c3`, then `git pull`.
5. `python -m dca_bot.symbol_guard --report`: all four „würde starten“ (would start).
6. Check script, expected (a) 11 with exactly the IDs from the table above, (b) 18, (c) 0, Trend and DCA 0 each:
```bash
python - <<'EOF'
import json, os
from dotenv import load_dotenv
load_dotenv()
num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
grid = json.load(open(os.getenv("GRID_STATE_FILE", "data/grid_positions.json"), encoding="utf-8"))
a = [r for r in grid if r.get("status") == "open" and r.get("dry_run") is False
     and num(r.get("quantity")) and r["quantity"] == 0
     and num(r.get("quote_spent")) and r["quote_spent"] == 0]
print("(a) Kandidaten:", len(a))
for r in a:
    print("   ", r["level_index"], r["bought_at"][:19], r["id"], r["client_order_id"])
b = [r for r in grid if str(r.get("bought_at", ""))[:16] in ("2026-10-09T05:17", "2026-10-11T16:01")]
print("(b) beide Minuten:", len(b))
for r in b:
    print("   ", r["level_index"], r["bought_at"][:19], r["status"], r["quantity"], r["quote_spent"], r["dry_run"])
c = [r for r in grid if r.get("status") == "open" and r.get("dry_run") is False
     and (not (num(r.get("quantity")) and num(r.get("quote_spent")))
          or (r["quantity"] == 0) != (r["quote_spent"] == 0))]
print("(c) halb leer oder keine Zahlen:", len(c))
for name, var, default in (("Trend", "TREND_STATE_FILE", "data/trend_ledger.json"),
                           ("DCA", "DCA_BOT_STATE_FILE", "data/trade_ledger.json")):
    rows = json.load(open(os.getenv(var, default), encoding="utf-8"))
    zero = [r for r in rows if r.get("dry_run") is False and r.get("status", "open") == "open"
            and (r.get("quantity") == 0 or r.get("quote_spent") == 0)]
    print(f"{name}: echte Einträge mit Menge oder Einsatz 0:", len(zero))
EOF
```
7. `python -m dca_bot.remove_unfilled_grid_positions` (report): 11 candidates, all „ohne Bestand belegt“ (proven without holdings), IDs as in (a). If one is refused: stop.
8. Lock test with the grid bot running: `python -m dca_bot.remove_unfilled_grid_positions --apply --expect 11`. Expected: exit code 2 (`echo $?`), „ABGEBROCHEN“ (aborted), no copy `grid_positions.json.pre-remove-*`.
9. `sudo systemctl stop grid-bot`, then `python -m dca_bot.remove_unfilled_grid_positions --apply --expect 11`: „GESCHRIEBEN: 11“ (written).
10. `python -m dca_bot.audit_positions` (grid has eleven fewer open positions, no new discrepancy) and the check script, expected 0 everywhere:
```bash
python - <<'EOF'
import json, os
from dotenv import load_dotenv
load_dotenv()
for name, var, default in (("Grid", "GRID_STATE_FILE", "data/grid_positions.json"),
                           ("Trend", "TREND_STATE_FILE", "data/trend_ledger.json"),
                           ("DCA", "DCA_BOT_STATE_FILE", "data/trade_ledger.json")):
    rows = json.load(open(os.getenv(var, default), encoding="utf-8"))
    zero = [r for r in rows if r.get("dry_run") is False and r.get("status", "open") == "open"
            and (r.get("quantity") == 0 or r.get("quote_spent") == 0)]
    print(f"{name}: {len(rows)} Einträge, davon echt und offen mit Menge oder Einsatz 0: {len(zero)}")
EOF
```
11. `sudo systemctl start grid-bot`, `journalctl -u grid-bot -f`: new code version, symbol check, first cycle without „Verkaufsmenge … 0“.
12. `sudo systemctl restart dca-bot trend-bot allocator`. DCA does not buy immediately because of W2; the trend bot still holds the dry-run position. Afterwards „Code-Version“ must show the new hash everywhere.
13. Note under "Deploy status" and here as a separate paragraph on the cleanup. The trend procedure of 07.10. stays paused until Elias releases it.

**Result on the ticker outliers** (Elias, 16.10.2026, script by hand on the home server). The real purchases of levels 4 and 5 of 09.10.2026 (05:17:43 and 05:17:44 UTC) yield, calculated from spend and quantity, about 72.139 and 66.600 USDT, levels 6 to 10 about 82.446. All sold real grid positions in the window of the last approx. 41 days were checked: purchase price against the mainnet low of the purchase hour (public hourly candles); a purchase more than 3 % below it counts as an outlier. Result: realised in total 16,82 USDT, of which 13,93 USDT from such purchases, in three events:

| Time (UTC) | Levels | Purchase prices | Mainnet low of the hour | Profit (USDT) |
|---|---|---|---|---|
| 02.10.2026 13:30 | 8 to 13 | 77.809 to 79.480 | 86.466 | 6,15 |
| 09.10.2026 05:17 | 4 and 5 | 72.139 and 66.600 | 82.225 | 3,56 |
| 09.10.2026 07:03 | 7 to 10 | 70.800 to 79.902 | 82.494 | 4,23 |

The exact total is 13,93 USDT (script, from the unrounded individual values). The event sums in the table are formed from rounded rows, so their sum of 13,94 deviates by 0,01 (rounding). Roughly 2,9 USDT remain from normal operation (approximation: 16,82 minus 13,93). The 3 % threshold and the hourly low as the yardstick are choices of this evaluation; purchases just above the threshold are not assessed individually. The purchases of levels 6 to 10 at 05:17 are at 82.446 and thus above the mainnet low of the hour. The entry of 06.10.2026 has an addendum on this.

**Cleanup and deploy (16.10.2026)** (Elias, following the procedure above; preliminary check, lock test and the verification afterwards done by hand on the server):

- **Preliminary check, by hand on the server:** the market responses in the journal carry the field `status`: `'EXPIRED'` for the orders of 11.10.2026, `'FILLED'` for the purchase of 14.10.2026.
- **Report of the tool:** 11 candidates, all confirmed by the exchange as without effect (`EXPIRED`, executed 0).
- **Lock test, by hand on the server,** with the grid bot running (`--apply --expect 99`): exit code 2, „ABGEBROCHEN“ (aborted), no copy.
- **Cleanup:** grid bot stopped, then `--apply --expect 11`: exit code 0, 11 entries removed, copy `data/grid_positions.json.pre-remove-20261016T143039Z` (on the server). In addition, a backup of the whole folder as `data.bak-2026-10-16`.
- **Verification afterwards, by hand on the server:** grid ledger 36 entries (previously 47), of which 4 open. In `trade_ledger`, `grid_positions` and `trend_ledger` no real entry without quantity or spend. The error lines „Verkaufsmenge … 0“ (sell quantity … 0) in the journal end with the stopping of the grid bot at 14:30 UTC.
- **Deploy `76f261b`:** grid bot restarted at 14:32 UTC, DCA, Trend and allocator at 14:40 UTC, all four with „Code-Version: 76f261b“, symbol checks „passt“ (matches), holdings reconciliation OK. Recorded under "Deploy status".
- **Precondition 7 remains open:** the fix is deployed; the proof in live operation arises as soon as the testnet again delivers a market order without execution.
- **Trend procedure of 07.10.2026:** no longer blocked by the fix. Status: ready for release, not yet carried out; plan: after a quiet night with the new code (forced disconnection: moves forward by roughly one minute per day; for 17.10. calculated at about 00:15 UTC, estimate, not measured since 05.10.). The procedure there has an addendum of 16.10.2026.
- **Blocked window for interventions:** from now on uniformly 00:05 to 00:35 UTC, no longer 00:20–00:35 UTC as in step 1 of the procedure above and of the procedure of 07.10.2026. Basis: the measurements up to 05.10. (00:27 UTC), see "Current status", "Operations".
- **Note (16.10.2026, after measurement):** the estimate "for 17.10. calculated at about 00:15 UTC" is replaced by measurements from 05.10. to 16.10. (last 16.10. 00:14:31 UTC, drift roughly 1,1 minutes per day). The blocked window applies from now on uniformly as 23:50 to 00:30 UTC instead of 00:05 to 00:35 UTC as in the item above, because the start of the disconnection already reaches 00:05 UTC around 20.10. This is an extrapolation of the measured drift, not a measurement; it will be measured again by 25.10.2026 at the latest. Details: "Current status", "Operations".

**Open, round 2** (own plan after round 1 is approved): book a partial fill on sale correctly, with `partial_exit_*`, `dust_qty`/`close_reason` for partial sales, `partial_exit_from_stop`, moving `open_quantity` and `record_partial_exit`.

### Testnet outage with HTTP 502 on 07.10.2026 (16.10.2026)

On 07.10.2026 from 04:37 to 10:32 UTC the testnet returned HTTP 502 Bad Gateway: roughly 72 failed grid cycles in just under six hours. The bots kept running afterwards without intervention; Telegram reported only once per error type. This was not a forced disconnection. The error counters in the dashboard on a screenshot of 07.10.2026, 10:01 local time (about 08:01 UTC), match this: „41 Fehlschläge in Folge“ (41 failures in a row) on the grid card and „1 Fehlschlag in Folge“ (1 failure in a row) on the DCA and Trend cards. Information from Elias, 16.10.2026.

### Trend procedure carried out, first real trend position (17.10.2026)

Elias, following the procedure of 07.10.2026 with the addendum of 16.10.2026; night check, lock probe, the query of the stop order and the checks for the procedure steps done by hand on the server, source in each case Elias's output on the home server. No deploy, code state on the home server still `76f261b`.

- **Previous evening, checked by hand, 16.10.2026 at 23:10 UTC** (before the intervention, not immediately before it):
  - Symbol report (step 3): all four bots „würde starten“ (would start).
  - Balances according to `check_orders` (step 10): BTC free 1.00022000, locked 0; USDT free 9.990,16599670, locked 0; price 81.741,84. Free USDT was not checked again on 17.10.; the value from the previous evening applies.
  - Allocator (step 5): `trend_fraction` 0.9945196322990328, `updated_at` 2026-10-16T22:40:44Z.
- **Night check before the intervention, by hand on the server:** four services `active`, server without reboot since 23.09. Exactly one error line „Unerwarteter Fehler im Grid-Zyklus“ (unexpected error in the grid cycle), on 17.10.2026 at 00:13:36 UTC (forced disconnection, the first under the new code). 11 grid cycles in the hour 00:00 to 01:00 UTC. Since the deploy no hits for `ORDER-OHNE`, `ORDER-UNKLAR`, `SYMBOL-KONFLIKT`, `DOPPELVERKAUF`, `TEILFUELLUNG` or `STAUB`. The measurement has been added under "Current status", "Operations".
- **Before the intervention, checked by hand, 17.10.2026 at about 09:21 UTC:**
  - Report of the tool (step 4): exactly one open position `c0e153c1-f5d8-45a2-9797-aa66da375728`, `dry_run=True`, stop order `None`, pending file not present, no latch, „Keine Einwände“ (no objections).
  - Allocator (step 5): `trend_fraction` 0.9949580617151103, `updated_at` 2026-10-17T08:40:48Z (41 minutes old).
  - Mainnet price (step 5): 81.719,30 at the query, 81.734,75 at the intervention.
- **Lock probe, by hand on the server,** with the trend bot running (`--apply` with an invented `--trade-id`): exit code 2, „ABGEBROCHEN“ (aborted), no copy. This proves the lock on Linux for the trend tool as well; the lock test of 16.10.2026 only covered the grid tool.
- **Closing the dry-run position:** trend bot stopped, then `python -m dca_bot.close_dry_run_trend --apply --trade-id c0e153c1-f5d8-45a2-9797-aa66da375728 --exit-price 81734.75` (mainnet price): exit code 0, position closed as `manual_close`, no stop-loss latch set, copy `data/trend_ledger.json.pre-close-20261017T092417Z` (on the server). The simulated `realized_pnl` of +0,93062751 never counts as a result. According to the analysis of 07.10.2026, the trend card of the dashboard app counts the entry as a closed trade, not as a result.
- **After closing, checked by hand, 17.10.2026 at 09:24 UTC** (step 9): `audit_positions` Trend „1 Einträge insgesamt, davon 0 offen (1 geschlossen)“ (1 entry in total, 0 of them open, 1 closed).
- **Start and first cycle:** trend bot started at 09:24:55 UTC, „Code-Version: 76f261b“. First cycle: allocator share 99,5 %, effective amount 14,92, real market buy with status `FILLED`, executed 0.00018000 BTC, entry 81.726,36. Afterwards the stop order was placed successfully (09:24:59 UTC), no `[TREND-FEHLER]`. Next cycle in 24 hours.
- **Stop order, read from the exchange, by hand on the server** (`python -m dca_bot.check_orders --client-order-id trend-d0d0c6b741f444518c07fc3f`, at about 09:30 UTC): status `NEW`, `SELL` / `STOP_LOSS_LIMIT`, orderId 3807835, quantity 0.00018000, stop 73.553,72, limit 73.185,95, time 2026-10-17 09:24:59 UTC.
- **Ledger:** position `bd1c3457-bdc0-4aa8-b1ee-ea2ee96c7a34`, entry 81.726,36, quantity 0.00018, spend 14,71, mode ECHT (real), `stop_loss_order_id` 3807835, limit 73.185,96. That is one cent more than on the exchange, presumably rounding, not checked. The spend of 14,71 is below the allocator amount of 14,92 because the quantity is rounded down to the step size 0.00001 (0.00018 × 81.726,36 = 14,71).
- **After the first cycle, checked by hand, 17.10.2026 at about 09:30 UTC** (step 12): `audit_positions` Trend: 2 entries, 1 of them open; ID `bd1c3457-bdc0-4aa8-b1ee-ea2ee96c7a34`, entry 81.726,36, quantity 0.00018000, spend 14,71, mode ECHT (real), stop-loss order 3807835 (limit 73.185,96). Account reconciliation BTC: DCA 0.00038000 (2 dry run, do not count), Grid 0.00054000, Trend 0.00018000, total 0.00110000; account free 1.00022000, locked 0.00018000 (all Trend, via the clientOrderId prefix), total 1.00040000; „In Ordnung“ (OK), surplus 0.99930000.
- **Telegram:** the message `[TREND-EINSTIEG]` arrived (information from Elias, 17.10.2026).
- **First real trend position:** this is the first real trend entry on the testnet and the trend bot's first real stop order on the exchange. Until 17.10.2026 the dry-run position of 15.09. occupied the only trend slot (entry of 07.10.2026).
- **Precondition 2:** trend procedure carried out, real entry with stop order, no fill data yet. If an outlier triggers the stop order, the bot closes with `stop_loss`, the latch takes effect, and the next entry requires `python -m dca_bot.reset_trend_stop_loss`. That is then a technology test of the chain (stop fill, booking, latch, manual reset), not a calibration value.
- **Precondition 7 remains open:** in the trend entry the buy path assessed the status `FILLED` correctly; a case without execution has still not occurred.

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
- **No purchase without execution** (since 16.10.2026,
  `binance_client._settle_market_response`): a regular response to a
  market order is also assessed before booking, with the same rule as in
  the reconciliation. Ended without execution (e.g. `EXPIRED` with
  `executedQty` 0) → pending entry removed, `[ORDER-OHNE-AUSFUEHRUNG]` in
  the log, the strategy books nothing and reports „nicht verbucht“ (not
  booked). Still active, no or unknown status → unclear, entry stays,
  `[ORDER-UNKLAR]`. Stop orders are excluded. Before this, all three bots
  booked such an order as a purchase with quantity 0 at the ticker price
  (log 16.10.2026). A trend entry with an unclear outcome occupies the
  slot until the next daily cycle, because the reconciliation only asks
  again at the start of the next cycle. A grid sale that ends as
  `EXPIRED` with 0 is attempted again in every cycle (ERROR and WARNING
  per cycle, Telegram once per position and process run).
- **Ledger guard** (since 16.10.2026, `risk.require_plausible_entry`): no
  ledger accepts a real purchase or entry with quantity ≤ 0 or spend
  ≤ 0. Only the new entry is checked. The exception is raised before
  `confirm_booked()`; the pending entry stays for the reconciliation.
- **Partial fill of a market order** (since 16.10.2026): on purchase, the
  executed quantity is booked; below the minimum volume it is closed
  immediately as dust (`order_utils.is_dust`, details in 7.2 and 7.3,
  `realized_pnl` = −`quote_spent`, valued cautiously). On sale, the full
  quantity is still booked until round 2, but a partial fill is reported
  loudly (`[GRID-TEILFUELLUNG-UNGEBUCHT]`/
  `[TREND-TEILFUELLUNG-UNGEBUCHT]`, directly and when recording).
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
- **Dust on purchase** (since 16.10.2026): if the exchange executes a
  purchase only partially and the purchased quantity at the fill price is
  below the minimum volume, it could never be sold. The position is then
  closed immediately: `close_reason` "dust", `dust_qty` the quantity
  actually received, `sell_price` empty, `realized_pnl` = −`quote_spent`
  (`[GRID-STAUB]`). The level is free afterwards; there is no latch. A
  sellable partial quantity is booked normally (`[GRID-KAUF]` with
  „Teilfüllung“). A purchase order without execution no longer occupies a
  level (7.1).
- **Telegram notifications** (if configured, see README section 7):
  `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]`, `[GRID-VERKAUF]` (with the
  realised profit/loss of this position), `[GRID-VERKAUF-FEHLGESCHLAGEN]`,
  `[GRID-VERKAUF-GESPERRT]`,
  `[GRID-STOP-LOSS]`, `[GRID-NOTAUS]`, `[GRID-FEHLER]`,
  `[GRID-DOPPELVERKAUF]` (since 27.09.2026, see 7.1), since 16.10.2026
  also `[GRID-STAUB]` and `[GRID-TEILFUELLUNG-UNGEBUCHT]`.
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
  `[TREND-TEILFUELLUNG]` and `[TREND-DOPPELVERKAUF]`, since 16.10.2026
  `[TREND-STAUB]` also on entry and `[TREND-TEILFUELLUNG-UNGEBUCHT]`.

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
- **Dust on entry** (since 16.10.2026): if the exchange executes the
  entry only partially and the quantity at the limit price of the stop
  order is below the minimum volume, the stop order would be rejected.
  The trade is then closed immediately: `exit_reason` "dust_on_entry",
  `dust_qty` the quantity received, `realized_pnl` = −`quote_spent`, no
  stop order, **no** latch (`[TREND-STAUB]`). A partial quantity that can
  be protected is booked normally and protected with exactly this
  quantity. An entry without execution no longer occupies the slot (7.1).
- **One single rule for order status:** the assessment of whether an order
  is filled, still active, ended or unreadable exists exactly once in the
  project (`order_lifecycle_state()` in `pending_orders.py`) and is used
  by the cycle check, by the pending-orders path (7.1) and, since
  16.10.2026, also by the assessment of every regular market response.
  Previously, the first two had their own, slightly different rules.
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
therefore also be tested here. Since 16.10.2026, the share that the
`FakeExchange` executes can be set per market order (`set_liquidity`).
Below 1 the order ends with `EXPIRED`, at 0 with executed 0, as on the
testnet on 09.10. and 11.10.2026.

`test_unfilled_market_orders.py` (since 16.10.2026) covers market orders
without or with only partial execution: the assessment in the real
`TradingClient`, the ledger guard of all three ledgers and the paths
through all three strategies on the shared account.
`test_remove_unfilled_grid_positions.py` models the situation on the home
server of 16.10.2026 for the cleanup tool.

The whole suite: `python -m unittest discover -s tests -t .`

---

*Living project document, in two files since 29.09.2026. Here: the current state with the open items and section 7 (technical reference), both corrected directly, as well as the log from 29.09.2026, which, like every log, only receives dated notes. In `trading-bot-projekt-archiv.md`: research, planning and the chronological log up to 28.09.2026 (sections 1–6i), moved unchanged. Created on 13.09.2026 by merging two versions maintained in parallel (chat artifact + local Claude Code continuation).*
