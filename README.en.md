# Trading Bots (Binance Testnet)

> English translation of `README.md`, kept in sync with it (every change
> lands in both files in the same commit). If they ever differ, the German
> original is authoritative. Log tags and
> messages (e.g. `[KAUF]`, `[NOTAUS]`) are quoted exactly as the code emits
> them, i.e. in German. Dates use the original DD.MM.YYYY format.

Three completely independent trading bots plus a controlling auxiliary
process in the same project, all running against the **Binance Testnet
API** – no real money is moved at any time as long as you do not enter
real API keys:

- **DCA bot** (`dca_bot/main.py`): buys a fixed amount of an asset at fixed
  intervals (dollar-cost averaging).
- **Grid trading bot** (`dca_bot/main_grid.py`, see section 3.1): buys at
  fixed price levels within a price range and sells each position
  individually once the price rises one level higher.
- **Trend-following bot** (`dca_bot/main_trend.py`, see section 3.2):
  EMA crossover with a trend-strength filter on daily candles, long-only,
  with a fixed stop-loss per trade. Validated by backtest across several
  historical market phases before the first dry run (see
  `trend_backtest.py`).
- **Capital allocator** (`dca_bot/main_allocator.py`, see section 3.3):
  not a trading bot of its own but a controlling auxiliary process that
  continuously shifts capital between the DCA and trend-following bots
  depending on the current trend strength. It never places orders itself
  and only affects DCA/Trend after an explicit opt-in.

All four share only the Binance/Telegram credentials in `.env` – state
(trade history, kill switch, stop-loss) is completely separate for each
bot, and they can run independently of each other (including at the same
time).

## Dashboard app

