import unittest
from unittest.mock import patch

from experiment.bot_llm import BotLLM
from experiment.constants import C
from experiment.bot_strategy import BotStrategy
from experiment.offer import Evaluation, Offer
from experiment.optimal import (nash_bargaining_solution,
                                optimal_counter_offer,
                                optimal_solution_string)
from experiment.prompts import (empty_offer_prompt, not_profitable_prompt,
                                acceptance_system_prompt,
                                offer_invalid_prompt,
                                offer_without_price_prompt,
                                offer_without_quantity_prompt,
                                offer_with_price_unfavourable_term_prompt,
                                offer_with_quantity_unfavourable_term_prompt,
                                system_final_prompt)


class InvalidOfferPathTests(unittest.TestCase):
    production_cost = 1
    market_price = 5

    def test_invalid_price_and_quantity_are_classified(self):
        invalid_price = Offer(price=5.50, quantity=None, from_chat=True)
        invalid_quantity = Offer(price=None, quantity=115, from_chat=True)

        self.assertEqual(
            invalid_price.evaluate(self.production_cost, self.market_price),
            Evaluation.INVALID_OFFER)
        self.assertEqual(
            invalid_quantity.evaluate(self.production_cost, self.market_price),
            Evaluation.INVALID_OFFER)

    def test_invalid_offer_uses_complete_nash_counteroffer(self):
        offer = Offer(price=5.50, quantity=None, from_chat=True)
        expected = nash_bargaining_solution(
            self.production_cost, self.market_price)['offer']

        self.assertEqual(
            optimal_counter_offer(
                Evaluation.INVALID_OFFER, offer,
                self.production_cost, self.market_price),
            expected)
        self.assertEqual(
            optimal_solution_string(
                Evaluation.INVALID_OFFER, offer,
                self.production_cost, self.market_price),
            'Price of €3.33 and quantity of 80')

    def test_all_case_prompts_are_restored_without_history(self):
        latest_message = 'This is the unique latest Supplier message.'
        optimal = 'Price of €3.33 and quantity of 80'
        cases = {
            'empty': empty_offer_prompt(
                latest_message, optimal, C.DISCLOSE_NONE),
            'price_unfavourable':
                offer_with_price_unfavourable_term_prompt(
                    latest_message, optimal),
            'quantity_unfavourable':
                offer_with_quantity_unfavourable_term_prompt(
                    latest_message, optimal),
            'without_quantity': offer_without_quantity_prompt(
                latest_message, optimal),
            'without_price': offer_without_price_prompt(
                latest_message, optimal),
            'not_profitable': not_profitable_prompt(
                latest_message, optimal),
            'invalid': offer_invalid_prompt(latest_message, optimal),
        }

        for name, content in cases.items():
            with self.subTest(case=name):
                self.assertEqual(content.count(latest_message), 1)
                self.assertIn('(end of supplier message)', content)
                self.assertIn(optimal, content)
                self.assertTrue(content.endswith(']'))
                self.assertNotIn('<generation_examples>', content)
                self.assertNotIn('</generation_examples>', content)
                self.assertNotIn('Retailer(Me):', content)
                self.assertNotIn('Supplier:', content)
                self.assertNotIn('negotiations_transcript', content)

        self.assertIn('without an offer', cases['empty'])
        self.assertIn(
            'do not quote, repeat, or paraphrase their message',
            cases['empty'])
        self.assertIn(
            'I will offer the most efficient combination for both',
            cases['empty'])
        self.assertIn('Wholesale price of 4', cases['price_unfavourable'])
        self.assertIn('Quantity of 20', cases['quantity_unfavourable'])
        self.assertIn('without quantity', cases['without_quantity'])
        self.assertIn('without Wholesale price', cases['without_price'])
        self.assertIn('non-profitable offer', cases['not_profitable'])
        self.assertIn('invalid offer', cases['invalid'])

    def test_strategy_prompt_and_fallback_do_not_raise_or_return_empty(self):
        bot = BotStrategy()
        bot.role = 'Retailer'
        bot.user_message = 'I offer €5.50.'
        bot.config = {
            'production_cost': self.production_cost,
            'market_price': self.market_price,
        }
        offer = Offer(price=5.50, quantity=None, from_chat=True)
        optimal = optimal_solution_string(
            Evaluation.INVALID_OFFER, offer,
            self.production_cost, self.market_price)

        prompt = bot._respond_prompt(Evaluation.INVALID_OFFER, optimal)
        fallback_message, fallback_offer = bot._fallback_response(
            Evaluation.INVALID_OFFER, offer)

        self.assertIn('Price of €3.33 and quantity of 80', prompt)
        self.assertTrue(fallback_message)
        self.assertEqual((fallback_offer.price, fallback_offer.quantity),
                         (3.33, 80))

    def test_partial_unfavourable_offers_use_price_and_quantity_prompts(self):
        bot = BotStrategy()
        bot.user_message = 'The proposed term does not work.'
        bot.config = {'bot_disclosure': C.DISCLOSE_TRUE}
        optimal = 'Price of €2.80 and quantity of 75'

        price_prompt = bot._respond_prompt(
            Evaluation.NOT_PROFITABLE_ON_BOTH, optimal,
            Offer(price=4, quantity=None))
        quantity_prompt = bot._respond_prompt(
            Evaluation.NOT_PROFITABLE_ON_BOTH, optimal,
            Offer(price=None, quantity=20))
        both_prompt = bot._respond_prompt(
            Evaluation.NOT_PROFITABLE_ON_BOTH, optimal,
            Offer(price=3.5, quantity=20))

        self.assertIn('Wholesale price of 4', price_prompt)
        self.assertNotIn('Quantity of 20', price_prompt)
        self.assertIn('Quantity of 20', quantity_prompt)
        self.assertNotIn('Wholesale price of 4', quantity_prompt)
        self.assertIn('non-profitable offer', both_prompt)
        for prompt in (price_prompt, quantity_prompt, both_prompt):
            self.assertIn(optimal, prompt)
            self.assertNotIn('<generation_examples>', prompt)

    def test_system_prompts_are_minimal_and_do_not_contain_history(self):
        disclosed = system_final_prompt(5, C.DISCLOSE_TRUE).strip()
        non_disclosed = system_final_prompt(5, C.DISCLOSE_NONE).strip()

        self.assertIn('Retail Price: €5. If asked, openly state this.',
                      disclosed)
        self.assertNotIn('Do not mention any retail price value', disclosed)
        self.assertNotIn('Retail Price:', non_disclosed)
        for prompt in (disclosed, non_disclosed):
            self.assertNotIn('RESPONSE EXAMPLES', prompt)
            self.assertNotIn('Retailer(Me):', prompt)
            self.assertNotIn('Supplier:', prompt)
            self.assertNotIn('optimal_offer', prompt)


class GenerationPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_ollama_payload_keeps_case_prompt_but_has_no_history(self):
        class CapturingBot(BotLLM):
            async def _chat(self, model, messages, options=None):
                self.captured_messages = messages
                return {'message': {'content': '€3.33 and 80 units.'}}

        bot = CapturingBot()
        bot.config = {
            'market_price': 5,
            'bot_disclosure': C.DISCLOSE_NONE,
            'llm_model': 'llama3',
            'llm_temp': 0.1,
        }
        user_prompt = empty_offer_prompt(
            'Give me your best deal.',
            'Price of €3.33 and quantity of 80',
            C.DISCLOSE_NONE)

        await bot.get_llm_response(user_prompt)

        self.assertEqual(len(bot.captured_messages), 2)
        system_message, user_message = bot.captured_messages
        self.assertEqual(system_message['role'], 'system')
        self.assertEqual(user_message['role'], 'user')
        self.assertEqual(user_message['content'], user_prompt)
        self.assertIn('without an offer', user_message['content'])
        self.assertIn('Decision Tree Logic', user_message['content'])
        self.assertIn('Price of €3.33 and quantity of 80',
                      user_message['content'])
        self.assertNotIn('RESPONSE EXAMPLES', system_message['content'])
        self.assertNotIn('conversation', user_message['content'].lower())
        self.assertNotIn('Retailer(Me):', user_message['content'])

    async def test_acceptance_generation_uses_dedicated_prompts(self):
        class CapturingStrategy(BotStrategy):
            async def get_llm_response(self, content,
                                       system_prompt_override=None):
                self.generation_calls = getattr(
                    self, 'generation_calls', 0) + 1
                self.captured_prompt = content
                self.captured_system_prompt = system_prompt_override
                return {
                    'message': {
                        'content': (
                            'I accept €3.33 and 80 units. Please click '
                            'Confirm to make the agreement official.'),
                    },
                }

            async def _interpret_offer_llm(self, message, idx):
                return Offer(idx=idx, price=3.33, quantity=80,
                             from_chat=True)

            @staticmethod
            def extract_content(response):
                return response['message']['content']

            def _say(self, text):
                return self.player.process_llm_output(self.role, text)

        class PlayerStub:
            def process_llm_output(self, role, body):
                return {'chat': [{'nick': role, 'body': body}]}

        bot = CapturingStrategy()
        bot.role = C.ROLE_RETAILER_EMPLOYEE
        bot.user_message = 'I offer €3.33 and 80 units.'
        bot.player = PlayerStub()
        offer = Offer(price=3.33, quantity=80, from_chat=True)

        replies = bot._accept_offer(offer)
        with patch('experiment.bot_strategy.scrub_text', side_effect=lambda s: s):
            await anext(replies)
        await replies.aclose()

        self.assertEqual(
            bot.captured_prompt,
            'You have already started a negotiation in terms of Wholesale '
            'Price and Quantity representing a Reailer via Instant Messaging '
            'with a Supplier counterpart.\n'
            'Your negotiating counterpart is sitting across from you.\n'
            'You just received a message from your counterpart suggesting a '
            'very profitable offer for you. Simply accept the offer and '
            'repeat the terms of the offer to the supplier. Recommend the '
            'Supplier to click confirm in the interface below to make the '
            'agreement official.\n'
            'The message from your supplier counterpart says:\n'
            'I offer €3.33 and 80 units. (end of supplier message)')
        self.assertEqual(bot.captured_system_prompt,
                         acceptance_system_prompt())
        self.assertNotIn('Retail Price:', bot.captured_system_prompt)
        self.assertEqual(bot.generation_calls, 1)

    async def test_acceptance_hallucinations_retry_three_times_then_fallback(self):
        class HallucinatingStrategy(BotStrategy):
            async def get_llm_response(self, content,
                                       system_prompt_override=None):
                self.generation_calls = getattr(
                    self, 'generation_calls', 0) + 1
                return {
                    'message': {
                        'content': (
                            'I accept €2.40 and 60 units. Please click '
                            'Confirm to make the agreement official.'),
                    },
                }

            async def _interpret_offer_llm(self, message, idx):
                return Offer(idx=idx, price=2.40, quantity=60,
                             from_chat=True)

            @staticmethod
            def extract_content(response):
                return response['message']['content']

            def _say(self, text):
                return self.player.process_llm_output(self.role, text)

        class PlayerStub:
            def process_llm_output(self, role, body):
                return {'chat': [{'nick': role, 'body': body}]}

        bot = HallucinatingStrategy()
        bot.role = C.ROLE_RETAILER_EMPLOYEE
        bot.user_message = 'I offer €3.33 and 80 units.'
        bot.player = PlayerStub()
        offer = Offer(price=3.33, quantity=80, from_chat=True)

        replies = bot._accept_offer(offer)
        with patch('experiment.bot_strategy.scrub_text', side_effect=lambda s: s), \
                patch('experiment.bot_strategy.log_debug'):
            first_payload = await anext(replies)
        await replies.aclose()

        sent_text = first_payload['chat'][0]['body']
        self.assertEqual(bot.generation_calls, 3)
        self.assertIn('€3.33', sent_text)
        self.assertIn('80', sent_text)
        self.assertIn('CONFIRM', sent_text)
        self.assertNotIn('€2.40', sent_text)


if __name__ == '__main__':
    unittest.main()
