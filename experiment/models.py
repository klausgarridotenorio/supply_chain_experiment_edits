"""
Structural models for the Supplier-Retailer negotiation experiment.

Design overview
===============
* 2 players per group: Retailer (id_in_group 1), Supplier (id_in_group 2).
  Roles are assigned natively by oTree from the ROLE_* constants.

* Single-Player game (ai_retailer=True): every human is a solo Supplier
  and `Player.other_id == C.BOT_ID` routes `Player.other` to the
  NegotiationBot (bot_negotiation.py). The bot has no player seat; the
  human's offers/chat_data JsonFields are the single source of truth.
  `Group.set_opponents()` is the single place where the human-vs-human /
  human-vs-AI wiring happens. The bot negotiates on its ACTING retail
  price (Group.bot_acting_market_price), never the true draw.

* Deal status is canonical on the Group (deal_reached / deal_price /
  deal_quantity) -- it drives the conditional Effort Task routing and the
  Results page. The per-player *_accepted fields are kept as well (repo
  convention, convenient for per-player data exports and for the AI mode).

* Payoffs (Group.set_payoffs): baseline €5 (oTree participation fee) plus
  5% of the realized post-demand profit; the Supplier's slider task raises
  the Retailer-side retail price by €0.02 per passed quality check (capped
  at +€1). The demand draw lives in Group.draw_demand().
"""
import json
import random
from functools import cached_property
from typing import Any, Union

from otree.api import *
from otree.database import LongStringField

from common import JsonField, retailer_profit, supplier_profit  # noqa: F401 (profit functions re-exported for the future payoff code)
from .bot_negotiation import NegotiationBot
from .constants import C
from .offer import Offer
from .optimal import nash_bargaining_solution, OPTIMAL_OFFER
from .utils import now_datetime


class Subsession(BaseSubsession):
    pass


def creating_session(subsession: Subsession):
    """Build the match structure, then draw the market parameters.

    PLAYERS_PER_GROUP is None, so the grouping is set explicitly here:
      * Two-Human game: participants are paired in order; within each pair,
        position 1 = Retailer and position 2 = Supplier (assigned natively
        by set_group_matrix from the ROLE_* constants).
      * Single-Player game (ai_retailer=True): every participant is a
        Supplier alone in their own group; the Retailer is the
        NegotiationBot (no player seat).
    """
    config = subsession.session.config
    _check_config(config)

    players = subsession.get_players()
    if config.get('ai_retailer', False):
        subsession.set_group_matrix([[p] for p in players])
        # set_group_matrix assigned the first role (Retailer) to every solo
        # player; in this mode every human is the Supplier.
        for player in subsession.get_players():
            player._role = C.ROLE_SUPPLIER_EMPLOYEE
    else:
        assert len(players) % 2 == 0, \
            'The Two-Human game needs an even number of participants'
        subsession.set_group_matrix(
            [players[i:i + 2] for i in range(0, len(players), 2)])

    for group in subsession.get_groups():
        group.initialize_group()
        # Negotiation-only demo: the wait pages (where set_opponents
        # normally runs) are skipped, so wire the human-vs-AI match here.
        if config.get('negotiation_only', False):
            group.set_opponents()


def _check_config(config: dict[str, Any]):
    assert config['market_price_high'] >= config['market_price_low']
    assert config['market_price_low'] > config['production_cost']
    assert config['demand_max'] > config['demand_min']
    if config.get('negotiation_only', False):
        assert config.get('ai_retailer', False), \
            'negotiation_only demos require ai_retailer=True'
    if config.get('ai_retailer', False):
        assert config['bot_disclosure'] in (
            C.DISCLOSE_TRUE, C.DISCLOSE_OWN, C.DISCLOSE_NONE)
        if config['bot_disclosure'] == C.DISCLOSE_OWN:
            assert config.get('bot_disclosed_value') is not None


