"""Bounded PHY recovery policy after an uncertain/cancelled native request.
Read register1 to preserve RHB, then write RHB|IBR|63 (TI SLLS424G p30).
Only a real native bus-reset indication completes recovery. Missing PHY status
fails closed after the policy deadline; local pending bits are never fabricated.
"""
from amaranth import Elaboratable,Module,Signal,Cat,Const

class PhyRecovery(Elaboratable):
    def __init__(self, *, timeout_cycles=4_915_200):
        self.timeout_cycles=timeout_cycles
        self.start=Signal();self.bus_reset=Signal();self.active=Signal();self.failed=Signal()
        self.valid=Signal();self.ready=Signal();self.kind=Signal(3);self.address=Signal(4);self.data=Signal(8)
        self.register_valid=Signal();self.register_address=Signal(4);self.register_data=Signal(8)
    def elaborate(self,p):
        m=Module();timer=Signal(range(self.timeout_cycles+1));rhb=Signal()
        with m.FSM() as fsm:
            with m.State('IDLE'):
                with m.If(self.start):m.d.sync += [timer.eq(0),self.active.eq(1),self.failed.eq(0)];m.next='READ'
            with m.State('READ'):
                m.d.comb += [self.valid.eq(1),self.kind.eq(4),self.address.eq(1)]
                with m.If(self.ready):m.next='VALUE'
            with m.State('VALUE'):
                with m.If(self.register_valid & (self.register_address==1)):
                    m.d.sync += rhb.eq(self.register_data[7]);m.next='WRITE'
            with m.State('WRITE'):
                m.d.comb += [self.valid.eq(1),self.kind.eq(5),self.address.eq(1),self.data.eq(Cat(Const(0x7f,7),rhb))]
                with m.If(self.ready):m.next='RESET'
            with m.State('RESET'):pass
            with m.State('FAILED'):pass
        with m.If(self.active):
            with m.If(timer<self.timeout_cycles):m.d.sync += timer.eq(timer+1)
            with m.Else():m.d.sync += [self.active.eq(0),self.failed.eq(1),fsm.state.eq(fsm.encoding['FAILED'])]
        with m.If(self.bus_reset):m.d.sync += [self.active.eq(0),self.failed.eq(0),fsm.state.eq(fsm.encoding['IDLE'])]
        return m
