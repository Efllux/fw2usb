"""Emit RTLIL, synthesize ECP5 and optionally route the safe board smoke design."""
import argparse
from pathlib import Path
import subprocess
from amaranth.back import rtlil
from fw2usb.smoke import Heartbeat
from fw2usb.lreq import LreqSerializer
from fw2usb.status import StatusReceiver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='store_true')
    parser.add_argument('--core', choices=['smoke', 'lreq', 'status'], default='smoke')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = root / 'build'
    out.mkdir(exist_ok=True)
    if args.route and args.core != 'smoke':
        parser.error('only the safe smoke image has board IO constraints')
    dut = {'smoke': Heartbeat, 'lreq': LreqSerializer, 'status': StatusReceiver}[args.core]()
    ports = [dut.led] if args.core == 'smoke' else [
        dut.valid, dut.ready, dut.kind, dut.speed, dut.address,
        dut.data, dut.accel, dut.lreq] if args.core == 'lreq' else [
            dut.ctl, dut.pair, dut.flags, dut.flags_valid, dut.flags_mask,
            dut.address, dut.data, dut.register_valid]
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
