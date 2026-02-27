"""
LLM Client - Multi-provider LLM interface supporting OpenAI, Anthropic, Google, Mistral, Local, and Custom.
"""

import json
import base64
import random
from typing import Optional, Protocol
from abc import ABC, abstractmethod
from loguru import logger

def validate_llm_response(content: str) -> dict:
    """Validate and parse LLM response content into a structured action dict.

    Expects JSON with at minimum 'action' and 'thought' keys.
    Returns the parsed dict on success, or an error dict on failure
    so downstream code always receives a well-formed structure.
    """
    if not content or not content.strip():
        return {"action": "error", "thought": "Empty LLM response", "params": {}}

    text = content.strip()

    # Strip markdown code-fence wrapper if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Locate the outermost JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return {
            "action": "error",
            "thought": "No JSON object found in LLM response",
            "params": {},
            "raw": content[:200],
        }

    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        return {
            "action": "error",
            "thought": f"Invalid JSON in LLM response: {exc}",
            "params": {},
            "raw": content[:200],
        }

    if not isinstance(parsed, dict):
        return {"action": "error", "thought": "LLM response is not a JSON object", "params": {}}

    # --- Validate required keys ------------------------------------------------
    if "action" not in parsed:
        # Accept common alternative key names
        if "type" in parsed:
            parsed["action"] = parsed["type"]
        else:
            return {
                "action": "error",
                "thought": "LLM response missing 'action' key",
                "params": {},
                "raw": content[:200],
            }

    if "thought" not in parsed:
        parsed["thought"] = parsed.get("reasoning", parsed.get("explanation", ""))

    return parsed

