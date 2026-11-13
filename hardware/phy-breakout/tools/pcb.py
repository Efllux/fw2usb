#!/usr/bin/env python3
"""fw2usb PHY breakout: footprints, placement, routing and copper zones.

Run with the Python bundled in KiCad 8 (it provides pcbnew). Everything on
the board is produced here from design.py, so the board is reproducible:
re-running overwrites phy-breakout.kicad_pcb and fw2usb.pretty.

Layers: F.Cu signals, In1.Cu solid ground, In2.Cu 3.3 V plane (plus the
digital core rail as a track), B.Cu ground fill and decoupling capacitors.
Routing coordinates are relative to the centre of U1, x east, y south.
"""
import json, math, sys
from pathlib import Path
import wx
app = wx.App(False)
import pcbnew as k
from design import (ROOT, ORIGIN, REV, parts, uid, u1_pad, PINS, u1_net, slot_y, SLOTS, slot_pin,
                    J2_X, J2_Y, J1_X, J1_Y, RCOL, BUS, OUTLINE, HOLES, DECOUPLING, inner,
                    RULES, NETCLASS, TP_PATTERN)

mm = k.FromMM
F, B, IN1, IN2 = k.F_Cu, k.B_Cu, k.In1_Cu, k.In2_Cu
W_SIG, W_TP, W_PWR = 0.2, 0.22, 0.4
VIA = (0.5, 0.3)        # diameter, drill
VIA_TH = (0.6, 0.3)     # thermal vias in the U1 pad


def P(x, y):
    return k.VECTOR2I(mm(x + ORIGIN[0]), mm(y + ORIGIN[1]))


def L(x, y):  # footprint-local point
    return k.VECTOR2I(mm(x), mm(y))


# ------------------------------------------------------------ footprints
def pad(fp, number, x, y, w, h, drill=None, shape=None, plated=True, slot=None):
    p = k.PAD(fp)
    p.SetNumber(str(number))
    p.SetPosition(L(x, y))
    p.SetSize(L(w, h))
    smd = drill is None
    p.SetShape(shape if shape is not None else (k.PAD_SHAPE_RECT if smd else k.PAD_SHAPE_OVAL))
    p.SetAttribute(k.PAD_ATTRIB_SMD if smd else (k.PAD_ATTRIB_PTH if plated else k.PAD_ATTRIB_NPTH))
    layers = k.LSET()
    for layer in ([k.F_Cu, k.F_Paste, k.F_Mask] if smd else [k.F_Cu, k.In1_Cu, k.In2_Cu, k.B_Cu, k.F_Mask, k.B_Mask]):
        layers.AddLayer(layer)
    p.SetLayerSet(layers)
    if not smd:
        if slot:
            p.SetDrillShape(k.PAD_DRILL_SHAPE_OBLONG)
            p.SetDrillSize(L(*slot))
        else:
            p.SetDrillSize(L(drill, drill))
    fp.Add(p)
    return p


def line(fp, layer, a, b, width=0.12):
    s = k.PCB_SHAPE(fp)
    s.SetShape(k.SHAPE_T_SEGMENT)
    s.SetStart(L(*a)); s.SetEnd(L(*b)); s.SetLayer(layer); s.SetWidth(mm(width))
    fp.Add(s)


def box(fp, layer, x0, y0, x1, y1, width=0.12):
    for a, b in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        line(fp, layer, a, b, width)


