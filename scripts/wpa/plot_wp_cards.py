#!/usr/bin/env python3
"""
ESPN-style win-probability cards (WPA step 11 example charts): one card per bout -- the winner's win probability
through the bout, the winner's side dotted in his team colour above 50, the loser's solid below, the winner's lowest
point ringed; overtime drawn on the same clock (sudden victory 2:00, tiebreaker rides 0:30 each). Regulation uses the
fitted model (wp_model.WPModel); overtime under the current rules (2022+) is the overtime model's chain as stored by
compute_wpa.py (data/wpa/output/events_wpa.parquet -- run that first), later rounds one step at the end; earlier seasons
are flat at the overtime win rate until the winner's last overtime score.

Usage (repo root):
  .venv/bin/python scripts/wpa/plot_wp_cards.py --year 2025                         # that year's 10 finals, 2 columns
  .venv/bin/python scripts/wpa/plot_wp_cards.py --year 2026 --wrestler "Aden Valencia"   # one wrestler's bouts, 1 column
Writes data/wpa/reports/img/finals_{year}_wp.png or {wrestler}_{year}_wp.png.
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg')
plt_dpi = 160
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from scipy.special import expit
import fit_state_model as F, wp_model as W
m = W.WPModel()
ap = argparse.ArgumentParser(); ap.add_argument('--year', type=int, required=True); ap.add_argument('--wrestler')
ARGS = ap.parse_args()
plt.rcParams['font.family'] = ['Helvetica Neue', 'Helvetica', 'Arial']; plt.rcParams['figure.dpi'] = 160
b = pd.read_csv('data/wpa/states/ncaa_bouts.csv'); e = pd.read_csv('data/wpa/states/ncaa_events.csv'); s = pd.read_csv('data/wpa/states/ncaa_samples.csv')
YEAR = ARGS.year
ORDER = ['R32', 'R16', 'QF', 'SF', 'Final']
if ARGS.wrestler:
    V = b[(b.year == YEAR) & (b.w_name == ARGS.wrestler) & b['round'].isin(ORDER)].copy()
    V = V.assign(o=V['round'].map(ORDER.index)).sort_values('o').reset_index(drop=True)
else:
    V = b[(b.year == YEAR) & (b['round'] == 'Final')].sort_values('weight').reset_index(drop=True)
BLACK = '#111111'
TEAM = {'Stanford': ('STAN', '#8C1515'), 'North Dakota State': ('NDSU', '#0A5640'), 'Ohio State': ('OSU', '#BB0000'),
        'Cornell': ('COR', '#B31B1B'), 'Michigan': ('MICH', '#00274C'), 'Penn State': ('PSU', '#041E42'),
        'NC State': ('NCST', '#CC0000'), 'Oklahoma State': ('OKST', '#FF7300'), 'Illinois': ('ILL', '#E84A27'),
        'Iowa': ('IOWA', BLACK), 'Nebraska': ('NEB', '#E41C38'), 'Virginia Tech': ('VT', '#630031'),
        'Purdue': ('PUR', BLACK), 'Missouri': ('MIZZ', BLACK), 'Northern Iowa': ('UNI', '#4B116F'),
        'Minnesota': ('MINN', '#7A0019'), 'Arizona State': ('ASU', '#8C1D40'), 'Virginia': ('UVA', '#232D4B')}
def team(t):
    """(abbreviation, colour); a team missing from TEAM gets its initials in black."""
    return TEAM.get(t) or (''.join(w[0] for w in t.split() if w[0].isupper())[:4] or t[:4].upper(), BLACK)
INK, INK2, GRID, SURF, MID = '#111111', '#6b6b6b', '#c9c9c9', '#ffffff', '#b8b8b8'
TERM = ['fall', 'tech_fall', 'injury', 'dq', 'misconduct', 'regulation_end']

OT_LEN = {1: 120, 2: 30, 3: 30, 4: 60, 5: 30, 6: 30}
OTX = {'SV1': (420, 120), 'TB1': (540, 30), 'TB2': (570, 30)}      # phase -> (x at its start, length)
O = pd.read_parquet('data/wpa/output/events_wpa.parquet',
                    columns=['bout_key', 'kind', 'seq', 'category', 'event_type', 'subtype', 't_after', 'wp_w_before',
                             'wp_w_after'])
O = O[(O.kind == 'ncaa') & (O.category == 'overtime')]


def ot_series(k):
    """(xs, ys) of the overtime model's chain for bout k (current rules), or None."""
    oc = O[O.bout_key == k].sort_values('seq')
    if not len(oc) or not oc.subtype.isin(OTX.keys()).any():
        return None
    xs, ys = [420.0], [100 * oc.wp_w_before.iloc[0]]
    for r in oc.itertuples():
        x0, L = OTX.get(r.subtype, (600, 0))
        x = x0 + L - r.t_after if r.subtype in OTX else max(xs[-1], 600)
        if r.event_type != 'clock':
            xs.append(x); ys.append(ys[-1])          # a score / a choice is a jump
        xs.append(x); ys.append(100 * r.wp_w_after)
    return np.array(xs), np.array(ys)