A separate, read-only web dashboard for displaying the bot stats (current
positions, total profit/loss, trade export for the tax return) lives in its
own repository:
[crypto-bot-app](https://github.com/EliasNein/crypto-bot-app).

Completely independent of this project – it only reads the ledger files
and has no access to API keys or trading functions.

## 1. Prerequisites

- Python 3.10+
- A free testnet account: https://testnet.binance.vision/
  (log in with a GitHub account, then "Generate HMAC_SHA256 Key" for API key + secret)

## 2. Installation

```bash
cd trading-bot
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configuration

```bash
cp .env.example .env
```

Then open `.env` and enter your testnet keys:

```
BINANCE_API_KEY=your_real_testnet_key
BINANCE_API_SECRET=your_real_testnet_secret
USE_TESTNET=true                       # false = REAL exchange, real money
DCA_BOT_ENABLE_TRADING=false

# Risk management (optional, defaults see dca_bot/config.py)
DCA_BOT_KILL_SWITCH_FILE=STOP          # If this file exists -> bot stops immediately
DCA_BOT_HALT=false                     # Alternative to the file: set to "true" to stop
DCA_BOT_STOP_LOSS_PCT=25.0             # Pause buying at X% loss vs. capital invested (0 = off)
DCA_BOT_STATE_FILE=data/trade_ledger.json

# Telegram notifications (optional, leave empty to disable)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

**Important:** keep `DCA_BOT_ENABLE_TRADING` at `false` initially. In this
mode the bot only simulates each purchase and logs it ("[DRY-RUN]"), but
places no real order. Only once you have checked the behaviour in the log,
set it to `true` to place real testnet orders (with test balance, no real
money).

Since the W12 fix, the DCA bot's symbol, amount, interval and daily limit
can also be set via `.env` (`DCA_SYMBOL`, `DCA_QUOTE_AMOUNT`,
`DCA_INTERVAL_HOURS`, `DCA_MAX_DAILY_SPEND`) – it was the only one of the
four bots where these previously existed only as defaults in the code. The
defaults are unchanged.

**`USE_TESTNET` is the project's live switch** (default `true`). Set to
`false`, all four processes trade against the real exchange with real
money – each of them reports this unmistakably in the log and via Telegram
at startup; there is no silent switchover. In live mode, Telegram
credentials and all position sizes also become mandatory (see section 6),
and the test values from `.env.example` are rejected. A test value that is
meant to apply deliberately after calibration is confirmed by name and
value, e.g. `LIVE_CONFIRMED_VALUES=TREND_STOP_LIMIT_OFFSET_PCT=0.5`. Don't
forget: testnet keys do not work on the real exchange,
`BINANCE_API_KEY`/`SECRET` must be switched as well.

### 3.1 Grid bot

In addition to the Binance/Telegram credentials above (which are shared):

```
GRID_SYMBOL=BTCUSDT
GRID_LOWER_LIMIT=70000.0      # Lower grid bound - ADJUST TO CURRENT MARKET!
GRID_UPPER_LIMIT=90000.0      # Upper grid bound - ADJUST TO CURRENT MARKET!
GRID_SPACING_PCT=1.5          # Spacing between levels in %
GRID_AMOUNT_PER_LEVEL=15.0    # Amount per level in quote currency
GRID_INTERVAL_MINUTES=5       # How often the price is checked
GRID_BOT_ENABLE_TRADING=false
GRID_KILL_SWITCH_FILE=STOP_GRID
GRID_BOT_HALT=false
GRID_STOP_LOSS_PCT=15.0
GRID_STATE_FILE=data/grid_positions.json
GRID_STOP_LOSS_STATE_FILE=data/grid_stop_loss_paused.json
```

**Important:** `GRID_LOWER_LIMIT`/`GRID_UPPER_LIMIT` are placeholder
defaults – be sure to adjust them to the current market price before
starting, otherwise the bot may buy (in dry run: simulate buying) far away
from the real price.

### 3.2 Trend-following bot

In addition to the Binance/Telegram credentials above (which are shared).
The defaults match exactly the values tested in the backtest:

```
TREND_SYMBOL=BTCUSDT
TREND_EMA_FAST_PERIOD=20      # Fast EMA in days
TREND_EMA_SLOW_PERIOD=50      # Slow EMA in days
TREND_MIN_GAP_PCT=1.0         # Trend-strength filter: minimum EMA gap in %
TREND_AMOUNT_PER_TRADE=15.0   # Position size per trade in quote currency
TREND_INTERVAL_HOURS=24       # Daily candles -> check once a day
TREND_BOT_ENABLE_TRADING=false
TREND_KILL_SWITCH_FILE=STOP_TREND
TREND_STOP_LOSS_PCT=10.0      # Fixed stop-loss below the entry price
TREND_STOP_LIMIT_OFFSET_PCT=0.5  # Gap between stop and limit price of the real exchange stop order (see trading-bot-project.en.md 7.3)
```

### 3.3 Capital allocator

In addition to the Binance/Telegram credentials above (which are shared):

```
ALLOCATOR_SYMBOL=BTCUSDT
ALLOCATOR_EMA_FAST_PERIOD=20
ALLOCATOR_EMA_SLOW_PERIOD=50
ALLOCATOR_ZERO_ANCHOR_PCT=0.0     # EMA gap at which the trend share is 0%
ALLOCATOR_FULL_ANCHOR_PCT=3.0     # EMA gap at which the trend share is 100%
ALLOCATOR_SMOOTHING_PERIOD=3      # EMA smoothing of the allocation, in DAYS
ALLOCATOR_INTERVAL_MINUTES=60     # How often the process wakes up (not: EMA cadence)
ALLOCATOR_NOTIFY_THRESHOLD_PP=15.0
ALLOCATOR_KILL_SWITCH_FILE=STOP_ALLOCATOR
ALLOCATOR_HALT=false
ALLOCATOR_STATE_FILE=data/allocator_state.json
```

The anchor points (0%/3%) are a deliberate starting point, not an
empirically derived optimum – see the backtest results for context.

**Effect on DCA/Trend only after explicit opt-in:** by default, neither
the DCA bot nor the trend bot knows about the allocator. Only when you
additionally set `DCA_ALLOCATOR_STATE_FILE` or
`TREND_ALLOCATOR_STATE_FILE` in `.env` to the same path as
`ALLOCATOR_STATE_FILE` does the respective bot scale the amount of a NEW
order by the current allocation. Open positions always remain unaffected.

## 4. Starting

Each component is its own process and runs completely independently of
the others (including in parallel):

| Component | Start | Log |
|---|---|---|
| DCA bot | `python -m dca_bot.main` | `logs/dca_bot.log` |
| Grid bot | `python -m dca_bot.main_grid` | `logs/grid_bot.log` |
| Trend-following bot | `python -m dca_bot.main_trend` | `logs/trend_bot.log` |
| Capital allocator | `python -m dca_bot.main_allocator` | `logs/allocator.log` |

Logs appear both in the console and in the respective file. Stop with
`Ctrl+C`. At startup, the trend bot and the allocator automatically load
real historical daily candles (public Binance API) so the EMAs don't have
to start from zero.

## 5. Project structure

```
trading-bot/
├── dca_bot/
│   ├── config.py         # Central configuration of the DCA bot (reads .env)
│   ├── config_guard.py   # Live switch + mandatory variable check (shared)
│   ├── balance_guard.py  # Consistency check before every sale (shared)
│   ├── startup_checks.py # Consistency check at bot startup (shared)
│   ├── binance_client.py # Wrapper around the Binance API (testnet, buy+sell, trading rules)
│   ├── order_utils.py    # Quantisation to tickSize/stepSize + fee correction (shared)
│   ├── pending_orders.py # Idempotent order placement + ground-truth reconciliation (shared)
│   ├── process_lock.py   # Protection against a duplicate bot start (shared)
│   ├── heartbeat.py      # Daily sign of life of all four bots (shared)
│   ├── heartbeat_status.py # Heartbeat status as a file for the dashboard app (shared)
│   ├── cycle_errors.py   # Rate limit for cycle error notifications (Grid + Allocator)
│   ├── strategy.py       # DCA logic incl. daily limit as an emergency brake
│   ├── risk.py           # Kill switch, trade ledger, portfolio stop-loss (DCA)
│   ├── notifier.py       # Telegram notifications (optional, shared)
│   ├── main.py           # Entry point DCA bot
│   ├── grid_config.py    # Central configuration of the grid bot (reads .env)
│   ├── grid_signals.py   # Crossing/sell/stop-loss logic (backtest AND live)
│   ├── grid_risk.py      # Position ledger, trend-break stop-loss (Grid)
│   ├── grid_strategy.py  # Grid buy/sell logic
│   ├── grid_backtest.py  # Backtest across historical market phases
│   ├── main_grid.py      # Entry point grid bot
│   ├── trend_config.py   # Central configuration of the trend bot (reads .env)
│   ├── trend_signals.py  # EMA crossover + trend-strength filter (backtest AND live)
│   ├── trend_risk.py     # Trade ledger, stop-loss latch (Trend)
│   ├── trend_strategy.py # Trend-following entry/exit logic
│   ├── trend_backtest.py # Backtest across historical market phases
│   ├── main_trend.py     # Entry point trend bot
│   ├── allocator_config.py  # Central configuration of the allocator (reads .env)
│   ├── allocator_signals.py # Allocation/smoothing logic + state reader (backtest AND live)
│   ├── allocator.py         # Allocator core logic (calculation + state file)
│   ├── allocator_backtest.py # Backtest: combined vs. isolated DCA/Trend
│   ├── main_allocator.py    # Entry point allocator
│   ├── audit_positions.py         # CLI: holdings of all three bots + account reconciliation (read-only)
│   ├── check_orders.py            # CLI: look up orders, e.g. after [ORDER-UNKLAR] (read-only)
│   ├── reset_stop_loss.py         # CLI: reset the DCA stop-loss pause
│   ├── reset_grid_stop_loss.py    # CLI: reset the grid stop-loss pause
│   ├── reset_trend_stop_loss.py   # CLI: reset the trend stop-loss pause
│   └── fix_dry_run_quote_spent.py # CLI: one-off correction of corrupted dry-run amounts
├── requirements.txt
├── .env.example
└── README.md
```

## 6. Safety mechanisms at a glance

Short version. The full description of each mechanism including its
rationale is in `trading-bot-project.en.md` section 7 (7.1 for all bots,
7.2 Grid, 7.3 Trend, 7.4 Allocator).

### In an emergency

```bash
touch STOP_ALL     # stops DCA, Grid, Trend and Allocator
```

**A kill switch terminates the processes.** They exit normally (exit code
0), and `Restart=on-failure` only restarts after a failure. Removing the
file again therefore starts **nothing**. Restarting takes two steps, in
this order:

```bash
rm STOP_ALL
sudo systemctl start dca-bot grid-bot trend-bot allocator
systemctl status dca-bot grid-bot trend-bot allocator   # check
```

If a service is started while the kill-switch source is still present, it
exits again immediately after the startup checks. Until it is started, no
cycle runs and no heartbeat arrives. Open grid positions have no
protection during this time (the grid bot has no stop order on the
exchange); a trend position only has its stop order on the exchange.

- Stop a single bot: create the kill-switch file (defaults `STOP`,
  `STOP_GRID`, `STOP_TREND`, `STOP_ALLOCATOR`) or set `*_HALT=true` or
  `STOP_ALL=true` – also later in `.env`, without a restart. Restarting
  works the same way: first clear all sources (remove the file, set the
  variable to `false` or delete the line), then start the service, e.g.
  `rm STOP_GRID && sudo systemctl start grid-bot`.
- Stop-loss locks never lift by themselves, reset only manually:
  `python -m dca_bot.reset_stop_loss`, `python -m
  dca_bot.reset_grid_stop_loss`, `python -m dca_bot.reset_trend_stop_loss`.
- Check holdings before a bot is re-enabled or `*_BOT_ENABLE_TRADING` is
  changed: `python -m dca_bot.audit_positions` (see section 8.1).

### All bots (details: 7.1)

- **Dry run by default:** no real orders without explicit opt-in
  (`*_BOT_ENABLE_TRADING=true`).
- **Live switch `USE_TESTNET`:** only `true`/`false` allowed, a typo
  aborts. In live mode an unmistakable warning in log and Telegram;
  Telegram credentials and all position sizes become mandatory, and the
  test values from `.env.example` are rejected unless confirmed via
  `LIVE_CONFIRMED_VALUES`.
- **Mandatory variable check at startup:** empty, nonsensical or values
  copied from `.env.example` stop the startup with a clear message –
  without a systemd restart loop.
- **Kill switch:** bot-specific or global (`STOP_ALL`), takes effect
  immediately, even in the middle of a cycle; for the grid bot before
  every single purchase.
- **Stop-loss with manual reset:** DCA pauses buying at a loss of
  `DCA_BOT_STOP_LOSS_PCT` (does not sell), Grid pauses buying on a trend
  break below the lower grid bound, Trend closes the position and pauses
  new entries.
- **Daily limit (DCA):** calculated from the persistent ledger, also
  applies after a restart; daily window in UTC.
- **No order without a ledger entry:** every order is written to a
  pending file before the network call. After a connection error or a
  response with an unknown outcome (HTTP 5xx, −1006/−1007) the bot asks
  Binance instead of guessing; the next cycle records anything missing as
  `[REKONZILIATION]` (reconciliation). If the outcome cannot be resolved,
  it reports `[ORDER-UNKLAR]` (order unclear) with the clientOrderId. To
  look up whether the order exists and whether it is booked (section
  8.4):
  `python -m dca_bot.check_orders --client-order-id grid-7f3a9c2e14b84d6fa0e51c83`
- **No second sale on an unclear outcome:** as long as a sale or a stop
  order is unresolved, the bot does not sell the same position again – on
  the shared account that would go through using another bot's holdings.
- **Corrupted ledger:** the bot does not start rather than silently
  carrying on with an empty history. All ledgers are written atomically.
- **No immediate purchase on every restart (DCA)** and **no duplicate bot
  start** (process lock).
- **Consistency check against the account balance:** before every real
  sale (not covered → no sale) and at every startup; a discrepancy in the
  ledger is reported loudly but blocks nothing.
- **Real trading rules, fees, fill prices:** quantities and prices are
  quantised to `stepSize`/`tickSize`, fees are deducted, and the ledger
  records the actual fill price.
- **Errors per cycle** do not terminate the bot. **Heartbeat** once a day
  with the time of the last successful cycle.

### Grid bot (details: 7.2)

- Dry-run positions are never really sold; real positions are never
  closed in simulation while trading is disabled
  (`[GRID-VERKAUF-GESPERRT]`, grid sale blocked).
- A failed real sale leaves the position open and the next cycle tries
  again – on an unclear outcome only once it has been resolved.
- Maximum capital commitment = number of buy levels ×
  `GRID_AMOUNT_PER_LEVEL` (no daily limit).
- `[GRID-FEHLER]` (grid error) is sent via Telegram only once per error
  type until a cycle has succeeded again.

### Trend-following bot (details: 7.3)

- Real `STOP_LOSS_LIMIT` order on the exchange, protects the position
  even during a bot, internet or power outage; threshold derived from the
  entry fill price.
- The protection heals itself: if the stop order is missing or has
  disappeared, the bot places a replacement; unclear states are counted
  and reported from 3 cycles on.
- Dry-run positions are never really sold; while trading is disabled, a
  real position is not touched and its stop order remains in place
  (`[TREND-AUSSTIEG-GESPERRT]`, trend exit blocked).
- A failed real sale leaves the position open and immediately places a
  new stop order; on an unclear outcome the bot polls for up to 60 s and
  only places it if the sale demonstrably did not happen.
- If the stop order has partially sold, this is booked and only the
  remainder is sold.

### Capital allocator (details: 7.4)

- Never places orders itself (enforced by the code).
- If the allocation is stale or unusable, DCA and Trend fall back to
  100 % DCA / 0 % Trend.
- `[ALLOCATOR-FEHLER]` (allocator error) is sent via Telegram only once
  per error type until a cycle has succeeded again.

## 7. Telegram notifications (optional)

The bot can optionally report events via Telegram message. If nothing is
configured, Telegram remains completely disabled (default) – the bot keeps
running identically, it just sends nothing.

### 7.1 Setup

1. **Create a bot:** chat with [@BotFather](https://t.me/BotFather) in
   Telegram, send `/newbot` and follow the instructions (assign a name +
   username). At the end you get a **bot token** (format
   `123456789:AAxx...`) – that is `TELEGRAM_BOT_TOKEN`.
2. **Start a chat with your bot:** search for your new bot in Telegram and
   send it any first message (e.g. "Hello") – without this step the
   Telegram API does not allow the bot to write to you.
3. **Find out the chat ID**, one of the following options:
   - Briefly message [@userinfobot](https://t.me/userinfobot); it shows
     your own chat ID, or
   - open `https://api.telegram.org/bot<TOKEN>/getUpdates` in the browser
     (after writing to your bot as in step 2) and look for
     `"chat":{"id": ...}` in the JSON.
4. Enter both values in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAxx...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Restart – the log then shows `Telegram-Benachrichtigungen aktiv.`
   (Telegram notifications active).

### 7.2 Which events are reported

- **Purchases**: every executed buy cycle – `[KAUF]` (buy) for a real
  order, `[DRY-RUN]` for a simulated purchase, `[FEHLER]` (error) if a real
  order fails at the exchange.
- **Stop-loss**: `[STOP-LOSS]` when the portfolio stop-loss triggers (see
  section 6) – only once when it triggers, no repetition while it remains
  paused.
- **Kill switch**: `[NOTAUS]` (kill switch) as soon as the kill-switch
  mechanism takes effect.
- **Errors**: `[FEHLER]` on unexpected errors in the buy cycle (e.g. API
  timeout), in addition to the log entry.
- **Daily summary**: `[TAGESZUSAMMENFASSUNG]` once per completed calendar
  day with the number of trades, spending and stop-loss status.

A Telegram outage, a wrong token or a network error never crashes the bot
or aborts a buy cycle – every error while sending is only logged (see
`dca_bot/notifier.py`).

### 7.3 Messages from Grid, Trend and Allocator

- **Grid bot:** `[GRID-KAUF]`/`[GRID-KAUF DRY-RUN]` (buy),
  `[GRID-VERKAUF]` (sale, with the realised profit/loss of this position),
  `[GRID-VERKAUF-FEHLGESCHLAGEN]` (sale failed),
  `[GRID-VERKAUF-GESPERRT]` (sale blocked), `[GRID-STOP-LOSS]`,
  `[GRID-NOTAUS]` (kill switch), `[GRID-FEHLER]` (error),
  `[GRID-DOPPELVERKAUF]` (double sale).
- **Trend-following bot:** `[TREND-EINSTIEG]`/`[TREND-EINSTIEG DRY-RUN]`
  (entry), `[TREND-AUSSTIEG]` (exit, with realised profit/loss and exit
  reason), `[TREND-VERKAUF-FEHLGESCHLAGEN]` (sale failed),
  `[TREND-AUSSTIEG-GESPERRT]` (exit blocked), `[TREND-STOP-LOSS]`,
  `[TREND-WARNUNG]` (warning), `[TREND-ABSICHERUNG-WIEDERHERGESTELLT]`
  (protection restored), `[TREND-NOTAUS]` (kill switch), `[TREND-FEHLER]`
  (error), `[TREND-TEILFUELLUNG]` (partial fill), `[TREND-DOPPELVERKAUF]`
  (double sale).
- **Capital allocator:** `[ALLOCATION-UPDATE]` (on a significant shift),
  `[ALLOCATOR-NOTAUS]` (kill switch), `[ALLOCATOR-FEHLER]` (error).
- **All four:** `[HEARTBEAT]` (sign of life, see section 6). Across bots
  also `[ORDER-UNKLAR]` (order unclear; look up: section 8.4),
  `[REKONZILIATION]` (reconciliation) and the `[…BESTAND-DISKREPANZ]`
  (holdings discrepancy) messages.

`[GRID-FEHLER]` and `[ALLOCATOR-FEHLER]` arrive only once per error type
until a cycle has succeeded again – further failures of the same kind
appear only in the log.

## 8. Tools

### 8.1 Position audit (check open positions)

```bash
python -m dca_bot.audit_positions
```

Lists the holdings of the **DCA, grid and trend bots**, each with its
**dry-run status**. Purely informational: the script only reads, changes
nothing in the ledger files and places no orders.

If Binance credentials are present, the script appends a cross-bot
reconciliation against the actual account balance (`--offline` switches
it off). Details and context: `trading-bot-project.en.md` section 7.5.

### 8.2 Backtests

```bash
python -m dca_bot.backtest             # DCA
python -m dca_bot.grid_backtest        # Grid
python -m dca_bot.trend_backtest       # Trend following
python -m dca_bot.allocator_backtest   # Allocator: combined vs. isolated
```

Results and their interpretation are in `trading-bot-projekt-archiv.md`
(German only; sections 5a, 6, 6f and 6i), the caveat on the grid price
range in `trading-bot-project.en.md` 7.2.

### 8.3 One-off data correction (dry-run amounts)

```bash
python -m dca_bot.fix_dry_run_quote_spent            # report only
python -m dca_bot.fix_dry_run_quote_spent --apply    # writes
```

One-off correction tool for the finding of 22.09.2026: recalculates
`quote_spent` and `realized_pnl` of affected dry-run entries. **Without
`--apply` nothing is written**, it only reports. Background and
properties: `trading-bot-projekt-archiv.md` (German only) section 6g
(„Folgefund aus K3“, follow-up finding from K3).

### 8.4 Looking up orders (e.g. after `[ORDER-UNKLAR]`)

```bash
python -m dca_bot.check_orders --client-order-id grid-7f3a9c2e14b84d6fa0e51c83
python -m dca_bot.check_orders             # overview of all three bots
```

With `--client-order-id` the script answers the question behind an
`[ORDER-UNKLAR]` message (the message includes the ready-made command):
does this order exist at Binance, and what has become of it? The symbol
follows from the prefix (`dca-`, `grid-`, `trend-`); `--symbol` overrides
it. It also checks the bot's own bookkeeping: is the ID still in its
pending file, is it in the ledger? The last line puts this into context,
e.g. "Executed, NOT yet in the ledger – the bot records the order in the
next cycle". A failed query says nothing about the order (exit code 2).

Without arguments it shows, for each symbol of the three bots, the price,
balance and the latest orders (`--limit`, default 10) with clientOrderId
and bot. This is also the **connection test**: if price and balance come
through, the connection and API keys work. (The former
`python -m dca_bot.test_connection` has been removed; it triggered a real
DCA purchase while trading was active.) The script only reads: it uses
the same client as the position audit (8.1), which structurally cannot
place orders.

## 9. Tests

```bash
python -m unittest discover -s tests -t .
```

All tests run without network access and without Binance credentials
(fake clients with the same interface as `binance_client.py`, temporary
ledger files). The safety-critical paths are covered: token hygiene of the
Telegram notifications, the real exchange-side stop-loss incl. race
conditions, the sell safety of Grid and Trend (dry-run positions, failed
real sales), and the connection to the real trading rules including fee
correction.

| Test file | Topic |
|---|---|
| `test_notifier` | Token hygiene of the Telegram messages (K5) |
| `test_order_utils`, `test_dca_fee_adjustment` | Trading rules, quantisation, fees (K3) |
| `test_grid_sell_safety` | Sell safety, trading rules and fill prices of the grid bot |
| `test_trend_stop_loss` | Exchange stop-loss, sell safety and fill prices of the trend bot |
| `test_pending_orders`, `test_order_reconciliation` | No order without a ledger entry, catch-up at startup (K2) |
| `test_process_lock`, `test_kill_switch` | Duplicate bot start, kill-switch paths |
| `test_stage_b_safety`, `test_stage_c_safety` | Review items stage B and C (incl. UTC window, ledger integrity, live switch, balance check) |
| `test_trend_decide_action`, `test_grid_signals`, `test_allocator_signals` | Decision logic of Trend, Grid and Allocator |
| `test_improvements_stage_1` | Allocator state file, global kill switch `STOP_ALL` |
| `test_startup_balance_check`, `test_audit_positions` | Consistency check at startup, position audit |
| `test_trend_auto_reset` | Analysis mode `--analyze-auto-reset` of the trend backtest |
| `test_fix_dry_run_quote_spent` | One-off data correction of the dry-run amounts |
| `test_request_timeout` | Request timeout of the grid bot |
| `test_heartbeat_last_cycle`, `test_cycle_error_notification` | Heartbeat timestamp, rate limit for cycle errors |
| `test_shared_account` | All bots on one shared account: partial fill, unclear sales, long run with ownership invariant |
| `test_check_orders` | Looking up orders (read-only), reconciliation with pending file and ledger |
| `test_strategy_entry_points` | Only the entry points use the trading strategies |
| `test_allocator_backtest` | Allocator backtest: stop-loss lock and consistency with the trend backtest |

What the individual tests check and how their effectiveness was measured
is described with the respective fixes in `trading-bot-projekt-archiv.md`
(German only; 6f, 6g, 6i), for newer ones in the "Log from 29.09.2026" in
`trading-bot-project.en.md`, supplemented there by 7.6.

## 10. Further documentation

Since 29.09.2026 the project document consists of two files (German
originals), plus an English translation of the first one.

`trading-bot-projekt.md` (English: `trading-bot-project.en.md`), the
current state:

- **Current status and open items:** operations, deploy status, dates,
  preconditions for real capital, deferred items
- **Log from 29.09.2026:** the ongoing progress log
- **Section 7:** Technical reference – all safety mechanisms and the core
  logic of the four components in detail

`trading-bot-projekt-archiv.md` (German only), planning, research and the
log up to 28.09.2026, moved unchanged:

- **Section 5 / 5a:** Research on the strategies, backtest of the allocator
- **Section 6:** Progress log incl. backtest results of DCA, Grid and Trend
- **Sections 6f-6i:** Exchange stop-loss, security review with all fixes
  (K1-K5, W1-W18), improvement proposals, system check of 27.09.2026 and
  symbol binding
