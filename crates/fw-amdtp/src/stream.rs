//! AMDTP stream framing in blocking mode (what BeBoB/DICE/Saffire devices use).
//!
//! Every 125 µs isochronous cycle carries either exactly `syt_interval` data blocks
//! with a SYT timestamp, or a NO-DATA packet. Which cycles carry data is decided by
//! advancing the "next event" time by `syt_interval / rate` seconds.

use crate::am824;
use crate::cip::{CipHeader, Sfc, FDF_NO_DATA, FMT_AM824, SYT_NO_INFO};
use crate::cycle::{CycleTime, TICKS_PER_CYCLE, TICKS_PER_SECOND};

/// Default presentation delay added to outgoing SYT (same value Linux ALSA uses: ~479 µs).
pub const TRANSFER_DELAY_TICKS: u32 = 0x2E00;

/// Decides, per isochronous cycle, whether a data packet is sent and with which SYT.
///
/// Exact rational arithmetic: positions are kept in units of 1/rate ticks, so
/// 44.1 kHz never drifts.
#[derive(Clone, Debug)]
pub struct SytScheduler {
    sfc: Sfc,
    /// Next event time within the current cycle, in (ticks * rate). May exceed one cycle.
    next_event: u64,
    step: u64,
    cycle_len: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CycleSlot {
    NoData,
    /// Data packet whose first sample is presented at `offset` ticks into this cycle.
    Data {
        offset: u16,
    },
}

impl SytScheduler {
    pub fn new(sfc: Sfc) -> Self {
        let rate = sfc.rate() as u64;
        SytScheduler {
            sfc,
            next_event: 0,
            step: TICKS_PER_SECOND as u64 * sfc.syt_interval() as u64,
            cycle_len: TICKS_PER_CYCLE as u64 * rate,
        }
    }

    pub fn sfc(&self) -> Sfc {
        self.sfc
    }

    /// Call once per isochronous cycle, in order.
    pub fn next_cycle(&mut self) -> CycleSlot {
        let slot = if self.next_event < self.cycle_len {
            let rate = self.sfc.rate() as u64;
            let offset = (self.next_event / rate) as u16;
            self.next_event += self.step;
            CycleSlot::Data { offset }
        } else {
            CycleSlot::NoData
        };
        self.next_event -= self.cycle_len;
        slot
    }
}

/// Builds outgoing (host → device) AMDTP packets.
pub struct PacketBuilder {
    pub sid: u8,
    /// Quadlets per data block: audio channels + MIDI slots.
    pub dbs: u8,
    /// Index of the first MIDI slot within a data block (== number of PCM channels).
    pub pcm_channels: u8,
    dbc: u8,
    sched: SytScheduler,
}

impl PacketBuilder {
    pub fn new(sid: u8, pcm_channels: u8, midi_slots: u8, sfc: Sfc) -> Self {
        PacketBuilder {
            sid,
            dbs: pcm_channels + midi_slots,
            pcm_channels,
            dbc: 0,
            sched: SytScheduler::new(sfc),
        }
    }

    pub fn frames_per_data_packet(&self) -> usize {
        self.sched.sfc().syt_interval() as usize
    }

    /// Max packet payload length in bytes (CIP header + one full data packet).
    pub fn max_len(&self) -> usize {
        CipHeader::LEN + self.frames_per_data_packet() * self.dbs as usize * 4
    }

