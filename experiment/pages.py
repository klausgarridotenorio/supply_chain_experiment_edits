"""
Page flow (Two-Human path; the Single-Player path reuses it with the
Retailer seat idle):

  1. Instructions          both            single page of text
     ComprehensionCheck1-5 every human     5 profit-calculation questions
                                           (wrong answer -> worked solution
                                           + fresh values; repo port)
  2. Disclosure            RETAILER only   private-information decision about
                                           the retail price (RP);
     DisclosureWaitPage    both            the Supplier is IDLE here while
                                           the Retailer decides
     DisclosureReceived    SUPPLIER only   the Supplier sees what the
                                           Retailer disclosed, then proceeds;
     NegotiationWaitPage   both            the Retailer waits here meanwhile
  3. Negotiation           both active     chat + binding offers + DST
                                           (migrated 1:1 from the repo)
  4. EffortTask            SUPPLIER only,  placeholder task + Next button;
                           only if a deal  skipped entirely when no deal
     ResultsWaitPage       both            the Retailer IDLES here while the
                                           Supplier works; on arrival of all:
                                           demand draw + payoff stub
  5. Results               both            demand + payoff placeholders

Negotiation-only demo (demo_* configs, negotiation_only=True): every page
above except Negotiation is skipped; set_opponents runs in creating_session
instead of the NegotiationWaitPage, and DemoResults closes the session.
"""
import json
import random
import time
from typing import Any

from otree.api import *

from common import retailer_profit, supplier_profit
from .comprehension import (get_error_message, RETAILER_PROFIT_CALC,
                            SUPPLIER_PROFIT_CALC)
from .constants import C
from .models import Player, Group
from .utils import now_datetime


def negotiation_only(player: Player) -> bool:
    """True in the standalone demo (demo_* session configs): only the
    Negotiation page (plus a minimal outcome page) is shown; every other
    page's is_displayed is gated on this."""
    return bool(player.session.config.get('negotiation_only', False))


################################################################################
# 1. Instructions
################################################################################

class Instructions(Page):
    """Single page of instructions text (see Instructions.html)."""

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return not negotiation_only(player)

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        config = player.session.config

        # "€4 or €5" -- same presentation helper as the example repository
        # (€ prefixed per value so the joined phrase reads unambiguously).
        prices = [f"€{x}" for x in range(config['market_price_low'],
                                         config['market_price_high'] + 1)]
        retail_prices = (' or '.join([', '.join(prices[:-1]), prices[-1]])
                         if len(prices) > 1 else prices[0])

        return {
            'retail_prices': retail_prices,
            'demand_interval': f"[{config['demand_min']}, "
                               f"{config['demand_max']}]",
            'timeout_minutes': config['timeout_negotiation'] // 60,
            'is_ai_mode': config.get('ai_retailer', False),

            # Compensation / quality-check parameters (transparency).
            'formatted_baseline': f"{float(config['participation_fee']):.2f}",
            'profit_share_pct': f"{config['profit_share'] * 100:g}",
            'quality_rp_per_slider':
                f"{config['quality_rp_per_slider']:.2f}",
            'quality_rp_max': f"{config['quality_rp_max']:.2f}",
        }


################################################################################
# 1b. Comprehension check (5 profit-calculation questions, repo port)
################################################################################

