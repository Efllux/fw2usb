#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Bilingual-port front-end study. Python stdlib + ngspice; plots optional.

Generates every deck into build/, runs ngspice, checks each result against the
limit named beside it and writes results.json. Exits nonzero if a check that
the design is supposed to pass fails, or if a negative control passes.

Nothing here is a vendor model: transistor cards come from datasheet headline
numbers, pads/comparators/SerDes are behavioural. See ../README.md.
"""
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / 'build'
RESULTS = ROOT / 'results.json'

# Datasheet-derived Gummel-Poon cards [verify]. rf: MMBTH10 / MMBTH81 class
# (fT about 650 / 600 MHz, Ccb under 1 pF). gp: MMBT3904 / MMBT3906 class.
MODELS = {
    'rf': ('.model QN NPN (IS=1e-15 BF=100 VAF=50 BR=3 TF=245p TR=5n CJC=0.9p CJE=1.2p RB=20 RE=0.5 RC=2 XTB=1.5)\n'
           '.model QP PNP (IS=1e-15 BF=80 VAF=30 BR=3 TF=265p TR=5n CJC=1.1p CJE=1.5p RB=20 RE=0.5 RC=2 XTB=1.5)\n'),
    'gp': ('.model QN NPN (IS=6.7e-15 BF=300 VAF=74 BR=1 TF=300p TR=240n CJC=3.6p CJE=4.5p RB=10 RC=1 XTB=1.5)\n'
           '.model QP PNP (IS=1.4e-15 BF=180 VAF=19 BR=4 TF=410p TR=33n CJC=9.7p CJE=8p RB=10 RC=2.5 XTB=1.5)\n'),
}
PAD_NODES = ['dbsp', 'dbsn', 'dbkp', 'dbkn', 'dasp', 'dasn', 'dakp', 'dakn',
             'bd2p', 'bd2n', 'bd4p', 'bd4n']
SINK_PADS = {'dbkp', 'dbkn', 'dakp', 'dakn', 'bd2p', 'bd2n', 'bd4p', 'bd4n'}
CABLE_NS = 22.725
FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)
    return bool(ok)


def simulate(name, body, vectors, analysis, tstep=None):
    deck, data = BUILD / (name + '.cir'), BUILD / (name + '.txt')
    lin = ('\nlinearize ' + ' '.join(vectors)) if tstep else ''
    deck.write_text('* SPDX-License-Identifier: CERN-OHL-S-2.0\n* Generated; see run.py.\n'
                    '.options method=gear reltol=1e-3\n' + body + '\n.save ' + ' '.join(vectors) +
                    '\n.control\nset wr_singlescale\n' + analysis + lin +
                    '\nwrdata ' + str(data) + ' ' + ' '.join(vectors) + '\nquit\n.endc\n.end\n')
    if data.exists():
        data.unlink()
    done = subprocess.run(['ngspice', '-b', str(deck)], cwd=ROOT, capture_output=True, text=True, check=False)
    (BUILD / (name + '.log')).write_text(done.stdout + done.stderr)
    if done.returncode or not data.exists():
        raise RuntimeError(f'{name}: ngspice failed; inspect build/{name}.log')
    return [[float(x) for x in line.split()] for line in data.read_text().splitlines() if line.strip()]


def pwl(node, values, start, bit_ns, edge_ns, scale=1.0, shift=0.0):
    """Piecewise-linear source: values[i] held for bit i, starting at start ns."""
    points, old = [(0.0, values[0] * scale)], values[0] * scale
    for i, value in enumerate(values):
        value *= scale
        t = start + i * bit_ns + shift
        if value != old:
            points.extend([(t, old), (t + edge_ns, value)])
            old = value
    points.append((start + len(values) * bit_ns + 1000, old))
    return f'V{node} {node} 0 PWL(' + ' '.join(f'{t:.6f}n {v:.6g}' for t, v in points) + ')\n'


def our_pads(pair, cmds, start, bit_ns, vdd=3.3, edge_ns=0.4, sink_skew=0.0):
    """Pad waveforms for one pair ('a' or 'b') from a -1/0/1 command list.
    Source pads are high when on; sink pads are low when on."""
    d = 'd' + pair
    return (pwl(d + 'sp', [1 if c > 0 else 0 for c in cmds], start, bit_ns, edge_ns, vdd)
            + pwl(d + 'sn', [1 if c < 0 else 0 for c in cmds], start, bit_ns, edge_ns, vdd)
            + pwl(d + 'kp', [0 if c < 0 else 1 for c in cmds], start, bit_ns, edge_ns, vdd, sink_skew)
            + pwl(d + 'kn', [0 if c > 0 else 1 for c in cmds], start, bit_ns, edge_ns, vdd, sink_skew))


def idle_pads(skip=(), vdd=3.3, beta=False, dead=False):
    """Constant pads. Legacy idle: sources low, sinks high. Beta parking:
    sources high, sinks low (VBP = VDD, VBN = 0, so no junction is stressed).
    Dead: everything at 0 V."""
    out = ''
    for node in PAD_NODES:
        if node in skip or any(node.startswith(s) for s in skip):
            continue
        high = (node in SINK_PADS) != beta
        out += f'V{node} {node} 0 {0 if dead else (vdd if high else 0)}\n'
    return out


def board(q='rf', vdd=3.3, temp=27, refs='on', pads='on', tpbias=1.8, pbias=1.86,
          amp_peer=4e-3, legacy=True, serdes=True, cpar='7p', ce='4.7p'):
    """Our port (both pairs), 4.5 m cable and the peer's terminations/drivers.
    Pair b: our TPB <-> peer TPA.  Pair a: our TPA <-> peer TPB."""
    ron = {'on': '22', 'off': '1g', 'dead': '3.3k'}
    s = MODELS[q] + f'.include bilingual.lib\n.options temp={temp}\nVdd vdd 0 {vdd}\n'
    if legacy:
        s += f'Xref vdd vbp vbn refs ron={ron[refs]}\n'
        s += f'Xlb bp bn vbp vbn dbsp dbsn dbkp dbkn legs ron={ron[pads]} ce={ce}\n'
        s += f'Xla ap an vbp vbn dasp dasn dakp dakn legs ron={ron[pads]} ce={ce}\n'
        s += f'Xsb bp bn vbn bd2p bd2n bd4p bd4n speed ron={ron[pads]}\n'
        s += f'Xob bp bn vdd bapp bapn banp bann loads cpar={cpar}\n'
        s += f'Xoa ap an vdd aapp aapn aanp aann loads cpar={cpar}\n'
    else:
        s += 'Cbp bp 0 1p\nCbn bn 0 1p\nCap ap 0 1p\nCan an 0 1p\n'
    s += 'Xtb bp bn bct bcm term_b\nXta ap an tpbias acm term_a\n'
    if serdes:
        s += 'Xsdb bp bn stxp stxn sd_tx\nXsda ap an srxp srxn sd_rx\n'
    if tpbias is not None:      # LDO on: 1 ohm output impedance is an assumption
        s += f'Vtb tbs 0 {tpbias}\nRtb tbs tpbias 1\n'
    # speed-detect thresholds are a divider from TPBIAS
    s += 'Rd1 tpbias th200 4.87k\nRd2 th200 th400 14.3k\nRd3 th400 0 80.6k\n'
    s += 'Xcb bp bn bq br cable\nXca ap an aq ar cable\n'
    s += 'Xpb bq br pbias peer_tpa\nXpa aq ar peer_tpb\n'
    s += f'Vpb pbias 0 {pbias}\n'
    s += f'Xdx bq br pcx psx idrv amp={amp_peer}\nXdy aq ar pcy psy idrv amp={amp_peer}\n'
    return s


def col(rows, i):
    return [r[i] for r in rows]


def interp(rows, t, c):
    dt = rows[1][0] - rows[0][0]
    k = (t - rows[0][0]) / dt
    i = max(0, min(len(rows) - 2, int(k)))
    f = k - i
    return rows[i][c] * (1 - f) + rows[i + 1][c] * f


def eye(rows, cp, cn, bits, start_ns, ui_ns, delay_ns, need_mv, skip=12):
    """Scan the sampling instant over three unit intervals around the expected
    delay. Returns inner eye height (2 x worst sample at the best instant) and
    the width of the contiguous window in which every bit clears need_mv."""
    steps, best, margins = 50, None, []
    for k in range(-steps, 2 * steps):
        tau = delay_ns + k * ui_ns / steps
        m = min(b * (interp(rows, (start_ns + (i + 0.5) * ui_ns + tau) * 1e-9, cp)
                     - interp(rows, (start_ns + (i + 0.5) * ui_ns + tau) * 1e-9, cn))
                for i, b in enumerate(bits) if skip <= i < len(bits) - 2)
        margins.append(m)
        if best is None or m > margins[best]:
            best = len(margins) - 1
    lo = hi = best
    while lo > 0 and margins[lo - 1] * 1000 > need_mv:
        lo -= 1
    while hi < len(margins) - 1 and margins[hi + 1] * 1000 > need_mv:
        hi += 1
    width = (hi - lo + 1) / steps if margins[best] * 1000 > need_mv else 0.0
    return {'inner_eye_mV': round(2 * margins[best] * 1000, 1),
            'worst_sample_mV': round(margins[best] * 1000, 1),
            'width_UI': round(min(width, 1.0), 2), 'width_measured_above_mV': need_mv}


def prbs7(n, seed=0x5a):
    out, s = [], seed & 0x7f
    for _ in range(n):
        bit = ((s >> 6) ^ (s >> 5)) & 1
        s = ((s << 1) | bit) & 0x7f
        out.append(1 if bit else -1)
    return out


def ds_encode(bits):
    prev, strobe, d, s = -1, -1, [], []
    for b in bits:
        if b == prev:
            strobe = -strobe
        d.append(b)
        s.append(strobe)
        prev = b
    return d, s


# ------------------------------------------------------------------ tests ---
def driver_dc():
    """Our transistor driver, DC, over supply/temperature/peer-bias corners.
    Limits: VOD 172..265 mV into the doubly terminated pair, algebraic sum of
    the two conductor currents within +/-1.05 mA (TSB81BA3E section 6.4)."""
    rows_out, worst = [], {'vod_min': 1e9, 'vod_max': 0, 'sum_max_mA': 0, 'voff_max_mV': 0}
    for q in ('rf', 'gp'):
        for vdd, temp, pbias in itertools.product((3.135, 3.3, 3.465), (0, 27, 70), (1.665, 1.86, 2.015)):
            for cmd in (1, -1, 0):
                body = board(q=q, vdd=vdd, temp=temp, pbias=pbias)
                body += idle_pads(skip=('dbs', 'dbk', 'das', 'dak'), vdd=vdd)
                for pair in 'ab':
                    body += our_pads(pair, [cmd], 0, 1, vdd)
                body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
                r = simulate('drvdc', body, ['v(bp)', 'v(bn)', 'v(bq)', 'v(br)', 'v(xpb.ct)', 'v(bct)',
                                             'v(ap)', 'v(an)', 'v(aq)', 'v(ar)', 'v(tpbias)', 'v(xpa.ct)'], 'op')[0][1:]
                # pair b (our TPB): net current leaves through the peer's bias and our 5k
                vod_b = r[0] - r[1]
                sum_b = ((r[2] + r[3] - 2 * r[4]) / 55 + (r[0] + r[1] - 2 * r[5]) / 54.9) * 1000
                vod_a = r[6] - r[7]
                sum_a = ((r[6] + r[7] - 2 * r[10]) / 54.9 + (r[8] + r[9] - 2 * r[11]) / 55) * 1000
                for vod, isum in ((vod_b, sum_b), (vod_a, sum_a)):
                    if cmd:
                        if q == 'rf':
                            worst['vod_min'] = min(worst['vod_min'], abs(vod) * 1000)
                            worst['vod_max'] = max(worst['vod_max'], abs(vod) * 1000)
                            worst['sum_max_mA'] = max(worst['sum_max_mA'], abs(isum))
                    elif q == 'rf':
                        worst['voff_max_mV'] = max(worst['voff_max_mV'], abs(vod) * 1000)
                if (vdd, temp, pbias) == (3.3, 27, 1.86) and cmd == 1:
                    rows_out.append({'transistors': q, 'TPB_VOD_mV': round(vod_b * 1000, 1), 'TPA_VOD_mV': round(vod_a * 1000, 1),
                                     'TPB_sum_mA': round(sum_b, 3), 'TPA_sum_mA': round(sum_a, 3)})
    res = {'corners': '3 supplies x 3 temperatures x 3 peer TPBIAS x 3 states, both pairs',
           'nominal': rows_out, 'rf_worst': {k: round(v, 2) for k, v in worst.items()}}
    res['pass_VOD_172_265mV'] = check(172 <= worst['vod_min'] and worst['vod_max'] <= 265, 'driver VOD window')
    res['pass_sum_within_1.05mA'] = check(worst['sum_max_mA'] <= 1.05, 'driver common-mode sum')
    res['pass_VOFF_20mV'] = check(worst['voff_max_mV'] <= 20, 'driver off-state voltage')
    return res


SPEEDS = {'S100': (1e3 / 98.304, 0.1, 64, 1.08 + 0.8), 'S400': (1e3 / 393.216, 0.05, 256, 0.315 + 0.5)}


def legacy_tx():
    """We transmit DS: data on our TPB, strobe on our TPA, through 4.5 m.
    Eye at the peer against its +/-30 mV receiver threshold and the 118 mV
    recommended minimum; rise time at our connector; common-mode disturbance at
    the peer's TPA against the 49 mV minimum S200 threshold."""
    out = []
    for speed, q, skew, ce in [('S100', 'rf', 0, '4.7p'), ('S100', 'gp', 0, '4.7p'), ('S400', 'rf', 0, '4.7p'),
                               ('S400', 'rf', 0, '0'), ('S400', 'gp', 0, '4.7p'),
                               ('S400', 'rf', 0.3, '4.7p'), ('S400', 'rf', -0.3, '4.7p')]:
        bit, tstep, n, win = SPEEDS[speed]
        d, s = ds_encode(prbs7(n))
        start = 60.0
        body = board(q=q, ce=ce) + idle_pads(skip=('dbs', 'dbk', 'das', 'dak'))
        body += our_pads('b', [0] + d, start - bit, bit, sink_skew=skew)
        body += our_pads('a', [0] + s, start - bit, bit, sink_skew=skew)
        body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
        rows = simulate(f'ltx_{speed}_{q}_{skew}_{ce}', body,
                        ['v(bq)', 'v(br)', 'v(aq)', 'v(ar)', 'v(bp)', 'v(bn)', 'v(xpb.ct)'],
                        f'tran {tstep}n {start + n * bit + 60}n', tstep)
        e_d = eye(rows, 1, 2, d, start, bit, CABLE_NS, 30)
        e_s = eye(rows, 3, 4, s, start, bit, CABLE_NS, 30)
        # 10..90 % rise of the first data edge at our connector
        t10 = t90 = None
        v0 = rows[int((start - 2) / tstep)][5] - rows[int((start - 2) / tstep)][6]
        first = d[0]
        for r in rows:
            v = (r[5] - r[6]) * first
            if r[0] * 1e9 > start - 1 and t10 is None and v > 0.022:
                t10 = r[0] * 1e9
            if t10 is not None and v > 0.19:
                t90 = r[0] * 1e9
                break
        droop = max(abs(r[7] - (r[1] + r[2]) / 2) for r in rows if r[0] * 1e9 > start + 40)
        item = {'speed': speed, 'transistors': q, 'sink_pad_skew_ns': skew, 'emitter_speedup_cap': ce, 'data_eye_at_peer': e_d,
                'strobe_eye_at_peer': e_s, 'approx_rise_ns_at_connector': round((t90 or 0) - (t10 or 0), 2),
                'peak_CM_disturbance_at_peer_TPA_mV': round(droop * 1000, 1), 'idle_diff_before_start_mV': round(v0 * 1000, 2)}
        rise_limit = 1.2 if speed == 'S400' else 3.2
        ok = (min(e_d['worst_sample_mV'], e_s['worst_sample_mV']) >= 118 and droop < 0.049
              and min(e_d['width_UI'], e_s['width_UI']) * bit > win and item['approx_rise_ns_at_connector'] <= rise_limit)
        item['window_needed_ns'] = round(win, 2)
        item['rise_limit_ns'] = rise_limit
        item['pass'] = bool(ok)
        if q == 'rf' and ce != '0':
            check(ok, f'legacy TX {speed} skew {skew}')
        out.append(item)
    return out


