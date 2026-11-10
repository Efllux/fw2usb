"""48k stereo PCM24 UAC2 research function, USB-domain streams.
USB-IF ADC2 Tables4-3..9/10/27/33..35 and section5.2.5.1. External controller
must bind a verified profile and supply recovered16.16 feedback before alt1.
"""
import struct
from amaranth import Elaboratable,Array,Cat,ClockDomain,ClockSignal,ResetSignal,Const,Module,Signal,Mux
from luna.usb2 import USBDevice,USBStreamInEndpoint,USBStreamOutEndpoint
from luna.gateware.usb.usb2.request import USBRequestHandler
from luna.gateware.usb.usb2.endpoints.isochronous_stream_in import USBIsochronousStreamInEndpoint
from luna.gateware.usb.usb2.endpoints.isochronous_stream_out import USBIsochronousStreamOutEndpoint
from fw2usb.usb_device import RawUsbDevice,SessionEndpoint,GetCaps
from amaranth.lib.fifo import SyncFIFOBuffered
from usb_protocol.emitters import DeviceDescriptorCollection


def descriptors():
    d=DeviceDescriptorCollection()
    with d.DeviceDescriptor() as x:
        x.idVendor=0x1209;x.idProduct=1;x.bcdDevice=1
        x.bDeviceClass=0xef;x.bDeviceSubclass=2;x.bDeviceProtocol=1
        x.iManufacturer='fw2usb development';x.iProduct='fw2usb experimental audio';x.bNumConfigurations=1
    ac=(bytes([8,0x24,10,1,0,5,0,0])+ # external clock, frequency/validity RO
        struct.pack('<BBBBHBBBIBHB',17,0x24,2,10,0x101,0,1,2,3,0,0,0)+
        struct.pack('<BBBBHBBBHB',12,0x24,3,11,0x301,0,10,1,0,0)+
        struct.pack('<BBBBHBBBIBHB',17,0x24,2,12,0x301,0,1,2,3,0,0,0)+
        struct.pack('<BBBBHBBBHB',12,0x24,3,13,0x101,0,12,1,0,0))
    ac=struct.pack('<BBBHBHB',9,0x24,1,0x200,8,len(ac)+9,0)+ac
    body=bytes([8,11,0,3,1,0,0x20,0])+bytes([9,4,0,0,0,1,1,0x20,0])+ac
    for number,terminal,address,eps in [(1,10,2,2),(2,13,0x82,1)]:
        body+=bytes([9,4,number,0,0,1,2,0x20,0])+bytes([9,4,number,1,eps,1,2,0x20,0])
        body+=struct.pack('<BBBBBBIBIB',16,0x24,1,terminal,0,1,1,2,3,0)
        body+=bytes([6,0x24,2,1,3,24])
        body+=struct.pack('<BBBBHB',7,5,address,5,42,1)
        body+=bytes([8,0x25,1,0,0,0,0,0])
        if number==1:body+=struct.pack('<BBBBHB',7,5,0x83,0x11,4,4)
    body+=bytes([9,4,3,0,2,255,2,0,0])
    for address in [1,0x81]:body+=struct.pack('<BBBBHB',7,5,address,2,512,0)
    config=struct.pack('<BBHBBBBB',9,2,len(body)+9,4,1,0,0x80,50)+body
    d.add_descriptor(config,descriptor_type=2)
    return d