class ComprehensionCheck1(Page):
    """Profit-calculation comprehension check, ported from the example
    repository (intro app). Five questions, one page each, shown to EVERY
    human player right after the Instructions -- in both the Two-Human and
    the Single-Player game (there the solo Supplier answers them).

    A wrong answer keeps the player on the page, shows the full worked
    solution (see comprehension.py), and regenerates fresh hypothetical
    prices; quantity and demand are fixed per question (QUANTITY_DEMAND).
    All answers and attempt counts are recorded on the player.
    """
    form_model = 'player'
    form_fields = ['comprehension_check']
    template_name = 'experiment/ComprehensionCheck.html'

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return not negotiation_only(player)

    # question index -> (quantity, demand): mixes over-, under- and
    # exactly-met demand, so the min(q, D) logic is exercised.
    QUANTITY_DEMAND = {
        1: (10, 90),
        2: (90, 10),
        3: (50, 50),
        4: (70, 80),
        5: (40, 30),
    }

    @classmethod
    def get_page_idx(cls) -> int:
        return int(cls.__name__[-1])

    @classmethod
    def vars_for_template(cls, player: Player) -> dict[str, Any]:
        def next_question():
            # Hypothetical values consistent with THIS game's parameters:
            # PC is fixed (common knowledge), the retail price is a draw
            # like the real one (4 or 5), and the wholesale price lies
            # strictly between the two.
            market_price = random.randint(config['market_price_low'],
                                          config['market_price_high'])
            production_cost = config['production_cost']
            price = random.randint(production_cost + 1, market_price - 1)

            # Calculate the correct profit based on the player's role
            quantity_sold = min(quantity, demand)
            quantity_unsold = max(0, quantity - demand)
            if player.is_retailer:
                profit = retailer_profit(market_price, price, quantity_sold)
            else:
                profit = supplier_profit(price, production_cost,
                                         quantity_sold, quantity_unsold)

            return {
                'market_price': market_price,
                'production_cost': production_cost,
                'price': price,
                'quantity': quantity,
                'demand': demand,
                'profit': profit,
            }

        config = player.session.config
        var_dict = player.participant.vars

        page_idx = cls.get_page_idx()
        quantity, demand = cls.QUANTITY_DEMAND[page_idx]

        # Generate new values if first time on this question or after error
        if page_idx not in var_dict.keys():
            var_dict[page_idx] = next_question()

        return {
            'market_price': var_dict[page_idx]['market_price'],
            'production_cost': var_dict[page_idx]['production_cost'],
            'price': var_dict[page_idx]['price'],
            'quantity': var_dict[page_idx]['quantity'],
            'demand': var_dict[page_idx]['demand'],
            'question_number': page_idx,
            'total_questions': len(cls.QUANTITY_DEMAND),
        }

    @classmethod
    def error_message(cls, player: Player, values) -> str | None:
        """Validate the answer; on a mistake, show the worked solution and
        regenerate the question values (repo logic)."""
        var_dict = player.participant.vars

        page_idx = cls.get_page_idx()
        comprehension_attempts = json.loads(player.comprehension_attempts)
        page_attempts = comprehension_attempts[str(page_idx)]

        answer = values['comprehension_check']
        correct = var_dict[page_idx]['profit']

        # Store answer
        comprehension_answer = json.loads(player.comprehension_answer)
        comprehension_answer[str(page_idx)].append(answer)
        player.comprehension_answer = json.dumps(comprehension_answer)

        if answer == correct:
            return None

        # Increase the number of attempts
        comprehension_attempts[str(page_idx)] = page_attempts + 1
        player.comprehension_attempts = json.dumps(comprehension_attempts)

        # Pop question and clear for new generation
        question = var_dict.pop(page_idx)

        market_price = question['market_price']
        price = question['price']
        production_cost = question['production_cost']
        quantity = question['quantity']
        demand = question['demand']
        quantity_sold = min(quantity, demand)
        quantity_unsold = max(0, quantity - demand)

        if player.is_retailer:
            profit_calc = RETAILER_PROFIT_CALC % (
                market_price, price, quantity_sold, correct)
        else:
            profit_calc = SUPPLIER_PROFIT_CALC % (
                price, production_cost, quantity_sold,
                production_cost, quantity_unsold, correct)

        return get_error_message(player, profit_calc,
                                 market_price, price, production_cost,
                                 quantity, demand)


class ComprehensionCheck2(ComprehensionCheck1):
    pass


class ComprehensionCheck3(ComprehensionCheck1):
    pass


class ComprehensionCheck4(ComprehensionCheck1):
    pass


class ComprehensionCheck5(ComprehensionCheck1):
    pass


################################################################################
# 2. Private information disclosure (Retailer decision, Supplier idle)
################################################################################

