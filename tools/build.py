#!/usr/bin/env python3
"""Rebuild the day-driven blocks of index.html from data/days.json.

Blocks live between <!--auto:NAME--> and <!--/auto:NAME--> markers:
  tape     homepage receipts tape (latest 5 traded days)
  home     homepage stat cards
  totals   Logbook totals
  rows     Logbook daily log rows
  wos      Logbook work orders
Everything outside the markers is left alone. Run:  python3 tools/build.py
"""
import json, os, re, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
FULL = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def d_(s): return date.fromisoformat(s)
def label(s): d = d_(s); return f'{WD[d.weekday()]} {MO[d.month - 1]} {d.day}'
def money(v, places=2):
    a = f'{abs(v):,.{places}f}'
    if round(v, places) < 0: return f'&minus;${a}'
    if round(v, places) > 0: return f'+${a}'
    return f'${a}'
def cls(v): return 'neg' if round(v, 2) < 0 else ('pos' if round(v, 2) > 0 else '')
def winrate(d): return f"{round(100 * d['wins'] / d['round_trips'])}%" if d['round_trips'] else '&mdash;'


def tape(traded):
    show = traded[-5:][::-1]
    items = []
    for d in show:
        items.append(('day', f"<b>DAY {d['n']}</b>{label(d['date'])}"))
        items.append(('', f"<b>NET</b><span class=\"{cls(d['net'])}\">{money(d['net'])}</span>"))
        for k, v in d['tape']: items.append(('', f'<b>{k}</b>{v}'))
    out = []
    for hidden in ('', ' aria-hidden="true"'):
        for c, body in items:
            out.append(f'      <span class="tape-item{" " + c if c else ""}"{hidden}>{body}</span>')
    dur = 5 * len(items)
    style = '' if dur == 130 else f' style="animation-duration:{dur}s"'
    return f'<div class="tape-track"{style}>\n' + '\n'.join(out) + '\n    </div>'


def home(traded):
    n = len(traded); last = traded[-1]; run = sum(d['net'] for d in traded); rts = sum(d['round_trips'] for d in traded)
    c = lambda v: f' class="{cls(v)}"' if cls(v) == 'neg' else ''
    if n <= 4:
        rt_note = f'Round trips in {n} days: ' + ', then '.join(str(d['round_trips']) for d in traded) if n > 1 else 'Round trips on day 1'
        prev = ', '.join(f"Day {d['n']} was {d['largest_pct']}%" for d in traded[:-1])
        size_note = f"Largest single position on Day {last['n']}. " + (prev + '. ' if prev else '') + 'My limit is 25%'
    else:
        rt_note = f"Round trips in {n} trading days. Day {last['n']} had {last['round_trips']}"
        top = max(traded, key=lambda d: d['largest_pct'])
        size_note = f"Largest single position on Day {last['n']}. The worst so far was {top['largest_pct']}% on Day {top['n']}. My limit is 25%"
    first, lastd = d_(traded[0]['date']), d_(last['date'])
    span = f'{label(traded[0]["date"])} through {label(last["date"])}, {lastd.year}' if n > 1 else f'{label(last["date"])}, {lastd.year}'
    prev_wd = FULL[(lastd.weekday() - 1) % 7]
    return '\n'.join([
        f'<div class="stat"><b{c(run)}>{money(run, 0)}</b><span>Running net after {n} day{"s" if n != 1 else ""}, commissions included</span></div>',
        f'          <div class="stat"><b{c(last["net"])}>{money(last["net"], 0)}</b><span>Day {last["n"]} net. {last["home_note"]}</span></div>',
        f'          <div class="stat"><b>{rts}</b><span>{rt_note}</span></div>',
        f'          <div class="stat"><b>{last["largest_pct"]}%</b><span>{size_note}</span></div>',
        f'          <p class="src">My own broker statements, {span}. A trade date runs 8 PM to 8 PM ET, so {prev_wd} night\'s overnight session counts toward {FULL[lastd.weekday()]}. These are the numbers I\'m working to change.</p>',
    ])


