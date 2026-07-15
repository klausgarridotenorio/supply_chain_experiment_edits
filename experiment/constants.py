from otree.api import BaseConstants


class C(BaseConstants):
    NAME_IN_URL = 'experiment'
    # None so the app supports BOTH match structures (see creating_session):
    #   * Two-Human game:     groups of 2 (id 1 = Retailer, id 2 = Supplier)
    #   * Single-Player game: groups of 1 (a human Supplier vs the AI
    #     retailer bot; session config ai_retailer=True)
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1

    # ── Roles ────────────────────────────────────────────────────────────
    # oTree registers any constant starting with ROLE_ (or ending in _ROLE)
    # as a native role, which makes player.role and
    # group.get_player_by_role() work. With PLAYERS_PER_GROUP = None the
    # per-player assignment happens in creating_session (set_group_matrix
    # assigns Retailer/Supplier by position for pairs; singles are set to
    # Supplier explicitly).
    # NOTE: because of this convention, any OTHER constant must not start
    # with "ROLE_" (use "ROLES_..." for lists).
    ROLE_RETAILER_EMPLOYEE = 'Retailer'
    ROLE_SUPPLIER_EMPLOYEE = 'Supplier'

    # ── Negotiation bounds (as in the example repository) ────────────────
    # Wholesale price: euros with two decimals in [PRICE_MIN, PRICE_MAX].
    PRICE_MIN = 1
    PRICE_MAX = 5
    PRICE_RANGE = [x / 100 for x in range(PRICE_MIN * 100, PRICE_MAX * 100 + 1)]
    # Quantity: integers in [QUANTITY_MIN, QUANTITY_MAX].
    QUANTITY_MIN = 1
    QUANTITY_MAX = 100
    QUANTITY_RANGE = [x for x in range(QUANTITY_MIN, QUANTITY_MAX + 1)]
    # Demand bounds used by the analytic helpers (offer.py / optimal.py).
    # Keep in sync with the session config keys demand_min / demand_max.
    DEMAND_MIN = 0
    DEMAND_MAX = 100
    # Demand Draw phase: this many independent Uniform[DEMAND_MIN,
    # DEMAND_MAX] draws are taken; their AVERAGE is the realized demand
    # used for the payoffs (all draws are shown on the Results page).
    NUM_DEMAND_DRAWS = 10

    # ── Disclosure stage (Retailer's private-information decision) ───────
    DISCLOSE_TRUE = 'true_value'    # disclose the true retail price
    DISCLOSE_OWN = 'own_value'      # disclose a self-chosen value
    DISCLOSE_NONE = 'no_disclosure'  # disclose nothing

    # ── Effort stage (slider task, Supplier only) ────────────────────────
    NUM_SLIDERS = 50      # number of sliders on the page
    SLIDER_TARGET = 50    # the goal: place each slider exactly here
    SLIDER_MIN = 0
    SLIDER_MAX = 100
    SLIDER_COLS = 3       # grid columns (also drives the cosmetic row offsets)

    # ── AI retailer (Single-Player game) ─────────────────────────────────
    # Player.other_id == BOT_ID marks a bot opponent (repo convention).
    BOT_ID = -1
    # Human-like pauses before the bot's replies (seconds).
    BOT_RESPONSE_DELAY = 1.5   # before any chat/counter-offer response
    BOT_ACCEPT_DELAY = 3.0     # between accepting verbally and finalizing
