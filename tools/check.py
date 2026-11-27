#!/usr/bin/env python3
"""Sanity checks before a Logbook post goes live. Exits non-zero on any problem.  python3 tools/check.py"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build

bad = []
data = json.load(open(os.path.join(build.ROOT, 'data', 'days.json'), encoding='utf-8'))
html = open(os.path.join(build.ROOT, 'index.html'), encoding='utf-8').read()
days = data['days']
if [d['date'] for d in days] != sorted(d['date'] for d in days): bad.append('days are not in date order')
if len({d['date'] for d in days}) != len(days): bad.append('a date appears twice')
traded = [d for d in days if not d.get('flat')]
if [d['n'] for d in traded] != list(range(1, len(traded) + 1)): bad.append('day numbers are not 1..N')
if [d['wo']['id'] for d in traded] != [f'WO-{i:03d}' for i in range(1, len(traded) + 1)]: bad.append('work order numbers are not in sequence')
for d in traded:
    if d['wins'] > d['round_trips'] or d['round_trips'] < 0 or d['fills'] < 1: bad.append(f'{d["date"]}: counts do not add up')
if build.apply(html, build.render(data)) != html: bad.append('index.html is out of date: run tools/build.py')
for name, text in (('index.html', html), ('data/days.json', json.dumps(data))):
    if re.search(r'\b[DF]?U\d{6,9}\b', text): bad.append(f'{name}: something that looks like a broker account number')
css = html[html.index('<style>'):html.index('</style>')]
if css.count('{') != css.count('}'): bad.append('unbalanced braces in the page styles')
for tag in ('section', 'article', 'table', 'tbody'):
    if len(re.findall(f'<{tag}[ >]', html)) != html.count(f'</{tag}>'): bad.append(f'unbalanced <{tag}> tags')
if bad:
    print('CHECK FAILED'); [print(' -', b) for b in bad]; sys.exit(1)
print(f'check ok: {len(traded)} traded days, {len(days) - len(traded)} flat days, running net {sum(d["net"] for d in traded):.2f}')
