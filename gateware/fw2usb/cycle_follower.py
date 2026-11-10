"""CRC-committed cycle-slave synchronization, IEEE1394-2008 8.3.2.3.1.
Forward corrections step; backward corrections pause local increments to repay
phase debt without reversing time. Modulo128s ordering assumes error<64s.
RX latency outside the measured link frame is a board-calibrated parameter.
"""
from amaranth import Array,Cat,Const,Elaboratable,Module,Mux,Signal

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
        offset=Signal(13);cycle=Signal(14);seconds=Signal(8)
        m.d.comb += [offset.eq(header[3][:12]+((age+2)>>1)+self.latency_ticks),
                     cycle.eq(header[3][12:25]+(offset>=3072)),seconds.eq(header[3][25:32]+(cycle>=8000)),
                     self.value.eq(Cat(Mux(offset>=3072,offset-3072,offset)[:12],Mux(cycle>=8000,cycle-8000,cycle)[:13],seconds[:7]))]
        period=128*8000*3072
        current=Signal(32);candidate=Signal(32);forward=Signal(32);backward=Signal(32)
        m.d.comb += [current.eq(self.now[25:32]*(8000*3072)+self.now[12:25]*3072+self.now[:12]),
                     candidate.eq(self.value[25:32]*(8000*3072)+self.value[12:25]*3072+self.value[:12]),
                     forward.eq(Mux(candidate>=current,candidate-current,candidate+period-current)),
                     backward.eq(Mux(current>=candidate,current-candidate,current+period-candidate)),
                     self.accepted.eq(self.enable & self.good & (count==20) & (age<256) &
                         (header[0]==0xffff008f)&(header[1][:16]==0xffff)&(header[1][16:32]==self.root)&
                         (header[2]==0xf0000200)&(header[3][:12]<3072)&(header[3][12:25]<8000)),
                     self.load.eq(self.accepted & (forward!=0)&(forward<period//2)),self.pause.eq(self.enable & (self.debt!=0))]
        with m.If(self.enable & (since<12288)):m.d.sync += since.eq(since+1)
        with m.If(self.tick & (self.debt!=0)):m.d.sync += self.debt.eq(self.debt-1)
        with m.If(since>=12287):m.d.sync += [self.synced.eq(0),self.debt.eq(0)]
        with m.If(self.accepted):
            m.d.sync += [since.eq(0),self.synced.eq(1),self.updates.eq(self.updates+1),self.debt.eq(Mux((forward!=0)&(forward>=period//2),backward,0))]
        with m.If(~self.enable):m.d.sync += [self.debt.eq(0),self.synced.eq(0),since.eq(0)]
        return m
