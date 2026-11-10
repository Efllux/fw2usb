//! Independently authored IEEE 1394 packet primitives, IEEE 1394-2008
//! §6.2.5.15 (CRC), §6.2.2 (async), §6.2.3 (iso). No driver code copied.
#![no_std]

/// MSB-first CRC-32, initial all ones, complemented on transmission.
pub fn crc32(bytes: &[u8]) -> u32 {
    let mut state = u32::MAX;
    for &byte in bytes {
        state ^= (byte as u32) << 24;
        for _ in 0..8 {
            state = (state << 1)
                ^ if state & 0x8000_0000 != 0 {
                    0x04c1_1db7
                } else {
                    0
                };
        }
    }
    !state
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    Length,
    HeaderCrc,
    DataCrc,
    Tcode,
    Field,
}

/// Append a big-endian header CRC to quadlet-aligned header bytes.
pub fn header_packet<'a>(header: &[u8], out: &'a mut [u8]) -> Result<&'a [u8], Error> {
    if !header.len().is_multiple_of(4) || out.len() < header.len() + 4 {
        return Err(Error::Length);
    }
    let n = header.len();
    out[..n].copy_from_slice(header);
    out[n..n + 4].copy_from_slice(&crc32(header).to_be_bytes());
    Ok(&out[..n + 4])
}

/// Iso wire packet; CRC covers the zero-padded final payload quadlet.
pub fn iso_packet<'a>(
    channel: u8,
    tag: u8,
    sy: u8,
    data: &[u8],
    out: &'a mut [u8],
) -> Result<&'a [u8], Error> {
    if channel > 63 || tag > 3 || sy > 15 || data.len() > u16::MAX as usize {
        return Err(Error::Field);
    }
    let padded = (data.len() + 3) & !3;
    let n = if data.is_empty() { 8 } else { 8 + padded + 4 };
    if out.len() < n {
        return Err(Error::Length);
    }
    let q = ((data.len() as u32) << 16)
        | ((tag as u32) << 14)
        | ((channel as u32) << 8)
        | 0xa0
        | sy as u32;
    out[..4].copy_from_slice(&q.to_be_bytes());
    let hcrc = crc32(&out[..4]);
    out[4..8].copy_from_slice(&hcrc.to_be_bytes());
    out[8..8 + padded].fill(0);
    out[8..8 + data.len()].copy_from_slice(data);
    if data.is_empty() {
        return Ok(&out[..8]);
    }
    let dcrc = crc32(&out[8..8 + padded]);
    out[8 + padded..n].copy_from_slice(&dcrc.to_be_bytes());
    Ok(&out[..n])
}

pub fn parse_iso(packet: &[u8]) -> Result<(u8, u8, u8, &[u8]), Error> {
    if packet.len() < 8 {
        return Err(Error::Length);
    }
    if packet[3] >> 4 != 0xa {
        return Err(Error::Tcode);
    }
    if crc32(&packet[..4]).to_be_bytes() != packet[4..8] {
        return Err(Error::HeaderCrc);
    }
    let len = u16::from_be_bytes([packet[0], packet[1]]) as usize;
    if len == 0 {
        return if packet.len() == 8 {
            Ok((packet[2] & 63, packet[2] >> 6, packet[3] & 15, &packet[8..]))
        } else {
            Err(Error::Length)
        };
    }
    let padded = (len + 3) & !3;
    if packet.len() != 12 + padded {
        return Err(Error::Length);
    }
    if crc32(&packet[8..8 + padded]).to_be_bytes() != packet[8 + padded..] {
        return Err(Error::DataCrc);
    }
    Ok((
        packet[2] & 63,
        packet[2] >> 6,
        packet[3] & 15,
        &packet[8..8 + len],
    ))
}

pub fn read_quadlet(
    destination: u16,
    source: u16,
    label: u8,
    offset: u64,
    out: &mut [u8],
) -> Result<&[u8], Error> {
    if label > 63 || offset >= 1 << 48 || offset & 3 != 0 {
        return Err(Error::Field);
    }
    let words = [
        ((destination as u32) << 16) | ((label as u32) << 10) | 0x140,
        ((source as u32) << 16) | (offset >> 32) as u32,
        offset as u32,
    ];
    let mut header = [0u8; 12];
    for (chunk, word) in header.as_chunks_mut::<4>().0.iter_mut().zip(words) {
        chunk.copy_from_slice(&word.to_be_bytes());
    }
    header_packet(&header, out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn crc_equations_and_corruption() {
        assert_eq!(crc32(b"123456789"), 0xfc89_1918);
        assert_eq!(crc32(&[]), 0);
        let mut bytes = [0; 16];
        let packet = header_packet(&[0; 12], &mut bytes).unwrap();
        // IEEE §6.2.5.15.3 checking remainder C(x), independent of message.
        assert_eq!(!crc32(packet), 0xc704_dd7b);
    }
    #[test]
    fn iso_padding_crc_and_errors() {
        let mut out = [0; 32];
        let packet = iso_packet(63, 1, 7, &[1, 2, 3, 4, 5], &mut out).unwrap();
        assert_eq!(parse_iso(packet), Ok((63, 1, 7, &[1, 2, 3, 4, 5][..])));
        let n = packet.len();
        out[8] ^= 1;
        assert_eq!(parse_iso(&out[..n]), Err(Error::DataCrc));
        out[0] ^= 1;
        assert_eq!(parse_iso(&out[..n]), Err(Error::HeaderCrc));
    }
}

pub mod topology;