class Group(BaseGroup):
    # ── Market parameters ────────────────────────────────────────────────
    # Retail price (RP): drawn per group (4 or 5, equal probability); the
    # Retailer's PRIVATE information and the subject of the Disclosure stage.
    market_price = models.IntegerField()
    # Production cost (PC): fixed (1), common knowledge.
    production_cost = models.IntegerField()
    # Demand (D): drawn in draw_demand() only after negotiation/effort.
    # NUM_DEMAND_DRAWS independent Uniform[demand_min, demand_max] draws
    # are stored in demand_draws; their AVERAGE is the realized demand
    # used in set_payoffs (hence a float).
    demand = models.FloatField()
    demand_draws = JsonField(initial=[])

    # ── Negotiation timing ────────────────────────────────────────────────
    # Epoch seconds of the FIRST load of the Negotiation page in this group
    # (set in pages.Negotiation.get_timeout_seconds). Anchors the hidden
    # hard cap on timer resets: once timeout_negotiation_hard_cap seconds
    # of real time have elapsed, the <30s offer reset is permanently
    # disabled for the round. Server-side only -- NEVER sent to the client
    # (the cap must stay invisible to participants).
    negotiation_start_epoch = models.FloatField()

    # ── Deal status (canonical; set in Player.process_accept) ────────────
    deal_reached = models.BooleanField(initial=False)
    deal_price = models.FloatField()      # agreed wholesale price w
    deal_quantity = models.IntegerField()  # agreed quantity q

    # ── Payoff results (set in set_payoffs) ──────────────────────────────
    # Quality checks: RP increase earned by the Supplier's slider task
    # (quality_rp_per_slider per slider on target, capped at
    # quality_rp_max). It benefits ONLY the Retailer's profit.
    quality_rp_increase = models.FloatField(initial=0)
    # RP actually used for the Retailer's realized profit:
    # market_price + quality_rp_increase.
    effective_market_price = models.FloatField(initial=0)
    # The AI retailer has no participant, so its outcome is stored here in
    # the Single-Player game -- computed exactly like a human Retailer's:
    # profit = (effective RP - w) * min(q, D), and
    # payment = participation_fee + profit_share * max(profit, 0).
    bot_retailer_profit = models.FloatField(initial=0)
    bot_retailer_payment = models.CurrencyField(initial=0)

    # Nash benchmark shown on the DST "Profit Analysis" tab.
    optimal_offer = JsonField(initial={})

    # ── Convenience accessors ────────────────────────────────────────────
    @property
    def is_ai_mode(self) -> bool:
        """True in the Single-Player game (human Supplier vs AI retailer)."""
        return bool(self.session.config.get('ai_retailer', False))

    @property
    def retailer(self) -> 'Player':
        # Only exists in the Two-Human game; the AI retailer has no seat.
        return self.get_player_by_role(C.ROLE_RETAILER_EMPLOYEE)

    @property
    def supplier(self) -> 'Player':
        return self.get_player_by_role(C.ROLE_SUPPLIER_EMPLOYEE)

    def _realized_disclosure(self) -> tuple[str | None, float | None]:
        """(choice, disclosed value) -- from the human Retailer's decision
        in the Two-Human game, or from the session config (the bot's
        scripted disclosure behavior) in the Single-Player game."""
        if self.is_ai_mode:
            config = self.session.config
            choice = config['bot_disclosure']
            if choice == C.DISCLOSE_TRUE:
                return choice, float(self.market_price)
            if choice == C.DISCLOSE_OWN:
                return choice, float(config['bot_disclosed_value'])
            return choice, None
        retailer = self.retailer
        return (retailer.field_maybe_none('disclosure_choice'),
                retailer.field_maybe_none('disclosed_value'))

    @property
    def disclosure_message(self) -> str:
        """What the Supplier gets to see about the Retailer's retail price.
        Deliberately worded identically for a TRUE and an OWN (made-up)
        value, so the Supplier cannot distinguish the two. Returns '' when
        nothing was (or has yet been) disclosed -- NOT None, because oTree
        raises on template access to attributes that resolve to None."""
        choice, value = self._realized_disclosure()
        if choice in (C.DISCLOSE_TRUE, C.DISCLOSE_OWN) and value is not None:
            return (f"The Retailer disclosed a Retail Price (RP) "
                    f"of €{value:g}.")
        return ''

    @property
    def bot_acting_market_price(self) -> int:
        """The retail price the AI retailer NEGOTIATES with: its profit
        functions, Nash target and counter-offers all use this value.

        Follows the disclosure when possible: the disclosed value (true or
        a lie); with no disclosure, the bot negotiates as if it had
        disclosed the fallback value (config bot_no_disclosure_rp = 4)."""
        choice, value = self._realized_disclosure()
        if choice in (C.DISCLOSE_TRUE, C.DISCLOSE_OWN) and value is not None:
            return int(value)
        return int(self.session.config.get('bot_no_disclosure_rp', 4))

    @property
    def formatted_optimal_offer(self) -> str:
        price, quantity = self.optimal_offer['offer']
        profit = self.optimal_offer['profit']
        return OPTIMAL_OFFER % (price, quantity, profit)

    # ── Lifecycle ────────────────────────────────────────────────────────
    def initialize_group(self):
        """Called from creating_session: draw the market parameters."""
        config = self.session.config
        self.market_price = random.randint(config['market_price_low'],
                                           config['market_price_high'])
        self.production_cost = config['production_cost']
        # Nash benchmark shown on the DST tab. In the Single-Player game it
        # is computed from the bot's ACTING retail price (the Supplier's
        # information environment) -- using the true draw would leak it.
        benchmark_rp = (self.bot_acting_market_price if self.is_ai_mode
                        else self.market_price)
        self.optimal_offer = nash_bargaining_solution(benchmark_rp,
                                                      self.production_cost)

    def set_opponents(self):
        """Wire up who negotiates with whom. Runs once, when the group
        reaches the NegotiationWaitPage (i.e. after the Disclosure stage
        and BEFORE anyone sees the Negotiation page)."""
        if self.is_ai_mode:
            # SINGLE-PLAYER game: the solo Supplier faces the AI retailer.
            supplier = self.supplier
            supplier.other_id = C.BOT_ID  # routes Player.other to the bot
            supplier.is_active = True
        else:
            # TWO-HUMAN game: link the two players to each other.
            retailer, supplier = self.retailer, self.supplier
            retailer.other_id = supplier.id_in_group
            supplier.other_id = retailer.id_in_group
            retailer.is_active = supplier.is_active = True

    def draw_demand(self):
        """Demand Draw phase: NUM_DEMAND_DRAWS independent uniform integer
        draws; their AVERAGE is the realized demand used for the payoffs.
        All draws are revealed on the Results page."""
        config = self.session.config
        draws = [random.randint(config['demand_min'], config['demand_max'])
                 for _ in range(C.NUM_DEMAND_DRAWS)]
        self.demand_draws = draws
        self.demand = sum(draws) / len(draws)

    def set_payoffs(self):
        """Final payoffs, identical rule for both game versions:

        pay = participation_fee (€5 baseline, handled natively by oTree)
              + profit_share (5%) * max(realized profit, 0)

        Realized profits use the DRAWN demand:
          Supplier: w * min(q, D) - PC * q          (RP plays no role)
          Retailer: (effective RP - w) * min(q, D)

        The Supplier's slider task acts as quality checks: each slider on
        target raises the RETAIL price by quality_rp_per_slider (capped at
        quality_rp_max), so the effort benefits ONLY the Retailer. In the
        Single-Player game the AI retailer's outcome is computed the same
        way -- with the TRUE drawn RP, regardless of what it disclosed --
        and stored in bot_retailer_profit / bot_retailer_payment.

        No deal (impasse/timeout): both profits are zero -> baseline only.
        """
        config = self.session.config
        share = config['profit_share']
        supplier = self.supplier

        supplier_profit_realized = 0.0
        retailer_profit_realized = 0.0
        self.quality_rp_increase = 0.0
        self.effective_market_price = float(self.market_price)

        if self.deal_reached:
            quantity_sold = min(self.deal_quantity, self.demand)
            quantity_unsold = max(0, self.deal_quantity - self.demand)

            # Quality checks from the effort task (Supplier's sliders).
            self.quality_rp_increase = min(
                supplier.effort_put_number_of_sliders
                * config['quality_rp_per_slider'],
                config['quality_rp_max'])
            self.effective_market_price = (self.market_price
                                           + self.quality_rp_increase)

            supplier_profit_realized = supplier_profit(
                self.deal_price, self.production_cost,
                quantity_sold, quantity_unsold)
            retailer_profit_realized = retailer_profit(
                self.effective_market_price, self.deal_price, quantity_sold)

        # ── Supplier (human in both game versions) ───────────────────────
        supplier.profit = supplier_profit_realized
        supplier.payoff = cu(max(supplier_profit_realized, 0) * share)

        # ── Retailer (human seat or the AI's group-level record) ─────────
        if self.is_ai_mode:
            self.bot_retailer_profit = retailer_profit_realized
            self.bot_retailer_payment = cu(
                config['participation_fee']
                + max(retailer_profit_realized, 0) * share)
        else:
            retailer = self.retailer
            retailer.profit = retailer_profit_realized
            retailer.payoff = cu(max(retailer_profit_realized, 0) * share)


