# Supplier–Retailer Negotiation Experiment — Overview

A two-role oTree experiment on **negotiation under private information**. A
Retailer and a Supplier bargain over a **wholesale price (w)** and a
**quantity (q)** for a product (10 kg pellet bags). The twist is that one
market parameter is private, and the Retailer decides how much of it to
reveal before bargaining begins.

## Core parameters

| Symbol | Meaning | Value | Known to |
|--------|---------|-------|----------|
| **PC** | Production cost | 1 (fixed) | Common knowledge |
| **RP** | Retail price | drawn from {4, 5}, equal prob. | **Retailer's private info** |
| **w** | Wholesale price | 1–5€, 2 decimals | Negotiated |
| **q** | Quantity | 1–100 integer | Negotiated |
| **D** | Demand | Uniform[0, 100], drawn *after* bargaining | Revealed on Results |

**Realized profits** (after the demand draw, with sold = min(q, D)):
- Supplier: `w · min(q, D) − PC · q` (bears unsold-inventory risk)
- Retailer: `(RP − w) · min(q, D)`

**Payment**: everyone gets a 5€ baseline (participation fee) plus **5% of
their own realized profit** (no negative bonus).

## Two game modes

- **Two-Human game** (`two_human_negotiation`): a real Retailer (id 1) and
  Supplier (id 2) are paired.
- **Single-Player game** (5 `ai_*` configs): every human is a **Supplier**
  negotiating against an **AI Retailer** bot. RP is fixed per treatment and
  the bot's disclosure behavior is scripted: RP=5 × {truthful, lie→4, none}
  and RP=4 × {truthful, none}.

## Page flow

1. **Instructions** → **Comprehension Check** (5 profit-calculation
   questions; wrong answers show the worked solution and regenerate).
2. **Disclosure** (Retailer only): the Retailer clicks one of three
   buttons — **Disclose 4**, **Disclose 5**, or **No Disclosure**. The
   Supplier idles on a wait page. The choice is re-derived server-side: a
   disclosed value equal to the true RP is stored as a *truthful*
   disclosure, anything else as an *own/made-up* value — so a Retailer with
   RP=4 who clicks "Disclose 5" is recorded as lying. **DisclosureReceived**
   then shows the Supplier what was disclosed (a truthful and a fabricated
   value are worded identically, so the Supplier can't tell them apart).
3. **Negotiation** (both active): live chat + binding price/quantity offers,
   with a **Decision Support System (DSS)** tab. See timer and DSS notes
   below.
4. **Disclosure Reveal** (Supplier only, *only if a deal was reached*):
   restates what the Retailer disclosed, then reveals the **actual RP** —
   exposing any lie — before the effort task.
5. **Effort Task** (Supplier only, only after a deal): an untimed 50-slider
   task acting as **quality checks**. Each slider on target raises the
   *Retailer's* effective RP by 0.02€ (capped at +1€), so the Supplier's
   effort benefits only the Retailer.
6. Demand draw → **Results** (each participant sees only their own outcome;
   the Supplier never learns the effective RP).

## Negotiation page mechanics

**Decision Support System (DSS) tab.** Instead of one absolute "optimal
offer" (which would leak the true RP), it shows **two conditional Nash
offers** — one assuming RP=4, one assuming RP=5 — plus an interactive
what-if graph. The user picks a hypothetical RP from a **dropdown**
(defaults to 4), enters a wholesale price and quantity, and the graph and
expected profit split recompute live from the chosen RP.

**Visible timer with a 30-second reset.** The countdown starts at 5 minutes.
If it drops **below 30 seconds** and *either* player makes a binding offer,
it resets to exactly 30 seconds — keeping an active negotiation alive.

**Hidden 10-minute hard cap.** Total real time since the negotiation page
first loaded is tracked **server-side only** (never sent to the browser).
Once 10 minutes have elapsed, the 30-second reset is permanently disabled
for the round: further offers no longer touch the timer, which simply runs
down to 0 and ends the negotiation. Participants never see this cap.

## The AI Retailer (Single-Player game)

The bot is a **hybrid**: a deterministic economic solver makes every
*decision*, while a local **llama3** model (via Ollama) writes the
natural-language chat and a dedicated *offer-reader* model extracts offers
out of the human's free-text messages.

**No full information.** The bot never negotiates on the true RP. It uses
its **acting RP** = the value it disclosed (truthful or a lie), or 4 when it
disclosed nothing. Its profit functions, Nash target, counter-offers, and
even its LLM system prompt all run on this acting RP.

**Reading the human's offer.** Each chat message is parsed for `(w, q)`:
first a fast numeric pass (spacy, when available), then the offer-reader LLM
that returns a strict `[Price, Quantity]`. A message may yield a **complete**
offer (both terms), a **partial** offer (one term), or **no** offer.

**Deciding.** A complete offer is `evaluate()`d: if its expected profit to
the bot meets the bot's Nash target, the bot **accepts** (announces
acceptance, then finalizes/asks the human to confirm). Otherwise the bot
computes optimal **counter-terms** with the solver and asks llama3 to phrase
a reply *anchored to those exact terms*. To keep chat and numbers
consistent, it generates up to 3 candidate messages, reads the offer back
out of each, and sends the first self-consistent one. If every LLM host is
unreachable, scripted fallback lines keep the negotiation moving.