class Disclosure(Page):
    """The Retailer (buyer) decides what to tell the Supplier about the
    retail price by clicking one of three buttons: Disclose 4, Disclose 5,
    or No Disclosure. The clicked button fills the (hidden) form fields and
    submits the page; the mapping onto disclosure_choice (true/own/none) is
    re-derived server-side in before_next_page, so the stored choice is
    authoritative regardless of what the client sent.
    The Supplier is IDLE on the DisclosureWaitPage in the meantime."""
    form_model = 'player'
    form_fields = ['disclosure_choice', 'disclosed_value']

    # The two Retail Price values a Retailer can claim (the RP draw domain).
    DISCLOSABLE_VALUES = (4, 5)

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_retailer and not negotiation_only(player)

    @staticmethod
    def js_vars(player: Player) -> dict[str, Any]:
        # Lets the page JS fill the hidden form fields without hardcoding
        # the choice values.
        return {
            'disclose_true': C.DISCLOSE_TRUE,
            'disclose_own': C.DISCLOSE_OWN,
            'disclose_none': C.DISCLOSE_NONE,
            'market_price': player.group.market_price,
        }

    @staticmethod
    def error_message(player: Player, values) -> str | None:
        if values['disclosure_choice'] == C.DISCLOSE_NONE:
            return None
        if values['disclosed_value'] not in Disclosure.DISCLOSABLE_VALUES:
            return ('Please make your choice by clicking one of the '
                    'buttons.')

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        # Normalize: store exactly what the Supplier will get to see, and
        # re-derive the choice category from the disclosed value vs. the
        # true RP (a disclosed value equal to the draw counts as a true
        # disclosure, anything else as an own/made-up value).
        if player.disclosure_choice == C.DISCLOSE_NONE:
            player.disclosed_value = None
        elif player.disclosed_value == player.group.market_price:
            player.disclosure_choice = C.DISCLOSE_TRUE
        else:
            player.disclosure_choice = C.DISCLOSE_OWN


class DisclosureWaitPage(WaitPage):
    """The Supplier is IDLE here, waiting to see what the buyer will
    disclose. Releases as soon as the Retailer submits the Disclosure
    page."""
    title_text = "Please wait"
    body_text = ("The Retailer is making their disclosure decision. "
                 "You will see the outcome next.")

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return not negotiation_only(player)


class DisclosureReceived(Page):
    """Second disclosure page: the Supplier is shown what the Retailer
    disclosed (or that nothing was disclosed) before entering the
    negotiation. The Retailer skips this page and waits on the
    NegotiationWaitPage. In the negotiation-only demo it is skipped: the
    bot's disclosure banner on the Negotiation page (prices tab) carries
    the same information."""

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_supplier and not negotiation_only(player)


class NegotiationWaitPage(WaitPage):
    """The Retailer waits here while the Supplier reviews the disclosure.
    Once both arrive, the opponents are wired up (human-human, or human-AI
    in the single-player game)."""
    title_text = "Please wait"
    body_text = "Waiting for the other participant. The negotiation starts next."

    @staticmethod
    def is_displayed(player: Player) -> bool:
        # Negotiation-only demo: skipped -- set_opponents already ran in
        # creating_session (models.py).
        return not negotiation_only(player)

    @staticmethod
    def after_all_players_arrive(group: Group):
        group.set_opponents()


################################################################################
# 3. Negotiation (interface + DST migrated from the example repository)
################################################################################

