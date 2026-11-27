#!/usr/bin/env python3
"""Score one trading day from the broker's fills and add it to the Logbook.

  python3 tools/post_day.py --fills /tmp/fills.json --nav 4564.10 --date 2026-11-27

--fills  JSON from the broker's trades export: {"trades": [...]} (a rolling window is fine)
--nav    account net liquidation value at the end of the day, used only for position size %
--date   the trade date (YYYY-MM-DD). A trade date runs 8 PM ET the evening before to 8 PM ET.

The method is fixed here on purpose so every day is scored the same way:
  net            sum of realized P&L, commissions included
  round trip     one symbol going from flat to flat inside the day's fills
  win            a round trip with realized P&L above zero
  largest size   biggest position notional of the day / end-of-day account value
  stop exit      a round trip whose closing fill was a STOP order
Nothing here is written by hand. The wording comes from templates driven by the numbers.
Prints a JSON summary. Exits 0 on success, 2 when nothing should be posted (market closed).
"""
import argparse, collections, html, json, os, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build

ET = ZoneInfo('America/New_York')
ROOT = build.ROOT
LIMIT_FIX = 'WO-001 stays open. Same fix: written setup card first, 1% risk, 25% max position.'
NA = '<span class="tag late">N/A</span>'   # shown in red wherever JJ did not turn in his part by the nightly post
HOLIDAYS = {  # NYSE full-day closures
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
    '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24',
}


def hour_label(h):
    def ap(x): return f'{(x % 12) or 12} {"AM" if x % 24 < 12 else "PM"}'
    a, b = ap(h), ap(h + 1)
    lab = f'{a.split()[0]}&ndash;{b}' if a.split()[1] == b.split()[1] else f'{a}&ndash;{b}'
    return lab + (' overnight' if (h >= 20 or h < 4) else '')
def clock(dt): return dt.strftime('%I:%M %p').lstrip('0')
def usd(v): return f'${abs(v):,.2f}'
def plural(n, w): return f'{n} {w}{"" if n == 1 else "s"}'


def score(trades, day, nav):
    y, m, d = map(int, day.split('-')); end = datetime(y, m, d, 20, 0, tzinfo=ET); start = end - timedelta(days=1)
    for t in trades: t['dt'] = datetime.fromisoformat(t['trade_time'].replace('Z', '+00:00')).astimezone(ET)
    fills = sorted((t for t in trades if start <= t['dt'] < end), key=lambda t: (t['dt'], str(t['trade_id'])))
    pos = collections.defaultdict(float); avg = {}; cur = {}; cycles = []
    for t in fills:
        s = t['symbol']; q = t['size'] if t['side'] == 'BUY' else -t['size']
        c = cur.setdefault(s, {'sym': s, 'start': t['dt'], 'pnl': 0.0, 'max': 0.0, 'added_to_loser': False})
        before = pos[s]
        if before != 0 and (before > 0) == (q > 0):            # adding to an existing position
            if (before > 0 and t['price'] < avg[s]) or (before < 0 and t['price'] > avg[s]): c['added_to_loser'] = True
            avg[s] = (avg[s] * abs(before) + t['price'] * abs(q)) / (abs(before) + abs(q))
        elif before == 0 or abs(q) > abs(before): avg[s] = t['price']
        pos[s] += q; c['pnl'] += t['realized_pnl']; c['max'] = max(c['max'], abs(pos[s]) * t['price'])
        if abs(pos[s]) < 1e-6:
            c['end'] = t['dt']; c['stop_exit'] = (t.get('order_type') == 'STOP'); cycles.append(c); del cur[s]; pos[s] = 0.0
    carried = [c for c in cur.values()]                          # positions not flat-to-flat today (swings, or opened and held)
    net = sum(t['realized_pnl'] for t in fills); com = sum(t['commission'] for t in fills)
    hours = collections.defaultdict(float)
    for t in fills: hours[t['dt'].hour] += t['realized_pnl']
    worst = min(hours.items(), key=lambda kv: kv[1]) if hours else None
    biggest = max(cycles + carried, key=lambda c: c['max']) if (cycles or carried) else None
    reentries = 0
    for a in cycles:
        if a['pnl'] < 0: reentries += sum(1 for b in cycles if b is not a and b['sym'] == a['sym'] and timedelta(0) <= b['start'] - a['end'] <= timedelta(seconds=120))
    night = [c for c in cycles if c['start'].hour >= 20 or c['start'].hour < 4]
    return {
        'fills': len(fills), 'net': round(net, 4), 'commissions': round(com, 4), 'cycles': cycles, 'carried': carried,
        'round_trips': len(cycles), 'wins': sum(1 for c in cycles if c['pnl'] > 0),
        'largest_pct': round(100 * biggest['max'] / nav) if biggest else 0, 'largest_sym': biggest['sym'] if biggest else None,
        'over_limit': sum(1 for c in cycles if 100 * c['max'] / nav > 25), 'stop_exits': sum(1 for c in cycles if c['stop_exit']),
        'reentries': reentries, 'adds': sum(1 for c in cycles if c['added_to_loser']), 'worst_hour': worst,
        'night': night, 'night_net': sum(c['pnl'] for c in night),
        'swing_exits': [c for c in carried if abs(c['pnl']) >= 0.005],
    }


