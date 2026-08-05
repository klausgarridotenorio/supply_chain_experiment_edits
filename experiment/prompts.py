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

The .txt fragments live in <project root>/prompts/retailer/ and are
concatenated by the *_prompt builder functions below, exactly like in the
repository.
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
        'follow_up_prompt_2nd': from_file('follow_up_user_message.txt'),
        'follow_up_prompt_without_offer': from_file(
            'follow_up_user_message_without_offer.txt'),
        'follow_up_prompt_unfavourable_term_offer': from_file(
            'follow_up_user_message_unfavourable_term_offer.txt'),
        'follow_up_prompt_without_price': from_file(
            'follow_up_user_message_without_price.txt'),
        'follow_up_prompt_without_quantity': from_file(
            'follow_up_user_message_without_quantity.txt'),
        'non_profitable_offer': from_file(
            'non_profitable_Send_Optimal_Offer.txt'),
        'unfavourable_term_offer': from_file(
            'single_term_unfavourable_send_nash.txt'),
        'non_profitable_offer_or_deal': from_file(
            'Send_Optimal_Offer_or_Instructions.txt'),
        # No-disclosure variant: Rule 2.b (retail price question) declines
        # instead of stating the price.
        'non_profitable_offer_or_deal_no_disclosure': from_file(
            'Send_Optimal_Offer_or_Instructions_no_disclosure.txt'),
        'follow_up_conversation': from_file(
            'follow_up_conversation_history.txt'),
        'non_quantity_offer': from_file(
            'Not_Quantity_Send_Optimal_Offer.txt'),
        'follow_up_invalid_offer': from_file(
            'follow_up_user_message_invalid_offer.txt'),
        'invalid_offer_reminder': from_file('invalid_offer_reminder.txt'),
        'non_price_offer': from_file('Not_Price_Send_Optimal_Offer.txt'),
    }


PROMPTS = {
    # The retailer bot opens the conversation with the human Supplier
    # (repository's first_message_PC).
    'first_message': "Hi Supplier! I'm excited to start our negotiation. "
                     "As we begin, I'd like to give you the opportunity to "
                     "make an offer first. Or if you prefer, I can make "
                     "the first offer. Just let me know! ",
    'offer_string': "Price of €%.2f and quantity of %s",

    'understanding_offer':
        'Here is the negotiator message you need to read: ',
    'accept_from_chat': 'Accept the offer sent by your negotiation counterpart '
                        'because the price and quantity terms are favourable, '
                        'thank your counterpart for their understanding but do not '
                        'disclose the existence of your payoff table. '
                        'Also, Ask your counterpart to please click the '
                        'CONFIRM button in the interface, which can be '
                        'found bellow the SEND button.'
                        '(Maximum 30 words and one paragraph) '
                        'Here is the last message from your counterpart: ',
    'accept_from_interface': 'Accept the offer sent by your negotiation counterpart '
                             'because the price and quantity terms are favourable, '
                             'thank your counterpart for their understanding but do not '
                             'disclose the existence of your payoff table. '
                             '(Maximum 30 words and one paragraph) '
                             'Here is the last message from your counterpart: ',

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
   - **RP** or **Retail Price** or **Market Price**.
   - **Production Cost** or **Cost** or **PC**.
   - **Previous offers** that are just being referenced.
2. **Valid Indicators:** - **Price:** Look for "Price", "Offer", "w=" (Wholesale), or "w" (e.g., "w=3").
   - **Quantity:** Look for "Quantity", "Units", "q=" (Quantity), or "q" (e.g., "q=50").
3. **RP is NOT Quantity:** If a user mentions "RP" or "Retail Price" (e.g., "RP is 4"), this is a price constraint, NOT a quantity. Do not put this number in the Quantity slot.
4. **Empty Output:** If the message contains numbers but no specific *new offer*, output `[,]`.

### EXAMPLES

Message: Here is the negotiator message you need to read: Thanks for sharing your goals. I'm happy to work towards a price agreement below the retail price. I'd like to explore Quantity options first. How about we aim for a Quantity of 40 and revisit Price later?
Output: [,40]

Message: Here is the negotiator message you need to read: Interesting, a price below 3.90€ and Quantity of 20 could work for me too. Can you consider a higher price, say around 2.40€, in exchange for a Quantity of 50?
Output: [2.40€, 50]

Message: Here is the negotiator message you need to read: I would like to agree on a price of 3.83 and a quantity of 30, do we have a deal?
Output: [3.83€, 30]

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
      before_constraint + €<RP> + after_constraint prompt. `market_price`
      must be the bot's ACTING retail price (the DISCLOSED value -- true
      or a lie), never the true draw. In ai_rp5_disclose_lie the acting
      value is 4, so the constraint reads €4 even though the draw is 5.
    * No disclosure: a single-file prompt with no retail price value in it
      (the bot is told not to mention any); `market_price` is unused.
    """
    prompts = PROMPTS['retailer']
    if disclosure_choice == C.DISCLOSE_NONE:
        return prompts['system_no_disclosure']
    # Splice inline: "... the fixed retail price of €5. ..." (from_file
    # newline-terminates the fragments, so rstrip before joining).
    return (prompts['before_constraint'].rstrip() + ' ' +
            f"€{market_price}" +
            prompts['after_constraint'].lstrip())


def empty_offer_prompt(user_message: str, optimal_offer_str: str,
                       interactions: str,
                       disclosure_choice: str = C.DISCLOSE_TRUE) -> str:
    """NOT_OFFER reply prompt. The decision tree differs per condition:
    with a disclosure (true or lie) Rule 2.b states the acting retail
    price; with no disclosure it declines to reveal it."""
    prompts = PROMPTS['retailer']
    decision_tree = (
        prompts['non_profitable_offer_or_deal_no_disclosure']
        if disclosure_choice == C.DISCLOSE_NONE
        else prompts['non_profitable_offer_or_deal'])
    return (prompts['follow_up_prompt_without_offer'] +
            user_message + ' ' +
            decision_tree +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_with_single_unfavourable_term_prompt(user_message: str,
                                               optimal_offer_str: str,
                                               interactions: str) -> str:
    prompts = PROMPTS['retailer']
    return (prompts['follow_up_prompt_unfavourable_term_offer'] +
            user_message + ' ' +
            prompts['unfavourable_term_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_without_quantity_prompt(user_message: str, optimal_offer_str: str,
                                  interactions: str) -> str:
    prompts = PROMPTS['retailer']
    return (prompts['follow_up_prompt_without_quantity'] +
            user_message + ' ' +
            prompts['non_quantity_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_without_price_prompt(user_message: str, optimal_offer_str: str,
                               interactions: str) -> str:
    prompts = PROMPTS['retailer']
    return (prompts['follow_up_prompt_without_price'] +
            user_message + ' ' +
            prompts['non_price_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def not_profitable_prompt(user_message: str, optimal_offer_str: str,
                          interactions: str) -> str:
    prompts = PROMPTS['retailer']
    return (prompts['follow_up_prompt_2nd'] +
            user_message + ' ' +
            prompts['non_profitable_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_invalid_prompt(user_message: str) -> str:
    prompts = PROMPTS['retailer']
    return (prompts['follow_up_invalid_offer'] +
            user_message + ' ' +
            prompts['invalid_offer_reminder'])
