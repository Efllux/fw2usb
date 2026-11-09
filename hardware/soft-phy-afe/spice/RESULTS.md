# Behavioral results

Run with ngspice-47, `./run.sh`. Parameters and sampling windows are [verify]
engineering assumptions; this is not transistor or hardware qualification.

243 DC solves cover 81 port codes at three corners. No classification errors;
smallest driven differential 196.0 mV; largest opposing-drive residual 47.92 mV.
This residual is a collision result, not a driver-off voltage qualification.

Eight 1024-bit directional DS runs have no bit errors and 1023 recovered edges
each. Minimum signed sampled eye is 202.07 mV. See ds-results.csv and eye.png;
no random jitter, transistor skew, connector or cable frequency loss is modeled.

Balanced modeled peak CM droop is 11.95 mV; 100 uA mismatch gives 14.40 mV.
Intentionally losing a 4 mA leg gives 110.07 mV and crosses the minimum peer
S200 threshold for 22.45 ns: balancing failures can look like speed signaling.
This is a raw crossing, not a qualified peer speed-detect event.

Powered-peer bias cases 1.665/1.86/2.015 V are detected; zero bias is not.
Nine dynamic arbitration states at both ends classify correctly at 200 ns.
Unpowered-peer probes, powered-off leakage, bias-loop stability and ESD/EOS
remain untested. Full numeric results are in results.json.
