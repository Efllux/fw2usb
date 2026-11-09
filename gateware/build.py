"""Emit RTLIL, synthesize ECP5 and optionally route the safe board smoke design."""
import argparse
from pathlib import Path
import subprocess
from amaranth.back import rtlil
from fw2usb.smoke import Heartbeat
from fw2usb.lreq import LreqSerializer
from fw2usb.status import StatusReceiver
from fw2usb.receive import ReceiveAdapter
from fw2usb.transmit import TransmitAdapter
from fw2usb.phy_link import PhyLink


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='store_true')
    parser.add_argument('--core', choices=['smoke', 'lreq', 'status', 'receive', 'transmit', 'phy_link'], default='smoke')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = root / 'build'
    out.mkdir(exist_ok=True)
    if args.route and args.core != 'smoke':
        parser.error('only the safe smoke image has board IO constraints')
    constructors = {'smoke': Heartbeat, 'lreq': LreqSerializer,
                    'status': StatusReceiver, 'receive': ReceiveAdapter, 'transmit': TransmitAdapter, 'phy_link': PhyLink}
    port_names = {
        'phy_link': ['enable', 'bus_reset', 'ctl_in', 'data_in', 'ctl_out',
                     'data_out', 'oe', 'lreq', 'pending', 'read_pending'],
        'smoke': ['led'],
        'lreq': ['valid', 'ready', 'kind', 'speed', 'address', 'data', 'accel', 'lreq'],
        'status': ['ctl', 'pair', 'flags', 'flags_valid', 'flags_mask',
                   'address', 'data', 'register_valid'],
        'transmit': ['grant', 'speed', 'allow_hold', 'valid', 'ready', 'byte', 'last',
                     'ctl', 'data', 'oe', 'done', 'underrun', 'concatenate',
                     'next_speed', 'multispeed', 'config_error'],
        'receive': ['ctl', 'data', 'byte', 'valid', 'start', 'end', 'error', 'speed'],
    }
    dut = constructors[args.core]()
    ports = [getattr(dut, name) for name in port_names[args.core]]
    if args.core == 'phy_link':
        for interface, names in [(dut.request, ['valid', 'ready', 'kind', 'speed', 'address', 'data', 'accel']),
                                 (dut.tx, ['valid', 'ready', 'byte', 'last', 'allow_hold', 'multispeed',
                                           'concatenate', 'next_speed', 'done', 'underrun', 'config_error']),
                                 (dut.rx, ['byte', 'valid', 'start', 'end', 'error', 'speed']),
                                 (dut.status, ['flags', 'flags_valid', 'flags_mask', 'address', 'data', 'register_valid'])]:
            ports.extend(getattr(interface, name) for name in names)
    (out / f'{args.core}.il').write_text(rtlil.convert(dut, name=args.core, ports=ports))
    subprocess.run(['yosys', '-p',
                    f'read_rtlil {args.core}.il; synth_ecp5 -top {args.core} -json {args.core}.json; check -assert'],
                   cwd=out, check=True)
    if args.route:
        subprocess.run(['nextpnr-ecp5', '--85k', '--package', 'CABGA381', '--speed', '6',
                        '--json', 'smoke.json', '--lpf', str(root / 'boards/ulx3s-smoke.lpf'),
                        '--textcfg', 'smoke.config', '--freq', '25', '--seed', '1'],
                       cwd=out, check=True)
        subprocess.run(['ecppack', 'smoke.config', 'smoke.bit'], cwd=out, check=True)


if __name__ == '__main__':
    main()