def wp_series(bb):
    wp_series.ot_end = 420
    k = bb.bout_key
    ev = e[(e.bout_key == k) & (e.section == 'reg') & (e.a_t_rem > 0) & ~e.event.isin(TERM)]
    evs = pd.DataFrame({'t_rem': ev.a_t_rem, 'period': pd.to_numeric(ev.a_period, errors='coerce'), 'margin': ev.a_margin,
                        'pos': ev.a_pos, 'choice': ev.a_choice, 'break_step': ev.a_break_step, 'rt_diff': ev.a_rt_diff,
                        'is_ev': True, 'seq': ev.seq})
    sm = s[(s.bout_key == k) & (s.t_rem > 0)].assign(is_ev=False, seq=-1)
    x = pd.concat([sm, evs], ignore_index=True).dropna(subset=['period'])
    pos = np.where(x.pos == 'w_top', 'A_top', np.where(x.pos == 'l_top', 'A_bottom',
                   np.where(x.pos == 'pending', 'pending_' + x.break_step.astype(str), x.pos)))
    df = pd.DataFrame({'margin': x.margin.astype(int), 't_rem': x.t_rem.astype(int), 'period': x.period.astype(int),
                       'pos': pos, 'choice': x.choice.map({'w': 'A', 'l': 'B'}).fillna('none'),
                       'rt_diff': x.rt_diff.astype(float), 'era_group': 'E3', 'seed_a': bb.w_seed, 'seed_b': bb.l_seed})
    ok = df.pos.isin(F.POS).to_numpy()
    x = x[ok].copy(); x['wp'] = m.wp(df[ok]) * 100; x['el'] = 420 - x.t_rem
    x = x.sort_values(['el', 'seq'], kind='stable')
    xs, ys, prev = [0.0], [x.wp.iloc[0]], x.wp.iloc[0]
    for el, wp, is_ev in zip(x.el, x.wp, x.is_ev):
        if is_ev:
            xs.append(el); ys.append(prev)      # a score is a jump, not a slope
        xs.append(el); ys.append(wp); prev = wp
    xs.append(420); ys.append(prev)
    end = 420
    oxy = ot_series(k) if bb.went_to_ot else None
    if oxy is not None:
        xs += list(oxy[0]); ys += list(oxy[1])
        wp_series.ot_end = max(oxy[0].max(), 540)
        return np.array(xs, float), np.array(ys, float), x
    if bb.went_to_ot:
        ot = e[(e.bout_key == k) & (e.section == 'ot')]
        per = pd.to_numeric(ot.ot_period, errors='coerce').fillna(1).astype(int)
        start = {p_: 420 + sum(OT_LEN[q] for q in range(1, p_)) for p_ in OT_LEN}
        wsc = ot[(ot.points > 0) & (ot.actor == 'w')]
        last = wsc.iloc[-1]; lp = int(pd.to_numeric(last.ot_period, errors='coerce') or 1)
        end = start[lp] + (OT_LEN[lp] - last.ot_clock if pd.notna(last.ot_clock) else OT_LEN[lp])
        rs = m.rank_signal(pd.DataFrame({'seed_a': [bb.w_seed], 'seed_b': [bb.l_seed]}))[0]
        v_ot = 100 * expit(m.prm['b_ot'] * rs)
        xs += [420, end]; ys += [v_ot, v_ot]
        wp_series.ot_end = start[max(per.max(), lp)] + OT_LEN[max(per.max(), lp)]
    xs += [end]; ys += [100.0]
    return np.array(xs, float), np.array(ys, float), x

