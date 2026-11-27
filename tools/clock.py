#!/usr/bin/env python3
"""The time clock. Clock-in is due at the desk by 8:00 AM ET on trading days.

  python3 tools/clock.py punch --date 2026-11-27 --time "7:52 AM"   record a punch (the time the punch message arrived)
  python3 tools/clock.py check --date 2026-11-27                    the 8:01 AM check: no punch yet -> today's row shows LATE
  python3 tools/clock.py journal --date 2026-11-27 --text "..."     record the day's journal entry for the nightly post
  python3 tools/clock.py off --date 2026-11-27                      a day off, called in before 8:00 AM: no LATE, no N/A

Exit 0 = something changed, 3 = nothing to change, 2 = market closed that day.
"""
import argparse, json, os, sys
from datetime import date, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
from post_day import HOLIDAYS

ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['punch', 'check', 'journal', 'off']); ap.add_argument('--date', required=True)
ap.add_argument('--time'); ap.add_argument('--text')
a = ap.parse_args()
d = date.fromisoformat(a.date)
if d.weekday() >= 5 or a.date in HOLIDAYS:
    print(json.dumps({'changed': False, 'reason': 'market closed on ' + a.date})); sys.exit(2)
p = os.path.join(build.ROOT, 'data', 'days.json'); data = json.load(open(p, encoding='utf-8'))
if any(x['date'] == a.date for x in data['days']): sys.exit(f'{a.date} is already posted')
before = json.dumps(data, sort_keys=True)
pend = next((x for x in data.setdefault('pending', []) if x['date'] == a.date), None)
if pend is None:
    pend = {'date': a.date, 'note': 'Posts itself at 8:12 PM ET'}; data['pending'].append(pend); data['pending'].sort(key=lambda x: x['date'], reverse=True)
box = data.setdefault('inbox', {}).setdefault(a.date, {})
out = {'date': a.date}
if a.cmd == 'punch':
    if not a.time: sys.exit('--time is required, like "7:52 AM"')
    t = datetime.strptime(a.time.strip().upper(), '%I:%M %p').strftime('%I:%M %p').lstrip('0')
    if 'clock_in' in box: sys.exit(f'already punched in at {box["clock_in"]}; the first punch stands')
    box['clock_in'] = t; pend.pop('late', None)
    out.update(punched=t, on_time=datetime.strptime(t, '%I:%M %p').time() <= datetime.strptime(data.get('clock_due', '8:00 AM'), '%I:%M %p').time())
elif a.cmd == 'off':
    if box.get('clock_in'): sys.exit('already punched in today; cannot also be off')
    box['off'] = True; pend.pop('late', None); pend['note'] = 'Day off, called in before the shift'; out.update(off=True)
elif a.cmd == 'check':
    if box.get('clock_in'): out.update(punched=box['clock_in'], late=False)
    elif box.get('off'): out.update(punched=None, late=False, off=True)
    else: pend['late'] = True; out.update(punched=None, late=True)
else:
    if not a.text: sys.exit('--text is required')
    box['journal'] = a.text.strip(); out.update(journal=True)
if not box: data['inbox'].pop(a.date, None)
changed = json.dumps(data, sort_keys=True) != before
if changed:
    json.dump(data, open(p, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); build.main()
out['changed'] = changed; print(json.dumps(out)); sys.exit(0 if changed else 3)
