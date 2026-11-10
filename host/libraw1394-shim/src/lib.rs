//! Independently implemented subset of the libraw1394 ABI over FW2R.
//! Each handle belongs to one thread. C pointers must remain valid for their
//! documented length; callbacks must not destroy/reenter the active handle.
//! Read/write buffers and lock scalars retain the raw1394 wire-order convention.
//! No GPL/LGPL implementation is incorporated; API facts are documented in README.
use fw2usb_cli::{
    client::Session,
    transport::{Replay, Transport, Usb},
};
use std::{
    ffi::{c_int, c_void},
    ptr,
};
type Reset = Option<unsafe extern "C" fn(*mut Handle, u32) -> c_int>;
type Receive =
    Option<unsafe extern "C" fn(*mut Handle, *mut u8, u32, u8, u8, u8, u32, u32) -> c_int>;
struct Iso {
    channel: u8,
    maximum: u32,
    packets: u32,
    callback: Receive,
    lease: Option<u32>,
    sequence: Option<u32>,
    dropped: u32,
}
pub struct Handle {
    session: Option<Session>,
    local: u16,
    nodes: u16,
    userdata: *mut c_void,
    reset: Reset,
    iso: Option<Iso>,
}
#[repr(C)]
struct PortInfo {
    nodes: c_int,
    name: [u8; 32],
}
fn errno(code: c_int) -> c_int {
    unsafe {
        #[cfg(target_os = "macos")]
        {
            *libc::__error() = code;
        }
        #[cfg(target_os = "linux")]
        {
            *libc::__errno_location() = code;
        }
    }
    -1
}
fn open() -> Result<Session, ()> {
    let transport: Box<dyn Transport> = if let Ok(path) = std::env::var("FW2USB_REPLAY") {
        Box::new(Replay::open(&path).map_err(|_| ())?)
    } else {
        Box::new(Usb::open(std::env::var("FW2USB_SERIAL").ok().as_deref()).map_err(|_| ())?)
    };
    Ok(Session::new(transport, 0))
}
impl Handle {
    fn session(&mut self) -> Result<&mut Session, ()> {
        if self.session.is_none() {
            let mut session = open()?;
            let info = session.call(3, vec![]).map_err(|_| ())?;
            if info.len() != 8 {
                return Err(());
            }
            self.local = u16::from_le_bytes([info[0], info[1]]) | 0xffc0;
            self.nodes = u16::from_le_bytes([info[4], info[5]]);
            self.session = Some(session);
        }
        self.session.as_mut().ok_or(())
    }
}
unsafe fn get<'a>(h: *mut Handle) -> Result<&'a mut Handle, c_int> {
    h.as_mut().ok_or_else(|| errno(libc::EINVAL))
}
#[no_mangle]
unsafe extern "C" fn raw1394_new_handle() -> *mut Handle {
    Box::into_raw(Box::new(Handle {
        session: None,
        local: 0xffff,
        nodes: 0,
        userdata: ptr::null_mut(),
        reset: None,
        iso: None,
    }))
}
#[no_mangle]
unsafe extern "C" fn raw1394_destroy_handle(h: *mut Handle) {
    if !h.is_null() {
        raw1394_iso_shutdown(h);
        drop(Box::from_raw(h));
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_set_port(h: *mut Handle, port: c_int) -> c_int {
    let Ok(h) = get(h) else {
        return -1;
    };
    if port != 0 {
        return errno(libc::ENODEV);
    }
    if h.session().is_err() {
        errno(libc::ENODEV)
    } else {
        0
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_new_handle_on_port(port: c_int) -> *mut Handle {
    let h = raw1394_new_handle();
    if raw1394_set_port(h, port) < 0 {
        raw1394_destroy_handle(h);
        ptr::null_mut()
    } else {
        h
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_get_port_info(h: *mut Handle, p: *mut PortInfo, max: c_int) -> c_int {
    let Ok(h) = get(h) else {
        return -1;
    };
    if max < 0 || (max > 0 && p.is_null()) {
        return errno(libc::EINVAL);
    }
    if h.session().is_err() {
        return errno(libc::ENODEV);
    }
    if max > 0 {
        let mut name = [0; 32];
        name[..10].copy_from_slice(b"fw2usb USB");
        p.write(PortInfo {
            nodes: h.nodes as c_int,
            name,
        });
    }
    1
}
#[no_mangle]
unsafe extern "C" fn raw1394_get_local_id(h: *mut Handle) -> u16 {
    get(h).map(|h| h.local).unwrap_or(0xffff)
}
#[no_mangle]
unsafe extern "C" fn raw1394_get_nodecount(h: *mut Handle) -> c_int {
    get(h).map(|h| h.nodes as c_int).unwrap_or(-1)
}
#[no_mangle]
unsafe extern "C" fn raw1394_get_generation(h: *mut Handle) -> u32 {
    get(h)
        .ok()
        .and_then(|h| h.session.as_ref().map(|s| s.generation))
        .unwrap_or(0)
}
#[no_mangle]
unsafe extern "C" fn raw1394_update_generation(h: *mut Handle, g: u32) {
    if let Ok(h) = get(h) {
        if let Some(s) = h.session.as_mut() {
            s.generation = g;
        }
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_set_userdata(h: *mut Handle, data: *mut c_void) {
    if let Ok(h) = get(h) {
        h.userdata = data;
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_get_userdata(h: *mut Handle) -> *mut c_void {
    get(h).map(|h| h.userdata).unwrap_or(ptr::null_mut())
}
#[no_mangle]
unsafe extern "C" fn raw1394_set_bus_reset_handler(h: *mut Handle, cb: Reset) -> Reset {
    get(h)
        .ok()
        .and_then(|h| std::mem::replace(&mut h.reset, cb))
}
#[no_mangle]
unsafe extern "C" fn raw1394_read(
    h: *mut Handle,
    node: u16,
    address: u64,
    length: usize,
    data: *mut u32,
) -> c_int {
    let Ok(h) = get(h) else {
        return -1;
    };
    if data.is_null() || length == 0 || length > 1_048_576 || !length.is_multiple_of(4) {
        return errno(libc::EINVAL);
    }
    match h
        .session()
        .and_then(|s| s.read(node, address, length as u32).map_err(|_| ()))
    {
        Ok(bytes) => {
            ptr::copy_nonoverlapping(bytes.as_ptr(), data.cast(), length);
            0
        }
        Err(_) => errno(libc::EIO),
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_write(
    h: *mut Handle,
    node: u16,
    address: u64,
    length: usize,
    data: *const u32,
) -> c_int {
    let Ok(h) = get(h) else {
        return -1;
    };
    if data.is_null() || length == 0 || length > 256 || !length.is_multiple_of(4) {
        return errno(libc::EINVAL);
    }
    let bytes = std::slice::from_raw_parts(data.cast::<u8>(), length);
    match h.session().and_then(|s| {
        s.submit(
            node,
            address,
            if length == 4 { 0 } else { 1 },
            bytes,
            length as u32,
        )
        .map_err(|_| ())
    }) {
        Ok(_) => 0,
        Err(_) => errno(libc::EIO),
    }
}
fn lock(s: &mut Session, node: u16, address: u64, data: &[u8], arg: &[u8]) -> Result<Vec<u8>, ()> {
    if address >= 1 << 48 || address & 3 != 0 {
        return Err(());
    }
    let mut p = Vec::new();
    p.extend(node.to_le_bytes());
    p.extend([9, 2]);
    p.extend(address.to_le_bytes());
    p.extend(2u16.to_le_bytes());
    p.extend(0u16.to_le_bytes());
    p.extend(((data.len() + arg.len()) as u32).to_le_bytes());
    p.extend(200_000u32.to_le_bytes());
    p.extend(arg);
    p.extend(data);
    let r = s.call(0x100, p).map_err(|_| ())?;
    if r.len() != 16 + data.len()
        || r[1] != 0
        || u32::from_le_bytes(r[4..8].try_into().map_err(|_| ())?) as usize != data.len()
    {
        return Err(());
    }
    Ok(r[16..].to_vec())
}
macro_rules! lock_export {
    ($name:ident,$ty:ty) => {
        #[no_mangle]
        unsafe extern "C" fn $name(
            h: *mut Handle,
            node: u16,
            address: u64,
            extended: u32,
            data: $ty,
            arg: $ty,
            result: *mut $ty,
        ) -> c_int {
            if result.is_null() {
                return errno(libc::EINVAL);
            }
            if extended != 2 {
                return errno(libc::ENOTSUP);
            }
            let Ok(h) = get(h) else {
                return -1;
            };
            match h
                .session()
                .and_then(|s| lock(s, node, address, &data.to_ne_bytes(), &arg.to_ne_bytes()))
            {
                Ok(r) => {
                    ptr::copy_nonoverlapping(r.as_ptr(), result.cast(), r.len());
                    0
                }
                Err(_) => errno(libc::EIO),
            }
        }
    };
}
lock_export!(raw1394_lock, u32);
lock_export!(raw1394_lock64, u64);
#[no_mangle]
unsafe extern "C" fn raw1394_get_irm_id(h: *mut Handle) -> u16 {
    let Ok(h) = get(h) else {
        return 0xffff;
    };
    let Ok(bytes) = h.session().and_then(|s| s.call(4, vec![]).map_err(|_| ())) else {
        errno(libc::EIO);
        return 0xffff;
    };
    if !bytes.len().is_multiple_of(8) {
        errno(libc::EIO);
        return 0xffff;
    }
    let mut irm = 0xffff;
    for pair in bytes.as_chunks::<8>().0 {
        let a = u32::from_be_bytes(pair[..4].try_into().unwrap());
        let b = u32::from_be_bytes(pair[4..].try_into().unwrap());
        let Ok(sid) = fw_phy_model::selfid::SelfId0::decode([a, b]) else {
            errno(libc::EIO);
            return 0xffff;
        };
        if sid.link_active && sid.contender {
            irm = 0xffc0 | u16::from(sid.phy_id);
        }
    }
    irm
}
#[no_mangle]
unsafe extern "C" fn raw1394_iso_recv_init(
    h: *mut Handle,
    cb: Receive,
    packets: u32,
    maximum: u32,
    channel: u8,
    mode: c_int,
    _irq: c_int,
) -> c_int {
    let Ok(h) = get(h) else {
        return -1;
    };
    if h.iso.is_some() {
        return errno(libc::EBUSY);
    }
    if cb.is_none()
        || packets == 0
        || packets > 64
        || maximum == 0
        || maximum > 4096
        || channel > 63
        || !matches!(mode, -1 | 1 | 2)
    {
        return errno(libc::EINVAL);
    }
    h.iso = Some(Iso {
        channel,
        maximum,
        packets,
        callback: cb,
        lease: None,
        sequence: None,
        dropped: 0,
    });
    0
}
#[no_mangle]
unsafe extern "C" fn raw1394_iso_recv_start(
    h: *mut Handle,
    cycle: c_int,
    _tag: c_int,
    _sync: c_int,
) -> c_int {
    if cycle != -1 || _tag != -1 || _sync != 0 {
        return errno(libc::ENOTSUP);
    }
    let Ok(h) = get(h) else {
        return -1;
    };
    let Some(i) = h.iso.as_ref() else {
        return errno(libc::EINVAL);
    };
    if i.lease.is_some() {
        return errno(libc::EBUSY);
    }
    let mut p = vec![0, i.channel, 2, 0];
    p.extend(i.maximum.to_le_bytes());
    p.extend(i.packets.to_le_bytes());
    match h.session().and_then(|s| s.call(0x200, p).map_err(|_| ())) {
        Ok(r) if r.len() >= 4 => {
            h.iso.as_mut().unwrap().lease = Some(u32::from_le_bytes(r[..4].try_into().unwrap()));
            h.iso.as_mut().unwrap().sequence = None;
            h.iso.as_mut().unwrap().dropped = 0;
            0
        }
        _ => errno(libc::EIO),
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_iso_stop(handle: *mut Handle) {
    if let Ok(h) = get(handle) {
        let lease = h.iso.as_mut().and_then(|i| i.lease.take());
        if let Some(lease) = lease {
            if h.session()
                .and_then(|s| s.call(0x202, lease.to_le_bytes().to_vec()).map_err(|_| ()))
                .is_err()
            {
                errno(libc::EIO);
            }
        }
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_iso_shutdown(h: *mut Handle) {
    raw1394_iso_stop(h);
    if let Ok(h) = get(h) {
        h.iso = None;
    }
}
#[no_mangle]
unsafe extern "C" fn raw1394_loop_iterate(handle: *mut Handle) -> c_int {
    let Ok(h) = get(handle) else {
        return -1;
    };
    let frame = match h.session().and_then(|s| s.transport.next().map_err(|_| ())) {
        Ok(Some(f)) => f,
        Ok(None) => return errno(libc::EAGAIN),
        Err(_) => return errno(libc::EIO),
    };
    if frame.opcode == 0x8000 {
        h.local = 0xffff;
        h.nodes = 0;
        if let Some(i) = h.iso.as_mut() {
            i.lease = None;
            i.sequence = None;
        }
        if let Some(cb) = h.reset {
            return cb(handle, frame.generation);
        }
        raw1394_update_generation(handle, frame.generation);
        return 0;
    }
    if frame.opcode == 0x203 {
        return errno(libc::EOVERFLOW);
    }
    if frame.opcode != 0x201 {
        return errno(libc::ENOTSUP);
    }
    let Some(i) = h.iso.as_mut() else {
        return errno(libc::ENOENT);
    };
    let mut p = frame.payload;
    if p.len() < 32 {
        return errno(libc::EPROTO);
    }
    let q = |o| u32::from_le_bytes(p[o..o + 4].try_into().unwrap());
    if Some(q(0)) != i.lease
        || Some(frame.generation) != h.session.as_ref().map(|s| s.generation)
        || q(4) != frame.generation
        || p[28] != i.channel
        || p[31] & 3 != 3
        || q(24) as usize != p.len() - 32
        || p.len() - 32 > i.maximum as usize
    {
        return errno(libc::EPROTO);
    }
    let seq = q(8);
    if let Some(old) = i.sequence {
        let delta = seq.wrapping_sub(old);
        if delta != 1 {
            if delta > 0 && delta < 0x8000_0000 {
                i.sequence = Some(seq);
                i.dropped = i.dropped.saturating_add(delta - 1);
            }
            return errno(libc::EOVERFLOW);
        }
    }
    i.sequence = Some(seq);
    let cb = i.callback.unwrap();
    let dropped = std::mem::take(&mut i.dropped);
    let (channel, tag, sy, cycle) = (p[28], p[29], p[30], (q(12) >> 12) & 0x1fff);
    let result = cb(
        handle,
        p[32..].as_mut_ptr(),
        (p.len() - 32) as u32,
        channel,
        tag,
        sy,
        cycle,
        dropped,
    );
    if result == 2 {
        return errno(libc::EIO);
    }
    if matches!(result, 3 | 4) {
        raw1394_iso_stop(handle);
    }
    0
}
#[no_mangle]
unsafe extern "C" fn raw1394_get_fd(_h: *mut Handle) -> c_int {
    errno(libc::ENOTSUP)
}
#[no_mangle]
unsafe extern "C" fn raw1394_reset_bus(_h: *mut Handle, _kind: c_int) -> c_int {
    errno(libc::ENOTSUP)
}
#[no_mangle]
unsafe extern "C" fn raw1394_wake_up(_h: *mut Handle) -> c_int {
    errno(libc::ENOTSUP)
}

unsafe fn resource(handle: *mut Handle, amount: u32, mode: c_int, channel: bool) -> c_int {
    if !matches!(mode, 0 | 1) || (channel && amount > 63) || (!channel && amount > 4915) {
        return errno(libc::EINVAL);
    }
    let irm = raw1394_get_irm_id(handle);
    if irm == 0xffff {
        return errno(libc::ENODEV);
    }
    let offset = if channel {
        0xffff_f000_0224 + u64::from(amount / 32) * 4
    } else {
        0xffff_f000_0220
    };
    // Retry only a confirmed compare mismatch. A transport failure is terminal.
    for _ in 0..8 {
        let mut old_wire = 0u32;
        if raw1394_read(handle, irm, offset, 4, &mut old_wire) < 0 {
            return -1;
        }
        let old = u32::from_be(old_wire);
        let new = if channel {
            let bit = 1 << (31 - amount % 32);
            if mode == 0 {
                if old & bit == 0 {
                    return errno(libc::EBUSY);
                }
                old & !bit
            } else {
                old | bit
            }
        } else if mode == 0 {
            let Some(n) = old.checked_sub(amount) else {
                return errno(libc::ENOSPC);
            };
            n
        } else {
            let Some(n) = old.checked_add(amount).filter(|n| *n <= 4915) else {
                return errno(libc::EINVAL);
            };
            n
        };
        let mut result = 0u32;
        if raw1394_lock(handle, irm, offset, 2, new.to_be(), old_wire, &mut result) < 0 {
            return -1;
        }
        if result == old_wire {
            return 0;
        }
    }
    errno(libc::EBUSY)
}
#[no_mangle]
unsafe extern "C" fn raw1394_bandwidth_modify(
    h: *mut Handle,
    bandwidth: u32,
    mode: c_int,
) -> c_int {
    resource(h, bandwidth, mode, false)
}
#[no_mangle]
unsafe extern "C" fn raw1394_channel_modify(h: *mut Handle, channel: u32, mode: c_int) -> c_int {
    resource(h, channel, mode, true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use fw2usb_cli::wire::Frame;
    struct Mock {
        events: std::collections::VecDeque<Frame>,
    }
    impl Transport for Mock {
        fn exchange(&mut self, r: Frame) -> Result<Frame, Box<dyn std::error::Error>> {
            let mut payload = vec![];
            match r.opcode {
                0x100 => {
                    let t = r.payload[2];
                    let n = u32::from_le_bytes(r.payload[16..20].try_into()?) as usize;
                    if t == 9 {
                        assert_eq!(&r.payload[12..14], &[2, 0]);
                        assert_eq!(&r.payload[24..28], &[1, 2, 3, 4]);
                    }
                    let bytes = if t == 4 {
                        vec![0x12, 0x34, 0x56, 0x78]
                    } else if t == 9 {
                        vec![0x22; n / 2]
                    } else {
                        vec![]
                    };
                    payload = vec![0; 16];
                    payload[4..8].copy_from_slice(&(bytes.len() as u32).to_le_bytes());
                    payload.extend(bytes);
                }
                0x200 => payload.extend(7u32.to_le_bytes()),
                0x202 => assert_eq!(r.payload, 7u32.to_le_bytes()),
                _ => return Err("unexpected command".into()),
            }
            Ok(Frame {
                kind: 1,
                opcode: if r.opcode == 0x100 { 0x101 } else { r.opcode },
                id: r.id,
                status: 0,
                generation: r.generation,
                payload,
            })
        }
        fn next(&mut self) -> Result<Option<Frame>, Box<dyn std::error::Error>> {
            Ok(self.events.pop_front())
        }
    }
    unsafe extern "C" fn reset(h: *mut Handle, g: u32) -> c_int {
        raw1394_update_generation(h, g);
        19
    }
    unsafe extern "C" fn receive(
        h: *mut Handle,
        p: *mut u8,
        n: u32,
        c: u8,
        tag: u8,
        sy: u8,
        cycle: u32,
        dropped: u32,
    ) -> c_int {
        assert_eq!(std::slice::from_raw_parts(p, n as usize), &[1, 2, 3, 4]);
        assert_eq!((c, tag, sy, cycle, dropped), (3, 1, 2, 123, 0));
        *(raw1394_get_userdata(h) as *mut u32) += 1;
        3
    }
    #[test]
    fn irm_cas_race_and_exhaustion() {
        use std::{cell::Cell, rc::Rc};
        struct Resource {
            value: Rc<Cell<u32>>,
            race: bool,
        }
        impl Transport for Resource {
            fn next(&mut self) -> Result<Option<Frame>, Box<dyn std::error::Error>> {
                Ok(None)
            }
            fn exchange(&mut self, r: Frame) -> Result<Frame, Box<dyn std::error::Error>> {
                let mut p = vec![];
                if r.opcode == 4 {
                    // Packet-zero contender with active link; port semantics are
                    // irrelevant to the IRM selection fact under test.
                    let a = 0x8040_0800u32;
                    p.extend(a.to_be_bytes());
                    p.extend((!a).to_be_bytes());
                } else {
                    assert_eq!(r.opcode, 0x100);
                    let mut old = self.value.get();
                    if r.payload[2] == 9 {
                        if self.race {
                            self.race = false;
                            old -= 1;
                            self.value.set(old);
                        }
                        let compare = u32::from_be_bytes(r.payload[24..28].try_into()?);
                        let new = u32::from_be_bytes(r.payload[28..32].try_into()?);
                        if compare == old {
                            self.value.set(new);
                        }
                    }
                    p = vec![0; 16];
                    p[4..8].copy_from_slice(&4u32.to_le_bytes());
                    p.extend(old.to_be_bytes());
                }
                Ok(Frame {
                    kind: 1,
                    opcode: if r.opcode == 0x100 { 0x101 } else { r.opcode },
                    id: r.id,
                    status: 0,
                    generation: r.generation,
                    payload: p,
                })
            }
        }
        unsafe {
            let value = Rc::new(Cell::new(4915));
            let h = raw1394_new_handle();
            (*h).session = Some(Session::new(
                Box::new(Resource {
                    value: value.clone(),
                    race: true,
                }),
                1,
            ));
            assert_eq!(raw1394_bandwidth_modify(h, 100, 0), 0);
            assert_eq!(value.get(), 4814);
            assert_eq!(raw1394_bandwidth_modify(h, 100, 1), 0);
            assert_eq!(value.get(), 4914);
            assert_eq!(raw1394_bandwidth_modify(h, 4915, 0), -1);
            assert_eq!(value.get(), 4914);
            value.set(u32::MAX);
            assert_eq!(raw1394_channel_modify(h, 31, 0), 0);
            assert_eq!(value.get(), u32::MAX - 1);
            assert_eq!(raw1394_channel_modify(h, 31, 0), -1);
            assert_eq!(raw1394_channel_modify(h, 31, 1), 0);
            assert_eq!(value.get(), u32::MAX);
            raw1394_destroy_handle(h);
        }
    }
    #[test]
    fn ffi_core_and_reset_iso_callbacks() {
        unsafe {
            let mut payload = vec![0; 36];
            payload[..4].copy_from_slice(&7u32.to_le_bytes());
            payload[4..8].copy_from_slice(&1u32.to_le_bytes());
            payload[12..16].copy_from_slice(&(123u32 << 12).to_le_bytes());
            payload[24..28].copy_from_slice(&4u32.to_le_bytes());
            payload[28..32].copy_from_slice(&[3, 1, 2, 3]);
            payload[32..].copy_from_slice(&[1, 2, 3, 4]);
            let events = std::collections::VecDeque::from([
                Frame {
                    kind: 2,
                    opcode: 0x201,
                    id: 0,
                    status: 0,
                    generation: 1,
                    payload,
                },
                Frame {
                    kind: 2,
                    opcode: 0x8000,
                    id: 0,
                    status: 0,
                    generation: 2,
                    payload: vec![],
                },
            ]);
            let h = raw1394_new_handle();
            (*h).session = Some(Session::new(Box::new(Mock { events }), 1));
            (*h).local = 0xffc0;
            (*h).nodes = 2;
            let mut word = 0u32;
            assert_eq!(raw1394_read(h, 1, 0x400, 4, &mut word), 0);
            assert_eq!(word.to_ne_bytes(), [0x12, 0x34, 0x56, 0x78]);
            assert_eq!(raw1394_write(h, 1, 0x400, 4, &word), 0);
            let mut old = 0u32;
            assert_eq!(
                raw1394_lock(
                    h,
                    1,
                    0x400,
                    2,
                    word,
                    u32::from_ne_bytes([1, 2, 3, 4]),
                    &mut old
                ),
                0
            );
            assert_eq!(old.to_ne_bytes(), [0x22; 4]);
            let mut seen = 0u32;
            raw1394_set_userdata(h, (&mut seen as *mut u32).cast());
            assert_eq!(
                raw1394_iso_recv_init(h, Some(receive), 1, 512, 3, -1, -1),
                0
            );
            assert_eq!(raw1394_iso_recv_start(h, -1, -1, 0), 0);
            assert_eq!(raw1394_loop_iterate(h), 0);
            assert_eq!(seen, 1);
            raw1394_set_bus_reset_handler(h, Some(reset));
            assert_eq!(raw1394_loop_iterate(h), 19);
            assert_eq!(raw1394_get_generation(h), 2);
            assert_eq!(raw1394_get_local_id(h), 0xffff);
            assert_eq!(raw1394_get_nodecount(h), 0);
            raw1394_destroy_handle(h);
        }
    }
    #[test]
    fn review_sequence_gap_recovers() {
        unsafe extern "C" fn keep(
            _: *mut Handle,
            _: *mut u8,
            _: u32,
            _: u8,
            _: u8,
            _: u8,
            _: u32,
            _: u32,
        ) -> c_int {
            0
        }
        unsafe {
            let mut events = std::collections::VecDeque::new();
            for seq in [0u32, 2, 3, u32::MAX, 0] {
                let mut payload = vec![0; 36];
                payload[..4].copy_from_slice(&7u32.to_le_bytes());
                payload[4..8].copy_from_slice(&1u32.to_le_bytes());
                payload[8..12].copy_from_slice(&seq.to_le_bytes());
                payload[24..28].copy_from_slice(&4u32.to_le_bytes());
                payload[28..32].copy_from_slice(&[3, 1, 0, 3]);
                events.push_back(Frame {
                    kind: 2,
                    opcode: 0x201,
                    id: 0,
                    status: 0,
                    generation: 1,
                    payload,
                });
            }
            let h = raw1394_new_handle();
            (*h).session = Some(Session::new(Box::new(Mock { events }), 1));
            assert_eq!(raw1394_iso_recv_init(h, Some(keep), 1, 512, 3, -1, -1), 0);
            assert_eq!(raw1394_iso_recv_start(h, -1, -1, 0), 0);
            assert_eq!(raw1394_loop_iterate(h), 0);
            assert_eq!(raw1394_loop_iterate(h), -1);
            assert_eq!(
                raw1394_loop_iterate(h),
                0,
                "one lost packet must not poison all later sequence numbers"
            );
            raw1394_iso_stop(h);
            assert_eq!(raw1394_iso_recv_start(h, -1, -1, 0), 0);
            assert_eq!(
                raw1394_loop_iterate(h),
                0,
                "new lease accepts fresh sequence baseline"
            );
            assert_eq!(raw1394_loop_iterate(h), 0, "sequence wraps MAX to zero");
            raw1394_destroy_handle(h);
        }
    }
}
