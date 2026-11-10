"""Bounded SCLK async transaction responder, validated wire RX -> CSR -> wire TX.
One request at a time, at most64 payload quadlets. Atomicity is per CSR quadlet;
block writes are sequential and may report an error after a committed prefix.
"""
from types import SimpleNamespace
from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, ResetInserter, Signal
from fw2usb.packet import PacketReceiver, PacketTransmitter
from fw2usb.transaction import CsrBank


class TransactionResponder(Elaboratable):
    def __init__(self, *, capacity=64):
        self.capacity = capacity
        self.rx = SimpleNamespace(start=Signal(),valid=Signal(),byte=Signal(8),end=Signal(),phy_error=Signal())
        self.csr = CsrBank()
        self.bus_reset = Signal()
        self.node_id = Signal(16,init=0xffc0)
        self.tx_valid = Signal()
        self.tx_ready = Signal()
        self.tx_byte = Signal(8)
        self.tx_last = Signal()
        self.busy = Signal()
        self.dropped = Signal(32)

    def elaborate(self, platform):
        m = Module()
        rx = PacketReceiver()
        m.submodules.rx = ResetInserter(self.bus_reset)(rx)
        m.submodules.csr = self.csr
        tx = PacketTransmitter()
        m.submodules.tx = ResetInserter(self.bus_reset)(tx)
        accept_rx = Signal()
        m.d.comb += [rx.start.eq(self.rx.start & ~self.busy),
                     rx.valid.eq(self.rx.valid & accept_rx),rx.end.eq(self.rx.end & accept_rx),
                     rx.byte.eq(self.rx.byte),rx.phy_error.eq(self.rx.phy_error),
                     self.csr.bus_reset.eq(self.bus_reset)]
        with m.If(self.rx.start):
            m.d.sync += accept_rx.eq(~self.busy)
        with m.Elif(self.rx.end):
            m.d.sync += accept_rx.eq(0)
        headers = Array(Signal(32,name=f'request_header{i}') for i in range(4))
        payload = Array(Signal(32,name=f'request_word{i}') for i in range(self.capacity))
        result = Array(Signal(32,name=f'response_word{i}') for i in range(self.capacity))
        count = Signal(18)
        tcode = Signal(4)
        response_tcode = Signal(4)
        label = Signal(6)
        source = Signal(16)
        address = Signal(48)
        words = Signal(range(self.capacity+1))
        index = Signal(range(self.capacity))
        rcode = Signal(4)
        response_length = Signal(16)
        header_length = Signal(5)
        send_index = Signal(17)
        response_q = Array([Cat(Const(0,4),response_tcode,Const(0,2),label,source),
                            Cat(Const(0,12),rcode,self.node_id),Const(0,32),
                            Mux(response_tcode == 6,result[0],
                                Cat(Mux(response_tcode == 11,Const(2,16),Const(0,16)),response_length))])
        header_byte = Signal(8)
        data_byte = Signal(8)
        m.d.comb += [header_byte.eq(response_q[send_index[2:4]] >> ((~send_index[:2]) << 3)),
                     data_byte.eq(result[(send_index-header_length) >> 2] >> ((~send_index[:2]) << 3)),
                     self.tx_valid.eq(tx.out_valid),self.tx_byte.eq(tx.out_byte),self.tx_last.eq(tx.out_last),
                     tx.out_ready.eq(self.tx_ready),tx.valid.eq(1),
                     tx.byte.eq(Mux(send_index < header_length,header_byte,data_byte)),
                     tx.header_last.eq(send_index == header_length-1),
                     tx.data_last.eq(send_index == header_length+response_length-1),
                     tx.has_data.eq((response_tcode == 7) | (response_tcode == 11)),
                     self.csr.address.eq(address),self.csr.data.eq(Mux(tcode == 0,headers[3],Mux(tcode == 9,payload[1],payload[index]))),
                     self.csr.compare.eq(payload[0]),self.csr.write.eq((tcode == 0) | (tcode == 1)),
                     self.csr.compare_swap.eq(tcode == 9)]
        # Caller supplies only complete frames when !busy. A frame started while
        # busy increments dropped; production FIFO/credits must prevent this.
        with m.If(self.rx.start):
            with m.If(self.busy):
                m.d.sync += self.dropped.eq(self.dropped+1)
            with m.Else():
                m.d.sync += count.eq(0)
        with m.Elif(self.rx.valid & ~self.busy & accept_rx):
            with m.If(count < 16):
                m.d.sync += headers[count[2:4]].eq(Cat(self.rx.byte,headers[count[2:4]][:24]))
            with m.Elif((count >= 20) & (count < 20+self.capacity*4)):
                word = (count-20) >> 2
                m.d.sync += payload[word].eq(Cat(self.rx.byte,payload[word][:24]))
            m.d.sync += count.eq(count+1)
        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing('IDLE'))
            with m.State('IDLE'):
                with m.If(rx.good & (headers[0][16:32] == self.node_id) &
                          ((rx.tcode == 0) | (rx.tcode == 1) | (rx.tcode == 4) | (rx.tcode == 5) | (rx.tcode == 9))):
                    m.d.sync += [tcode.eq(rx.tcode),source.eq(headers[1][16:32]),
                                 label.eq(headers[0][10:16]),address.eq(Cat(headers[2],headers[1][:16])),
                                 index.eq(0),rcode.eq(0),response_length.eq(0),words.eq(1),result[0].eq(0)]
                    with m.Switch(rx.tcode):
                        with m.Case(0,1):
                            m.d.sync += [response_tcode.eq(2),header_length.eq(12)]
                        with m.Case(4):
                            m.d.sync += [response_tcode.eq(6),header_length.eq(16)]
                        with m.Case(5):
                            m.d.sync += [response_tcode.eq(7),header_length.eq(16)]
                        with m.Case(9):
                            m.d.sync += [response_tcode.eq(11),header_length.eq(16)]
                        with m.Default():
                            m.d.sync += rcode.eq(6)
                    m.next = 'VALIDATE'
            with m.State('VALIDATE'):
                with m.If((tcode == 1) | (tcode == 5)):
                    with m.If((headers[3][16:32] == 0) | (headers[3][16:32] > self.capacity*4) |
                              (headers[3][16:18] != 0)):
                        m.d.sync += rcode.eq(6)
                        m.next = 'REPLY'
                    with m.Else():
                        m.d.sync += words.eq(headers[3][18:32])
                        m.next = 'ISSUE'
                with m.Elif((tcode == 9) & (headers[3] != 0x00080002)):
                    m.d.sync += rcode.eq(6)
                    m.next = 'REPLY'
                with m.Elif(rcode != 0):
                    m.next = 'REPLY'
                with m.Else():
                    m.next = 'ISSUE'
            with m.State('ISSUE'):
                m.d.comb += self.csr.valid.eq(1)
                with m.If(self.csr.ready):
                    m.next = 'RESULT'
            with m.State('RESULT'):
                m.d.comb += self.csr.response_ready.eq(1)
                with m.If(self.csr.response_valid):
                    m.d.sync += [result[index].eq(self.csr.response_data),rcode.eq(self.csr.rcode)]
                    with m.If(self.csr.rcode != 0):
                        m.next = 'REPLY'
                    with m.Elif(index+1 == words):
                        with m.If((tcode == 5) | (tcode == 9)):
                            m.d.sync += response_length.eq(words << 2)
                        m.next = 'REPLY'
                    with m.Else():
                        m.d.sync += [index.eq(index+1),address.eq(address+4)]
                        m.next = 'ISSUE'
            with m.State('REPLY'):
                # Error block responses have no payload, per IEEE response rules.
                m.d.sync += send_index.eq(0)
                m.d.comb += [tx.start.eq(1),tx.has_data.eq(((response_tcode == 7) | (response_tcode == 11)) & (response_length != 0))]
                m.next = 'SEND'
            with m.State('SEND'):
                with m.If(tx.ready):
                    m.d.sync += send_index.eq(send_index+1)
                with m.If(tx.out_valid & self.tx_ready & tx.out_last):
                    m.next = 'IDLE'
        with m.If(self.bus_reset):
            m.d.sync += [fsm.state.eq(fsm.encoding['IDLE']),accept_rx.eq(0)]
        return m
