from typing import List

_VERSIONS = {1: (26, 7, 1), 2: (44, 10, 1), 3: (70, 15, 1), 4: (100, 20, 1), 5: (134, 26, 1), 6: (172, 18, 2)}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 256:
        _x ^= 285
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n: int) -> List[int]:
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _mul(c, _EXP[i])
        g = nxt
    return g


def _rs_remainder(data: List[int], n: int) -> List[int]:
    gen = _rs_generator(n)
    rem = [0] * n
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        if f:
            for i in range(n):
                rem[i] ^= _mul(gen[i + 1], f)
    return rem


def _codewords(data: bytes, version: int) -> List[int]:
    total, ec, blocks = _VERSIONS[version]
    cap = total - ec * blocks
    bits = "0100" + format(len(data), "08b") + "".join((format(b, "08b") for b in data))
    bits += "0" * min(4, cap * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    words = [int(bits[i : i + 8], 2) for i in range(0, len(bits), 8)]
    pad = (236, 17)
    while len(words) < cap:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    size = cap // blocks
    chunks = [words[i * size : (i + 1) * size] for i in range(blocks)]
    eccs = [_rs_remainder(c, ec) for c in chunks]
    out = [c[i] for i in range(size) for c in chunks]
    out += [e[i] for i in range(ec) for e in eccs]
    return out


def _bch(value: int, poly: int, deg: int) -> int:
    v = value << deg
    top = poly.bit_length() - 1
    for i in range(v.bit_length() - 1, top - 1, (-1)):
        if v >> i & 1:
            v ^= poly << i - top
    return v


def _format_bits(mask: int) -> int:
    data = 8 | mask
    return (data << 10 | _bch(data, 1335, 10)) ^ 21522


def _build(version: int, words: List[int], mask: int):
    n = 17 + 4 * version
    mod = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(x, y, dark, func=True):
        if 0 <= x < n and 0 <= y < n:
            mod[y][x] = dark
            if func:
                fn[y][x] = True

    for cx, cy in [(3, 3), (n - 4, 3), (3, n - 4)]:
        for dy in range((-4), 5):
            for dx in range((-4), 5):
                d = max(abs(dx), abs(dy))
                put(cx + dx, cy + dy, d != 4 and d != 2)
    for i in range(8, n - 8):
        put(i, 6, i % 2 == 0)
        put(6, i, i % 2 == 0)
    pos = _ALIGN[version]
    for cy in pos:
        for cx in pos:
            if cx == 6 and cy == 6 or (cx == 6 and cy == pos[(-1)]) or (cx == pos[(-1)] and cy == 6):
                continue
            else:
                for dy in range((-2), 3):
                    for dx in range((-2), 3):
                        put(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    fb = _format_bits(mask)

    def bit(i):
        return bool(fb >> i & 1)

    for i in range(6):
        put(8, i, bit(i))
    put(8, 7, bit(6))
    put(8, 8, bit(7))
    put(7, 8, bit(8))
    for i in range(9, 15):
        put(14 - i, 8, bit(i))
    for i in range(8):
        put(n - 1 - i, 8, bit(i))
    for i in range(8, 15):
        put(8, n - 15 + i, bit(i))
    put(8, n - 8, True)
    bits = [w >> 7 - k & 1 for w in words for k in range(8)]
    idx, up = (0, True)
    x = n - 1
    while x > 0:
        if x == 6:
            x -= 1
        ys = range(n - 1, (-1), (-1)) if up else range(n)
        for y in ys:
            for dx in [0, 1]:
                xx = x - dx
                if not fn[y][xx]:
                    dark = bool(bits[idx]) if idx < len(bits) else False
                    idx += 1
                    if _mask_fn(mask)(xx, y):
                        dark = not dark
                    mod[y][xx] = dark
        up = not up
        x -= 2
    return mod


def _mask_fn(m: int):
    return (
        lambda x, y: (x + y) % 2 == 0,
        lambda x, y: y % 2 == 0,
        lambda x, y: x % 3 == 0,
        lambda x, y: (x + y) % 3 == 0,
        lambda x, y: (x // 3 + y // 2) % 2 == 0,
        lambda x, y: (x * y % 2 + x * y % 3) == 0,
        lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
    )[m]


def _penalty(m) -> int:
    n = len(m)
    score = 0
    for grid in [m, [list(c) for c in zip(*m)]]:
        for row in grid:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]:
                    run += 1
                    if run == 5:
                        score += 3
                    else:
                        if run > 5:
                            score += 1
                else:
                    run = 1
            s = "".join(("1" if v else "0" for v in row))
            score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum((v for row in m for v in row))
    score += 10 * (abs(dark * 100 // (n * n) - 50) // 5)
    return score


def make_matrix(text: str) -> List[List[bool]]:
    data = text.encode("utf-8")
    for version, (total, ec, blocks) in _VERSIONS.items():
        if len(data) <= total - ec * blocks - 2:
            break
    else:
        raise ValueError("text too long for the built-in QR encoder")
    words = _codewords(data, version)
    best = min((_build(version, words, mask) for mask in range(8)), key=_penalty)
    return best
