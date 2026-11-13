"""CRC-committed cycle-slave synchronization, IEEE1394-2008 8.3.2.3.1.
Forward corrections step; backward corrections pause local increments to repay
phase debt without reversing time. Modulo128s ordering assumes error<64s.
RX latency outside the measured link frame is a board-calibrated parameter.

Timing structure. A correction is needed once per 125 us, so it is computed
over PIPELINE SCLK cycles after the cycle-start packet is accepted instead of
in one cycle. All arithmetic stays in the seconds/cycles/offset fields of
CYCLE_TIME (no multiplication to ticks and back); only a backward debt is
converted to ticks, with shifts and adds, in its own stage.

``accepted``, ``updates`` and ``synced`` still change with the accepted packet.
``load``/``value`` and a new ``debt`` follow PIPELINE cycles later. PIPELINE is
even and the loaded value is advanced by PIPELINE/2 ticks, so the timer ends in
exactly the state an immediate load would have reached by then. Any older debt
is dropped at acceptance, so the total pause equals the measured backward error.
"""
from amaranth import Array,Cat,Const,Elaboratable,Module,Mux,Signal

PIPELINE=6


def normalized(offset,cycle,second):
    """Carry an offset below 2*3072 into cycle and second fields."""
    wrap=offset>=3072;bumped=cycle+wrap;carry=bumped>=8000
    return Cat(Mux(wrap,offset-3072,offset)[:12],Mux(carry,bumped-8000,bumped)[:13],(second+carry)[:7])


class CycleFollower(Elaboratable):
    def __init__(self, *, latency_ticks=0):
        if not 0<=latency_ticks<=1024:raise ValueError('latency outside bounded correction')
        self.latency_ticks=latency_ticks
        self.now=Signal(32);self.tick=Signal();self.enable=Signal();self.root=Signal(16,init=0xffff)
        self.start=Signal();self.valid=Signal();self.byte=Signal(8);self.end=Signal();self.good=Signal()
        self.load=Signal();self.value=Signal(32);self.pause=Signal();self.debt=Signal(32)
        self.accepted=Signal();self.updates=Signal(32);self.synced=Signal()
    def elaborate(self,p):
        m=Module();since=Signal(range(12289));header=Array(Signal(32,name=f'cycle_header{i}') for i in range(4))
        count=Signal(6);age=Signal(10);active=Signal()
        with m.If(self.start):m.d.sync += [count.eq(0),age.eq(0),active.eq(1)]
        with m.Elif(active):
            with m.If(age<1023):m.d.sync += age.eq(age+1)
            with m.If(self.valid):
                with m.If(count<16):m.d.sync += header[count[2:4]].eq(Cat(self.byte,header[count[2:4]][:24]))
                with m.If(count<63):m.d.sync += count.eq(count+1)
            with m.If(self.end):m.d.sync += active.eq(0)
        m.d.comb += [self.accepted.eq(self.enable & self.good & (count==20) & (age<256) &
                         (header[0]==0xffff008f)&(header[1][:16]==0xffff)&(header[1][16:32]==self.root)&
                         (header[2]==0xf0000200)&(header[3][:12]<3072)&(header[3][12:25]<8000)),
                     self.pause.eq(self.enable & (self.debt!=0))]
        stage=Signal(PIPELINE)  # one-hot progress of the accepted correction
        m.d.sync += stage.eq(Cat(self.accepted,stage[:-1]))
        # Stage 0, with the accepted packet: receive-age compensation, once as
        # of now (to measure the error) and once as of the cycle of the load.
        measured_offset=Signal(13);loaded_offset=Signal(13);local=Signal(32)
        with m.If(self.accepted):
            m.d.sync += [measured_offset.eq(header[3][:12]+((age+2)>>1)+self.latency_ticks),
                         loaded_offset.eq(header[3][:12]+((age+2+PIPELINE)>>1)+self.latency_ticks),
                         local.eq(self.now)]
        # Stage 1: carry both candidates into cycle and second fields.
        measured=Signal(32);loaded=Signal(32)
        with m.If(stage[0]):m.d.sync += [measured.eq(normalized(measured_offset,header[3][12:25],header[3][25:32])),
                     loaded.eq(normalized(loaded_offset,header[3][12:25],header[3][25:32]))]
        # Stage 2: forward distance, offset field resolved, others still raw.
        offset_raw=Signal(13);offset_ahead=Signal(12);offset_borrow=Signal()
        cycle_raw=Signal(14);second_raw=Signal(7)
        m.d.comb += offset_raw.eq(measured[:12]-local[:12])
        m.d.sync += [offset_borrow.eq(offset_raw[12]),offset_ahead.eq(Mux(offset_raw[12],offset_raw+3072,offset_raw)),
                     cycle_raw.eq(measured[12:25]-local[12:25]),second_raw.eq(measured[25:32]-local[25:32])]
        # Stage 3: resolve the cycle and second borrows.
        cycle_step=Signal(14);cycle_ahead=Signal(13);second_ahead=Signal(7)
        m.d.comb += cycle_step.eq(cycle_raw-offset_borrow)
        m.d.sync += [cycle_ahead.eq(Mux(cycle_step[13],cycle_step+8000,cycle_step)),
                     second_ahead.eq(second_raw-cycle_step[13])]
        # Stage 4: classify, and take the complement for a backward error.
        forward=Signal();backward=Signal();offset_behind=Signal(12);cycle_behind=Signal(13);second_behind=Signal(7)
        moved=Signal();offset_carry=Signal();cycle_carry=Signal();cycle_left=Signal(14)
        m.d.comb += [moved.eq((offset_ahead!=0)|(cycle_ahead!=0)|(second_ahead!=0)),
                     offset_carry.eq(offset_ahead!=0),cycle_left.eq(8000-cycle_ahead-offset_carry),
                     cycle_carry.eq(cycle_left!=8000)]
        m.d.sync += [forward.eq(moved & ~second_ahead[6]),backward.eq(moved & second_ahead[6]),
                     offset_behind.eq(Mux(offset_carry,3072-offset_ahead,0)),
                     cycle_behind.eq(Mux(cycle_carry,cycle_left,0)),
                     second_behind.eq(0-second_ahead-cycle_carry)]
        # Stage 5: backward error in ticks. 24576000 == 375<<16, 3072 == 3<<10.
        owed=Signal(32);seconds_375=Signal(16)
        m.d.comb += seconds_375.eq((second_behind<<8)+(second_behind<<7)-(second_behind<<3)-second_behind)
        m.d.sync += owed.eq((seconds_375<<16)+(cycle_behind<<11)+(cycle_behind<<10)+offset_behind)
        applying=Signal()
        m.d.comb += [applying.eq(stage[-1] & self.enable),self.value.eq(loaded),
                     self.load.eq(applying & forward)]
        with m.If(self.enable & (since<12288)):m.d.sync += since.eq(since+1)
        with m.If(self.tick & (self.debt!=0)):m.d.sync += self.debt.eq(self.debt-1)
        with m.If(since>=12287):m.d.sync += [self.synced.eq(0),self.debt.eq(0)]
        with m.If(self.accepted):
            m.d.sync += [since.eq(0),self.synced.eq(1),self.updates.eq(self.updates+1),self.debt.eq(0)]
        with m.If(applying & backward):m.d.sync += self.debt.eq(owed)
        with m.If(~self.enable):m.d.sync += [self.debt.eq(0),self.synced.eq(0),since.eq(0)]
        return m
