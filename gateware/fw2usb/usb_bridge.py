"""LUNA raw USB bridge with complete-frame response/audio mux and CDC queues.
No header fragments are interleaved. USB session reset flushes both FIFO write
domains; native bus reset preserves USB byte framing and emits generation events.
"""
from amaranth import ClockDomain,ClockSignal,ResetSignal,Elaboratable,Module,ResetInserter,Signal
from amaranth.lib.cdc import PulseSynchronizer
from amaranth.lib.fifo import AsyncFIFOBuffered
from fw2usb.usb_device import RawUsbDevice
from fw2usb.raw_worker import RawWorker
from fw2usb.raw_iso_bridge import RawIsoBridge


class RawUsbBridge(Elaboratable):
    def __init__(self):
        self.usb=RawUsbDevice(capabilities=7,external_domain=True)
        self.worker=RawWorker(iso_capacity=4096)
        self.audio=RawIsoBridge(capacity=4096,cdc=False,opaque=True)

    def elaborate(self,platform):
        m=Module();m.domains+=ClockDomain('usb')
        m.d.comb += [ClockSignal('usb').eq(self.usb.clock),ResetSignal('usb').eq(self.usb.reset)]
        m.submodules.usb=self.usb;m.submodules.worker=self.worker
        m.submodules.reset_crossing=reset_crossing=PulseSynchronizer('usb','sync')
        m.submodules.audio=ResetInserter(reset_crossing.o)(self.audio)
        last_reset=Signal();m.d.usb += last_reset.eq(self.usb.reset_detected)
        m.d.comb += [reset_crossing.i.eq(self.usb.reset_detected & ~last_reset),self.worker.session_reset.eq(reset_crossing.o)]
        incoming=AsyncFIFOBuffered(width=8,depth=1025,w_domain='usb',r_domain='sync')
        outgoing=AsyncFIFOBuffered(width=9,depth=8193,w_domain='sync',r_domain='usb')
        m.submodules.incoming=ResetInserter({'usb':self.usb.reset_detected})(incoming)
        m.submodules.outgoing=ResetInserter({'sync':reset_crossing.o})(outgoing)
        m.d.comb += [incoming.w_data.eq(self.usb.out_byte),incoming.w_en.eq(self.usb.out_valid),self.usb.out_ready.eq(incoming.w_rdy),
                     self.worker.command.valid.eq(incoming.r_rdy),self.worker.command.byte.eq(incoming.r_data),incoming.r_en.eq(self.worker.command.ready),
                     self.audio.iso.rx.start.eq(self.worker.link.phy.rx.start & self.worker.iso_enabled & ~self.worker.link.selfid_phase),
                     self.audio.iso.rx.valid.eq(self.worker.link.phy.rx.valid),self.audio.iso.rx.byte.eq(self.worker.link.phy.rx.byte),
                     self.audio.iso.rx.end.eq(self.worker.link.phy.rx.end),self.audio.iso.rx.phy_error.eq(self.worker.link.phy.rx.error),
                     self.audio.iso.channel.eq(self.worker.iso_channel),self.audio.handle.eq(self.worker.iso_handle),
                     self.audio.generation.eq(self.worker.generation),self.audio.cycle_time.eq(self.worker.link.cycle.timer.value),
                     self.audio.ticks.eq(self.worker.monotonic_ticks),self.worker.iso_losses.eq(self.audio.iso.losses+self.audio.errors),
                     self.usb.in_valid.eq(outgoing.r_rdy),self.usb.in_byte.eq(outgoing.r_data[:8]),self.usb.in_last.eq(outgoing.r_data[8]),outgoing.r_en.eq(self.usb.in_ready)]
        held=Signal();audio=Signal();choose_audio=Signal();valid=Signal();last=Signal();byte=Signal(8)
        m.d.comb += choose_audio.eq(audio)
        with m.If(~held):m.d.comb += choose_audio.eq(~self.worker.out_valid & self.audio.bulk_valid)
        with m.If(choose_audio):
            m.d.comb += [valid.eq(self.audio.bulk_valid),last.eq(self.audio.bulk_last),byte.eq(self.audio.bulk_byte),self.audio.bulk_ready.eq(outgoing.w_rdy)]
        with m.Else():
            m.d.comb += [valid.eq(self.worker.out_valid),last.eq(self.worker.out_last),byte.eq(self.worker.out_byte),self.worker.out_ready.eq(outgoing.w_rdy)]
        m.d.comb += [outgoing.w_en.eq(valid),outgoing.w_data.eq(byte|(last<<8))]
        with m.If(valid & outgoing.w_rdy):
            m.d.sync += [held.eq(~last),audio.eq(choose_audio)]
        with m.If(reset_crossing.o):m.d.sync += held.eq(0)
        return m