def record(s, day, n, inbox, due='8:00 AM'):
    N, W = s['round_trips'], s['wins']; net = s['net']; big = s['largest_pct']; over = big > 25
    faults = over or (N > 0 and s['stop_exits'] == 0) or s['reentries'] > 0 or s['adds'] > 0 or round(net, 2) < 0
    # --- Logbook "Finding" cell and the homepage sentence
    bits = []
    if over: bits.append(f'oversized at {big}%')
    if N: bits.append(f'{W} for {N}')
    if N and s['stop_exits'] == 0: bits.append('no stop exits')
    if s['reentries']: bits.append('re-entry after a loss')
    if s['adds']: bits.append('added to a loser')
    if not bits: bits.append(f'{plural(len(s["swing_exits"]), "carried position")} closed or trimmed' if s['swing_exits'] else 'no completed round trips')
    finding = ', '.join(bits); finding = finding[0].upper() + finding[1:]
    wh = s['worst_hour']
    home = f'{plural(N, "round trip")}, {plural(W, "winner")}' + (f'. Worst hour was {hour_label(wh[0])}' if wh and wh[1] <= -1 else '')
    # --- tape
    tape = [['ROUND TRIPS', str(N)], ['WIN RATE', f'{round(100 * W / N)}%' if N else '&mdash;'], ['LARGEST SIZE', f'{big}% of acct'], ['COMMISSIONS', usd(s['commissions'])],
            ['WORST HOURS', f'{hour_label(wh[0])} {build.money(wh[1], 0)}' if wh and wh[1] <= -1 else 'none in the red'], ['EXITS BY STOP ORDER', f'{s["stop_exits"]} of {N}']]
    if s['swing_exits']:
        tot = sum(c['pnl'] for c in s['swing_exits']); g = sum(1 for c in s['swing_exits'] if c['pnl'] > 0)
        tape.insert(0, ['CARRIED POSITIONS', f'{len(s["swing_exits"])} closed or trimmed, {g} green <span class="{build.cls(tot)}">{build.money(tot)}</span>'])
    # --- work order bullets, straight from the numbers
    li = []
    if N:
        worst = min(s['cycles'], key=lambda c: c['pnl'])
        line = f'{W} of {plural(N, "round trip")} made money'
        if worst['pnl'] < 0: line += f'. Worst one: {worst["sym"]}, {build.money(worst["pnl"])}, {clock(worst["start"])} to {clock(worst["end"])}'
        li.append(line)
    if over: li.append(f'Oversized: {s["largest_sym"]} hit {big}% of the account' + (f', and {s["over_limit"]} of {plural(N, "round trip")} went over the 25% limit' if N else '') )
    elif s['largest_sym']: li.append(f'Size stayed inside the 25% limit. Largest position was {s["largest_sym"]} at {big}% of the account')
    if N: li.append('No round trip was closed by a stop order' if s['stop_exits'] == 0 else f'{s["stop_exits"]} of {plural(N, "round trip")} closed by a stop order')
    if s['reentries']: li.append(f'Re-entry: back in the same symbol within two minutes of taking a loss, {plural(s["reentries"], "time")}')
    if s['adds']: li.append(f'Added to a losing position on {plural(s["adds"], "round trip")}')
    if s['night']: li.append(f'{plural(len(s["night"]), "round trip")} opened overnight, between 8 PM and 4 AM: {build.money(s["night_net"])}')
    if wh and wh[1] <= -1 and N > 1: li.append(f'Worst hour: {hour_label(wh[0])}, {build.money(wh[1])}')
    if round(net, 2) < 0 and s['commissions'] >= 0.10 * abs(net): li.append(f'Commissions were {usd(s["commissions"])}, {round(100 * s["commissions"] / abs(net))}% of the day\'s loss')
    if s['swing_exits']:
        tot = sum(c['pnl'] for c in s['swing_exits'])
        li.append(f'{plural(len(s["swing_exits"]), "carried position")} closed or trimmed: {build.money(tot)}')
    fields = [['Root cause (def night shift)' if faults else 'Findings', '<ul>' + ''.join(f'<li>{x}</li>' for x in li) + '</ul>'],
              ['Corrective action', LIMIT_FIX if faults else 'None needed. Same rules tomorrow.']]
    j = (inbox or {}).get('journal')
    fields.append(['Journal', f'&ldquo;{html.escape(j, quote=False)}&rdquo;' if j else NA])
    return {'date': day, 'n': n, 'net': s['net'], 'round_trips': N, 'wins': W, 'fills': s['fills'], 'commissions': round(s['commissions'], 2), 'largest_pct': big,
            'clock_in': punch(inbox, due), 'finding': finding, 'home_note': home, 'tape': tape,
            'wo': {'id': f'WO-{n:03d}', 'status': 'Open' if faults else 'No fault found', 'fields': fields}, 'auto': True}


