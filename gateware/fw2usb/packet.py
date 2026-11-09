"""Streaming packet validation, IEEE1394-2008 §6.2 packet layouts.
Bytes are provisional until good; downstream must buffer/commit by packet epoch.
No backpressure on RX. Self-ID/PHY and ACK packets use separate receivers.
"""
from amaranth import Cat, Elaboratable, Module, Mux, Signal
from fw2usb.link import Crc32


class PacketReceiver(Elaboratable):
    def __init__(self):
        self.start = Signal()
        self.valid = Signal()
        self.byte = Signal(8)
        self.end = Signal()
        self.phy_error = Signal()
        self.good = Signal()
        self.bad = Signal()
        self.header_good = Signal()
        self.tcode = Signal(4)
        self.length = Signal(16)

    def elaborate(self, platform):
        m = Module()
        m.submodules.header_crc = hcrc = Crc32()
        m.submodules.data_crc = dcrc = Crc32()
        count = Signal(17)
        hlen = Signal(5, init=12)
        has_data = Signal()
        data_length = Signal(16)
        padded = Signal(17)
        received_hcrc = Signal(32)
        received_dcrc = Signal(32)
        invalid = Signal()
        active = Signal()
        hvalid = Signal()
        data_start = Signal(6)
        expected = Signal(18)
        m.d.comb += [padded.eq((data_length + 3) & 0x1fffc), data_start.eq(hlen + 4),
                     expected.eq(hlen + 4 + Mux(has_data & (data_length != 0), padded + 4, 0)),
                     hcrc.clear.eq(self.start), dcrc.clear.eq(self.start),
                     hcrc.valid.eq(active & self.valid & (count < hlen)),
                     dcrc.valid.eq(active & self.valid & has_data & (count >= data_start) &
                                   (count < data_start + padded)),
                     hcrc.byte.eq(self.byte), dcrc.byte.eq(self.byte)]
        m.d.sync += [self.good.eq(0), self.bad.eq(0)]
        with m.If(self.start):
            m.d.sync += [count.eq(0), hlen.eq(12), has_data.eq(0), data_length.eq(0),
                         invalid.eq(0), active.eq(1), hvalid.eq(0), self.header_good.eq(0),
                         received_hcrc.eq(0), received_dcrc.eq(0)]
        with m.Elif(active):
            with m.If(self.phy_error):
                m.d.sync += invalid.eq(1)
            with m.If(self.valid):
                with m.If(count < 0x1ffff):
                    m.d.sync += count.eq(count + 1)
                with m.Else():
                    m.d.sync += invalid.eq(1)
                with m.If(count == 0):
                    m.d.sync += data_length[8:16].eq(self.byte)
                with m.If(count == 1):
                    m.d.sync += data_length[:8].eq(self.byte)
                with m.If(count == 3):
                    m.d.sync += self.tcode.eq(self.byte[4:8])
                    with m.Switch(self.byte[4:8]):
                        with m.Case(10):
                            m.d.sync += [hlen.eq(4), has_data.eq(1)]
                        with m.Case(0, 5, 6, 8):
                            m.d.sync += [hlen.eq(16), data_length.eq(0)]
                        with m.Case(1, 7, 9, 11):
                            m.d.sync += [hlen.eq(16), has_data.eq(1), data_length.eq(0)]
                        with m.Case(2, 4):
                            m.d.sync += [hlen.eq(12), data_length.eq(0)]
                        with m.Default():
                            m.d.sync += invalid.eq(1)
                with m.If(has_data & (self.tcode != 10)):
                    with m.If(count == 12):
                        m.d.sync += data_length[8:16].eq(self.byte)
                    with m.If(count == 13):
                        m.d.sync += data_length[:8].eq(self.byte)
                with m.If((count >= hlen) & (count < data_start)):
                    value = Cat(self.byte, received_hcrc[:24])
                    m.d.sync += received_hcrc.eq(value)
                    with m.If(count == data_start - 1):
                        m.d.sync += hvalid.eq(value == hcrc.value)
                with m.If(count >= data_start + padded):
                    m.d.sync += received_dcrc.eq(Cat(self.byte, received_dcrc[:24]))
            with m.If(self.end):
                good = (~invalid & ~self.phy_error & hvalid & (count == expected) &
                        (~has_data | (data_length == 0) | (received_dcrc == dcrc.value)))
                m.d.sync += [self.good.eq(good), self.bad.eq(~good), active.eq(0),
                             self.header_good.eq(hvalid), self.length.eq(data_length)]
        return m


