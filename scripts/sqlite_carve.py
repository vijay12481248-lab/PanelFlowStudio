"""Read-only carver: pull table rows out of every b-tree leaf page of a SQLite file, including pages that were freed.

SQLite does not wipe a freed page, so rows deleted from a table (or a table that was emptied) can still be decoded from the file.
Usage as a module: `for page_no, rowid, values in carve(path): ...` (values is a list of str/int/float/bytes/None).
Overflow chains are followed; a record whose chain is broken or overwritten is skipped, never guessed.
"""
from __future__ import annotations

import struct
from pathlib import Path


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for i in range(9):
        b = buf[pos + i]
        if i == 8:
            return (value << 8) | b, pos + 9
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos + i + 1
    raise ValueError("varint")


_FIXED = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8, 7: 8, 8: 0, 9: 0}


def _record(payload: bytes) -> list | None:
    try:
        hdr_len, pos = _varint(payload, 0)
        types, end = [], hdr_len
        while pos < end:
            t, pos = _varint(payload, pos)
            types.append(t)
        out, p = [], hdr_len
        for t in types:
            if t == 0:
                out.append(None)
            elif t == 8:
                out.append(0)
            elif t == 9:
                out.append(1)
            elif t in (1, 2, 3, 4, 5, 6):
                n = _FIXED[t]
                out.append(int.from_bytes(payload[p:p + n], "big", signed=True))
                p += n
            elif t == 7:
                out.append(struct.unpack(">d", payload[p:p + 8])[0])
                p += 8
            elif t >= 12:
                n = (t - 12) // 2 if t % 2 == 0 else (t - 13) // 2
                raw = payload[p:p + n]
                if len(raw) != n:
                    return None
                out.append(raw if t % 2 == 0 else raw.decode("utf-8", "strict"))
                p += n
            else:
                return None
        return out
    except (IndexError, ValueError, UnicodeDecodeError, struct.error):
        return None


def carve(path: str | Path):
    data = Path(path).read_bytes()
    page_size = struct.unpack(">H", data[16:18])[0] or 65536
    reserved = data[20]
    usable = page_size - reserved
    total = len(data) // page_size
    max_local = usable - 35
    min_local = (usable - 12) * 32 // 255 - 23

    def page(n: int) -> bytes:
        return data[(n - 1) * page_size:n * page_size]

    for n in range(1, total + 1):
        pg = page(n)
        base = 100 if n == 1 else 0
        if pg[base] != 0x0D:        # table b-tree leaf
            continue
        cells = struct.unpack(">H", pg[base + 3:base + 5])[0]
        for i in range(cells):
            try:
                off = struct.unpack(">H", pg[base + 8 + 2 * i:base + 10 + 2 * i])[0]
                if off < base + 8 or off >= usable:
                    continue
                plen, p = _varint(pg, off)
                rowid, p = _varint(pg, p)
                if plen > max_local:
                    local = min_local + (plen - min_local) % (usable - 4)
                    local = local if local <= max_local else min_local
                    payload = bytearray(pg[p:p + local])
                    nxt = struct.unpack(">I", pg[p + local:p + local + 4])[0]
                    hops = 0
                    while nxt and len(payload) < plen and hops < 100000:
                        if not 1 <= nxt <= total:
                            payload = None
                            break
                        op = page(nxt)
                        payload += op[4:4 + min(usable - 4, plen - len(payload))]
                        nxt = struct.unpack(">I", op[:4])[0]
                        hops += 1
                    if payload is None or len(payload) < plen:
                        continue
                    payload = bytes(payload[:plen])
                else:
                    payload = pg[p:p + plen]
                    if len(payload) != plen:
                        continue
                vals = _record(payload)
                if vals:
                    yield n, rowid, vals
            except (IndexError, ValueError, struct.error):
                continue
