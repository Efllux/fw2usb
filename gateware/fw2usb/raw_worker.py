"""Single-outstanding raw-tunnel worker, USB byte framing -> native PHY/link.

Supported SUBMIT: quadlet/block read/write and compare-swap32/64. No transport
error or busy ACK silently replays a FireWire write. Native bus reset retires the
request, disables raw ISO and emits a new generation event at a frame boundary.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, ResetInserter, Signal
from fw2usb.async_request import AsyncRequestEncoder
from fw2usb.link_layer import LinkLayer
from fw2usb.tunnel import FrameDecoder, FrameEncoder


class RawWorker(Elaboratable):
    def __init__(self, *, iso_capacity=512):
        self.iso_capacity=iso_capacity
        self.command=FrameDecoder(capacity=512)
        self.link=LinkLayer()
        self.epoch_reset=Signal()
        self.session_reset=Signal()
        self.cycle_master_enable=Signal()
        self.generation=Signal(32,init=1)
        self.local_node=Signal(16,init=0xffff)
        self.node_count=Signal(7)
        self.ready=Signal()
        self.iso_enabled=Signal()
        self.iso_handle=Signal(32)
        self.monotonic_ticks=Signal(64)
        self.iso_channel=Signal(6)
        self.iso_losses=Signal(32)
        self.iso_cost=Signal(16);self.iso_consume=Signal();self.iso_admit=Signal()
        self.iso_packet_credits=Signal(6);self.iso_byte_credits=Signal(14)
        self.iso_maximum=Signal(16)
        self.out_valid=Signal();self.out_ready=Signal();self.out_byte=Signal(8);self.out_last=Signal()

    def elaborate(self,platform):
        m=Module();m.submodules.command=self.command;m.submodules.link=self.link
        encoder=FrameEncoder();m.submodules.response=ResetInserter(self.session_reset)(encoder)
        grant=Signal();grant_packets=Signal(6);grant_bytes=Signal(14);new_lease=Signal()
        m.d.comb += self.iso_admit.eq(self.iso_enabled & (self.iso_packet_credits!=0) & (self.iso_byte_credits>=self.iso_cost) & (self.iso_cost<=56+self.iso_maximum))
        with m.If(grant | self.iso_consume):
            m.d.sync += [self.iso_packet_credits.eq(self.iso_packet_credits+Mux(grant,grant_packets,0)-self.iso_consume),
                         self.iso_byte_credits.eq(self.iso_byte_credits+Mux(grant,grant_bytes,0)-Mux(self.iso_consume,self.iso_cost,0))]
        abort_request=Signal()
        m.d.comb += self.command.reset.eq(self.session_reset)
        status=self.link.phy.status
        reset=Signal()
        m.d.comb += reset.eq(self.epoch_reset | (status.flags_valid & status.flags_mask[1] & status.flags[1]))
        request=AsyncRequestEncoder();m.submodules.request=ResetInserter(reset | self.session_reset | abort_request)(request)
        sid_words=Array(Signal(32,name=f'selfid_word{i}') for i in range(63))
        selfid_phase=Signal(init=1);root=Signal(6);local_root=Signal();topology_error=Signal()
        reset_pending=Signal();loss_pending=Signal();loss_seen=Signal(32)
        ticks=self.monotonic_ticks;divider=Signal();m.d.sync += divider.eq(~divider)
        with m.If(divider):m.d.sync += ticks.eq(ticks+1)
        m.d.comb += [self.link.selfid_phase.eq(selfid_phase),self.link.phy.bus_reset.eq(reset),
                     self.link.cycle.node_id.eq(self.local_node),self.link.cycle.timer.root.eq(local_root & self.ready),
                     self.link.cycle.timer.enable.eq(self.cycle_master_enable & self.ready)]
        with m.If(self.link.selfid.accept & selfid_phase):
            with m.If(self.link.selfid.physical_id<63):
                m.d.sync += sid_words[self.link.selfid.physical_id].eq(self.link.selfid.packet)
                with m.If(self.link.selfid.physical_id+1>self.node_count):
                    m.d.sync += [self.node_count.eq(self.link.selfid.physical_id+1),root.eq(self.link.selfid.physical_id)]
            with m.Else():m.d.sync += topology_error.eq(1)
        with m.If(self.link.selfid.error & selfid_phase):m.d.sync += topology_error.eq(1)
        with m.If(status.register_valid & (status.address==0)):
            m.d.sync += [self.local_node.eq(Cat(status.data[2:8],Const(0x3ff,10))),local_root.eq(status.data[1]),
                         selfid_phase.eq(0),self.ready.eq(~topology_error & (status.data[2:8]<self.node_count))]
        with m.If(self.iso_losses!=loss_seen):
            m.d.sync += [loss_seen.eq(self.iso_losses),loss_pending.eq(1)]
        with m.If(reset):
            m.d.sync += [self.generation.eq(self.generation+1),self.ready.eq(0),self.node_count.eq(0),
                         selfid_phase.eq(1),topology_error.eq(0),self.iso_enabled.eq(0),reset_pending.eq(1)]
        parameters=Array(Signal(8,name=f'raw_parameter{i}') for i in range(28))
        parse_index=Signal(5)
        destination=Cat(parameters[0],parameters[1]);tcode=parameters[2][:4];speed=parameters[3][:2]
        address=Cat(*parameters[4:10]);upper_address=Cat(parameters[10],parameters[11])
        extended=Cat(parameters[12],parameters[13]);length=Cat(*parameters[16:20]);timeout_us=Cat(*parameters[20:24])
        quadlet=Cat(parameters[27],parameters[26],parameters[25],parameters[24])
        label=Signal(6);active_label=Signal(6);posted=Signal();timeout=Signal(32);limit=Signal(32)
        rx_header=Array(Signal(32,name=f'raw_rx_header{i}') for i in range(4))
        rx_data=Array(Signal(8,name=f'raw_rx_byte{i}') for i in range(256))
        rx_count=Signal(17);first_byte=Signal(8);held_quadlet=Signal(32)
        result_length=Signal(16);result_quadlet=Signal();ack=Signal(8);rcode=Signal(8);completion_ticks=Signal(64)
        mode=Signal(3);response_opcode=Signal(16);response_status=Signal(32);response_id=Signal(32)
        response_length=Signal(16);response_index=Signal(16);event=Signal()
        bus_info=Cat(self.local_node,root,Const(0x3ff,10),self.node_count,Const(0,9),self.ready,local_root,topology_error,Const(0,13))
        complete=Cat(ack,rcode,Const(0,16),result_length,Const(0,16),completion_ticks)
        caps=Const(int.from_bytes(bytes.fromhex('00000000000001000f00000000000000'),'little'),128)
        pair=sid_words[response_index>>3]
        sid_quad=Signal(32);payload_byte=Signal(8)
        m.d.comb += [sid_quad.eq(Mux(response_index[2],~pair,pair)),payload_byte.eq(0)]
        with m.Switch(mode):
            with m.Case(0):m.d.comb += payload_byte.eq(bus_info >> (response_index<<3))
            with m.Case(1):m.d.comb += payload_byte.eq(sid_quad >> ((~response_index[:2])<<3))
            with m.Case(2):
                with m.If(response_index<16):m.d.comb += payload_byte.eq(complete >> (response_index<<3))
                with m.Elif(result_quadlet):m.d.comb += payload_byte.eq(held_quadlet >> ((~response_index[:2])<<3))
                with m.Else():m.d.comb += payload_byte.eq(rx_data[response_index-16])
            with m.Case(3):m.d.comb += payload_byte.eq(Cat(self.iso_handle,self.iso_maximum,Const(0,16),Const(1,32),Const(1,32)) >> (response_index<<3))
            with m.Case(5):m.d.comb += payload_byte.eq(caps >> (response_index<<3))
            with m.Case(6):m.d.comb += payload_byte.eq(loss_seen >> (response_index<<3))
        m.d.comb += [encoder.kind.eq(Mux(event,2,1)),encoder.opcode.eq(response_opcode),encoder.id.eq(response_id),
                     encoder.status.eq(response_status),encoder.generation.eq(self.generation),encoder.length.eq(response_length),
                     encoder.valid.eq(1),encoder.byte.eq(payload_byte),encoder.out_ready.eq(self.out_ready),
                     self.out_valid.eq(encoder.out_valid),self.out_byte.eq(encoder.out_byte),self.out_last.eq(encoder.out_last),
                     self.link.request.kind.eq(3),self.link.request.speed.eq(speed<<1),
                     self.link.tx_valid.eq(request.valid),self.link.tx_byte.eq(request.byte),self.link.tx_last.eq(request.last),
                     request.ready.eq(self.link.tx_ready),request.destination.eq(destination),request.source.eq(self.local_node),
                     request.label.eq(active_label),request.tcode.eq(tcode),request.address.eq(address),request.length.eq(length[:16]),
                     request.extended.eq(extended),request.quadlet.eq(quadlet),request.data_byte.eq(self.command.read_data)]
        m.d.comb += self.command.read_index.eq(24+request.data_index)
        with m.If(self.link.request.valid & self.link.request.ready):m.d.sync += posted.eq(1)
        with m.If(self.link.phy.rx.start):m.d.sync += rx_count.eq(0)
        with m.If(self.link.phy.rx.valid):
            with m.If(rx_count==0):m.d.sync += first_byte.eq(self.link.phy.rx.byte)
            with m.If(rx_count<16):m.d.sync += rx_header[rx_count[2:4]].eq(Cat(self.link.phy.rx.byte,rx_header[rx_count[2:4]][:24]))
            m.d.sync += rx_count.eq(rx_count+1)
        with m.FSM() as fsm:
            with m.State('IDLE'):
                m.d.sync += [response_status.eq(0),event.eq(0),result_length.eq(0),result_quadlet.eq(0),ack.eq(0),rcode.eq(0)]
                with m.If(reset_pending):
                    m.d.sync += [event.eq(1),response_id.eq(0),response_opcode.eq(0x8000),response_length.eq(0),reset_pending.eq(0)]
                    m.next='REPLY'
                with m.Elif(loss_pending):
                    m.d.sync += [event.eq(1),response_id.eq(0),response_opcode.eq(0x203),response_length.eq(4),mode.eq(6),loss_pending.eq(0)]
                    m.next='REPLY'
                with m.Elif(self.command.command_valid):
                    m.d.sync += [response_id.eq(self.command.id),response_opcode.eq(Mux(self.command.opcode==0x100,0x101,self.command.opcode)),
                                 response_length.eq(0),mode.eq(4)]
                    with m.If((self.command.opcode!=3)&(self.command.opcode!=1)&(self.command.generation!=self.generation)):
                        m.d.sync += response_status.eq(4);m.next='REPLY'
                    with m.Else():
                        with m.Switch(self.command.opcode):
                            with m.Case(1):m.d.sync += [mode.eq(5),response_length.eq(16)];m.next='REPLY'
                            with m.Case(3):m.d.sync += [mode.eq(0),response_length.eq(8)];m.next='REPLY'
                            with m.Case(4):m.d.sync += [mode.eq(1),response_length.eq(self.node_count<<3)];m.next='REPLY'
                            with m.Case(0x100):
                                with m.If(~self.ready | self.link.phy.pending | self.link.phy.tx.busy):m.d.sync += response_status.eq(3);m.next='REPLY'
                                with m.Elif(self.command.length<24):m.d.sync += response_status.eq(1);m.next='REPLY'
                                with m.Else():m.d.sync += parse_index.eq(0);m.next='PARSE'
                            with m.Case(0x200):
                                with m.If(self.command.length!=12):m.d.sync += response_status.eq(1);m.next='REPLY'
                                with m.Else():m.d.sync += parse_index.eq(0);m.next='PARSE_ISO'
                            with m.Case(0x204):
                                with m.If(self.command.length!=12):m.d.sync += response_status.eq(1);m.next='REPLY'
                                with m.Else():m.d.sync += parse_index.eq(0);m.next='PARSE_CREDIT'
                            with m.Case(0x202):
                                with m.If(self.command.length!=4):m.d.sync += response_status.eq(1);m.next='REPLY'
                                with m.Else():m.d.sync += parse_index.eq(0);m.next='PARSE_DESTROY'
                            with m.Default():m.d.sync += response_status.eq(2);m.next='REPLY'
            with m.State('PARSE'):
                m.d.comb += self.command.read_index.eq(parse_index)
                m.d.sync += parameters[parse_index].eq(self.command.read_data)
                with m.If(parse_index==27):m.next='VALIDATE'
                with m.Else():m.d.sync += parse_index.eq(parse_index+1)
            with m.State('VALIDATE'):
                write=(tcode==0)|(tcode==1)|(tcode==9)
                valid_type=(tcode==0)|(tcode==1)|(tcode==4)|(tcode==5)|(tcode==9)
                invalid=((~valid_type)|(parameters[2]>15)|(upper_address!=0)|
                        (Cat(parameters[14],parameters[15])!=0)|((tcode!=9)&(extended!=0))|(address[:2]!=0)|(parameters[3]>2)|(destination[:6]==63)|
                        (length==0)|(length>256)|(self.command.length!=24+Mux(write,length,0))|
                        (((tcode==0)|(tcode==4))&(length!=4))|
                        ((tcode==9)&((extended!=2)|((length!=8)&(length!=16)))))
                with m.If(self.command.generation!=self.generation):m.d.sync += response_status.eq(4);m.next='REPLY'
                with m.Elif(invalid):m.d.sync += response_status.eq(1);m.next='REPLY'
                with m.Else():
                    m.d.sync += [active_label.eq(label),label.eq(label+1),posted.eq(0),timeout.eq(0),
                                 limit.eq(Mux(timeout_us>1_000_000,49_152_000,Mux(timeout_us==0,49_152,(timeout_us*49152)//1000)))]
                    m.next='START'
            with m.State('PARSE_ISO'):
                m.d.comb += self.command.read_index.eq(parse_index)
                m.d.sync += parameters[parse_index].eq(self.command.read_data)
                with m.If(parse_index==11):m.next='ENABLE_ISO'
                with m.Else():m.d.sync += parse_index.eq(parse_index+1)
            with m.State('PARSE_CREDIT'):
                m.d.comb += self.command.read_index.eq(parse_index)
                m.d.sync += parameters[parse_index].eq(self.command.read_data)
                with m.If(parse_index==11):m.next='CREDIT'
                with m.Else():m.d.sync += parse_index.eq(parse_index+1)
            with m.State('CREDIT'):
                packets=Cat(*parameters[4:8]);bytes_=Cat(*parameters[8:12])
                with m.If((Cat(*parameters[:4])!=self.iso_handle)|~self.iso_enabled|(self.command.generation!=self.generation)|
                          (packets==0)|(bytes_==0)|(packets>32)|(bytes_>8192)|
                          (self.iso_packet_credits+packets>32)|(self.iso_byte_credits+bytes_>8192)):
                    m.d.sync += response_status.eq(1)
                with m.Else():m.d.comb += [grant.eq(1),grant_packets.eq(packets),grant_bytes.eq(bytes_)]
                m.next='REPLY'
            with m.State('PARSE_DESTROY'):
                m.d.comb += self.command.read_index.eq(parse_index)
                m.d.sync += parameters[parse_index].eq(self.command.read_data)
                with m.If(parse_index==3):m.next='DESTROY'
                with m.Else():m.d.sync += parse_index.eq(parse_index+1)
            with m.State('DESTROY'):
                with m.If((Cat(*parameters[:4])==self.iso_handle)&self.iso_enabled):m.d.sync += self.iso_enabled.eq(0)
                with m.Else():m.d.sync += response_status.eq(1)
                m.next='REPLY'
            with m.State('ENABLE_ISO'):
                with m.If(self.iso_enabled):m.d.sync += response_status.eq(3)
                with m.Elif((parameters[0]!=0)|(parameters[1]>63)|(parameters[2]>2)|(parameters[3]!=0)|~self.ready|
                            (Cat(*parameters[4:8])==0)|(Cat(*parameters[4:8])>self.iso_capacity)|(Cat(*parameters[8:12])==0)|(Cat(*parameters[8:12])>64)):
                    m.d.sync += response_status.eq(1)
                with m.Else():
                    m.d.comb += new_lease.eq(1)
                    m.d.sync += [self.iso_maximum.eq(Cat(*parameters[4:6])),self.iso_channel.eq(parameters[1][:6]),self.iso_enabled.eq(1),self.iso_handle.eq(self.iso_handle+1),mode.eq(3),response_length.eq(16)]
                m.next='REPLY'
            with m.State('START'):
                m.d.comb += request.start.eq(1);m.next='SEND'
            with m.State('SEND'):
                m.d.sync += timeout.eq(timeout+1)
                with m.If(timeout>=limit):
                    m.d.comb += abort_request.eq(1)
                    m.d.sync += [response_status.eq(6),response_length.eq(16),mode.eq(2),rcode.eq(255),completion_ticks.eq(ticks)]
                    m.next='REPLY'
                m.d.comb += self.link.request.valid.eq(request.valid & ~posted)
                with m.If(request.valid & request.ready & request.last):m.next='WAIT'
                with m.If(reset | (self.command.generation!=self.generation)):m.d.sync += [response_status.eq(4),response_length.eq(0)];m.next='REPLY'
            with m.State('WAIT'):
                m.d.sync += timeout.eq(timeout+1)
                with m.If(self.link.phy.rx.valid & (rx_count>=20)&(rx_count<276)):
                    m.d.sync += rx_data[rx_count-20].eq(self.link.phy.rx.byte)
                with m.If(self.link.phy.rx.end & (rx_count==1) & ((first_byte[:4]^first_byte[4:8])==15)):
                    m.d.sync += ack.eq(first_byte[4:8])
                    with m.If((first_byte[4:8]==1)&((tcode==0)|(tcode==1))):
                        m.d.sync += [rcode.eq(0),completion_ticks.eq(ticks),mode.eq(2),response_length.eq(16)];m.next='REPLY'
                    with m.Elif((first_byte[4:8]!=1)&(first_byte[4:8]!=2)):
                        m.d.sync += [response_status.eq(6),rcode.eq(255),completion_ticks.eq(ticks),mode.eq(2),response_length.eq(16)];m.next='REPLY'
                expected= Mux((tcode==0)|(tcode==1),2,Mux(tcode==4,6,Mux(tcode==5,7,11)))
                with m.If(self.link.packet.good & (rx_header[0][16:32]==self.local_node)&
                          (rx_header[1][16:32]==destination)&(rx_header[0][10:16]==active_label)&(self.link.packet.tcode==expected)):
                    m.d.sync += [rcode.eq(rx_header[1][12:16]),completion_ticks.eq(ticks),mode.eq(2),response_length.eq(16)]
                    with m.If(rx_header[1][12:16]==0):
                        with m.If(expected==6):
                            m.d.sync += [held_quadlet.eq(rx_header[3]),result_quadlet.eq(1),result_length.eq(4),response_length.eq(20)]
                        with m.Elif((expected==7)|(expected==11)):
                            with m.If(rx_header[3][16:32]>256):m.d.sync += response_status.eq(6)
                            with m.Else():m.d.sync += [result_length.eq(rx_header[3][16:32]),response_length.eq(16+rx_header[3][16:32])]
                    m.next='REPLY'
                with m.If(timeout>=limit):
                    m.d.sync += [response_status.eq(6),response_length.eq(16),mode.eq(2),rcode.eq(255),completion_ticks.eq(ticks)];m.next='REPLY'
                with m.If(reset | (self.command.generation!=self.generation)):m.d.sync += [response_status.eq(4),response_length.eq(0)];m.next='REPLY'
            with m.State('REPLY'):
                m.d.comb += encoder.start.eq(1);m.d.sync += response_index.eq(0);m.next='RESPONSE'
            with m.State('RESPONSE'):
                with m.If(encoder.ready):m.d.sync += response_index.eq(response_index+1)
                with m.If(encoder.out_valid & self.out_ready & encoder.out_last):
                    m.d.comb += self.command.command_ready.eq(~event);m.next='IDLE'
        with m.If(self.session_reset):
            m.d.sync += [fsm.state.eq(fsm.encoding['IDLE']),self.iso_enabled.eq(0),reset_pending.eq(0),loss_pending.eq(0)]
        with m.If(new_lease | reset | self.session_reset | ~self.iso_enabled):
            m.d.sync += [self.iso_packet_credits.eq(0),self.iso_byte_credits.eq(0)]
        return m
