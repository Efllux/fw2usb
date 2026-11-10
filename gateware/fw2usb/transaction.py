"""Bounded hardware CSR/IRM engine and remote ROM reader.
Choice: gateware avoids a CPU/toolchain/firmware dependency for the small atomic
CSR surface. Packet validation/commit must precede local write requests.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, ResetInserter, Signal
from fw2usb.packet import PacketTransmitter


def rom_words():
    # Synthetic development identity; no registered production GUID claim.
    from fw2usb.rom import rom
    data = rom(0,1,1)
    return [int.from_bytes(data[i:i+4],'big') for i in range(0,len(data),4)]


class CsrBank(Elaboratable):
    def __init__(self, rom=None):
        self.rom = rom if rom is not None else rom_words()
        self.valid = Signal()
        self.ready = Signal()
        self.address = Signal(48)
        self.write = Signal()
        self.compare_swap = Signal()
        self.compare = Signal(32)
        self.data = Signal(32)
        self.response_valid = Signal()
        self.response_ready = Signal()
        self.response_data = Signal(32)
        self.rcode = Signal(4)
        self.bus_reset = Signal()
        self.cycle_time = Signal(32)
        self.cycle_write = Signal()
        self.cycle_data = Signal(32)
        self.output_channel = Signal(6)
        self.input_channel = Signal(6)
        self.connected = Signal()

    def elaborate(self, platform):
        m = Module()
        m.d.sync += self.cycle_write.eq(0)
        manager = Signal(32,init=63)
        bandwidth = Signal(32,init=4915)
        high = Signal(32,init=0xffffffff)
        low = Signal(32,init=0xffffffff)
        opcr = Signal(32,init=0x80000010)
        ipcr = Signal(32,init=0x80000010)
        m.d.comb += [self.output_channel.eq(opcr[16:22]),self.input_channel.eq(ipcr[16:22]),
                     self.connected.eq((opcr[24:30] != 0) & (ipcr[24:30] != 0))]
        m.d.comb += self.ready.eq((~self.response_valid | self.response_ready) & ~self.bus_reset)
        with m.If(self.response_ready):
            m.d.sync += self.response_valid.eq(0)
        with m.If(self.bus_reset):
            m.d.sync += [manager.eq(63),bandwidth.eq(4915),high.eq(0xffffffff),low.eq(0xffffffff),
                         self.response_valid.eq(0),opcr.eq(0x80000010),ipcr.eq(0x80000010)]
        with m.Elif(self.valid & self.ready):
            m.d.sync += [self.response_valid.eq(1),self.rcode.eq(0),self.response_data.eq(0)]
            with m.Switch(self.address):
                for address,register in [(0x21c,manager),(0x220,bandwidth),(0x224,high),(0x228,low),(0x904,opcr),(0x984,ipcr)]:
                    with m.Case(0xfffff0000000+address):
                        m.d.sync += self.response_data.eq(register)
                        with m.If(self.write | (self.compare_swap & (register == self.compare))):
                            m.d.sync += register.eq(self.data)
                with m.Case(0xfffff0000200):
                    m.d.sync += self.response_data.eq(self.cycle_time)
                    with m.If(self.compare_swap | (self.write & ((self.data[:12]>=3072)|(self.data[12:25]>=8000)))):
                        m.d.sync += self.rcode.eq(6)
                    with m.Elif(self.write):m.d.sync += [self.cycle_write.eq(1),self.cycle_data.eq(self.data)]
                for index,value in enumerate(self.rom):
                    with m.Case(0xfffff0000400+index*4):
                        m.d.sync += self.response_data.eq(value)
                        with m.If(self.write | self.compare_swap):
                            m.d.sync += self.rcode.eq(6)
                with m.Default():
                    m.d.sync += self.rcode.eq(7)
        return m


class RomReader(Elaboratable):
    """One outstanding quadlet read, source/label/rcode matching, bounded ROM.

    Header/data CRC validation is supplied by link PacketReceiver. Reads bus-info
    and root directory; nested unit/leaf traversal is controller work, not guessed.
    """
    def __init__(self, *, capacity=64, timeout_cycles=1_000_000):
        if not 2 <= capacity <= 64 or timeout_cycles < 2:
            raise ValueError('invalid reader bounds')
        self.capacity = capacity
        self.timeout_cycles = timeout_cycles
        self.start = Signal()
        self.bus_reset = Signal()
        self.local_node = Signal(16)
        self.remote_node = Signal(16)
        self.tx_valid = Signal()
        self.tx_ready = Signal()
        self.tx_byte = Signal(8)
        self.tx_last = Signal()
        self.response_valid = Signal()
        self.response_source = Signal(16)
        self.response_label = Signal(6)
        self.response_data = Signal(32)
        self.response_rcode = Signal(4)
        self.done = Signal()
        self.error = Signal()
        self.busy = Signal()
        self.length = Signal(range(capacity+1))
        self.read_index = Signal(range(capacity))
        self.read_data = Signal(32)

    def elaborate(self, platform):
        m = Module()
        packet = PacketTransmitter()
        m.submodules.packet = ResetInserter(self.bus_reset)(packet)
        memory = Array(Signal(32,name=f'rom_word{i}') for i in range(self.capacity))
        index = Signal(range(self.capacity))
        root = Signal(8)
        target = Signal(17)
        offset = Signal(32)
        byte_index = Signal(range(12))
        timeout = Signal(range(self.timeout_cycles+1))
        header = Array([self.remote_node[8:16],self.remote_node[:8],Cat(Const(1,2),index[:6]),Const(0x40,8),
                        self.local_node[8:16],self.local_node[:8],Const(255,8),Const(255,8),
                        offset[24:32],offset[16:24],offset[8:16],offset[:8]])
        # Quadlet0 has tl[15:10], retry[9:8]=01, tcode[7:4]=4.
        # byte2 = label<<2 | retry; Cat below uses exactly 8 bits.
        m.d.comb += [self.read_data.eq(memory[self.read_index]), offset.eq(0xf0000400+(index << 2)),
                     packet.byte.eq(header[byte_index]),packet.header_last.eq(byte_index == 11),
                     packet.valid.eq(1), packet.has_data.eq(0),packet.out_ready.eq(self.tx_ready),
                     self.tx_valid.eq(packet.out_valid),self.tx_byte.eq(packet.out_byte),self.tx_last.eq(packet.out_last)]
        m.d.sync += [self.done.eq(0),self.error.eq(0)]
        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing('IDLE'))
            with m.State('IDLE'):
                with m.If(self.start):
                    m.d.sync += [index.eq(0),root.eq(0),target.eq(1),self.length.eq(0)]
                    m.next = 'BEGIN'
            with m.State('BEGIN'):
                m.d.comb += packet.start.eq(1)
                m.d.sync += [byte_index.eq(0),timeout.eq(0)]
                m.next = 'SEND'
            with m.State('SEND'):
                with m.If(packet.ready & (byte_index < 11)):
                    m.d.sync += byte_index.eq(byte_index + 1)
                with m.If(packet.out_valid & self.tx_ready & packet.out_last):
                    m.next = 'WAIT'
            with m.State('WAIT'):
                m.d.sync += timeout.eq(timeout + 1)
                with m.If(self.response_valid & (self.response_source == self.remote_node) &
                          (self.response_label == index)):
                    with m.If(self.response_rcode != 0):
                        m.d.sync += self.error.eq(1)
                        m.next = 'IDLE'
                    with m.Else():
                        m.d.sync += [memory[index].eq(self.response_data),self.length.eq(index+1)]
                        with m.If(index == 0):
                            m.d.sync += [root.eq(self.response_data[24:32]+1),
                                         target.eq(self.response_data[24:32]+2)]
                        with m.If((index != 0) & (index == root)):
                            m.d.sync += target.eq(root + 1 + self.response_data[16:32])
                            with m.If(root + 1 + self.response_data[16:32] > self.capacity):
                                m.d.sync += self.error.eq(1)
                                m.next = 'IDLE'
                            with m.Elif(self.response_data[16:32] == 0):
                                m.d.sync += self.done.eq(1)
                                m.next = 'IDLE'
                            with m.Else():
                                m.d.sync += index.eq(index+1)
                                m.next = 'BEGIN'
                        with m.Elif((index != 0) & (index + 1 >= target)):
                            m.d.sync += self.done.eq(1)
                            m.next = 'IDLE'
                        with m.Elif(index == self.capacity-1):
                            m.d.sync += self.error.eq(1)
                            m.next = 'IDLE'
                        with m.Else():
                            m.d.sync += index.eq(index+1)
                            m.next = 'BEGIN'
                with m.Elif(timeout == self.timeout_cycles-1):
                    m.d.sync += self.error.eq(1)
                    m.next = 'IDLE'
        with m.If(self.bus_reset):
            m.d.sync += [self.error.eq(self.busy),fsm.state.eq(fsm.encoding['IDLE']),self.length.eq(0)]
        return m
