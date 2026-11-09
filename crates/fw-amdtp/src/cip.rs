//! Common Isochronous Packet (CIP) two-quadlet header, IEC 61883-1.
//!
//! ```text
//! Q0: 0 0 | SID(6) | DBS(8) | FN(2) QPC(3) SPH(1) rsv(2) | DBC(8)
//! Q1: 1 0 | FMT(6) | FDF(8) | SYT(16)
//! ```

/// FMT value for AM824 audio & music data (IEC 61883-6).
pub const FMT_AM824: u8 = 0x10;
/// SYT value meaning "no timestamp in this packet".
pub const SYT_NO_INFO: u16 = 0xFFFF;
/// FDF value for an AM824 NO-DATA packet.
pub const FDF_NO_DATA: u8 = 0xFF;

/// Sampling frequency code carried in FDF for AM824 streams.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Sfc {
    Hz32000 = 0,
    Hz44100 = 1,
    Hz48000 = 2,
    Hz88200 = 3,
    Hz96000 = 4,
    Hz176400 = 5,
    Hz192000 = 6,
}

impl Sfc {
    pub const fn rate(self) -> u32 {
        match self {
            Sfc::Hz32000 => 32_000,
            Sfc::Hz44100 => 44_100,
            Sfc::Hz48000 => 48_000,
            Sfc::Hz88200 => 88_200,
            Sfc::Hz96000 => 96_000,
            Sfc::Hz176400 => 176_400,
            Sfc::Hz192000 => 192_000,
        }
    }

    /// Data blocks per SYT interval (one timestamp every `syt_interval` frames).
    pub const fn syt_interval(self) -> u32 {
        match self {
            Sfc::Hz32000 | Sfc::Hz44100 | Sfc::Hz48000 => 8,
            Sfc::Hz88200 | Sfc::Hz96000 => 16,
            Sfc::Hz176400 | Sfc::Hz192000 => 32,
        }
    }

    pub const fn from_code(code: u8) -> Option<Sfc> {
        Some(match code {
            0 => Sfc::Hz32000,
            1 => Sfc::Hz44100,
            2 => Sfc::Hz48000,
            3 => Sfc::Hz88200,
            4 => Sfc::Hz96000,
            5 => Sfc::Hz176400,
            6 => Sfc::Hz192000,
            _ => return None,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CipHeader {
    /// Source node ID (low 6 bits of the sender's node ID).
    pub sid: u8,
    /// Data block size in quadlets (= number of AM824 channels incl. MIDI slots).
    pub dbs: u8,
    /// Data block counter of the first data block in this packet.
    pub dbc: u8,
    pub fmt: u8,
    pub fdf: u8,
    pub syt: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CipError {
    TooShort,
    BadEoh,
    /// FN/QPC/SPH not zero: fractions/source packet headers are not used by AM824.
    Unsupported,
}

impl CipHeader {
    pub const LEN: usize = 8;

    pub fn is_no_data(&self) -> bool {
        self.fdf == FDF_NO_DATA || self.syt == SYT_NO_INFO
    }

    pub fn sfc(&self) -> Option<Sfc> {
        Sfc::from_code(self.fdf & 0x07)
    }

    pub fn encode(&self, out: &mut [u8; 8]) {
        let q0: u32 =
            ((self.sid as u32 & 0x3F) << 24) | ((self.dbs as u32) << 16) | self.dbc as u32;
        let q1: u32 = (0b10 << 30)
            | ((self.fmt as u32 & 0x3F) << 24)
            | ((self.fdf as u32) << 16)
            | self.syt as u32;
        out[..4].copy_from_slice(&q0.to_be_bytes());
        out[4..].copy_from_slice(&q1.to_be_bytes());
    }

    pub fn decode(buf: &[u8]) -> Result<CipHeader, CipError> {
        if buf.len() < 8 {
            return Err(CipError::TooShort);
        }
        let q0 = u32::from_be_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let q1 = u32::from_be_bytes([buf[4], buf[5], buf[6], buf[7]]);
        if q0 >> 30 != 0b00 || q1 >> 30 != 0b10 {
            return Err(CipError::BadEoh);
        }
        if (q0 >> 8) & 0xFF != 0 {
            return Err(CipError::Unsupported);
        }
        Ok(CipHeader {
            sid: ((q0 >> 24) & 0x3F) as u8,
            dbs: ((q0 >> 16) & 0xFF) as u8,
            dbc: (q0 & 0xFF) as u8,
            fmt: ((q1 >> 24) & 0x3F) as u8,
            fdf: ((q1 >> 16) & 0xFF) as u8,
            syt: (q1 & 0xFFFF) as u16,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        let h = CipHeader {
            sid: 0x3E,
            dbs: 10,
            dbc: 0xF8,
            fmt: FMT_AM824,
            fdf: Sfc::Hz48000 as u8,
            syt: 0x1234,
        };
        let mut b = [0u8; 8];
        h.encode(&mut b);
        // Known layout: 3E 0A 00 F8 | 90 02 12 34
        assert_eq!(b, [0x3E, 0x0A, 0x00, 0xF8, 0x90, 0x02, 0x12, 0x34]);
        assert_eq!(CipHeader::decode(&b).unwrap(), h);
        assert_eq!(h.sfc(), Some(Sfc::Hz48000));
    }

    #[test]
    fn rejects_bad_eoh() {
        assert_eq!(
            CipHeader::decode(&[0x80, 0, 0, 0, 0x90, 0, 0, 0]),
            Err(CipError::BadEoh)
        );
    }
}