class Negotiation(Page):
    """Live negotiation: free-form chat plus binding price/quantity offers,
    with the Decision Support Tool always visible on the right half of the
    single-screen layout (no tabs; see Negotiation.html).

    Timer-reset rule: once the countdown has dropped below
    TIMER_RESET_SECONDS, every NEW binding offer (from either player)
    resets it to exactly TIMER_RESET_SECONDS. Server side, the deadline
    lives in participant._timeout_expiration_time (oTree's native page
    timeout); the clients restart their countdown widgets on the
    'timer_reset' live message (see experiment.js).

    HIDDEN hard cap on resets: the group's total elapsed real time since
    the Negotiation page first loaded is tracked SERVER-SIDE ONLY
    (Group.negotiation_start_epoch). Once it exceeds
    config timeout_negotiation_hard_cap (10 minutes), the reset rule is
    permanently disabled for the round: later offers no longer touch the
    visible timer, which simply runs down to 0 and ends the round.
    Nothing about this cap -- not the limit, not the elapsed time, not the
    fact a reset was denied -- is ever sent to the client."""

    TIMER_RESET_SECONDS = 30
    HARD_CAP_SECONDS = 10 * 60  # fallback when the config key is absent

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_active

    @staticmethod
    def get_timeout_seconds(player: Player) -> int:
        # First load of the page in this group anchors the hidden hard
        # cap. get_timeout_seconds runs on each participant's initial GET,
        # so the earliest player's arrival defines the negotiation start.
        group = player.group
        if group.field_maybe_none('negotiation_start_epoch') is None:
            group.negotiation_start_epoch = time.time()
        # Timeout without an accepted offer = no deal (impasse).
        return player.session.config['timeout_negotiation']

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        # The collapsible how-to box above the chat starts OPEN in the
        # negotiation-only demo (no Instructions page preceded it) and
        # collapsed in the full experiment (participants just read them).
        return {'instructions_start_open': negotiation_only(player)}

    @staticmethod
    def js_vars(player: Player) -> dict[str, Any]:
        if player.field_maybe_none('time_start') is None:
            player.time_start = now_datetime()

        group = player.group
        # Parameters for the Decision Support Tool (analysis.js).
        # Two-Human game: exactly as in the example repository, the TRUE
        # market (retail) price is passed to BOTH players. TODO(design):
        # gate on the disclosure decision if that must change.
        # Single-Player game: the DST gets the bot's ACTING retail price
        # (= the Supplier's information environment); passing the true
        # draw would leak the private information / the lie.
        dst_market_price = (group.bot_acting_market_price
                            if group.is_ai_mode else group.market_price)

        return {
            'id_in_group': player.id_in_group,
            'bot_opponent': player.bot_opponent,
            'messages': player.chat_data,
            'offers': player.offers,

            'market_price': dst_market_price,
            'production_cost': group.production_cost,
            'demand_min': player.session.config['demand_min'],
            'demand_max': player.session.config['demand_max'],

            # Interface input bounds (experiment.js clamps as you type).
            'price_min': C.PRICE_MIN,
            'price_max': C.PRICE_MAX,
        }

    @classmethod
    def _reset_timer_if_needed(cls, player: Player) -> bool:
        """Timer-reset rule: when a NEW offer arrives while the countdown
        is below TIMER_RESET_SECONDS, push every active player's page
        deadline back out to exactly TIMER_RESET_SECONDS from now.
        Returns True when a reset happened (so live_method can notify the
        clients to restart their countdown widgets).

        Hidden hard cap: resets are only granted while the group's total
        elapsed real time is below timeout_negotiation_hard_cap. Past the
        cap this silently returns False -- the client is told nothing, the
        visible timer just keeps dropping."""
        now = time.time()
        group = player.group

        start = group.field_maybe_none('negotiation_start_epoch')
        hard_cap = player.session.config.get(
            'timeout_negotiation_hard_cap', cls.HARD_CAP_SECONDS)
        if start is None or now - start >= hard_cap:
            return False

        active = [p for p in group.get_players() if p.is_active]

        remaining = [
            p.participant._timeout_expiration_time - now
            for p in active
            if p.participant._timeout_expiration_time is not None
        ]
        if not remaining or min(remaining) >= cls.TIMER_RESET_SECONDS:
            return False

        for p in active:
            p.participant._timeout_expiration_time = (
                now + cls.TIMER_RESET_SECONDS)
        return True

    @staticmethod
    def error_message(player: Player, values) -> str | None:
        """Guard against premature auto-submits: under prodserver the
        timeout worker posts at the ORIGINAL deadline, which the
        timer-reset rule may have extended. A non-timeout submit with no
        deal and time still on the (possibly extended) clock is rejected;
        genuine timeouts carry timeout_happened and skip this check."""
        if player.group.deal_reached:
            return None
        expiration = player.participant._timeout_expiration_time
        if expiration is not None and expiration - time.time() > 2:
            return 'The negotiation is still running.'

    @staticmethod
    async def live_method(player: Player, data: dict[str, Any]):
        """Async generator (oTree 6): every `yield` is broadcast
        immediately. Against the AI retailer this allows delayed,
        multi-part bot replies (chat, counter-offer, deal finalization)
        within one incoming message -- replacing the example repository's
        background-task + channel-push machinery."""
        if data['type'] == 'ping':
            # Keep-alive from the client, once per second.
            yield {}

        elif data['type'] == 'initial':
            # Single-player game only: the client asks the AI counterpart
            # to open the negotiation.
            assert player.bot_opponent
            async for response in player.other.start_initial():
                yield {player.id_in_group: response}

        elif data['type'] == 'chat':
            yield player.process_chat(data)
            if player.bot_opponent:
                async for response in \
                        player.other.receive_chat_from_human(data['body']):
                    yield {player.id_in_group: response}
                    # The AI's binding (counter-)offers reset the clock
                    # exactly like a human's interface offers, so the
                    # human always has time to CONFIRM a late bot offer.
                    if 'offers' in response \
                            and Negotiation._reset_timer_if_needed(player):
                        yield {idx: {'timer_reset':
                                     Negotiation.TIMER_RESET_SECONDS}
                               for idx in player.live_ids}

        elif data['type'] == 'propose':
            price, quantity = data['price'], data['quantity']
            offers = player.process_offer(price, quantity)
            yield {idx: {'offers': offers} for idx in player.live_ids}
            if Negotiation._reset_timer_if_needed(player):
                yield {idx: {'timer_reset': Negotiation.TIMER_RESET_SECONDS}
                       for idx in player.live_ids}
            if player.bot_opponent:
                async for response in \
                        player.other.receive_offer_from_human(price, quantity):
                    yield {player.id_in_group: response}
                    # Same clock-reset rule for the AI's counter-offers.
                    if 'offers' in response \
                            and Negotiation._reset_timer_if_needed(player):
                        yield {idx: {'timer_reset':
                                     Negotiation.TIMER_RESET_SECONDS}
                               for idx in player.live_ids}

        elif data['type'] == 'accept':
            player.process_accept(data['price'], data['quantity'])
            # 'finished' makes the clients submit the page.
            yield {idx: {'finished': True} for idx in player.live_ids}

        else:
            raise NotImplementedError(
                f"Unknown live message: {data['type']}")


