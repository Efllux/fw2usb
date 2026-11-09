"""Independent event-time device audio clock and blocking AM824 packet source.
Drift is true sample-clock frequency error; jitter perturbs SYT in bus ticks.
Synthetic samples/timestamps, no real device capture implied.
"""
from fractions import Fraction
import struct


class AudioClock:
    def __init__(self, *, rate=48000, channels=2, sid=1, ppm=0, jitter_ticks=(0,), sampler=None):
        codes={32000:0,44100:1,48000:2,88200:3,96000:4,176400:5,192000:6}
        if rate not in codes or not 1<=channels<=32 or not jitter_ticks:
            raise ValueError('unsupported audio fixture')
        self.rate,self.channels,self.sid=rate,channels,sid
        self.code=codes[rate]
        self.interval=8 if rate<=48000 else (16 if rate<=96000 else 32)
        actual=Fraction(rate)*(1+Fraction(ppm)/1_000_000)
        if actual<=0:raise ValueError('invalid sample clock')
        self.interval_ns=Fraction(self.interval*1_000_000_000)/actual
        self.jitter=tuple(jitter_ticks)
        self.sampler=sampler or (lambda frame,channel: ((frame*7919+channel*0x31415)&0xffffff)-0x800000)
        self.next_ns=None;self.last_cycle=None;self.frame=0;self.dbc=0;self.packets=0

    def next_cycle(self,cycle):
        if self.last_cycle is not None and cycle!=self.last_cycle+1:
            raise ValueError('audio cycles must be contiguous')
        self.last_cycle=cycle
        if self.next_ns is None:self.next_ns=Fraction(cycle*125_000)
        payload=bytearray();syt=65535;fdf=255
        if self.next_ns < (cycle+1)*125_000:
            target=int(self.next_ns*Fraction(24_576_000,1_000_000_000))+0x2e00+self.jitter[self.packets%len(self.jitter)]
            syt=((target//3072 & 15)<<12)|(target%3072)
            fdf=self.code
            for frame in range(self.interval):
                for channel in range(self.channels):
                    sample=self.sampler(self.frame+frame,channel)
                    payload+=struct.pack('>I',0x40000000|(sample&0xffffff))
            self.frame+=self.interval
            self.next_ns+=self.interval_ns
        header=struct.pack('>II',((self.sid&63)<<24)|(self.channels<<16)|self.dbc,
                           0x90000000|(fdf<<16)|syt)
        if payload:self.dbc=(self.dbc+self.interval)&255
        self.packets+=1
        return header+payload
