# API integrations for model comparison evaluations.
import requests
import json
import logging
import time
from django.conf import settings

logger = logging.getLogger(__name__)


def call_model(model_config: dict, messages: list, system_prompt: str) -> dict:
    """
    Route model call to appropriate provider based on model name.
    
    Central routing function that determines which API to call based on model name prefix.
    This ensures consistent routing logic across validation and production use.
    
    Args:
        model_config: Dict with 'name' (required) and optional provider-specific config
        messages: OpenAI-compatible message array with role/content dicts
        system_prompt: System instruction to prepend to messages
        
    Returns:
        Dict with 'response' (text), 'reasoning' (text or empty), and 'metadata'
    """
    model_name = model_config.get('name', '')
    
    if model_name.startswith('GDX/'):
        return call_gdx_model(model_config, messages, system_prompt)
    elif model_name.startswith('swiss-ai/'):
        return call_publicai_model(model_config, messages, system_prompt)
    else:
        return call_openrouter_model(model_config, messages, system_prompt)


def call_gdx_model(model_config: dict, messages: list, system_prompt: str) -> dict:
    """
    Call GDX API to generate a response from a specific model.
    
    Makes a synchronous request to GDX's chat completions endpoint with the specified
    model configuration. Model name format is "GDX/model-name" where model-name is extracted
    and used as the actual model parameter. Uses temperature 0.7 to match the current
    guidance system. If the API call fails, returns an error response with the model name
    revealed (for debugging in the comparison UI).

    Args:
        model_config: Dict with 'name' (required, format: "GDX/model-name")
        messages: OpenAI-compatible message array with role/content dicts
        system_prompt: System instruction to prepend to messages

    Returns:
        Dict with 'response' (text), 'reasoning' (empty), and 'metadata' (usage, model, etc.)
        On error, returns response starting with "ERROR:" and metadata contains 'error' key
    """
    url = "https://spark.kb28.ch/v1/chat/completions"
    
    if not settings.GDX_API_KEY:
        logger.error("GDX_API_KEY is not set in environment variables!")
        return {
            'response': "ERROR: GDX_API_KEY is not configured",
            'reasoning': '',
            'metadata': {'error': 'Missing API key', 'model': model_config['name']}
        }
    
    # Extract actual model name from "GDX/model-name" format
    actual_model = model_config['name'].split('/', 1)[1] if '/' in model_config['name'] else model_config['name']
    
    headers = {
        "Authorization": f"Bearer {settings.GDX_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": actual_model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "temperature": 0.7,
    }

    try:
        logger.info(f"Calling GDX for model: {model_config['name']} (actual: {actual_model})")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        
        start_time = time.time()
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        elapsed_time = time.time() - start_time
        
        logger.info(f"GDX response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"GDX error response: {response.text}")
        
        response.raise_for_status()
        data = response.json()

        choice = data['choices'][0]
        message = choice['message']

        return {
            'response': message.get('content', ''),
            'reasoning': '',
            'metadata': {
                'model': data.get('model'),
                'usage': data.get('usage', {}),
                'finish_reason': choice.get('finish_reason'),
                'response_time_seconds': round(elapsed_time, 3),
            }
        }
    except Exception as e:
        logger.error(f"GDX API call failed for {model_config['name']}: {e}")
        return {
            'response': f"ERROR: {str(e)}",
            'reasoning': '',
            'metadata': {'error': str(e), 'model': model_config['name']}
        }


def call_publicai_model(model_config: dict, messages: list, system_prompt: str) -> dict:
    """
    Call PublicAI API to generate a response from a specific model.
    
    Makes a synchronous request to PublicAI's chat completions endpoint with the specified
    model configuration. Uses temperature 0.7 to match the current guidance system. If the
    API call fails, returns an error response with the model name revealed (for debugging
    in the comparison UI).

    Args:
        model_config: Dict with 'name' (required)
        messages: OpenAI-compatible message array with role/content dicts
        system_prompt: System instruction to prepend to messages

    Returns:
        Dict with 'response' (text), 'reasoning' (empty), and 'metadata' (usage, model, etc.)
        On error, returns response starting with "ERROR:" and metadata contains 'error' key
    """
    url = "https://api.publicai.co/v1/chat/completions"
    
    logger.info(f"call_publicai_model called for {model_config.get('name')}")
    logger.info(f"PUBLICAI_API_KEY from settings: {repr(settings.PUBLICAI_API_KEY)}")
    
    if not settings.PUBLICAI_API_KEY:
        logger.error("PUBLICAI_API_KEY is not set in environment variables!")
        return {
            'response': "ERROR: PUBLICAI_API_KEY is not configured",
            'reasoning': '',
            'metadata': {'error': 'Missing API key', 'model': model_config['name']}
        }
    
    # Log API key info for debugging (first/last 4 chars only)
    api_key = settings.PUBLICAI_API_KEY
    print(f"PUBLICAI_API_KEY: {api_key[:4]}...{api_key[-4:]} (length: {len(api_key)})")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "User-Agent": "MyApp/1.0"
    }

    payload = {
        "model": model_config['name'],
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }

    try:
        logger.info(f"Calling PublicAI for model: {model_config['name']}")
        print(f"URL: {url}")
        print(f"Headers: {headers}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print(f"API key bytes: {api_key.encode()}")
        
        start_time = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        elapsed_time = time.time() - start_time
        
        logger.info(f"PublicAI response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        if response.status_code != 200:
            logger.error(f"PublicAI error response: {response.text}")
        
        response.raise_for_status()
        data = response.json()
        
        logger.debug(f"PublicAI response data: {json.dumps(data, indent=2)}")

        choice = data['choices'][0]
        message = choice['message']

        return {
            'response': message.get('content', ''),
            'reasoning': '',
            'metadata': {
                'model': data.get('model'),
                'usage': data.get('usage', {}),
                'finish_reason': choice.get('finish_reason'),
                'response_time_seconds': round(elapsed_time, 3),
            }
        }
    except KeyError as e:
        logger.error(f"PublicAI response parsing error for {model_config['name']}: missing key {e}")
        logger.error(f"Response data: {data if 'data' in locals() else 'N/A'}")
        return {
            'response': f"ERROR: Response parsing failed - missing key {e}",
            'reasoning': '',
            'metadata': {'error': f'Missing key: {e}', 'model': model_config['name']}
        }
    except Exception as e:
        logger.error(f"PublicAI API call failed for {model_config['name']}: {e}")
        logger.error(f"Full exception: {type(e).__name__}: {str(e)}")
        return {
            'response': f"ERROR: {str(e)}",
            'reasoning': '',
            'metadata': {'error': str(e), 'model': model_config['name']}
        }


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
        
        start_time = time.time()
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        elapsed_time = time.time() - start_time
        
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
                'response_time_seconds': round(elapsed_time, 3),
            }
        }
    except Exception as e:
        logger.error(f"OpenRouter API call failed for {model_config['name']}: {e}")
        return {
            'response': f"ERROR: {str(e)}",
            'reasoning': '',
            'metadata': {'error': str(e), 'model': model_config['name']}
        }

