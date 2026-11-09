"""Profile-bounded ISO audio framing with CRC commit before PCM delivery."""
from types import SimpleNamespace
from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, Signal, unsigned
from amaranth.lib.memory import Memory
from fw2usb.amdtp import AmdtpReceiver, AmdtpTransmitter
from fw2usb.packet import PacketReceiver, PacketTransmitter


class IsoAudioReceiver(Elaboratable):
    def __init__(self, *, dbs=2, capacity=512):
        self.dbs,self.capacity=dbs,capacity
        self.rx=SimpleNamespace(start=Signal(),valid=Signal(),byte=Signal(8),end=Signal(),phy_error=Signal())
        self.channel=Signal(6)
        self.sample=Signal(24)
        self.sample_channel=Signal(8)
        self.sample_valid=Signal()
        self.sample_ready=Signal(init=1)
        self.syt=Signal(16)
        self.done=Signal()
        self.error=Signal()
        self.busy=Signal()
        self.losses=Signal(32)
        self.dbc_gap=Signal()

    def elaborate(self, platform):
        m=Module()
        m.submodules.validator=validator=PacketReceiver()
        m.submodules.codec=codec=AmdtpReceiver()
        m.submodules.memory=memory=Memory(shape=unsigned(8),depth=self.capacity,init=[])
        wp=memory.write_port(); rp=memory.read_port()
        accept=Signal(); count=Signal(18); selected=Signal(); invalid=Signal()
        length=Signal(16); read_index=Signal(range(self.capacity))
        m.d.comb += [validator.start.eq(self.rx.start & ~self.busy),validator.valid.eq(self.rx.valid & accept),
                     validator.byte.eq(self.rx.byte),validator.end.eq(self.rx.end & accept),validator.phy_error.eq(self.rx.phy_error),
                     wp.en.eq(self.rx.valid & accept & (count>=8) & (count<8+self.capacity)),
                     wp.addr.eq(count-8),wp.data.eq(self.rx.byte),rp.addr.eq(read_index),rp.en.eq(1),
                     codec.byte.eq(rp.data),self.sample.eq(codec.sample),self.sample_channel.eq(codec.channel),
                     self.sample_valid.eq(codec.sample_valid),self.syt.eq(codec.syt),self.dbc_gap.eq(codec.dbc_gap)]
        m.d.sync += [self.done.eq(0),self.error.eq(0)]
        with m.If(codec.sample_valid & ~self.sample_ready):
            m.d.sync += self.losses.eq(self.losses+1)
        with m.If(self.rx.start):
            m.d.sync += [accept.eq(~self.busy),count.eq(0),invalid.eq(0),selected.eq(0)]
            with m.If(self.busy):
                m.d.sync += self.losses.eq(self.losses+1)
        with m.Elif(self.rx.end):
            m.d.sync += accept.eq(0)
        with m.If(self.rx.valid & accept):
            m.d.sync += count.eq(count+1)
            with m.Switch(count):
                with m.Case(2):
                    m.d.sync += selected.eq((self.rx.byte[:6]==self.channel) & (self.rx.byte[6:8]==1))
                with m.Case(8):
                    with m.If(self.rx.byte[6:8] != 0):m.d.sync += invalid.eq(1)
                with m.Case(9):
                    with m.If(self.rx.byte != self.dbs):m.d.sync += invalid.eq(1)
                with m.Case(10):
                    with m.If(self.rx.byte != 0):m.d.sync += invalid.eq(1)
                with m.Case(12):
                    with m.If(self.rx.byte != 0x90):m.d.sync += invalid.eq(1)
                with m.Case(13):
                    with m.If((self.rx.byte>6) & (self.rx.byte!=255)):m.d.sync += invalid.eq(1)
        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing('IDLE'))
            with m.State('IDLE'):
                with m.If(validator.bad):m.d.sync += self.error.eq(1)
                with m.If(validator.good & (validator.tcode==10) & selected):
                    with m.If(invalid | (validator.length<8) | (validator.length>self.capacity) |
                              ((validator.length-8) % (self.dbs*4) != 0)):
                        m.d.sync += self.error.eq(1)
                    with m.Else():
                        m.d.sync += [length.eq(validator.length),read_index.eq(0)]
                        m.next='START'
            with m.State('START'):
                m.d.comb += codec.start.eq(1)
                m.next='WAIT'
            with m.State('WAIT'):
                m.next='BYTE'
            with m.State('BYTE'):
                m.d.comb += codec.valid.eq(1)
                with m.If(read_index+1==length):m.next='END'
                with m.Else():
                    m.d.sync += read_index.eq(read_index+1)
                    m.next='WAIT'
            with m.State('END'):
                m.d.comb += codec.end.eq(1)
                m.next='DONE'
            with m.State('DONE'):
                m.d.sync += [self.done.eq(1),self.error.eq(codec.error)]
                m.next='IDLE'
        return m


class IsoAudioTransmitter(Elaboratable):
    def __init__(self):
        self.codec=AmdtpTransmitter()
        self.start=Signal()
        self.channel=Signal(6)
        self.valid=Signal(); self.ready=Signal(); self.byte=Signal(8); self.last=Signal()

    def elaborate(self, platform):
        m=Module()
        m.submodules.codec=self.codec
        m.submodules.packet=packet=PacketTransmitter()
        header=Signal(32); index=Signal(3)
        m.d.comb += [packet.start.eq(self.start),self.codec.start.eq(self.start),packet.has_data.eq(1),
                     packet.valid.eq(Mux(index<4,1,self.codec.valid)),
                     packet.byte.eq(Mux(index<4,header >> ((3-index[:2]).as_unsigned()<<3),self.codec.byte)),
                     packet.header_last.eq(index==3),packet.data_last.eq(self.codec.last),
                     self.codec.ready.eq(packet.ready & (index>=4)),
                     packet.out_ready.eq(self.ready),self.valid.eq(packet.out_valid),
                     self.byte.eq(packet.out_byte),self.last.eq(packet.out_last)]
        with m.If(self.start):
            m.d.sync += [index.eq(0),header.eq(Cat(Const(0xa0,8),self.channel,Const(1,2),
                                                (8+self.codec.frames*self.codec.dbs*4)[:16]))]
        with m.Elif(packet.ready & (index<4)):
            m.d.sync += index.eq(index+1)
        return m