def legacy_rx():
    """The peer transmits at its minimum amplitude (172 mV at its connector);
    eye at our SN65LVDS34 inputs against its +/-50 mV threshold, with every
    legacy load and the idle SerDes branches attached."""
    out = []
    for speed, edge in (('S100', 1.2), ('S400', 1.2), ('S400', 0.5)):
        bit, tstep, n, win = SPEEDS[speed]
        d, s = ds_encode(prbs7(n))
        start = 60.0
        body = board(amp_peer=3.13e-3) + idle_pads()
        body += pwl('pcy', [0] + d, start - bit, bit, edge) + pwl('pcx', [0] + s, start - bit, bit, edge)
        body += 'Vpsx psx 0 0\nVpsy psy 0 0\n'
        rows = simulate(f'lrx_{speed}_{edge}', body, ['v(ap)', 'v(an)', 'v(bp)', 'v(bn)'],
                        f'tran {tstep}n {start + n * bit + 60}n', tstep)
        e_d = eye(rows, 1, 2, d, start, bit, CABLE_NS, 50)
        e_s = eye(rows, 3, 4, s, start, bit, CABLE_NS, 50)
        ok = min(e_d['width_UI'], e_s['width_UI']) * bit > win + 0.2
        out.append({'speed': speed, 'peer_edge_ns': edge, 'data_eye_at_our_TPA': e_d, 'strobe_eye_at_our_TPB': e_s,
                    'window_needed_ns_incl_0.2_receiver_pulse_skew': round(win + 0.2, 2),
                    'pass': check(ok, f'legacy RX {speed}')})
    return out


