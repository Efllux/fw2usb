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
    pub fn compare_swap(
        &mut self,
        node: u16,
        address: u64,
        compare: &[u8],
        replacement: &[u8],
    ) -> Result<Vec<u8>> {
        if !matches!(compare.len(), 4 | 8)
            || compare.len() != replacement.len()
            || address >= 1 << 48
            || address & 3 != 0
        {
            return Err("invalid compare-swap parameters".into());
        }
        let mut p = Vec::new();
        p.extend(node.to_le_bytes());
        p.extend([9, 2]);
        p.extend(address.to_le_bytes());
        p.extend(2u16.to_le_bytes());
        p.extend(0u16.to_le_bytes());
        p.extend((compare.len() as u32 * 2).to_le_bytes());
        p.extend(200_000u32.to_le_bytes());
        p.extend(compare);
        p.extend(replacement);
        let r = self.call(0x100, p)?;
        if r.len() != 16 + compare.len()
            || r[1] != 0
            || u32::from_le_bytes(r[4..8].try_into()?) as usize != compare.len()
        {
            return Err("compare-swap failed".into());
        }
        Ok(r[16..].to_vec())
    }
    /// Native packed CYCLE_TIME and correlated 24.576 MHz monotonic ticks.
    pub fn clock_snapshot(&mut self) -> Result<(u32, u64)> {
        let r = self.call(5, Vec::new())?;
        if r.len() != 12 {
            return Err("malformed clock snapshot".into());
        }
        Ok((
            u32::from_le_bytes(r[..4].try_into()?),
            u64::from_le_bytes(r[4..].try_into()?),
        ))
    }
    pub fn iso_tx_create(&mut self, channel: u8, speed: u8, maximum: u32) -> Result<u32> {
        if channel > 63 || speed > 2 || maximum == 0 || maximum > 256 {
            return Err("invalid ISO TX lease".into());
        }
        let mut p = vec![1, channel, speed, 0];
        p.extend(maximum.to_le_bytes());
        p.extend(1u32.to_le_bytes());
        let r = self.call(0x200, p)?;
        if r.len() != 16 || u32::from_le_bytes(r[4..8].try_into()?) != maximum || r[12..] != [0; 4]
        {
            return Err("unsupported ISO TX allocation".into());
        }
        Ok(u32::from_le_bytes(r[..4].try_into()?))
    }
    /// Submit once. A transport error must never cause an automatic replay.
    pub fn iso_send(
        &mut self,
        handle: u32,
        channel: u8,
        tag: u8,
        sy: u8,
        target: u32,
        data: &[u8],
    ) -> Result<()> {
        if channel > 63
            || tag > 3
            || sy > 15
            || data.len() > 256
            || target & 4095 != 0
            || (target >> 12) & 8191 >= 8000
        {
            return Err("invalid ISO TX packet".into());
        }
        let mut p = Vec::new();
        for n in [handle, self.generation, 0, target] {
            p.extend(n.to_le_bytes());
        }
        p.extend(0u64.to_le_bytes());
        p.extend((data.len() as u32).to_le_bytes());
        p.extend([channel, tag, sy, 0]);
        p.extend(data);
        if !self.call(0x201, p)?.is_empty() {
            return Err("malformed ISO TX completion".into());
        }
        Ok(())
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::{cell::RefCell, rc::Rc};
    struct FailOnce(Rc<RefCell<Vec<Frame>>>);
    impl Transport for FailOnce {
        fn exchange(&mut self, request: Frame) -> Result<Frame> {
            self.0.borrow_mut().push(request);
            Err("uncertain wire completion".into())
        }
        fn next(&mut self) -> Result<Option<Frame>> {
            Ok(None)
        }
    }
    #[test]
    fn iso_tx_failure_is_single_submission_and_invalid_packet_never_posts() {
        let sent = Rc::new(RefCell::new(Vec::new()));
        let mut s = Session::new(Box::new(FailOnce(sent.clone())), 9);
        assert!(s.iso_send(4, 7, 1, 0, 12 << 12, b"abc").is_err());
        assert_eq!(sent.borrow().len(), 1);
        let frames = sent.borrow();
        let f = &frames[0];
        assert_eq!((f.opcode, f.generation), (0x201, 9));
        assert_eq!(&f.payload[0..8], &[4, 0, 0, 0, 9, 0, 0, 0]);
        assert_eq!(
            &f.payload[24..],
            &[3, 0, 0, 0, 7, 1, 0, 0, b'a', b'b', b'c']
        );
        drop(frames);
        for (channel, tag, sy, target, data) in [
            (64, 1, 0, 0, vec![]),
            (7, 4, 0, 0, vec![]),
            (7, 1, 16, 0, vec![]),
            (7, 1, 0, 1, vec![]),
            (7, 1, 0, 8000 << 12, vec![]),
            (7, 1, 0, 0, vec![0; 257]),
        ] {
            assert!(s.iso_send(4, channel, tag, sy, target, &data).is_err());
        }
        assert_eq!(sent.borrow().len(), 1);
    }
}
