# OpenRouter API integration for model comparison evaluations.
import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def call_openrouter_model(model_config: dict, messages: list, system_prompt: str) -> dict:
    """
    Call OpenRouter API to generate a response from a specific model.
    
    Makes a synchronous request to OpenRouter's chat completions endpoint with the specified
    model configuration, including support for quantization filtering and reasoning tokens.
    Uses temperature 0.7 to match the current guidance system. If the API call fails, returns
    an error response with the model name revealed (for debugging in the comparison UI).

    Args:
        model_config: Dict with 'name' (required), optional 'quantizations' list, and optional
                     'reasoning' config (e.g., {"effort": "high", "exclude": false})
        messages: OpenAI-compatible message array with role/content dicts
        system_prompt: System instruction to prepend to messages

    Returns:
        Dict with 'response' (text), 'reasoning' (text or empty), and 'metadata' (usage, model, etc.)
        On error, returns response starting with "ERROR:" and metadata contains 'error' key
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set in environment variables!")
        return {
            'response': "ERROR: OPENROUTER_API_KEY is not configured",
            'reasoning': '',
            'metadata': {'error': 'Missing API key', 'model': model_config['name']}
        }
    
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    # Build request payload
    payload = {
        "model": model_config['name'],
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "temperature": 0.7,
    }

    # Add quantization parameter if specified
    if 'quantizations' in model_config and model_config['quantizations']:
        payload['provider'] = {
            "quantizations": model_config['quantizations']
        }

    # Add reasoning parameter if specified
    if 'reasoning' in model_config:
        payload['reasoning'] = model_config['reasoning']

    try:
        logger.info(f"Calling OpenRouter for model: {model_config['name']}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        logger.debug(f"Request headers: {headers}")
        
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        
        logger.info(f"OpenRouter response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"OpenRouter error response: {response.text}")
        
        response.raise_for_status()
        data = response.json()

        choice = data['choices'][0]
        message = choice['message']

        return {
            'response': message.get('content', ''),
            'reasoning': message.get('reasoning', ''),
            'metadata': {
                'model': data.get('model'),
                'usage': data.get('usage', {}),
                'finish_reason': choice.get('finish_reason'),
            }
        }
    except Exception as e:
        logger.error(f"OpenRouter API call failed for {model_config['name']}: {e}")
        return {
            'response': f"ERROR: {str(e)}",
            'reasoning': '',
            'metadata': {'error': str(e), 'model': model_config['name']}
        }

