#!/usr/bin/env python3
"""fw2usb PHY breakout: netlist, bill of materials and placement.

Single source for schematic.py and pcb.py. Pin and function facts are from
TI SLLSFA1 (TSB41BA3F-EP); see ../REVIEW.md for page citations. No vendor
CAD is used. All dimensions are millimetres.

Placement coordinates in this file are relative to the centre of U1 with x
to the east and y to the south. pcb.py adds ORIGIN to get board coordinates.
"""
import csv, json, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = (100.0, 80.0)
REV = '0.2'


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'fw2usb-phy-breakout-v0/' + name))


def q(s):
    return json.dumps(str(s))


# ---------------------------------------------------------------- U1 pins
PINS = {1: 'PINT', 2: 'S5_LKON', 3: 'LREQ', 4: 'DGND', 5: 'PCLK', 6: 'DVDD33', 7: 'LCLK_PMC', 8: 'DVDD_CORE',
        9: 'CTL0', 10: 'CTL1', 11: 'D0', 12: 'D1', 13: 'D2', 14: 'DGND', 15: 'D3', 16: 'D4', 17: 'D5',
        18: 'DVDD33', 19: 'D6', 20: 'D7', 21: 'AGND', 22: 'R1', 23: 'R0', 24: 'AVDD', 25: 'PLLGND', 26: 'XO',
        27: 'XI', 28: 'PLLGND', 29: 'PLLVDD_CORE', 30: 'PLLVDD_CORE', 31: 'PLLVDD33', 32: 'S4', 33: 'S3',
        34: 'CPS', 35: 'SE', 36: 'SM', 37: 'DVDD_CORE', 38: 'DGND', 39: 'AVDD', 40: 'AGND', 41: 'TPB0-',
        42: 'TPB0+', 43: 'AGND', 44: 'AVDD', 45: 'TPA0-', 46: 'TPA0+', 47: 'TPBIAS0', 48: 'TPB1-', 49: 'TPB1+',
        50: 'AGND', 51: 'AVDD', 52: 'TPA1-', 53: 'TPA1+', 54: 'TPBIAS1', 55: 'TPB2-', 56: 'TPB2+', 57: 'AVDD',
        58: 'TPA2-', 59: 'TPA2+', 60: 'TPBIAS2', 61: 'AGND', 62: 'AGND', 63: 'AVDD', 64: 'DGND',
        65: 'DVDD_CORE', 66: 'S2_PC0', 67: 'S1_PC1', 68: 'S0_PC2', 69: 'DVDD33', 70: 'DVDD33',
        71: 'DVDD_CORE', 72: 'DGND', 73: 'VREG_PD', 74: 'BMODE', 75: 'RESET_N', 76: 'DGND', 77: 'PD',
        78: 'TESTM', 79: 'ENHANCE_EN', 80: 'LPS', 81: 'EP'}
assert set(PINS) == set(range(1, 82))
SUPPLY = {'AVDD', 'DVDD33', 'PLLVDD33'}
# Tied straight to ground: supply grounds, the exposed pad, the tie-low mode
# inputs, and TPB of the unused data-strobe port 1 (SLLSFA1 p18).
GROUND = {'AGND', 'DGND', 'PLLGND', 'EP', 'LCLK_PMC', 'BMODE', 'VREG_PD', 'PD', 'SM', 'SE', 'TPB1-', 'TPB1+'}
NC = {'PINT', 'TPB0-', 'TPB0+', 'TPA0-', 'TPA0+', 'TPBIAS0', 'TPA1-', 'TPA1+', 'TPBIAS1'}


def u1_net(number):
    name = PINS[number]
    return '3V3' if name in SUPPLY else 'GND' if name in GROUND else None if name in NC else name


UPINS = []
for number, name in PINS.items():
    kind = 'power_in' if name in SUPPLY | {'AGND', 'DGND', 'PLLGND', 'EP', 'DVDD_CORE', 'PLLVDD_CORE'} else 'bidirectional'
    if name in {'LREQ', 'LPS', 'RESET_N', 'TESTM', 'ENHANCE_EN', 'S4', 'S3', 'S2_PC0', 'S1_PC1', 'S0_PC2', 'CPS',
                'XI', 'LCLK_PMC', 'VREG_PD', 'BMODE', 'PD', 'SM', 'SE'}:
        kind = 'input'
    if name in {'PCLK', 'XO', 'PINT'}:
        kind = 'output'
    if name.startswith('TP'):
        kind = 'passive'
    if number in {8, 29}:
        kind = 'power_out'  # internal regulator outputs
    UPINS.append((str(number), name, u1_net(number), kind))