class Player(BasePlayer):
    # ── Opponent wiring (set in Group.set_opponents) ─────────────────────
    # id_in_group of the human opponent; C.BOT_ID (-1) means "AI bot" (or
    # "not yet wired" -- set_opponents always runs before the Negotiation
    # page).
    other_id = models.IntegerField(initial=-1)
    # False = seat that skips the Negotiation page (not wired yet).
    is_active = models.BooleanField(initial=False)

    # ── Comprehension check (5 questions right after the Instructions;
    #    every HUMAN player, in both game versions; repo port) ────────────
    # The current answer field (one page per question, values regenerate
    # after a wrong answer).
    comprehension_check = models.FloatField(min=-999999999)
    # Full answer history / attempt counters per question, JSON-encoded
    # (kept as LongStringFields exactly like the example repository).
    comprehension_answer = LongStringField(
        initial=json.dumps({i: [] for i in range(1, 6)}))
    comprehension_attempts = LongStringField(
        initial=json.dumps({str(i): 1 for i in range(1, 6)}))

    # ── Disclosure stage (filled by the Retailer only) ───────────────────
    disclosure_choice = models.StringField(
        choices=[
            [C.DISCLOSE_TRUE, 'True value disclosure'],
            [C.DISCLOSE_OWN, 'Input your own value'],
            [C.DISCLOSE_NONE, 'No disclosure'],
        ],
        widget=widgets.RadioSelect,
        label='Your disclosure decision:',
    )
    # The retail-price value shown to the Supplier. Normalized in
    # Disclosure.before_next_page: the true RP for DISCLOSE_TRUE, the
    # Retailer's input for DISCLOSE_OWN, empty for DISCLOSE_NONE.
    # TODO(design): tighten min/max once the disclosure rules are final.
    disclosed_value = models.FloatField(
        blank=True, min=0,
        label='The value you want to disclose to the Supplier (€):',
    )

    # ── Negotiation stage ────────────────────────────────────────────────
    price_proposed = models.FloatField()
    quantity_proposed = models.IntegerField()
    price_accepted = models.FloatField()
    quantity_accepted = models.IntegerField()

    offers = JsonField(initial=[])     # full offer history [{idx, price, quantity, stamp}]
    chat_data = JsonField(initial=[])  # chat transcript   [{nick, body}]

    time_start = models.StringField(max_length=20)
    time_end = models.StringField(max_length=20)

    # ── Effort stage (Supplier only; slider task) ────────────────────────
    # All three fields are written by the EffortTask page's JavaScript
    # through hidden form inputs (see EffortTask.html + effort_task.js), so
    # they are saved via the regular oTree form submission when the Supplier
    # clicks Next -- including when they leave early with an unfinished grid.
    effort_put_number_of_sliders = models.IntegerField(
        initial=0, min=0, max=C.NUM_SLIDERS,
        doc="Final score: sliders exactly at the target when Next was "
            "clicked",
    )
    effort_put_time_on_sliders = models.FloatField(
        initial=0,
        doc="Total seconds spent on the EffortTask page before clicking "
            "Next",
    )
    effort_put_relative_time_on_sliders = LongStringField(
        initial='[]',
        doc="JSON array of ms-since-page-load at which the k-th slider was "
            "durably placed on target (pacing_timestamps logic adapted from "
            "the Qualtrics reference implementation)",
    )

    # ── Results (placeholder until the payoff logic exists) ──────────────
    profit = models.FloatField(initial=0)

    # ── Role helpers ─────────────────────────────────────────────────────
    @property
    def is_supplier(self) -> bool:
        return self.role == C.ROLE_SUPPLIER_EMPLOYEE

    @property
    def is_retailer(self) -> bool:
        return self.role == C.ROLE_RETAILER_EMPLOYEE

    # ── Opponent helpers (identical semantics to the example repository) ─
    @cached_property
    def other(self) -> Union['Player', NegotiationBot]:
        if self.other_id == C.BOT_ID:
            return NegotiationBot(self)
        return self.group.get_player_by_id(self.other_id)

    @property
    def bot_opponent(self) -> bool:
        return self.other_id == C.BOT_ID

    @property
    def proposal(self) -> str:
        """Current own proposal, formatted for the interface table."""
        price = self.field_maybe_none('price_proposed')
        quantity = self.field_maybe_none('quantity_proposed')
        if None not in (price, quantity):
            return f"€ {price}<br>{quantity}"
        return '(none)<br> '

    @property
    def live_ids(self) -> list[int]:
        """ids that live_method responses should be broadcast to (bots have
        no live connection, hence the > 0 filter)."""
        return [idx for idx in [self.id_in_group, self.other_id] if idx > 0]

    # ── live_method handlers (called from pages.Negotiation) ─────────────
    def process_offer(self, price: float, quantity: int) -> list[dict]:
        """A binding offer submitted through the interface. Against a bot,
        only this player's offers field exists (single source of truth);
        the bot's reaction is driven by the live_method afterwards."""
        self.price_proposed = price
        self.quantity_proposed = quantity

        offer = Offer(idx=self.id_in_group, price=price, quantity=quantity)
        # JsonField: reassign, never append in place.
        self.offers = self.offers + [offer]
        if not self.bot_opponent:
            self.other.offers = self.other.offers + [offer]
        return self.offers

    def process_accept(self, price: float, quantity: int):
        """The player accepts the counterpart's standing offer, which makes
        the deal binding and ends the negotiation."""
        self.time_end = now_datetime()
        self.price_accepted = price
        self.quantity_accepted = quantity

        if not self.bot_opponent:
            # Sanity check: what was accepted is what was on the table.
            assert price == self.other.price_proposed
            assert quantity == self.other.quantity_proposed
            self.other.time_end = self.time_end
            self.other.price_accepted = price
            self.other.quantity_accepted = quantity

        # Canonical deal status: drives the conditional EffortTask page and
        # the Results page.
        self.group.deal_reached = True
        self.group.deal_price = price
        self.group.deal_quantity = quantity

    def process_chat(self, data: dict[str, Any]) -> dict[int, Any]:
        """A (non-binding) chat message from this player. Against a bot,
        the bot's reaction is driven by the live_method afterwards."""
        body = data['body']

        self.chat_data = self.chat_data + [
            {'nick': f"{self.role} (Me)", 'body': body}]
        result = {self.id_in_group: {'chat': self.chat_data}}

        if not self.bot_opponent:
            self.other.chat_data = self.other.chat_data + [
                {'nick': self.role, 'body': body}]
            result[self.other.id_in_group] = {'chat': self.other.chat_data}

        return result

    def process_llm_output(self, role: str, body: str) -> dict[str, Any]:
        """Store a chat line spoken by the AI counterpart and build the
        live payload for it (name kept from the example repository)."""
        self.chat_data = self.chat_data + [{'nick': role, 'body': body}]
        return {'chat': self.chat_data}
