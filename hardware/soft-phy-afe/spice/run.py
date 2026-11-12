#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Reproducible architecture study. Python stdlib + ngspice; plots optional.
No downloaded/vendor models. All generated decks and raw traces in build/.
Exit nonzero on an unexpected regression; the injected false-speed case MUST fail.
"""
import itertools
import json
import math
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / 'build'
RESULTS = ROOT / 'results.json'


def simulate(name, body, vectors, analysis):
    deck = BUILD / (name + '.cir')
    data = BUILD / (name + '.txt')
    deck.write_text('* SPDX-License-Identifier: CERN-OHL-S-2.0\n'
                    '* Generated behavioral study; see README.\n.options method=gear\n.include afe.lib\n' + body +
                    '\n.save ' + ' '.join(vectors) + '\n.control\nset wr_singlescale\n' + analysis +
                    ('\nlinearize ' + ' '.join(vectors) if analysis.startswith('tran') else '') +
                    '\nwrdata ' + str(data) + ' ' + ' '.join(vectors) + '\nquit\n.endc\n.end\n')
    done = subprocess.run(['ngspice', '-b', str(deck)], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    (BUILD / (name + '.log')).write_text(done.stdout + done.stderr)
    if done.returncode or not data.exists() or 'Error' in done.stderr:
        raise RuntimeError(f'{name}: ngspice failed; inspect build/{name}.log')
    return [[float(x) for x in line.split()] for line in data.read_text().splitlines()
            if line.strip()]


def classify(v, threshold=0.125):
    return 1 if v > threshold else -1 if v < -threshold else 0


def dc_study():
    # Covers both pairs independently and their Cartesian product (81 port codes).
    # Pair1 local A->remote B; pair2 remote A->local B. Labels are terminal-local.
    worst_z, smallest_driven, tests = 0.0, 1.0, 0
    for corner, (amp_l, amp_r, mis, bias) in enumerate([
        (0.004, 0.004, 0, 1.86),
        (0.0036, 0.0044, 0.0001, 1.665),
        (0.0044, 0.0036, -0.0001, 2.015),
    ]):
        for a, b, c, d in itertools.product([-1, 0, 1], repeat=4):
            body = f'''Vref ref 0 {bias}
Va a 0 {a}
Vb b 0 {b}
Vc c 0 {c}
Vd d 0 {d}
Vcm cm 0 0
Xone p n q r ref a b cm cm port_pair ampL={amp_l} ampR={amp_r} mis={mis}
Xtwo u v w x ref c d cm cm port_pair ampL={amp_l} ampR={amp_r} mis={mis}
'''
            row = simulate(f'dc_{corner}_{tests}', body,
                           ['v(p)', 'v(n)', 'v(q)', 'v(r)', 'v(u)', 'v(v)', 'v(w)', 'v(x)'], 'op')[0][1:]
            for start, left, right in [(0, a, b), (4, c, d)]:
                expected = (left + right > 0) - (left + right < 0)
                for index in (start, start + 2):
                    voltage = row[index] - row[index + 1]
                    for th in (0.110, 0.125, 0.140):
                        assert classify(voltage, th) == expected, (corner, left, right, voltage, th)
                    if expected:
                        smallest_driven = min(smallest_driven, abs(voltage))
                    else:
                        worst_z = max(worst_z, abs(voltage))
            tests += 1
    return {'port_codes_per_corner': 81, 'corners': 3, 'dc_solves': tests,
            'smallest_driven_mV': smallest_driven * 1000, 'largest_Z_mV': worst_z * 1000,
            'driven_margin_at_140mV_mV': smallest_driven * 1000 - 140,
            'Z_margin_at_110mV_mV': 110 - worst_z * 1000,
            'classification_errors': 0}


def pwl(name, values, start, bit_ns, edge_ns=0.8):
    points = [(0.0, 0.0), (start - 2.0, 0.0)]
    old = 0.0
    for i, value in enumerate(values):
        t = start + i * bit_ns
        if value != old:
            points.extend([(t, old), (t + edge_ns, float(value))])
            old = float(value)
    points.append((start + len(values) * bit_ns + 100, old))
    return f'V{name} {name} 0 PWL(' + ' '.join(f'{t:.9f}n {v}' for t, v in points) + ')\n'


def interpolate(rows, time, col):
    # Transient output is adaptive. Binary-search/interpolate physical bit centers.
    lo, hi = 0, len(rows) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if rows[mid][0] < time:
            lo = mid
        else:
            hi = mid
    f = (time - rows[lo][0]) / (rows[hi][0] - rows[lo][0])
    return rows[lo][col] * (1 - f) + rows[hi][col] * f


def ds_study():
    state, random_bits = 0x31415927, []
    for _ in range(1024):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        state &= 0xffffffff
        random_bits.append(state & 1)
    patterns = {'prbs': random_bits, 'zero': [0]*1024, 'one': [1]*1024,
                'alternating': [i & 1 for i in range(1024)]}
    bit_ns, start = 1e9 / 98_304_000, 100.0
    reports, plot_data = [], None
    for direction in ('forward', 'reverse'):
        for pattern, bits in patterns.items():
            prev, strobe, ds = 0, 0, []
            for bit in bits:
                if bit == prev:
                    strobe ^= 1
                ds.append((2*bit-1, 2*strobe-1))
                prev = bit
            body = 'Vref ref 0 1.86\nVz z 0 0\nVcm cm 0 0\n'
            body += pwl('dat', [x[0] for x in ds], start, bit_ns)
            body += pwl('str', [x[1] for x in ds], start, bit_ns)
            if direction == 'forward':
                body += 'Xa ap an aq ar ref str z cm cm port_pair\nXb bp bn bq br ref dat z cm cm port_pair\n'
                nodes = ['bq', 'br', 'aq', 'ar']
            else:
                body += 'Xa ap an aq ar ref z dat cm cm port_pair\nXb bp bn bq br ref z str cm cm port_pair\n'
                nodes = ['ap', 'an', 'bp', 'bn']
            rows = simulate('ds_' + direction + '_' + pattern, body,
                            [f'v({n})' for n in nodes], f'tran 0.1n {start + 1024*bit_ns + 100}n')
            margin, errors, recovered = 1.0, 0, []
            # Ideal TLV comparator fixed latency is not relevant to eye amplitude;
            # mismatch and the actual FPGA asynchronous capture are separate risks.
            for i, (data, strobe) in enumerate(ds):
                t = (start + 22.725 + (i + 0.5)*bit_ns) * 1e-9
                for jitter in (-1.88e-9, 0, 1.88e-9):
                    window_d = interpolate(rows,t+jitter,1)-interpolate(rows,t+jitter,2)
                    window_s = interpolate(rows,t+jitter,3)-interpolate(rows,t+jitter,4)
                    margin = min(margin, data*window_d, strobe*window_s)
                vd = interpolate(rows,t,1) - interpolate(rows,t,2)
                vs = interpolate(rows,t,3) - interpolate(rows,t,4)
                margin = min(margin, data*vd, strobe*vs)
                errors += int((vd > 0) != (data > 0)) + int((vs > 0) != (strobe > 0))
                recovered.append((vd > 0) ^ (vs > 0))
            edges = sum(a != b for a,b in zip(recovered,recovered[1:]))
            assert errors == 0 and edges == len(bits)-1
            assert margin > 0.118, (direction, pattern, margin)
            reports.append({'direction':direction,'pattern':pattern,'bits':len(bits),
                            'bit_errors':errors,'XOR_edges_between_centers':edges,
                            'minimum_signed_eye_mV':margin*1000,
                            'tested_center_timing_window_ns':3.76,
                            'margin_over_30mV_data_threshold_mV':margin*1000-30})
            if direction == 'forward' and pattern == 'prbs':
                plot_data = (rows, start, bit_ns)
    return reports, plot_data


def cm_study():
    reports = []
    for label, pulse, width in [('balanced',0,20), ('100uA_imbalance',-0.0001,20),
                                 ('negative_control_missing_4mA_leg',-0.004,20)]:
        body = f'''Vref ref 0 1.86
Vz z 0 0
Vc c 0 1
Vcm cm 0 PULSE(0 {pulse} 200n 0.2n 0.2n {width}n 1u)
Xpair p n q r ref z c z cm port_pair
'''
        rows = simulate('cm_' + label, body, ['v(p)','v(n)','v(q)','v(r)'], 'tran 0.05n 500n')
        # Observe the peer TPA at the biased end, relative to its TPBIAS reference.
        droops = [(r[0],1.86-(r[1]+r[2])/2) for r in rows if r[0]>100e-9]
        peak = max(v for _,v in droops)
        duration = sum(t1-t0 for (t0,v0),(t1,v1) in zip(droops,droops[1:])
                       if max(v0,v1)>0.049)
        detects = peak > 0.049
        assert detects == label.startswith('negative_control'), (label,peak)
        reports.append({'case':label,'peak_TPA_droop_mV':peak*1000,
                        'time_above_49mV_ns':duration*1e9,
                        'crosses_minimum_S200_threshold':detects})
    return reports


def window_study():
    combinations = list(itertools.product([-1,0,1],repeat=2))
    body = 'Vref ref 0 1.86\nVz z 0 0\n'
    body += pwl('lc',[a for a,b in combinations],100,500)
    body += pwl('rc',[b for a,b in combinations],100,500)
    body += 'Xpair p n q r ref lc rc z z port_pair\n'
    body += 'Xwl p n pl nl window\nXwr q r pr nr window\n'
    rows = simulate('arbitration_window',body,['v(pl)','v(nl)','v(pr)','v(nr)'],
                    'tran 0.5n 4700n')
    for i,(a,b) in enumerate(combinations):
        expected = (a+b>0)-(a+b<0)
        t=(100+i*500+200)*1e-9
        for positive,negative in [(1,2),(3,4)]:
            got = int(interpolate(rows,t,positive)>0.5)-int(interpolate(rows,t,negative)>0.5)
            assert got==expected, (a,b,got,expected)
    return {'states':9,'ends':2,'post_change_sample_ns':200,
            'assumed_differential_bandwidth_MHz':10,'classification_errors':0}


def connect_study():
    result = []
    # DC: a powered or unpowered remote bias; no active probe of an unpowered peer.
    for bias in (0,1.665,1.86,2.015):
        body = f'Vref ref 0 {bias}\nVz z 0 0\nXpair p n q r ref z z z z port_pair\n'
        row = simulate('connect_' + str(bias),body,['v(q)','v(r)'],'op')[0]
        observed = (row[1]+row[2])/2
        assert (observed>0.8) == (bias>0)
        result.append({'remote_bias_V':bias,'local_TPB_common_mode_V':observed,
                       'bias_present':observed>0.8})
    return result


def plot_eye(data):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    rows,start,bit_ns = data
    fig, ax = plt.subplots(figsize=(8,4))
    for r in rows:
        phase = ((r[0]*1e9-start-22.725) % (2*bit_ns))/bit_ns
        if r[0]*1e9>start+100 and r[0]*1e9<start+3000:
            ax.plot(phase,(r[1]-r[2])*1000,'.',color='#2274a5',ms=0.5,alpha=.20)
    for threshold in (-30,30):
        ax.axhline(threshold,color='#b33',ls='--',lw=.8)
    ax.set(xlabel='Bit periods (two-unit-interval overlay)',ylabel='Data differential voltage (mV)',
           title='S100 behavioral cable eye: 4.5 m, 5 pF per terminal; no jitter/receiver macromodel')
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(ROOT / 'eye.png',dpi=150)
    plt.close(fig)
    return True


def main():
    if not shutil.which('ngspice'):
        raise SystemExit('Install ngspice (macOS: brew install ngspice).')
    BUILD.mkdir(exist_ok=True)
    result = {'model':'architecture only; no board or transistor qualification',
              'ngspice':subprocess.check_output(['ngspice','--version'],text=True).splitlines()[1],
              'dc':dc_study()}
    result['ds'],data = ds_study()
    result['common_mode'] = cm_study()
    result['connect_detect'] = connect_study()
    result['arbitration_window'] = window_study()
    result['eye_png_generated'] = plot_eye(data)
    RESULTS.write_text(json.dumps(result,indent=2) + '\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
