//! Peak IRM reservation, not average PCM bit rate.
//! Clean-room formula cross-check: Linux v6.12 sound/firewire/iso-resources.c
//! lines 48..76, 114..130; drivers/firewire/core.h BANDWIDTH_AVAILABLE_INITIAL.
use crate::{stream::PacketBuilder, Sfc};

pub const ISO_BUDGET_UNITS: u32 = 4915;
/// One bandwidth unit is one byte at S400: 1 / 49.152 MHz seconds.
pub const UNITS_PER_SECOND: u32 = 49_152_000;

/// Input is the CIP payload INCLUDING CIP header, speed is 0=S100..2=S400.
/// Overhead reserves prefix/end, arbitration and cable delay per Linux's
/// conservative accounting; cycle-start/asynchronous time is outside the
/// 4915-unit isochronous budget. Returns None for unsupported speeds/gap count.
pub const fn reservation(payload: u32, speed: u8, gap_count: u8) -> Option<u32> {
    if speed > 2 || gap_count > 63 {
        return None;
    }
    let overhead = if gap_count == 63 {
        512
    } else {
        (gap_count as u32 * 97) / 10 + 89
    };
    let Some(aligned) = payload.checked_add(3) else {
        return None;
    };
    let Some(bytes) = (aligned & !3).checked_add(12) else {
        return None;
    };
    let Some(units) = bytes.checked_mul(1 << (2 - speed)) else {
        return None;
    };
    units.checked_add(overhead)
}
/// Generic isochronous data field: works for CIP and custom/no-CIP streams.
/// `header_bytes` excludes the 1394 header and CRCs (added by reservation).
pub const fn stream_payload(header_bytes: u32, block_bytes: u32, max_blocks: u32) -> Option<u32> {
    let Some(data) = block_bytes.checked_mul(max_blocks) else {
        return None;
    };
    header_bytes.checked_add(data)
}

/// First S100/S200/S400 speed satisfying peak packet size and total IRM budget.
/// This is a capacity result, not evidence that device firmware accepts that speed.
pub fn minimum_speed(payloads: &[u32], gap_count: u8) -> Option<u8> {
    if payloads.is_empty() {
        return None;
    }
    for speed in 0..=2 {
        let mut sum = 0u32;
        let mut fits = true;
        for &payload in payloads {
            if payload > (1024 << speed) {
                fits = false;
                break;
            }
            sum = sum.checked_add(reservation(payload, speed, gap_count)?)?;
        }
        if fits && sum <= ISO_BUDGET_UNITS {
            return Some(speed);
        }
    }
    None
}

/// Use the existing packet builder as the authority for blocking packet length.
pub fn am824_peak_payload(pcm: u8, midi_slots: u8, rate: Sfc) -> Option<u32> {
    if pcm > 32 || pcm.checked_add(midi_slots)? == 0 {
        return None;
    }
    let builder = PacketBuilder::new(0, pcm, midi_slots, rate).ok()?;
    Some(builder.max_len() as u32)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn duplex(streams: &[(u8, u8)]) -> u32 {
        streams
            .iter()
            .map(|&(pcm, midi)| {
                reservation(am824_peak_payload(pcm, midi, Sfc::Hz48000).unwrap(), 0, 63).unwrap()
            })
            .sum()
    }
    #[test]
    fn saffire_48k_peak_budget() {
        // Source/channel provenance and profile caveats: docs/SOFT-PHY.md.
        assert_eq!(am824_peak_payload(10, 1, Sfc::Hz48000), Some(360));
        assert_eq!(duplex(&[(10, 1), (10, 1)]), 4000); // PRO10, PRO26 ADAT disabled
        assert_eq!(duplex(&[(26, 1), (26, 1)]), 8096); // PRO26 i/o max, fails
        assert_eq!(duplex(&[(16, 1), (8, 1)]), 4512); // PRO24/DSP
                                                      // PRO40 original: capture10+10, playback12+8; MIDI in first of each.
        assert_eq!(duplex(&[(10, 1), (10, 0), (12, 1), (8, 0)]), 7744);
        assert!(duplex(&[(10, 1), (10, 1)]) < ISO_BUDGET_UNITS);
        assert!(duplex(&[(16, 1), (8, 1)]) < ISO_BUDGET_UNITS);
        assert!(duplex(&[(26, 1), (26, 1)]) > ISO_BUDGET_UNITS);
        assert!(duplex(&[(10, 1), (10, 0), (12, 1), (8, 0)]) > ISO_BUDGET_UNITS);
        assert_eq!(reservation(360, 0, 5), Some(1625));
        assert_eq!(reservation(u32::MAX, 0, 63), None);
    }
    #[test]
    fn generic_payload_and_link_speed_selection() {
        assert_eq!(stream_payload(0, 18 * 4, 8), Some(576)); // RME FF400, no CIP
        assert_eq!(minimum_speed(&[576, 576], 63), Some(1));
        assert_eq!(minimum_speed(&[360, 360], 63), Some(0));
        assert_eq!(minimum_speed(&[872, 872], 63), Some(1));
        assert_eq!(minimum_speed(&[4096, 4096], 63), None);
        assert_eq!(minimum_speed(&[], 63), None);
        assert_eq!(stream_payload(8, u32::MAX, 2), None);
    }
    #[test]
    fn cross_family_peak_budgets() {
        let cases: &[(&[u32], [u32; 3], u8)] = &[
            (&[200], [1360, 936, 724], 0),           // OXFW FireWave
            (&[424, 424], [4512, 2768, 1896], 0),    // EFW AudioFire12
            (&[616, 616], [6048, 3536, 2280], 1),    // MOTU 828mkII, Digi002/003
            (&[648, 584], [6048, 3536, 2280], 1),    // TASCAM FW1884
            (&[896, 896], [8288, 4656, 2840], 1),    // RME FF800
            (&[1288, 1672], [12960, 6992, 4008], 2), // MOTU UltraLiteMk3 192k
            (&[1536, 1536], [13408, 7216, 4120], 2), // RME FF800 192k
        ];
        for &(payloads, expected, speed) in cases {
            for (scode, &want) in expected.iter().enumerate() {
                let got: u32 = payloads
                    .iter()
                    .map(|&p| reservation(p, scode as u8, 63).unwrap())
                    .sum();
                assert_eq!(got, want);
            }
            assert_eq!(minimum_speed(payloads, 63), Some(speed));
        }
    }
    #[test]
    fn s100_per_packet_limit_is_independent_of_duplex_budget() {
        assert!(am824_peak_payload(26, 1, Sfc::Hz48000).unwrap() <= 1024);
        assert!(am824_peak_payload(26, 1, Sfc::Hz96000).unwrap() > 1024);
        assert_eq!(am824_peak_payload(33, 0, Sfc::Hz48000), None);
        assert_eq!(reservation(360, 3, 63), None);
    }
}
