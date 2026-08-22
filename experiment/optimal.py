"""
Nash bargaining benchmark and optimal counter-offer construction, ported
from the example repository.

Used in two places:
  * the "Nash Equilibrium Offer" text on the DST tab of the Negotiation
    page (nash_bargaining_solution + OPTIMAL_OFFER), and
  * the AI retailer's strategy (optimal_counter_offer), which decides what
    to offer back when the human's offer is rejected.

IMPORTANT: for the AI retailer, every constraint pair passed in here uses
the bot's ACTING retail price (disclosed value or the no-disclosure
fallback), never the true one -- the "no full information" design.
"""
import math

from .constants import C
from .offer import Offer, Evaluation

OPTIMAL_OFFER = ("A Wholesale Price of €%.2f and %d units have expected "
                 "profits of %.1f (Same expected profit for you and your "
                 "counterpart).")


def nash_bargaining_solution(constraint_a: int, constraint_b: int) \
        -> dict[str, float | tuple[float, int]]:
    """Return the symmetric Nash bargaining offer and its expected profit.

    The two constraints are the (acting) market price and the production
    cost, in either order (the function sorts them itself, as in the
    original repository).
    """
    market_price = max(constraint_a, constraint_b)
    production_cost = min(constraint_a, constraint_b)

    demand_range = C.DEMAND_MAX - C.DEMAND_MIN
    quantity_continuous = demand_range * (
            market_price - production_cost) / market_price
    price_star = round(market_price * (market_price + 3 * production_cost) / (
            2 * (market_price + production_cost)), 2)

    # Choose between floor and ceil by maximizing total profit
    q_candidates = [math.floor(quantity_continuous),
                    math.ceil(quantity_continuous)]

    def sort_function(q):
        return (Offer.profit_supplier(price_star, q, production_cost)
                + Offer.profit_retailer(price_star, q, market_price))

    quantity_star = int(max(q_candidates, key=sort_function))

    profit_retailer = Offer.profit_retailer(
        price_star, quantity_star, market_price)
    target_profit = math.floor(profit_retailer * 100) / 100

    return {'profit': target_profit, 'offer': (price_star, quantity_star)}


def optimal_wholesale_price_for_quantity(offer: Offer,
                                         constraint_user: int,
                                         constraint_bot: int) \
        -> tuple[float | None, int | None]:
    """Keep the offer's quantity, find the wholesale price that gives the
    bot exactly its Nash target profit (repo logic, verbatim math)."""
    q = float(offer.quantity)
    pm = max(constraint_bot, constraint_user)  # (acting) market price
    c = min(constraint_bot, constraint_user)   # production cost
    d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX
    es = (((q ** 2 - d_min ** 2) / 2) + q * (d_max - q)) / (d_max - d_min)

    # Nash bargaining solution: the minimum acceptable profit for the bot
    target = nash_bargaining_solution(constraint_user, constraint_bot)['profit']

    # rounding down to ensure reaching target profit
    best_p = math.floor((pm - target / es) * 100) / 100

    if best_p > 0:
        return best_p, int(q)
    return None, None


