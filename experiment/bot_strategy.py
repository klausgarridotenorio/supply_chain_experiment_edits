"""
Decision core of the AI retailer -- ported from the example repository's
BotBase + BotStrategy, with the deliberate changes:

1. NO FULL INFORMATION: the bot's market-price constraint is its ACTING
   retail price (the value it disclosed to the human, or the no-disclosure
   fallback of 4), injected via config['market_price'] by NegotiationBot.
   Its whole strategy -- profit functions, Nash target, counter-offers,
   accept decisions, and now the LLM system prompt -- is therefore informed
   by the disclosed private information, exactly as specified. The true
   retail price is carried in config['true_market_price'] for reference
   only and is never used here.

2. TRANSPORT: instead of the repository's background asyncio tasks +
   channel pushes (needed there because of slow LLM calls and a patched
   oTree), the response hooks are async GENERATORS consumed by the
   Negotiation page's async live_method (native oTree 6). Each yielded
   payload is broadcast to the human immediately, which preserves the
   repository's delayed, multi-part reply behavior.

3. CHAT VIA LLM (llama3 over Ollama, see bot_llm.py): the deterministic
   bot_messages.py layer is gone. Replies are generated with the
   repository's retry loop -- generate up to 3 candidate messages, read
   the offer back OUT of each candidate with the offer reader, evaluate
   it, and send the best one. The DECISION logic (what is acceptable,
   which counter-terms to anchor on) stays with the deterministic solver:
   the solver's optimal offer is embedded in every prompt, and the loop
   guarantees the message the human sees matches a sane offer.
   If every LLM host is unreachable, _fallback_* keeps the negotiation
   alive with solver-scripted lines instead of hanging the experiment.
"""
import asyncio
import random
from typing import Any, AsyncIterator

from .bot_guard import lint_problems, scrub_text
from .bot_llm import BotLLM
from .constants import C
from .offer import Offer, OfferList, Evaluation
from .optimal import optimal_counter_offer, optimal_solution_string
from .prompts import (PROMPTS, empty_offer_prompt, not_profitable_prompt,
                      offer_invalid_prompt, offer_without_price_prompt,
                      offer_without_quantity_prompt,
                      offer_with_single_unfavourable_term_prompt)
from .utils import log_debug

# Solver-scripted fallback lines, used when no LLM host is reachable or all
# three generated drafts fail validation.
FALLBACK_OFFER_STRING = "a Wholesale Price of €%.2f and a quantity of %d units"
FALLBACK_OPTIMAL_OFFER = ("I'm more than happy to offer a Wholesale price "
                          "of €%.2f and %d units.")
FALLBACK_ACCEPT_FROM_INTERFACE = (
    "That works for me -- I accept your offer of %s. "
    "Thank you, finalizing the deal now.")
FALLBACK_ACCEPT_FROM_CHAT = (
    "That works for me -- I accept %s. "
    "I have put it in the interface as a binding offer: please click the "
    "CONFIRM button (below the SEND button) to finalize the deal.")
FALLBACK_COUNTER = ("I'm afraid those terms don't work for me. "
                    "How about %s? I have put that offer in the interface.")


