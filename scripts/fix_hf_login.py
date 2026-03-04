import json

with open('notebooks/ogenti_a100_scout.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb['cells']:
    src = ''.join(cell.get('source', []))
    if 'google.colab import userdata' in src:
        cell['source'] = [
            'from huggingface_hub import login\n',
            '\n',
            '# Paste your HuggingFace token below\n',
            'HF_TOKEN = "hf_YOUR_TOKEN_HERE"\n',
            '\n',
            'login(token=HF_TOKEN)\n',
            'print("Logged in!")'
        ]
        print('FIXED!')
        break
else:
    print('Cell not found')

with open('notebooks/ogenti_a100_scout.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Saved!')
