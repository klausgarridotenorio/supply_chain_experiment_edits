"""
LLM layer of the AI retailer, adapted from the example repository's
bot_llm.py (Ollama + llama3).

Adaptations for this project:
  * TRANSPORT: no channel pushes / asyncio tasks -- the methods here just
    RETURN strings/Offers; BotStrategy yields the payloads through the
    Negotiation page's async live_method (native oTree 6).
  * HOSTS: the repository leased hosts through a session-level queue
    (session_patch.py). Here the enabled `http(s)://...` keys of the
    session config form a failover list, with the LOCAL Ollama
    (http://localhost:11434) always appended as the last resort -- so a
    plain local `ollama serve` with llama3 works with no remote hosts.
  * READER: every natural-language message being interpreted as an offer
    is sent directly to offer_reader_v4, with no alternate parsing or
    plain-llama fallback in the offer-reading path.

The mixin expects the concrete class (NegotiationBot) to provide:
config (with llm_* keys, market_price, production_cost, participant_code),
constraint_user / constraint_bot (BotStrategy).
"""
import json
import re
from typing import Any

import httpx
from ollama import AsyncClient, ChatResponse

from .constants import C
from .optimal import nash_bargaining_solution
from .offer import Offer
from .prompts import PROMPTS, system_final_prompt
from .utils import log_debug, log_interpret

LOCAL_OLLAMA = 'http://localhost:11434'
PATTERN_OFFER = re.compile(r'\[([^]]+)]')