def arbitration():
    """All nine (our drive, peer drive) states on both pairs through the real
    driver and the resistive-offset comparator networks. A comparator is read
    150 ns after the change and must clear +/-8 mV (offset plus hysteresis)."""
    combos = list(itertools.product([-1, 0, 1], repeat=2))
    step, start, worst, errors, n = 400.0, 100.0, 1e9, 0, 0
    for vdd, temp, amp, pbias in [(3.3, 27, 4e-3, 1.86), (3.135, 70, 4.73e-3, 2.015), (3.465, 0, 3.13e-3, 1.665),
                                  (3.135, 0, 3.13e-3, 2.015), (3.465, 70, 4.73e-3, 1.665)]:
        body = board(vdd=vdd, temp=temp, amp_peer=amp, pbias=pbias) + idle_pads(skip=('dbs', 'dbk', 'das', 'dak'), vdd=vdd)
        ours, peer = [0] + [a for a, b in combos], [0] + [b for a, b in combos]
        for pair in 'ab':
            body += our_pads(pair, ours, start - step, step, vdd)
        body += pwl('pcx', peer, start - step, step, 1.0) + pwl('pcy', peer, start - step, step, 1.0)
        body += 'Vpsx psx 0 0\nVpsy psy 0 0\n'
        vec = ['v(bapp)', 'v(bapn)', 'v(banp)', 'v(bann)', 'v(aapp)', 'v(aapn)', 'v(aanp)', 'v(aann)']
        rows = simulate('arb', body, vec, f'tran 0.5n {start + 9 * step}n', 0.5)
        for i, (a, b) in enumerate(combos):
            expected = (a + b > 0) - (a + b < 0)
            t = (start + i * step + 150) * 1e-9
            for base in (1, 5):
                pos = interp(rows, t, base) - interp(rows, t, base + 1)
                neg = interp(rows, t, base + 2) - interp(rows, t, base + 3)
                got = (1 if pos > 0 else 0) - (1 if neg > 0 else 0)
                margin = min(abs(pos), abs(neg))
                worst = min(worst, margin)
                errors += int(got != expected or margin < 0.008)
                n += 1
    return {'classifications': n, 'errors': errors, 'smallest_overdrive_at_comparator_mV': round(worst * 1000, 1),
            'pass': check(errors == 0, 'arbitration classification')}


