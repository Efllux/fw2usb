"""Integrated SCLK link datapath; topology policy is handled by Rust controller.
External TX supplies prebuffered CRC-framed bytes. Cycle-start request preempts
new user bus requests; an already-pending request is never overwritten.
"""
from types import SimpleNamespace
from amaranth import Elaboratable, Module, Mux, ResetInserter, Signal
from fw2usb.phy_link import PhyLink
from fw2usb.packet import PacketReceiver
from fw2usb.link import SelfIdCapture, AckDecision
from fw2usb.cycle_master import CycleMaster
from fw2usb.cycle_follower import CycleFollower


class LinkLayer(Elaboratable):
    def __init__(self):
        self.phy = PhyLink()
        self.packet = PacketReceiver()
        self.selfid = SelfIdCapture()
        self.cycle = CycleMaster()
        self.follower = CycleFollower()
        self.follow_cycles = Signal()
        self.timer_load = Signal()
        self.timer_value = Signal(32)
        self.root_node = Signal(16,init=0xffff)
        self.selfid_phase = Signal()
        self.capacity = Signal(init=1)
        self.request = SimpleNamespace(valid=Signal(),ready=Signal(),kind=Signal(3),speed=Signal(3),
                                       address=Signal(4),data=Signal(8),accel=Signal())
        self.user_grant = Signal()
        self.user_hold = Signal(init=1)
        self.tx_valid = Signal()
        self.tx_ready = Signal()
        self.tx_byte = Signal(8)
        self.tx_last = Signal()

    def elaborate(self, platform):
        m = Module()
        m.submodules.phy = self.phy
        m.submodules.packet = ResetInserter(self.phy.bus_reset | ~self.phy.enable)(self.packet)
        m.submodules.selfid = ResetInserter(self.phy.bus_reset | ~self.phy.enable)(self.selfid)
        m.submodules.cycle = self.cycle
        m.submodules.follower = ResetInserter(self.phy.bus_reset | ~self.phy.enable | self.timer_load)(self.follower)
        m.d.comb += [self.follower.now.eq(self.cycle.timer.value),self.follower.tick.eq(self.cycle.timer.tick),
                     self.follower.enable.eq(self.follow_cycles),self.follower.root.eq(self.root_node),
                     self.follower.start.eq(self.phy.rx.start & ~self.selfid_phase),self.follower.valid.eq(self.phy.rx.valid & ~self.selfid_phase),
                     self.follower.byte.eq(self.phy.rx.byte),self.follower.end.eq(self.phy.rx.end & ~self.selfid_phase),self.follower.good.eq(self.packet.good),
                     self.cycle.timer.load.eq(self.follower.load | self.timer_load),self.cycle.timer.load_value.eq(Mux(self.timer_load,self.timer_value,self.follower.value)),self.cycle.timer.pause.eq(self.follower.pause)]
        m.submodules.ack = ack = AckDecision()
        cycle_owned = Signal()
        ack_owned = Signal()
        ack_wanted = Signal()
        ack_valid = Signal()
        ack_byte = Signal(8)
        choose_ack = Signal()
        # With registered pins the PHY's earliest grant reaches the transmit
        # adapter in the same cycle as the receive adapter's ``end``, and the
        # adapter takes its first byte in that cycle. The ACK code is therefore
        # decided combinationally from flags the packet receiver registered
        # while the bytes arrived; the address match is registered at decode.
        addressed = Signal()
        broadcast = Signal()
        with m.If(self.packet.header_decoded):
            m.d.sync += [addressed.eq(self.packet.destination == self.cycle.node_id),
                         broadcast.eq(self.packet.destination[:6] == 63)]
        m.d.comb += [
            choose_ack.eq(ack_wanted),
            ack.end.eq(self.packet.good_now | self.packet.bad_now),
            ack.addressed.eq(addressed),
            ack.broadcast.eq(broadcast),
            ack.header_good.eq(self.packet.header_good), ack.data_good.eq(self.packet.good_now),
            ack.tcode.eq(self.packet.tcode),ack.capacity.eq(self.capacity)]
        with m.If(self.packet.header_decoded & (self.packet.destination == self.cycle.node_id) &
                  (self.packet.destination[:6] != 63) & (self.packet.tcode != 8) & (self.packet.tcode != 10)):
            m.d.sync += ack_wanted.eq(1)
        with m.If(ack.now_valid):
            m.d.sync += [ack_valid.eq(1), ack_byte.eq(ack.now_byte)]
        with m.If(self.phy.rx.start):
            m.d.sync += ack_valid.eq(0)
        with m.If(self.phy.tx.done & ack_owned):
            m.d.sync += ack_valid.eq(0)
        choose_cycle = Signal()
        m.d.comb += [choose_cycle.eq(self.cycle.request & ~choose_ack & ~(self.request.valid & (self.request.kind>=4))),
                     self.phy.request.valid.eq(Mux(choose_ack | choose_cycle,1,self.request.valid)),
                     self.phy.request.kind.eq(Mux(choose_ack,0,Mux(choose_cycle,2,self.request.kind))),
                     self.phy.request.speed.eq(Mux(choose_ack,self.phy.rx.speed << 1,Mux(choose_cycle,0,self.request.speed))),
                     self.phy.request.address.eq(self.request.address),
                     self.phy.request.data.eq(self.request.data),self.phy.request.accel.eq(self.request.accel),
                     self.request.ready.eq(self.phy.request.ready & ~choose_cycle & ~choose_ack),
                     self.cycle.grant.eq(self.phy.tx.grant & cycle_owned),
                     self.cycle.ready.eq(self.phy.tx.ready & cycle_owned),
                     self.phy.tx.valid.eq(Mux(ack_owned,ack_valid | ack.now_valid,Mux(cycle_owned,self.cycle.valid,self.tx_valid))),
                     self.phy.tx.byte.eq(Mux(ack_owned,Mux(ack.now_valid,ack.now_byte,ack_byte),Mux(cycle_owned,self.cycle.byte,self.tx_byte))),
                     self.phy.tx.last.eq(Mux(ack_owned,1,Mux(cycle_owned,self.cycle.last,self.tx_last))),
                     self.tx_ready.eq(self.phy.tx.ready & ~cycle_owned & ~ack_owned),
                     self.user_grant.eq(self.phy.tx.grant & ~cycle_owned & ~ack_owned),
                     self.phy.tx.allow_hold.eq(~ack_owned & (cycle_owned | self.user_hold)),
                     self.packet.start.eq(self.phy.rx.start & ~self.selfid_phase),
                     self.packet.valid.eq(self.phy.rx.valid & ~self.selfid_phase),
                     self.packet.byte.eq(self.phy.rx.byte),
                     self.packet.end.eq(self.phy.rx.end & ~self.selfid_phase),
                     self.packet.phy_error.eq(self.phy.rx.error),
                     self.selfid.start.eq(self.phy.rx.start & self.selfid_phase),
                     self.selfid.valid.eq(self.phy.rx.valid & self.selfid_phase),
                     self.selfid.byte.eq(self.phy.rx.byte),
                     self.selfid.end.eq(self.phy.rx.end & self.selfid_phase)]
        with m.If(self.phy.request.valid & self.phy.request.ready & (self.phy.request.kind < 4)):
            m.d.sync += [cycle_owned.eq(choose_cycle), ack_owned.eq(choose_ack)]
            with m.If(choose_ack):
                m.d.sync += ack_wanted.eq(0)
        with m.If(self.phy.bus_reset | ~self.phy.enable):
            m.d.sync += [cycle_owned.eq(0), ack_owned.eq(0), ack_wanted.eq(0), ack_valid.eq(0)]
        return m
