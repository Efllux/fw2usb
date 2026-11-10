//! FW2R v0 framing: PR16 raw tunnel contract, bounded byte stream parsing.
use std::io::{self, Read, Write};

#[derive(Clone, Debug)]
pub struct Frame {
    pub kind: u8,
    pub opcode: u16,
    pub id: u32,
    pub status: u32,
    pub generation: u32,
    pub payload: Vec<u8>,
}
fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}
impl Frame {
    pub fn read(reader: &mut dyn Read) -> io::Result<Option<Self>> {
        let mut header = [0u8; 24];
        match reader.read(&mut header[..1])? {
            0 => return Ok(None),
            1 => (),
            _ => unreachable!(),
        }
        reader.read_exact(&mut header[1..])?;
        if &header[..4] != b"FW2R" || header[4] != 0 || header[5] > 2 {
            return Err(invalid("invalid tunnel header"));
        }
        let get = |i| u32::from_le_bytes(header[i..i + 4].try_into().unwrap());
        let length = get(12) as usize;
        if length > 65536 - 24 {
            return Err(invalid("oversized tunnel frame"));
        }
        let mut payload = vec![0; length];
        reader.read_exact(&mut payload)?;
        let frame = Self {
            kind: header[5],
            opcode: u16::from_le_bytes([header[6], header[7]]),
            id: get(8),
            status: get(16),
            generation: get(20),
            payload,
        };
        if (frame.kind == 2) != (frame.id == 0) {
            return Err(invalid("invalid request cookie"));
        }
        Ok(Some(frame))
    }
    pub fn write(&self, writer: &mut dyn Write) -> io::Result<()> {
        if self.payload.len() > 65536 - 24 {
            return Err(invalid("oversized tunnel frame"));
        }
        let mut header = Vec::from(&b"FW2R\0"[..]);
        header.push(self.kind);
        header.extend(self.opcode.to_le_bytes());
        header.extend(self.id.to_le_bytes());
        header.extend((self.payload.len() as u32).to_le_bytes());
        header.extend(self.status.to_le_bytes());
        header.extend(self.generation.to_le_bytes());
        writer.write_all(&header)?;
        writer.write_all(&self.payload)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fragmented_roundtrip_and_bad_length() {
        let f = Frame {
            kind: 2,
            opcode: 0x201,
            id: 0,
            status: 0,
            generation: 7,
            payload: vec![0x55; 1025],
        };
        let mut bytes = Vec::new();
        f.write(&mut bytes).unwrap();
        struct Fragment<'a>(&'a [u8]);
        impl Read for Fragment<'_> {
            fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
                let n = out.len().min(self.0.len()).min(7);
                out[..n].copy_from_slice(&self.0[..n]);
                self.0 = &self.0[n..];
                Ok(n)
            }
        }
        assert_eq!(
            Frame::read(&mut Fragment(&bytes)).unwrap().unwrap().payload,
            f.payload
        );
        bytes[12..16].copy_from_slice(&65536u32.to_le_bytes());
        assert!(Frame::read(&mut &bytes[..]).is_err());
    }
}