def u1_pad(number):
    """Centre of a U1 land, relative to the U1 centre."""
    i = (number - 1) % 20
    side = (number - 1) // 20
    return [(-6.8, -4.75 + i * .5), (-4.75 + i * .5, 6.8), (6.8, 4.75 - i * .5), (4.75 - i * .5, -6.8)][side]


# ---------------------------------------------------------------- parts
parts = []


def add(ref, value, foot, pins, mpn, note='', **place):
    parts.append(dict(ref=ref, value=value, foot=foot, pins=pins, mpn=mpn, verify=note, **place))


def two(ref, value, net1, net2, p1, p2, mpn, foot='R', side='F', note=''):
    """Two-pad part given by where pad 1 and pad 2 must end up."""
    add(ref, value, foot, [('1', '1', net1, 'passive'), ('2', '2', net2, 'passive')], mpn, note,
        pads={'1': p1, '2': p2}, side=side)


R1K, R22 = 'Yageo RC0402FR-071KL', 'Yageo RC0402FR-0722RL'
C100N, C1N, C1U = 'Murata GRM155R71C104KA88D', 'Murata GRM1555C1H102JA01D', 'Murata GRM155R61A105KE15D'

add('U1', 'TSB41BA3FTPFPEP', 'HTQFP80', UPINS, 'TI TSB41BA3FTPFPEP',
    'check stock and price before ordering; see REVIEW.md', xy=(0, 0), check={'1': (-6.8, -4.75)})

# --- J2: 2x10 header to the FPGA board. Odd pins are the west column.
# Trace slots run north to south at 1.27 mm pitch: slot 2r-1 goes to the east
# pin of row r (pin 2r), slot 2r to the west pin (pin 2r-1).
J2_X, J2_Y = -24.0, -13.1
SLOTS = ['RESET_N', 'GND', 'LPS_H', 'LKON_H', 'LREQ_H', 'GND', 'SCLK_H', 'GND', 'CTL0_H', 'GND', 'CTL1_H',
         'D0_H', 'D1_H', 'D2_H', 'D3_H', 'D4_H', 'D5_H', 'D6_H', 'D7_H', 'GND']


def slot_y(net):
    return J2_Y + SLOTS.index(net) * 1.27


def slot_pin(k):  # k is the 0-based slot index
    row = k // 2
    return 2 * row + 2 if k % 2 == 0 else 2 * row + 1


J2_NET = {slot_pin(k): net for k, net in enumerate(SLOTS)}
add('J2', 'FPGA_2x10', 'Header20',
    [(str(n), J2_NET[n] if J2_NET[n] != 'GND' else 'GND', J2_NET[n],
      'passive' if J2_NET[n] == 'GND' else 'bidirectional') for n in range(1, 21)],
    'Samtec TSW-110-07-G-D', 'any 2x10 2.54 mm header', xy=(J2_X, J2_Y), check={'2': (J2_X + 2.54, J2_Y)})

add('J3', 'BENCH_3V3', 'Header2', [('1', '3V3', '3V3', 'power_out'), ('2', 'GND', 'GND', 'power_out')],
    'Samtec TSW-102-07-G-S', 'regulated 3.3 V, 200 mA or more', xy=(9.0, 9.9), check={'2': (9.0, 12.44)})

# --- J1: FW400 6-pin receptacle, mouth to the east. VP is not connected.
J1_X, J1_Y = 18.7, -2.25
add('J1', 'FW400_6PIN', 'FW6SMT',
    [('1', 'VP', None, 'passive'), ('2', 'VG', 'GND', 'passive'), ('3', 'TPB-', 'TPB2-', 'passive'),
     ('4', 'TPB+', 'TPB2+', 'passive'), ('5', 'TPA-', 'TPA2-', 'passive'), ('6', 'TPA+', 'TPA2+', 'passive'),
     ('SH', 'SHELL', 'SHIELD', 'passive')],
    'Keystone 927TR', 'second source Assmann WSW A-IES-SMT-U/R: check its pad order by continuity first',
    xy=(J1_X, J1_Y), check={'6': (J1_X - .05, J1_Y - 2.5), '1': (J1_X - .05, J1_Y + 2.5)})

