"""Streaming packet validation, IEEE1394-2008 §6.2 packet layouts.
Bytes are provisional until good; downstream must buffer/commit by packet epoch.
No backpressure on RX. Self-ID/PHY and ACK packets use separate receivers.
"""
from amaranth import Cat, Elaboratable, Module, Mux, Signal
from fw2usb.link import Crc32


class PacketReceiver(Elaboratable):
    """good/bad pulse in the cycle after ``end``. ``good_now``/``bad_now`` are
    the same decision, combinational during the ``end`` cycle, built from
    flags registered as the bytes arrive so the immediate-ACK path stays short.
    """
    def __init__(self):
        self.start = Signal()
        self.valid = Signal()
        self.byte = Signal(8)
        self.end = Signal()
        self.phy_error = Signal()
        self.good = Signal()
        self.bad = Signal()
        self.good_now = Signal()
        self.bad_now = Signal()
        self.header_good = Signal()
        self.tcode = Signal(4)
        self.length = Signal(16)
        self.destination = Signal(16)
        self.header_decoded = Signal()

    def elaborate(self, platform):
        m = Module()
        m.submodules.header_crc = hcrc = Crc32()
        m.submodules.data_crc = dcrc = Crc32()
        # The packet is walked as header, header CRC, padded data, data CRC.
        # ``left`` counts the bytes still expected in the current section, so
        # no comparison against a computed total length is needed.
        HEADER, HEADER_CRC, DATA, DATA_CRC, COMPLETE, EXCESS = range(6)
        section = Signal(3)
        position = Signal(4)
        long_header = Signal()
        left = Signal(17)
        has_data = Signal()
        data_length = Signal(16)
        padded = Signal(17)
        received = Signal(32)
        invalid = Signal()
        active = Signal()
        hvalid = Signal()
        data_ok = Signal()
        header_last = Signal()
        value = Signal(32)
        m.d.comb += [padded.eq((data_length + 3) & 0x1fffc),
                     hcrc.clear.eq(self.start), dcrc.clear.eq(self.start),
                     hcrc.valid.eq(active & self.valid & (section == HEADER)),
                     dcrc.valid.eq(active & self.valid & (section == DATA)),
                     hcrc.byte.eq(self.byte), dcrc.byte.eq(self.byte),
                     value.eq(Cat(self.byte, received[:24])),
                     header_last.eq(((position == 3) & (self.byte[4:8] == 10)) |
                                    ((position == 11) & ~long_header) | (position == 15)),
                     self.good_now.eq(active & self.end & ~invalid & ~self.phy_error & hvalid &
                                      (section == COMPLETE) & data_ok),
                     self.bad_now.eq(active & self.end & ~self.good_now)]
        m.d.sync += [self.good.eq(0), self.bad.eq(0), self.header_decoded.eq(0)]
        with m.If(self.start):
            m.d.sync += [section.eq(HEADER), position.eq(0), long_header.eq(0), has_data.eq(0),
                         data_length.eq(0), invalid.eq(0), active.eq(1), hvalid.eq(0),
                         data_ok.eq(0), self.header_good.eq(0), received.eq(0)]
        with m.Elif(active):
            with m.If(self.phy_error):
                m.d.sync += invalid.eq(1)
            with m.If(self.valid):
                with m.Switch(section):
                    with m.Case(HEADER):
                        m.d.sync += position.eq(position + 1)
                        with m.If(position == 0):
                            m.d.sync += [data_length[8:16].eq(self.byte), self.destination[8:16].eq(self.byte)]
                        with m.If(position == 1):
                            m.d.sync += [data_length[:8].eq(self.byte), self.destination[:8].eq(self.byte)]
                        with m.If(position == 3):
                            m.d.sync += [self.tcode.eq(self.byte[4:8]), self.header_decoded.eq(1)]
                            with m.Switch(self.byte[4:8]):
                                with m.Case(10):
                                    m.d.sync += has_data.eq(1)
                                with m.Case(0, 5, 6, 8):
                                    m.d.sync += [long_header.eq(1), data_length.eq(0)]
                                with m.Case(1, 7, 9, 11):
                                    m.d.sync += [long_header.eq(1), has_data.eq(1), data_length.eq(0)]
                                with m.Case(2, 4):
                                    m.d.sync += data_length.eq(0)
                                with m.Default():
                                    m.d.sync += invalid.eq(1)
                        with m.If(has_data & (self.tcode != 10)):
                            with m.If(position == 12):
                                m.d.sync += data_length[8:16].eq(self.byte)
                            with m.If(position == 13):
                                m.d.sync += data_length[:8].eq(self.byte)
                        with m.If(header_last):
                            m.d.sync += [section.eq(HEADER_CRC), left.eq(3)]
                    with m.Case(HEADER_CRC):
                        m.d.sync += [received.eq(value), left.eq(left - 1)]
                        with m.If(left == 0):
                            m.d.sync += [hvalid.eq(value == hcrc.value), self.header_good.eq(value == hcrc.value),
                                         received.eq(0)]
                            with m.If(has_data & (data_length != 0)):
                                m.d.sync += [section.eq(DATA), left.eq(padded - 1)]
                            with m.Else():
                                m.d.sync += [section.eq(COMPLETE), data_ok.eq(1)]
                    with m.Case(DATA):
                        m.d.sync += left.eq(left - 1)
                        with m.If(left == 0):
                            m.d.sync += [section.eq(DATA_CRC), left.eq(3)]
                    with m.Case(DATA_CRC):
                        m.d.sync += [received.eq(value), left.eq(left - 1)]
                        with m.If(left == 0):
                            m.d.sync += [section.eq(COMPLETE), data_ok.eq(value == dcrc.value)]
                    with m.Default():
                        m.d.sync += section.eq(EXCESS)
            with m.If(self.end):
                m.d.sync += [self.good.eq(self.good_now), self.bad.eq(~self.good_now), active.eq(0),
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
