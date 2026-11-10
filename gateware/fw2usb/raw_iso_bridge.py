"""Validated SCLK ISO -> FW2R record -> asynchronous USB byte stream.
One retained ISO packet, 1025-byte CDC FIFO. Generation resets must coordinate
both domains externally before reconnecting USB/session; no bitwise bus sync.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Signal
from amaranth.lib.fifo import AsyncFIFOBuffered
from fw2usb.iso import IsoAudioReceiver
from fw2usb.tunnel import FrameEncoder


class RawIsoBridge(Elaboratable):
    def __init__(self,*,dbs=2,capacity=512):
        self.iso=IsoAudioReceiver(dbs=dbs,capacity=capacity)
        self.generation=Signal(32)
        self.handle=Signal(32,init=1)
        self.cycle_time=Signal(32)
        self.ticks=Signal(64)
        self.bulk_valid=Signal();self.bulk_ready=Signal();self.bulk_byte=Signal(8);self.bulk_last=Signal()
        self.sequence=Signal(32)

    def elaborate(self,platform):
        m=Module();m.submodules.iso=self.iso;m.submodules.encoder=encoder=FrameEncoder()
        m.submodules.fifo=fifo=AsyncFIFOBuffered(width=9,depth=1025,w_domain='sync',r_domain='usb')
        metadata=Signal(256);index=Signal(6)
        m.d.comb += [encoder.start.eq(self.iso.payload_start),encoder.kind.eq(2),encoder.opcode.eq(0x201),encoder.id.eq(0),
                     encoder.generation.eq(self.generation),encoder.length.eq(32+self.iso.payload_length),
                     encoder.valid.eq((index<32)|self.iso.payload_valid),
                     encoder.byte.eq(metadata >> (index<<3)),self.iso.payload_ready.eq((index>=32)&encoder.ready),
                     encoder.out_ready.eq(fifo.w_rdy),fifo.w_en.eq(encoder.out_valid),
                     fifo.w_data.eq(Cat(encoder.out_byte,encoder.out_last)),
                     self.bulk_valid.eq(fifo.r_rdy),self.bulk_byte.eq(fifo.r_data[:8]),self.bulk_last.eq(fifo.r_data[8]),
                     fifo.r_en.eq(self.bulk_ready)]
        with m.If(index>=32):m.d.comb += encoder.byte.eq(self.iso.payload_byte)
        with m.If(self.iso.payload_start):
            m.d.sync += [index.eq(0),metadata.eq(Cat(self.handle,self.generation,self.sequence,self.cycle_time,self.ticks,
                                                   self.iso.payload_length,Const(0,16),self.iso.channel,Const(0,2),
                                                   Const(1,8),Const(0,8),Const(3,8)))]
        with m.Elif(encoder.valid & encoder.ready & (index<32)):m.d.sync += index.eq(index+1)
        with m.If(encoder.out_valid & encoder.out_ready & encoder.out_last):m.d.sync += self.sequence.eq(self.sequence+1)
        return m
