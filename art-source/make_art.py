# Taxi Time - custom art generator (plain Python 3, no libraries).
# Every picture is drawn here from shapes typed into this file; no outside art.
# Draws two design directions (silhouette / cartoon) of the flyer sprite
# sheets, the four 128 px painted flyer sheets (gryphon, wind rider, bat, hippogryph), bar fill, bar frame, cloud and sparkle, writes TGA (game) and
# PNG (preview) files plus preview sheets.
# Usage: python make_art.py        -> out\ holds the 10 .tga files the addon ships
#        python make_art.py all    -> also out\deliver\ and out\previews\ (both looks)
# Everything goes to out\ next to this script; copy the 10 files to TaxiTime\media\ by hand.
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

# ---------------------------------------------------------------- flyers v2 (shipped)
# Gryphon, wind rider, bat, hippogryph: 128 px frames, 4-frame flap, sheet 512x128,
# painted look, see-through. Drawn in 128-unit space, scaled by K into the frame.
U = 128          # frame size in units (= output px)
SS = 4           # art px per unit (supersampling)
W = U * SS
FR = 4
K = 0.78         # whole drawing scaled into the frame so wings never touch the edge
BOB2 = [2.0, 0.0, -2.0, 0.0]
FEATHER_ANG = [(-95, 1.0), (-172, 0.6), (122, 0.95), (-140, 0.62)]
BAT_ANG = [(-84, 1.0), (-106, 0.85), (118, 0.95), (-116, 0.8)]

