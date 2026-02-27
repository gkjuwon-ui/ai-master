"""Test the idle-agents endpoint to check if LLM config is properly loaded"""
import requests
import json

# Try to find the runtime secret
config_paths = [
    r'C:\Users\gkjuw\AppData\Local\Programs\ogenti\resources\config.json',
    r'C:\Users\gkjuw\Downloads\ai_master\config.json',
]

secret = None
for p in config_paths:
    try:
        with open(p) as f:
            cfg = json.load(f)
        secret = cfg.get('agentRuntime', {}).get('secret', '')
        if secret:
            print(f"Found secret in {p}: {secret[:8]}...")
            break
    except:
        pass

if not secret:
    print("No secret found, trying default...")
    secret = "ogenti-runtime-secret"

# Call idle-agents endpoint
try:
    resp = requests.get(
        'http://localhost:4000/api/community/idle-agents',
        headers={'X-Runtime-Secret': secret},
        timeout=5,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json().get('data', [])
        print(f"Got {len(data)} agents")
        for a in data[:3]:
            llm = a.get('llm_config', {})
            key = llm.get('apiKey', '')
            masked_key = key[:8] + '...' + key[-4:] if key and len(key) > 12 else key
            print(f"  {a['name']}: provider={llm.get('provider')} model={llm.get('model')} baseUrl={llm.get('baseUrl')} key={masked_key}")
    else:
        print(f"Response: {resp.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Also test OpenAI directly with the key
if resp.status_code == 200 and data:
    llm = data[0].get('llm_config', {})
    api_key = llm.get('apiKey', '')
    model = llm.get('model', '')
    if api_key:
        print(f"\nTesting OpenAI API with model={model}...")
        try:
            test_resp = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={'model': model, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5},
                timeout=10,
            )
            print(f"OpenAI response: {test_resp.status_code}")
            if test_resp.status_code != 200:
                print(f"  Body: {test_resp.text[:300]}")
            else:
                print(f"  OK: {test_resp.json()['choices'][0]['message']['content']}")
        except Exception as e:
            print(f"  API test error: {e}")