    /// Build the packet for isochronous cycle `now`.
    ///
    /// `frames` supplies interleaved 24-bit samples (`pcm_channels` per frame) and is
    /// only consumed when this cycle carries data. Returns (bytes written, frames consumed).
    pub fn build(
        &mut self,
        now: CycleTime,
        frames: &mut dyn FnMut() -> Option<[i32; 32]>,
        out: &mut [u8],
    ) -> (usize, usize) {
        let slot = self.sched.next_cycle();
        let mut hdr = CipHeader {
            sid: self.sid,
            dbs: self.dbs,
            dbc: self.dbc,
            fmt: FMT_AM824,
            fdf: FDF_NO_DATA,
            syt: SYT_NO_INFO,
        };
        let CycleSlot::Data { offset } = slot else {
            hdr.encode((&mut out[..8]).try_into().unwrap());
            return (8, 0);
        };
        let cycle_start = now.ticks() - now.offset as u32;
        let syt_time = CycleTime::from_ticks(cycle_start + offset as u32 + TRANSFER_DELAY_TICKS);
        hdr.fdf = self.sched.sfc() as u8;
        hdr.syt = syt_time.syt();
        hdr.encode((&mut out[..8]).try_into().unwrap());

        let n = self.frames_per_data_packet();
        let mut pos = 8;
        for _ in 0..n {
            let frame = frames().unwrap_or([0; 32]); // underrun → silence, keep the stream alive
            let pcm = frame
                .iter()
                .take(self.pcm_channels as usize)
                .map(|&s| am824::encode_audio(s));
            let midi = core::iter::repeat((am824::LABEL_MIDI_NONE as u32) << 24);
            for q in pcm.chain(midi).take(self.dbs as usize) {
                out[pos..pos + 4].copy_from_slice(&q.to_be_bytes());
                pos += 4;
            }
        }
        self.dbc = self.dbc.wrapping_add(n as u8);
        (pos, n)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RxEvent {
    NoData,
    /// `frames` data blocks were decoded; `syt` is the presentation time of the first one.
    Data {
        frames: usize,
        syt: Option<u16>,
        dbc_gap: bool,
    },
}

/// Parses incoming (device → host) AMDTP packets and tracks DBC continuity.
pub struct PacketParser {
    expected_dbc: Option<u8>,
    pub discontinuities: u32,
}

impl Default for PacketParser {
    fn default() -> Self {
        Self::new()
    }
}

impl PacketParser {
    pub const fn new() -> Self {
        PacketParser {
            expected_dbc: None,
            discontinuities: 0,
        }
    }

    /// Decode `payload` (CIP header + data). Each sample is handed to `sink(frame, channel, sample24)`.
    pub fn parse(
        &mut self,
        payload: &[u8],
        sink: &mut dyn FnMut(usize, usize, i32),
    ) -> Result<RxEvent, crate::cip::CipError> {
        let hdr = CipHeader::decode(payload)?;
        let data = &payload[CipHeader::LEN..];
        if hdr.dbs == 0 || data.is_empty() {
            return Ok(RxEvent::NoData);
        }
        let block = hdr.dbs as usize * 4;
        let frames = data.len() / block;
        let dbc_gap = matches!(self.expected_dbc, Some(e) if e != hdr.dbc);
        if dbc_gap {
            self.discontinuities += 1;
        }
        self.expected_dbc = Some(hdr.dbc.wrapping_add(frames as u8));
        for f in 0..frames {
            for ch in 0..hdr.dbs as usize {
                let o = f * block + ch * 4;
                let q = u32::from_be_bytes([data[o], data[o + 1], data[o + 2], data[o + 3]]);
                if let am824::Am824::Audio(s) = am824::decode(q) {
                    sink(f, ch, s);
                }
            }
        }
        let syt = (hdr.syt != SYT_NO_INFO).then_some(hdr.syt);
        Ok(RxEvent::Data {
            frames,
            syt,
            dbc_gap,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn data_packets_per_second(sfc: Sfc) -> u32 {
        let mut s = SytScheduler::new(sfc);
        (0..8000)
            .filter(|_| matches!(s.next_cycle(), CycleSlot::Data { .. }))
            .count() as u32
    }

    #[test]
    fn scheduler_rates_are_exact() {
        for sfc in [
            Sfc::Hz32000,
            Sfc::Hz44100,
            Sfc::Hz48000,
            Sfc::Hz88200,
            Sfc::Hz96000,
            Sfc::Hz176400,
            Sfc::Hz192000,
        ] {
            let pkts = data_packets_per_second(sfc);
            let frames = pkts * sfc.syt_interval();
            // 44.1k family: 5512.5 packets/s → alternate 5512/5513 per second.
            assert!(
                frames.abs_diff(sfc.rate()) <= sfc.syt_interval() / 2 + 4,
                "{sfc:?}: {frames}"
            );
        }
        // Over 2 seconds 44.1 kHz must be exact.
        let mut s = SytScheduler::new(Sfc::Hz44100);
        let n = (0..16000)
            .filter(|_| matches!(s.next_cycle(), CycleSlot::Data { .. }))
            .count();
        assert_eq!(n * 8, 88_200);
    }

    #[test]
    fn scheduler_48k_pattern() {
        // 48 kHz: 3 of every 4 cycles carry data, offsets step by 1024 ticks.
        let mut s = SytScheduler::new(Sfc::Hz48000);
        let got: [CycleSlot; 4] = core::array::from_fn(|_| s.next_cycle());
        assert_eq!(
            got,
            [
                CycleSlot::Data { offset: 0 },
                CycleSlot::Data { offset: 1024 },
                CycleSlot::Data { offset: 2048 },
                CycleSlot::NoData
            ]
        );
    }

    #[test]
    fn build_then_parse_roundtrip() {
        let mut b = PacketBuilder::new(1, 2, 1, Sfc::Hz48000);
        let mut p = PacketParser::new();
        let mut counter = 0i32;
        let mut src = || {
            let mut f = [0i32; 32];
            f[0] = counter;
            f[1] = -counter;
            counter += 1;
            Some(f)
        };
        let mut buf = [0u8; 256];
        let mut seen = 0i32;
        for cycle in 0..400u32 {
            let now = CycleTime::from_ticks(cycle * TICKS_PER_CYCLE);
            let (len, _) = b.build(now, &mut src, &mut buf);
            let ev = p
                .parse(&buf[..len], &mut |_, ch, s| {
                    if ch == 0 {
                        assert_eq!(s, seen);
                        seen += 1;
                    } else {
                        assert_eq!(s, -(seen - 1));
                    }
                })
                .unwrap();
            if let RxEvent::Data { syt, dbc_gap, .. } = ev {
                assert!(!dbc_gap);
                assert!(syt.is_some());
            }
        }
        assert_eq!(seen, 300 * 8);
        assert_eq!(p.discontinuities, 0);
    }
}