# ---------------------------------------------------------------- masks + paint
def pmask(pts):
    P = [(((x - 60) * K + 64) * SS, ((y - 58) * K + 67) * SS) for x, y in pts]; n = len(P); rows = [0] * W
    ys = [p[1] for p in P]
    y0 = max(0, int(math.floor(min(ys)))); y1 = min(W - 1, int(math.ceil(max(ys))))
    for py in range(y0, y1 + 1):
        yc = py + 0.5; xs = []
        for i in range(n):
            ax, ay = P[i]; bx, by = P[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            xa = max(0, int(math.ceil(xs[j] - 0.5))); xb = min(W - 1, int(math.floor(xs[j + 1] - 0.5)))
            if xb >= xa: rows[py] |= ((1 << (xb - xa + 1)) - 1) << xa
    return rows

def OR(*ms):
    out = [0] * W
    for m in ms:
        out = [a | b for a, b in zip(out, m)]
    return out

def ell(cx, cy, rx, ry, rot=0):
    return pmask(ellipse(cx, cy, rx, ry, rot, 40))

def strk(pts, widths):
    ms = []
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        wa, wb = widths[i] / 2, widths[i + 1] / 2
        dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        ms.append(pmask([(ax + nx * wa, ay + ny * wa), (bx + nx * wb, by + ny * wb),
                         (bx - nx * wb, by - ny * wb), (ax - nx * wa, ay - ny * wa)]))
    for (x, y), w in zip(pts, widths):
        ms.append(pmask(ellipse(x, y, w / 2, w / 2, 0, 20)))
    return OR(*ms)

def paint(art, m, col):
    fn = callable(col)
    for y, r in enumerate(m):
        while r:
            lsb = r & -r; x = lsb.bit_length() - 1; r ^= lsb
            c = col(((x + 0.5) / SS - 64) / K + 60, ((y + 0.5) / SS - 67) / K + 58) if fn else col
            art.blend(y * W + x, *c)

def part(art, m, col, hi=None, lo=None, hk=1.6, lk=3.2):
    """Base colour, a light band along the top edge and a soft shade along the bottom (painted look)."""
    paint(art, m, col)
    if hi:
        paint(art, andnot(m, shift(m, 0, -int(hk * SS), W)), hi)
    if lo:
        paint(art, andnot(m, shift(m, 0, int(lk * SS), W)), lo)
        paint(art, andnot(m, shift(m, 0, int(lk * 0.45 * SS), W)), lo)
    return m

def A(c, a):
    return (c[0], c[1], c[2], a)

# ---------------------------------------------------------------- wings
def feather_wing(art, sx, sy, th, sp, pal, near):
    """Feathered wing: separate primaries + secondaries, covert band, light leading edge."""
    L = lambda pts: pmask(wing_pts(pts, sx, sy, th, sp))
    feathers = []
    for i, u in enumerate([3, 9, 15, 21, 27, 33]):
        a = math.radians(95 - i * 3); ln = 25
        feathers.append((u + math.cos(a) * ln / 2, 3 + math.sin(a) * ln / 2, ln / 2, 3.6, 95 - i * 3))
    for u, ad, ln in [(38, 76, 28), (43, 62, 29), (48, 47, 29), (52, 32, 28), (55, 17, 26), (57, 4, 22)]:
        a = math.radians(ad)
        feathers.append((u + math.cos(a) * ln / 2, -1 + math.sin(a) * ln / 2, ln / 2, 3.4, ad))
    fmasks = [L(ellipse(cx, cy, rx, ry, rot, 24)) for cx, cy, rx, ry, rot in feathers]
    covert_pts = [(0, -7), (14, -11), (30, -11), (46, -8), (57, -3), (50, 6), (40, 11), (28, 13), (14, 14), (0, 12)]
    cov = OR(L(covert_pts), *[L(ellipse(u, 13 - u * 0.1, 4.2, 3.2, 0, 16)) for u in range(4, 46, 7)])
    marg = L([(0, -7), (14, -11), (30, -11), (46, -8), (55, -4), (44, 0), (28, 1.5), (12, 2.5), (0, 3)])
    whole = OR(cov, marg, *fmasks)
    if near:
        paint(art, dilate(whole, W, 5), pal['sep'])
    for m in reversed(fmasks):                       # outer feathers under inner ones
        paint(art, dilate(m, W, 2), pal['fline'])
        part(art, m, pal['feather'], A(pal['fhi'], 0.45))
    part(art, cov, pal['covert'], A(pal['chi'], 0.5), A(pal['fline'], 0.35))
    part(art, marg, pal['marg'], A(pal['chi'], 0.6))

BW_MEMB = [(0, -5), (16, -11), (30, -12), (60, -4), (49, 3), (53, 15), (41, 13), (39, 26), (29, 17),
           (23, 26), (13, 16), (0, 14)]
BW_ARM = [(0, -1), (16, -8), (30, -10)]
BW_FINGERS = [[(30, -10), (60, -4)], [(30, -10), (53, 14.5)], [(30, -10), (39, 25.5)], [(30, -10), (23, 25.5)]]

def bat_wing(art, sx, sy, th, sp, pal, near, sc=1.0):
    L = lambda pts: wing_pts([(u * sc, v * sc) for u, v in pts], sx, sy, th, sp)
    memb = pmask(L(BW_MEMB))
    if not near:
        part(art, memb, pal['farwing'])
        return
    bones = OR(strk(L(BW_ARM), [3.6, 3.0, 2.6]), *[strk(L(fg), [2.2, 1.2]) for fg in BW_FINGERS])
    paint(art, dilate(OR(memb, bones), W, 5), pal['sep'])
    part(art, memb, pal['wing'], A(pal['whi'], 0.35), A(pal['wlo'], 0.45), lk=4)
    paint(art, andnot(dilate(bones, W, 3), bones), A(pal['wlo'], 0.6))   # crease shadow beside bones
    part(art, bones, pal['bone'], A(pal['bonehi'], 0.7))
    wx, wy = L([(30, -10)])[0]
    part(art, pmask([(wx - 1, wy - 1), (wx + 1.5, wy - 5), (wx + 1.6, wy)]), pal['claw'])

# ---------------------------------------------------------------- creatures
def gryphon(art, f, g):
    dy = BOB2[f]; th, sp = FEATHER_ANG[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + dy, rx, ry, rot)
    sx, sy = 62, 56 + dy
    feather_wing(art, sx + 5, sy - 3, th - 12, sp * 0.9, g['far'], False)
    part(art, strk(P([(36, 74), (24, 76), (15, 70), (10, 61)]), [6, 5, 4, 3.4]), g['body2'], A(g['hi'], .4))
    part(art, E(9, 56, 6.5, 4.6, -65), g['tuft'], A(g['hi'], .3))
    part(art, strk(P([(46, 82), (40, 94), (32, 100)]), [9, 6, 5]), g['farleg'])
    part(art, strk(P([(76, 80), (82, 91), (90, 95)]), [5, 3.6, 3]), g['fartalon'])
    part(art, E(56, 73, 27, 14.5, -8), g['body'], A(g['hi'], .5), A(g['lo'], .4))
    part(art, E(58, 83, 17, 4, -8), A(g['belly'], .8))
    part(art, E(40, 77, 11.5, 10.5, 20), g['body'], A(g['hi'], .4), A(g['lo'], .35))
    part(art, strk(P([(38, 84), (32, 94), (24, 99)]), [9, 6.5, 5.5]), g['body2'], A(g['hi'], .4), A(g['lo'], .35))
    part(art, E(22, 99.5, 4.8, 3.4), g['paw'], A(g['hi'], .4))
    # saddle: blue blanket, gold trim, leather seat
    part(art, pmask(P([(45, 58), (68, 55), (71, 72), (48, 76)])), g['gold'], A(g['goldhi'], .7))
    part(art, pmask(P([(47, 59.5), (66.5, 57), (69, 70.5), (49.5, 74)])), g['blanket'], A(g['bhi'], .4), A(g['lo'], .3))
    part(art, pmask(P([(55, 63), (59, 62.4), (60, 67), (56, 67.6)])), g['gold'], A(g['goldhi'], .7))
    part(art, E(58, 56.5, 10, 4, -8), g['leather'], A(g['hi'], .35))
    # white chest + feathered front leg with golden talons
    part(art, E(78, 64, 15, 15), g['white'], A((1, 1, 1), .6), A(g['wlo'], .45))
    for (x, y) in [(72, 64), (79, 66), (75, 71), (82, 72), (70, 70), (77, 58)]:
        paint(art, pmask(P([(x - 2.5, y - 1), (x, y + 1.2), (x + 2.5, y - 1), (x, y + 0.2)])), A(g['wlo'], .55))
    part(art, E(81, 76, 6.5, 8), g['white'], A((1, 1, 1), .5), A(g['wlo'], .4))
    part(art, strk(P([(82, 80), (87, 90), (94, 94)]), [4.8, 3.6, 3.2]), g['talon'], A(g['goldhi'], .6))
    for tx, ty in [(95, 92.5), (96.5, 95), (93, 96.5)]:
        paint(art, pmask(P([(tx - 1, ty - 1), (tx + 3.4, ty + 0.6), (tx, ty + 1.4)])), g['claw'])
    # golden neck plate (armour hint)
    part(art, pmask(P([(73, 50), (79, 45), (88, 59), (82, 64), (76, 62)])), g['gold'], A(g['goldhi'], .8), A(g['goldlo'], .5))
    # head: swept-back feathers, white head, gold helm, hooked beak
    for pts in ([(84, 41), (69, 35), (80, 47)], [(83, 47), (67, 45), (80, 53)], [(84, 53), (71, 55), (82, 57)]):
        part(art, pmask(P(pts)), g['white2'], A((1, 1, 1), .4))
    part(art, E(90, 46, 13, 12), g['white'], A((1, 1, 1), .6), A(g['wlo'], .45))
    part(art, pmask(P([(79, 41), (85, 33.5), (96, 33), (102, 37.5), (100, 41), (90, 38.5), (82, 44)])), g['gold'],
         A(g['goldhi'], .9), A(g['goldlo'], .5), hk=1.2, lk=1.6)
    part(art, pmask(P([(88, 33.5), (91, 27.5), (93.5, 33.3)])), g['gold'], A(g['goldhi'], .9))   # helm fin
    part(art, pmask(P([(100, 40), (110, 40.5), (118, 46), (119, 55), (114.5, 51.5), (104, 55), (100, 53)])), g['beak'],
         A(g['goldhi'], .8), A(g['goldlo'], .45), hk=1.2, lk=2)
    paint(art, pmask(P([(101, 49.5), (113, 49), (113.5, 50.3), (101.5, 51)])), g['beakline'])
    paint(art, strk(P([(92, 41.4), (99, 41.8)]), [1.6, 1.2]), A(g['wlo'], .9))         # brow
    part(art, E(96, 45.5, 2.8, 3.3), g['eye'])
    part(art, E(96.9, 44.3, 1.0, 1.0), (1, 1, 1, 1))
    feather_wing(art, sx, sy, th, sp, g['near'], True)

def windrider(art, f, w):
    dy = BOB2[f]; th, sp = BAT_ANG[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + dy, rx, ry, rot)
    sx, sy = 62, 58 + dy
    bat_wing(art, sx + 6, sy - 3, th - 18, sp * 0.95, w, False, 1.2)
    # scorpion tail, curled up over the back, stinger forward
    tail = P([(34, 70), (23, 70), (14, 63), (10, 51), (12, 40), (19, 32), (28, 29)])
    part(art, strk(tail, [8, 7.6, 7.2, 6.8, 6.2, 5.6, 5]), w['tail'], A(w['hi'], .35), A(w['lo'], .4))
    for i, (x, y) in enumerate(tail[1:]):
        r = 5.0 - i * 0.35
        part(art, ell(x, y, r, r), w['tail'], A(w['hi'], .5), A(w['lo'], .45), hk=1.2, lk=2.2)
        paint(art, andnot(ell(x, y, r, r), ell(x + 0.6, y + 0.4, r - 0.9, r - 0.9)), A(w['seg'], .55))
    part(art, E(33, 29, 5.6, 4.6, -10), w['sting'], A(w['hi'], .5), A(w['lo'], .4))
    part(art, pmask(P([(33, 24.5), (42, 25), (47.5, 34.5), (41, 31), (36.5, 33)])), w['barb'], A((1, 1, 1), .5))
    part(art, strk(P([(44, 82), (40, 94), (32, 98)]), [8, 6, 5]), w['farleg'])
    part(art, strk(P([(72, 82), (76, 93), (83, 96)]), [7, 5.6, 5]), w['farleg'])
    part(art, E(55, 75, 27, 14, -6), w['body'], A(w['hi'], .5), A(w['lo'], .4))
    part(art, E(57, 84, 18, 4, -6), A(w['belly'], .85))
    part(art, E(39, 78, 11, 10.5, 20), w['body'], A(w['hi'], .4), A(w['lo'], .35))
    part(art, strk(P([(37, 84), (31, 93), (23, 96)]), [9.5, 7, 6]), w['body'], A(w['hi'], .4), A(w['lo'], .4))
    part(art, E(21.5, 96.5, 5, 3.4), w['paw'], A(w['hi'], .4))
    part(art, strk(P([(74, 80), (80, 91), (88, 94)]), [9, 7, 6]), w['body'], A(w['hi'], .4), A(w['lo'], .4))
    part(art, E(89, 94.5, 5, 3.4), w['paw'], A(w['hi'], .4))
    # saddle: red blanket with dark trim + spikes, leather seat
    part(art, pmask(P([(43, 60), (66, 57), (69, 74), (46, 78)])), w['trim'])
    part(art, pmask(P([(45, 61.5), (64.5, 59), (67, 72.5), (47.5, 76)])), w['blanket'], A(w['bhi'], .4), A(w['lo'], .3))
    for x in (49, 56, 63):
        part(art, pmask(P([(x - 1.6, 74.6 - (x - 49) * 0.13), (x + 1.6, 74.2 - (x - 49) * 0.13), (x, 80 - (x - 49) * 0.13)])), w['trim'])
    part(art, E(56, 58.5, 10, 4, -8), w['leather'], A(w['hi'], .35))
    # shaggy mane
    part(art, pmask(star(83, 57 + dy, 25, 16, 9, 12, 1.0)), w['mane'], A(w['manehi'], .5), A(w['lo'], .4))
    part(art, pmask(star(85, 55 + dy, 17, 11, 9, 32, 1.0)), w['mane2'], A(w['manehi'], .5))
    # ears + cat head + muzzle
    part(art, pmask(P([(87, 39), (89, 25), (97, 37)])), w['ear'], A(w['hi'], .5))
    paint(art, pmask(P([(89, 37), (90, 29), (94.5, 36.5)])), A(w['lo'], .6))
    part(art, E(95, 49, 12, 11), w['head'], A(w['hi'], .55), A(w['lo'], .35))
    part(art, pmask(P([(98, 45), (110, 45.5), (115, 48.5), (115.5, 55.5), (110, 60), (98, 59)])), w['muzzle'],
         A((1, 1, 1), .35), A(w['lo'], .35))
    part(art, pmask(P([(110.5, 46), (116, 48), (113.5, 51.5)])), w['nose'])
    paint(art, pmask(P([(103, 56.4), (113.5, 55.2), (113.7, 56.2), (103.5, 57.6)])), w['nose'])
    for fx in (106, 110):
        part(art, pmask(P([(fx - 1.2, 56.4), (fx + 1.2, 56.1), (fx + 0.2, 60)])), w['fang'])
    paint(art, strk(P([(93, 43), (101.5, 44.3)]), [2.2, 1.6]), w['brow'])
    part(art, E(98, 47.5, 3, 2.4, 10), w['eye'])
    paint(art, E(98.5, 47.5, 0.9, 2.1), C(30, 14, 8))
    bat_wing(art, sx, sy, th, sp, w, True, 1.2)

def bat(art, f, b):
    dy = BOB2[f]; th, sp = BAT_ANG[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + dy, rx, ry, rot)
    sx, sy = 62, 58 + dy
    bat_wing(art, sx + 6, sy - 3, th - 18, sp * 0.95, b, False, 1.08)
    # legs trailing back, hooked feet
    part(art, strk(P([(40, 80), (30, 86), (20, 88)]), [7, 5, 4]), b['farleg'])
    part(art, strk(P([(44, 83), (35, 92), (24, 95)]), [8, 5.5, 4.4]), b['leg'], A(b['hi'], .3))
    for (x, y) in [(20, 88), (24, 95)]:
        for k in (-1.8, 0, 1.8):
            paint(art, pmask(P([(x, y + k - 0.8), (x - 4.4, y + k + 0.6), (x, y + k + 1)])), b['claw'])
    part(art, strk(P([(36, 74), (29, 76)]), [5, 3]), b['body'])        # stubby tail
    # furry body + ruff
    part(art, E(57, 72, 25, 15.5, -6), b['body'], A(b['hi'], .45), A(b['lo'], .45))
    part(art, pmask(star(57, 82 + dy, 18, 13, 11, 0, 0.4)), A(b['fur'], .6))
    part(art, pmask(star(80, 66 + dy, 14, 10, 9, 18, 1.0)), b['fur'], A(b['hi'], .4), A(b['lo'], .35))
    # red-purple saddle
    part(art, pmask(P([(44, 56), (66, 53.5), (69, 70), (47, 74)])), b['trim'], A((1, 1, 1), .35))
    part(art, pmask(P([(46, 57.5), (64.5, 55.5), (67, 68.5), (48.5, 72)])), b['blanket'], A(b['bhi'], .45), A(b['lo'], .35))
    part(art, pmask(P([(48, 66), (66, 63.4), (66.6, 65.3), (48.5, 68)])), b['trim'])
    part(art, E(56, 55, 10, 4, -8), b['leather'], A(b['hi'], .35))
    # big ears (far one darker), round head, pug snout with leaf nose, fangs
    part(art, pmask(P([(83, 48), (77, 23), (92, 44)])), b['farear'], A(b['hi'], .3))
    part(art, pmask(P([(88, 46), (95, 19), (102, 45)])), b['ear'], A(b['hi'], .45))
    paint(art, pmask(P([(91, 44), (95.3, 25), (99.5, 44)])), b['earin'])
    part(art, E(90, 57, 13, 12), b['head'], A(b['hi'], .5), A(b['lo'], .4))
    part(art, E(101.5, 61, 7.5, 6, 8), b['snout'], A(b['hi'], .4), A(b['lo'], .4))
    part(art, pmask(P([(104, 53.5), (108.5, 57.5), (105.5, 60), (102.4, 58)])), b['nose'])
    paint(art, pmask(P([(95, 65.5), (107.5, 64.2), (106, 67.4), (97, 68)])), b['mouth'])
    for fx in (99, 104):
        part(art, pmask(P([(fx - 1.3, 65.6), (fx + 1.3, 65.3), (fx, 70)])), b['fang'])
    paint(art, strk(P([(90, 50.6), (99, 51.6)]), [2.0, 1.4]), b['brow'])
    paint(art, E(95, 55, 4.2, 3.6), A(b['glow'], .35))
    part(art, E(95, 55, 3, 2.6), b['eye'], A((1, 1, 0.8), .6))
    paint(art, E(95.6, 55, 0.9, 1.9), C(40, 8, 8))
    bat_wing(art, sx, sy, th, sp, b, True, 1.08)

def hippogryph(art, f, h):
    dy = BOB2[f]; th, sp = FEATHER_ANG[f]
    P = lambda pts: [(x, y + dy) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + dy, rx, ry, rot)
    sx, sy = 62, 56 + dy
    feather_wing(art, sx + 5, sy - 3, th - 12, sp * 0.9, h['far'], False)
    # long feather plumes for a tail
    for (cx, cy, rx, ry, rot, col) in [(20, 66, 17, 4.2, 25, 'plume2'), (19, 74, 18, 4.4, 5, 'plume'),
                                      (22, 82, 15, 4, -18, 'plume2')]:
        m = E(cx, cy, rx, ry, rot)
        paint(art, dilate(m, W, 2), h['fline'])
        part(art, m, h[col], A(h['phi'], .5), A(h['fline'], .35))
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        paint(art, strk([(cx - c * rx * 0.9, cy + dy - s * rx * 0.9), (cx + c * rx * 0.7, cy + dy + s * rx * 0.7)], [0.9, 0.5]), A(h['fline'], .6))
    # far deer legs with hooves
    part(art, strk(P([(46, 80), (40, 90), (35, 92), (30, 100)]), [8, 4.4, 3.6, 3.2]), h['farleg'])
    part(art, E(29.5, 101, 2.6, 2), h['hoof'])
    part(art, strk(P([(74, 80), (80, 89), (77, 99)]), [6, 3.8, 3.2]), h['farleg'])
    part(art, E(77.5, 100, 2.6, 2), h['hoof'])
    # slim body
    part(art, E(57, 73, 26, 13, -8), h['body'], A(h['hi'], .5), A(h['lo'], .45))
    part(art, E(58, 82, 17, 3.6, -8), A(h['belly'], .8))
    part(art, E(41, 77, 10.5, 10, 20), h['body'], A(h['hi'], .4), A(h['lo'], .35))
    part(art, strk(P([(39, 83), (32, 92), (27, 94), (21, 102)]), [8.5, 4.8, 4, 3.4]), h['leg'], A(h['hi'], .4), A(h['lo'], .3))
    part(art, E(20.5, 103, 2.8, 2.2), h['hoof'], A(h['hi'], .3))
    part(art, strk(P([(77, 79), (84, 88), (81, 99)]), [7, 4.2, 3.6]), h['leg'], A(h['hi'], .4), A(h['lo'], .3))
    part(art, E(81.5, 100.5, 2.8, 2.2), h['hoof'], A(h['hi'], .3))
    # saddle: deep blue blanket, silver trim, moon
    part(art, pmask(P([(45, 58), (68, 55), (71, 72), (48, 76)])), h['trim'], A((1, 1, 1), .4))
    part(art, pmask(P([(47, 59.5), (66.5, 57), (69, 70.5), (49.5, 74)])), h['blanket'], A(h['bhi'], .4), A(h['lo'], .35))
    part(art, andnot(E(58, 66, 3.2, 3.2), E(59.4, 65.2, 2.8, 2.8)), h['trim'])
    part(art, E(58, 56.5, 10, 4, -8), h['leather'], A(h['hi'], .35))
    # teal feathered chest and neck
    part(art, pmask(star(79, 63 + dy, 16, 12, 10, 8, 1.0)), h['chest'], A(h['chi'], .5), A(h['lo'], .35))
    for (x, y) in [(72, 64), (79, 66), (75, 71), (82, 72), (70, 70), (78, 58)]:
        paint(art, pmask(P([(x - 2.5, y - 1), (x, y + 1.2), (x + 2.5, y - 1), (x, y + 0.2)])), A(h['fline'], .5))
    # antlers behind the head (far one darker)
    for off, col in ((-4, 'farantler'), (0, 'antler')):
        o = lambda pts: P([(x + off, y + abs(off) * 0.25) for x, y in pts])
        m = OR(strk(o([(88, 38), (84, 27), (77, 19), (69, 15)]), [4, 3.4, 2.6, 1.8]),
               strk(o([(84.5, 28), (89, 18), (89.5, 11)]), [2.8, 2.2, 1.6]),
               strk(o([(79, 21), (79, 12.5)]), [2.2, 1.4]),
               strk(o([(73, 16.8), (70, 9.5)]), [1.8, 1.2]))
        part(art, m, h[col], A((1, 1, 1), .4), A(h['lo'], .3), hk=0.8, lk=1.2)
    # owl head: feathered head, pale facial disc with ring, big golden eye, short hooked beak
    part(art, pmask(P([(84, 43), (73, 40), (82, 49)])), h['crest'], A(h['chi'], .4))
    part(art, E(92, 47, 13.5, 12.5), h['head'], A(h['chi'], .55), A(h['lo'], .4))
    part(art, E(98, 48, 8.6, 9.6, -5), h['ring'])
    part(art, E(98.4, 48, 7.4, 8.4, -5), h['disc'], A((1, 1, 1), .4), A(h['ring'], .35))
    part(art, E(98.5, 45.5, 3.8, 3.8), h['iris'], A((1, 1, 0.8), .5))
    paint(art, E(99.2, 45.5, 2.0, 2.2), C(18, 14, 30))
    paint(art, E(100, 44.5, 0.8, 0.8), C(255, 255, 255))
    part(art, pmask(P([(103, 47.5), (108.5, 49), (109, 54.5), (106.8, 52.5), (103, 54)])), h['beak'], A((1, 1, 1), .4))
    feather_wing(art, sx, sy, th, sp, h['near'], True)

# ---------------------------------------------------------------- palettes
def fw(feather, fhi, covert, chi, marg, fline, sep):
    return dict(feather=feather, fhi=fhi, covert=covert, chi=chi, marg=marg, fline=fline, sep=sep)

GRY = dict(
    far=fw(C(112, 74, 40), C(150, 104, 60), C(128, 88, 48), C(160, 116, 70), C(140, 100, 58), C(70, 44, 22), C(0, 0, 0)),
    near=fw(C(176, 128, 72), C(232, 204, 150), C(150, 100, 52), C(214, 170, 110), C(238, 226, 200), C(92, 58, 28), C(60, 38, 20)),
    body=vgrad(C(228, 184, 112), C(170, 120, 62), 58, 88), body2=C(196, 148, 84), tuft=C(130, 86, 44),
    farleg=C(150, 104, 56), fartalon=C(196, 150, 50), paw=C(214, 168, 100),
    hi=C(255, 240, 200), lo=C(110, 70, 34), belly=C(244, 222, 176),
    blanket=C(36, 78, 176), bhi=C(120, 160, 240), leather=C(110, 64, 34),
    gold=vgrad(C(250, 210, 90), C(196, 140, 40), 30, 70), goldhi=C(255, 246, 190), goldlo=C(130, 84, 20),
    white=C(248, 246, 238), white2=C(222, 218, 206), wlo=C(150, 150, 160),
    talon=C(240, 186, 60), claw=C(50, 40, 34), beak=vgrad(C(252, 210, 80), C(220, 150, 40), 40, 55),
    beakline=C(150, 96, 30), eye=C(28, 24, 34), outline=C(46, 30, 18))

WR = dict(
    farwing=C(122, 78, 44), wing=vgrad(C(214, 160, 96), C(150, 100, 54), 20, 100), whi=C(250, 222, 170), wlo=C(96, 56, 28),
    bone=C(104, 60, 30), bonehi=C(170, 116, 70), claw=C(240, 230, 210), sep=C(54, 30, 14),
    tail=vgrad(C(206, 148, 80), C(150, 96, 46), 25, 75), seg=C(96, 56, 26), sting=C(120, 66, 34),
    barb=C(240, 230, 204), farleg=C(150, 102, 52),
    body=vgrad(C(232, 184, 108), C(174, 122, 62), 60, 90), belly=C(244, 218, 164), paw=C(232, 206, 156),
    hi=C(255, 236, 190), lo=C(110, 66, 30),
    trim=C(64, 34, 22), blanket=C(168, 32, 28), bhi=C(240, 100, 80), leather=C(92, 52, 28),
    mane=C(104, 56, 28), mane2=C(140, 80, 38), manehi=C(196, 136, 76), ear=C(206, 152, 86),
    head=vgrad(C(236, 190, 116), C(196, 142, 76), 38, 60), muzzle=C(246, 224, 178),
    nose=C(70, 34, 20), fang=C(252, 248, 236), brow=C(96, 52, 26), eye=C(255, 206, 60), outline=C(44, 24, 12))

BAT = dict(
    farwing=C(34, 26, 34), wing=vgrad(C(74, 58, 72), C(40, 30, 42), 20, 100), whi=C(130, 108, 128), wlo=C(20, 14, 22),
    bone=C(98, 82, 92), bonehi=C(150, 132, 140), claw=C(226, 216, 196), sep=C(14, 10, 16),
    farleg=C(46, 38, 46), leg=C(66, 54, 64), body=vgrad(C(96, 80, 92), C(58, 46, 58), 55, 90),
    fur=C(120, 104, 112), hi=C(170, 150, 166), lo=C(26, 18, 28),
    trim=C(212, 196, 150), blanket=vgrad(C(150, 26, 64), C(96, 20, 70), 55, 75), bhi=C(230, 90, 130),
    leather=C(60, 34, 30),
    farear=C(60, 48, 60), ear=C(88, 72, 86), earin=C(168, 104, 124),
    head=vgrad(C(104, 88, 100), C(70, 56, 68), 45, 68), snout=C(128, 108, 116), nose=C(40, 26, 34),
    mouth=C(70, 16, 26), fang=C(250, 246, 232), brow=C(34, 24, 34),
    glow=C(255, 80, 40), eye=C(255, 120, 50), outline=C(12, 8, 14))

HIP = dict(
    far=fw(C(56, 96, 120), C(80, 130, 150), C(70, 66, 120), C(96, 92, 150), C(80, 80, 130), C(30, 34, 60), C(0, 0, 0)),
    near=fw(C(54, 176, 182), C(170, 240, 236), C(110, 84, 176), C(170, 150, 226), C(150, 212, 220), C(34, 40, 82), C(26, 24, 54)),
    plume=C(60, 180, 186), plume2=C(116, 88, 184), phi=C(190, 246, 240), fline=C(34, 40, 82),
    farleg=C(92, 76, 140), leg=C(132, 112, 190), hoof=C(40, 32, 56),
    body=vgrad(C(150, 128, 214), C(98, 80, 160), 58, 88), belly=C(196, 186, 236),
    hi=C(226, 214, 255), lo=C(46, 34, 90),
    trim=C(206, 216, 236), blanket=C(36, 40, 110), bhi=C(110, 120, 220), leather=C(70, 52, 70),
    chest=C(70, 182, 186), chi=C(190, 248, 240),
    farantler=C(150, 140, 120), antler=C(232, 224, 200),
    crest=C(60, 160, 170), head=vgrad(C(90, 196, 198), C(56, 140, 150), 35, 60),
    ring=C(70, 60, 120), disc=C(222, 226, 244), iris=C(250, 196, 60), beak=C(206, 186, 120), outline=C(22, 20, 44))

FLYERS = [('gryphon', gryphon, GRY), ('windrider', windrider, WR), ('bat', bat, BAT), ('hippogryph', hippogryph, HIP)]

def make_sheet2(fn, pal):
    sheet = Img(U * FR, U)
    for f in range(FR):
        art = Img(W, W)
        fn(art, f, pal)
        m = mask_of(art)
        out = Img(W, W)
        paint(out, dilate(m, W, 7), pal['outline'])
        compose(out, art)
        cell = downsample(out, SS)
        blit(sheet, cell, f * U, 0)
    return sheet

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
    """The 10 files in TaxiTime\\media\\: cartoon look; old 64 px flyer_alliance/horde plus the
    four 128 px sheets flyer_gryphon/windrider/bat/hippogryph."""
    pal = lambda kind: PALETTES[('cartoon', kind)]
    files = {'flyer_alliance': make_sheet('gryphon', pal('gryphon'), False),
             'flyer_horde': make_sheet('windrider', pal('windrider'), False),
             **{'flyer_' + name: make_sheet2(fn, p) for name, fn, p in FLYERS},
             'bar_fill': make_fill('cartoon'), 'bar_frame': make_frame('cartoon'),
             'cloud': make_cloud('cartoon'), 'sparkle': make_sparkle()}
    for name, im in files.items():
        write_tga(os.path.join(BASE, name + '.tga'), im)
    print('done: %d files in' % len(files), BASE)

if __name__ == '__main__':
    import sys
    args = sys.argv[1:]
    if 'v2' in args:
        main_v2()                 # python make_art.py v2  -> only the Horde v2 files
    elif 'all' in args:
        main(); main_v2(); main_ship()
    else:
        main_ship()