def optimal_quantity_for_wholesale_price(offer: Offer,
                                         constraint_user: int,
                                         constraint_bot: int) \
        -> tuple[float | None, int | None]:
    """Keep the offer's price, find the quantity that (1) satisfies the
    bot's Nash target and (2) maximizes the user's profit (repo logic)."""
    p = float(offer.price)
    pm = max(constraint_bot, constraint_user)  # (acting) market price
    c = min(constraint_bot, constraint_user)   # production cost
    dmin, dmax = C.DEMAND_MIN, C.DEMAND_MAX

    target = float(
        nash_bargaining_solution(constraint_user, constraint_bot)['profit'])

    def es(q: float) -> float:
        return ((q * q - dmin * dmin) / 2.0 + q * (dmax - q)) / (dmax - dmin)

    def retailer_profit(q: float) -> float:
        return (pm - p) * es(q)

    def supplier_profit(q: float) -> float:
        return p * es(q) - c * q

    bot_profit, user_profit = retailer_profit, supplier_profit

    def retailer_roots(b: float):
        """Solves (pm - p) * es(q) = b for q."""
        a = pm - p
        rad = -a * (dmax - dmin) * (
                2 * b - pm * (dmax + dmin) + p * (dmax + dmin))
        if rad < -1e-12:
            return None, None
        s = math.sqrt(max(0.0, rad))
        return (dmax * a - s) / a, (dmax * a + s) / a

    def supplier_roots(s_target: float):
        """Solves p * es(q) - c * q = s_target for q."""
        a = -p
        bc = 2 * p * dmax - 2 * c * (dmax - dmin)
        c0 = p * dmin * dmin - 2 * s_target * (dmax - dmin)
        disc = bc * bc - 4 * a * c0
        if disc < -1e-12:
            return None, None
        s = math.sqrt(max(0.0, disc))
        return (-bc - s) / (2 * a), (-bc + s) / (2 * a)

    retailer_vertex = dmax
    supplier_vertex = (dmax - c * (dmax - dmin) / p
                       if p != 0 else (dmin + dmax) / 2)

    def build_candidates(roots, extra_vertex=None) -> list[int]:
        cand = {int(dmin), int(dmax)}
        if roots != (None, None):
            for q in roots:
                q = max(min(q, dmax), dmin)
                b = math.floor(q)
                for k in (-2, -1, 0, 1, 2):
                    qi = int(b + k)
                    if dmin <= qi <= dmax:
                        cand.add(qi)
        if extra_vertex is not None:
            v = max(min(extra_vertex, dmax), dmin)
            b = math.floor(v)
            for k in (-3, -2, -1, 0, 1, 2, 3):
                qi = int(b + k)
                if dmin <= qi <= dmax:
                    cand.add(qi)
        return sorted(cand)

    cand = build_candidates(retailer_roots(target),
                                extra_vertex=retailer_vertex)

    feas = [q for q in cand if bot_profit(q) + 1e-9 >= target]

    if feas:
        best_q = max(feas, key=lambda q: (user_profit(q),
                                          user_profit(q) + bot_profit(q)))
        return round(p, 2), int(best_q)

    return None, None


def optimal_solution_string(evaluation: Evaluation,
                            offer: Offer,
                            constraint_user: int,
                            constraint_bot: int) -> str:
    """The optimal offer as prompt text ("Price of X€ and quantity of Y")
    inserted into the LLM prompts (repo's optimal_solution_string, adapted
    to this project's solver signatures). Empty only for ACCEPT; invalid
    offers are countered with the Nash offer so the generation prompt always
    receives a complete, valid price/quantity pair."""
    from .prompts import PROMPTS  # local import to avoid cycles

    if evaluation == Evaluation.ACCEPT:
        return ''
    price, quantity = optimal_counter_offer(
        evaluation, offer, constraint_user, constraint_bot)
    if None in (price, quantity):
        price, quantity = nash_bargaining_solution(
            constraint_user, constraint_bot)['offer']
    return PROMPTS['offer_string'] % (price, quantity)


def optimal_counter_offer(evaluation: Evaluation,
                          offer: Offer,
                          constraint_user: int,
                          constraint_bot: int) \
        -> tuple[float | None, int | None]:
    """The bot's counter-offer terms for a non-acceptable offer, following
    the same evaluation -> solver mapping as the example repository's
    optimal_solution_string."""
    args = (offer, constraint_user, constraint_bot)

    if evaluation == Evaluation.ACCEPT:
        return None, None
    elif evaluation == Evaluation.INVALID_OFFER:
        price, quantity = nash_bargaining_solution(
            constraint_user, constraint_bot)['offer']
    elif evaluation in (Evaluation.OFFER_PRICE,
                        Evaluation.NOT_PROFITABLE_ON_QUANTITY):
        price, quantity = optimal_quantity_for_wholesale_price(*args)
    elif evaluation in (Evaluation.OFFER_QUANTITY,
                        Evaluation.NOT_PROFITABLE_ON_PRICE,
                        Evaluation.NOT_PROFITABLE_ON_COMBINATION):
        # ON_COMBINATION: both terms are feasible alone -- concede by
        # keeping the human's quantity and re-pricing at the Nash target.
        price, quantity = optimal_wholesale_price_for_quantity(*args)
    else:
        # NOT_PROFITABLE_ON_BOTH, NOT_OFFER
        price, quantity = nash_bargaining_solution(
            constraint_user, constraint_bot)['offer']

    if None in (price, quantity):
        # Solver found no feasible terms: fall back to the Nash offer.
        price, quantity = nash_bargaining_solution(
            constraint_user, constraint_bot)['offer']
    return price, quantity
