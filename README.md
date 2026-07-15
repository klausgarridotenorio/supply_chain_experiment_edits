# Supplier-Retailer Negotiation Experiment (Template)

A clean oTree template adapted from `Example_repository_for_inspiration`.
It implements the **structure** of the new experiment -- page routing, roles,
disclosure stage, the migrated negotiation interface with the Decision
Support Tool, the conditional effort-task stage, and the results layout.
Payoffs, the effort task itself, and the AI counterpart are deliberate stubs.

## Running

A ready-made virtualenv lives in `venv/` (oTree 6.0.15). Activate it first --
the machine's global oTree install is broken (incompatible `starlette`), and
`otree devserver` re-spawns `otree` from `PATH`, so the venv must be active:

```bash
cd supply_chain_experiment
source venv/bin/activate
otree devserver
```

(Or recreate the environment with `python3 -m venv venv && venv/bin/pip
install -r requirements.txt`.)

Then open the demo session **"Supplier-Retailer Negotiation (Two Human
Players)"** with two browser windows.

## Game flow (Two-Human path)

| # | Page                 | Who                          | What |
|---|----------------------|------------------------------|------|
| 1 | `Instructions`       | both                         | single page of text |
| 2 | `Disclosure`         | Retailer only                | disclose true RP / own value / nothing; the Supplier is IDLE on `DisclosureWaitPage` |
|   | `DisclosureReceived` | Supplier only                | the Supplier sees what the Retailer disclosed; the Retailer waits on `NegotiationWaitPage` |
| 3 | `Negotiation`        | both                         | chat + binding offers on wholesale price `w` and quantity `q`, with the DST tab (migrated 1:1 from the example repo) |
| 4 | `EffortTask`        | Supplier, **only if deal**   | untimed slider task (50 sliders, target 50) with always-available Next; Retailer idles on `ResultsWaitPage`. No deal -> both skip straight to the demand draw |
| 5 | `Results`           | both                         | drawn demand + payoff placeholders |

## Where things live

```
settings.py                  session configs (two_human_negotiation / single_player_ai stub)
common.py                    JsonField helper + base profit functions (UI/DST formulas)
experiment/
  constants.py               roles (ROLE_RETAILER_EMPLOYEE, ROLE_SUPPLIER_EMPLOYEE),
                             negotiation bounds, disclosure codes, bot timing
  models.py                  creating_session (pairs vs solo groups), Group
                             (market params, deal status, demand draw,
                             set_opponents, acting-RP helpers, set_payoffs
                             STUB) and Player (disclosure fields,
                             offers/chat, live handlers)
  pages.py                   the whole page flow + async live_method routing
  offer.py / optimal.py      offer container + evaluation machinery + Nash
                             benchmark and counter-offer solvers (repo port)
  bot_negotiation.py         the AI retailer (entry points, acting-RP config)
  bot_strategy.py            its decision core (evaluate/accept/counter)
  bot_messages.py            scripted chat + offer reader (LLM stand-in)
  templates/experiment/      page templates; tabs/ holds the Negotiation tabs
  static/experiment/         experiment.js (negotiation UI), analysis.js (DST),
                             chart.js (Chart.js v4), css, image
```

## The effort task (implemented)

`EffortTask` is an untimed slider task: 50 sliders (0-100, start at 0) that
must be dragged exactly onto 50, with a live "Sliders at target: X / 50"
counter. The Next button is never blocked. Recorded on the Player (written
by `static/experiment/js/effort_task.js` via hidden form inputs, saved on
the normal form submission -- also when leaving early):

* `effort_put_number_of_sliders` -- sliders exactly on target at submission,
* `effort_put_time_on_sliders` -- seconds spent on the page,
* `effort_put_relative_time_on_sliders` -- JSON array of ms-since-page-load
  at which each successive slider was durably placed (500 ms debounce;
  pacing logic adapted from the Qualtrics reference implementation).

## The AI retailer (Single-Player game, implemented)

Five session configs run a human Supplier alone against the AI retailer
(architecture ported from the example repository's NegotiationBot /
BotStrategy stack, driven by oTree 6 async live_methods):