def footprint(name):
    f = k.FOOTPRINT(None)
    f.SetFPID(k.LIB_ID('fw2usb', name))
    f.SetAttributes(k.FP_SMD)
    body = None      # fabrication-layer outline
    silk = None      # silkscreen outline, only for parts that need orienting
    if name in ['R', 'C', 'R0603', 'C0603', 'C0805']:
        spacing, w, h = .55, .6, .6
        if '0603' in name: spacing, w, h = .8, .9, .95
        if '0805' in name: spacing, w, h = 1.0, 1.0, 1.4
        pad(f, 1, -spacing, 0, w, h); pad(f, 2, spacing, 0, w, h)
        body = (-spacing, -h / 2 + .1, spacing, h / 2 - .1)
    elif name == 'HTQFP80':
        # 12 x 12 mm body, 14 mm lead span, 0.5 mm pitch, 6 x 6 mm exposed pad.
        for i in range(20):
            pad(f, i + 1, -6.8, -4.75 + i * .5, 1.5, .3)
            pad(f, i + 21, -4.75 + i * .5, 6.8, .3, 1.5)
            pad(f, i + 41, 6.8, 4.75 - i * .5, 1.5, .3)
            pad(f, i + 61, 4.75 - i * .5, -6.8, .3, 1.5)
        pad(f, 81, 0, 0, 6, 6)
        body = (-6, -6, 6, 6)
        # Pin 1 mark outside the north-west corner.
        line(f, k.F_SilkS, (-7.9, -5.4), (-7.9, -7.9)); line(f, k.F_SilkS, (-7.9, -7.9), (-5.4, -7.9))
        line(f, k.F_Fab, (-6, -5), (-5, -6), .1)
    elif name == 'Header20':
        f.SetAttributes(k.FP_THROUGH_HOLE)
        for i in range(20):
            pad(f, i + 1, (i % 2) * 2.54, (i // 2) * 2.54, 1.7, 1.7, 1.0,
                shape=k.PAD_SHAPE_RECT if i == 0 else None)
        body = silk = (-1.37, -1.37, 3.91, 24.23)
    elif name == 'Header2':
        f.SetAttributes(k.FP_THROUGH_HOLE)
        for i in range(2):
            pad(f, i + 1, 0, i * 2.54, 1.7, 1.7, 1.0, shape=k.PAD_SHAPE_RECT if i == 0 else None)
        body = silk = (-1.37, -1.37, 1.37, 3.91)
    elif name == 'Crystal4':
        for number, x, y in [(1, -1.1, .8), (2, 1.1, .8), (3, 1.1, -.8), (4, -1.1, -.8)]:
            pad(f, number, x, y, 1.2, 1.0)
        body = (-1.6, -1.25, 1.6, 1.25)
    elif name == 'USON10':
        # TI DQA, 2.5 x 1.0 mm, 0.5 mm pitch; land pattern as KiCad USON-10.
        for i in range(5):
            pad(f, i + 1, -.385, -1 + i * .5, .55, .3)
            pad(f, 10 - i, .385, -1 + i * .5, .55, .3)
        body = (-.5, -1.25, .5, 1.25)
        line(f, k.F_SilkS, (-1.0, -1.5), (-.4, -1.5))
    elif name == 'FW6SMT':
        # IEEE 1394 6-pin right-angle SMT receptacle: Keystone 927TR mounting
        # detail and Assmann WSW drawing ASS 8005 CO (same land pattern).
        # Origin: midpoint of the two locating pegs. Drawn with the board
        # edge toward +y; pcb.py turns it so the mouth faces east.
        for n in range(1, 7):
            pad(f, n, -2.5 + (n - 1), -.05, .7, 2.5)
        for x in (-5.0, 5.0):
            pad(f, '', x, 0, 1.6, 1.6, 1.6, shape=k.PAD_SHAPE_CIRCLE, plated=False)
        for x in (-5.85, 5.85):
            pad(f, 'SH', x, 4.65, 1.8, 3.3, 1.0, slot=(1.0, 2.5))
        body = (-6.75, -1.6, 6.75, 8.5)
        line(f, k.F_SilkS, (-6.75, -1.6), (-6.75, 2.6)); line(f, k.F_SilkS, (6.75, -1.6), (6.75, 2.6))
        line(f, k.F_SilkS, (-6.75, -1.6), (-3.3, -1.6)); line(f, k.F_SilkS, (6.75, -1.6), (3.3, -1.6))
    elif name == 'MH3':
        f.SetAttributes(k.FP_EXCLUDE_FROM_POS_FILES | k.FP_EXCLUDE_FROM_BOM | k.FP_BOARD_ONLY)
        pad(f, '', 0, 0, 3.2, 3.2, 3.2, shape=k.PAD_SHAPE_CIRCLE, plated=False)
    else:
        raise ValueError(name)
    if body:
        box(f, k.F_Fab, *body, width=.1)
        box(f, k.F_CrtYd, body[0] - .15, body[1] - .15, body[2] + .15, body[3] + .15, width=.05)
    if silk:
        box(f, k.F_SilkS, *silk)
    f.Reference().SetVisible(False)
    f.Value().SetVisible(False)
    return f


# ------------------------------------------------------------ board items
board = None
nets = {}
lengths = {}


def padpos(ref, number, index=0):
    fp = board.FindFootprintByReference(ref)
    found = [p for p in fp.Pads() if p.GetNumber() == str(number)]
    c = found[index].GetPosition()
    return (k.ToMM(c.x) - ORIGIN[0], k.ToMM(c.y) - ORIGIN[1])


def near(a, b, tol=2e-3):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def T(net, pts, layer=F, w=W_SIG):
    """Track through the listed points; returns its length."""
    total = 0
    for a, b in zip(pts, pts[1:]):
        if near(a, b, 1e-6):
            continue
        t = k.PCB_TRACK(board)
        t.SetStart(P(*a)); t.SetEnd(P(*b)); t.SetWidth(mm(w)); t.SetLayer(layer); t.SetNet(nets[net])
        board.Add(t)
        total += math.dist(a, b)
    lengths[net] = lengths.get(net, 0) + total
    return total


def V(net, x, y, size=VIA):
    v = k.PCB_VIA(board)
    v.SetPosition(P(x, y)); v.SetViaType(k.VIATYPE_THROUGH); v.SetLayerPair(F, B)
    v.SetWidth(mm(size[0])); v.SetDrill(mm(size[1])); v.SetNet(nets[net])
    board.Add(v)
    return (x, y)


def offset(pts, d):
    """Parallel copy of a polyline, d to the left of the direction of travel
    (which is north for a line running east, because y points south)."""
    out = []
    normals = []
    for a, b in zip(pts, pts[1:]):
        n = math.dist(a, b)
        normals.append(((b[1] - a[1]) / n, -(b[0] - a[0]) / n))
    for i, p in enumerate(pts):
        if i == 0:
            n = normals[0]; out.append((p[0] + d * n[0], p[1] + d * n[1]))
        elif i == len(pts) - 1:
            n = normals[-1]; out.append((p[0] + d * n[0], p[1] + d * n[1]))
        else:
            n1, n2 = normals[i - 1], normals[i]
            c = 1 + n1[0] * n2[0] + n1[1] * n2[1]
            out.append((p[0] + d * (n1[0] + n2[0]) / c, p[1] + d * (n1[1] + n2[1]) / c))
    return out


def with_stops(pts, xs):
    """Add vertices at the given x positions on horizontal runs, so a track
    that passes through a pad has an end point inside it."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if abs(a[1] - b[1]) < 1e-9:
            for x in sorted(xs, reverse=a[0] > b[0]):
                if min(a[0], b[0]) + 1e-6 < x < max(a[0], b[0]) - 1e-6:
                    out.append((x, a[1]))
        out.append(b)
    return out


def place():
    for p in parts:
        fp = footprint(p['foot'])
        fp.SetReference(p['ref']); fp.SetValue(p['value'])
        fp.SetPath(k.KIID_PATH('/' + uid(p['ref'])))
        k.PCB_IO_KICAD_SEXPR().FootprintSave(str(ROOT / 'fw2usb.pretty'), fp)
        board.Add(fp)
        net_by_pad = {pin[0]: pin[2] for pin in p['pins']}
        for pad_ in fp.Pads():
            name = net_by_pad.get(pad_.GetNumber())
            if name:
                pad_.SetNet(nets[name])
        want = p.get('pads') or p.get('check')
        if 'pads' in p:
            a, b = p['pads']['1'], p['pads']['2']
            centre = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        else:
            centre = p['xy']
        fp.SetPosition(P(*centre))
        if p.get('side') == 'B':
            fp.Flip(P(*centre), False)
        # Find the rotation that puts the named pads where the design says.
        for rot in (0, 90, 180, 270):
            fp.SetOrientationDegrees(rot)
            if all(near(padpos(p['ref'], n), xy) for n, xy in want.items()):
                break
        else:
            raise RuntimeError('cannot orient ' + p['ref'])
        # Assembly-drawing reference on the fabrication layer.
        ref = fp.Reference()
        ref.SetLayer(k.B_Fab if p.get('side') == 'B' else k.F_Fab)
        ref.SetVisible(True)
        small = p['foot'] in ('R', 'C', 'R0603', 'C0603', 'USON10')
        ref.SetTextSize(L(.4, .4) if small else L(.8, .8))
        ref.SetTextThickness(mm(.06 if small else .12))
        ref.SetPosition(P(*centre))
        ref.SetTextAngleDegrees(0)
    for i, (x, y) in enumerate(HOLES):
        fp = footprint('MH3'); fp.SetReference('H%d' % (i + 1)); fp.SetValue('M3')
        k.PCB_IO_KICAD_SEXPR().FootprintSave(str(ROOT / 'fw2usb.pretty'), fp)
        fp.SetPosition(P(x, y)); board.Add(fp)


# ------------------------------------------------------------ routing
def side_point(number, r):
    """Point at distance r from the U1 centre on the axis of a U1 pin."""
    x, y = u1_pad(number)
    side = (number - 1) // 20
    return [(-r, y), (x, r), (r, y), (x, -r)][side]


def rt(number, r, t):
    """Point given as (distance from centre, position along the side) for the
    side that the U1 pin is on."""
    side = (number - 1) // 20
    return [(-r, t), (t, r), (r, t), (t, -r)][side]


def tangent(number):
    x, y = u1_pad(number)
    return y if ((number - 1) // 20) % 2 == 0 else x


def route_u1_ground():
    """Ground pins and tie-low inputs go straight to the thermal pad on the
    top layer (SLLSFA1 section 13.2.9); the pad has a via field to ground."""
    for n in range(1, 81):
        if u1_net(n) != 'GND':
            continue
        t = tangent(n)
        over = abs(t) - 2.9
        if over <= 0:
            pts = [u1_pad(n), rt(n, 2.8, t)]
        else:
            s = 1 if t > 0 else -1
            pts = [u1_pad(n), rt(n, 3.05 + over, t), rt(n, 3.05, s * 2.9), rt(n, 2.8, s * 2.9)]
        T('GND', pts)
    for i in range(5):
        for j in range(5):
            V('GND', -2.4 + i * 1.2, -2.4 + j * 1.2, VIA_TH)


# Supply pins: a via just inside the pin row, then the capacitor on the back.
SUPPLY_VIAS = {  # U1 pins -> position of the via along the side
    (6,): -2.25, (8,): -1.25, (18,): 3.75, (24,): -3.25, (29, 30): -0.5, (31,): 0.35, (37,): 3.25,
    (39,): 4.25, (44,): 3.25, (51,): -0.25, (57,): -3.25, (63,): 3.75, (65,): 2.75, (69, 70): 0.5,
    (71,): -0.25}
RV = 5.5  # distance of those vias from the U1 centre


def route_u1_supply():
    via_at = {}
    for pins, t in SUPPLY_VIAS.items():
        net = u1_net(pins[0])
        v = rt(pins[0], RV, t)
        V(net, *v)
        for n in pins:
            T(net, [u1_pad(n), side_point(n, 6.05), v], w=0.25)
        via_at[pins[0]] = v
    cap = {ref: inner(side, t) for ref, value, net, side, t, mpn in DECOUPLING}

    def b(net, *pts):
        T(net, list(pts), B, 0.3)
    b('3V3', via_at[6], cap['C8'][0])
    b('DVDD_CORE', via_at[8], cap['C9'][0], cap['C10'][0])
    b('3V3', via_at[18], cap['C11'][0])
    b('3V3', via_at[24], cap['C12'][0], cap['C13'][0])
    b('PLLVDD_CORE', via_at[29], cap['C15'][0], cap['C14'][0])
    b('PLLVDD_CORE', via_at[29], (-0.5, 6.3))
    b('3V3', via_at[31], cap['C16'][0], cap['C17'][0], cap['C18'][0])
    b('DVDD_CORE', via_at[37], cap['C19'][0])
    b('3V3', via_at[39], cap['C20'][0])
    b('3V3', via_at[44], cap['C21'][0], cap['C22'][0], cap['C23'][0], cap['C24'][0], via_at[51])
    b('3V3', via_at[57], cap['C26'][0], cap['C25'][0])
    b('3V3', via_at[63], cap['C27'][0])
    b('DVDD_CORE', via_at[65], cap['C28'][0])
    b('3V3', via_at[69], cap['C30'][0], cap['C29'][0])
    b('DVDD_CORE', via_at[71], cap['C31'][0])
    V('GND', -0.5, 8.2); b('GND', (-0.5, 7.4), (-0.5, 8.2))
    # Digital core rail: joins its four pins as a track on the 3.3 V plane
    # layer, running between the thermal vias and the supply vias.
    ring = 4.3
    T('DVDD_CORE', [via_at[8], (-ring, -1.25), (-ring, -ring), (ring, -ring), (ring, ring), (3.25, ring),
                    via_at[37]], IN2, W_PWR)
    T('DVDD_CORE', [(-0.25, -ring), via_at[71]], IN2, W_PWR)
    T('DVDD_CORE', [(2.75, -ring), via_at[65]], IN2, W_PWR)


def route_bus():
    """PHY-LINK bus on the top layer, no vias: U1 west side, a 45 degree fan
    to the 1.27 mm slot pitch, series resistor, header."""
    # U1 pin, net at the PHY, x where the 45 degree leg starts
    fan = [(2, 'S5_LKON', 'LKON_H', -9.4), (3, 'LREQ', 'LREQ_H', -9.5), (5, 'PCLK', 'SCLK_H', -9.2),
           (9, 'CTL0', 'CTL0_H', -8.5), (10, 'CTL1', 'CTL1_H', -8.7), (11, 'D0', 'D0_H', -8.9),
           (12, 'D1', 'D1_H', -8.8), (13, 'D2', 'D2_H', -8.7), (15, 'D3', 'D3_H', -8.7), (16, 'D4', 'D4_H', -8.6),
           (17, 'D5', 'D5_H', -8.5), (19, 'D6', 'D6_H', -8.5), (20, 'D7', 'D7_H', -8.3)]
    report = []
    for pin, net, hnet, xb in fan:
        ys, yt = u1_pad(pin)[1], slot_y(hnet)
        pts = [u1_pad(pin), (xb, ys), (xb - abs(yt - ys), yt), (RCOL[0], yt)]
        if pin == 2:
            pts = with_stops(pts, [-8.9])  # R1 strap resistor sits on this run
        a = T(net, pts)
        report.append((hnet, a, header_side(hnet)))
    T('S5_LKON', [(-8.9, -4.25), padpos('R1', 1)])
    T('GND', [padpos('R1', 2), V('GND', -8.9, -6.4)])
    # LPS and RESET leave the north side of U1 and turn west above the fan.
    y = slot_y('LPS_H')
    a = T('LPS', [u1_pad(80), (-4.75, -8.2), (-4.75 - (-8.2 - y), y), (RCOL[0], y)])
    report.append(('LPS_H', a, header_side('LPS_H')))
    T('GND', [padpos('R20', 2), V('GND', -19.0, y - 1.1)])
    y = slot_y('RESET_N')
    T('RESET_N', [u1_pad(75), padpos('C5', 1), (-2.25, -11.5), (-2.25 - (-11.5 - y), y), (J2_X + 2.54, y)])
    T('GND', [padpos('C5', 2), V('GND', -0.3, -8.6)])
    return report


def header_side(hnet):
    """Series resistor (or R20 for LPS) to the header pin."""
    kslot = SLOTS.index(hnet)
    y = slot_y(hnet)
    pin = slot_pin(kslot)
    start = [(RCOL[1], y)]
    if hnet == 'LPS_H':
        start.append((-18.0, y))
    if kslot % 2 == 0:   # east column: straight in
        return T(hnet, start + [(J2_X + 2.54, y)])
    # west column: pass between two east-column pads, then 45 degrees up
    return T(hnet, start + [(J2_X + 1.27, y), (J2_X, y - 1.27)])


def route_straps():
    def strap(pin, ref, mid, net2, via):
        net = PINS[pin]
        T(net, [u1_pad(pin)] + mid + [padpos(ref, 1)])
        T(net2, [padpos(ref, 2), V(net2, *via)])
    # north side
    strap(78, 'R7', [(-3.75, -7.8), (-3.45, -8.1)], '3V3', (-3.45, -10.5))
    strap(79, 'R8', [], '3V3', (-5.15, -11.7))
    T('S0_PC2', [u1_pad(68), (1.25, -7.8), (0.75, -8.3), padpos('R6', 1)])
    T('S1_PC1', [u1_pad(67), padpos('R5', 1)])
    T('S2_PC0', [u1_pad(66), (2.25, -7.8), (2.75, -8.3), padpos('R4', 1)])
    T('GND', [padpos('R6', 2), padpos('R5', 2), padpos('R4', 2)])
    T('GND', [padpos('R5', 2), V('GND', 1.75, -10.7)])
    # south side: three straps leave as parallel 45 degree legs
    strap(32, 'R2', [(0.75, 7.75), (2.3, 9.3)], '3V3', (2.3, 12.3))
    strap(33, 'R3', [(1.25, 7.75), (3.4, 9.9)], 'GND', (3.4, 12.6))
    strap(34, 'R9', [(1.75, 7.75), (4.5, 10.5)], 'GND', (4.5, 13.0))
    # current-setting resistor between R1 (pin 22) and R0 (pin 23)
    T('R1', [u1_pad(22), (-4.25, 7.9), (-4.55, 8.2), padpos('R13', 1)])
    T('R0', [u1_pad(23), (-3.75, 7.9), (-3.45, 8.2), padpos('R13', 2)])


def route_crystal():
    T('XI', [u1_pad(27), (-1.75, 8.9), (-1.2, 9.45), padpos('Y1', 3), padpos('C6', 1)])
    T('XO', [u1_pad(26), (-2.25, 10.6), (-2.9, 11.25), padpos('Y1', 1), padpos('C7', 1)])
    T('GND', [padpos('C7', 2), (-3.8, 9.8), padpos('Y1', 4)])
    T('GND', [padpos('C7', 2), V('GND', -4.3, 9.45)])
    T('GND', [padpos('C6', 2), V('GND', 1.45, 10.7)])
    T('GND', [padpos('Y1', 2), V('GND', -0.9, 12.4)])


def route_port():
    """Port 2 pairs: U1 east side, termination, ESD array, connector. Top
    layer only, over unbroken ground on In1. 0.22 mm lines, 0.28 mm gap."""
    stops = [9.8, 11.2, 13.815, 14.585]
    out = {}
    for name, yc, step in (('TPA2', -4.0, -1), ('TPB2', -2.5, 1)):
        # centre line: spread for the termination resistors, back to the pin
        # pitch for the ESD array, then out to suit the connector pads
        centre = [(6.8, yc), (8.2, yc), (8.65, yc + .45 * step), (12.7, yc + .45 * step), (13.15, yc),
                  (15.0, yc), (15.25, yc + .25 * step), (16.6, yc + .25 * step)]
        for sign, d in (('+', .25), ('-', -.25)):
            pts = offset(centre, d)
            pts[0] = u1_pad({'TPA2+': 59, 'TPA2-': 58, 'TPB2+': 56, 'TPB2-': 55}[name + sign])
            ye = pts[-1][1] - d
            pts += [(16.85, ye), (J1_X - .05, ye)]
            assert near(pts[-1], padpos('J1', {'TPA2+': 6, 'TPA2-': 5, 'TPB2+': 4, 'TPB2-': 3}[name + sign]))
            out[name + sign] = T(name + sign, with_stops(pts, stops), w=W_TP)
    # termination stubs: the pad sits on the line, the track gets an end in it
    for ref, net in (('R15', 'TPA2+'), ('R14', 'TPA2-'), ('R17', 'TPB2+'), ('R16', 'TPB2-')):
        x, y = padpos(ref, 1)
        line_y = {'TPA2+': -4.70, 'TPA2-': -4.20, 'TPB2+': -2.30, 'TPB2-': -1.80}[net]
        T(net, [(x, line_y), (x, y)], w=W_TP)
    # TPBIAS: pin 60, 1 uF, the TPA resistors (one reached on the back)
    T('TPBIAS2', [u1_pad(60), (7.9, -4.75), (8.6, -5.45), padpos('C2', 1), padpos('R15', 2),
                  V('TPBIAS2', 10.9, -5.9)])
    T('TPBIAS2', [(10.9, -5.9), (12.1, -3.0)], B, 0.3)
    T('TPBIAS2', [padpos('R14', 2), V('TPBIAS2', 12.1, -3.0)])
    T('GND', [padpos('C2', 2), V('GND', 8.6, -7.9)])
    # TPB common-mode node
    T('TPB_CM', [padpos('R17', 2), V('TPB_CM', 8.95, -3.5)])
    T('TPB_CM', [(8.95, -3.5), (8.95, -1.85), (10.2, -0.6)], B, 0.3)
    T('TPB_CM', [V('TPB_CM', 10.2, -0.6), padpos('R16', 2), padpos('R18', 1)])
    T('TPB_CM', [padpos('R16', 2), padpos('C1', 1)])
    T('GND', [padpos('R18', 2), V('GND', 14.3, -0.6)])
    T('GND', [padpos('C1', 2), V('GND', 11.2, 2.5)])
    # ESD array ground and the cable ground pin
    T('GND', [padpos('U2', 3), padpos('U2', 8), V('GND', 16.0, -3.25)])
    T('GND', [padpos('J1', 2), V('GND', 16.9, J1_Y + 1.5)], w=W_PWR)
    # Shield: both shell tabs, then 1 Mohm, 10 nF and 1 nF to ground
    north, south = sorted([padpos('J1', 'SH', 0), padpos('J1', 'SH', 1)], key=lambda p: p[1])
    T('SHIELD', [north, (25.5, north[1]), (25.5, south[1]), south], B, W_PWR)
    T('SHIELD', [south, (23.35, 5.2), (22.9, 5.65), padpos('C4', 1), padpos('C3', 1), padpos('R19', 1)], w=W_PWR)
    for ref in ('R19', 'C3', 'C4'):
        x, y = padpos(ref, 2)
        T('GND', [(x, y), V('GND', x, y + 1.0)], w=W_PWR)
    return out


def route_power():
    T('3V3', [padpos('J3', 1), padpos('C33', 1)], w=0.5)
    T('GND', [padpos('J3', 2), padpos('C33', 2)], w=0.5)
    for n, net in ((1, '3V3'), (2, 'GND')):
        x, y = padpos('C34', n)
        T(net, [(x, y), V(net, x, y - 1.2)], w=W_PWR)
        V(net, x + (.6 if n == 2 else -.6), y - 1.2)
        T(net, [(x, y - 1.2), (x + (.6 if n == 2 else -.6), y - 1.2)], w=W_PWR)


def zone(net, layer, clearance=0.2):
    z = k.ZONE(board)
    z.SetLayer(layer); z.SetNet(nets[net])
    w, n, e, s = OUTLINE
    o = z.Outline(); o.NewOutline()
    for x, y in ((w, n), (e, n), (e, s), (w, s)):
        o.Append(P(x, y))
    z.SetPadConnection(k.ZONE_CONNECTION_FULL)
    z.SetLocalClearance(mm(clearance)); z.SetMinThickness(mm(0.2))
    z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(0)
    board.Add(z)


def text(s, x, y, size=0.8, layer=k.F_SilkS, angle=0):
    t = k.PCB_TEXT(board)
    t.SetText(s); t.SetPosition(P(x, y)); t.SetLayer(layer)
    t.SetTextSize(L(size, size)); t.SetTextThickness(mm(size * .15)); t.SetTextAngleDegrees(angle)
    if layer in (k.B_SilkS, k.B_Fab):
        t.SetMirrored(True)
    board.Add(t)


def write_project():
    """Put the design rules and net classes into the project file that KiCad
    wrote next to the board, keeping the rest of what KiCad wrote."""
    pro = ROOT / 'phy-breakout.kicad_pro'
    d = json.loads(pro.read_text())
    d['board']['design_settings']['rules'].update(RULES)
    default = d['net_settings']['classes'][0]
    default.update(NETCLASS)
    d['net_settings']['classes'] = [default, dict(default, name='TP', track_width=W_TP)]
    d['net_settings']['netclass_patterns'] = [{'netclass': 'TP', 'pattern': TP_PATTERN}]
    pro.write_text(json.dumps(d, indent=2, sort_keys=True) + '\n')
    prl = ROOT / 'phy-breakout.kicad_prl'
    if prl.exists():
        prl.unlink()


def main():
    global board
    (ROOT / 'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "fw2usb") (type "KiCad") '
                                       '(uri "${KIPRJMOD}/fw2usb.pretty") (options "") (descr "Original footprints")))\n')
    for old in (ROOT / 'fw2usb.pretty').glob('*.kicad_mod'):
        old.unlink()
    board = k.BOARD()
    board.SetCopperLayerCount(4)
    for name in sorted({pin[2] for p in parts for pin in p['pins'] if pin[2]}):
        net = k.NETINFO_ITEM(board, '/' + name); board.Add(net); nets[name] = net
    place()
    route_u1_ground()
    route_u1_supply()
    bus = route_bus()
    route_straps()
    route_crystal()
    pairs = route_port()
    route_power()
    w, n, e, s = OUTLINE
    for a, b in [((w, n), (e, n)), ((e, n), (e, s)), ((e, s), (w, s)), ((w, s), (w, n))]:
        ln = k.PCB_SHAPE(board); ln.SetShape(k.SHAPE_T_SEGMENT); ln.SetStart(P(*a)); ln.SetEnd(P(*b))
        ln.SetLayer(k.Edge_Cuts); ln.SetWidth(mm(.1)); board.Add(ln)
    zone('GND', IN1); zone('3V3', IN2); zone('GND', B)
    # Silkscreen: what a person wiring or probing the board needs.
    text('fw2usb PHY breakout r%s' % REV, -12.0, 14.2, 1.0)
    text('CERN-OHL-S-2.0', 17.0, 14.3, 0.8)
    text('J2', J2_X + 1.27, J2_Y - 2.3); text('1', J2_X - 1.9, J2_Y)
    text('3V3', 6.4, 9.9); text('GND', 6.4, 12.44); text('J3', 9.0, 14.6)
    text('J1 FW400', 13.5, 5.6); text('U1', -7.0, -9.0); text('Y1', -6.3, 12.6)
    path = str(ROOT / 'phy-breakout.kicad_pcb')
    k.SaveBoard(path, board)
    write_project()
    # Fill the zones on a freshly loaded copy, so that the filler works with
    # the project rules and built connectivity, then save again.
    loaded = k.LoadBoard(path)
    k.ZONE_FILLER(loaded).Fill(loaded.Zones())
    k.SaveBoard(path, loaded)
    write_project()
    with (ROOT / 'reports' / 'lengths.txt').open('w') as f:
        f.write('Routed lengths in mm, from pcb.py. Delay uses 6.9 ps/mm (outer layer, FR-4).\n\n')
        f.write('PHY-LINK bus: U1 pin to series resistor, resistor to header pin, total\n')
        totals = []
        for net, a, b in bus:
            totals.append(a + b + 1.1)
            f.write('  %-8s %6.2f %6.2f %6.2f\n' % (net, a, b, a + b + 1.1))
        spread = max(totals) - min(totals)
        f.write('  spread %.2f mm = %.0f ps\n\n' % (spread, spread * 6.9))
        f.write('Port 2 pairs: U1 pin to connector pad\n')
        for name in ('TPA2', 'TPB2'):
            p_, n_ = pairs[name + '+'], pairs[name + '-']
            f.write('  %s+ %.3f  %s- %.3f  skew %.3f mm = %.1f ps\n' % (name, p_, name, n_, abs(p_ - n_),
                                                                       abs(p_ - n_) * 6.9))
    print('placed %d parts, %d tracks and vias' % (len(parts), len(board.GetTracks())))


if __name__ == '__main__':
    main()