################################################################################
# 3b. Disclosure reveal (Supplier only, only if a deal was made)
################################################################################

class Disclosure_reveal(Page):
    """Shown to the SUPPLIER right after the negotiation, but only when a
    deal was reached: restates what the Retailer disclosed on the earlier
    Disclosure page and then reveals the ACTUAL Retail Price (RP), before
    the Supplier proceeds to the Effort Task. The Retailer never sees this
    page."""

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return (player.is_supplier and player.group.deal_reached
                and not negotiation_only(player))


################################################################################
# 4. Effort task (conditional: Supplier, only if a deal was reached)
################################################################################

class EffortTask(Page):
    """The Supplier's post-deal effort task: a slider task.

    NUM_SLIDERS sliders (SLIDER_MIN..SLIDER_MAX, starting at SLIDER_MIN);
    the goal is to drag each one exactly onto SLIDER_TARGET. The task is
    UNTIMED (no countdowns anywhere) and the Next button is always
    clickable -- the Supplier may leave at any point, and whatever was
    achieved by then is recorded.

    Data flow: the page's JavaScript (static/experiment/js/effort_task.js)
    keeps three hidden form inputs in sync (score, seconds on page, pacing
    timestamps), so the effort_put_* fields are saved through the normal
    oTree form submission when Next is clicked.
    """
    form_model = 'player'
    form_fields = [
        'effort_put_number_of_sliders',
        'effort_put_time_on_sliders',
        'effort_put_relative_time_on_sliders',
    ]

    @staticmethod
    def is_displayed(player: Player) -> bool:
        # Skipped entirely (by BOTH players) when no deal was reached, which
        # routes everyone straight to the Demand Draw / Results phase.
        return (player.is_supplier and player.group.deal_reached
                and not negotiation_only(player))

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        # Quality-check stakes, restated on the page for transparency.
        config = player.session.config
        return {
            'quality_rp_per_slider':
                f"{config['quality_rp_per_slider']:.2f}",
            'quality_rp_max': f"{config['quality_rp_max']:.2f}",
        }

    @staticmethod
    def js_vars(player: Player) -> dict[str, Any]:
        return {
            'num_sliders': C.NUM_SLIDERS,
            'target': C.SLIDER_TARGET,
            'slider_min': C.SLIDER_MIN,
            'slider_max': C.SLIDER_MAX,
            'cols': C.SLIDER_COLS,
        }


