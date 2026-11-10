"""Event-level multi-node alpha bus research, not cable-waveform conformance.

IEEE1394a §4.3.5/4.3.6 gap equations and §4.4.3 self-ID order; TI SLLS424G
reset/self-ID semantics. Link payloads are opaque here; link RTL validates CRC.
Tree handshakes are abstracted; arbitration ties use declared topology ordering.
"""
from dataclasses import dataclass
from fractions import Fraction
import heapq


@dataclass(frozen=True)
class Frame:
    source: int
    data: bytes
    speed: int
    start_ns: Fraction
    end_ns: Fraction
    epoch: int


@dataclass(frozen=True)
class Reservation:
    source: int
    speed: int
    start_ns: Fraction
    epoch: int


class Bus:
    def __init__(self, edges, *, nodes, root=0, propagation_ns=25, gap_count=63):
        if nodes < 1 or nodes > 63 or not 0 <= root < nodes or not 0 <= gap_count <= 63:
            raise ValueError('invalid topology configuration')
        self.nodes = nodes
        self.root = root
        self.edges = [[] for _ in range(nodes)]
        if len(edges) != nodes-1 or propagation_ns < 0:
            raise ValueError('bus must be a tree')
        for a, b in edges:
            if not 0 <= a < nodes or not 0 <= b < nodes or a == b:
                raise ValueError('invalid cable')
            self.edges[a].append(b)
            self.edges[b].append(a)
        self.propagation_ns = Fraction(propagation_ns)
        self.gap_count = gap_count
        self.parent = {}
        self.order = []
        self._tree(root, None)
        if len(self.order) != nodes:
            raise ValueError('disconnected tree')
        self.ids = {node: i for i, node in enumerate(self.order)}
        self.now = Fraction(0)
        self.epoch = 0
        self.events = []
        self.serial = 0
        self.listeners = [[] for _ in range(nodes)]
        self.received = [[] for _ in range(nodes)]
        self.trace = []
        self.pending = {}
        self.reservation_callbacks = {}
        self.reserved = None
        self.served = set()
        self.ready = False
        self.busy_until = Fraction(0)
        self.arbitrating = False

    def _tree(self, node, parent):
        if node in self.parent:
            raise ValueError('topology cycle')
        self.parent[node] = parent
        for child in sorted(self.edges[node]):
            if child != parent:
                self._tree(child, node)
        self.order.append(node)

    def schedule(self, at, callback):
        if at < self.now:
            raise ValueError('event in past')
        self.serial += 1
        heapq.heappush(self.events, (Fraction(at), self.serial, self.epoch, callback))

    def run(self, until=None):
        while self.events and (until is None or self.events[0][0] <= until):
            at, _, epoch, callback = heapq.heappop(self.events)
            self.now = at
            if epoch == self.epoch:
                callback()
        if until is not None:
            self.now = Fraction(until)

    def _distance(self, source, target):
        queue = [(source, 0)]
        seen = set()
        while queue:
            node, hops = queue.pop(0)
            if node == target:
                return hops
            seen.add(node)
            queue.extend((peer, hops+1) for peer in self.edges[node] if peer not in seen)
        raise ValueError('no path')

    def _deliver(self, node, kind, value):
        self.received[node].append((self.now, kind, value))
        for callback in self.listeners[node]:
            callback(kind, value)

    def reset(self):
        self.epoch += 1
        self.ready = False
        self.pending.clear()
        self.reservation_callbacks.clear()
        self.reserved = None
        self.served.clear()
        self.arbitrating = False
        self.trace.append((self.now, 'reset', self.epoch))
        for node in range(self.nodes):
            self._deliver(node, 'reset', self.epoch)
        # Selected legal long-reset and wait corners. Tree signaling itself is
        # abstracted; per-depth delay below is a declared fixture, not IEEE bound.
        start = self.now + 166_660 + 170 + 144 * max(self._distance(self.root, n) for n in range(self.nodes))
        for ordinal, node in enumerate(self.order):
            parent = self.parent[node]
            children = [p for p in sorted(self.edges[node]) if p != parent]
            ports = ([2] if parent is not None else []) + [3] * len(children)
            if len(ports) > 3:
                raise ValueError('extended self-ID needed for this topology')
            ports += [0] * (3-len(ports))
            q = (0x80400800 | (ordinal << 24) | (self.gap_count << 16) | (2 << 14) |
                 (ports[0] << 6) | (ports[1] << 4) | (ports[2] << 2))
            packet = q.to_bytes(4, 'big') + (q ^ 0xffffffff).to_bytes(4, 'big')
            duration = Fraction(64_000_000_000, 98_304_000) + 180 + 250 + 110
            for receiver in range(self.nodes):
                at = start + duration + self._distance(node, receiver) * self.propagation_ns
                self.schedule(at, lambda r=receiver, p=packet: self._deliver(r, 'selfid', p))
            start += duration
        self.busy_until = start + max(self._distance(self.root, n) for n in range(self.nodes)) * self.propagation_ns
        self.schedule(self.busy_until, self._initialized)

    def _initialized(self):
        self.ready = True
        for node in range(self.nodes):
            self._deliver(node, 'initialized', self.ids[node])
        self._arbitrate()

    def request(self, node, data, *, kind='fair', speed=2):
        if node not in self.ids or kind not in ('fair', 'priority', 'iso', 'immediate') or speed not in (0,1,2):
            raise ValueError('invalid request')
        if node in self.pending:
            return False
        self.pending[node] = (bytes(data), kind, speed)
        self._arbitrate()
        return True

    def reserve(self,node,*,kind='fair',speed=2,granted):
        """Reserve cable ownership before LLC has streamed the packet bytes.

        Completion time comes from the PHY-LINK observer, avoiding a second
        modeled wire duration after serialization. PHY/cable pipeline skew is
        still an explicit uncalibrated boundary, not a normative timing claim.
        """
        if node not in self.ids or kind not in ('fair','priority','iso','immediate') or speed not in (0,1,2):
            raise ValueError('invalid reservation')
        if node in self.pending or (self.reserved and self.reserved.source==node):return False
        self.reservation_callbacks[node]=granted;self.pending[node]=(None,kind,speed);self._arbitrate();return True

    def cancel_reservation(self,node):
        if node not in self.reservation_callbacks:return False
        del self.reservation_callbacks[node];del self.pending[node];return True

    def complete_reservation(self,token,data):
        if self.reserved is not token or token.epoch!=self.epoch:return False
        self.reserved=None;data=bytes(data)
        if not data:
            self.trace.append((self.now,'cancel_grant',token));self.busy_until=self.now;self._arbitrate();return True
        frame=Frame(token.source,data,token.speed,token.start_ns,self.now,self.epoch)
        self.trace.append((token.start_ns,'transmit',frame))
        for receiver in range(self.nodes):
            if receiver!=token.source:
                self.schedule(self.now+self._distance(token.source,receiver)*self.propagation_ns,
                              lambda r=receiver:self._deliver(r,'packet',frame))
        self.busy_until=self.now+max(self._distance(token.source,r) for r in range(self.nodes))*self.propagation_ns
        def finished():
            self._deliver(token.source,'transmitted',frame);self._arbitrate()
        self.schedule(self.busy_until,finished);return True

    def _arbitrate(self):
        if not self.ready or self.arbitrating or self.reserved is not None or not self.pending:
            return
        self.arbitrating = True
        # Nominal subaction detect + originating arbitration delay. Reset-gap
        # event opens a new fairness interval when every fair contender is served.
        waiting_fair = [n for n, (_, k, _) in self.pending.items() if k == 'fair']
        reset_gap = bool(waiting_fair) and all(n in self.served for n in waiting_fair) and all(k == 'fair' for _, k, _ in self.pending.values())
        urgent = any(k in ('immediate', 'iso') for _, k, _ in self.pending.values())
        ticks = 4 if urgent else (52 + 36*self.gap_count if reset_gap else 28 + 20*self.gap_count)
        delay = Fraction(ticks * 1_000_000_000, 98_304_000)
        def choose():
            self.arbitrating = False
            if reset_gap:
                self.served.clear()
                self.trace.append((self.now, 'fairness_reset', self.epoch))
            if not self.pending:return
            rank = {'immediate': 0, 'priority': 1, 'iso': 2, 'fair': 3}
            eligible = [n for n, (_, k, _) in self.pending.items() if k != 'fair' or n not in self.served]
            if not eligible:
                self._arbitrate()
                return
            node = min(eligible, key=lambda n: (rank[self.pending[n][1]], self._distance(n, self.root), self.ids[n]))
            data, kind, speed = self.pending.pop(node)
            if kind == 'fair':
                self.served.add(node)
            if data is None:
                self.reserved=Reservation(node,speed,self.now,self.epoch)
                self.trace.append((self.now,'grant',self.reserved))
                self.reservation_callbacks.pop(node)(self.reserved)
                return
            end = self.now + 180 + Fraction(len(data)*8*1_000_000_000, 98_304_000 << speed) + 250
            frame = Frame(node, data, speed, self.now, end, self.epoch)
            self.trace.append((self.now, 'transmit', frame))
            for receiver in range(self.nodes):
                if receiver != node:
                    self.schedule(end + self._distance(node, receiver)*self.propagation_ns,
                                  lambda r=receiver: self._deliver(r, 'packet', frame))
            self.busy_until = end + max(self._distance(node, r) for r in range(self.nodes))*self.propagation_ns
            def finished():
                self._deliver(node, 'transmitted', frame)
                self._arbitrate()
            self.schedule(self.busy_until, finished)
        self.schedule(max(self.now, self.busy_until) + delay, choose)
