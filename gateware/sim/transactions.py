"""Independent wire transaction fixture, IEEE1394 §6.2/7.
Polynomial long division is deliberately distinct from the Rust/RTL LFSRs.
"""
import struct
from sim.devices import DeviceError


def crc(data):
    bits = len(data)*8
    value = (int.from_bytes(data,'big') << 32) ^ (0xffffffff << bits)
    polynomial = (1 << 32) | 0x04c11db7
    for bit in range(value.bit_length()-1,31,-1):
        if value & (1 << bit):
            value ^= polynomial << (bit-32)
    return value ^ 0xffffffff


def packet(header, data=b''):
    result = header + crc(header).to_bytes(4,'big')
    if data:
        padded = data + bytes((-len(data)) % 4)
        result += padded + crc(padded).to_bytes(4,'big')
    return result


def request(destination,source,label,address,*,tcode=4,data=b'',length=4,extended=0):
    header = struct.pack('>III',(destination << 16) | (label << 10) | 0x100 | (tcode << 4),
                         (source << 16) | (address >> 32),address & 0xffffffff)
    if tcode == 0:
        if len(data) != 4:
            raise ValueError('quadlet write requires four bytes')
        header += data
    elif tcode in (1,5,9):
        header += struct.pack('>I',((len(data) if tcode != 5 else length) << 16) | extended)
    return packet(header,data if tcode in (1,9) else b'')


def decode(data):
    if len(data) < 16:
        raise DeviceError('short_header')
    tcode = data[3] >> 4
    hlen = 12 if tcode in (2,4) else 16
    if len(data) < hlen+4 or crc(data[:hlen]).to_bytes(4,'big') != data[hlen:hlen+4]:
        raise DeviceError('header_crc')
    q = struct.unpack('>'+'I'*(hlen//4),data[:hlen])
    payload = b''
    if tcode in (1,7,9,11):
        length = q[3] >> 16
        padded = (length+3) & ~3
        expected = hlen+4+(padded+4 if length else 0)
        if len(data) != expected:
            raise DeviceError('length')
        if length:
            payload = data[hlen+4:hlen+4+length]
            if crc(data[hlen+4:hlen+4+padded]).to_bytes(4,'big') != data[-4:]:
                raise DeviceError('data_crc')
    elif len(data) != hlen+4:
        raise DeviceError('length')
    return {'destination':q[0] >> 16,'source':q[1] >> 16,'label':q[0] >> 10 & 63,
            'tcode':tcode,'address':((q[1] & 0xffff) << 32) | q[2],
            'quadlet':q[3] if hlen == 16 else 0,'data':payload,'rcode':q[1] >> 12 & 15}


def response(req, *, rcode=0, data=b''):
    tcode = {0:2,1:2,4:6,5:7,9:11}[req['tcode']]
    header = struct.pack('>III',(req['source'] << 16) | (req['label'] << 10) | (tcode << 4),
                         (req['destination'] << 16) | (rcode << 12),0)
    if tcode == 6:
        header += data if len(data) == 4 else bytes(4)
    elif tcode in (7,11):
        header += struct.pack('>I',(len(data) << 16) | (2 if tcode == 11 else 0))
    return packet(header,data if tcode in (7,11) else b'')


class Peer:
    def __init__(self,bus,node,device):
        self.bus,self.node,self.device = bus,node,device
        self.reply = None
        self.node_id = None
        bus.listeners[node].append(self.event)

    def event(self,kind,value):
        if kind == 'reset':
            self.device.reset()
            self.reply = None
            self.node_id = None
        elif kind == 'initialized':
            self.node_id = 0xffc0 | value
            self.device.physical_id = value
        elif kind == 'transmitted' and len(value.data) == 1 and self.reply is not None:
            data,self.reply = self.reply,None
            self.bus.request(self.node,data,kind='fair')
        elif kind == 'packet' and len(value.data) > 1:
            try:
                req = decode(value.data)
            except DeviceError as error:
                if error.rcode in ('data_crc', 'length'):
                    self.bus.request(self.node, b'\xd2', kind='immediate')
                return  # header failure: no ACK; data failure: data-error ACK
            if req['destination'] != self.node_id or req['tcode'] not in (0,1,4,5,9):
                return
            data,rcode = b'',0
            try:
                if req['tcode'] in (4,5):
                    data = self.device.read(req['address'],4 if req['tcode'] == 4 else req['quadlet'] >> 16)
                elif req['tcode'] in (0,1):
                    self.device.write(req['address'],req['quadlet'].to_bytes(4,'big') if req['tcode'] == 0 else req['data'])
                else:
                    if req['quadlet'] & 0xffff != 2 or len(req['data']) not in (8,16):
                        raise DeviceError(6)
                    n = len(req['data'])//2
                    data = self.device.compare_swap(req['address'],req['data'][:n],req['data'][n:],generation=self.device.generation)
            except DeviceError as error:
                rcode = error.rcode if isinstance(error.rcode,int) else 4
            self.reply = response(req,rcode=rcode,data=data)
            if not self.bus.request(self.node,b'\x2d',kind='immediate'):
                self.reply = None


class Client:
    def __init__(self,bus,node):
        self.bus,self.node = bus,node
        self.node_id = None
        self.pending = {}
        self.completed = []
        self.next_label = 0
        self.sequence = 0
        bus.listeners[node].append(self.event)

    def event(self,kind,value):
        if kind == 'reset':
            self.completed.extend((label,'stale_generation',b'') for label in self.pending)
            self.pending.clear()
            self.node_id = None
        elif kind == 'initialized':
            self.node_id = 0xffc0 | value
        elif kind == 'packet' and len(value.data) > 1:
            try:
                reply = decode(value.data)
            except DeviceError:
                return
            label = reply['label']
            if reply['destination'] != self.node_id or label not in self.pending:
                return
            expected_source,expected_type,_ = self.pending[label]
            if reply['source'] != expected_source or reply['tcode'] != expected_type:
                return
            self.pending.pop(label)
            data = reply['quadlet'].to_bytes(4,'big') if reply['tcode'] == 6 else reply['data']
            self.completed.append((label,reply['rcode'],data))
            self.bus.request(self.node,b'\x1e',kind='immediate')

    def submit(self,destination,address,*,tcode=4,data=b'',length=4,extended=0,timeout_ns=10_000_000):
        if self.node_id is None or len(self.pending) >= 64:
            raise DeviceError('not_ready')
        label = self.next_label
        while label in self.pending:
            label = (label+1) & 63
        self.next_label = (label+1) & 63
        wire = request(destination,self.node_id,label,address,tcode=tcode,data=data,length=length,extended=extended)
        if not self.bus.request(self.node,wire):
            raise DeviceError('busy')
        self.sequence += 1
        token = self.sequence
        self.pending[label] = (destination,{0:2,1:2,4:6,5:7,9:11}[tcode],token)
        def timeout():
            if label in self.pending and self.pending[label][2] == token:
                self.pending.pop(label)
                self.completed.append((label,'timeout',b''))
        self.bus.schedule(self.bus.now+timeout_ns,timeout)
        return label
