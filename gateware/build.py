"""Emit RTLIL, synthesize ECP5 and optionally route the safe board smoke design."""
import argparse
from pathlib import Path
import subprocess
from amaranth.back import rtlil
from fw2usb.smoke import Heartbeat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = root / 'build'
    out.mkdir(exist_ok=True)
    dut = Heartbeat()
    (out / 'smoke.il').write_text(rtlil.convert(dut, name='smoke', ports=[dut.led]))
    subprocess.run(['yosys', '-p',
                    'read_rtlil smoke.il; synth_ecp5 -top smoke -json smoke.json; check -assert'],
                   cwd=out, check=True)
    if args.route:
        subprocess.run(['nextpnr-ecp5', '--85k', '--package', 'CABGA381', '--speed', '6',
                        '--json', 'smoke.json', '--lpf', str(root / 'boards/ulx3s-smoke.lpf'),
                        '--textcfg', 'smoke.config', '--freq', '25', '--seed', '1'],
                       cwd=out, check=True)
        subprocess.run(['ecppack', 'smoke.config', 'smoke.bit'], cwd=out, check=True)


if __name__ == '__main__':
    main()
