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
from fw2usb.link import Crc32, CycleTimer, SelfIdCapture, AckDecision
from fw2usb.packet import PacketReceiver, PacketTransmitter
from fw2usb.cycle_master import CycleMaster
from fw2usb.link_layer import LinkLayer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='store_true')
    parser.add_argument('--core', choices=['smoke', 'lreq', 'status', 'receive', 'transmit', 'phy_link', 'crc32', 'cycle', 'selfid', 'packet_rx', 'packet_tx', 'ack', 'cycle_master', 'link_layer'], default='smoke')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = root / 'build'
    out.mkdir(exist_ok=True)
    if args.route and args.core != 'smoke':
        parser.error('only the safe smoke image has board IO constraints')
    constructors = {'smoke': Heartbeat, 'lreq': LreqSerializer,
                    'status': StatusReceiver, 'receive': ReceiveAdapter, 'transmit': TransmitAdapter, 'phy_link': PhyLink, 'crc32': Crc32, 'cycle': CycleTimer, 'selfid': SelfIdCapture, 'packet_rx': PacketReceiver, 'packet_tx': PacketTransmitter,
                    'ack': AckDecision, 'cycle_master': CycleMaster, 'link_layer': LinkLayer}
    port_names = {
        'packet_rx': ['start', 'valid', 'byte', 'end', 'phy_error', 'good', 'bad', 'header_good', 'tcode', 'length'],
        'packet_tx': ['start', 'has_data', 'valid', 'ready', 'byte', 'header_last', 'data_last',
                      'out_valid', 'out_ready', 'out_byte', 'out_last', 'busy'],
        'ack': ['end', 'addressed', 'broadcast', 'header_good', 'data_good', 'capacity', 'tcode', 'valid', 'byte'],
        'link_layer': ['selfid_phase', 'tx_valid', 'tx_ready', 'tx_byte', 'tx_last'],
        'cycle_master': ['node_id', 'grant', 'request', 'valid', 'ready', 'byte', 'last'],
        'crc32': ['clear', 'valid', 'byte', 'value', 'raw'],
        'cycle': ['load', 'load_value', 'value', 'root', 'enable',
                  'cycle_start_valid', 'cycle_start_ready', 'missed'],
        'selfid': ['start', 'valid', 'byte', 'end', 'packet', 'accept', 'error',
                   'physical_id', 'ports'],
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
    if args.core == 'link_layer':
        for interface, names in [(dut.phy, ['enable', 'bus_reset', 'ctl_in', 'data_in', 'ctl_out', 'data_out', 'oe', 'lreq']),
                                 (dut.request, ['valid', 'ready', 'kind', 'speed', 'address', 'data', 'accel']),
                                 (dut.packet, ['good', 'bad', 'header_good', 'tcode', 'length']),
                                 (dut.selfid, ['accept', 'error', 'packet', 'physical_id']),
                                 (dut.cycle, ['node_id']),
                                 (dut.cycle.timer, ['root', 'enable', 'load', 'load_value', 'value', 'missed'])]:
            ports.extend(getattr(interface, name) for name in names)
    if args.core == 'cycle_master':
        ports.extend(getattr(dut.timer, name) for name in ['root', 'enable', 'value', 'load', 'load_value', 'missed'])
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
