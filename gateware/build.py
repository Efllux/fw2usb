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
from fw2usb.transaction import CsrBank, RomReader
from fw2usb.responder import TransactionResponder
from fw2usb.transaction_link import TransactionLink
from fw2usb.amdtp import AmdtpReceiver, AmdtpTransmitter, SytEngine
from fw2usb.iso import IsoAudioReceiver, IsoAudioTransmitter
from fw2usb.usb_device import RawUsbDevice
from fw2usb.raw_iso_bridge import RawIsoBridge
from fw2usb.tunnel import FrameEncoder, FrameDecoder
from fw2usb.async_request import AsyncRequestEncoder
from fw2usb.raw_worker import RawWorker
from fw2usb.usb_bridge import RawUsbBridge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='store_true')
    parser.add_argument('--core', choices=['smoke', 'lreq', 'status', 'receive', 'transmit', 'phy_link', 'crc32', 'cycle', 'selfid', 'packet_rx', 'packet_tx', 'ack', 'cycle_master', 'link_layer', 'csr', 'rom_reader', 'transaction', 'transaction_link', 'amdtp_rx', 'amdtp_tx', 'syt', 'iso_rx', 'iso_tx', 'usb_raw', 'raw_iso', 'frame_encoder', 'frame_decoder', 'async_request', 'raw_worker', 'usb_bridge'], default='smoke')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = root / 'build'
    out.mkdir(exist_ok=True)
    if args.route and args.core != 'smoke':
        parser.error('only the safe smoke image has board IO constraints')
    constructors = {'smoke': Heartbeat, 'lreq': LreqSerializer,
                    'status': StatusReceiver, 'receive': ReceiveAdapter, 'transmit': TransmitAdapter, 'phy_link': PhyLink, 'crc32': Crc32, 'cycle': CycleTimer, 'selfid': SelfIdCapture, 'packet_rx': PacketReceiver, 'packet_tx': PacketTransmitter,
                    'ack': AckDecision, 'cycle_master': CycleMaster, 'link_layer': LinkLayer, 'csr': CsrBank, 'rom_reader': RomReader, 'transaction': TransactionResponder, 'transaction_link': TransactionLink, 'amdtp_rx': AmdtpReceiver, 'amdtp_tx': AmdtpTransmitter,
                    'syt': SytEngine, 'iso_rx': IsoAudioReceiver, 'iso_tx': IsoAudioTransmitter, 'usb_raw': RawUsbDevice, 'raw_iso': RawIsoBridge, 'frame_encoder': FrameEncoder, 'frame_decoder': FrameDecoder, 'async_request': AsyncRequestEncoder, 'raw_worker': RawWorker, 'usb_bridge': RawUsbBridge}
    port_names = {
        'packet_rx': ['start', 'valid', 'byte', 'end', 'phy_error', 'good', 'bad', 'header_good', 'tcode', 'length'],
        'packet_tx': ['start', 'has_data', 'valid', 'ready', 'byte', 'header_last', 'data_last',
                      'out_valid', 'out_ready', 'out_byte', 'out_last', 'busy'],
        'ack': ['end', 'addressed', 'broadcast', 'header_good', 'data_good', 'capacity', 'tcode', 'valid', 'byte'],
        'csr': ['valid', 'ready', 'address', 'write', 'compare_swap', 'compare', 'data',
                'response_valid', 'response_ready', 'response_data', 'rcode', 'bus_reset', 'cycle_time'],
        'rom_reader': ['start', 'bus_reset', 'local_node', 'remote_node', 'tx_valid', 'tx_ready', 'tx_byte',
                       'tx_last', 'response_valid', 'response_source', 'response_label', 'response_data',
                       'response_rcode', 'done', 'error', 'busy', 'length', 'read_index', 'read_data'],
        'async_request': ['start','destination','source','label','tcode','address','length','extended','quadlet','data_index','data_byte','valid','ready','byte','last'],
        'raw_worker': ['epoch_reset','session_reset','cycle_master_enable','generation','local_node','node_count','ready','iso_enabled','iso_handle','iso_channel','iso_losses','monotonic_ticks','out_valid','out_ready','out_byte','out_last'],
        'usb_bridge': [],
        'raw_iso': ['generation','handle','cycle_time','ticks','bulk_valid','bulk_ready','bulk_byte','bulk_last','sequence'],
        'frame_encoder': ['start','kind','opcode','id','status','generation','length','valid','ready','byte','out_valid','out_ready','out_byte','out_last','busy','error'],
        'frame_decoder': ['valid','ready','byte','reset','command_valid','command_ready','opcode','id','generation','length','halted','read_index','read_data'],
        'usb_raw': ['in_valid','in_ready','in_byte','in_last','out_valid','out_ready','out_byte','connect','clock','reset'],
        'amdtp_rx': ['start','valid','byte','end','sample_valid','sample','channel','frame','syt','dbc','dbs','error','dbc_gap'],
        'amdtp_tx': ['start','sid','dbs','dbc','fdf','syt','frames','sample','sample_valid','sample_ready','valid','ready','byte','last','busy'],
        'syt': ['cycle','advance','data','syt','fdf','frames'],
        'iso_rx': ['channel','sample','sample_channel','sample_valid','sample_ready','syt','done','error','busy','losses','dbc_gap'],
        'iso_tx': ['start','channel','valid','ready','byte','last'],
        'transaction_link': [],
        'transaction': ['node_id', 'bus_reset', 'tx_valid', 'tx_ready', 'tx_byte', 'tx_last', 'busy', 'dropped'],
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
    if args.core == 'raw_worker':
        ports.extend(getattr(dut.command,name) for name in ['valid','ready','byte','halted'])
        ports.extend(getattr(dut.link.phy,name) for name in ['enable','ctl_in','data_in','ctl_out','data_out','oe','lreq'])
    if args.core == 'usb_bridge':
        ports.extend([dut.usb.clock,dut.usb.reset,dut.usb.connect,dut.usb.ulpi.data.i,dut.usb.ulpi.data.o,dut.usb.ulpi.data.oe,dut.usb.ulpi.nxt.i,dut.usb.ulpi.stp.o,dut.usb.ulpi.dir.i,dut.usb.ulpi.rst.o])
        ports.extend(getattr(dut.worker.link.phy,name) for name in ['enable','ctl_in','data_in','ctl_out','data_out','oe','lreq'])
        ports.extend([dut.worker.epoch_reset,dut.worker.cycle_master_enable])
    if args.core == 'raw_iso':
        ports.extend(getattr(dut.iso.rx,name) for name in ['start','valid','byte','end','phy_error'])
        ports.extend([dut.iso.channel,dut.iso.error,dut.iso.losses])
    if args.core == 'usb_raw':
        ports.extend([dut.ulpi.data.i,dut.ulpi.data.o,dut.ulpi.data.oe,dut.ulpi.nxt.i,dut.ulpi.stp.o,dut.ulpi.dir.i,dut.ulpi.rst.o])
    if args.core == 'iso_rx':
        ports.extend(getattr(dut.rx,name) for name in ['start','valid','byte','end','phy_error'])
    if args.core == 'iso_tx':
        ports.extend(getattr(dut.codec,name) for name in ['sid','dbs','dbc','fdf','syt','frames','sample','sample_valid','sample_ready'])
    if args.core == 'transaction_link':
        ports.extend(getattr(dut.link.phy, name) for name in ['enable', 'bus_reset', 'ctl_in', 'data_in', 'ctl_out', 'data_out', 'oe', 'lreq'])
        ports.extend([dut.link.cycle.node_id, dut.link.selfid_phase])
        ports.extend(getattr(dut.link.cycle.timer, name) for name in ['root', 'enable', 'load', 'load_value', 'value'])
    if args.core == 'transaction':
        ports.extend(getattr(dut.rx, name) for name in ['start', 'valid', 'byte', 'end', 'phy_error'])
        ports.append(dut.csr.cycle_time)
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
