"""
Prompt library for the AI retailer's LLM chat layer, ported from the
example repository's prompts.py.

Differences from the repository:
  * Retailer-only: in this experiment the bot is ALWAYS the Retailer
    (the human is always the Supplier), so only prompts/retailer/ exists
    and the role indirection is dropped.
  * Paths are resolved relative to the project root (the repository used
    cwd-relative paths, which breaks when oTree is started elsewhere).
  * READER_SYSTEM_PROMPT: the offer-reader Modelfile's SYSTEM prompt is
    embedded as a fallback, so a plain `llama3`-only Ollama install still
    reads offers when the custom reader model was not created.

The generation system prompts live in <project root>/prompts/retailer/system/.
Counteroffer user prompts retain their case-specific fragments but never add
conversation history; accepted offers use their own dedicated system and user
prompts.
"""
import os

from .constants import C

# <project root>/prompts/retailer/ -- resolved from this file's location.
_PROMPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts', 'retailer')


def from_file(file_path: str) -> str:
    with open(os.path.join(_PROMPT_DIR, file_path), 'r') as f:
        content = f.read()
    # These markers previously moved examples into the system prompt. The
    # system prompt is now intentionally fixed and minimal, so retain the
    # examples in their case-specific user fragments without exposing the
    # implementation tags to the model.
    content = content.replace('<generation_examples>', '')
    content = content.replace('</generation_examples>', '')
    return content.strip() + '\n'


def _retailer_prompts() -> dict[str, str]:
    return {
        'before_constraint': from_file('system/before_constraint.txt'),
        'after_constraint': from_file('system/after_constraint.txt'),
        # Single-file system prompt for the no-disclosure condition: the
        # bot must not mention ANY retail price value, so no constraint
        # is spliced in at all.
        'system_no_disclosure': from_file(
            'system/sys_prompt_no_disclosure.txt'),
        'system_accept': from_file('system/sys_prompt_accept.txt'),
        'accept_profitable_offer': from_file('accept_profitable_offer.txt'),
        'follow_up_prompt_non_profitable': from_file('follow_up_user_message_non_profitable.txt'),
        'follow_up_prompt_without_offer': from_file(
            'follow_up_user_message_without_offer.txt'),
        'follow_up_prompt_unfavourable_term_offer': from_file(
            'follow_up_user_message_unfavourable_term_offer.txt'),
        'follow_up_prompt_without_price': from_file(
            'follow_up_user_message_without_price.txt'),
        'follow_up_prompt_without_quantity': from_file(
            'follow_up_user_message_without_quantity.txt'),
        'follow_up_invalid_offer': from_file(
            'follow_up_user_message_invalid_offer.txt'),
        'non_profitable_offer': from_file(
            'non_profitable_Send_Optimal_Offer.txt'),
        'unfavourable_term_price_offer': from_file(
            'single_term_price_unfavourable_send_nash.txt'),
        'unfavourable_term_quantity_offer': from_file(
            'single_term_quantity_unfavourable_send_nash.txt'),
        'non_profitable_offer_or_deal': from_file(
            'Send_Optimal_Offer_or_Instructions.txt'),
        'non_profitable_offer_or_deal_no_disclosure': from_file(
            'Send_Optimal_Offer_or_Instructions_no_disclosure.txt'),
        'non_quantity_offer': from_file(
            'Not_Quantity_Send_Optimal_Offer.txt'),
        'non_price_offer': from_file('Not_Price_Send_Optimal_Offer.txt'),
        'invalid_offer_reminder': from_file('invalid_offer_reminder.txt'),
    }


PROMPTS = {
    # The retailer bot opens the conversation with the human Supplier
    # (repository's first_message_PC).
    'first_message': "Hi Supplier! I'm excited to start our negotiation. "
                     "I'd like to give you the opportunity to "
                     "make an offer first. Or if you prefer, I can make "
                     "the first offer. Just let me know! ",
    'offer_string': "Price of €%.2f and quantity of %s",

    'understanding_offer':
        'Here is the negotiator message you need to read: ',
    'retailer': _retailer_prompts(),
}

# Fallback SYSTEM prompt for the offer reader, taken verbatim from
# Ollama_LLMs/Modelfile_reader_of_offers_v4. Used with the plain llm_model
# when the dedicated reader model (config llm_reader) is not available on
# the selected Ollama host.
READER_SYSTEM_PROMPT = """
You are a strict data extraction engine. Your task is to extract the **Proposed Wholesale Price** and **Proposed Quantity** from a negotiation message.

### OUTPUT FORMAT
Output a python list: `[Price, Quantity]`
1. **Price:** Must include "€" and 2 decimals (e.g., 2.50€). If the input is just a number (e.g., "w=3"), you must add the "€".
2. **Quantity:** Integer only. If no *new* quantity is proposed, leave empty.

### CRITICAL RULES (READ CAREFULLY)
1. **Ignore Contextual Numbers:** You must **IGNORE** numbers referring to:
   - **P** or **Retail Price** or **Market Price**.
   - **Production Cost** or **Cost** or **PC**.
   - **Previous offers** that are just being referenced.
2. **Valid Indicators:** - **Price:** Look for "Price", "Offer", "w=" (Wholesale), or "w" (e.g., "w=3").
   - **Quantity:** Look for "Quantity", "Units", "q=" (Quantity), or "q" (e.g., "q=50").
3. **P is NOT Quantity:** If a user mentions "P" or "Retail Price" (e.g., "P is 4"), this is a price constraint, NOT a quantity. Do not put this number in the Quantity slot.
4. **Empty Output:** If the message contains numbers but no specific *new offer*, output `[,]`.

### EXAMPLES

Message: Here is the negotiator message you need to read: Thanks for sharing your goals. I'm happy to work towards a price agreement below the retail price. I'd like to explore Quantity options first. How about a Quantity of 40 and revisit Price later?
Output: [,40]

Message: Here is the negotiator message you need to read: Interesting, a price below 3.90€ and Quantity of 20 could work for me too. Can you consider a higher price, say around 2.40€, in exchange for a Quantity of 50?
Output: [2.40€, 50]

Message: Here is the negotiator message you need to read: Here is the negotiator message you need to read: I would like to agree on a price of 2.83 and a quantity of 30, deal?
Output: [2.83€, 30]

Message: Here is the negotiator message you need to read: My production cost is 2€ so I can't go that low.
Output: [,]

Message: Here is the negotiator message you need to read: my pc is 1 can you give a nice offer
Output: [,]

Message: Here is the negotiator message you need to read: I need 100 units. My budget is tight because my retail price is 11.
Output: [,100]

Message: Here is the negotiator message you need to read: considering my production cost of 1€, i have to offer a price of 3€ with a quantity of 80
Output: [3.00€,80]

Message: Here is the negotiator message you need to read: ok let's do w=2 and q=50
Output: [2.00€,50]

Message: Here is the negotiator message you need to read: my pc is 1 so the best I can do is w=3.5
Output: [3.50€,]

Message: Here is the negotiator message you need to read: w=2
Output: [2€,]
"""