# --- U2: ESD array, flow-through. Pins 6, 7, 9, 10 are unconnected inside
# the part and exist for straight-through routing, so they carry the nets.
add('U2', 'TPD4E05U06', 'USON10',
    [('1', 'D1+', 'TPA2+', 'passive'), ('2', 'D1-', 'TPA2-', 'passive'), ('3', 'GND', 'GND', 'passive'),
     ('4', 'D2+', 'TPB2+', 'passive'), ('5', 'D2-', 'TPB2-', 'passive'), ('6', 'NC6', 'TPB2-', 'passive'),
     ('7', 'NC7', 'TPB2+', 'passive'), ('8', 'GND', 'GND', 'passive'), ('9', 'NC9', 'TPA2-', 'passive'),
     ('10', 'NC10', 'TPA2+', 'passive')],
    'TI TPD4E05U06DQAR', '', xy=(14.2, -3.25), check={'1': (13.815, -4.25), '10': (14.585, -4.25)})

# --- Y1: 49.152 MHz fundamental, 3.2 x 2.5 mm, pads 2 and 4 ground.
# The crystal is not polarised: pad 3 is used for XI and pad 1 for XO.
add('Y1', '49.152MHz CL6pF', 'Crystal4',
    [('1', 'X1', 'XO', 'passive'), ('2', 'GND', 'GND', 'passive'), ('3', 'X2', 'XI', 'passive'),
     ('4', 'GND', 'GND', 'passive')],
    'Abracon ABM8W-49.1520MHZ-6-K1Z-T3',
    'any 49.152 MHz fundamental 3225 crystal, 30 ppm; recalculate C6/C7 for its load',
    xy=(-2.0, 10.6), check={'3': (-0.9, 9.8), '1': (-3.1, 11.4)})

# --- Straps (SLLSFA1 Table 5-1 mode 3: S5=0, S4=1, S3=0, power class 000).
two('R1', '1k', 'S5_LKON', 'GND', (-8.9, -4.35), (-8.9, -5.45), R1K)
two('R2', '1k', 'S4', '3V3', (2.3, 10.3), (2.3, 11.4), R1K)
two('R3', '1k', 'S3', 'GND', (3.4, 10.6), (3.4, 11.7), R1K)
two('R4', '1k', 'S2_PC0', 'GND', (2.75, -8.7), (2.75, -9.8), R1K)
two('R5', '1k', 'S1_PC1', 'GND', (1.75, -8.7), (1.75, -9.8), R1K)
two('R6', '1k', 'S0_PC2', 'GND', (0.75, -8.7), (0.75, -9.8), R1K)
two('R7', '1k', 'TESTM', '3V3', (-3.45, -8.5), (-3.45, -9.6), R1K)
two('R8', '1k', 'ENHANCE_EN', '3V3', (-4.25, -10.6), (-4.25, -11.7), R1K)
two('R9', '1k', 'CPS', 'GND', (4.5, 11.0), (4.5, 12.1), R1K)

# --- PHY-LINK bus: series resistors in one column, pad 1 toward the PHY.
RCOL = (-15.0, -16.1)
two('R10', '1k', 'LPS', 'LPS_H', (RCOL[0], slot_y('LPS_H')), (RCOL[1], slot_y('LPS_H')), R1K)
two('R11', '1k', 'S5_LKON', 'LKON_H', (RCOL[0], slot_y('LKON_H')), (RCOL[1], slot_y('LKON_H')), R1K)
BUS = [('R12', 'PCLK', 'SCLK_H'), ('R21', 'LREQ', 'LREQ_H'), ('R22', 'CTL0', 'CTL0_H'), ('R23', 'CTL1', 'CTL1_H')] + \
      [('R%d' % (24 + i), 'D%d' % i, 'D%d_H' % i) for i in range(8)]
for ref, a, b in BUS:
    two(ref, '22', a, b, (RCOL[0], slot_y(b)), (RCOL[1], slot_y(b)), R22)
two('R20', '10k', 'LPS_H', 'GND', (-18.0, slot_y('LPS_H')), (-18.0, slot_y('LPS_H') - 1.1),
    'Yageo RC0402FR-0710KL')

