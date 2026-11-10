# CoreAudio AudioServerPlugIn design and skeleton

`make check` on macOS builds a loadable development bundle under target/coreaudio
and tests the actual SDK vtable through its factory, QueryInterface, properties and
IO rejection. No installation or signing is performed. All audio IO methods reject
unknown devices. The plug-in publishes an empty device list and immutable plug-in
properties; this is a skeleton, not an audio driver or an installed HAL component.
It uses public SDK declarations and independently written code.

The proposed bridge daemon owns USB/raw transport, discovery, CMP/vendor startup
and generation-scoped stream handles. CoreAudio's realtime methods must never
call nusb, allocate, take a mutex, log or perform IPC round trips. A control IPC
connection establishes bounded shared-memory SPSC capture/playback rings and a
clock-correlation snapshot using a versioned ABI. A packet loss/reset/daemon crash
increments an epoch. Before publishing a device, daemon supplies verified profile,
format, channel map and clock lock; after loss it marks the device unavailable
and notifies properties through the host control path. Never present a guessed
sample clock while an external FireWire source is stopped.

The future device exposes interleaved signed PCM32 (24 significant bits), one
capture and one playback stream, external device-master clock, nominal48k subset,
bounded buffer size and measured latency. Conversion from AM824/USB PCM24 happens
in the daemon/ring producer, not through SRC. StartIO validates the current epoch,
starts refcounted leases outside realtime context and then admits IO. The last
StopIO schedules teardown. Multiple clients share rings and clock state; app death
must release ownership without leaking FireWire reservations.

GetZeroTimeStamp must derive sample time/host mach_absolute_time/seed from a
measured common correlation (FireWire extended time + USB SOF + host monotonic),
using a bounded seqlock snapshot. Epoch/rate/clock-source change increments seed;
monotonic timestamps within an epoch must be tested under drift, lost packets and
sleep/wake. The Rust recovery model supplies a frequency estimate, not host time.
A production controller must request configuration changes via the host callback
and commit/abort on the matching callbacks; properties cannot mutate midway
through an IO cycle. Never use bulk-arrival time as audio presentation time.

Outstanding implementation: daemon IPC, shared rings, device/stream properties,
clock correlation, actual IO, multi-client tests, sandbox/signing/install/uninstall
and recovery on USB removal/suspend. These are explicit future tasks beyond this
requested design+skeleton. No DriverKit entitlement is assumed or requested.
The CFPlugIn type UUID matches the public SDK; the factory UUID is project-owned.
No vendor sample implementation was copied.

Primary reference: [Apple AudioServerPlugInDriverInterface](https://developer.apple.com/documentation/coreaudio/audioserverplugindriverinterface),
plus installed public CoreAudio AudioServerPlugIn.h/AudioHardwareBase.h definitions.
