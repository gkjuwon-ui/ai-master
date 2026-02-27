"""Test action parser inline + multiline formats."""
import sys, json
sys.path.insert(0, 'agent-runtime')
from core.plugin_loader import PluginLoader

pl = PluginLoader('agent-runtime/plugins')
pl.discover_plugins()
plugin = pl.get_plugin('apex-researcher')

tests = [
    ('ACTION: open_app PARAMS: {"name": "chrome"}', 'inline'),
    ('ACTION: open_app\nPARAMS: {"name": "chrome"}', 'multiline'),
    ('ACTION: wait PARAMS: {"seconds": 3}', 'inline-wait'),
    ('ACTION: hotkey PARAMS: {"keys": ["ctrl", "l"]}', 'inline-hotkey'),
    ('TOOL: google_search TOOL_PARAMS: {"query": "openai"}', 'inline-tool'),
    ('TOOL: google_search\nTOOL_PARAMS: {"query": "openai"}', 'multiline-tool'),
]

print("=== Parser Test ===")
ok = 0
fail = 0
for text, label in tests:
    result = plugin._parse_actions(text)
    if result:
        r = result[0]
        atype = r.get('tool_name', r.get('type', '?'))
        params = r.get('params', {})
        print(f"  OK   [{label:15s}]: type={atype}  params={params}")
        ok += 1
    else:
        print(f"  FAIL [{label:15s}]: no actions parsed")
        fail += 1

print(f"\n{ok}/{ok+fail} passed")
if fail:
    sys.exit(1)
