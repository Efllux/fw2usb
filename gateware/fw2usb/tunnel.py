"""FW2R/FW2C v0 bounded USB bulk byte-stream framing (PR16 contract).
Domain is sync; rename to usb when attaching LUNA. Transfer boundaries ignored.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Signal


class FrameEncoder(Elaboratable):
    def __init__(self, *, raw=True):
        self.raw=raw
        self.start=Signal();self.kind=Signal(8);self.opcode=Signal(16);self.id=Signal(32)
        self.status=Signal(32);self.generation=Signal(32);self.length=Signal(16)
        self.valid=Signal();self.ready=Signal();self.byte=Signal(8)
        self.out_valid=Signal();self.out_ready=Signal();self.out_byte=Signal(8);self.out_last=Signal()
        self.busy=Signal();self.error=Signal()

    def elaborate(self,platform):
        m=Module();header=Signal(192);index=Signal(5);remaining=Signal(16)
        m.d.sync += self.error.eq(0)
        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing('IDLE'))
            with m.State('IDLE'):
                with m.If(self.start):
                    with m.If(self.length>65512):m.d.sync += self.error.eq(1)
                    with m.Else():
                        magic=int.from_bytes(b'FW2R' if self.raw else b'FW2C','little')
                        m.d.sync += [header.eq(Cat(Const(magic,32),Const(0,8),self.kind,self.opcode,self.id,
                                                 self.length,Const(0,16),self.status,self.generation)),
                                     index.eq(0),remaining.eq(self.length)]
                        m.next='HEADER'
            with m.State('HEADER'):
                m.d.comb += [self.out_valid.eq(1),self.out_byte.eq(header >> (index << 3)),
                             self.out_last.eq((index==23)&(remaining==0))]
                with m.If(self.out_ready):
                    with m.If(index==23):
                        with m.If(remaining==0):m.next='IDLE'
                        with m.Else():m.next='PAYLOAD'
                    with m.Else():m.d.sync += index.eq(index+1)
            with m.State('PAYLOAD'):
                m.d.comb += [self.out_valid.eq(self.valid),self.ready.eq(self.out_ready),self.out_byte.eq(self.byte),self.out_last.eq(remaining==1)]
                with m.If(self.valid & self.out_ready):
                    m.d.sync += remaining.eq(remaining-1)
                    with m.If(remaining==1):m.next='IDLE'
        return m


class FrameDecoder(Elaboratable):
    def __init__(self, *, raw=True,capacity=256):
        self.raw,self.capacity=raw,capacity
        self.valid=Signal();self.ready=Signal();self.byte=Signal(8);self.reset=Signal()
        self.command_valid=Signal();self.command_ready=Signal();self.opcode=Signal(16);self.id=Signal(32)
        self.generation=Signal(32);self.length=Signal(16);self.halted=Signal()
        self.read_index=Signal(range(capacity));self.read_data=Signal(8)

    def elaborate(self,platform):
        m=Module();header=Array(Signal(8,name=f'frame_header{i}') for i in range(24))
        payload=Array(Signal(8,name=f'frame_payload{i}') for i in range(self.capacity))
        index=Signal(range(max(self.capacity,24)))
        length=Signal(32)
        m.d.comb += [self.opcode.eq(Cat(header[6],header[7])),self.id.eq(Cat(*header[8:12])),
                     self.generation.eq(Cat(*header[20:24])),length.eq(Cat(*header[12:16])),
                     self.length.eq(length[:16]),self.read_data.eq(payload[self.read_index])]
        with m.FSM() as fsm:
            with m.State('HEADER'):
                m.d.comb += self.ready.eq(1)
                with m.If(self.valid):
                    m.d.sync += header[index].eq(self.byte)
                    with m.If(index==23):
                        m.d.sync += index.eq(0);m.next='CHECK'
                    with m.Else():m.d.sync += index.eq(index+1)
            with m.State('CHECK'):
                magic=int.from_bytes(b'FW2R' if self.raw else b'FW2C','little')
                valid=(Cat(*header[:4])==magic)&(header[4]==0)&(header[5]==0)&(self.id!=0)&(Cat(*header[16:20])==0)&(length<=self.capacity)
                with m.If(~valid):m.next='HALT'
                with m.Elif(length==0):m.next='COMMAND'
                with m.Else():m.next='PAYLOAD'
            with m.State('PAYLOAD'):
                m.d.comb += self.ready.eq(1)
                with m.If(self.valid):
                    m.d.sync += payload[index].eq(self.byte)
                    with m.If(index+1==length):
                        m.d.sync += index.eq(0);m.next='COMMAND'
                    with m.Else():m.d.sync += index.eq(index+1)
            with m.State('COMMAND'):
                m.d.comb += self.command_valid.eq(1)
                with m.If(self.command_ready):m.next='HEADER'
            with m.State('HALT'):m.d.comb += self.halted.eq(1)
        with m.If(self.reset):m.d.sync += [index.eq(0),fsm.state.eq(fsm.encoding['HEADER'])]
        return m
