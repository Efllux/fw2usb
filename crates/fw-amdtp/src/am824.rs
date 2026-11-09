//! AM824 data channel quadlets (IEC 61883-6): 8-bit label + 24-bit payload.

/// Multi-bit linear audio, 24-bit raw sample.
pub const LABEL_MBLA_24: u8 = 0x40;
/// MIDI conformant data, 0 bytes valid (used to pad MIDI slots).
pub const LABEL_MIDI_NONE: u8 = 0x80;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Am824 {
    /// Signed 24-bit PCM sample, sign-extended into i32.
    Audio(i32),
    /// MIDI conformant data with 0..=3 valid bytes.
    Midi {
        count: u8,
        bytes: [u8; 3],
    },
    Other(u32),
}

#[inline]
pub fn encode_audio(sample24: i32) -> u32 {
    ((LABEL_MBLA_24 as u32) << 24) | (sample24 as u32 & 0x00FF_FFFF)
}

#[inline]
pub fn decode(q: u32) -> Am824 {
    let label = (q >> 24) as u8;
    match label {
        0x40..=0x43 => Am824::Audio(((q << 8) as i32) >> 8),
        0x80..=0x83 => Am824::Midi {
            count: label - 0x80,
            bytes: [(q >> 16) as u8, (q >> 8) as u8, q as u8],
        },
        _ => Am824::Other(q),
    }
}

/// Convert a 24-bit sample (in i32) to the left-justified i32 format USB Audio uses.
#[inline]
pub fn s24_to_s32(s: i32) -> i32 {
    s << 8
}

#[inline]
pub fn s32_to_s24(s: i32) -> i32 {
    s >> 8
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn audio_roundtrip_sign() {
        for s in [0, 1, -1, 0x7F_FFFF, -0x80_0000, 12345, -54321] {
            let q = encode_audio(s);
            assert_eq!(q >> 24, 0x40);
            assert_eq!(decode(q), Am824::Audio(s));
        }
    }

    #[test]
    fn midi() {
        assert_eq!(
            decode(0x8190_0000),
            Am824::Midi {
                count: 1,
                bytes: [0x90, 0, 0]
            }
        );
    }
}