class AudioControl(USBRequestHandler):
    def __init__(self):
        super().__init__();self.valid=Signal();self.play=Signal();self.capture=Signal()

    @staticmethod
    def claims(s):
        return ((s.type==1)&(s.recipient==1))|((s.type==0)&(s.recipient==1)&((s.request==10)|(s.request==11)))

    def elaborate(self,p):
        m=Module();i=self.interface;s=i.setup
        data=Array(Signal(8,name=f'reply{j}') for j in range(14));count=Signal(4);pos=Signal(4)
        selected=Signal();supported=Signal()
        m.d.comb += [i.claim.eq(self.claims(s)),selected.eq(Mux(s.index==1,self.play,self.capture))]
        with m.FSM(domain='usb') as fsm:
            with m.State('IDLE'):pass
            with m.State('DATA'):
                with m.If(i.data_requested):m.d.usb+=pos.eq(0);m.next='SEND'
            with m.State('SEND'):
                m.d.comb += [i.tx.valid.eq(1),i.tx.payload.eq(data[pos]),i.tx.first.eq(pos==0),i.tx.last.eq(pos+1==count)]
                with m.If(i.tx.ready):
                    with m.If(pos+1==count):m.next='ACK'
                    with m.Else():m.d.usb+=pos.eq(pos+1)
            with m.State('ACK'):
                with m.If(i.handshakes_in.ack):m.next='STATUS'
                with m.Elif(i.data_requested):m.d.usb+=pos.eq(0);m.next='SEND'
            with m.State('STATUS'):
                with m.If(i.status_requested):m.d.comb+=i.handshakes_out.ack.eq(1);m.next='IDLE'
            with m.State('ZLP'):
                with m.If(i.status_requested):m.d.comb+=self.send_zlp();m.next='IDLE'
            with m.State('STALL'):
                with m.If(i.data_requested|i.status_requested):m.d.comb+=i.handshakes_out.stall.eq(1)
        with m.If(s.received & self.claims(s)):
            m.d.usb += [fsm.state.eq(fsm.encoding['STALL']),pos.eq(0)]
            with m.If((s.type==0)&((s.index==1)|(s.index==2))):
                with m.If((s.request==10)&s.is_in_request&(s.length!=0)&(s.value==0)):
                    m.d.usb += [data[0].eq(selected),count.eq(1),fsm.state.eq(fsm.encoding['DATA'])]
                with m.Elif((s.request==11)&~s.is_in_request&(s.length==0)&(s.value<=1)&((s.value==0)|self.valid)):
                    with m.If(s.index==1):m.d.usb+=self.play.eq(s.value)
                    with m.Else():m.d.usb+=self.capture.eq(s.value)
                    m.d.usb+=fsm.state.eq(fsm.encoding['ZLP'])
            with m.Elif((s.type==1)&s.is_in_request&(s.index==0x100)&(s.value[:8]==0)&(s.length!=0)):
                with m.If((s.value==0x100)&((s.request==1)|(s.request==2))):
                    cur=struct.pack('<I',48000);ran=struct.pack('<HIII',1,48000,48000,0)
                    with m.If(s.request==1):
                        for j,b in enumerate(cur):m.d.usb+=data[j].eq(b)
                        m.d.usb += count.eq(Mux(s.length<4,s.length,4))
                    with m.Else():
                        for j,b in enumerate(ran):m.d.usb+=data[j].eq(b)
                        m.d.usb += count.eq(Mux(s.length<14,s.length,14))
                    m.d.usb+=fsm.state.eq(fsm.encoding['DATA'])
                with m.Elif((s.value==0x200)&(s.request==1)):
                    m.d.usb += [data[0].eq(self.valid),count.eq(1),fsm.state.eq(fsm.encoding['DATA'])]
        with m.If(~self.valid | (i.active_config==0)):m.d.usb += [self.play.eq(0),self.capture.eq(0)]
        return m


class AudioPacketBuffer(Elaboratable):
    """Packet-atomic USB capture; underflow inserts an entire silent packet."""
    def __init__(self):
        self.valid=Signal();self.ready=Signal();self.byte=Signal(8)
        self.start=Signal();self.length=Signal(6);self.out_ready=Signal();self.out_byte=Signal(8)
        self.underruns=Signal(32)
    def elaborate(self,p):
        m=Module();m.submodules.fifo=fifo=SyncFIFOBuffered(width=8,depth=512)
        available=Signal();remaining=Signal(6)
        m.d.comb += [fifo.w_en.eq(self.valid),fifo.w_data.eq(self.byte),self.ready.eq(fifo.w_rdy),
                     self.out_byte.eq(Mux(available,fifo.r_data,0)),fifo.r_en.eq(self.out_ready & available & (remaining!=0))]
        with m.If(self.start):
            m.d.sync += [available.eq(fifo.level>=self.length),remaining.eq(self.length)]
            with m.If((fifo.level<self.length)&(self.length!=0)):m.d.sync+=self.underruns.eq(self.underruns+1)
        with m.Elif(self.out_ready & (remaining!=0)):m.d.sync+=remaining.eq(remaining-1)
        return m