---

## Bot logic on **partial** offers (only a price, or only a quantity)

This is the case where the human proposes just **one** term. The bot's job
is to **hold the term the human gave and fill in the missing one** with the
value that hits its own Nash target profit — never to throw the human's term
away (unless that term is infeasible).

### Step 1 — Classify the partial offer (`Offer.evaluate`)

- **Only a wholesale price `w`** (quantity is `None`), and `w` is in range:
  the bot checks whether it can *still reach its Nash target profit* at that
  price (`_is_price_feasible`).
  - Feasible → evaluation **`OFFER_PRICE`** ("price given, quantity
    missing").
  - Not feasible → **`NOT_PROFITABLE_ON_BOTH`** (the price alone already
    rules out a good deal).
- **Only a quantity `q`** (price is `None`), and `q` is in range: the bot
  checks whether a profitable price still exists at that quantity
  (`_is_quantity_feasible`).
  - Feasible → evaluation **`OFFER_QUANTITY`** ("quantity given, price
    missing").
  - Not feasible → **`NOT_PROFITABLE_ON_BOTH`**.
- A single term that is **out of range** (e.g. w=9, or q=250) →
  **`INVALID_OFFER`**.

### Step 2 — Compute the completing term (`optimal_counter_offer`)

- **`OFFER_PRICE`** (human fixed the price) → `optimal_quantity_for_wholesale_price`:
  **keep the human's price `w`**, and find the **quantity** that (1) still
  yields the bot at least its Nash target profit and (2) among those,
  **maximizes the human's (Supplier's) profit**. Result: `(w, q*)`.
- **`OFFER_QUANTITY`** (human fixed the quantity) → `optimal_wholesale_price_for_quantity`:
  **keep the human's quantity `q`**, and solve for the **wholesale price**
  that gives the bot *exactly* its Nash target profit (rounded down to stay
  at or above target). Result: `(w*, q)`.
- If the fixed term was **infeasible** (`NOT_PROFITABLE_ON_BOTH`) or the
  solver finds no valid completion → the bot **abandons anchoring** and
  proposes the full symmetric **Nash bargaining offer** `(w_nash, q_nash)`
  instead.

So the intent is: *"I'll take the number you gave me and meet you with the
matching number that makes this work for me while being as good as possible
for you."*

### Step 3 — Phrase it and post it as a binding counter-offer

The evaluation selects the matching prompt fragment, and the solver's
completed offer is injected into it as the `optimal_offer`:

| Human gave | Evaluation | Solver keeps | Prompt fragment |
|------------|-----------|--------------|-----------------|
| only price | `OFFER_PRICE` | the price, computes q | `offer_without_quantity_prompt` → *Not_Quantity_Send_Optimal_Offer* |
| only quantity | `OFFER_QUANTITY` | the quantity, computes w | `offer_without_price_prompt` → *Not_Price_Send_Optimal_Offer* |
| infeasible single term | `NOT_PROFITABLE_ON_BOTH` | neither (Nash) | `offer_with_single_unfavourable_term_prompt` → *single_term_unfavourable_send_nash* |

llama3 turns that into a short natural message (e.g. *"With that wholesale
price I could do a quantity of 75 units — I've put that offer in the
interface."*), the retry loop confirms the message's numbers match the
solver's terms, and the completed `(w, q)` is appended to the offer list as
the bot's binding proposal (idx = BOT_ID). It appears in the human's
interface as the bot's current offer, ready to accept.

### Worked example (acting RP = 4, PC = 1; Nash target ≈ 56.25)

- Human chats *"how about a wholesale price of 3.90?"* → only a price.
  Evaluation `OFFER_PRICE`. The bot keeps 3.90€ and searches for the
  quantity that meets its target while maximizing the Supplier's profit,
  then replies with `(3.90€, q*)`.
- Human chats *"let's do a quantity of 60 units"* → only a quantity.
  Evaluation `OFFER_QUANTITY`. The bot keeps 60 units and solves for the
  wholesale price that gives it exactly its Nash target, replying with
  `(w*, 60)`.