def punch(inbox, due='8:00 AM'):
    t = (inbox or {}).get('clock_in')
    return build.clock_cell(t, due) if t else NA


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--fills', required=True); ap.add_argument('--nav', type=float, required=True); ap.add_argument('--date', required=True)
    ap.add_argument('--force', action='store_true', help='replace a day that was posted by hand'); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    d = date.fromisoformat(a.date)
    if d.weekday() >= 5 or a.date in HOLIDAYS:
        print(json.dumps({'posted': False, 'reason': 'market closed on ' + a.date})); sys.exit(2)
    if a.nav <= 0: sys.exit('nav must be the account net liquidation value, above zero')
    raw = json.load(open(a.fills, encoding='utf-8')); trades = raw['trades'] if isinstance(raw, dict) else raw
    p = os.path.join(ROOT, 'data', 'days.json'); data = json.load(open(p, encoding='utf-8'))
    old = next((x for x in data['days'] if x['date'] == a.date), None)
    if old and not old.get('auto') and not a.force: sys.exit(f'{a.date} was posted by hand. Use --force to replace it.')
    data['days'] = [x for x in data['days'] if x['date'] != a.date]
    if any(x['date'] > a.date for x in data['days']): sys.exit('a later day is already posted; refusing to insert out of order')
    inbox = data.get('inbox', {}).get(a.date)
    s = score(trades, a.date, a.nav)
    if s['fills'] == 0:
        rec = {'date': a.date, 'flat': True, 'clock_in': punch(inbox, data.get('clock_due', '8:00 AM')), 'finding': 'No trades. Stayed flat', 'auto': True}
    else:
        n = sum(1 for x in data['days'] if not x.get('flat')) + 1
        rec = record(s, a.date, n, inbox, data.get('clock_due', '8:00 AM'))
    data['days'].append(rec); data['pending'] = [x for x in data.get('pending', []) if x['date'] != a.date]
    out = {'posted': not a.dry_run, 'date': a.date, 'flat': bool(rec.get('flat')), 'fills': s['fills'], 'net': round(s['net'], 2), 'round_trips': s['round_trips'], 'wins': s['wins'],
           'largest_pct': s['largest_pct'], 'finding': rec['finding'], 'work_order': rec.get('wo', {}).get('id')}
    if a.dry_run: print(json.dumps(out)); print(json.dumps(rec, indent=1, ensure_ascii=False)); return
    json.dump(data, open(p, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    build.main(); print(json.dumps(out))


if __name__ == '__main__':
    main()