def system_final_prompt(market_price: int | float,
                        disclosure_choice: str = C.DISCLOSE_NONE) -> str:
    """The retailer bot's negotiation system prompt, per condition.

    * Disclosure conditions (true_value / own_value): the split
      before_constraint + €<P> + after_constraint prompt. `market_price`
      must be the bot's ACTING retail price (the DISCLOSED value -- true
      or a lie), never the true draw. In ai_rp5_disclose_lie the acting
      value is 4, so the constraint reads €4 even though the draw is 5.
    * No disclosure: a single-file prompt with no retail price value in it
      (the bot is told not to mention any); `market_price` is unused.
    """
    prompts = PROMPTS['retailer']
    if disclosure_choice == C.DISCLOSE_NONE:
        return prompts['system_no_disclosure']
    # Splice inline: "Retail Price: €5. If asked, openly state this."
    return (prompts['before_constraint'].rstrip() + ' ' +
            f"€{market_price}" +
            prompts['after_constraint'].lstrip())


def acceptance_system_prompt() -> str:
    """Dedicated system prompt for an offer already evaluated as ACCEPT."""
    return PROMPTS['retailer']['system_accept']


def acceptance_user_prompt(user_message: str) -> str:
    """Ask the Retailer to accept and repeat the Supplier's exact terms."""
    return (PROMPTS['retailer']['accept_profitable_offer'] +
            user_message.strip() + ' (end of supplier message)')


def _case_prompt(prefix: str, user_message: str, strategy: str,
                 optimal_offer_str: str) -> str:
    """Compose a case-specific prompt without any conversation history."""
    strategy = strategy.replace(
        '(end of counterpart message)', '(end of supplier message)')
    return (prefix + user_message.strip() + strategy +
            optimal_offer_str + ']')


def empty_offer_prompt(user_message: str, optimal_offer_str: str,
                       disclosure_choice: str = C.DISCLOSE_TRUE) -> str:
    prompts = PROMPTS['retailer']
    strategy = (
        prompts['non_profitable_offer_or_deal_no_disclosure']
        if disclosure_choice == C.DISCLOSE_NONE
        else prompts['non_profitable_offer_or_deal'])
    return _case_prompt(strategy,
                        user_message, prompts['follow_up_prompt_without_offer'], optimal_offer_str,)


def offer_with_price_unfavourable_term_prompt(
        user_message: str, optimal_offer_str: str) -> str:
    prompts = PROMPTS['retailer']
    return _case_prompt(prompts['follow_up_prompt_unfavourable_term_offer'],
                        user_message, prompts['unfavourable_term_price_offer'],
                        optimal_offer_str)

def offer_with_quantity_unfavourable_term_prompt(
        user_message: str, optimal_offer_str: str) -> str:
    prompts = PROMPTS['retailer']
    return _case_prompt(prompts['follow_up_prompt_unfavourable_term_offer'],
                        user_message, prompts['unfavourable_term_quantity_offer'],
                        optimal_offer_str)


def offer_without_quantity_prompt(user_message: str,
                                  optimal_offer_str: str) -> str:
    prompts = PROMPTS['retailer']
    return _case_prompt(prompts['follow_up_prompt_without_quantity'],
                        user_message, prompts['non_quantity_offer'],
                        optimal_offer_str)


def offer_without_price_prompt(user_message: str,
                               optimal_offer_str: str) -> str:
    prompts = PROMPTS['retailer']
    return _case_prompt(prompts['follow_up_prompt_without_price'],
                        user_message, prompts['non_price_offer'],
                        optimal_offer_str)


def not_profitable_prompt(user_message: str,
                          optimal_offer_str: str) -> str:
    prompts = PROMPTS['retailer']
    return _case_prompt(prompts['follow_up_prompt_non_profitable'], user_message,
                        prompts['non_profitable_offer'], optimal_offer_str)


def offer_invalid_prompt(user_message: str,
                         optimal_offer_str: str) -> str:
    prompts = PROMPTS['retailer']
    return _case_prompt(prompts['follow_up_invalid_offer'], user_message,
                        prompts['invalid_offer_reminder'], optimal_offer_str)
