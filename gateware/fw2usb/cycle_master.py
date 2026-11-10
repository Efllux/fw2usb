"""Cycle-start packet source. Root qualification via CycleTimer enable/root.
Grant is external priority arbitration; timestamp snapshots at grant. Actual
PHY transmit latency compensation remains a separately documented timing gap.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Signal
from fw2usb.link import CycleTimer
from fw2usb.packet import PacketTransmitter


class CycleMaster(Elaboratable):
    def __init__(self):
        self.timer = CycleTimer()
        self.node_id = Signal(16, init=0xffc0)
        self.grant = Signal()
        self.request = Signal()
        self.valid = Signal()
        self.ready = Signal()
        self.byte = Signal(8)
        self.last = Signal()

    def elaborate(self, platform):
        m = Module()
        m.submodules.timer = self.timer
        m.submodules.packet = packet = PacketTransmitter()
        timestamp = Signal(32)
        node_id = Signal(16)
        index = Signal(range(16))
        start = Signal()
        header = Array([Const(255, 8), Const(255, 8), Const(0, 8), Const(0x8f, 8),
                        node_id[8:16], node_id[:8], Const(255, 8), Const(255, 8),
                        Const(0xf0, 8), Const(0, 8), Const(2, 8), Const(0, 8),
                        timestamp[24:32], timestamp[16:24], timestamp[8:16], timestamp[:8]])
        m.d.comb += [self.request.eq(self.timer.cycle_start_valid & ~packet.busy & (self.timer.value[:12] >= 17)),
                     start.eq(self.request & self.grant),
                     self.timer.cycle_start_ready.eq(start), packet.start.eq(start),
                     packet.has_data.eq(0), packet.valid.eq(1), packet.byte.eq(header[index]),
                     packet.header_last.eq(index == 15), packet.out_ready.eq(self.ready),
                     self.valid.eq(packet.out_valid), self.byte.eq(packet.out_byte),
                     self.last.eq(packet.out_last)]
        with m.If(start):
            m.d.sync += [timestamp.eq(self.timer.value), node_id.eq(self.node_id), index.eq(0)]
        with m.Elif(packet.ready & (index < 15)):
            m.d.sync += index.eq(index + 1)
        return m