def speed_signalling():
    """Transmit: our S200/S400 sinks while TPB drives 1. Per-conductor current
    must be 2.53..4.84 / 8.1..12.4 mA. Receive: the peer sinks its limit
    currents; our TPA common mode against thresholds divided from TPBIAS, with
    +/-8 mV comparator uncertainty. S100 imbalance must not be detected."""
    tx, worst = [], {}
    for vdd, temp, pbias in itertools.product((3.135, 3.3, 3.465), (0, 27, 70), (1.665, 2.015)):
        for level in ('S200', 'S400'):
            body = board(vdd=vdd, temp=temp, pbias=pbias) + idle_pads(skip=('dbs', 'dbk', 'bd'), vdd=vdd)
            body += our_pads('b', [1], 0, 1, vdd)
            body += f'Vbd2p bd2p 0 0\nVbd2n bd2n 0 0\nVbd4p bd4p 0 {0 if level == "S400" else vdd}\n'
            body += f'Vbd4n bd4n 0 {0 if level == "S400" else vdd}\n'
            body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
            r = simulate('spdtx', body, ['v(bq)', 'v(br)', 'v(xpb.ct)', 'v(pbias)', 'v(bp)', 'v(bn)'], 'op')[0][1:]
            per_cond = (2 * r[2] - r[0] - r[1]) / 55 / 2 * 1000
            droop = (r[3] - (r[0] + r[1]) / 2) * 1000
            w = worst.setdefault(level, {'I_min': 1e9, 'I_max': 0, 'droop_min': 1e9, 'droop_max': 0, 'vod_min': 1e9})
            w['I_min'], w['I_max'] = min(w['I_min'], per_cond), max(w['I_max'], per_cond)
            w['droop_min'], w['droop_max'] = min(w['droop_min'], droop), max(w['droop_max'], droop)
            w['vod_min'] = min(w['vod_min'], (r[4] - r[5]) * 1000)
    lim = {'S200': (2.53, 4.84, 131, 314), 'S400': (8.1, 12.4, 396, 1e9)}
    for level, w in worst.items():
        lo, hi, dlo, dhi = lim[level]
        ok = lo <= w['I_min'] and w['I_max'] <= hi and w['droop_min'] > dlo and w['droop_max'] < dhi and w['vod_min'] > 172
        tx.append({'level': level, 'per_conductor_mA': [round(w['I_min'], 2), round(w['I_max'], 2)],
                   'droop_at_peer_TPA_mV': [round(w['droop_min'], 1), round(w['droop_max'], 1)],
                   'data_VOD_during_signal_min_mV': round(w['vod_min'], 1),
                   'pass': check(ok, f'speed signal TX {level}')})
    rx = []
    for label, sink, want in [('S100 with 0.81 mA/conductor imbalance', 0.81e-3, 0), ('S200 min', 2.53e-3, 1),
                              ('S200 max', 4.84e-3, 1), ('S400 min', 8.1e-3, 2), ('S400 max', 12.4e-3, 2)]:
        body = board() + idle_pads()
        body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 PWL(0 0 99n 0 100n 1)\n'
        body += f'Vpsy psy 0 PWL(0 0 100n 0 102n {sink} 210n {sink} 212n 0)\n'
        rows = simulate('spdrx', body, ['v(acm)', 'v(th200)', 'v(th400)', 'v(tpbias)'], 'tran 0.5n 400n', 0.5)
        t = (100 + CABLE_NS + 60) * 1e-9
        cm, t2, t4, tb = (interp(rows, t, c) for c in (1, 2, 3, 4))
        got = int(cm < t2 - 0.008) + int(cm < t4 - 0.008)
        ambiguous = any(abs(cm - th) < 0.008 for th in (t2, t4))
        rx.append({'case': label, 'TPA_CM_droop_mV': round((tb - cm) * 1000, 1), 'threshold_mV': [round((tb - t2) * 1000, 1), round((tb - t4) * 1000, 1)],
                   'TPBIAS_sag_mV': round((1.8 - min(col(rows, 4))) * 1000, 1), 'classified': ['S100', 'S200', 'S400'][got],
                   'pass': check(got == want and not ambiguous, f'speed detect {label}')})
    return {'transmit': tx, 'receive': rx}


