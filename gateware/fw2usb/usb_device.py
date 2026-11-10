"""LUNA0.2.3 ULPI HS vendor transport, prototype IDs only.
External bridge logic supplies/parses FW2R/FW2C frames on bulk streams. This core
provides USB enumeration/transport, not an implicit success response to commands.
"""
import struct
from amaranth import Array, ClockDomain, ClockSignal, ResetSignal, Const, Elaboratable, Module, Record, Signal, ResetInserter
from luna.usb2 import USBDevice, USBStreamInEndpoint, USBStreamOutEndpoint
from luna.gateware.usb.usb2.request import USBRequestHandler
from usb_protocol.emitters import DeviceDescriptorCollection


def descriptors(*, raw=True):
    result=DeviceDescriptorCollection()
    with result.DeviceDescriptor() as d:
        d.idVendor=0x1209;d.idProduct=2 if raw else 1;d.bcdDevice=0x0001
        d.iManufacturer='fw2usb development';d.iProduct='fw2usb raw prototype' if raw else 'fw2usb companion prototype'
        d.iSerialNumber='FW2USB-SIM-0001';d.bNumConfigurations=1
    with result.ConfigurationDescriptor() as c:
        c.bConfigurationValue=1;c.bmAttributes=0x80;c.bMaxPower=50
        with c.InterfaceDescriptor() as i:
            i.bInterfaceNumber=0;i.bInterfaceClass=255;i.bInterfaceSubclass=2;i.bInterfaceProtocol=int(raw)
            for address in (0x01,0x81):
                with i.EndpointDescriptor() as e:
                    e.bEndpointAddress=address;e.bmAttributes=2;e.wMaxPacketSize=512;e.bInterval=0
    return result


class GetCaps(USBRequestHandler):
    def __init__(self, *, capabilities=0, interface_number=0):
        super().__init__()
        self.capabilities=capabilities;self.interface_number=interface_number

    def elaborate(self,platform):
        m=Module();i=self.interface;s=i.setup
        caps=Array(Const(b,8) for b in struct.pack('<HHIQ',0,0,65536,self.capabilities))
        index=Signal(4);length=Signal(5)
        valid=Signal()
        m.d.comb += [i.claim.eq(s.type==2),valid.eq((s.recipient==1)&s.is_in_request&(s.request==1)&
                                                 (s.index==self.interface_number)&(s.value==0)&(s.length!=0))]
        with m.FSM(domain='usb') as fsm:
            with m.State('IDLE'):pass
            with m.State('WAIT'):
                with m.If(i.data_requested):
                    m.d.usb += index.eq(0);m.next='SEND'
            with m.State('SEND'):
                m.d.comb += [i.tx.valid.eq(1),i.tx.payload.eq(caps[index]),i.tx.first.eq(index==0),
                             i.tx.last.eq(index+1==length)]
                with m.If(i.tx.ready):
                    with m.If(index+1==length):m.next='ACK'
                    with m.Else():m.d.usb += index.eq(index+1)
            with m.State('ACK'):
                with m.If(i.handshakes_in.ack):m.next='STATUS'
                with m.Elif(i.data_requested):
                    m.d.usb += index.eq(0);m.next='SEND'
            with m.State('STATUS'):
                with m.If(i.status_requested):
                    m.d.comb += i.handshakes_out.ack.eq(1);m.next='IDLE'
            with m.State('STALL'):
                with m.If(i.data_requested | i.status_requested):m.d.comb += i.handshakes_out.stall.eq(1)
        with m.If(s.received & (s.type==2)):
            with m.If(valid):
                m.d.usb += [length.eq(16),fsm.state.eq(fsm.encoding['WAIT'])]
                with m.If(s.length<16):m.d.usb += length.eq(s.length)
            with m.Else():m.d.usb += fsm.state.eq(fsm.encoding['STALL'])
        return m


class SessionEndpoint(Elaboratable):
    """Reset endpoint queues, DATA PID and FSMs on USB bus reset."""
    def __init__(self, endpoint, reset):
        self.interface=endpoint.interface
        self.endpoint=endpoint;self.reset=reset

    def elaborate(self, platform):
        m=Module();m.submodules.endpoint=ResetInserter({'usb':self.reset})(self.endpoint);return m


class RawUsbDevice(Elaboratable):
    def __init__(self, *, raw=True, capabilities=0, external_domain=False):
        self.raw=raw
        self.capabilities=capabilities;self.external_domain=external_domain
        self.ulpi=Record([('data',[('i',8),('o',8),('oe',1)]),('dir',[('i',1)]),
                          ('nxt',[('i',1)]),('stp',[('o',1)]),('rst',[('o',1)])])
        self.in_valid=Signal();self.in_ready=Signal();self.in_byte=Signal(8);self.in_last=Signal()
        self.out_valid=Signal();self.out_ready=Signal();self.out_byte=Signal(8)
        self.connect=Signal(init=1)
        self.clock=Signal();self.reset=Signal();self.reset_detected=Signal()

    def elaborate(self,platform):
        m=Module()
        if not self.external_domain:
            m.domains+=ClockDomain('usb')
            m.d.comb += [ClockSignal('usb').eq(self.clock),ResetSignal('usb').eq(self.reset)]
        m.submodules.usb=usb=USBDevice(bus=self.ulpi,handle_clocking=False)
        control=usb.add_standard_control_endpoint(descriptors(raw=self.raw))
        control.add_request_handler(GetCaps(capabilities=self.capabilities))
        incoming=USBStreamOutEndpoint(endpoint_number=1,max_packet_size=512,buffer_size=2048)
        outgoing=USBStreamInEndpoint(endpoint_number=1,max_packet_size=512)
        usb.add_endpoint(SessionEndpoint(incoming,usb.reset_detected))
        usb.add_endpoint(SessionEndpoint(outgoing,usb.reset_detected))
        m.d.comb += [usb.connect.eq(self.connect),self.reset_detected.eq(usb.reset_detected),outgoing.stream.valid.eq(self.in_valid),
                     outgoing.stream.payload.eq(self.in_byte),outgoing.stream.last.eq(self.in_last),
                     self.in_ready.eq(outgoing.stream.ready),self.out_valid.eq(incoming.stream.valid),
                     self.out_byte.eq(incoming.stream.payload),incoming.stream.ready.eq(self.out_ready)]
        return m