class PacketTransmitter(Elaboratable):
    """Insert separate header/data CRCs and zero pad data to quadlet boundary.

    Source marks header_last/data_last. has_data is latched on start; false for
    zero-data ISO. Output can backpressure before a prebuffered PHY TX launch.
    """
    def __init__(self):
        self.start = Signal()
        self.has_data = Signal()
        self.valid = Signal()
        self.ready = Signal()
        self.byte = Signal(8)
        self.header_last = Signal()
        self.data_last = Signal()
        self.out_valid = Signal()
        self.out_ready = Signal()
        self.out_byte = Signal(8)
        self.out_last = Signal()
        self.busy = Signal()

    def elaborate(self, platform):
        m = Module()
        m.submodules.crc = crc = Crc32()
        data = Signal()
        lane = Signal(2)
        crc_lane = Signal(2)
        m.d.comb += crc.clear.eq(self.start)
        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing('IDLE'))
            with m.State('IDLE'):
                with m.If(self.start):
                    m.d.sync += [data.eq(self.has_data), lane.eq(0)]
                    m.next = 'HEADER'
            with m.State('HEADER'):
                m.d.comb += [self.out_valid.eq(self.valid), self.out_byte.eq(self.byte),
                             self.ready.eq(self.out_ready), crc.byte.eq(self.byte),
                             crc.valid.eq(self.valid & self.out_ready)]
                with m.If(self.valid & self.out_ready & self.header_last):
                    m.d.sync += crc_lane.eq(3)
                    m.next = 'HEADER_CRC'
            with m.State('HEADER_CRC'):
                m.d.comb += [self.out_valid.eq(1), self.out_byte.eq(crc.value >> (crc_lane << 3)),
                             self.out_last.eq((crc_lane == 0) & ~data)]
                with m.If(self.out_ready):
                    with m.If(crc_lane == 0):
                        m.d.comb += crc.clear.eq(1)
                        with m.If(data):
                            m.next = 'DATA'
                        with m.Else():
                            m.next = 'IDLE'
                    with m.Else():
                        m.d.sync += crc_lane.eq(crc_lane - 1)
            with m.State('DATA'):
                m.d.comb += [self.out_valid.eq(self.valid), self.out_byte.eq(self.byte),
                             self.ready.eq(self.out_ready), crc.byte.eq(self.byte),
                             crc.valid.eq(self.valid & self.out_ready)]
                with m.If(self.valid & self.out_ready):
                    m.d.sync += lane.eq(lane + 1)
                    with m.If(self.data_last):
                        with m.If(lane == 3):
                            m.d.sync += crc_lane.eq(3)
                            m.next = 'DATA_CRC'
                        with m.Else():
                            m.next = 'PAD'
            with m.State('PAD'):
                m.d.comb += [self.out_valid.eq(1), self.out_byte.eq(0),
                             crc.valid.eq(self.out_ready), crc.byte.eq(0)]
                with m.If(self.out_ready):
                    m.d.sync += lane.eq(lane + 1)
                    with m.If(lane == 3):
                        m.d.sync += crc_lane.eq(3)
                        m.next = 'DATA_CRC'
            with m.State('DATA_CRC'):
                m.d.comb += [self.out_valid.eq(1), self.out_byte.eq(crc.value >> (crc_lane << 3)),
                             self.out_last.eq(crc_lane == 0)]
                with m.If(self.out_ready):
                    with m.If(crc_lane == 0):
                        m.next = 'IDLE'
                    with m.Else():
                        m.d.sync += crc_lane.eq(crc_lane - 1)
        return m