def false_speed():
    """Negative control: one sink leg of our TPB driver missing for a whole
    data state must show up as a false S200 indication at the peer."""
    body = board() + idle_pads(skip=('dbs', 'dbk'))
    body += pwl('dbsp', [0, 1], 80, 100, 0.4, 3.3) + 'Vdbsn dbsn 0 0\nVdbkp dbkp 0 3.3\nVdbkn dbkn 0 3.3\n'
    body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
    rows = simulate('falsespeed', body, ['v(bq)', 'v(br)', 'v(xpb.ct)'], 'tran 0.5n 400n', 0.5)
    rise = max((r[1] + r[2]) / 2 - r[3] for r in rows)
    body = board() + idle_pads(skip=('dbs', 'dbk'))
    body += 'Vdbsp dbsp 0 0\nVdbsn dbsn 0 0\nVdbkp dbkp 0 3.3\n' + pwl('dbkn', [1, 0], 80, 100, 0.4, 3.3)
    body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
    rows = simulate('falsespeed2', body, ['v(bq)', 'v(br)', 'v(xpb.ct)'], 'tran 0.5n 400n', 0.5)
    droop = max(r[3] - (r[1] + r[2]) / 2 for r in rows)
    detected = droop > 0.049
    check(detected, 'negative control: missing source leg must look like S200')
    return {'source_only_CM_rise_mV': round(rise * 1000, 1), 'sink_only_CM_droop_mV': round(droop * 1000, 1),
            'sink_only_crosses_49mV': detected,
            'note': 'negative control; a stuck or missing source pad is indistinguishable from speed signalling'}