two('R13', '6.34k 1%', 'R1', 'R0', (-4.55, 8.6), (-3.45, 8.6), 'Yageo RC0402FR-076K34L')

# --- Port 2 termination (SLLSFA1 Figure 13-3). Pad 1 sits on the line.
RTERM = 'Yageo RC0402FR-0756R2L'
two('R15', '56.2 1%', 'TPA2+', 'TPBIAS2', (9.8, -4.80), (9.8, -5.90), RTERM)
two('R14', '56.2 1%', 'TPA2-', 'TPBIAS2', (11.2, -4.10), (11.2, -3.00), RTERM)
two('R17', '56.2 1%', 'TPB2+', 'TPB_CM', (9.8, -2.40), (9.8, -3.50), RTERM)
two('R16', '56.2 1%', 'TPB2-', 'TPB_CM', (11.2, -1.70), (11.2, -0.60), RTERM)
two('R18', '4.99k 1%', 'TPB_CM', 'GND', (12.3, -0.6), (13.4, -0.6), 'Yageo RC0402FR-074K99L')
two('C1', '270p C0G', 'TPB_CM', 'GND', (11.2, 0.5), (11.2, 1.6), 'Murata GRM1555C1H271JA01D', 'C')
two('C2', '1u', 'TPBIAS2', 'GND', (8.6, -5.9), (8.6, -7.0), C1U, 'C')

# --- Shield to ground (SLLSFA1 Figure 13-4).
two('R19', '1M', 'SHIELD', 'GND', (19.5, 6.0), (19.5, 7.6), 'Yageo RC0603FR-071ML', 'R0603')
two('C3', '10n 50V', 'SHIELD', 'GND', (21.2, 6.0), (21.2, 7.6), 'Murata GRM188R71H103KA01D', 'C0603')
two('C4', '1n 50V', 'SHIELD', 'GND', (22.9, 6.0), (22.9, 7.6), 'Murata GRM1885C1H102JA01D', 'C0603')

two('C5', '220n', 'RESET_N', 'GND', (-2.25, -8.6), (-1.15, -8.6), 'Murata GRM155R71C224KA12D', 'C',
    note='measure reset low time at power-up, 2 ms minimum')
two('C6', '8.2p C0G', 'XI', 'GND', (0.35, 9.8), (1.45, 9.8), 'Murata GRM1555C1H8R2DA01D', 'C',
    note='trim so that PCLK is 49.152 MHz within 100 ppm')
two('C7', '8.2p C0G', 'XO', 'GND', (-4.3, 11.4), (-4.3, 10.3), 'Murata GRM1555C1H8R2DA01D', 'C',
    note='keep equal to C6')

# --- Decoupling on the bottom side, under the U1 pin rows. Each capacitor
# lies radially: pad 1 (supply) 4.75 mm from the U1 centre, pad 2 (ground)
# 3.65 mm, where it joins the ground copper under the thermal pad.
def inner(side, t):
    return {'W': ((-4.75, t), (-3.65, t)), 'E': ((4.75, t), (3.65, t)),
            'N': ((t, -4.75), (t, -3.65)), 'S': ((t, 4.75), (t, 3.65))}[side]


DECOUPLING = [  # ref, value, net, side, position along the side, mpn
    ('C8', '100n', '3V3', 'W', -2.25, C100N), ('C9', '100n', 'DVDD_CORE', 'W', -1.25, C100N),
    ('C10', '1u', 'DVDD_CORE', 'W', -0.2, C1U), ('C11', '100n', '3V3', 'W', 2.9, C100N),
    ('C12', '100n', '3V3', 'S', -3.25, C100N), ('C13', '1n', '3V3', 'S', -2.3, C1N),
    ('C14', '1n', 'PLLVDD_CORE', 'S', -1.5, C1N), ('C15', '100n', 'PLLVDD_CORE', 'S', -0.7, C100N),
    ('C16', '100n', '3V3', 'S', 0.4, C100N), ('C17', '1n', '3V3', 'S', 1.3, C1N),
    ('C18', '1n', '3V3', 'S', 2.25, C1N), ('C19', '100n', 'DVDD_CORE', 'S', 3.25, C100N),
    ('C20', '100n', '3V3', 'S', 4.25, C100N),
    ('C21', '100n', '3V3', 'E', 2.6, C100N), ('C22', '1n', '3V3', 'E', 1.65, C1N),
    ('C23', '1n', '3V3', 'E', 0.7, C1N), ('C24', '100n', '3V3', 'E', -0.25, C100N),
    ('C25', '1n', '3V3', 'E', -1.95, C1N), ('C26', '100n', '3V3', 'E', -2.9, C100N),
    ('C27', '100n', '3V3', 'N', 3.75, C100N), ('C28', '100n', 'DVDD_CORE', 'N', 2.75, C100N),
    ('C29', '1n', '3V3', 'N', 1.75, C1N), ('C30', '100n', '3V3', 'N', 0.7, C100N),
    ('C31', '100n', 'DVDD_CORE', 'N', -0.4, C100N)]