class AudioUsbDevice(RawUsbDevice):
    def __init__(self):
        super().__init__()
        self.profile_ready=Signal();self.clock_locked=Signal();self.feedback=Signal(32,init=6<<16)
        self.capture_valid=Signal();self.capture_ready=Signal();self.capture_byte=Signal(8)
        self.play_valid=Signal();self.play_ready=Signal();self.play_byte=Signal(8)
        self.underruns=Signal(32)

    def elaborate(self,p):
        m=Module();m.domains+=ClockDomain('usb')
        m.d.comb += [ClockSignal('usb').eq(self.clock),ResetSignal('usb').eq(self.reset)]
        m.submodules.usb=usb=USBDevice(bus=self.ulpi,handle_clocking=False)
        control=usb.add_standard_control_endpoint(descriptors(),skiplist=[AudioControl.claims])
        handler=AudioControl();control.add_request_handler(SessionEndpoint(handler,usb.reset_detected))
        control.add_request_handler(GetCaps(interface_number=3))
        # Companion capability negotiation is vendor-interface3 in this configuration.
        cin=USBStreamOutEndpoint(endpoint_number=1,max_packet_size=512,buffer_size=2048)
        cout=USBStreamInEndpoint(endpoint_number=1,max_packet_size=512)
        capture=USBIsochronousStreamInEndpoint(endpoint_number=2,max_packet_size=42)
        play=USBIsochronousStreamOutEndpoint(endpoint_number=2,max_packet_size=42)
        feedback=USBIsochronousStreamInEndpoint(endpoint_number=3,max_packet_size=4)
        for ep in [cin,cout,capture,play,feedback]:usb.add_endpoint(SessionEndpoint(ep,usb.reset_detected))
        buffer=AudioPacketBuffer();m.submodules.capture_buffer=SessionEndpointBuffer(buffer,usb.reset_detected)
        phase=Signal(16);frames=Signal(4,init=6);total=Signal(33);fb=Signal(32);index=Signal(2)
        m.d.comb += total.eq(phase+self.feedback)
        with m.If(usb.sof_detected):m.d.usb += [phase.eq(total[:16]),frames.eq(total[16:20])]
        with m.If(feedback.data_requested):m.d.usb += [fb.eq(self.feedback),index.eq(0)]
        with m.Elif(feedback.stream.ready):m.d.usb+=index.eq(index+1)
        m.d.comb += [usb.connect.eq(self.connect),self.reset_detected.eq(usb.reset_detected),
            handler.valid.eq(self.profile_ready & self.clock_locked),
            capture.bytes_in_frame.eq(Mux(handler.capture,frames*6,0)),capture.stream.valid.eq(1),
            capture.stream.payload.eq(buffer.out_byte),
            buffer.start.eq(capture.data_requested),buffer.length.eq(Mux(handler.capture,frames*6,0)),buffer.out_ready.eq(capture.stream.ready),
            buffer.valid.eq(self.capture_valid & handler.capture),buffer.byte.eq(self.capture_byte),self.capture_ready.eq(buffer.ready & handler.capture),
            self.underruns.eq(buffer.underruns),
            feedback.bytes_in_frame.eq(Mux(handler.play,4,0)),feedback.stream.valid.eq(1),feedback.stream.payload.eq(fb.word_select(index,8)),
            self.play_valid.eq(play.stream.valid & handler.play),self.play_byte.eq(play.stream.payload),
            play.stream.ready.eq(self.play_ready | ~handler.play),
            self.in_ready.eq(cout.stream.ready),cout.stream.valid.eq(self.in_valid),cout.stream.payload.eq(self.in_byte),cout.stream.last.eq(self.in_last),
            self.out_valid.eq(cin.stream.valid),self.out_byte.eq(cin.stream.payload),cin.stream.ready.eq(self.out_ready)]
        with m.If(usb.reset_detected):m.d.usb += [phase.eq(0),frames.eq(6)]
        return m


class SessionEndpointBuffer(Elaboratable):
    def __init__(self,buffer,reset):self.buffer=buffer;self.reset=reset
    def elaborate(self,p):
        from amaranth import DomainRenamer,ResetInserter
        m=Module();m.submodules.buffer=ResetInserter({'usb':self.reset})(DomainRenamer('usb')(self.buffer));return m