def unpowered():
    """Board unpowered (VDD = 0), peer biased at 2.015 V. Current taken from
    the peer's TPBIAS, compared with the 5k termination the standard already
    puts there. Negative control: FPGA differential inputs wired straight to
    TPB on a bank that clamps to VCCIO."""
    out = {}
    for label, refs, extra in [('typical_pins_open', 'off', ''), ('worst_case_1mA_pin_leakage', 'dead', ''),
                               ('negative_control_fpga_inputs_on_clamping_bank', 'dead',
                                'Dfp bp vdd DCLAMP\nDfn bn vdd DCLAMP\n')]:
        body = board(vdd=0, refs=refs, pads='off' if refs == 'off' else 'dead', tpbias=None, pbias=2.015)
        body += idle_pads(dead=True) + extra
        body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
        r = simulate('unpowered_' + label, body, ['i(vpb)', 'v(bq)', 'v(br)', 'v(bct)'], 'op')[0][1:]
        out[label] = {'peer_TPBIAS_current_mA': round(-r[0] * 1000, 3), 'peer_TPA_CM_V': round((r[1] + r[2]) / 2, 3),
                      'of_which_standard_5k_mA': round(r[3] / 5000 * 1000, 3)}
    check(out['typical_pins_open']['peer_TPBIAS_current_mA'] < 1.3, 'unpowered typical load')
    check(out['worst_case_1mA_pin_leakage']['peer_TPBIAS_current_mA'] < 5.6, 'unpowered worst-case load')
    check(out['negative_control_fpga_inputs_on_clamping_bank']['peer_TPBIAS_current_mA'] > 5.6,
          'negative control: clamping FPGA inputs must overload TPBIAS')
    out['limit'] = 'peer TPBIAS can source 5.6 mA (TSB81BA3E); pass needs well below that'
    return out


