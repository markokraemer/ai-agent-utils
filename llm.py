from typing import Union
import litellm
from litellm import acompletion
import os
import json
import openai
from openai import OpenAIError
import asyncio
import logging
from config import settings 

# Load environment variables
OPENAI_API_KEY = settings.openai_api_key
ANTHROPIC_API_KEY = settings.anthropic_api_key
GROQ_API_KEY = settings.groq_api_key

# Export environment variables
os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
os.environ['ANTHROPIC_API_KEY'] = ANTHROPIC_API_KEY
os.environ['GROQ_API_KEY'] = GROQ_API_KEY
# os.environ['LITELLM_LOG'] = 'DEBUG'

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def make_llm_api_call(messages, model_name, json_mode=False, temperature=0, max_tokens=None, tools=None, tool_choice="auto"):
    # litellm.set_verbose = True

    async def attempt_api_call(api_call_func, max_attempts=3):
        for attempt in range(max_attempts):
            try:
                response = await api_call_func()
                response_content = response.choices[0].message['content'] if json_mode else response
                if json_mode:
                    if not json.loads(response_content):
                        logger.info(f"Invalid JSON received, retrying attempt {attempt + 1}")
                        continue
                    else:
                        return response
                else:
                    return response
            except litellm.exceptions.RateLimitError as e:
                logger.warning(f"Rate limit exceeded. Waiting for 30 seconds before retrying...")
                await asyncio.sleep(30)
                continue
            except OpenAIError as e:
                logger.info(f"API call failed, retrying attempt {attempt + 1}. Error: {e}")
                await asyncio.sleep(5)
            except json.JSONDecodeError:
                logger.error(f"JSON decoding failed, retrying attempt {attempt + 1}")
                await asyncio.sleep(5)
        raise Exception("Failed to make API call after multiple attempts.")

    async def api_call():
        api_call_params = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"} if json_mode else None,
            **({"max_tokens": max_tokens} if max_tokens is not None else {})
        }
        if tools:
            api_call_params["tools"] = tools
            api_call_params["tool_choice"] = tool_choice

        # Ensure the first message is from the user for Anthropic models
        if "claude" in model_name.lower() or "anthropic" in model_name.lower():
            if messages[0]["role"] != "user":
                api_call_params["messages"] = [{"role": "user", "content": "."}] + messages
            api_call_params["extra_headers"] = {
                "anthropic-beta": "prompt-caching-2024-07-31"
            }
        # Log the API request
        logger.info(f"Sending API request: {json.dumps(api_call_params, indent=2)}")

        response = await acompletion(**api_call_params)

        # Log the API response
        logger.info(f"Received API response: {response}")

        return response
    
    return await attempt_api_call(api_call)


# Sample Usage
if __name__ == "__main__":
    pass