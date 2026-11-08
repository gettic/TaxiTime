# Taxi Time - custom art generator (plain Python 3, no libraries).
# Every picture is drawn here from shapes typed into this file; no outside art.
# Draws two design directions (silhouette / cartoon) of the flyer sprite
# sheets, bar fill, bar frame, cloud and sparkle, writes TGA (game) and
# PNG (preview) files plus preview sheets.
# Usage: python make_art.py        -> out\ holds the 6 .tga files the addon ships
#        python make_art.py all    -> also out\deliver\ and out\previews\ (both looks)
# Everything goes to out\ next to this script; copy the 6 files to TaxiTime\media\ by hand.
import math, os, struct, zlib

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')

# ---------------------------------------------------------------- image core
class Img:
    def __init__(s, w, h, fill=(0, 0, 0, 0)):
        s.w, s.h = w, h
        r, g, b, a = fill
        s.p = [r * a, g * a, b * a, a] * (w * h)   # premultiplied floats

    def blend(s, i, r, g, b, a):
        p = s.p; k = i * 4; ia = 1 - a
        p[k] = r * a + p[k] * ia; p[k+1] = g * a + p[k+1] * ia
        p[k+2] = b * a + p[k+2] * ia; p[k+3] = a + p[k+3] * ia

def C(r, g, b, a=1.0):
    return (r / 255, g / 255, b / 255, a)

def lerp(a, b, t):
    return a + (b - a) * t

