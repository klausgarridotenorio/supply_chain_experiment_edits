"""
Offer: dict-like container for one binding offer, plus the offer-evaluation
machinery used by the AI retailer -- ported from the example repository.

IMPORTANT DEPARTURE FROM THE REPOSITORY: there, both constraints (market
price and production cost) were common knowledge. Here the retail price is
the Retailer's private information, so the AI retailer calls everything in
this module with its ACTING retail price (the value it disclosed, or the
no-disclosure fallback) -- see Group.bot_acting_market_price and
bot_strategy.py. The math itself is unchanged.
"""
import time
from enum import Enum

from .constants import C


class Evaluation(Enum):
    """Classification of an incoming offer from the bot's perspective
    (ported unchanged from the example repository)."""
    ACCEPT = 'accept'
    NOT_PROFITABLE_ON_BOTH = 'not_profitable_on_both'
    NOT_PROFITABLE_ON_PRICE = 'not_profitable_on_price'
    NOT_PROFITABLE_ON_QUANTITY = 'not_profitable_on_quantity'
    OFFER_QUANTITY = 'offer_quantity'
    OFFER_PRICE = 'offer_price'
    NOT_OFFER = 'not_offer'
    INVALID_OFFER = 'invalid_offer'

    @property
    def is_non_offer(self) -> bool:
        return self in (self.INVALID_OFFER, self.NOT_OFFER)


class Offer(dict):
    """Subclasses dict so instances serialize transparently into the
    Player.offers JSON column while still allowing attribute access."""

    def __init__(self, idx: int = -1, price: float = None,
                 quantity: int = None, stamp: int = None,
                 from_chat: bool = False,
                 profit_bot: float = None, profit_user: float = None):
        stamp = stamp or int(time.time())
        dict.__init__(self, idx=idx, price=price, quantity=quantity,
                      stamp=stamp, from_chat=from_chat,
                      profit_bot=profit_bot, profit_user=profit_user)

    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, key, value):
        self.__setitem__(key, value)

    # ── Validity helpers ──────────────────────────────────────────────────
    @property
    def is_valid(self) -> bool:
        return self.price_in_range and self.quantity_in_range

    @property
    def is_complete(self) -> bool:
        return None not in (self.price, self.quantity)

    @property
    def price_in_range(self) -> bool:
        return self.price in C.PRICE_RANGE

    @property
    def quantity_in_range(self) -> bool:
        return self.quantity in C.QUANTITY_RANGE

    # ── Expected-profit helpers ───────────────────────────────────────────
    @staticmethod
    def _expected_demand(quantity: int) -> float:
        """E[min(q, D)] for D ~ Uniform[DEMAND_MIN, DEMAND_MAX]."""
        d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX
        if quantity <= d_min:
            return quantity
        if quantity >= d_max:
            return (d_min + d_max) / 2
        return ((quantity ** 2 - d_min ** 2) / 2 +
                quantity * (d_max - quantity)) / (d_max - d_min)

    @classmethod
    def profit_supplier(cls, price: float, quantity: int,
                        production_cost: int) -> float:
        """Expected supplier profit: w * E[min(q, D)] - PC * q."""
        expected_sales = cls._expected_demand(quantity)
        return (price * expected_sales) - (production_cost * quantity)

    @classmethod
    def profit_retailer(cls, price: float, quantity: int,
                        market_price: int) -> float:
        """Expected retailer profit: (RP - w) * E[min(q, D)].
        For the AI retailer, market_price is its ACTING retail price."""
        expected_sales = cls._expected_demand(quantity)
        return (market_price - price) * expected_sales

    def profits(self, bot_role: str, constraint_user: int,
                constraint_bot: int):
        """Fill profit_user / profit_bot for this offer (repo logic)."""
        if not self.is_valid or None in (constraint_user, constraint_bot):
            self.profit_bot = -11
            self.profit_user = -10
            return

        args_bot = (self.price, self.quantity, constraint_bot)
        args_user = (self.price, self.quantity, constraint_user)

        if bot_role == C.ROLE_SUPPLIER_EMPLOYEE:
            self.profit_bot = self.profit_supplier(*args_bot)
            self.profit_user = self.profit_retailer(*args_user)
        else:
            self.profit_bot = self.profit_retailer(*args_bot)
            self.profit_user = self.profit_supplier(*args_user)

    # ── Feasibility checks (repo logic, verbatim math) ────────────────────
    def _is_price_feasible(self, params: dict) -> bool:
        """Can the bot still reach its Nash profit at this price?"""
        if self.price is None:
            return False

        d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX

        q_best = d_max
        es_best = (((q_best ** 2 - d_min ** 2) / 2) +
                    q_best * (d_max - q_best)) / (d_max - d_min)
        max_profit = (params['market_price'] - self.price) * es_best
        if max_profit < params['nash_profit']:
            return False

        return True

    def _is_quantity_feasible(self, params: dict) -> bool:
        """Can the bot still reach its Nash profit at this quantity?"""
        if self.quantity is None:
            return False

        d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX
        es = (((self.quantity ** 2 - d_min ** 2) / 2) +
              self.quantity * (d_max - self.quantity)) / (d_max - d_min)

        max_acceptable_price = (params['market_price'] -
                                params['nash_profit'] / es)
        if max_acceptable_price < params['production_cost']:
            return False

        return True

    def _validate_non_profitable_offer(self, params: dict) -> Evaluation:
        price_is_unfeasible = not self._is_price_feasible(params)
        quantity_is_unfeasible = not self._is_quantity_feasible(params)
        if quantity_is_unfeasible and price_is_unfeasible:
            return Evaluation.NOT_PROFITABLE_ON_BOTH
        elif price_is_unfeasible:
            return Evaluation.NOT_PROFITABLE_ON_PRICE
        elif quantity_is_unfeasible:
            return Evaluation.NOT_PROFITABLE_ON_QUANTITY
        else:
            # Should not happen; default to not profitable on both.
            return Evaluation.NOT_PROFITABLE_ON_BOTH

    def evaluate(self, constraint_user: int, constraint_bot: int) -> Evaluation:
        """Evaluate this offer from the bot's perspective (repo logic).
        For the AI retailer, constraint_bot is the ACTING retail price."""
        from .optimal import nash_bargaining_solution

        params = {
            'nash_profit': nash_bargaining_solution(
                constraint_user, constraint_bot)['profit'],
            'production_cost': min([constraint_user, constraint_bot]),
            'market_price': max([constraint_user, constraint_bot]),
        }

        if self.profit_bot is not None \
                and self.profit_bot >= params['nash_profit']:
            return Evaluation.ACCEPT

        if self.is_valid:
            return self._validate_non_profitable_offer(params)

        if self.price is None and self.quantity_in_range:
            if self._is_quantity_feasible(params):
                return Evaluation.OFFER_QUANTITY
            return Evaluation.NOT_PROFITABLE_ON_BOTH

        if self.quantity is None and self.price_in_range:
            if self._is_price_feasible(params):
                return Evaluation.OFFER_PRICE
            return Evaluation.NOT_PROFITABLE_ON_BOTH

        if self.price is not None and not self.price_in_range:
            return Evaluation.INVALID_OFFER
        if self.quantity is not None and not self.quantity_in_range:
            return Evaluation.INVALID_OFFER

        return Evaluation.NOT_OFFER


class OfferList(list):
    def __init__(self, *args):
        list.__init__(self, *args)
        # Keep sorted on timestamp, as in the example repository.
        self.sort(key=lambda o: o.stamp)