class ResultsWaitPage(WaitPage):
    """The Retailer skips EffortTask (is_displayed False) and IDLES here
    while the Supplier is working. When everyone has arrived: draw the
    demand and run the (stub) payoff calculation."""
    title_text = "Please wait"
    body_text = ("Please wait for the other participant. "
                 "The results will be shown next.")

    @staticmethod
    def is_displayed(player: Player) -> bool:
        # Negotiation-only demo: no demand draw, no payoffs.
        return not negotiation_only(player)

    @staticmethod
    def after_all_players_arrive(group: Group):
        group.draw_demand()
        group.set_payoffs()  # TODO(payoffs): currently a stub


################################################################################
# 5. Results
################################################################################

class Results(Page):
    """Layout/styling migrated from the example repository's Results page.

    Each participant sees their OWN outcome only (deal terms, drawn demand,
    realized profit and payment). In particular the Supplier never sees the
    Retailer's profit or the effective RP -- that would reveal the true
    retail price (and, in the Single-Player game, whether the AI lied)."""

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return not negotiation_only(player)

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        group = player.group
        config = player.session.config
        deal = group.deal_reached

        baseline = float(config['participation_fee'])
        bonus = float(player.payoff)
        total = float(player.participant.payoff_plus_participation_fee())

        return {
            'deal_reached': deal,
            'formatted_deal_price': f"{group.deal_price:.2f}" if deal else "",
            'formatted_deal_quantity':
                str(group.deal_quantity) if deal else "",

            # Demand Draw: all NUM_DEMAND_DRAWS draws, and their average
            # (= the demand the payoffs were computed with).
            'demand_draws': ', '.join(str(d) for d in group.demand_draws),
            'formatted_demand': f"{group.demand:.1f}",

            # Own realized outcome (see Group.set_payoffs).
            'formatted_profit': f"{player.profit:.2f}",
            'profit_is_negative': player.profit < 0,

            # Quality checks: shown to the RETAILER (whose profit they
            # raise); the template gates on player.is_retailer.
            'quality_sliders': group.supplier.effort_put_number_of_sliders,
            'formatted_quality_rp_increase':
                f"{group.quality_rp_increase:.2f}",
            'formatted_effective_rp': f"{group.effective_market_price:.2f}",

            # Payment breakdown: baseline + share of positive profit.
            'profit_share_pct': f"{config['profit_share'] * 100:g}",
            'formatted_baseline': f"{baseline:.2f}",
            'formatted_bonus': f"{bonus:.2f}",
            'formatted_total': f"{total:.2f}",
        }


class DemoResults(Page):
    """Negotiation-only demo (demo_* configs) closing page: states whether
    a deal was reached and its terms. No demand draw, no payoffs -- the
    demo ends here."""

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return negotiation_only(player)

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        group = player.group
        deal = group.deal_reached
        return {
            'deal_reached': deal,
            'formatted_deal_price': f"{group.deal_price:.2f}" if deal else "",
            'formatted_deal_quantity':
                str(group.deal_quantity) if deal else "",
        }


page_sequence = [
    Instructions,

    ComprehensionCheck1,
    ComprehensionCheck2,
    ComprehensionCheck3,
    ComprehensionCheck4,
    ComprehensionCheck5,

    Disclosure,
    DisclosureWaitPage,
    DisclosureReceived,
    NegotiationWaitPage,

    Negotiation,

    Disclosure_reveal,
    EffortTask,
    ResultsWaitPage,

    Results,
    DemoResults,
]