def detect_dc():
    """Connect detect (our TPBIAS off, 47k pull-up on the TPBIAS node, 1.2 V
    threshold) and bias detect (TPB common mode against 0.8 V)."""
    out = []
    for label, peer_present, pbias in [('nothing attached', False, 0), ('peer attached, its bias off', True, 0),
                                       ('peer bias 1.665 V', True, 1.665), ('peer bias 2.015 V', True, 2.015)]:
        body = board(tpbias=None, pbias=pbias) + idle_pads() + 'Rcd vdd tpbias 47k\n'
        if not peer_present:  # open the cable by parking the peer far away
            body = body.replace('Xcb bp bn bq br cable', 'Rob1 bp bq 1g\nRob2 bn br 1g')
            body = body.replace('Xca ap an aq ar cable', 'Roa1 ap aq 1g\nRoa2 an ar 1g')
        body += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
        r = simulate('detect', body, ['v(tpbias)', 'v(bcm)'], 'op')[0][1:]
        out.append({'case': label, 'TPBIAS_node_V': round(r[0], 3), 'connected': r[0] < 1.2,
                    'TPB_common_mode_V': round(r[1], 3), 'bias_detected': r[1] > 0.8})
    check([o['connected'] for o in out] == [False, True, True, True], 'connect detect')
    check([o['bias_detected'] for o in out] == [False, False, True, True], 'bias detect')
    check(out[1]['TPB_common_mode_V'] < 0.6 and out[2]['TPB_common_mode_V'] > 1.0, 'bias detect window 0.6..1.0 V')
    return out


BETA_UI = 1e3 / 983.04