def lerpc(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(lerp(c1[i], c2[i], t) for i in range(4))

def vgrad(c1, c2, y0, y1):
    return lambda x, y: lerpc(c1, c2, (y - y0) / (y1 - y0))

def compose(dst, src):            # src over dst (same size)
    d, s = dst.p, src.p
    for k in range(0, len(s), 4):
        sa = s[k+3]
        if sa <= 0: continue
        ia = 1 - sa
        d[k] = s[k] + d[k] * ia; d[k+1] = s[k+1] + d[k+1] * ia
        d[k+2] = s[k+2] + d[k+2] * ia; d[k+3] = sa + d[k+3] * ia

def blit(dst, src, ox, oy):
    for y in range(src.h):
        dy = y + oy
        if dy < 0 or dy >= dst.h: continue
        for x in range(src.w):
            dx = x + ox
            if dx < 0 or dx >= dst.w: continue
            k = (y * src.w + x) * 4
            sa = src.p[k+3]
            if sa <= 0: continue
            j = (dy * dst.w + dx) * 4; ia = 1 - sa
            for c in range(3):
                dst.p[j+c] = src.p[k+c] + dst.p[j+c] * ia
            dst.p[j+3] = sa + dst.p[j+3] * ia

def downsample(img, S):
    w, h = img.w // S, img.h // S
    out = Img(w, h); n = S * S; p = img.p
    for y in range(h):
        for x in range(w):
            acc = [0.0, 0.0, 0.0, 0.0]
            for yy in range(y * S, y * S + S):
                base = (yy * img.w + x * S) * 4
                for xx in range(S):
                    k = base + xx * 4
                    acc[0] += p[k]; acc[1] += p[k+1]; acc[2] += p[k+2]; acc[3] += p[k+3]
            j = (y * w + x) * 4
            out.p[j:j+4] = [v / n for v in acc]
    return out

def _weights(ns, nd):
    sc = ns / nd; W = []
    for i in range(nd):
        a, b = i * sc, (i + 1) * sc
        ws = []; j = int(a)
        while j < b and j < ns:
            lo, hi = max(a, j), min(b, j + 1)
            if hi > lo: ws.append((j, (hi - lo) / sc))
            j += 1
        W.append(ws)
    return W

def resize(img, nw, nh):          # area resample (premultiplied)
    wx, wy = _weights(img.w, nw), _weights(img.h, nh)
    tmp = [0.0] * (nw * img.h * 4)
    for y in range(img.h):
        for x in range(nw):
            acc = [0.0] * 4
            for j, wt in wx[x]:
                k = (y * img.w + j) * 4
                for c in range(4): acc[c] += img.p[k+c] * wt
            tmp[(y * nw + x) * 4:(y * nw + x) * 4 + 4] = acc
    out = Img(nw, nh)
    for y in range(nh):
        for x in range(nw):
            acc = [0.0] * 4
            for j, wt in wy[y]:
                k = (j * nw + x) * 4
                for c in range(4): acc[c] += tmp[k+c] * wt
            out.p[(y * nw + x) * 4:(y * nw + x) * 4 + 4] = acc
    return out

def crop(img, x0, y0, w, h):
    out = Img(w, h)
    for y in range(h):
        k = ((y0 + y) * img.w + x0) * 4
        out.p[y * w * 4:(y + 1) * w * 4] = img.p[k:k + w * 4]
    return out

def nearest(img, f):
    out = Img(img.w * f, img.h * f)
    for y in range(out.h):
        for x in range(out.w):
            k = ((y // f) * img.w + x // f) * 4
            j = (y * out.w + x) * 4
            out.p[j:j+4] = img.p[k:k+4]
    return out

def tint(img, col):
    out = Img(img.w, img.h)
    for k in range(0, len(img.p), 4):
        out.p[k] = img.p[k] * col[0]; out.p[k+1] = img.p[k+1] * col[1]
        out.p[k+2] = img.p[k+2] * col[2]; out.p[k+3] = img.p[k+3]
    return out

def scale_alpha(img, f):
    out = Img(img.w, img.h); out.p = [v * f for v in img.p]; return out

def box_blur(img, r):
    out = img
    for _ in range(2):                         # horizontal then vertical
        new = Img(out.w, out.h)
        for y in range(out.h):
            for x in range(out.w):
                acc = [0.0] * 4; n = 0
                for d in range(-r, r + 1):
                    xx, yy = (x + d, y) if _ == 0 else (x, y + d)
                    if 0 <= xx < out.w and 0 <= yy < out.h:
                        k = (yy * out.w + xx) * 4
                        for c in range(4): acc[c] += out.p[k+c]
                    n += 1
                new.p[(y * out.w + x) * 4:(y * out.w + x) * 4 + 4] = [v / n for v in acc]
        out = new
    return out

# ---------------------------------------------------------------- writers
def _straight(img):
    out = bytearray()
    for k in range(0, len(img.p), 4):
        a = img.p[k+3]
        if a > 1e-6:
            r, g, b = img.p[k] / a, img.p[k+1] / a, img.p[k+2] / a
        else:
            r = g = b = 0
        out += bytes(max(0, min(255, int(round(v * 255)))) for v in (r, g, b, min(a, 1)))
    return out

def write_png(path, img):
    px = _straight(img); raw = bytearray(); row = img.w * 4
    for y in range(img.h):
        raw.append(0); raw += px[y * row:(y + 1) * row]
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', img.w, img.h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(data)

def write_tga(path, img):         # uncompressed 32-bit, bottom-left origin
    px = _straight(img); row = img.w * 4
    hdr = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, img.w, img.h, 32, 8)
    body = bytearray()
    for y in range(img.h - 1, -1, -1):
        r = px[y * row:(y + 1) * row]
        for i in range(0, row, 4):
            body += bytes((r[i+2], r[i+1], r[i], r[i+3]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(hdr + body)

# ---------------------------------------------------------------- shapes
def fill_poly(img, pts, col, S):
    P = [(x * S, y * S) for x, y in pts]; n = len(P)
    ys = [p[1] for p in P]
    y0 = max(0, int(math.floor(min(ys)))); y1 = min(img.h - 1, int(math.ceil(max(ys))))
    fn = callable(col)
    for py in range(y0, y1 + 1):
        yc = py + 0.5; xs = []
        for i in range(n):
            ax, ay = P[i]; bx, by = P[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            xa = max(0, int(math.ceil(xs[j] - 0.5))); xb = min(img.w - 1, int(math.floor(xs[j+1] - 0.5)))
            for px in range(xa, xb + 1):
                c = col((px + 0.5) / S, yc / S) if fn else col
                img.blend(py * img.w + px, *c)

def ellipse(cx, cy, rx, ry, rot=0, n=48):
    t = math.radians(rot); ct, st = math.cos(t), math.sin(t); out = []
    for i in range(n):
        a = 2 * math.pi * i / n; x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + x * ct - y * st, cy + x * st + y * ct))
    return out

def thick(img, pts, widths, col, S):
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        wa, wb = widths[i] / 2, widths[i + 1] / 2
        dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        fill_poly(img, [(ax + nx * wa, ay + ny * wa), (bx + nx * wb, by + ny * wb),
                        (bx - nx * wb, by - ny * wb), (ax - nx * wa, ay - ny * wa)], col, S)
    for (x, y), w in zip(pts, widths):
        fill_poly(img, ellipse(x, y, w / 2, w / 2, 0, 20), col, S)

# ---------------------------------------------------------------- masks
def mask_of(img):
    rows = []
    for y in range(img.h):
        v = 0; base = y * img.w * 4 + 3
        for x in range(img.w):
            if img.p[base + x * 4] >= 0.5: v |= 1 << x
        rows.append(v)
    return rows

def dilate(rows, w, steps):
    full = (1 << w) - 1; H = len(rows)
    for i in range(steps):
        h = [(r | (r << 1) | (r >> 1)) & full for r in rows]
        if i % 2 == 0:
            rows = [h[y] | (h[y-1] if y > 0 else 0) | (h[y+1] if y < H - 1 else 0) for y in range(H)]
        else:
            rows = [h[y] | (rows[y-1] if y > 0 else 0) | (rows[y+1] if y < H - 1 else 0) for y in range(H)]
    return rows

def shift(rows, dx, dy, w):       # result(x,y) = rows(x+dx, y+dy)
    full = (1 << w) - 1; H = len(rows); out = []
    for y in range(H):
        sy = y + dy; r = rows[sy] if 0 <= sy < H else 0
        out.append((r >> dx) if dx >= 0 else ((r << -dx) & full))
    return out

def paint_mask(img, rows, col):
    for y, r in enumerate(rows):
        while r:
            lsb = r & -r; x = lsb.bit_length() - 1; r ^= lsb
            img.blend(y * img.w + x, *col)

def andnot(a, b):
    return [x & ~y for x, y in zip(a, b)]

# ---------------------------------------------------------------- flyers
S = 4                     # supersampling
CELL = 64                 # frame size in the sheet
FRAMES = 4
# (wing angle in degrees, span) per frame: up, going down, down, going up
WING = [(-95, 1.0), (-172, 0.58), (122, 0.95), (-140, 0.6)]
BOB = [1.0, 0.0, -1.0, 0.0]

FEATHER_WING = [(0, -3), (8, -5), (17, -5), (24, -3), (28, 0), (26, 3), (24, 2), (23, 6), (20, 4),
                (18, 8), (15, 5), (13, 9), (10, 6), (8, 9), (5, 6), (2, 8), (0, 5)]
FEATHER_COVERT = [(0, -3), (8, -5), (17, -5), (24, -3), (26, -0.5), (19, 1.5), (12, 2.5), (5, 3), (0, 2.5)]
BAT_WING = [(0, -3), (10, -6), (20, -5), (27, -2), (20, 2), (19.5, 9), (14, 6), (10.5, 11), (6, 6), (0, 7)]
BAT_BONES = [[(0, -2), (12, -5.2), (26.5, -2.2)], [(12, -5), (19.5, 8.5)], [(8, -4), (10.3, 10.5)]]

def wing_pts(local, sx, sy, theta, span):
    t = math.radians(theta); ux, uy = math.cos(t), math.sin(t)
    px, py = -math.sin(t), math.cos(t)
    if px > 0.01 or (abs(px) <= 0.01 and py < 0): px, py = -px, -py   # trailing edge faces back
    return [(sx + ux * u * span + px * v, sy + uy * u * span + py * v) for u, v in local]

def draw_gryphon(art, f, pal, sil):
    dy = BOB[f]; th, sp = WING[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    sx, sy = 33, 30 + dy
    fill_poly(art, wing_pts(FEATHER_WING, sx + 2, sy - 1, th - 12, sp * 0.9), pal['farwing'], S)
    thick(art, P([(19, 37), (12, 36), (6, 31)]), [2.6, 2.2, 1.8], pal['tail'], S)
    fill_poly(art, ellipse(5, 30 + dy, 3.6, 2.6, -40), pal['tuft'], S)
    thick(art, P([(22, 40), (17, 44), (12, 45)]), [4, 3, 2.4], pal['hindleg'], S)
    fill_poly(art, ellipse(29, 37 + dy, 13, 7.5, -12), pal['body'], S)
    if not sil:
        fill_poly(art, P([(24.2, 29.2), (34.8, 27.6), (36, 35.6), (25.2, 37.8)]), pal['trim'], S)
        fill_poly(art, P([(25, 29.8), (34, 28.5), (35, 34.8), (26, 36.8)]), pal['blanket'], S)
    thick(art, P([(40, 37), (43, 43), (47, 45)]), [3, 2.2, 1.6], pal['leg'], S)
    fill_poly(art, ellipse(39, 32 + dy, 7.5, 7, 0), pal['chest'], S)
    fill_poly(art, P([(42, 21), (35.5, 16.5), (40, 23.5)]), pal['crest'], S)
    fill_poly(art, P([(44, 19.5), (40.5, 13), (46, 20.5)]), pal['crest'], S)
    fill_poly(art, ellipse(45, 25 + dy, 6.5, 6.2, 0), pal['head'], S)
    fill_poly(art, P([(50, 21.5), (55, 22), (58.5, 25.5), (57.5, 29), (55, 26.8), (50.5, 28.5)]), pal['beak'], S)
    if sil:
        fill_poly(art, ellipse(47.6, 24 + dy, 1.2, 1.1), pal['eye'], S)
    else:
        fill_poly(art, ellipse(47.5, 24 + dy, 1.5, 1.8), pal['eye'], S)
        fill_poly(art, ellipse(47.9, 23.3 + dy, 0.55, 0.55), C(255, 255, 255), S)
    wing = Img(art.w, art.h)
    fill_poly(wing, wing_pts(FEATHER_WING, sx, sy, th, sp), pal['wingtip'], S)
    fill_poly(wing, wing_pts(FEATHER_COVERT, sx, sy, th, sp), pal['wing'], S)
    near_wing(art, wing, pal, sil)

def draw_wyvern(art, f, pal, sil):
    dy = BOB[f]; th, sp = WING[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    sx, sy = 33, 31 + dy
    fill_poly(art, wing_pts(BAT_WING, sx + 2, sy - 1, th - 12, sp * 0.9), pal['farwing'], S)
    thick(art, P([(18, 38), (10, 41), (5, 38), (3, 33)]), [3, 2.2, 1.6, 1.2], pal['tail'], S)
    fill_poly(art, P([(3, 28), (6.5, 32), (3.5, 34.5), (0.8, 32)]), pal['spade'], S)
    thick(art, P([(24, 40), (21, 45.5), (16.5, 47)]), [3.6, 2.6, 1.8], pal['hindleg'], S)
    fill_poly(art, ellipse(28, 37 + dy, 13, 6.5, -10), pal['body'], S)
    fill_poly(art, P([(18, 32), (20, 28.5), (22, 31.5)]), pal['spine'], S)
    fill_poly(art, P([(23, 30.8), (25.5, 27.2), (27.5, 30.3)]), pal['spine'], S)
    if not sil:
        fill_poly(art, ellipse(30, 40.2 + dy, 9.5, 3, -10), pal['belly'], S)
        fill_poly(art, P([(23.4, 29.6), (33.6, 28.4), (35.2, 35.9), (25, 37.6)]), pal['trim'], S)
        fill_poly(art, P([(24.2, 30.2), (32.9, 29.2), (34.3, 35.2), (25.8, 36.7)]), pal['blanket'], S)
    thick(art, P([(35, 35), (40, 30), (44, 26.5)]), [6, 5, 4.5], pal['neck'], S)
    fill_poly(art, P([(44, 22.3), (36.5, 17.5), (42.8, 24.5)]), pal['horn'], S)
    fill_poly(art, P([(46.5, 21.5), (42, 14.5), (48.3, 22.2)]), pal['horn'], S)
    fill_poly(art, ellipse(46.5, 25 + dy, 5.6, 4.2, 8), pal['head'], S)
    fill_poly(art, P([(49, 22.3), (56.5, 24.3), (57.5, 26.6), (55, 28), (49.5, 29)]), pal['head'], S)
    if sil:
        fill_poly(art, ellipse(49, 24.4 + dy, 1.2, 0.9), pal['eye'], S)
    else:
        fill_poly(art, ellipse(49, 24.4 + dy, 1.5, 1.2), pal['eye'], S)
        fill_poly(art, ellipse(49.2, 24.4 + dy, 0.35, 1.0), C(30, 15, 10), S)
        fill_poly(art, P([(55.5, 26.8), (57.3, 26.6), (55.2, 27.6)]), pal['trim'], S)  # nostril/mouth line
    wing = Img(art.w, art.h)
    fill_poly(wing, wing_pts(BAT_WING, sx, sy, th, sp), pal['wing'], S)
    if not sil:
        for bone in BAT_BONES:
            pts = wing_pts(bone, sx, sy, th, sp)
            thick(wing, pts, [1.3] + [0.8] * (len(pts) - 1), pal['bone'], S)
    near_wing(art, wing, pal, sil)

# ---- Horde v2: wind rider (lion body + mane, bat wings, scorpion tail)
WR_WING = [(0, -3.5), (9, -6.5), (19, -6.2), (29.5, -2.6), (23.5, 1.2), (22.5, 10.5), (18, 5),
           (13.5, 12.5), (10, 5.5), (5, 10.5), (0, 6)]
WR_BONES = [[(0, -2.6), (10, -5.6), (19, -5.2), (29, -2.7)], [(19, -5), (22.3, 10)],
            [(18.5, -5), (13.6, 12)], [(10, -5.4), (5.2, 10)]]

def star(cx, cy, ro, ri, n, rot=0, sy=1.0):
    out = []
    for i in range(2 * n):
        a = math.radians(rot) + math.pi * i / n; r = ro if i % 2 == 0 else ri
        out.append((cx + r * math.cos(a), cy + r * math.sin(a) * sy))
    return out

WR_WING_ANG = [(-84, 1.0), (-104, 0.86), (118, 0.95), (-114, 0.8)]   # mid frames kept big so the wing reads

def draw_windrider(art, f, pal, sil):
    dy = BOB[f]; th, sp = WR_WING_ANG[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    sx, sy = 33, 32 + dy
    # far wing (behind everything)
    far = Img(art.w, art.h)
    fill_poly(far, wing_pts(WR_WING, sx + 3, sy - 1.5, th - 14, sp * 0.88), pal['farwing'], S)
    compose(art, far)
    # scorpion tail: curls up and forward over the back, stinger points forward
    tail = P([(17, 35.5), (11, 35.5), (6.5, 32), (4.8, 26.5), (6.2, 21.2), (10, 18.4)])
    thick(art, tail, [4.6, 4.2, 3.9, 3.6, 3.2, 2.8], pal['tail'], S)
    for i, (x, y) in enumerate(tail[1:]):            # bulging segments -> bumpy scorpion outline
        r = 2.7 - i * 0.18
        fill_poly(art, ellipse(x, y, r, r), pal['tail'], S)
        if not sil:
            fill_poly(art, ellipse(x - 0.4, y - 0.4, r * 0.45, r * 0.45), pal['tailseg'], S)
    fill_poly(art, ellipse(12, 18.4 + dy, 3.0, 2.5, -15), pal['sting'], S)        # venom bulb
    fill_poly(art, P([(11.5, 16), (16, 16.4), (19.5, 21.8), (15.6, 19.8), (13, 20.8)]), pal['sting'], S)  # hooked barb
    # far legs
    thick(art, P([(22, 41), (19.5, 46), (15.5, 47.5)]), [3.6, 2.8, 2.4], pal['farleg'], S)
    thick(art, P([(36, 41), (38, 46), (41.5, 47.5)]), [3.4, 2.6, 2.2], pal['farleg'], S)
    # lion body
    fill_poly(art, ellipse(27.5, 38 + dy, 13, 6.8, -6), pal['body'], S)
    if not sil:
        fill_poly(art, ellipse(28.5, 42 + dy, 9.5, 2.4, -6), pal['belly'], S)
    # near legs with paws
    thick(art, P([(19, 41), (15.5, 46), (11.5, 47)]), [5.2, 3.8, 3.2], pal['leg'], S)
    fill_poly(art, ellipse(11, 47 + dy, 2.2, 1.6), pal['paw'], S)
    thick(art, P([(38, 40), (41, 45.5), (45, 46.8)]), [5.0, 3.8, 3.2], pal['leg'], S)
    fill_poly(art, ellipse(45.5, 46.8 + dy, 2.2, 1.6), pal['paw'], S)
    # mane: big spiky ruff around the neck and head
    fill_poly(art, star(41, 29 + dy, 13, 8, 7, 14, 1.05), pal['mane'], S)
    if not sil:
        fill_poly(art, star(42, 28.5 + dy, 8.4, 5.8, 8, 34, 1.0), pal['mane2'], S)
    # ears
    fill_poly(art, P([(42.6, 22.2), (43.6, 16.4), (47.2, 21.4)]), pal['ear'], S)
    # cat head + blunt muzzle
    fill_poly(art, ellipse(46.8, 27 + dy, 5.9, 5.4, 0), pal['head'], S)
    fill_poly(art, P([(48.5, 24.6), (54, 25), (56.4, 26.6), (56.6, 30.2), (54, 32.4), (48, 31.8)]), pal['muzzle'], S)
    if not sil:
        fill_poly(art, P([(54.4, 26.4), (56.8, 27.4), (55.6, 28.8)]), pal['nose'], S)
        fill_poly(art, P([(50.5, 30.6), (55.4, 30.0), (51.5, 31.2)]), pal['nose'], S)    # mouth line
        fill_poly(art, P([(46.2, 24.1), (50.6, 24.6), (50.2, 25.3), (46.4, 24.9)]), pal['brow'], S)
        fill_poly(art, ellipse(48.4, 26.1 + dy, 1.5, 1.2, 10), pal['eye'], S)
        fill_poly(art, ellipse(48.7, 26.1 + dy, 0.45, 1.0), C(30, 14, 8), S)
    else:
        fill_poly(art, P([(47, 25.2), (50.4, 25.8), (47.4, 27.0)]), pal['eye'], S)      # slit eye glint
    # near wing: dark membrane, light finger bones -> clear bat outline
    wing = Img(art.w, art.h)
    fill_poly(wing, wing_pts(WR_WING, sx, sy, th, sp), pal['wing'], S)
    for bone in WR_BONES:
        pts = wing_pts(bone, sx, sy, th, sp)
        thick(wing, pts, [1.3] + [0.75] * (len(pts) - 1), pal['bone'], S)
    near_wing(art, wing, pal, sil)

def near_wing(art, wing, pal, sil):
    m = mask_of(wing)
    edge = dilate(m, wing.w, 3)
    paint_mask(art, edge, pal['sep'])           # thin separation line around the near wing
    compose(art, wing)

def finish_creature(art, pal, sil):
    m = mask_of(art); W = art.w
    if sil:
        rim = andnot(m, shift(m, 3, -6, W))     # light from above-front
        paint_mask(art, rim, pal['rim'])
        out = Img(W, art.h)
        d1, d2, d3 = dilate(m, W, 2), dilate(m, W, 5), dilate(m, W, 9)
        gr, gg, gb, _ = pal['glow']
        paint_mask(out, andnot(d3, d2), (gr, gg, gb, 0.08))
        paint_mask(out, andnot(d2, d1), (gr, gg, gb, 0.22))
        paint_mask(out, andnot(d1, m), (gr, gg, gb, 0.55))
    else:
        out = Img(W, art.h)
        paint_mask(out, dilate(m, W, 4), pal['outline'])
    compose(out, art)
    return out

def make_sheet(kind, pal, sil):
    sheet = Img(CELL * FRAMES, CELL)
    for f in range(FRAMES):
        art = Img(CELL * S, CELL * S)
        {'gryphon': draw_gryphon, 'wyvern': draw_wyvern, 'windrider': draw_windrider}[kind](art, f, pal, sil)
        cell = downsample(finish_creature(art, pal, sil), S)
        blit(sheet, cell, f * CELL, 0)
    return sheet

def same(col, **over):
    keys = ['farwing', 'tail', 'tuft', 'hindleg', 'body', 'leg', 'chest', 'crest', 'head', 'beak',
            'wing', 'wingtip', 'spade', 'spine', 'neck', 'horn', 'bone', 'sep']
    d = {k: col for k in keys}; d.update(over); return d

PALETTES = {
    ('silhouette', 'gryphon'): same(C(14, 18, 32), farwing=C(44, 52, 82), sep=C(60, 70, 105),
                                    eye=C(255, 225, 130), rim=C(255, 214, 120, 0.95), glow=C(90, 150, 255)),
    ('silhouette', 'wyvern'): same(C(30, 15, 12), farwing=C(70, 34, 28), sep=C(100, 48, 38),
                                   eye=C(255, 175, 60), rim=C(255, 150, 70, 0.95), glow=C(230, 60, 30)),
    ('cartoon', 'gryphon'): dict(
        farwing=C(105, 66, 36), tail=C(185, 128, 62), tuft=C(120, 78, 40), hindleg=C(180, 124, 60),
        body=vgrad(C(222, 168, 86), C(160, 106, 48), 30, 45), leg=C(242, 172, 48),
        chest=C(246, 241, 226), crest=C(232, 224, 206), head=C(250, 246, 236), beak=C(246, 182, 40),
        eye=C(22, 22, 34), wing=C(148, 94, 48), wingtip=C(214, 176, 112), sep=C(70, 44, 24),
        blanket=C(42, 88, 196), trim=C(242, 202, 72), outline=C(44, 28, 18)),
    ('cartoon', 'wyvern'): dict(
        farwing=C(108, 34, 30), tail=C(188, 112, 56), spade=C(120, 40, 34), hindleg=C(172, 100, 50),
        body=vgrad(C(218, 138, 72), C(158, 88, 44), 30, 45), belly=C(240, 202, 142), spine=C(122, 40, 34),
        neck=vgrad(C(222, 144, 76), C(178, 104, 52), 24, 38), horn=C(240, 230, 202),
        head=vgrad(C(224, 146, 78), C(184, 108, 54), 20, 30), eye=C(255, 214, 60),
        wing=vgrad(C(190, 62, 50), C(140, 36, 32), 5, 45), bone=C(92, 34, 24), sep=C(70, 24, 18),
        blanket=C(176, 30, 30), trim=C(70, 50, 38), outline=C(42, 20, 14)),
    # Horde v2 wind rider
    ('silhouette', 'windrider'): same(C(28, 14, 11), farwing=C(66, 30, 24), sep=C(110, 50, 36),
                                      bone=C(52, 26, 20), farleg=C(44, 22, 18), sting=C(235, 120, 50),
                                      mane=C(52, 22, 16), ear=C(28, 14, 11), muzzle=C(28, 14, 11),
                                      paw=C(28, 14, 11), eye=C(255, 190, 70),
                                      rim=C(255, 160, 80, 0.95), glow=C(180, 44, 22)),
    ('cartoon', 'windrider'): dict(
        farwing=C(88, 26, 24), tail=vgrad(C(176, 110, 54), C(132, 76, 38), 18, 38), tailseg=C(104, 56, 28),
        sting=C(244, 232, 200), farleg=C(150, 98, 48),
        body=vgrad(C(232, 182, 100), C(170, 118, 56), 31, 45), belly=C(244, 216, 156),
        leg=C(214, 160, 82), paw=C(244, 222, 170),
        mane=C(92, 40, 22), mane2=C(150, 68, 30), ear=C(196, 136, 66),
        head=vgrad(C(238, 190, 108), C(206, 150, 76), 21, 32), muzzle=C(246, 224, 172),
        nose=C(70, 30, 20), brow=C(92, 40, 22), eye=C(255, 214, 60),
        wing=vgrad(C(168, 40, 34), C(116, 26, 24), 5, 50), bone=C(214, 118, 76), sep=C(50, 16, 12),
        outline=C(40, 18, 12)),
}

# ---------------------------------------------------------------- bar parts
def make_fill(style):
    img = Img(256, 32)
    for y in range(32):
        for x in range(256):
            if style == 'silhouette':
                if y < 2: v = 0.55
                elif y < 4: v = 1.0
                elif y >= 30: v = 0.32
                else: v = lerp(0.86, 0.46, (y - 4) / 26)
                # faint wind streaks
                for (sy, x0, ln) in ((9, 20, 60), (14, 110, 80), (20, 40, 50), (24, 170, 70), (11, 200, 40)):
                    if abs(y - sy) < 1 and x0 <= x <= x0 + ln:
                        v += 0.07 * math.sin(math.pi * (x - x0) / ln)
            else:
                if y < 2: v = 0.62
                elif y < 14: v = lerp(1.0, 0.86, (y - 2) / 12)
                elif y >= 30: v = 0.40
                else: v = lerp(0.74, 0.50, (y - 14) / 16)
            k = (y * 256 + x) * 4; v = min(v, 1.0)
            img.p[k:k+4] = [v, v, v, 1.0]
    return img

def sd_rrect(px, py, x0, y0, x1, y1, r):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; hw, hh = (x1 - x0) / 2, (y1 - y0) / 2
    qx, qy = abs(px - cx) - (hw - r), abs(py - cy) - (hh - r)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r

def frame_color(style, x, y):
    do = -sd_rrect(x, y, 0, 0, 256, 64, 14)      # depth from outer edge
    di = sd_rrect(x, y, 10, 10, 246, 54, 4)      # distance outside the inner hole
    if do < 0 or di < 0: return None
    t = y / 64
    if style == 'silhouette':
        if do < 1.4: return C(8, 8, 12)
        c = lerpc(C(92, 95, 110), C(34, 36, 44), t)
        if do < 3.0 and y < 32: c = lerpc(c, C(150, 152, 168), 0.5)
        if di < 0.9: c = C(14, 11, 6)
        elif di < 2.2: c = lerpc(C(240, 200, 105), C(170, 125, 50), t)
        # gold diamond studs on the end caps
        for cx in (5, 251):
            if abs(x - cx) / 3.2 + abs(y - 32) / 6.5 < 1:
                c = lerpc(C(255, 225, 140), C(170, 120, 45), (y - 25.5) / 13)
        return c
    else:
        if do < 1.4: return C(48, 28, 14)
        c = lerpc(C(232, 180, 92), C(146, 92, 38), t)
        if do < 3.2 and y < 32: c = lerpc(c, C(255, 232, 160), 0.55)
        if di < 1.4: c = C(62, 36, 16)
        for cx in (5.5, 250.5):
            d = math.hypot(x - cx, y - 32)
            if d < 2.8: c = lerpc(C(255, 240, 190), C(170, 115, 50), (y - 29.5) / 5) if d < 2.0 else C(70, 40, 18)
        return c

def make_frame(style):
    img = Img(256, 64); ss = 4
    for y in range(64):
        for x in range(256):
            acc = [0.0] * 4
            for sy in range(ss):
                for sx in range(ss):
                    c = frame_color(style, x + (sx + 0.5) / ss, y + (sy + 0.5) / ss)
                    if c:
                        acc[0] += c[0] * c[3]; acc[1] += c[1] * c[3]; acc[2] += c[2] * c[3]; acc[3] += c[3]
            k = (y * 256 + x) * 4
            img.p[k:k+4] = [v / (ss * ss) for v in acc]
    return img

def make_cloud(style):
    art = Img(64 * S, 32 * S)
    blobs = [(20, 19, 9), (32, 14, 11), (45, 18, 9), (12, 23, 6), (53, 23, 6)]
    if style == 'silhouette':
        col = C(150, 162, 192, 0.7)
        for x, y, r in blobs: fill_poly(art, ellipse(x, y, r, r), C(150, 162, 192), S)
        fill_poly(art, ellipse(32, 24, 25, 5.5), C(150, 162, 192), S)
        img = scale_alpha(box_blur(downsample(art, S), 1), 0.7)
        return img
    col = vgrad(C(255, 255, 255), C(196, 216, 244), 6, 29)
    for x, y, r in blobs: fill_poly(art, ellipse(x, y, r, r), col, S)
    fill_poly(art, ellipse(32, 24, 25, 5.5), col, S)
    m = mask_of(art); out = Img(art.w, art.h)
    paint_mask(out, dilate(m, art.w, 4), C(70, 92, 132))
    compose(out, art)
    return downsample(out, S)

def make_sparkle():
    img = Img(128, 32)
    scales = [0.45, 1.0, 0.7, 0.3]; rots = [0, 12, 24, 36]
    for f in range(4):
        s = scales[f]; t = math.radians(rots[f]); ct, st = math.cos(t), math.sin(t)
        for y in range(32):
            for x in range(32):
                acc = 0.0
                for sy in (0.25, 0.75):
                    for sx in (0.25, 0.75):
                        dx, dy = x + sx - 16, y + sy - 16
                        u, v = dx * ct + dy * st, -dx * st + dy * ct
                        I = math.exp(-((u * u + v * v) / (3.2 * s) ** 2))
                        for (a, b, L, W) in ((u, v, 14 * s, 1.6), (v, u, 14 * s, 1.6),
                                             ((u + v) * 0.7071, (u - v) * 0.7071, 7 * s, 1.1),
                                             ((u - v) * 0.7071, (u + v) * 0.7071, 7 * s, 1.1)):
                            if abs(a) < L:
                                k = 1 - abs(a) / L
                                I = max(I, k * max(0.0, 1 - abs(b) / (W * k + 0.35)))
                        acc += min(I, 1.0)
                I = acc / 4
                c = lerpc(C(255, 196, 70), C(255, 255, 240), I * I)
                kk = (y * 128 + f * 32 + x) * 4
                img.p[kk:kk+4] = [c[0] * I, c[1] * I, c[2] * I, I]
    return img

# ---------------------------------------------------------------- previews
def bg(w, h):
    img = Img(w, h)
    for y in range(h):
        c = lerpc(C(26, 32, 44), C(10, 12, 18), y / max(1, h - 1))
        for x in range(w):
            img.p[(y * w + x) * 4:(y * w + x) * 4 + 4] = [c[0], c[1], c[2], 1.0]
    return img

def frames_of(sheet, n, size):
    cw = sheet.w // n
    return [resize(crop(sheet, i * cw, 0, cw, sheet.h), size, size * sheet.h // cw) for i in range(n)]

def bar_mock(fill, frame, flyer, color, pct, fidx, ipct=None):
    W, H = 300, 64
    img = bg(W, H)
    fx, fy = 16, 30                       # frame top-left; frame 268x26
    inner = Img(260, 18, (0, 0, 0, 0.6)); blit(img, inner, fx + 4, fy + 4)
    fw = max(1, int(round(260 * pct)))
    part = crop(fill, 0, 0, max(1, int(round(256 * pct))), 32)
    blit(img, tint(resize(part, fw, 18), color), fx + 4, fy + 4)
    blit(img, resize(crop(frame, 0, 0, 32, 64), 13, 26), fx, fy)
    blit(img, resize(crop(frame, 32, 0, 192, 64), 242, 26), fx + 13, fy)
    blit(img, resize(crop(frame, 224, 0, 32, 64), 13, 26), fx + 255, fy)
    icon = frames_of(flyer, 4, 28)[fidx]
    x = 14 + (260 - 28) * (pct if ipct is None else ipct)           # same formula as SetIconX
    blit(img, icon, int(round(fx + 4 + x - 14)), fy + 4 - 28 + 6)
    return img

def main():
    out = BASE
    made = []
    sparkle = make_sparkle()
    write_tga(os.path.join(out, 'deliver', 'shared', 'sparkle.tga'), sparkle)
    write_png(os.path.join(out, 'deliver', 'shared', 'sparkle.png'), sparkle)
    for style in ('silhouette', 'cartoon'):
        d = os.path.join(out, 'deliver', style)
        sheets = {}
        for fac, kind in (('alliance', 'gryphon'), ('horde', 'wyvern')):
            sh = make_sheet(kind, PALETTES[(style, kind)], style == 'silhouette')
            sheets[fac] = sh
            write_tga(os.path.join(d, 'flyer_%s.tga' % fac), sh)
            write_png(os.path.join(d, 'flyer_%s.png' % fac), sh)
        fill, frame, cloud = make_fill(style), make_frame(style), make_cloud(style)
        for name, im in (('bar_fill', fill), ('bar_frame', frame), ('cloud', cloud)):
            write_tga(os.path.join(d, name + '.tga'), im)
            write_png(os.path.join(d, name + '.png'), im)
        pv = os.path.join(out, 'previews')
        # 8x of the 32 px version, per faction
        for fac in ('alliance', 'horde'):
            fr = frames_of(sheets[fac], 4, 32)
            big = bg(4 * 256 + 5 * 16, 256 + 32)
            for i, f in enumerate(fr):
                blit(big, nearest(f, 8), 16 + i * 272, 16)
            write_png(os.path.join(pv, '%s_%s_8x.png' % (style, fac)), big)
        # real size: frames at 32 and 24 px, cloud, sparkle
        rs = bg(420, 120)
        for r, fac in enumerate(('alliance', 'horde')):
            for i, f in enumerate(frames_of(sheets[fac], 4, 32)):
                blit(rs, f, 10 + i * 38, 8 + r * 40)
            for i, f in enumerate(frames_of(sheets[fac], 4, 24)):
                blit(rs, f, 170 + i * 30, 12 + r * 40)
        blit(rs, cloud, 300, 10)
        for i, f in enumerate(frames_of(sparkle, 4, 32)):
            blit(rs, f, 10 + i * 38, 86)
        write_png(os.path.join(pv, '%s_realsize.png' % style), rs)
        # extras at 8x of their real size
        ex = bg(64 * 8 + 32, 32 * 8 + 32); blit(ex, nearest(cloud, 8), 16, 16)
        write_png(os.path.join(pv, '%s_cloud_8x.png' % style), ex)
        # bar mock-ups: flight / recording / done for both factions at 1x, then 3x
        rows = [('alliance', (0.25, 0.6, 1.0), 0.55, 0), ('horde', (0.25, 0.6, 1.0), 0.3, 2),
                ('alliance', (1.0, 0.5, 0.1), 1.0, 1), ('horde', (0.2, 0.8, 0.3), 1.0, 3)]
        mocks = [bar_mock(fill, frame, sheets[fac], col, pct, fi, 0.0 if col[0] == 1.0 else None) for fac, col, pct, fi in rows]
        m1 = bg(300, 64 * 4)
        for i, m in enumerate(mocks): blit(m1, m, 0, i * 64)
        write_png(os.path.join(pv, '%s_bar_mock_1x.png' % style), m1)
        write_png(os.path.join(pv, '%s_bar_mock_3x.png' % style), nearest(m1, 3))
        print('done', style)
    s8 = bg(4 * 256 + 5 * 16, 256 + 32)
    for i, f in enumerate(frames_of(sparkle, 4, 32)):
        blit(s8, nearest(f, 8), 16 + i * 272, 16)
    write_png(os.path.join(out, 'previews', 'sparkle_8x.png'), s8)

def main_v2():
    """Horde v2 (wind rider): writes only *_v2 files, never touches the v1 files."""
    out = BASE; pv = os.path.join(out, 'previews')
    sparkle = make_sparkle()
    for style in ('silhouette', 'cartoon'):
        sil = style == 'silhouette'; d = os.path.join(out, 'deliver', style)
        sheets = {'alliance': make_sheet('gryphon', PALETTES[(style, 'gryphon')], sil),
                  'horde': make_sheet('windrider', PALETTES[(style, 'windrider')], sil)}
        write_tga(os.path.join(d, 'flyer_horde_v2.tga'), sheets['horde'])
        write_png(os.path.join(d, 'flyer_horde_v2.png'), sheets['horde'])
        fill, frame, cloud = make_fill(style), make_frame(style), make_cloud(style)
        fr = frames_of(sheets['horde'], 4, 32)
        big = bg(4 * 256 + 5 * 16, 256 + 32)
        for i, f in enumerate(fr):
            blit(big, nearest(f, 8), 16 + i * 272, 16)
        write_png(os.path.join(pv, '%s_horde_v2_8x.png' % style), big)
        rs = bg(420, 120)
        for r, fac in enumerate(('alliance', 'horde')):
            for i, f in enumerate(frames_of(sheets[fac], 4, 32)):
                blit(rs, f, 10 + i * 38, 8 + r * 40)
            for i, f in enumerate(frames_of(sheets[fac], 4, 24)):
                blit(rs, f, 170 + i * 30, 12 + r * 40)
        blit(rs, cloud, 300, 10)
        for i, f in enumerate(frames_of(sparkle, 4, 32)):
            blit(rs, f, 10 + i * 38, 86)
        write_png(os.path.join(pv, '%s_realsize_v2.png' % style), rs)
        rows = [('alliance', (0.25, 0.6, 1.0), 0.55, 0), ('horde', (0.25, 0.6, 1.0), 0.3, 2),
                ('horde', (1.0, 0.5, 0.1), 1.0, 1), ('horde', (0.2, 0.8, 0.3), 1.0, 3)]
        mocks = [bar_mock(fill, frame, sheets[fac], col, pct, fi, 0.0 if col[0] == 1.0 else None) for fac, col, pct, fi in rows]
        m1 = bg(300, 64 * 4)
        for i, m in enumerate(mocks): blit(m1, m, 0, i * 64)
        write_png(os.path.join(pv, '%s_bar_mock_1x_v2.png' % style), m1)
        write_png(os.path.join(pv, '%s_bar_mock_3x_v2.png' % style), nearest(m1, 3))
        print('done v2', style)

def main_ship():
    """The 6 files in TaxiTime\\media\\: cartoon look, wind rider as the Horde flyer."""
    pal = lambda kind: PALETTES[('cartoon', kind)]
    files = {'flyer_alliance': make_sheet('gryphon', pal('gryphon'), False),
             'flyer_horde': make_sheet('windrider', pal('windrider'), False),
             'bar_fill': make_fill('cartoon'), 'bar_frame': make_frame('cartoon'),
             'cloud': make_cloud('cartoon'), 'sparkle': make_sparkle()}
    for name, im in files.items():
        write_tga(os.path.join(BASE, name + '.tga'), im)
    print('done: 6 files in', BASE)

if __name__ == '__main__':
    import sys
    args = sys.argv[1:]
    if 'v2' in args:
        main_v2()                 # python make_art.py v2  -> only the Horde v2 files
    elif 'all' in args:
        main(); main_v2(); main_ship()
    else:
        main_ship()