def totals(traded):
    run = sum(d['net'] for d in traded); n = len(traded)
    op = sum(1 for d in traded if d.get('wo', {}).get('status') == 'Open'); cl = sum(1 for d in traded if d.get('wo', {}).get('status') == 'Closed')
    c = f' class="{cls(run)}"' if cls(run) else ''
    return '\n'.join([
        f'<div><b{c}>{money(run)}</b><span>Running net after {n} day{"s" if n != 1 else ""}</span></div>',
        f'        <div><b>{sum(d["round_trips"] for d in traded)}</b><span>Round trips so far</span></div>',
        f'        <div><b>{op}</b><span>Work orders open</span></div>',
        f'        <div><b>{cl}</b><span>Work orders closed</span></div>',
    ])


def rows(data):
    out = []
    for p in data.get('pending', []):
        out.append(f'<tr class="pending"><td>{label(p["date"])}</td><td>&mdash;</td><td class="num">&mdash;</td><td class="num">&mdash;</td><td class="num">&mdash;</td><td>{p["note"]}</td><td>&mdash;</td></tr>')
    for d in data['days'][::-1]:
        if d.get('flat'):
            out.append(f'<tr><td>{label(d["date"])}</td><td>{d["clock_in"]}</td><td class="num">$0.00</td><td class="num">0</td><td class="num">&mdash;</td><td>{d["finding"]}</td><td>&mdash;</td></tr>')
            continue
        nc = f' {cls(d["net"])}' if cls(d['net']) else ''
        wo = d['wo']['id']
        out.append(f'<tr><td>{label(d["date"])}</td><td>{d["clock_in"]}</td><td class="num{nc}">{money(d["net"])}</td><td class="num">{d["round_trips"]}</td><td class="num">{winrate(d)}</td><td>{d["finding"]}</td><td><a href="#{wo.lower()}">{wo} &rarr;</a></td></tr>')
    return '\n            '.join(out)


def wos(traded):
    out = []
    for d in traded[::-1]:
        w = d['wo']; dd = d_(d['date'])
        rep = f'Reported {label(d["date"])} {dd.year}' + (' &middot; auto-posted' if d.get('auto') else '')
        sub = f'{d["round_trips"]} round trip{"s" if d["round_trips"] != 1 else ""} &middot; {d["fills"]} fills &middot; {winrate(d).replace("&mdash;", "no")} win rate &middot; ${d["commissions"]:,.2f} commissions'
        f = [f'            <div class="k">Symptom</div>',
             f'            <div class="v"><div class="big {cls(d["net"]) or "pos"}">{money(d["net"])}</div><span class="sub">{sub}</span></div>']
        for k, v in w['fields']:
            f += [f'            <div class="k">{k}</div>', f'            <div class="v">{v}</div>']
        out.append('\n'.join([
            f'<article class="wo" id="{w["id"].lower()}">',
            f'          <div class="wo-head"><span><b>{w["id"]}</b> &middot; Unit: trading account</span><span>{rep}</span><span class="status">{w["status"]}</span></div>',
            '          <div class="wo-fields">', *f, '          </div>', '        </article>']))
    return '\n        '.join(out)


def render(data):
    traded = [d for d in data['days'] if not d.get('flat')]
    return {'tape': tape(traded), 'home': home(traded), 'totals': totals(traded), 'rows': rows(data), 'wos': wos(traded)}


def apply(html, blocks):
    for name, body in blocks.items():
        pat = re.compile(r'(<!--auto:%s-->).*?(<!--/auto:%s-->)' % (name, name), re.S)
        if len(pat.findall(html)) != 1: sys.exit(f'marker auto:{name} must appear exactly once in index.html')
        html = pat.sub(lambda m: m.group(1) + body + m.group(2), html)
    return html


def main():
    data = json.load(open(os.path.join(ROOT, 'data', 'days.json'), encoding='utf-8'))
    p = os.path.join(ROOT, 'index.html'); html = open(p, encoding='utf-8').read()
    new = apply(html, render(data))
    if new != html: open(p, 'w', encoding='utf-8').write(new)
    print('index.html', 'updated' if new != html else 'already up to date')


if __name__ == '__main__':
    main()
