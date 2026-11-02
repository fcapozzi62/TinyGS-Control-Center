# AX.100 Mode 5: offline Stage2 Golay analyzer

This tool analyzes **raw post-syncword bytes** captured by TinyGS Stage2 on
the SX1262 in FSK packet mode. It makes no MQTT connection, never changes
the radio firmware, and does not decode a satellite payload.

It reproduces the 24-bit Golay systematic code from
`tinyGS/src/BitCode/golay24.cpp`, searches a bounded set of **bit offsets**
and reports minimum Hamming distance to all 4096 valid codewords.

```bash
cd ~/Scaricati/gitRoot/TinyGS-Control-Center
source .venv/bin/activate
python -m pip install -e .
tcc ax100-analyze examples/frontiersat-stage2-20261102-103915.hex
```

The fixture is the **255-byte FrontierSat dump** from the user on
2026-11-02 at 10:39:15. It starts with `EB AC EE`.

Expected key results:

- `at_expected_offset.raw_header_hex`: `EBACEE`
- `minimum_distance_bits`: **4**
- `golay_correctable`: **false**
- `nearest_candidate_count`: **6** (NOT one unique candidate)
- `rs_verified`: **false**
- Several shifted bit windows may pass the header and length checks.
  Such matches **do not prove** that the hardware was bit-misaligned.

To inspect every offset:

```bash
tcc ax100-analyze examples/frontiersat-stage2-20261102-103915.hex \\
  --max-shift-bits 31 --show-all
```

To analyze a different frame, copy **only the hex-byte columns** into
a text file, as whitespace-separated two-digit bytes, then run
`tcc ax100-analyze path/to/raw-frame.hex`. Do not include ASCII columns,
byte offsets or the RadioLib log prefix in the file.

The reported `candidate_length_feasible` checks the length extracted
from a uniquely correctable Golay header against received bytes and
the firmware's allowance for up to 3 missing RS symbols. It does **not**
test the descrambler, Reed–Solomon, CRC, actual syncword alignment or
the transmitted RF waveform.

Why caution is needed: extended Golay(24,12) has covering radius 4.
Any random 24-bit sequence is at distance at most 4 from some
valid codeword. A distance-4 result by itself therefore does **not**
prove that the RF signal was nearly correct. Many shifted candidates
also occur by chance. A later phase may add end-to-end RS/CRC validation
and multiple-frame correlations with actual radio timestamps.

For Stage2 `err=-3` means **uncorrectable Golay header** and RS has
not run. Separately, older Stage2 code uses `int eras_pos[3]` even
though `decode_rs_8` can write up to `NROOTS` corrected positions;
this is a distinct potential buffer overflow when RS processing is
reached and erasures are passed. It is not addressed by this offline
analyzer and requires a separate firmware patch/test.