def beta_eye():
    """983.04 Mbaud PRBS7 through the AC-coupled SerDes branches, the shared
    termination and 4.5 m of cable. Three builds: bare line (reference), full
    legacy front end attached and parked, and a 2:1 switch that disconnects
    the legacy front end. Behavioural SerDes and switch; see the lib."""
    n, start, plots = 254, 20.0, {}
    bits = prbs7(n)
    out = {'transmit': [], 'receive': []}
    for build in ('reference', 'legacy_attached', 'legacy_attached_gp', 'switch'):
        legacy = build.startswith('legacy')
        q = 'gp' if build.endswith('gp') else 'rf'
        # --- we transmit: SerDes open-circuit swing 1.2 V peak (TLK1221 minimum)
        body = board(q=q, refs='off', tpbias=None, pbias=0, legacy=legacy, cpar='7p')
        if legacy:
            body += idle_pads(beta=True)
        body += 'Rbcm vdd bct 6.04k\nRacm1 vdd tpbias 5.6k\nRacm2 tpbias 0 4.7k\n'
        if build == 'switch':
            body = body.replace('Xcb bp bn bq br cable', 'Xmb1 mbp bp mux_on\nXmb2 mbn bn mux_on\nXcb mbp mbn bq br cable')
            body = body.replace('Xca ap an aq ar cable', 'Xma1 map ap mux_on\nXma2 man an mux_on\nXca map man aq ar cable')
        body = body.replace('Vpb pbias 0 0\n', 'Rpbz pbias 0 1g\n')
        tx = body + pwl('sig', bits, start, BETA_UI, 0.15, 0.6)
        tx += 'Etp sa 0 sig 0 1\nEtn sb 0 sig 0 -1\nRtp sa stxp 50\nRtn sb stxn 50\n'
        tx += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpcy pcy 0 0\nVpsy psy 0 0\n'
        rows = simulate('beta_tx_' + build, tx, ['v(bq)', 'v(br)', 'v(bp)', 'v(bn)'], f'tran 0.02n {start + n * BETA_UI + 30}n', 0.02)
        e = eye(rows, 1, 2, bits, start, BETA_UI, CABLE_NS, 100)
        launch = max(abs(r[3] - r[4]) for r in rows[len(rows) // 2:])
        out['transmit'].append({'build': build, 'eye_at_peer_receiver': e, 'peak_at_our_connector_mV': round(launch * 1000)})
        if build in ('reference', 'legacy_attached'):
            plots['tx_' + build] = (rows, 1, 2)
        # --- we receive: peer launches 250 mV peak (500 mV p-p) from 110 ohm
        rx = body + pwl('sig', bits, start, BETA_UI, 0.15, 0.25 * 2 / 110)
        rx += 'Vpcx pcx 0 0\nVpsx psx 0 0\nVpsy psy 0 0\nRstx1 stxp 0 1g\nRstx2 stxn 0 1g\n'
        rx += 'Bpy ar aq I={v(sig)}\nVpcy pcy 0 0\n'
        rows = simulate('beta_rx_' + build, rx, ['v(srxp)', 'v(srxn)'], f'tran 0.02n {start + n * BETA_UI + 30}n', 0.02)
        e = eye(rows, 1, 2, bits, start, BETA_UI, CABLE_NS, 100)
        out['receive'].append({'build': build, 'eye_at_SerDes_pins': e})
        if build in ('reference', 'legacy_attached'):
            plots['rx_' + build] = (rows, 1, 2)
    ref_t = out['transmit'][0]['eye_at_peer_receiver']['inner_eye_mV']
    ref_r = out['receive'][0]['eye_at_SerDes_pins']['inner_eye_mV']
    for group, ref, key in (('transmit', ref_t, 'eye_at_peer_receiver'), ('receive', ref_r, 'eye_at_SerDes_pins')):
        for item in out[group]:
            item['eye_height_vs_reference'] = round(item[key]['inner_eye_mV'] / ref, 2)
    att_t, att_r = out['transmit'][1], out['receive'][1]
    out['pass_tx_inner_eye_200mV'] = check(att_t['eye_at_peer_receiver']['inner_eye_mV'] >= 200
                                          and att_t['eye_at_peer_receiver']['width_UI'] >= 0.5, 'beta TX eye')
    out['pass_rx_inner_eye_200mV'] = check(att_r['eye_at_SerDes_pins']['inner_eye_mV'] >= 200
                                          and att_r['eye_at_SerDes_pins']['width_UI'] >= 0.5, 'beta RX eye')
    out['pass_tx_peak_within_800mV'] = check(att_t['peak_at_our_connector_mV'] <= 800, 'beta TX amplitude ceiling')
    out['switch_needed'] = not (out['pass_tx_inner_eye_200mV'] and out['pass_rx_inner_eye_200mV'])
    return out, plots


def beta_legacy_isolation():
    """In legacy mode the idle SerDes branches must not disturb DS: compare the
    S400 receive eye with and without them."""
    bit, tstep, n, _ = SPEEDS['S400']
    d, s = ds_encode(prbs7(n))
    res = {}
    for label, serdes in (('with_serdes_branches', True), ('without', False)):
        body = board(amp_peer=3.13e-3, serdes=serdes) + idle_pads()
        body += pwl('pcy', [0] + d, 60 - bit, bit, 1.2) + pwl('pcx', [0] + s, 60 - bit, bit, 1.2)
        body += 'Vpsx psx 0 0\nVpsy psy 0 0\n'
        if serdes:
            body += 'Rstx1 stxp 0 1g\nRstx2 stxn 0 1g\n'
        rows = simulate('iso_' + label, body, ['v(ap)', 'v(an)'], f'tran {tstep}n {60 + n * bit + 60}n', tstep)
        res[label] = eye(rows, 1, 2, d, 60, bit, CABLE_NS, 50)
    return res


def plot(plots):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), sharex=True)
    titles = {'tx_reference': 'We transmit, bare line (reference)', 'tx_legacy_attached': 'We transmit, legacy front end attached',
              'rx_reference': 'We receive, bare line (reference)', 'rx_legacy_attached': 'We receive, legacy front end attached'}
    for ax, key in zip(axes.flat, titles):
        rows, cp, cn = plots[key]
        t = [(r[0] * 1e9 - 20.0 - CABLE_NS) % (2 * BETA_UI) / BETA_UI for r in rows if r[0] * 1e9 > 60]
        v = [(r[cp] - r[cn]) * 1000 for r in rows if r[0] * 1e9 > 60]
        ax.plot(t, v, '.', color='#2274a5', ms=0.6, alpha=0.25)
        for th in (-100, 100):
            ax.axhline(th, color='#b33', ls='--', lw=0.8)
        ax.set_title(titles[key], fontsize=9)
        ax.grid(alpha=0.2)
    for ax in axes[1]:
        ax.set_xlabel('Unit intervals (two-UI overlay)')
    for ax in axes[:, 0]:
        ax.set_ylabel('Differential voltage (mV)')
    fig.suptitle('983.04 Mbaud behavioural eye, 4.5 m, dashed = 200 mV inner-eye requirement', fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / 'beta-eye.png', dpi=130)
    plt.close(fig)
    return True


def main():
    if not shutil.which('ngspice'):
        raise SystemExit('Install ngspice (macOS: brew install ngspice).')
    BUILD.mkdir(exist_ok=True)
    result = {'model': 'component-level study; datasheet-derived transistor cards, behavioural pads, comparators, SerDes and switch',
              'ngspice': subprocess.check_output(['ngspice', '--version'], text=True).splitlines()[1].strip()}
    result['driver_dc'] = driver_dc()
    result['legacy_transmit'] = legacy_tx()
    result['legacy_receive'] = legacy_rx()
    result['arbitration'] = arbitration()
    result['speed_signalling'] = speed_signalling()
    result['false_speed_negative_control'] = false_speed()
    result['unpowered'] = unpowered()
    result['connect_and_bias_detect'] = detect_dc()
    result['beta_eye'], plots = beta_eye()
    result['legacy_eye_with_idle_serdes'] = beta_legacy_isolation()
    result['beta_eye_png_generated'] = plot(plots)
    result['failed_checks'] = FAILS
    RESULTS.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if FAILS:
        sys.exit('FAILED: ' + '; '.join(FAILS))


if __name__ == '__main__':
    main()
