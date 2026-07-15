"""
Project settings.

Session configs:
  * two_human_negotiation -- the Two-Human game.
  * ai_* -- the five Single-Player settings (human Supplier vs the AI
    retailer). The retail price draw is fixed per setting via
    market_price_low == market_price_high, and bot_disclosure scripts what
    the AI retailer discloses before the negotiation:
        RP = 5:  truthful (5) | lie (4) | no disclosure
        RP = 4:  truthful (4) | no disclosure
    During the negotiation the bot follows its disclosure: it negotiates on
    the disclosed value; with no disclosure it negotiates as if it had
    disclosed 4 (bot_no_disclosure_rp).
"""
from os import environ


def ai_setting(name: str, display_name: str, retail_price: int,
               bot_disclosure: str) -> dict:
    """One Single-Player (Supplier vs AI retailer) treatment setting."""
    return dict(
        name=name,
        display_name=display_name,
        app_sequence=['experiment'],
        num_demo_participants=1,
        ai_retailer=True,
        market_price_low=retail_price,
        market_price_high=retail_price,
        bot_disclosure=bot_disclosure,
    )


SESSION_CONFIGS = [
    dict(
        name='two_human_negotiation',
        display_name="Supplier-Retailer Negotiation (Two Human Players)",
        app_sequence=['experiment'],
        num_demo_participants=2,
        ai_retailer=False,
    ),

    # ── The five AI-retailer settings ────────────────────────────────────
    ai_setting('ai_rp5_disclose_true',
               "AI Retailer -- RP=5, truthful disclosure (5)",
               retail_price=5, bot_disclosure='true_value'),
    ai_setting('ai_rp5_disclose_lie',
               "AI Retailer -- RP=5, lies and discloses 4",
               retail_price=5, bot_disclosure='own_value'),
    ai_setting('ai_rp4_disclose_true',
               "AI Retailer -- RP=4, truthful disclosure (4)",
               retail_price=4, bot_disclosure='true_value'),
    ai_setting('ai_rp4_no_disclosure',
               "AI Retailer -- RP=4, no disclosure",
               retail_price=4, bot_disclosure='no_disclosure'),
]

SESSION_CONFIG_DEFAULTS = dict(
    # ── Mode switch ──────────────────────────────────────────────────────
    # False: Two-Human game. True: Single-Player game (Supplier vs the AI
    # retailer; see experiment/bot_negotiation.py).
    ai_retailer=False,

    # ── AI retailer behavior (only used when ai_retailer=True) ──────────
    # What the bot disclosed before the negotiation:
    #   'true_value'    -> discloses the drawn retail price
    #   'own_value'     -> discloses bot_disclosed_value instead (the lie)
    #   'no_disclosure' -> discloses nothing
    bot_disclosure='no_disclosure',
    bot_disclosed_value=4,
    # With no disclosure the bot negotiates as if it had disclosed this:
    bot_no_disclosure_rp=4,

    # ── LLM chat stack (AI retailer's natural-language layer) ────────────
    # llama3 over Ollama writes the bot's chat; llm_reader is the dedicated
    # offer-extraction model (create it with:
    #   ollama create offer_reader_v4 -f Ollama_LLMs/Modelfile_reader_of_offers_v4
    # -- when it is missing, bot_llm.py falls back to llm_model with the
    # Modelfile's system prompt). Credentials apply to the remote hosts.
    llm_user='otree',
    llm_pass='ped+GlubbomOnEc4',
    llm_model='llama3',
    llm_temp=0.1,
    llm_reader='offer_reader_v4',
    # Ollama hosts: every enabled (True) http(s) key joins the failover
    # list; the local Ollama (http://localhost:11434) is always tried as
    # the last resort, so a local `ollama serve` needs no entry here.
    **{
        "https://ollama1.src-automating.src.surf-hosted.nl": True,
        "https://ollama2.src-automating.src.surf-hosted.nl": True,
        "https://ollama3.src-automating.src.surf-hosted.nl": True,
        "https://ollama4.src-automating.src.surf-hosted.nl": True,
        "https://ollama5.src-automating.src.surf-hosted.nl": True,
        "https://ollama6.src-automating.src.surf-hosted.nl": True,
        "https://ollama7.src-automating.src.surf-hosted.nl": True,
    },

    # ── Timing ───────────────────────────────────────────────────────────
    timeout_negotiation=5 * 60,  # seconds on the Negotiation page
    # HIDDEN hard cap on the <30s offer reset rule: once this much total
    # real time has elapsed since the Negotiation page first loaded,
    # binding offers stop resetting the visible timer (it just runs out).
    # Tracked server-side only -- participants never see this value.
    timeout_negotiation_hard_cap=10 * 60,

    # ── Market parameters ─────────────────────────────────────────────────
    # Production cost (PC) is fixed and common knowledge; the retail price
    # (RP) is drawn uniformly from [low, high] per group (i.e. 4 or 5 with
    # equal probability) and is the Retailer's private information (subject
    # of the Disclosure stage).
    production_cost=1,
    market_price_low=4,
    market_price_high=5,

    # Demand is drawn uniformly from [demand_min, demand_max] AFTER the
    # negotiation/effort stages (see Group.draw_demand). The same bounds
    # feed the client-side Decision Support Tool.
    demand_min=0,
    demand_max=100,

    # ── Payoffs (see Group.set_payoffs) ──────────────────────────────────
    # Everyone gets the baseline (oTree participation fee) of 5€; on top of
    # that, each side earns profit_share (5%) of their REALIZED profit from
    # the deal, computed after the demand draw. Negative profit = no bonus.
    participation_fee=5.00,
    profit_share=0.05,
    # Effort task -> quality checks: every slider placed exactly on target
    # raises the RETAIL price by quality_rp_per_slider euros, capped at
    # quality_rp_max in total. This benefits only the Retailer's profit.
    quality_rp_per_slider=0.02,
    quality_rp_max=1.00,

    real_world_currency_per_point=1.00,
    doc="",
)

PARTICIPANT_FIELDS = []
SESSION_FIELDS = []

# ISO-639 code, e.g. de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ """

SECRET_KEY = '4127905536189'
