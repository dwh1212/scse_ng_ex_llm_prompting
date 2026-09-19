import io
import contextlib
import json

from parse_data import load_items, get_unclaimed_items, save_result
from investigate import build_prompt, parse_response, validate_result, display_matches

# --- parse_data tests ---
items = load_items('found_items.json')
assert len(items) == 4, items
unclaimed = get_unclaimed_items(items)
ids = [i['id'] for i in unclaimed]
assert ids == ['F101', 'F102', 'F104'], ids
print('[OK] load_items / get_unclaimed_items')

save_result({'matches': ['F101'], 'confidence': 'HIGH'}, 'output/test.json')
with open('output/test.json', encoding='utf-8') as f:
    assert json.load(f) == {'matches': ['F101'], 'confidence': 'HIGH'}
print('[OK] save_result (dir auto-created)')

# --- build_prompt tests ---
sys_p, usr_p = build_prompt('I lost a black bag', unclaimed)
assert 'black bag' in usr_p and 'F101' in usr_p
assert 'matches' in sys_p and 'LOW' in sys_p and 'HIGH' in sys_p and 'MEDIUM' in sys_p
print('[OK] build_prompt')

# --- parse_response tests: plain JSON / fenced / extra text ---
r1 = parse_response('{"matches": ["F101"], "confidence": "MEDIUM"}')
assert r1 == {'matches': ['F101'], 'confidence': 'MEDIUM'}
r2 = parse_response('```json\n{"matches": [], "confidence": "LOW"}\n```')
assert r2 == {'matches': [], 'confidence': 'LOW'}, r2
r3 = parse_response('Here you go: {"matches": ["F102"], "confidence": "HIGH"} hope it helps')
assert r3 == {'matches': ['F102'], 'confidence': 'HIGH'}, r3
print('[OK] parse_response (plain / fenced / extra text)')

# --- validate_result tests ---
assert validate_result({'matches': ['F101'], 'confidence': 'LOW'}, unclaimed)
assert validate_result({'matches': [], 'confidence': 'HIGH'}, unclaimed)
assert not validate_result({'matches': ['F999'], 'confidence': 'HIGH'}, unclaimed)  # invalid id
assert not validate_result({'matches': 'F101', 'confidence': 'LOW'}, unclaimed)     # wrong type
assert not validate_result({'matches': [], 'confidence': 'MAYBE'}, unclaimed)       # bad confidence
assert not validate_result({'matches': []}, unclaimed)                              # missing key
assert not validate_result([], unclaimed)                                           # not a dict
print('[OK] validate_result')

# --- display_matches tests (capture stdout) ---
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    display_matches({'matches': ['F101'], 'confidence': 'MEDIUM'}, unclaimed)
out = buf.getvalue()
assert 'ID: F101' in out and 'backpack' in out and 'black' in out
assert 'Library 2nd floor' in out and 'MEDIUM' in out
print('[OK] display_matches (with matches)')

buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    display_matches({'matches': [], 'confidence': 'LOW'}, unclaimed)
assert 'No matches were found' in buf2.getvalue() and '[]' in buf2.getvalue()
print('[OK] display_matches (empty)')

print()
print('ALL UNIT TESTS PASSED')