class LLMClient(ABC):
    """Abstract LLM client interface."""

    # Provider identifier (set by create_llm_client factory)
    provider: str = "UNKNOWN"

    @abstractmethod
    async def chat(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> dict:
        """
        Send messages to LLM and return response.
        
        Args:
            messages: List of {role, content} dicts
            screenshot_b64: Optional base64 screenshot for multimodal
            
        Returns:
            dict with "content" key containing response text
        """
        pass


def create_llm_client(config: dict) -> LLMClient:
    """Factory to create the appropriate LLM client from config.

    For OGENT provider, the backend has already resolved platform keys into
    the config dict. The runtime just sees a normal OPENAI/CUSTOM config with
    an __ogent flag for token tracking.
    """
    provider = config.get("provider", "").upper()
    api_key = config.get("apiKey", "")
    model = config.get("model", "")
    base_url = config.get("baseUrl", "")
    is_ogent = config.get("__ogent", False)

    if provider == "OPENAI":
        client = OpenAIClient(api_key=api_key, model=model, base_url=base_url)
    elif provider == "ANTHROPIC":
        client = AnthropicClient(api_key=api_key, model=model)
    elif provider == "GOOGLE":
        client = GoogleClient(api_key=api_key, model=model)
    elif provider == "MISTRAL":
        client = MistralClient(api_key=api_key, model=model)
    elif provider == "LOCAL":
        client = LocalClient(model=model, base_url=base_url or "http://localhost:11434")
    elif provider == "CUSTOM":
        client = OpenAIClient(api_key=api_key, model=model, base_url=base_url)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    
    # Tag client with provider name for prompt adaptation
    client.provider = "OGENT" if is_ogent else provider
    # Carry ogent metadata for token tracking
    if is_ogent:
        client._ogent = True
        client._ogent_owner_id = config.get("__ogentOwnerId", "")
    return client


class OpenAIClient(LLMClient):
    """OpenAI / OpenAI-compatible client."""

    # Models known to support vision (image_url content type)
    _VISION_MODELS = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview",
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "gpt-5", "gpt-5-mini", "gpt-5.2",
        "chatgpt-4o-latest", "gpt-4o-2024",
    }

    # Models that require max_completion_tokens instead of max_tokens
    _MAX_COMPLETION_TOKENS_MODELS = {
        "gpt-5", "gpt-5-mini", "gpt-5.2",
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "o1", "o1-mini", "o1-pro", "o1-preview",
        "o3", "o3-mini", "o4-mini",
    }

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str = ""):
        self.model = model
        self._vision_supported: Optional[bool] = None  # None = unknown, auto-detect
        self._temperature_supported: Optional[bool] = None  # None = unknown, auto-detect
        # Pre-detect models known to not support temperature param
        model_lower = model.lower()
        _NO_TEMP_PREFIXES = ("o1", "o3", "o4", "gpt-5")
        for prefix in _NO_TEMP_PREFIXES:
            if model_lower.startswith(prefix):
                self._temperature_supported = False
                break
        try:
            from openai import AsyncOpenAI
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = AsyncOpenAI(**kwargs)
        except ImportError:
            raise RuntimeError("openai package not installed")

    def _get_token_param(self, max_tokens: int = 4096) -> dict:
        """Return the correct token limit parameter based on model."""
        model_lower = self.model.lower()
        for prefix in self._MAX_COMPLETION_TOKENS_MODELS:
            if model_lower.startswith(prefix):
                return {"max_completion_tokens": max_tokens}
        return {"max_tokens": max_tokens}

    def _check_vision_support(self) -> bool:
        """Check if the current model supports vision (image_url content).
        Returns cached result if already determined."""
        if self._vision_supported is not None:
            return self._vision_supported
        
        model_lower = self.model.lower()
        
        # Check against known vision models
        for vm in self._VISION_MODELS:
            if model_lower.startswith(vm):
                self._vision_supported = True
                return True
        
        # Known non-vision models/providers
        non_vision_prefixes = (
            "deepseek", "o1", "o3", "o4", "text-", "davinci", "babbage",
            "qwen", "yi-", "mixtral", "codestral",
        )
        for prefix in non_vision_prefixes:
            if model_lower.startswith(prefix):
                self._vision_supported = False
                logger.info(f"Model '{self.model}' detected as non-vision — screenshots will be described as text")
                return False
        
        # Default: assume vision is supported for unknown models (will fallback on error)
        return True

    def _format_messages(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> list[dict]:
        """Format messages, optionally attaching screenshot to the last user message."""
        formatted_messages = []
        use_vision = screenshot_b64 and self._check_vision_support()
        
        for msg in messages:
            if msg["role"] == "user" and use_vision and msg == messages[-1]:
                # Multimodal message with screenshot — use HIGH detail for accurate coordinate recognition
                content = [
                    {"type": "text", "text": msg["content"]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{screenshot_b64}",
                            "detail": "high",
                        },
                    },
                ]
                formatted_messages.append({"role": "user", "content": content})
            else:
                # Ensure content is always a plain string (strip any leftover image_url parts)
                if isinstance(msg.get("content"), list):
                    # Extract only text parts
                    text_parts = [p.get("text", "") for p in msg["content"] if isinstance(p, dict) and p.get("type") == "text"]
                    formatted_messages.append({"role": msg["role"], "content": " ".join(text_parts) if text_parts else str(msg["content"])})
                else:
                    formatted_messages.append(msg)
        
        return formatted_messages

    def _format_messages_text_only(self, messages: list[dict]) -> list[dict]:
        """Strip all image content — text-only fallback for non-vision models."""
        formatted = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                text_parts = [p.get("text", "") for p in msg["content"] if isinstance(p, dict) and p.get("type") == "text"]
                formatted.append({"role": msg["role"], "content": " ".join(text_parts) if text_parts else ""})
            else:
                formatted.append({"role": msg["role"], "content": msg.get("content", "")})
        return formatted

    async def chat(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> dict:
        formatted_messages = self._format_messages(messages, screenshot_b64)
        token_param = self._get_token_param(4096)
        temp_param = {} if self._temperature_supported is False else {"temperature": 0.2}

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                **temp_param,
                **token_param,
            )
            result = {"content": response.choices[0].message.content or ""}
            # Track token usage for ogent-1.0 billing
            if hasattr(response, "usage") and response.usage:
                result["_usage"] = {
                    "input_tokens": response.usage.prompt_tokens or 0,
                    "output_tokens": response.usage.completion_tokens or 0,
                    "total_tokens": response.usage.total_tokens or 0,
                }
            return result
        except Exception as e:
            error_str = str(e)

            # Detect temperature-unsupported error (e.g. gpt-5-mini only supports default temp)
            if "temperature" in error_str and ("unsupported" in error_str.lower() or "not support" in error_str.lower()):
                logger.warning(f"Model '{self.model}' does not support temperature param — retrying without it")
                self._temperature_supported = False
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=formatted_messages,
                        **token_param,
                    )
                    return {"content": response.choices[0].message.content or ""}
                except Exception as temp_err:
                    logger.error(f"OpenAI API no-temperature fallback failed: {temp_err}")
                    return {"content": f"[LLM Error: {temp_err}]"}

            # Detect vision-unsupported error and retry without images
            if "image_url" in error_str or "image" in error_str.lower() and "400" in error_str:
                logger.warning(f"Model '{self.model}' does not support vision — retrying without screenshots")
                self._vision_supported = False  # Cache for future calls
                text_only = self._format_messages_text_only(messages)
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=text_only,
                        **temp_param,
                        **token_param,
                    )
                    return {"content": response.choices[0].message.content or ""}
                except Exception as fallback_err:
                    logger.error(f"OpenAI API text-only fallback also failed: {fallback_err}")
                    return {"content": f"[LLM Error: {fallback_err}]"}

            logger.error(f"OpenAI API error: {e} | model={self.model} | base_url={getattr(self.client, '_base_url', 'default')}")
            # Check if this is a model-not-found error
            error_str = str(e)
            if hasattr(e, 'response'):
                try:
                    logger.error(f"OpenAI API error body: {e.response.text}")
                except:
                    pass
            if hasattr(e, 'body'):
                logger.error(f"OpenAI API error body attr: {e.body}")
            # Rate limit (429) — exponential backoff with up to 3 retries
            error_str = str(e)
            import asyncio
            if "429" in error_str or "rate" in error_str.lower() or "too many" in error_str.lower():
                for attempt in range(3):
                    delay = (2 ** attempt) * 2 + random.uniform(0, 1)  # 2s, 4s, 8s + jitter
                    logger.warning(f"OpenAI 429 rate limit — retry {attempt+1}/3 after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    try:
                        response = await self.client.chat.completions.create(
                            model=self.model,
                            messages=formatted_messages,
                            **temp_param,
                            **token_param,
                        )
                        return {"content": response.choices[0].message.content or ""}
                    except Exception as retry_err:
                        if attempt == 2:
                            logger.error(f"OpenAI API rate limit retries exhausted: {retry_err}")
                            return {"content": f"[LLM Error: rate limit — {retry_err}]"}
                        continue

            # Server-side transient errors (502 Bad Gateway, 503, 504) — retry with backoff
            if any(code in error_str for code in ("502", "503", "504", "Bad Gateway", "Service Unavailable", "Gateway Timeout")):
                for attempt in range(3):
                    delay = (2 ** attempt) * 3 + random.uniform(0, 2)  # 3s, 8s, 18s + jitter
                    logger.warning(f"OpenAI server error (5xx) — retry {attempt+1}/3 after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    try:
                        response = await self.client.chat.completions.create(
                            model=self.model,
                            messages=formatted_messages,
                            **temp_param,
                            **token_param,
                        )
                        return {"content": response.choices[0].message.content or ""}
                    except Exception as retry_err:
                        if attempt == 2:
                            logger.error(f"OpenAI API 5xx retries exhausted: {retry_err}")
                            return {"content": f"[LLM Error: server error — {retry_err}]"}
                        continue

            # Other errors — retry once after a brief delay
            await asyncio.sleep(1.0)
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=formatted_messages,
                    **temp_param,
                    **token_param,
                )
                return {"content": response.choices[0].message.content or ""}
            except Exception as retry_err:
                logger.error(f"OpenAI API retry failed: {retry_err}")
                return {"content": f"[LLM Error: {retry_err}]"}


class AnthropicClient(LLMClient):
    """Anthropic Claude client."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise RuntimeError("anthropic package not installed")

    async def chat(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> dict:
        # Separate system messages and build cache-aware system blocks
        system_blocks = []
        chat_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                block = {"type": "text", "text": msg["content"]}
                # Apply prompt caching for tagged selfPrompt messages
                if msg.get("__cached__"):
                    block["cache_control"] = {"type": "ephemeral"}
                system_blocks.append(block)
            elif msg["role"] == "user" and screenshot_b64 and msg == messages[-1]:
                content = [
                    {"type": "text", "text": msg["content"]},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": screenshot_b64,
                        },
                    },
                ]
                chat_messages.append({"role": "user", "content": content})
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        # Use structured system blocks for caching, fall back to plain string
        system_param = system_blocks if system_blocks else ""

        try:
            response = await self.client.messages.create(
                model=self.model,
                system=system_param,
                messages=chat_messages,
                max_tokens=4096,
                temperature=0.2,
            )

            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            # Log cache performance if available
            usage = getattr(response, 'usage', None)
            if usage:
                cache_read = getattr(usage, 'cache_read_input_tokens', 0)
                cache_create = getattr(usage, 'cache_creation_input_tokens', 0)
                if cache_read or cache_create:
                    logger.debug(f"Anthropic cache: read={cache_read}, created={cache_create}")

            return {"content": content}
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            import asyncio
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower() or "too many" in error_str.lower():
                for attempt in range(3):
                    delay = (2 ** attempt) * 2 + random.uniform(0, 1)
                    logger.warning(f"Anthropic 429 rate limit — retry {attempt+1}/3 after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    try:
                        response = await self.client.messages.create(
                            model=self.model,
                            system=system_param,
                            messages=chat_messages,
                            max_tokens=4096,
                            temperature=0.2,
                        )
                        content = ""
                        for block in response.content:
                            if hasattr(block, "text"):
                                content += block.text
                        return {"content": content}
                    except Exception as retry_err:
                        if attempt == 2:
                            logger.error(f"Anthropic rate limit retries exhausted: {retry_err}")
                            return {"content": f"[LLM Error: rate limit — {retry_err}]"}
                        continue

            # Server-side transient errors (502, 503, 504) — retry with backoff
            if any(code in error_str for code in ("502", "503", "504", "Bad Gateway", "Service Unavailable", "Gateway Timeout", "overloaded")):
                for attempt in range(3):
                    delay = (2 ** attempt) * 3 + random.uniform(0, 2)
                    logger.warning(f"Anthropic server error — retry {attempt+1}/3 after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    try:
                        response = await self.client.messages.create(
                            model=self.model,
                            system=system_param,
                            messages=chat_messages,
                            max_tokens=4096,
                            temperature=0.2,
                        )
                        content = ""
                        for block in response.content:
                            if hasattr(block, "text"):
                                content += block.text
                        return {"content": content}
                    except Exception as retry_err:
                        if attempt == 2:
                            logger.error(f"Anthropic 5xx retries exhausted: {retry_err}")
                            return {"content": f"[LLM Error: server error — {retry_err}]"}
                        continue

            await asyncio.sleep(1.0)
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    system=system_param,
                    messages=chat_messages,
                    max_tokens=4096,
                    temperature=0.2,
                )
                content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        content += block.text
                return {"content": content}
            except Exception as retry_err:
                logger.error(f"Anthropic API retry failed: {retry_err}")
                return {"content": f"[LLM Error: {retry_err}]"}


class GoogleClient(LLMClient):
    """Google Gemini client."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.model = model
        self.api_key = api_key
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.genai = genai
            self.gmodel = genai.GenerativeModel(model)
        except ImportError:
            raise RuntimeError("google-generativeai package not installed")

    async def chat(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> dict:
        import asyncio

        # Build proper multi-turn contents with roles for Gemini
        # Gemini expects: role="user" or role="model", with "parts" list
        contents = []
        system_text = ""
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            elif msg["role"] == "user":
                contents.append({"role": "user", "parts": [msg["content"]]})
            elif msg["role"] == "assistant":
                contents.append({"role": "model", "parts": [msg["content"]]})

        # Prepend system prompt to first user message (Gemini has no system role)
        if system_text and contents and contents[0]["role"] == "user":
            contents[0]["parts"][0] = system_text + "\n\n" + contents[0]["parts"][0]

        # Ensure conversation alternates user/model (Gemini requires this)
        # Merge consecutive same-role messages
        merged = []
        for c in contents:
            if merged and merged[-1]["role"] == c["role"]:
                merged[-1]["parts"].extend(c["parts"])
            else:
                merged.append(c)
        contents = merged

        # Ensure conversation starts with user
        if contents and contents[0]["role"] != "user":
            contents.insert(0, {"role": "user", "parts": ["Continue."]})
        
        # Ensure conversation ends with user (Gemini requires last message to be user)
        if contents and contents[-1]["role"] != "user":
            contents.append({"role": "user", "parts": ["Continue with your next action."]})

        # Add screenshot to the last user message if available
        if screenshot_b64 and contents:
            img_bytes = base64.b64decode(screenshot_b64)
            # Find last user message
            for i in range(len(contents) - 1, -1, -1):
                if contents[i]["role"] == "user":
                    contents[i]["parts"].append({
                        "mime_type": "image/jpeg",
                        "data": img_bytes,
                    })
                    break

        def _safe_extract_text(response) -> str:
            """Safely extract text from Gemini response — response.text raises ValueError if blocked."""
            try:
                return response.text or ""
            except ValueError:
                # Response blocked by safety filters
                feedback = getattr(response, 'prompt_feedback', None)
                block_reason = getattr(feedback, 'block_reason', 'UNKNOWN') if feedback else 'UNKNOWN'
                logger.warning(f"Gemini response blocked by safety filter: {block_reason}")
                return f"[LLM Error: Response blocked by safety filter — {block_reason}]"
            except Exception as ex:
                logger.warning(f"Gemini response text extraction failed: {ex}")
                return f"[LLM Error: Could not extract response text — {ex}]"

        # ── Attempt 1: Async call with timeout ──
        try:
            logger.debug("GoogleClient: calling generate_content_async…")
            response = await asyncio.wait_for(
                self.gmodel.generate_content_async(
                    contents,
                    generation_config={"temperature": 0.2, "max_output_tokens": 4096},
                ),
                timeout=120.0,
            )
            return {"content": _safe_extract_text(response)}
        except asyncio.TimeoutError:
            logger.error("Gemini API async call timed out after 120 seconds")
            return {"content": "[LLM Error: Gemini API call timed out after 120 seconds. Check your network connection and API key.]"}
        except Exception as e:
            logger.warning(f"Async Gemini call failed: {e}")

        # ── Attempt 2: Sync fallback in executor with timeout ──
        try:
            logger.debug("GoogleClient: trying sync fallback via executor…")
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.gmodel.generate_content(
                        contents,
                        generation_config={"temperature": 0.2, "max_output_tokens": 4096},
                    )
                ),
                timeout=120.0,
            )
            return {"content": _safe_extract_text(response)}
        except asyncio.TimeoutError:
            logger.error("Gemini API sync fallback timed out after 120 seconds")
            return {"content": "[LLM Error: Gemini API call timed out after 120 seconds]"}
        except Exception as e2:
            logger.error(f"Google Gemini API both attempts failed: {e2}")
            return {"content": f"[LLM Error: {e2}]"}


