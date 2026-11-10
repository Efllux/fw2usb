"""Bounded async request wire encoder, IEEE1394 §6.2.2."""
from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, Signal
from fw2usb.packet import PacketTransmitter


class AsyncRequestEncoder(Elaboratable):
    def __init__(self):
        self.start=Signal();self.destination=Signal(16);self.source=Signal(16);self.label=Signal(6)
        self.tcode=Signal(4);self.address=Signal(48);self.length=Signal(16);self.extended=Signal(16)
        self.quadlet=Signal(32);self.data_index=Signal(16);self.data_byte=Signal(8)
        self.valid=Signal();self.ready=Signal();self.byte=Signal(8);self.last=Signal()

    def elaborate(self,platform):
        m=Module();m.submodules.packet=packet=PacketTransmitter();index=Signal(17);hlen=Signal(5)
        words=Array([Cat(Const(0,4),self.tcode,Const(1,2),self.label,self.destination),
                     Cat(self.address[32:48],self.source),self.address[:32],
                     Mux(self.tcode==0,self.quadlet,Cat(self.extended,self.length))])
        m.d.comb += [hlen.eq(Mux(self.tcode==4,12,16)),packet.start.eq(self.start),
                     packet.has_data.eq(((self.tcode==1)|(self.tcode==9))&(self.length!=0)),
                     packet.valid.eq(1),packet.byte.eq(words[index[2:4]] >> ((~index[:2])<<3)),
                     packet.header_last.eq(index==hlen-1),packet.data_last.eq(index==hlen+self.length-1),
                     self.data_index.eq(index-hlen),packet.out_ready.eq(self.ready),
                     self.valid.eq(packet.out_valid),self.byte.eq(packet.out_byte),self.last.eq(packet.out_last)]
        with m.If(index>=hlen):m.d.comb += packet.byte.eq(self.data_byte)
        with m.If(self.start):m.d.sync += index.eq(0)
        with m.Elif(packet.ready):m.d.sync += index.eq(index+1)
        return m