class BotLLM:
    """LLM helpers mixed into NegotiationBot (see bot_strategy.py)."""
    config: dict[str, Any] = None

    # Lazy state (class-level defaults; instances overwrite on first use).
    client = None
    _llm_host = None

    @staticmethod
    def _log_llm_input(backend: str, model: str,
                       messages: list[dict[str, str]],
                       options: dict[str, Any] = None):
        """Print the exact messages sent to a model, without credentials."""
        log_debug(
            f"[LLM INPUT] backend={backend} model={model} options={options}",
            "\n" + json.dumps(messages, indent=2, ensure_ascii=False))

    @staticmethod
    def _log_llm_raw_output(backend: str, model: str,
                            response: ChatResponse | dict[str, Any]):
        """Print model text before extract_content/scrub_text trimming."""
        try:
            content = response['message']['content']
        except (KeyError, TypeError):
            content = response
        log_debug(
            f"[LLM RAW OUTPUT before trimming] backend={backend} model={model}",
            "\n" + str(content))

    ############################################################################
    # Client / host handling
    ############################################################################
    def _host_candidates(self) -> list[str]:
        """Load-balance enabled remote Ollama hosts, then try local last."""
        hosts = [key for key, enabled in self.config['session_config'].items()
                 if isinstance(key, str)
                 and key.startswith(('http://', 'https://'))
                 and key != LOCAL_OLLAMA
                 and enabled is True]
        # Stable per-participant rotation spreads groups across hosts.
        if hosts:
            shift = sum(map(ord, self.config['participant_code'])) % len(hosts)
            hosts = hosts[shift:] + hosts[:shift]
        return hosts + [LOCAL_OLLAMA]

    def _make_client(self, host: str) -> AsyncClient:
        auth = None
        if self.config['llm_user'] and host != LOCAL_OLLAMA:
            auth = httpx.BasicAuth(username=self.config['llm_user'],
                                   password=self.config['llm_pass'])
        # Short connect timeout: an unreachable host must fail over fast,
        # while a slow generation still gets a generous read window.
        timeout = httpx.Timeout(120, connect=5)
        return AsyncClient(host=host, auth=auth, timeout=timeout)

    async def _chat(self, model: str, messages: list[dict[str, str]],
                    options: dict[str, Any] = None) \
            -> ChatResponse | dict[str, Any]:
        """One chat call with failover across the host candidates. The
        winning host is kept for the rest of the negotiation.

        Calls fail over across the configured SURF Ollama servers and the
        local Ollama instance. If every host is unavailable, the final
        connection error is raised to the solver fallback."""

        if self.client is not None:
            backend = self._llm_host or 'ollama-sticky-host'
            self._log_llm_input(backend, model, messages, options)
            response = await self.client.chat(model=model, options=options,
                                              messages=messages)
            self._log_llm_raw_output(backend, model, response)
            return response

        last_exc = None
        for host in self._host_candidates():
            client = self._make_client(host)
            self._log_llm_input(host, model, messages, options)
            try:
                response = await client.chat(model=model, options=options,
                                             messages=messages)
            except (httpx.HTTPError, ConnectionError, OSError) as exc:
                log_debug(f"[BotLLM] host {host} unavailable: {exc!r}")
                last_exc = exc
                continue
            self.client = client
            self._llm_host = host
            log_debug(f"[BotLLM] using host {host}")
            self._log_llm_raw_output(host, model, response)
            return response

        raise last_exc

    ############################################################################
    # Message generation
    ############################################################################
    async def get_llm_response(self, content: str,
                               system_prompt_override: str | None = None) \
            -> ChatResponse:
        assert isinstance(content, str)
        # The system prompt depends on the disclosure condition: with a
        # disclosed value (true or a lie) it carries the bot's ACTING
        # retail price -- never the true draw; with no disclosure it is
        # the dedicated prompt that names no retail price at all.
        system_prompt = system_prompt_override
        if system_prompt is None:
            system_prompt = system_final_prompt(
                self.config['market_price'],
                self.config.get('bot_disclosure', C.DISCLOSE_NONE))
        messages = [{'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': content}]
        return await self._chat(
            model=self.config['llm_model'],
            options={'temperature': self.config['llm_temp']},
            messages=messages)

    @staticmethod
    def extract_content(response: ChatResponse) -> str:
        """Clean the raw LLM output into a single chat line (repo logic)."""
        def remove_inner(string: str, start_char: str, end_char: str):
            while start_char in string and end_char in string:
                start_pos = string.find(start_char)
                end_pos = string.find(end_char, start_pos) + 1
                if 0 <= start_pos < end_pos:
                    string = string[:start_pos] + string[end_pos:]
                else:
                    break
            return string

        def clean_leading_non_alphanum(s: str) -> str:
            return re.sub(r'^[^a-zA-Z0-9]+', '', s)

        try:
            raw_content: str = response['message']['content']
            content = raw_content.strip()
        except KeyError:
            log_debug(f"Unexpected response format: {response}")
            return f"\nUnexpected response format: {response}\n"

        # Extract text within the quotes if quotes are found
        if content.count('"') > 1:
            start = content.find('"') + 1
            end = content.rfind('"')
            # Prevent cases in which user introduces parameters inside ""
            if len(content[start:end]) > 30:
                content = content[start:end]
        else:
            # Remove 'System' starts
            if content.lower().startswith('system:'):
                content = content[7:].strip()
            if content.lower().startswith('system,'):
                content = content[7:].strip()

        # Remove text within parentheses if no quotes are found
        content = remove_inner(content, '(', ')')

        # Remove text before "optimal_offer"
        if 'optimal_offer' in content:
            split_list = content.split('optimal_offer', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content

        # Remove text before the first colon
        s = 0
        while ':' in content and s != 3:
            split_list = content.split(':', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content
            s += 1

        # Remove internal thoughts
        s = 0
        while 'Here is the most efficient offer' in content and s != 3:
            split_list = content.split('Here is the most efficient offer', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content
            s += 1

        s = 0
        while 'response' in content and s != 3:
            split_list = content.split('response', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content
            s += 1

        content = clean_leading_non_alphanum(content)
        # Split the content at line breaks and take only the first part
        content = content.split('\n', 1)[0]
        content = content.strip().strip('"')

        log_debug('[LLM OUTPUT after extract_content]', '\n' + content)
        return content

    ############################################################################
    # Offer interpretation (reading offers out of natural language)
    ############################################################################
    async def interpret_offer(self, message: str, idx: int) -> Offer:
        """Send the message directly to offer_reader_v4."""
        return await self._interpret_offer_llm(message, idx)

    async def _interpret_offer_llm(self, message: str, idx: int) -> Offer:
        content = PROMPTS['understanding_offer'] + message
        response = await self._chat(
            model='offer_reader_v4',
            messages=[{'role': 'user', 'content': content}])
        llm_output = response['message']['content']
        log_debug('[DEBUG bot_llm.interpret_offer]', llm_output)

        # Find the [Price, Quantity] pattern in the reader output.
        price = quantity = None
        match_list = list(PATTERN_OFFER.finditer(llm_output))
        for match in reversed(match_list):
            parts = [part.replace('<', '').replace('>', '').strip()
                     for part in match.group(1).split(',')]

            price, quantity = self.extract_price_quantity_1(parts)
            if price is not None and quantity is not None:
                break

            price, quantity = self.extract_price_quantity_2(parts)
            if price is not None and quantity is not None:
                break

        log_interpret(message, llm_output, price, quantity)

        return Offer(idx=idx, from_chat=True, price=price, quantity=quantity)

    def extract_price_quantity_1(self, parts: list[str]) \
            -> tuple[float | None, int | None]:
        # Range outputs like [None, 60-85]: answer with the Nash offer when
        # it falls inside the range (repo logic).
        for index, part in enumerate(parts):
            if '-' in part:
                nash_result = nash_bargaining_solution(self.constraint_user,
                                                       self.constraint_bot)
                nash_price, nash_quantity = nash_result['offer']

                bits = part.split('-')
                try:
                    if index == 0:
                        low, high = float(bits[0]), float(bits[1])
                        if low <= nash_price <= high:
                            return nash_price, nash_quantity
                    if index == 1:
                        low, high = int(bits[0]), int(bits[1])
                        if low <= nash_quantity <= high:
                            return nash_price, nash_quantity
                except ValueError:
                    continue

        return None, None

    @classmethod
    def extract_price_quantity_2(cls, parts: list[str]) \
            -> tuple[float | None, int | None]:
        floats = [cls.get_float(part.replace('€', '')) for part in parts]

        if len(floats) == 1:
            pass
        elif len(floats) == 2:
            return floats[0], int(floats[1]) if floats[1] is not None else None
        elif len(floats) == 3:
            if floats[0] is not None and floats[2] is not None:
                return floats[0], int(floats[2])
            elif floats[0] is not None and floats[1:] == [None, None]:
                return floats[0], None
            elif floats[:2] == [None, None] and floats[2] is not None:
                return None, int(floats[2])

        return None, None

    @staticmethod
    def get_float(p: str) -> float | None:
        try:
            p = ''.join(s for s in p if s.isdigit() or s == '.')
            return round(float(p), 2)
        except ValueError:
            pass