def split50(xs, ys):
    """insert the exact 50% crossings so each side can be drawn in its own colour"""
    X, Y = [xs[0]], [ys[0]]
    for i in range(1, len(xs)):
        y0, y1 = ys[i - 1], ys[i]
        if (y0 - 50) * (y1 - 50) < 0:
            X.append(xs[i - 1] + (50 - y0) / (y1 - y0) * (xs[i] - xs[i - 1])); Y.append(50.0)
        X.append(xs[i]); Y.append(ys[i])
    return np.array(X), np.array(Y)

def tint(c, a):
    r, g, b_ = to_rgb(c); return (1 - a + a * r, 1 - a + a * g, 1 - a + a * b_)

from PIL import Image
NUM = 'DIN Condensed'
def row(fig, y, label, color, dotted, pct, top):
    t = fig.text(0.045, y, label, fontsize=13, color=INK2, va='center')
    fig.canvas.draw()
    bb_ = t.get_window_extent().transformed(fig.transFigure.inverted())
    x0 = bb_.x1 + 0.018
    fig.add_artist(plt.Line2D([x0, x0 + 0.045], [y, y], transform=fig.transFigure, color=color, lw=2.6,
                              ls=(0, (1.2, 1.2)) if dotted else '-'))
    fig.text(0.955, y, pct, fontsize=30, color=INK, ha='right', va='center', family=NUM)

cards = []
for i, (_, bb) in enumerate(V.iterrows()):
    fig = plt.figure(figsize=(7.2, 5.2), facecolor=SURF)
    ax = fig.add_axes([0.045, 0.20, 0.79, 0.56]); ax.set_facecolor(SURF)
    xs, ys, x = wp_series(bb)
    X, Y = split50(xs, ys)
    ta, ca = team(bb.w_team); tb, cb = team(bb.l_team)
    if np.linalg.norm(np.array(to_rgb(ca)) - np.array(to_rgb(cb))) < 0.4:
        cb = '#8a8a8a' if np.mean(to_rgb(ca)) < 0.35 else '#3a3a3a'   # colours too close: opponent goes gray
    xmax = max(wp_series.ot_end, 420)
    ax.fill_between(X, Y, 50, where=Y >= 50, color=tint(ca, 0.16), lw=0, interpolate=True, zorder=1)
    ax.fill_between(X, Y, 50, where=Y <= 50, color=tint(cb, 0.16), lw=0, interpolate=True, zorder=1)
    up = np.ma.masked_where(Y < 50, Y); dn = np.ma.masked_where(Y > 50, Y)
    ax.plot(X, up, color=ca, lw=2.4, ls=(0, (1.2, 1.2)), zorder=3)
    ax.plot(X, dn, color=cb, lw=2.4, solid_capstyle='round', zorder=3)
    for yv in (0, 25, 75, 100):
        ax.axhline(yv, color=GRID, lw=1.1, ls=(0, (1, 3)), zorder=0)
    ax.axhline(50, color=MID, lw=1.3, zorder=2)
    for t in [180, 300] + [x_ for x_ in (420, 540, 570, 600) if x_ < xmax]:
        ax.axvline(t, color=GRID, lw=1.1, ls=(0, (1, 3)), zorder=0)
    ax.set_xlim(0, xmax); ax.set_ylim(-2, 102)
    ot_t = [(480, 'SV')] + ([(570, 'TB')] if xmax > 540 else [])
    ax.set_xticks([90, 240, 360] + ([t for t, _ in ot_t] if bb.went_to_ot else []))
    ax.set_xticklabels(['1st', '2nd', '3rd'] + ([l for _, l in ot_t] if bb.went_to_ot else []), fontsize=12, color=INK2)
    ax.yaxis.tick_right(); ax.set_yticks([0, 50, 100]); ax.set_yticklabels(['100', '50', '100'], fontsize=12, color=INK2)
    ax.tick_params(length=0, pad=8)
    for sp_ in ax.spines.values(): sp_.set_visible(False)
    i_lo = int(np.argmin(ys))                        # the whole line, overtime included
    lo = pd.Series({'el': xs[i_lo], 'wp': ys[i_lo]})
    ax.scatter(lo.el, lo.wp, s=50, facecolor=SURF, edgecolor=INK, lw=1.4, zorder=5, clip_on=False)
    ax.annotate(f"{lo.wp:.1f}%", (lo.el, lo.wp), xytext=(0, -15 if lo.wp > 14 else 10), textcoords='offset points',
                ha='center', fontsize=10, color=INK, family='Arial', fontweight='bold')
    sd = lambda v: f"#{int(v)} " if pd.notna(v) else ''
    rnd = {'R32': 'ROUND OF 32', 'R16': 'ROUND OF 16', 'QF': 'QUARTERFINAL', 'SF': 'SEMIFINAL', 'Final': 'FINAL'}[bb['round']]
    fig.text(0.045, 0.955, f"{rnd if ARGS.wrestler else str(bb.weight) + ' LBS'}   ·   {bb.result_type} {bb.final_w}-{bb.final_l}   ·   {' '.join(bb.w_name.split()[1:])}'s low point {lo.wp:.1f}%",
             fontsize=10.5, color=INK2, va='center', family='Arial', fontweight='bold')
    row(fig, 0.865, f"{sd(bb.w_seed_raw)}{' '.join(bb.w_name.split()[1:]).upper()}  {ta}", ca, True, '100%', True)
    row(fig, 0.075, f"{sd(bb.l_seed_raw)}{' '.join(bb.l_name.split()[1:]).upper()}  {tb}", cb, False, '0%', False)
    fig.canvas.draw()
    cards.append(Image.frombuffer('RGBA', fig.canvas.get_width_height(), fig.canvas.buffer_rgba()).convert('RGB'))
    plt.close(fig)