class BotStrategy(BotLLM):
    """Mixin with the evaluate/accept/counter logic. Expects the concrete
    class (NegotiationBot) to provide: player, role, config, offer_list,
    user_message."""
    player = None
    role: str = None
    config: dict[str, Any] = None
    offer_list: OfferList = None
    user_message: str = ''

    # ── Constraints (repo's BotBase, acting values in bot mode) ───────────
    @property
    def constraint_user(self) -> int:
        if self.role == C.ROLE_RETAILER_EMPLOYEE:
            return self.config['production_cost']
        return self.config['market_price']

    @property
    def constraint_bot(self) -> int:
        return self.config['market_price']

    def add_profits(self, offer: Offer):
        offer.profits(self.role, self.constraint_user, self.constraint_bot)

    # ── Payload helpers ───────────────────────────────────────────────────
    def _say(self, text: str) -> dict[str, Any]:
        """Store a bot chat line on the human player and build the live
        payload for it."""
        log_debug('[CHATBOT OUTPUT sent to participant]', '\n' + text)
        return self.player.process_llm_output(self.role, text)

    def _store_offers(self):
        """Persist the (possibly extended) offer list on the human player.
        JsonField: reassign, never mutate in place."""
        self.player.offers = list(self.offer_list)

    def _interactions_slice(self, from_human: bool) -> str:
        """One side of the split conversation history: the last three
        messages of that speaker, most recent first, one per line -- fed
        into the prompts' two separate triple-quoted history blocks
        (conversation_history_bot/_counterpart.txt). Human lines carry
        '(Me)' in the nick (models.process_chat)."""
        lines = [message['body'] for message in self.player.chat_data
                 if ('(Me)' in message.get('nick', '')) == from_human]
        recent = lines[-3:][::-1]
        if not recent:
            return '(none)'
        return '\n'.join(f'- {line}' for line in recent)

    def _interactions_bot(self) -> str:
        return self._interactions_slice(from_human=False)

    def _interactions_counterpart(self) -> str:
        return self._interactions_slice(from_human=True)

    # ── Core response logic (repo's BotStrategy.evaluate, LLM-driven) ────
    async def evaluate_and_respond(self, offer: Offer) \
            -> AsyncIterator[dict[str, Any]]:
        """Evaluate the human's offer and yield the bot's response
        payload(s): acceptance (chat, then deal finalization) or a
        rejection message with a binding counter-offer."""
        # Add profits for user and bot to all offers (repo behavior).
        for known_offer in self.offer_list:
            self.add_profits(known_offer)
        self.add_profits(offer)

        evaluation = offer.evaluate(self.constraint_user,
                                    self.constraint_bot)

        await asyncio.sleep(C.BOT_RESPONSE_DELAY)

        if evaluation == Evaluation.ACCEPT:
            async for payload in self._accept_offer(offer):
                yield payload
            return

        # Rejection: LLM-generated reply anchored on the solver's optimal
        # counter terms; deterministic fallback when no host is reachable.
        try:
            message, bot_offer = await self._respond_to_offer(evaluation,
                                                              offer)
        except Exception as exc:
            log_debug('[BotStrategy] LLM generation failed, solver fallback:',
                      repr(exc))
            message, bot_offer = self._fallback_response(evaluation, offer)

        payload = self._say(message)
        if bot_offer is not None and bot_offer.is_complete \
                and bot_offer.is_valid:
            # Binding counter-offer: appears in the human's interface as
            # the bot's current proposal (idx == BOT_ID).
            bot_offer['idx'] = C.BOT_ID
            self.add_profits(bot_offer)
            self.offer_list.append(bot_offer)
            self._store_offers()
            payload = {**payload, 'offers': list(self.offer_list)}
        yield payload

    # ── LLM response generation (repo's respond_to_offer retry loop) ─────
    def _respond_prompt(self, evaluation: Evaluation | None,
                        optimal_offer_str: str) -> str:
        args = (self.user_message, optimal_offer_str,
                self._interactions_bot(), self._interactions_counterpart())
        if evaluation == Evaluation.NOT_OFFER:
            # Condition-split decision tree (retail-price question rule).
            return empty_offer_prompt(*args,
                                      self.config.get('bot_disclosure',
                                                      C.DISCLOSE_TRUE))
        elif evaluation == Evaluation.NOT_PROFITABLE_ON_BOTH:
            return offer_with_single_unfavourable_term_prompt(*args)
        elif evaluation == Evaluation.OFFER_QUANTITY:
            return offer_without_price_prompt(*args)
        elif evaluation == Evaluation.OFFER_PRICE:
            return offer_without_quantity_prompt(*args)
        elif evaluation == Evaluation.INVALID_OFFER:
            return offer_invalid_prompt(*args)
        else:
            return not_profitable_prompt(*args)

    async def _respond_to_offer(self, evaluation: Evaluation,
                                offer: Offer) \
            -> tuple[str, Offer | None]:
        """Generate up to 3 candidate replies, read each candidate's offer
        back with the reader LLM and evaluate it; send the first
        self-consistent one (or the most profitable candidate)."""
        optimal_offer_str = optimal_solution_string(
            evaluation, offer, self.constraint_user, self.constraint_bot)
        content1 = self._respond_prompt(evaluation, optimal_offer_str)
        content2 = self._respond_prompt(None, optimal_offer_str)
        llm_offers = []
        last_offer = llm_output = None
        while len(llm_offers) < 3:
            content = content1 if len(llm_offers) < 2 else content2
            response = await self.get_llm_response(content)
            log_debug('[BotStrategy._respond_to_offer] raw:',
                      response['message']['content'])
            llm_output = scrub_text(self.extract_content(response))
            log_debug('[BotStrategy._respond_to_offer] cleaned:', llm_output)

            # Guard lints (bot_guard): a draft with closure claims,
            # wrong-direction price language, or code is never sendable.
            problems = lint_problems(llm_output, evaluation)
            if problems:
                log_debug('[BotStrategy._respond_to_offer] linted:',
                          problems)
                llm_offers.append(
                    (float('-inf'), llm_output, Offer(idx=C.BOT_ID)))
                continue

            last_offer = await self._interpret_offer_llm(llm_output, C.BOT_ID)
            if last_offer.is_complete:
                self.add_profits(last_offer)
                candidate_eval = last_offer.evaluate(self.constraint_user,
                                                     self.constraint_bot)
                log_debug('[BotStrategy._respond_to_offer] candidate eval:',
                          candidate_eval.value)
                if candidate_eval == Evaluation.ACCEPT:
                    return llm_output, last_offer
            else:
                # Every generated negotiation reply, including replies from
                # the two Send_Optimal_Offer_or_Instructions prompts, must
                # contain both a price and a quantity. An incomplete draft
                # is rejected and generated again, up to three attempts.
                log_debug(
                    '[BotStrategy._respond_to_offer] incomplete draft; '
                    'retrying:',
                    {'price': last_offer.price,
                     'quantity': last_offer.quantity})
                llm_offers.append(
                    (float('-inf'), llm_output, last_offer))
                continue

            llm_offers.append(
                (last_offer['profit_bot'], llm_output, last_offer))

        # No self-profitable candidate after 3 attempts: best of the batch,
        # excluding drafts the guard lints rejected. If every draft was
        # linted away or omitted a complete price/quantity pair, raise so
        # the caller uses the solver-scripted optimal-offer fallback instead
        # of showing a rule-violating or incomplete message.
        viable = [candidate for candidate in llm_offers
                  if candidate[0] > float('-inf')]
        if not viable:
            raise RuntimeError(
                'all LLM drafts failed validation or omitted complete terms')
        best_profit = max(candidate[0] for candidate in viable)
        _, llm_output, last_offer = random.choice(
            [candidate for candidate in viable
             if candidate[0] == best_profit])
        return llm_output, (last_offer if last_offer.is_complete else None)

    def _fallback_response(self, evaluation: Evaluation, offer: Offer) \
            -> tuple[str, Offer | None]:
        """Solver-scripted reply for host or three-draft validation failure."""
        counter_price, counter_quantity = optimal_counter_offer(
            evaluation, offer, self.constraint_user, self.constraint_bot)
        if evaluation.is_non_offer or None in (counter_price,
                                               counter_quantity):
            counter_price, counter_quantity = optimal_counter_offer(
                Evaluation.NOT_PROFITABLE_ON_BOTH, offer,
                self.constraint_user, self.constraint_bot)
            bot_offer = Offer(idx=C.BOT_ID, price=counter_price,
                              quantity=counter_quantity)
            return (FALLBACK_OPTIMAL_OFFER % (counter_price,
                                              counter_quantity),
                    bot_offer)
        terms = FALLBACK_OFFER_STRING % (counter_price, counter_quantity)
        bot_offer = Offer(idx=C.BOT_ID, price=counter_price,
                          quantity=counter_quantity)
        return FALLBACK_COUNTER % terms, bot_offer

    # ── Acceptance (repo's accept_offer / accept_final_*) ────────────────
    async def _accept_offer(self, offer: Offer) \
            -> AsyncIterator[dict[str, Any]]:
        terms = FALLBACK_OFFER_STRING % (offer.price, offer.quantity)
        if offer.from_chat:
            prompt = PROMPTS['accept_from_chat'] + self.user_message
            fallback = FALLBACK_ACCEPT_FROM_CHAT % terms
        else:
            prompt = PROMPTS['accept_from_interface'] + self.user_message
            fallback = FALLBACK_ACCEPT_FROM_INTERFACE % terms

        try:
            response = await self.get_llm_response(prompt)
            text = scrub_text(self.extract_content(response))
            if not text:
                text = fallback
        except Exception as exc:
            log_debug('[BotStrategy] LLM unavailable on accept:', repr(exc))
            text = fallback

        if offer.from_chat:
            # Chat offers are non-binding: announce acceptance, then post a
            # matching binding offer for the human to CONFIRM.
            yield self._say(text)
            await asyncio.sleep(C.BOT_ACCEPT_DELAY)
            bot_offer = Offer(idx=C.BOT_ID, price=offer.price,
                              quantity=offer.quantity)
            self.add_profits(bot_offer)
            self.offer_list.append(bot_offer)
            self._store_offers()
            yield {'offers': list(self.offer_list)}
        else:
            # Interface offers are binding: announce, pause, close the deal.
            yield self._say(text)
            await asyncio.sleep(C.BOT_ACCEPT_DELAY)
            self.player.process_accept(offer.price, offer.quantity)
            yield {'finished': True}