for ref, value, net, side, t, mpn in DECOUPLING:
    p1, p2 = inner(side, t)
    two(ref, value, net, 'GND', p1, p2, mpn, 'C', side='B')
two('C32', '1u', 'PLLVDD_CORE', 'GND', (-0.5, 6.3), (-0.5, 7.4), C1U, 'C', side='B')
two('C33', '10u 10V', '3V3', 'GND', (11.4, 10.2), (11.4, 12.2), 'Murata GRM21BR61A106KE19L', 'C0805')
two('C34', '10u 10V', '3V3', 'GND', (6.0, -9.6), (8.0, -9.6), 'Murata GRM21BR61A106KE19L', 'C0805')

# Board outline and mounting holes (3.2 mm, unplated, not in the schematic).
OUTLINE = (-30.6, -16.8, 27.2, 15.8)  # west, north, east, south
HOLES = [(-27.8, -14.0), (-27.8, 13.0), (24.2, -13.6), (24.2, 12.8)]

FOOT_DESC = {'R': '0402', 'C': '0402', 'R0603': '0603', 'C0603': '0603', 'C0805': '0805',
             'HTQFP80': 'HTQFP-80 12x12 mm 0.5 mm pitch, 6x6 mm pad', 'Header20': '2x10 2.54 mm',
             'Header2': '1x2 2.54 mm', 'Crystal4': '3.2x2.5 mm 4-pad', 'USON10': 'USON-10 2.5x1.0 mm',
             'FW6SMT': 'IEEE 1394 6-pin right-angle SMT'}

# Design rules, written into the KiCad project file by pcb.py. They are the
# limits this board is checked against; see README for the board-house rules.
RULES = {'min_clearance': 0.127, 'min_track_width': 0.127, 'min_via_diameter': 0.45,
         'min_via_annular_width': 0.1, 'min_through_hole_diameter': 0.3, 'min_hole_to_hole': 0.25,
         'min_hole_clearance': 0.2, 'min_copper_edge_clearance': 0.3, 'min_text_height': 0.4,
         'min_text_thickness': 0.05, 'min_resolved_spokes': 1}
NETCLASS = {'clearance': 0.15, 'track_width': 0.2, 'via_diameter': 0.5, 'via_drill': 0.3,
            'diff_pair_width': 0.22, 'diff_pair_gap': 0.28}
TP_PATTERN = '/TP[AB]2*'   # the port 2 pairs get their own class for width


def bom_rows():
    groups = {}
    for p in parts:
        key = (p['value'], p['foot'], p['mpn'])
        groups.setdefault(key, []).append(p)
    rows = []
    for (value, foot, mpn), members in groups.items():
        refs = [m['ref'] for m in members]
        sides = sorted({m.get('side', 'F') for m in members})
        notes = sorted({m['verify'] for m in members if m['verify']})
        rows.append([' '.join(refs), len(refs), value, FOOT_DESC[foot], mpn,
                     'top' if sides == ['F'] else 'bottom' if sides == ['B'] else 'both', '; '.join(notes)])
    return rows


if __name__ == '__main__':
    refs = [p['ref'] for p in parts]
    assert len(refs) == len(set(refs)), 'duplicate reference'
    (ROOT / 'design.json').write_text(json.dumps(parts, indent=1) + '\n')
    with (ROOT / 'BOM.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['References', 'Qty', 'Value', 'Package', 'Manufacturer part', 'Side', 'Note'])
        w.writerows(bom_rows())
    print(len(parts), 'components,', len(bom_rows()), 'BOM lines')
