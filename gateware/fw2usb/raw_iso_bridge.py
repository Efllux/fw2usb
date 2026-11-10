"""Validated SCLK ISO -> FW2R record -> asynchronous USB byte stream.
One retained ISO packet, 1025-byte CDC FIFO. Generation resets must coordinate
both domains externally before reconnecting USB/session; no bitwise bus sync.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Signal
from amaranth.lib.fifo import AsyncFIFOBuffered
from fw2usb.iso import IsoAudioReceiver
from fw2usb.tunnel import FrameEncoder


class RawIsoBridge(Elaboratable):
    def __init__(self,*,dbs=2,capacity=512,cdc=True,opaque=False):
        self.cdc=cdc
        self.iso=IsoAudioReceiver(dbs=dbs,capacity=capacity,validate_cip=not opaque)
        self.generation=Signal(32)
        self.handle=Signal(32,init=1)
        self.cycle_time=Signal(32)
        self.ticks=Signal(64)
        self.bulk_valid=Signal();self.bulk_ready=Signal();self.bulk_byte=Signal(8);self.bulk_last=Signal()
        self.sequence=Signal(32)
        self.errors=Signal(32)

    def elaborate(self,platform):
        m=Module();m.submodules.iso=self.iso;m.submodules.encoder=encoder=FrameEncoder()
        metadata=Signal(256);index=Signal(6)
        m.d.comb += [self.iso.release_ready.eq(~encoder.busy),encoder.start.eq(self.iso.payload_start),encoder.kind.eq(2),encoder.opcode.eq(0x201),encoder.id.eq(0),
                     encoder.generation.eq(self.generation),encoder.length.eq(32+self.iso.payload_length),
                     encoder.valid.eq((index<32)|self.iso.payload_valid),
                     encoder.byte.eq(metadata >> (index<<3)),self.iso.payload_ready.eq((index>=32)&encoder.ready),
                     ]
        if self.cdc:
            m.submodules.fifo=fifo=AsyncFIFOBuffered(width=9,depth=1025,w_domain='sync',r_domain='usb')
            m.d.comb += [encoder.out_ready.eq(fifo.w_rdy),fifo.w_en.eq(encoder.out_valid),
                         fifo.w_data.eq(Cat(encoder.out_byte,encoder.out_last)),
                         self.bulk_valid.eq(fifo.r_rdy),self.bulk_byte.eq(fifo.r_data[:8]),self.bulk_last.eq(fifo.r_data[8]),fifo.r_en.eq(self.bulk_ready)]
        else:
            m.d.comb += [encoder.out_ready.eq(self.bulk_ready),self.bulk_valid.eq(encoder.out_valid),
                         self.bulk_byte.eq(encoder.out_byte),self.bulk_last.eq(encoder.out_last)]
        held_handle=Signal(32);held_generation=Signal(32);held_cycle=Signal(32);held_ticks=Signal(64);held_channel=Signal(6)
        with m.If(self.iso.rx.start & ~self.iso.busy):
            m.d.sync += [held_handle.eq(self.handle),held_generation.eq(self.generation),held_cycle.eq(self.cycle_time),
                         held_ticks.eq(self.ticks),held_channel.eq(self.iso.channel)]
        m.d.comb += encoder.generation.eq(held_generation)
        with m.If(index>=32):m.d.comb += encoder.byte.eq(self.iso.payload_byte)
        with m.If(self.iso.payload_start):
            m.d.sync += [index.eq(0),metadata.eq(Cat(held_handle,held_generation,self.sequence,held_cycle,held_ticks,
                                                   self.iso.payload_length,Const(0,16),held_channel,Const(0,2),
                                                   self.iso.tag,Const(0,6),self.iso.sy,Const(0,4),Const(3,8)))]
        with m.Elif(encoder.valid & encoder.ready & (index<32)):m.d.sync += index.eq(index+1)
        with m.If(encoder.out_valid & encoder.out_ready & encoder.out_last):m.d.sync += self.sequence.eq(self.sequence+1)
        with m.If(self.iso.error):m.d.sync += self.errors.eq(self.errors+1)
        return m
