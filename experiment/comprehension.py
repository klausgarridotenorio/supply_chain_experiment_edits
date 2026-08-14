"""
Comprehension-check content: worked-solution error messages, ported from
the example repository's intro/comprehension.py (employee part).

Adapted to this game's parameterization: every value in a question is
FIXED (see pages.ComprehensionCheck1.TERMS) -- a wrong answer shows the
worked solution and the player retries the very same question. The demand
figure is the AVERAGE across the game's 10 demand draws, and is labeled
as such. `player.clean_role` became `player.role` (already clean here).
"""

RETAILER_PROFIT_CALC = "Profit = (%d - %d) * %d = %d"
SUPPLIER_PROFIT_CALC = "Profit = ((%d - %d) * %d) - (%d * %d) = %d"


def get_error_message(player: 'Player', profit_calc: str,
                      market_price: int, price: int,
                      production_cost: int, quantity: int, demand: int) \
        -> str:
    """The full worked solution, shown when the answer is wrong. Returned
    as HTML (oTree renders error messages unescaped)."""
    if player.is_retailer:
        return (
            f"Oops! You entered the incorrect profit.<br><br>"
            f"<b>The Solution:</b><br>"
            f"Retail Price: {market_price}<br>"
            f"Agreed Wholesale Price: {price}<br>"
            f"Agreed Quantity: {quantity}<br>"
            f"The Average Demand (across the 10 draws): {demand}<br>"
            f"Your profit (as a {player.role}) is calculated as:<br>"
            f"<b>Profit = (Retail Price - Wholesale Price) * Quantity Sold</b><br>"
            f"<b>Please try again!</b> "
        )
    else:
        return (
            f"Oops! You entered the incorrect profit.<br><br>"
            f"<b>The Solution:</b><br>"
            f"Production Cost: {production_cost}<br>"
            f"Agreed Wholesale Price: {price}<br>"
            f"Agreed Quantity: {quantity}<br>"
            f"The Average Demand (across the 10 draws): {demand}<br>"
            f"Your profit (as a {player.role}) is calculated as:<br>"
            f"<b>Profit = ((Wholesale Price - Production Cost) * Quantity Sold) - "
            f"(Production Cost * Unsold Quantity)</b><br>"
            f"Note: Unsold Quantity = max(0, Agreed Quantity - Average Demand)<br><br>"
            f"<b>Please try again!</b>"
        )
