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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='store_true')
    parser.add_argument('--core', choices=['smoke', 'lreq', 'status', 'receive', 'transmit'], default='smoke')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = root / 'build'
    out.mkdir(exist_ok=True)
    if args.route and args.core != 'smoke':
        parser.error('only the safe smoke image has board IO constraints')
    constructors = {'smoke': Heartbeat, 'lreq': LreqSerializer,
                    'status': StatusReceiver, 'receive': ReceiveAdapter, 'transmit': TransmitAdapter}
    port_names = {
        'smoke': ['led'],
        'lreq': ['valid', 'ready', 'kind', 'speed', 'address', 'data', 'accel', 'lreq'],
        'status': ['ctl', 'pair', 'flags', 'flags_valid', 'flags_mask',
                   'address', 'data', 'register_valid'],
        'transmit': ['grant', 'speed', 'valid', 'ready', 'byte', 'last',
                     'ctl', 'data', 'oe', 'done', 'underrun'],
        'receive': ['ctl', 'data', 'byte', 'valid', 'start', 'end', 'error', 'speed'],
    }
    dut = constructors[args.core]()
    ports = [getattr(dut, name) for name in port_names[args.core]]
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