| config                 | true RP | bot disclosure | negotiates on |
|------------------------|---------|----------------|---------------|
| `ai_rp5_disclose_true` | 5       | truthful: 5    | RP = 5        |
| `ai_rp5_disclose_lie`  | 5       | lies: 4        | RP = 4        |
| `ai_rp4_disclose_true` | 4       | truthful: 4    | RP = 4        |
| `ai_rp4_no_disclosure` | 4       | nothing        | RP = 4        |

**No full information:** the bot knows PC = 1 (common knowledge) but its
whole strategy -- profit functions, Nash target, accept decisions,
counter-offers (`offer.py` + `optimal.py`) -- runs on its ACTING retail
price (`Group.bot_acting_market_price`): the disclosed value when it
disclosed, otherwise 4 (`bot_no_disclosure_rp`). The true draw never enters
the strategy, and the Supplier-side DST/Nash benchmark also uses the acting
value so the true RP cannot leak. Chat text and the chat offer-reader are
scripted stand-ins for the repository's LLM stack -- see `TODO(llm)` in
`bot_messages.py` for the upgrade path.

Flow: the bot's disclosure is shown on `DisclosureReceived` (wait pages
release instantly for solo groups); the bot greets first on the Negotiation
page, evaluates every chat/interface offer, counters with binding offers
(idx = -1), and finalizes deals (`{'finished': True}` after a short delay).

## Payoffs (implemented -- `Group.set_payoffs` in `models.py`)

Identical rule in both game versions, all parameters in
`SESSION_CONFIG_DEFAULTS`:

* **Baseline** 5€ for everyone (oTree `participation_fee`).
* **Bonus** = `profit_share` (5%) of the REALIZED profit, computed after
  the demand draw; a negative profit earns no bonus.
    * Supplier: `w * min(q, D) - PC * q`
    * Retailer: `(effective RP - w) * min(q, D)`
* **Quality checks**: each slider the Supplier places exactly on target is
  a passed quality check and raises the RETAIL price by
  `quality_rp_per_slider` (0.02€), capped at `quality_rp_max` (+1€ = all
  50 sliders). This benefits ONLY the Retailer -- stated transparently in
  the Instructions and on the EffortTask page itself.
* **No deal**: both profits zero -> baseline only.
* **AI retailer**: its outcome is computed the same way -- with the TRUE
  drawn RP (its disclosure/acting price only shaped the negotiation) --
  and stored on the group: `bot_retailer_profit`, `bot_retailer_payment`
  (= 5€ + 5% of positive profit), plus `effective_market_price` /
  `quality_rp_increase` for both modes.
* **Results page** shows each participant their OWN outcome only (deal,
  demand, profit, payment breakdown); the Retailer additionally sees the
  quality-check breakdown. The Supplier never sees the effective RP or the
  Retailer's profit -- that would reveal the private retail price (and,
  vs the AI, whether it lied).

## Design notes / differences from the example repository

* **2 roles instead of 4** -- the manager/delegation layer is gone. Roles are
  assigned natively by oTree via the `ROLE_*` constants (id 1 = Retailer,
  id 2 = Supplier), so the repo's `session_patch.py` is unnecessary.
* **Deal status is group-level** -- `Group.deal_reached / deal_price /
  deal_quantity` (set in `Player.process_accept`) drive the conditional
  effort-task routing and the Results page. Per-player `*_accepted` fields
  are kept for exports and the future AI mode.
* **The retail price is private** -- the production cost is fixed (1€) and
  common knowledge, while RP is drawn (4€ or 5€, equal probability) and known
  only to the Retailer. The Supplier only sees the Retailer's disclosure (on
  the DisclosureReceived page and the Negotiate tab).
  **Exception, as requested:** the DST still receives the true
  `market_price` for both players (identical to the repo); see the NOTE in
  `Negotiation.js_vars` if that should be gated on disclosure later.
* **Demand draw** happens in `Group.draw_demand()` on `ResultsWaitPage`
  (an explicit "Demand Draw phase") instead of at session creation.
* The LLM stack (`bot_llm`, `bot_strategy`, `prompts/`, Ollama hosts,
  `session_patch`) was not migrated.
