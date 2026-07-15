"""
Shared helpers, importable from any app in this project.
Mirrors the structure of the example repository's common.py, trimmed to what
the new experiment needs (the 4-role manager/employee machinery is gone; the
game has exactly two roles, defined in experiment/constants.py).
"""
from otree.database import wrap_column, OTreeColumn, AUTO_SUBMIT_DEFAULTS
from sqlalchemy.sql import sqltypes as st

# Ensure timeout auto-submission has a sane default for JSON columns.
AUTO_SUBMIT_DEFAULTS[st.JSON] = {}


def JsonField(**kwargs) -> OTreeColumn:
    """A JSON database column for structured data (offer history, chat log).

    IMPORTANT (same caveat as the example repository):
      * always REASSIGN, e.g. `player.offers = player.offers + [offer]`;
        never mutate in place with .append() / .update() -- SQLAlchemy does
        not detect in-place mutation of JSON values;
      * JsonFields cannot be used as form_fields.
    """
    return wrap_column(st.JSON, **kwargs)


################################################################################
# Base profit functions
#
# These are the per-deal profit formulas from the example repository. They are
# kept for the UI: instructions, examples, and (in JavaScript form) the
# Decision Support Tool on the Negotiation page
# (experiment/static/experiment/js/analysis.js implements the same formulas
# client-side).
#
# TODO(payoffs): the FINAL participant payoff calculation is intentionally NOT
# implemented. When you build it, use these functions from
# Group.set_payoffs() in experiment/models.py.
################################################################################

def retailer_profit(market_price: float, price: float,
                    quantity_sold: int) -> float:
    """Retailer earns the retail margin on every unit actually sold:
    (RP - w) * min(q, D)."""
    return (market_price - price) * quantity_sold


def supplier_profit(price: float, production_cost: float,
                    quantity_sold: int, quantity_unsold: int) -> float:
    """Supplier earns the wholesale margin on sold units and bears the
    production cost of unsold ones: w * min(q, D) - PC * q."""
    return (price - production_cost) * quantity_sold \
        - production_cost * quantity_unsold
