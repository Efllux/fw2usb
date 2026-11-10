"""Opaque ISO packet source: retained external payload -> wire header/CRCs.
The caller owns payload retention, admission, channel lease and cycle deadline.
Start is accepted only while idle; metadata is latched before backpressured TX.
"""
from amaranth import Cat,Const,Elaboratable,Module,Mux,Signal
from fw2usb.packet import PacketTransmitter


class RawIsoTransmitter(Elaboratable):
    def __init__(self, *, capacity=4096):
        self.capacity=capacity;self.error=Signal()
        self.start=Signal();self.channel=Signal(6);self.tag=Signal(2);self.sy=Signal(4);self.length=Signal(16)
        self.data_index=Signal(16);self.data_byte=Signal(8)
        self.valid=Signal();self.ready=Signal();self.byte=Signal(8);self.last=Signal();self.busy=Signal();self.done=Signal()

    def elaborate(self,p):
        m=Module();m.submodules.packet=packet=PacketTransmitter()
        header=Signal(32);index=Signal(17);length=Signal(16)
        m.d.comb += [packet.start.eq(self.start & ~self.busy & (self.length<=self.capacity)),packet.has_data.eq(self.length!=0),
                     packet.valid.eq(1),packet.byte.eq(Mux(index<4,header >> ((3-index[:2]).as_unsigned()<<3),self.data_byte)),
                     packet.header_last.eq(index==3),packet.data_last.eq(index==length+3),self.data_index.eq(Mux(index>=4,index-4,0)),
                     self.valid.eq(packet.out_valid),self.byte.eq(packet.out_byte),self.last.eq(packet.out_last),packet.out_ready.eq(self.ready)]
        m.d.sync += [self.done.eq(0),self.error.eq(0)]
        with m.If(self.start & ~self.busy & (self.length>self.capacity)):
            m.d.sync += [self.error.eq(1),self.done.eq(1)]
        with m.Elif(self.start & ~self.busy):
            m.d.sync += [header.eq(Cat(self.sy,Const(10,4),self.channel,self.tag,self.length)),length.eq(self.length),index.eq(0),self.busy.eq(1)]
        with m.Elif(packet.ready):m.d.sync += index.eq(index+1)
        with m.If(self.valid & self.ready & self.last):m.d.sync += [self.busy.eq(0),self.done.eq(1)]
        return m


class IsoTxWindow(Elaboratable):
    """Cycle-scoped admission, modulo128seconds, maximum forward horizon64s.
    Target offset must be zero. Reserve a conservative PHY serialization budget
    plus64 bus ticks; this is bridge policy, not a claimed IEEE timing constant.
    """
    def __init__(self):
        self.now=Signal(32);self.target=Signal(32);self.length=Signal(16);self.speed=Signal(2)
        self.valid=Signal();self.future=Signal();self.open=Signal();self.late=Signal()
    def elaborate(self,p):
        m=Module();current=Signal(20);target=Signal(20);distance=Signal(20);budget=Signal(20)
        m.d.comb += [current.eq(self.now[25:32]*8000+self.now[12:25]),target.eq(self.target[25:32]*8000+self.target[12:25]),
                     distance.eq(Mux(target>=current,target-current,target+1024000-current)),
                     budget.eq(Mux(self.speed==0,(self.length+12)*4,Mux(self.speed==1,(self.length+12)*2,self.length+12))+64),
                     self.valid.eq((self.now[12:25]<8000)&(self.now[:12]<3072)&(self.target[12:25]<8000)&(self.target[:12]==0)&(self.speed<3)&(self.length<=256)),
                     self.future.eq(self.valid & (distance!=0)&(distance<512000)),
                     self.open.eq(self.valid & (distance==0)&(self.now[:12]+budget<3072)),
                     self.late.eq(self.valid & ~self.future & ~self.open)]
        return m
