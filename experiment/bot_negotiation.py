"""
The AI retailer for the Single-Player game (session config ai_retailer=True),
structured like the example repository's NegotiationBot.

Key departure from the repository -- NO FULL INFORMATION:
  * the bot knows the production cost (€1, common knowledge), and
  * it negotiates with its ACTING retail price: the value it disclosed to
    the human Supplier (truthful or a lie, per the session setting), or 4
    when it disclosed nothing (config bot_no_disclosure_rp). The true drawn
    retail price never enters its strategy -- including the LLM system
    prompt.

The entry points below are async generators, driven by the Negotiation
page's live_method; every yielded dict is broadcast to the human player
immediately (with human-like delays between parts).

Chat generation and offer reading run on the repository's Ollama stack
(bot_llm.py + prompts.py): llama3 writes the bot's messages, and the
offer-reader model (Ollama_LLMs/Modelfile_reader_of_offers_v3) reads
offers out of the human's natural-language chat.
"""
import asyncio
from typing import Any, AsyncIterator

from .bot_guard import (ACCEPT_POINTER, ACCEPT_POINTER_NO_OFFER,
                        REFUSAL_LINE, classify_message, widget_like)
from .bot_strategy import BotStrategy, FALLBACK_OFFER_STRING
from .constants import C
from .offer import Offer, OfferList
from .prompts import PROMPTS


class NegotiationBot(BotStrategy):
    """AI stand-in for the Retailer, negotiating against a human Supplier."""

    def __init__(self, player):
        # `player` is the human Supplier this bot negotiates against.
        self.player = player
        self.id_in_group = C.BOT_ID
        self.role = C.ROLE_RETAILER_EMPLOYEE
        self.user_message = ''

        group = player.group
        session_config = player.session.config
        self.config = {
            # Production cost: common knowledge -- the bot knows it is 1.
            'production_cost': group.production_cost,
            # THE key line of the information design: the bot's strategy
            # AND its LLM system prompt run on the acting retail price
            # (disclosed value, or the no-disclosure fallback), NOT on the
            # true draw.
            'market_price': group.bot_acting_market_price,
            # True draw, for reference/data only; never used in strategy.
            'true_market_price': group.market_price,
            # Scripted disclosure condition: selects which SYSTEM prompt
            # the LLM gets (split constraint prompt when a value was
            # disclosed, the single no-disclosure prompt otherwise).
            'bot_disclosure': session_config.get('bot_disclosure',
                                                 C.DISCLOSE_NONE),

            # ── LLM stack (see bot_llm.py) ────────────────────────────────
            'llm_user': session_config.get('llm_user'),
            'llm_pass': session_config.get('llm_pass'),
            'llm_model': session_config.get('llm_model', 'llama3'),
            'llm_temp': session_config.get('llm_temp', 0.1),
            'llm_reader': session_config.get('llm_reader',
                                             'offer_reader_v2'),
            # Host flags ("https://...": True) are read from here.
            'session_config': session_config,
            'participant_code': player.participant.code,
        }

        self.offer_list = self._load_offers()

    def _load_offers(self) -> OfferList:
        """The human player's offers JsonField is the single source of
        truth; rebuild rich Offer objects from it (repo behavior)."""
        return OfferList(Offer(**offer) for offer in self.player.offers)

    # ── Attributes read by the negotiation templates ──────────────────────
    @property
    def proposal(self) -> str:
        """The bot's current binding proposal, for the interface table."""
        bot_offers = [o for o in self.offer_list if o.idx == C.BOT_ID]
        if not bot_offers:
            return '(none)<br> '
        last = bot_offers[-1]
        return f"€ {last['price']}<br>{last['quantity']}"

    # ── Entry points (driven by pages.Negotiation.live_method) ───────────
    async def start_initial(self) -> AsyncIterator[dict[str, Any]]:
        """Called once when the human's Negotiation page loads (the client
        sends {'type': 'initial'}). Guarded so reloads don't re-greet."""
        if not self.player.chat_data:
            yield self._say(PROMPTS['first_message'])

    def _recent_context(self, body: str) -> list[dict[str, Any]]:
        """Conversation context for the classifier: the last 3 exchanged
        messages plus the bot's last line (if older than those), excluding
        the message currently being processed (pages.py stores it in
        chat_data BEFORE the bot runs)."""
        history = list(self.player.chat_data)
        if history and history[-1].get('body') == body \
                and '(Me)' in history[-1].get('nick', ''):
            history = history[:-1]
        recent = history[-3:]
        bot_lines = [m for m in history if '(Me)' not in m.get('nick', '')]
        if bot_lines and bot_lines[-1] not in recent:
            recent = [bot_lines[-1]] + recent
        return recent

    async def receive_chat_from_human(self, body: str) \
            -> AsyncIterator[dict[str, Any]]:
        """A chat message: classify it first IN CONTEXT (bot_guard --
        widget-only scope, verbal acceptances, short answers to the bot's
        own questions), then read a possible offer out of the natural
        language (spacy fast path, then the offer-reader LLM) and
        evaluate. Terms the reader misses but the context-aware classifier
        caught (e.g. a bare "25" answering a quantity question) are
        backfilled. Incomplete/absent terms flow into the NOT_OFFER
        guidance reply."""
        self.user_message = body

        verdict = await classify_message(self, body,
                                         self._recent_context(body))
        if verdict is not None:
            # Off-topic requests and non-widget goods: fixed refusal, the
            # generation LLM never sees the message.
            if verdict['type'] == 'offtopic' or (
                    verdict['type'] == 'offer'
                    and not widget_like(verdict['item'])):
                await asyncio.sleep(C.BOT_RESPONSE_DELAY)
                yield self._say(REFUSAL_LINE)
                return

            # Verbal acceptance is never binding: scripted pointer to the
            # CONFIRM button (can never misstate the deal state).
            if verdict['type'] == 'acceptance':
                await asyncio.sleep(C.BOT_RESPONSE_DELAY)
                bot_offers = [o for o in self.offer_list
                              if o.idx == C.BOT_ID]
                if bot_offers:
                    last = bot_offers[-1]
                    terms = FALLBACK_OFFER_STRING % (last['price'],
                                                     last['quantity'])
                    yield self._say(ACCEPT_POINTER % terms)
                else:
                    yield self._say(ACCEPT_POINTER_NO_OFFER)
                return

        offer = await self.interpret_offer(body,
                                           idx=self.player.id_in_group)

        # Backfill terms the reader missed but the context-aware
        # classifier extracted (short contextual answers like "25").
        if verdict is not None and not offer.is_complete:
            price = offer.price if offer.price is not None \
                else verdict['price']
            quantity = offer.quantity if offer.quantity is not None \
                else verdict['quantity']
            if (price, quantity) != (offer.price, offer.quantity):
                offer = Offer(idx=self.player.id_in_group, from_chat=True,
                              price=price, quantity=quantity)

        if offer.is_complete:
            self.offer_list.append(offer)
        async for payload in self.evaluate_and_respond(offer):
            yield payload

    async def receive_offer_from_human(self, price: float, quantity: int) \
            -> AsyncIterator[dict[str, Any]]:
        """A binding interface offer (already stored on the player by
        Player.process_offer; reload to include it)."""
        # Rendered as text so the LLM prompts have a counterpart message.
        self.user_message = ("I am making a binding offer of " +
                             FALLBACK_OFFER_STRING % (price, quantity) + ".")
        self.offer_list = self._load_offers()
        offer = self.offer_list[-1]
        async for payload in self.evaluate_and_respond(offer):
            yield payload