class MistralClient(LLMClient):
    """Mistral AI client using OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str = "mistral-large-latest"):
        self.model = model
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.mistral.ai/v1",
            )
        except ImportError:
            raise RuntimeError("openai package not installed (used for Mistral)")

    async def chat(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> dict:
        # Mistral doesn't support vision yet in most models, skip screenshots
        formatted = [{"role": m["role"], "content": m["content"]} for m in messages]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted,
                max_tokens=4096,
                temperature=0.2,
            )
            return {"content": response.choices[0].message.content or ""}
        except Exception as e:
            logger.error(f"Mistral API error: {e}")
            import asyncio
            await asyncio.sleep(1.0)
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=formatted,
                    max_tokens=4096,
                    temperature=0.2,
                )
                return {"content": response.choices[0].message.content or ""}
            except Exception as retry_err:
                logger.error(f"Mistral API retry failed: {retry_err}")
                return {"content": f"[LLM Error: {retry_err}]"}


class LocalClient(LLMClient):
    """Local/Ollama client using OpenAI-compatible API."""

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key="ollama",
                base_url=f"{base_url}/v1",
            )
        except ImportError:
            raise RuntimeError("openai package not installed (used for local/Ollama)")

    async def chat(self, messages: list[dict], screenshot_b64: Optional[str] = None) -> dict:
        formatted = [{"role": m["role"], "content": m["content"]} for m in messages]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted,
                max_tokens=4096,
                temperature=0.2,
            )
            return {"content": response.choices[0].message.content or ""}
        except Exception as e:
            logger.error(f"Local LLM API error: {e}")
            import asyncio
            await asyncio.sleep(1.0)
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=formatted,
                    max_tokens=4096,
                    temperature=0.2,
                )
                return {"content": response.choices[0].message.content or ""}
            except Exception as retry_err:
                logger.error(f"Local LLM API retry failed: {retry_err}")
                return {"content": f"[LLM Error: {retry_err}]"}