W_, H_ = cards[0].size
cols = 1 if ARGS.wrestler else 2
tf = plt.figure(figsize=(7.2 * cols, 0.95), facecolor=SURF)
if ARGS.wrestler:
    w0 = V.iloc[0]
    head = f"{ARGS.wrestler} — {YEAR} NCAA Championships, {w0.weight} lbs"
    sub = f"#{int(w0.w_seed_raw)} seed, {w0.w_team} · win probability through each bout" if pd.notna(w0.w_seed_raw) else f"{w0.w_team} · win probability through each bout"
else:
    head = f"{YEAR} NCAA Championships — the finals"
    sub = "Champion's win probability through each final (champion on top). Ringed: the champion's lowest point."
tf.text(0.045 / cols, 0.66, head, fontsize=16 + cols, color=INK, family='Arial', fontweight='bold', va='center')
tf.text(0.045 / cols, 0.25, sub, fontsize=11, color=INK2, va='center')
tf.canvas.draw(); title = Image.frombuffer('RGBA', tf.canvas.get_width_height(), tf.canvas.buffer_rgba()).convert('RGB')
rows_ = (len(cards) + cols - 1) // cols
out_img = Image.new('RGB', (cols * W_, title.size[1] + rows_ * (H_ + 6)), 'white')
out_img.paste(title, (0, 0))
for i, c in enumerate(cards):
    x0, y0 = (i % cols) * W_, title.size[1] + (i // cols) * (H_ + 6)
    out_img.paste(Image.new('RGB', (W_ - 60, 2), (225, 225, 225)), (x0 + 30, y0 + 2)); out_img.paste(c, (x0, y0 + 6))
name = ARGS.wrestler.lower().replace(' ', '_') if ARGS.wrestler else 'finals'
out = f'data/wpa/reports/img/{name}_{YEAR}_wp.png'
out_img.save(out); print(out, out_img.size)
