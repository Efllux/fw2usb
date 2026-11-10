use crate::{transport::Transport, wire::Frame};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub struct Session {
    pub transport: Box<dyn Transport>,
    pub generation: u32,
    id: u32,
}
impl Session {
    pub fn new(transport: Box<dyn Transport>, generation: u32) -> Self {
        Self {
            transport,
            generation,
            id: 0,
        }
    }
    pub fn call(&mut self, opcode: u16, payload: Vec<u8>) -> Result<Vec<u8>> {
        self.id = self.id.checked_add(1).ok_or("request cookie exhausted")?;
        let response = self.transport.exchange(Frame {
            kind: 0,
            opcode,
            id: self.id,
            status: 0,
            generation: self.generation,
            payload,
        })?;
        if opcode == 3 && response.status == 0 {
            self.generation = response.generation;
        }
        if response.generation != self.generation || response.status != 0 || response.id != self.id
        {
            return Err("failed/stale completion".into());
        }
        if response.opcode != if opcode == 0x100 { 0x101 } else { opcode } {
            return Err("wrong completion opcode".into());
        }
        Ok(response.payload)
    }
    pub fn submit(
        &mut self,
        node: u16,
        address: u64,
        tcode: u8,
        data: &[u8],
        length: u32,
    ) -> Result<Vec<u8>> {
        if address >= 1 << 48 || address & 3 != 0 {
            return Err("unaligned/invalid address".into());
        }
        let mut payload = Vec::new();
        payload.extend(node.to_le_bytes());
        payload.extend([tcode, 2]);
        payload.extend(address.to_le_bytes());
        payload.extend(0u16.to_le_bytes());
        payload.extend(0u16.to_le_bytes());
        payload.extend(length.to_le_bytes());
        payload.extend(200_000u32.to_le_bytes());
        payload.extend(data);
        let response = self.call(0x100, payload)?;
        if response.len() < 16 || response[1] != 0 {
            return Err("FireWire transaction failed".into());
        }
        let len = u32::from_le_bytes(response[4..8].try_into()?) as usize;
        if response.len() != 16 + len {
            return Err("malformed async completion".into());
        }
        Ok(response[16..].to_vec())
    }
    pub fn iso_credit(&mut self, handle: u32, packets: u32, bytes: u32) -> Result<()> {
        let mut p = Vec::new();
        p.extend(handle.to_le_bytes());
        p.extend(packets.to_le_bytes());
        p.extend(bytes.to_le_bytes());
        self.call(0x204, p)?;
        Ok(())
    }
    pub fn read(&mut self, node: u16, address: u64, length: u32) -> Result<Vec<u8>> {
        if length == 0 || length > 1_048_576 {
            return Err("read size outside host bound".into());
        }
        let mut data = Vec::with_capacity(length as usize);
        while data.len() < length as usize {
            let part = (length as usize - data.len()).min(256) as u32;
            let bytes = self.submit(
                node,
                address
                    .checked_add(data.len() as u64)
                    .ok_or("address overflow")?,
                if part == 4 { 4 } else { 5 },
                &[],
                part,
            )?;
            if bytes.len() != part as usize {
                return Err("short read response".into());
            }
            data.extend(bytes);
        }
        Ok(data)
    }
}
