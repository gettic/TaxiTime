# Taxi Time - the four flyer sheets (pixel art v3b). Plain Python 3, no libraries.
# Every pixel comes from shapes typed into this file; no outside or Blizzard art.
#
# How it works: each creature is drawn on a 96x96 pixel grid (shapes designed on a 64 grid,
# scaled by Q = 1.5, 4x4 supersampled, hard edges, no anti-aliasing), shaded with small colour
# ramps (cool shadows, warm lights), given a 1 px outline and dark lines where front parts overlap.
# Each 96x96 frame sits centred 1:1 in a 128x128 cell:
#   flyer_<kind>.tga = 512x128, 32-bit with alpha, uncompressed, 4 frames of 128x128,
#   frame i at tex coords (i*0.25, (i+1)*0.25, 0, 1): wings up, going down, down, going up.
#   Shown crisp on the bar at SHEET_SIZE 128 (SHEET_Y -26).
#
# Usage: python make_flyers_v3b.py           -> out\flyer_gryphon/windrider/bat/hippogryph.tga (+ .png)
#        python make_flyers_v3b.py previews  -> also out\previews\ (large frames, bar mock-ups)
# Copy the 4 .tga files to TaxiTime\media\ by hand.
import math, os, struct, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
MEDIA = os.path.join(ROOT, 'TaxiTime', 'media')      # read only: bar parts for the preview mock-ups
OUT = os.path.join(HERE, 'out')
PREV = os.path.join(OUT, 'previews')

Q = 1.5           # design units (64 grid) -> native pixels
N = 96            # native pixel-art frame
SS = 4            # supersampling of the shapes
HR = N * SS
FR = 4
CELL = 128        # frame size in the shipped sheet (native frame centred 1:1)
PADC = (CELL - N) // 2
OY = 3            # whole creature moved down this many pixels (room for the raised wing)

# ================================================================ small image class (straight RGBA 0-255)
class Pic:
    def __init__(s, w, h, fill=(0, 0, 0, 0)):
        s.w, s.h = w, h
        s.px = [fill] * (w * h)

    def over(s, x, y, c):
        if not (0 <= x < s.w and 0 <= y < s.h): return
        a = c[3] / 255
        if a <= 0: return
        i = y * s.w + x; d = s.px[i]; da = d[3] / 255
        oa = a + da * (1 - a)
        if oa <= 0: return
        s.px[i] = tuple(int(round((c[k] * a + d[k] * da * (1 - a)) / oa)) for k in range(3)) + (int(round(oa * 255)),)

def blit(dst, src, ox, oy):
    for y in range(src.h):
        for x in range(src.w):
            c = src.px[y * src.w + x]
            if c[3]: dst.over(x + ox, y + oy, c)

def zoom(p, f):
    out = Pic(p.w * f, p.h * f)
    for y in range(out.h):
        row = p.px[(y // f) * p.w:(y // f + 1) * p.w]
        out.px[y * out.w:(y + 1) * out.w] = [c for c in row for _ in range(f)]
    return out

def crop(p, x0, y0, w, h):
    out = Pic(w, h)
    for y in range(h):
        out.px[y * w:(y + 1) * w] = p.px[(y0 + y) * p.w + x0:(y0 + y) * p.w + x0 + w]
    return out

def _wts(ns, nd):
    sc = ns / nd; W = []
    for i in range(nd):
        a, b = i * sc, (i + 1) * sc; ws = []; j = int(a)
        while j < b and j < ns:
            lo, hi = max(a, j), min(b, j + 1)
            if hi > lo: ws.append((j, (hi - lo) / sc))
            j += 1
        W.append(ws)
    return W

def resize(p, nw, nh):          # area resample, premultiplied (stands in for the game's texture filtering)
    wx, wy = _wts(p.w, nw), _wts(p.h, nh)
    pre = [(c[0] * c[3], c[1] * c[3], c[2] * c[3], c[3]) for c in p.px]
    tmp = []
    for y in range(p.h):
        for x in range(nw):
            acc = [0.0] * 4
            for j, w in wx[x]:
                c = pre[y * p.w + j]
                for k in range(4): acc[k] += c[k] * w
            tmp.append(acc)
    out = Pic(nw, nh)
    for y in range(nh):
        for x in range(nw):
            acc = [0.0] * 4
            for j, w in wy[y]:
                c = tmp[j * nw + x]
                for k in range(4): acc[k] += c[k] * w
            a = acc[3]
            out.px[y * nw + x] = (0, 0, 0, 0) if a < 0.5 else tuple(int(round(acc[k] / a)) for k in range(3)) + (int(round(a)),)
    return out

def write_png(path, p):
    raw = bytearray()
    for y in range(p.h):
        raw.append(0)
        for c in p.px[y * p.w:(y + 1) * p.w]: raw += bytes(c)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', p.w, p.h, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))

def write_tga(path, p):         # uncompressed 32-bit, bottom-left origin, 8 alpha bits
    body = bytearray()
    for y in range(p.h - 1, -1, -1):
        for r, g, b, a in p.px[y * p.w:(y + 1) * p.w]: body += bytes((b, g, r, a))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, p.w, p.h, 32, 8) + body)

def read_tga(path):
    d = open(path, 'rb').read()
    w, h = struct.unpack('<HH', d[12:16]); assert d[2] == 2 and d[16] == 32
    off = 18 + d[0]; top = d[17] & 0x20; p = Pic(w, h)
    for row in range(h):
        y = row if top else h - 1 - row
        for x in range(w):
            b, g, r, a = d[off:off + 4]; off += 4
            p.px[y * w + x] = (r, g, b, a)
    return p

# ================================================================ shapes -> hi-res bit masks
def pmask(pts):
    P = [(x * Q * SS, (y + OY) * Q * SS) for x, y in pts]; n = len(P); rows = [0] * HR
    ys = [q[1] for q in P]
    y0 = max(0, int(math.floor(min(ys)))); y1 = min(HR - 1, int(math.ceil(max(ys))))
    for py in range(y0, y1 + 1):
        yc = py + 0.5; xs = []
        for i in range(n):
            ax, ay = P[i]; bx, by = P[(i + 1) % n]
            if (ay <= yc < by) or (by <= yc < ay):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            xa = max(0, int(math.ceil(xs[j] - 0.5))); xb = min(HR - 1, int(math.floor(xs[j + 1] - 0.5)))
            if xb >= xa: rows[py] |= ((1 << (xb - xa + 1)) - 1) << xa
    return rows

def epts(cx, cy, rx, ry, rot=0, n=40):
    t = math.radians(rot); ct, st = math.cos(t), math.sin(t)
    return [(cx + rx * math.cos(2 * math.pi * i / n) * ct - ry * math.sin(2 * math.pi * i / n) * st,
             cy + rx * math.cos(2 * math.pi * i / n) * st + ry * math.sin(2 * math.pi * i / n) * ct) for i in range(n)]

def ell(cx, cy, rx, ry, rot=0):
    return pmask(epts(cx, cy, rx, ry, rot))

def OR(*ms):
    out = [0] * HR
    for m in ms: out = [a | b for a, b in zip(out, m)]
    return out

def SUB(a, b):
    return [x & ~y for x, y in zip(a, b)]

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
        ms.append(pmask(epts(x, y, w / 2, w / 2, 0, 16)))
    return OR(*ms)

def star(cx, cy, ro, ri, n, rot=0, sy=1.0):
    pts = []
    for i in range(2 * n):
        r = ro if i % 2 == 0 else ri; a = math.radians(rot) + math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a) * sy))
    return pmask(pts)

PC = [bin(i).count('1') for i in range(16)]

def cover(m):
    out = [0] * (N * N)
    for ny in range(N):
        r = m[ny * SS:(ny + 1) * SS]
        if not (r[0] | r[1] | r[2] | r[3]): continue
        for nx in range(N):
            sh = nx * SS
            out[ny * N + nx] = PC[(r[0] >> sh) & 15] + PC[(r[1] >> sh) & 15] + PC[(r[2] >> sh) & 15] + PC[(r[3] >> sh) & 15]
    return out

# ================================================================ colour ramps (hue-shifted: cool shade, warm light)
SHADE = (34, 18, 52)
LIGHT = (255, 246, 206)

def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

def ramp(c, dk=(0.66, 0.36), lt=(0.28, 0.56), shade=SHADE, light=LIGHT):
    """5 shades, index 0 darkest .. 4 lightest, base colour at 2."""
    return [mix(c, shade, dk[0]), mix(c, shade, dk[1]), tuple(c), mix(c, light, lt[0]), mix(c, light, lt[1])]

# light comes from the upper left (and a bit from the front)
LX, LY = -0.45, -0.89
BAYER = [[0.0, 0.5], [0.75, 0.25]]

class Frame:
    def __init__(s):
        s.parts = []
        s.lab = [-1] * (N * N)

    def add(s, m, rp, base=2, sph=None, k=1.6, rim=1, low=1, line=False, thr=8, group=None, dith=0.0, flat=False):
        """m: mask; rp: ramp; sph: (cx, cy, rx, ry) round shading; rim/low: light top edge, dark bottom edge;
        line: dark line where this part lies over parts behind it; thr: coverage (of 16) to count as filled."""
        idx = len(s.parts)
        if sph: sph = (sph[0] * Q, (sph[1] + OY) * Q, sph[2] * Q, sph[3] * Q)
        s.parts.append(dict(rp=rp, base=base, sph=sph, k=k, rim=rim, low=low, line=line,
                            group=idx if group is None else group, dith=dith, flat=flat))
        cov = cover(m)
        lab = s.lab
        for i, c in enumerate(cov):
            if c >= thr: lab[i] = idx
        return idx

    def render(s):
        lab, parts = s.lab, s.parts
        pic = Pic(N, N)
        def L(x, y):
            return lab[y * N + x] if 0 <= x < N and 0 <= y < N else -1
        for y in range(N):
            for x in range(N):
                p = lab[y * N + x]
                if p < 0: continue
                P = parts[p]; g = P['group']; rp = P['rp']
                if P['flat']:
                    pic.px[y * N + x] = rp[P['base']] + (255,); continue
                v = P['base']
                if P['sph']:
                    cx, cy, rx, ry = P['sph']
                    nx = (x + 0.5 - cx) / rx; ny = (y + 0.5 - cy) / ry
                    v += P['k'] * max(-1.0, min(1.0, nx * LX + ny * LY))
                def same(xx, yy):
                    q = L(xx, yy)
                    return q >= 0 and parts[q]['group'] == g
                if P['rim'] and not same(x, y - 1): v += P['rim']
                if P['low'] and not same(x, y + 1): v -= P['low']
                if P['dith']: v += (BAYER[y % 2][x % 2] - 0.375) * P['dith']
                i = max(0, min(len(rp) - 1, int(math.floor(v + 0.5))))
                col = rp[i]
                if P['line']:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        q = L(x + dx, y + dy)
                        if 0 <= q < p and parts[q]['group'] != g:
                            col = rp[0]; break
                pic.px[y * N + x] = col + (255,)
        # 1 px outline outside the silhouette, from the darkest shade of the part it touches
        out = list(pic.px)
        for y in range(N):
            for x in range(N):
                if lab[y * N + x] >= 0: continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    q = L(x + dx, y + dy)
                    if q >= 0:
                        d = parts[q]['rp'][0]
                        oc = getattr(s, 'outline', None) or mix(d, (10, 6, 12), 0.6)
                        out[y * N + x] = oc + (255,); break
        pic.px = out
        return pic

# ================================================================ wings
def wpts(local, sx, sy, th, sp):
    t = math.radians(th); ux, uy = math.cos(t), math.sin(t)
    px, py = -math.sin(t), math.cos(t)
    if px > 0.01 or (abs(px) <= 0.01 and py < 0): px, py = -px, -py     # trailing edge faces back
    return [(sx + ux * u * sp + px * v, sy + uy * u * sp + py * v) for u, v in local]

# frames: wings up, going down, down, going up
FEATHER_ANG = [(-116, 1.0), (-170, 0.7), (136, 0.9), (-142, 0.78)]
BAT_ANG = [(-92, 1.0), (-160, 0.74), (122, 0.94), (-128, 0.8)]
BOB = [1, 0, -1, 0]

# feathered wing in wing space: u along the span (root 0 -> tip ~33), v = toward the trailing edge
FW_COV = [(0, -3.5), (9, -6), (18, -6.4), (25, -5), (29, -2.6), (24, 1.2), (17, 2.6), (9, 3.2), (0, 3.4)]
FW_MARG = [(0, -3.5), (9, -6), (18, -6.4), (25, -5), (28, -3.4), (18, -3.4), (9, -2.8), (0, -1.4)]
# (u, v) base, angle from the span axis toward the trailing edge, length, half-width
FW_PRIM = [(26, -3.5, 8, 10.5, 1.55), (25, -2.2, 26, 11, 1.6), (23.5, -0.8, 44, 11, 1.6), (21.5, 0.2, 60, 10.5, 1.6),
           (19, 0.8, 74, 10, 1.6)]
FW_SEC = [(16, 1.0, 82, 9, 1.7), (12.5, 1.2, 86, 8.6, 1.7), (9, 1.3, 88, 8.2, 1.7), (5.5, 1.3, 90, 7.6, 1.7),
          (2, 1.2, 92, 7, 1.7)]

def feather_wing(F, sx, sy, th, sp, R, near, sc=1.0):
    W = lambda pts: wpts([(u * sc, v * sc) for u, v in pts], sx, sy, th, sp)
    def feather(u, v, ang, ln, hw):
        a = math.radians(ang); ca, sa = math.cos(a), math.sin(a)
        loc = []
        for i in range(16):                       # tapered feather, rounded tip
            t = i / 15; w = hw * (0.75 + 0.35 * math.sin(t * math.pi)) * (1 - 0.35 * t)
            loc.append((t * ln, -w))
        for i in range(16):
            t = 1 - i / 15; w = hw * (0.75 + 0.35 * math.sin(t * math.pi)) * (1 - 0.35 * t)
            loc.append((t * ln, w))
        return pmask(W([(u + x * ca - y * sa, v + x * sa + y * ca) for x, y in loc]))
    feathers = [feather(*p) for p in FW_PRIM] + [feather(*p) for p in reversed(FW_SEC)]
    if not near:
        F.add(OR(pmask(W(FW_COV)), *feathers), R['far'], base=2, rim=0, low=0)
        return
    for i, m in enumerate(feathers):                 # tip feathers first, so inner ones overlap them
        F.add(m, R['prim'], base=2 if i % 2 == 0 else 1, rim=0, low=0, line=True)
    g = len(F.parts)
    F.add(pmask(W(FW_COV)), R['cov'], base=2, rim=0, low=1, line=True, group=g)
    for u in (6, 12, 18):                            # covert feather row
        F.add(pmask(W([(u - 3, 2.2), (u, 3.6), (u + 3, 2.2), (u, 2.8)])), R['cov'], base=0, flat=True, thr=6, group=g)
    F.add(pmask(W(FW_MARG)), R['marg'], base=2, rim=1, low=0, group=g)
BW_MEMB = [(0, -3), (9, -6.5), (16, -7.2), (30, -2.6), (25, 1.6), (26.5, 8.4), (20.5, 5.6), (19.5, 13.4), (14, 8.4),
           (11, 13.4), (6, 8.2), (0, 7)]
BW_ARM = [(0, -2), (9, -6), (16, -6.6)]
BW_FING = [[(16, -6.6), (30, -2.6)], [(16, -6.6), (26.5, 8.2)], [(16, -6.6), (19.5, 13.2)], [(14, -6.2), (11, 13.2)]]

def bat_wing(F, sx, sy, th, sp, R, near, sc=1.0):
    W = lambda pts: wpts([(u * sc, v * sc) for u, v in pts], sx, sy, th, sp)
    if not near:
        F.add(pmask(W(BW_MEMB)), R['farwing'], base=2, rim=0, low=0)
        return
    g = len(F.parts)
    F.add(pmask(W(BW_MEMB)), R['memb'], base=2, rim=0, low=1, line=True, group=g)
    F.add(OR(strk(W(BW_ARM), [2.0, 1.6, 1.4]), *[strk(W(f), [1.1, 0.9]) for f in BW_FING]), R['bone'],
          base=2, rim=1, low=0, thr=6, group=g + 1, line=False)
    wx, wy = W([(16, -6.6)])[0]
    F.add(pmask([(wx - 0.8, wy - 0.4), (wx + 1.2, wy - 3.2), (wx + 1.4, wy + 0.4)]), R['claw'], base=3, rim=0, low=0, thr=6)

# ================================================================ creatures
def gryphon(f, R):
    F = Frame(); b = BOB[f]; th, sp = FEATHER_ANG[f]
    P = lambda pts: [(x, y + b) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + b, rx, ry, rot)
    S = lambda cx, cy, rx, ry: (cx, cy + b, rx, ry)
    sx, sy = 31, 29 + b
    feather_wing(F, sx + 2.5, sy - 1.5, th - 12, sp * 0.9, R, False, 0.95)
    # lion tail with a dark tuft, streaming back
    F.add(strk(P([(19, 37), (13, 38), (8, 36.5), (4.5, 34)]), [2.6, 2.2, 1.8, 1.6]), R['body'], base=2)
    F.add(E(3.5, 33.5, 3.2, 2.1, -25), R['tuft'], sph=S(3.5, 33.5, 3.2, 2.1))
    # far legs (darker)
    F.add(strk(P([(22, 40), (16, 44), (11, 45.5)]), [4, 3, 2.4]), R['bodyfar'], base=2, rim=0)
    F.add(strk(P([(41, 40), (44, 44.5), (48.5, 46)]), [2.4, 1.8, 1.4]), R['talonfar'], base=2, rim=0)
    # body + haunch (one group so no seam)
    g = F.add(E(29, 36, 13.5, 7, -6), R['body'], sph=S(29, 36, 13.5, 7), dith=0.5)
    F.add(E(19.5, 37.5, 6.2, 5.6, 20), R['body'], sph=S(19.5, 37.5, 6.2, 5.6), group=g, dith=0.5)
    F.add(E(30, 41.5, 9, 2, -6), R['belly'], base=2, rim=0, group=g)
    # near hind leg tucked back, paw
    F.add(strk(P([(19, 41), (13, 45.5), (7.5, 47)]), [4.4, 3.2, 2.6]), R['body'], base=2, line=True)
    F.add(E(6.5, 47, 2.4, 1.7), R['body'], base=3, rim=0)
    # saddle: blue blanket, gold trim, brown seat
    F.add(pmask(P([(23, 30), (35.5, 28.4), (37, 37), (24.5, 39.5)])), R['gold'], base=2, line=True)
    F.add(pmask(P([(24.2, 31), (34.4, 29.6), (35.7, 36), (25.5, 38.2)])), R['blue'], base=2)
    F.add(pmask(P([(29, 32.6), (31, 32.3), (31.3, 34.6), (29.3, 34.9)])), R['gold'], base=3, rim=0, low=0)
    F.add(E(29.5, 28.6, 5.4, 2, -7), R['leather'], sph=S(29.5, 28.6, 5.4, 2), line=True)
    # white chest + feathered front leg with yellow talons
    gc = F.add(star(40, 33 + b, 8.4, 6.8, 11, 0, 1.0), R['white'], sph=S(40, 33, 8, 8), line=True)
    F.add(E(41.5, 38.5, 3.4, 4.2), R['white'], sph=S(41.5, 38.5, 3.4, 4.2), group=gc)
    F.add(strk(P([(42, 41), (45, 44.5), (49, 45.5)]), [2.4, 1.9, 1.6]), R['talon'], base=2)
    for tx, ty in [(49.5, 44.6), (50.4, 46.2)]:
        F.add(pmask(P([(tx - 0.5, ty - 0.6), (tx + 2, ty + 0.3), (tx, ty + 0.9)])), R['claw'], base=1, flat=True, thr=5)
    # head feathers swept back (ear tufts) - the classic gryphon outline
    gh = F.add(pmask(P([(44, 22.5), (34.5, 17.5), (37, 20.5), (35.5, 21.5), (42, 26)])), R['white'], base=2)
    F.add(pmask(P([(43, 26), (35.5, 25.5), (41.5, 29.5)])), R['white'], base=1, group=gh)
    F.add(E(46.5, 26, 6.6, 6.1), R['white'], sph=S(46.5, 26, 6.6, 6.1), group=gh)
    # big hooked yellow beak
    F.add(pmask(P([(50.5, 22.6), (55, 22.8), (58.6, 25.4), (59.2, 29.8), (57.6, 30.4), (56.4, 28.2), (51.5, 29.6)])),
          R['beak'], sph=S(54, 24, 6, 5), line=True)
    F.add(strk(P([(52, 28), (56.2, 27.6)]), [0.9, 0.9]), R['beak'], base=0, flat=True, thr=5)
    # fierce brow + eye
    F.add(strk(P([(46.6, 23.4), (50.6, 23.9)]), [1.3, 1.1]), R['white'], base=0, flat=True, thr=6)
    F.add(E(49.3, 25.3, 1.15, 1.25), R['eye'], base=2, flat=True, thr=6)
    feather_wing(F, sx, sy, th, sp, R, True, 0.95)
    return F.render()

def windrider(f, R):
    F = Frame(); b = BOB[f]; th, sp = BAT_ANG[f]
    P = lambda pts: [(x, y + b) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + b, rx, ry, rot)
    S = lambda cx, cy, rx, ry: (cx, cy + b, rx, ry)
    sx, sy = 31, 30 + b
    bat_wing(F, sx + 3, sy - 1.5, th - 16, sp * 0.92, R, False, 1.1)
    # segmented scorpion tail curling up over the back, stinger pointing forward
    tail = P([(19, 36), (12.5, 35.5), (7.5, 31.5), (5.5, 25.5), (7.5, 19.5), (12, 15.5), (17.5, 14.5)])
    gt = F.add(strk(tail, [3.6, 3.4, 3.2, 3.0, 2.8, 2.6, 2.4]), R['tail'], base=2)
    for i, (x, y) in enumerate(tail[1:]):
        r = 2.4 - i * 0.12
        F.add(ell(x, y, r, r), R['tail'], base=2 if i % 2 else 3, sph=(x, y, r, r), k=1.3, rim=0, low=0, line=True)
    F.add(E(18.5, 14.5, 2.8, 2.4), R['tail'], sph=S(18.5, 14.5, 2.8, 2.4), line=True)
    F.add(pmask(P([(18.5, 11.8), (23.5, 12.2), (27.5, 17.8), (23, 15.6), (20, 17.2)])), R['sting'], base=2, line=True)
    # far legs
    F.add(strk(P([(22, 40.5), (16, 44.5), (10.5, 46)]), [4, 3, 2.6]), R['bodyfar'], base=2, rim=0)
    F.add(strk(P([(40, 40), (43.5, 44.5), (48, 45.5)]), [3.6, 2.8, 2.4]), R['bodyfar'], base=2, rim=0)
    # tawny lion body
    g = F.add(E(28.5, 36.5, 13.5, 6.8, -5), R['body'], sph=S(28.5, 36.5, 13.5, 6.8), dith=0.5)
    F.add(E(19.5, 38, 6, 5.4, 20), R['body'], sph=S(19.5, 38, 6, 5.4), group=g, dith=0.5)
    F.add(E(30, 41.6, 9, 1.9, -5), R['belly'], base=2, rim=0, group=g)
    # dark stripes on the back
    for x in (15, 19.5, 24):
        F.add(strk(P([(x, 31.5 + (24 - x) * 0.05), (x - 1.4, 35)]), [1.2, 0.8]), R['body'], base=0, flat=True, thr=6)
    # near legs: hind tucked back, front reaching forward, big paws
    F.add(strk(P([(19, 41.5), (13, 46), (7.5, 47.5)]), [4.6, 3.4, 2.8]), R['body'], base=2, line=True)
    F.add(E(6.8, 47.6, 2.5, 1.8), R['paw'], base=2, rim=0)
    F.add(strk(P([(39.5, 40.5), (43, 45), (47.5, 46.5)]), [4, 3, 2.6]), R['body'], base=2, line=True)
    F.add(E(48, 46.5, 2.5, 1.8), R['paw'], base=2, rim=0)
    # saddle: red blanket, dark trim with spikes, leather seat
    F.add(pmask(P([(22.5, 30.5), (35, 29), (36.5, 37.4), (24, 39.6)])), R['trim'], base=2, line=True)
    F.add(pmask(P([(23.6, 31.4), (34, 30.1), (35.3, 36.4), (25, 38.4)])), R['red'], base=2)
    for x in (25.5, 29.5, 33.5):
        F.add(pmask(P([(x - 0.9, 38.8 - (x - 25) * 0.18), (x + 0.9, 38.6 - (x - 25) * 0.18), (x, 41.8 - (x - 25) * 0.18)])),
              R['spike'], base=3, rim=0, low=0, thr=6)
    F.add(E(29, 29.2, 5.4, 2, -7), R['leather'], sph=S(29, 29.2, 5.4, 2), line=True)
    # shaggy dark mane around neck and head
    gm = F.add(star(42.5, 29.5 + b, 10.5, 6.8, 10, 10, 1.0), R['mane'], sph=S(42.5, 29.5, 10, 10), k=1.4, line=True)
    F.add(star(44, 27.5 + b, 7.5, 5, 8, 30, 1.0), R['mane'], base=3, sph=S(44, 27.5, 7.5, 7.5), k=1.2, group=gm)
    # swept-back ears, small horns
    F.add(pmask(P([(46, 22), (37.5, 14.5), (49, 20.5)])), R['body'], base=3, line=True)
    F.add(pmask(P([(45.6, 20.8), (40.6, 16.6), (47.6, 20.4)])), R['earin'], base=2, flat=True, thr=6)
    # head + long muzzle with fangs
    gh = F.add(E(49, 26.5, 5.6, 5.2), R['head'], sph=S(49, 26.5, 5.6, 5.2), line=True)
    F.add(pmask(P([(51.5, 24.2), (55.6, 24.2), (58.6, 26.2), (58.8, 30.4), (55.6, 32.8), (51, 32)])), R['muzzle'],
          sph=S(55, 25, 6, 5), group=gh)
    F.add(pmask(P([(56.2, 24.4), (59, 25.8), (58, 27.6), (56.2, 26.6)])), R['nose'], base=2, flat=True, thr=6)
    F.add(strk(P([(52.5, 30.2), (58.4, 29.6)]), [0.9, 0.9]), R['nose'], base=2, flat=True, thr=5)
    F.add(pmask(P([(43.5, 22.5), (47.5, 19.8), (52.4, 21.6), (53, 23.6), (48, 23.4), (44.5, 26)])), R['mane'], base=2,
          sph=S(48, 21, 5, 3), line=True)
    for fx in (54.2, 57):
        F.add(pmask(P([(fx - 0.7, 29.6), (fx + 0.7, 29.5), (fx, 32.6)])), R['fang'], base=2, flat=True, thr=5)
    F.add(strk(P([(47.4, 23.6), (52, 24.4)]), [1.3, 1.1]), R['mane'], base=0, flat=True, thr=6)
    F.add(E(50.4, 25.6, 1.25, 1.0), R['eye'], base=2, flat=True, thr=5)
    F.add(E(50.8, 25.6, 0.5, 0.9), R['pupil'], base=2, flat=True, thr=4)
    bat_wing(F, sx, sy, th, sp, R, True, 1.1)
    return F.render()

def bat(f, R):
    F = Frame(); b = BOB[f]; th, sp = BAT_ANG[f]
    P = lambda pts: [(x, y + b) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + b, rx, ry, rot)
    S = lambda cx, cy, rx, ry: (cx, cy + b, rx, ry)
    F.outline = (58, 40, 72)       # lighter violet edge so the dark bat stays visible on the dark bar
    sx, sy = 32, 30 + b
    bat_wing(F, sx + 3, sy - 1.5, th - 16, sp * 0.95, R, False, 1.25)
    # legs trailing back with hooked feet
    F.add(strk(P([(25, 39), (18, 42), (11, 43)]), [3.2, 2.4, 1.8]), R['legfar'], base=2, rim=0)
    F.add(strk(P([(27, 40.5), (20, 45), (12.5, 46.5)]), [3.6, 2.6, 2]), R['leg'], base=2)
    for (x, y) in [(11, 43), (12.5, 46.5)]:
        for k in (-0.9, 0.9):
            F.add(pmask(P([(x, y + k - 0.5), (x - 2.6, y + k + 0.3), (x, y + k + 0.6)])), R['claw'], base=2, flat=True, thr=5)
    # furry body + ruff
    g = F.add(E(31, 36, 11.5, 7.2, -8), R['body'], sph=S(31, 36, 11.5, 7.2), dith=0.5)
    F.add(star(31, 41.5 + b, 9, 6.5, 9, 0, 0.35), R['body'], base=1, group=g, rim=0)
    F.add(strk(P([(21, 35), (17, 35.5)]), [2.4, 1.4]), R['body'], base=2, group=g)
    gr = F.add(star(40.5, 34.5 + b, 7.5, 5.4, 9, 16, 1.0), R['fur'], sph=S(40.5, 34.5, 7.5, 7.5), line=True)
    # Forsaken saddle: purple blanket, bone trim
    F.add(pmask(P([(24, 29.5), (35, 28.2), (36.6, 36.4), (25.4, 38.6)])), R['bonew'], base=2, line=True)
    F.add(pmask(P([(25.1, 30.4), (34, 29.3), (35.3, 35.4), (26.3, 37.3)])), R['purple'], base=2)
    F.add(E(29.5, 28.6, 5, 1.9, -7), R['leather'], sph=S(29.5, 28.6, 5, 1.9), line=True)
    # huge ears (far one darker), pink inside
    F.add(pmask(P([(41, 27), (38, 14.5), (46, 25)])), R['earfar'], base=2, rim=0, low=0)
    ge = F.add(pmask(P([(44, 26.5), (47, 12.5), (51, 26)])), R['ear'], base=2, line=True)
    F.add(pmask(P([(45.6, 25.5), (47.2, 16.5), (49.4, 25.4)])), R['earin'], base=2, group=ge, rim=0)
    # round head, pug snout with leaf nose, fangs, glowing eyes
    gh = F.add(E(46.5, 31, 6.6, 6.2), R['head'], sph=S(46.5, 31, 6.6, 6.2), line=True)
    F.add(E(52.5, 33, 3.8, 3.2, 8), R['snout'], sph=S(52.5, 33, 3.8, 3.2), group=gh)
    F.add(pmask(P([(53.5, 28.6), (56, 30.8), (54.4, 32.4), (52.8, 31)])), R['nose'], base=2, flat=True, thr=6)
    F.add(strk(P([(49.5, 35.4), (55.2, 34.6)]), [1.0, 0.9]), R['mouth'], base=2, flat=True, thr=5)
    for fx in (51, 53.8):
        F.add(pmask(P([(fx - 0.7, 35.2), (fx + 0.7, 35.1), (fx, 37.8)])), R['fang'], base=2, flat=True, thr=5)
    F.add(strk(P([(46.2, 28), (51, 28.8)]), [1.2, 1.0]), R['head'], base=0, flat=True, thr=6)
    F.add(E(49.2, 30.2, 1.5, 1.3), R['eye'], base=2, flat=True, thr=5)
    F.add(E(49.6, 29.8, 0.55, 0.55), R['eye'], base=4, flat=True, thr=3)
    bat_wing(F, sx, sy, th, sp, R, True, 1.25)
    return F.render()

def hippogryph(f, R):
    F = Frame(); b = BOB[f]; th, sp = FEATHER_ANG[f]
    P = lambda pts: [(x, y + b) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + b, rx, ry, rot)
    S = lambda cx, cy, rx, ry: (cx, cy + b, rx, ry)
    sx, sy = 31, 29 + b
    feather_wing(F, sx + 2.5, sy - 1.5, th - 12, sp * 0.9, R, False, 0.92)
    # long tail plumes
    for cx, cy, rx, ry, rot, key in [(10, 32.5, 9, 2.1, 22, 'plume2'), (9, 36.5, 9.5, 2.3, 4, 'plume'),
                                     (10.5, 40.5, 8, 2.0, -16, 'plume2')]:
        F.add(E(cx, cy, rx, ry, rot), R[key], sph=S(cx, cy, rx, ry), line=True)
    # far deer legs folded, hooves
    F.add(strk(P([(24, 40), (22, 45), (17, 46), (14, 49)]), [3.8, 2.2, 1.8, 1.6]), R['legfar'], base=2, rim=0)
    F.add(E(13.6, 49.6, 1.4, 1.1), R['hoof'], base=1, flat=True, thr=6)
    F.add(strk(P([(39, 40), (43, 44), (41, 48.5)]), [3, 2, 1.7]), R['legfar'], base=2, rim=0)
    F.add(E(41, 49.2, 1.4, 1.1), R['hoof'], base=1, flat=True, thr=6)
    # slim purple body
    g = F.add(E(29, 36.5, 13, 6.4, -6), R['body'], sph=S(29, 36.5, 13, 6.4), dith=0.5)
    F.add(E(20.5, 38, 5.4, 5, 20), R['body'], sph=S(20.5, 38, 5.4, 5), group=g, dith=0.5)
    F.add(E(30, 41.4, 8.5, 1.7, -6), R['belly'], base=2, rim=0, group=g)
    # near legs: thin deer legs, folded
    F.add(strk(P([(21, 41.5), (19, 46.5), (13.5, 47.5), (10.5, 50.5)]), [4.4, 2.4, 2, 1.8]), R['leg'], base=2, line=True)
    F.add(E(10, 51.1, 1.5, 1.2), R['hoof'], base=2, flat=True, thr=6)
    F.add(strk(P([(38.5, 41), (43.5, 45.5), (41.5, 50)]), [3.4, 2.2, 1.8]), R['leg'], base=2, line=True)
    F.add(E(41.4, 50.7, 1.5, 1.2), R['hoof'], base=2, flat=True, thr=6)
    # night elf saddle: deep blue blanket, silver trim, moon
    F.add(pmask(P([(23, 30), (35.5, 28.4), (37, 37), (24.5, 39.5)])), R['silver'], base=2, line=True)
    F.add(pmask(P([(24.2, 31), (34.4, 29.6), (35.7, 36), (25.5, 38.2)])), R['navy'], base=2)
    F.add(SUB(E(29.8, 33.8, 2.2, 2.2), E(30.9, 33.2, 1.9, 1.9)), R['silver'], base=3, flat=True, thr=6)
    F.add(E(29.5, 28.6, 5.2, 1.9, -7), R['leather'], sph=S(29.5, 28.6, 5.2, 1.9), line=True)
    # teal feathered chest and neck
    gc = F.add(star(40, 32.5 + b, 8.4, 6.6, 9, 8, 1.0), R['teal'], sph=S(40, 32.5, 8, 8), line=True)
    for (x, y) in [(37, 33), (40.5, 34.5), (38.5, 37.5), (42, 38), (43, 31.5)]:
        F.add(pmask(P([(x - 1.3, y - 0.5), (x, y + 0.7), (x + 1.3, y - 0.5), (x, y + 0.1)])), R['teal'], base=1, flat=True, thr=6)
    # antlers (far one darker), sweeping up and back
    for off, key in ((-2.2, 'antlerfar'), (0, 'antler')):
        o = lambda pts: P([(x + off, y + abs(off) * 0.4) for x, y in pts])
        F.add(OR(strk(o([(45, 21.5), (41.5, 16), (36.5, 12.5), (30.5, 11.5)]), [2.0, 1.7, 1.3, 1.0]),
                 strk(o([(42, 17), (44, 11.5), (43.6, 7.4)]), [1.4, 1.1, 0.9]),
                 strk(o([(38, 13.6), (37.6, 8.2)]), [1.2, 0.9]),
                 strk(o([(33.6, 12), (31.6, 8)]), [1.0, 0.8])), R[key], base=2, line=True, thr=6)
    # owl head: teal feathers, pale facial disc, big golden eye, short hooked beak
    F.add(pmask(P([(42.5, 23), (36.5, 21.5), (41.5, 26.5)])), R['teal'], base=2)
    gh = F.add(E(47, 26, 6.8, 6.3), R['teal'], sph=S(47, 26, 6.8, 6.3), line=True)
    F.add(E(49.6, 26.6, 4.4, 4.8, -5), R['ring'], base=2, flat=True, group=gh)
    F.add(E(49.8, 26.6, 3.7, 4.1, -5), R['disc'], sph=S(49.8, 25.6, 3.7, 4.1), k=1.0, group=gh, rim=0, low=0)
    F.add(E(50.1, 25.3, 2.0, 2.0), R['iris'], sph=S(50.1, 25.3, 2, 2), k=0.8, rim=0, low=0, thr=6)
    F.add(E(50.6, 25.3, 1.05, 1.15), R['pupil'], base=2, flat=True, thr=4)
    F.add(E(51.1, 24.5, 0.5, 0.5), R['disc'], base=4, flat=True, thr=3)
    F.add(pmask(P([(53.6, 25.8), (56.2, 26.5), (56.8, 29.6), (55.5, 28.8), (53.8, 29.6)])), R['beak'],
          sph=S(55, 25.8, 3, 3), k=1.0, line=True)
    feather_wing(F, sx, sy, th, sp, R, True, 0.92)
    return F.render()

# ================================================================ palettes (WoW-like colours, our own picks)
def R5(c, **kw):
    return ramp(c, **kw)

GRY = dict(
    far=R5((118, 76, 40)), prim=R5((142, 92, 48)), cov=R5((200, 146, 78)), marg=R5((240, 226, 196)),
    body=R5((214, 158, 82)), bodyfar=R5((156, 104, 54)), tuft=R5((112, 64, 30)), belly=R5((238, 206, 150)),
    gold=R5((236, 186, 60)), blue=R5((40, 86, 196)), leather=R5((120, 68, 36)),
    white=R5((236, 234, 226), dk=(0.5, 0.25), lt=(0.4, 0.8)), talon=R5((236, 180, 48)), talonfar=R5((176, 126, 36)),
    claw=R5((48, 36, 34)), beak=R5((246, 190, 44)), eye=R5((24, 18, 30)))

WR = dict(
    farwing=R5((120, 58, 34)), memb=R5((214, 116, 58)), bone=R5((104, 52, 28)), claw=R5((236, 224, 200)),
    tail=R5((196, 132, 66)), sting=R5((232, 220, 190)),
    body=R5((214, 150, 76)), bodyfar=R5((150, 96, 48)), belly=R5((236, 200, 140)), paw=R5((226, 186, 128)),
    trim=R5((70, 36, 26)), red=R5((178, 30, 26)), spike=R5((214, 206, 190)), leather=R5((98, 54, 30)),
    mane=R5((118, 54, 22)), earin=R5((150, 82, 64)),
    head=R5((222, 164, 90)), muzzle=R5((238, 204, 150)), nose=R5((60, 28, 18)), fang=R5((252, 248, 236)),
    eye=R5((255, 200, 40)), pupil=R5((40, 16, 8)))

BAT = dict(
    farwing=R5((26, 18, 30)), memb=R5((52, 38, 58)), bone=R5((98, 76, 104)), claw=R5((232, 222, 204)),
    legfar=R5((32, 24, 36)), leg=R5((48, 38, 54)),
    body=R5((50, 40, 58)), fur=R5((66, 54, 74)),
    bonew=R5((220, 210, 176)), purple=R5((110, 40, 140)), green=R5((110, 190, 70)), leather=R5((66, 40, 36)),
    earfar=R5((36, 28, 40)), ear=R5((58, 46, 64)), earin=R5((150, 84, 112)),
    head=R5((58, 46, 66)), snout=R5((80, 64, 86)), nose=R5((24, 14, 22)), mouth=R5((90, 20, 34)),
    fang=R5((252, 248, 236)), eye=R5((255, 70, 30), lt=(0.4, 0.75)))

HIP = dict(
    far=R5((70, 64, 132)), prim=R5((92, 84, 186)), cov=R5((60, 176, 180)), marg=R5((210, 240, 236)),
    plume=R5((60, 170, 176)), plume2=R5((112, 92, 196)),
    legfar=R5((96, 78, 150)), leg=R5((138, 116, 196)), hoof=R5((44, 34, 60)),
    body=R5((136, 114, 206)), belly=R5((196, 186, 236)),
    silver=R5((206, 214, 232)), navy=R5((36, 44, 120)), leather=R5((80, 56, 76)),
    teal=R5((70, 176, 178)), antler=R5((236, 226, 196)), antlerfar=R5((170, 158, 132)),
    ring=R5((60, 56, 110)), disc=R5((226, 232, 244)), iris=R5((255, 196, 50)), pupil=R5((20, 14, 30)),
    beak=R5((206, 186, 120)))

FLYERS = [('gryphon', gryphon, GRY), ('windrider', windrider, WR), ('bat', bat, BAT), ('hippogryph', hippogryph, HIP)]

# ================================================================ previews
def game_bg(w, h):
    p = Pic(w, h)
    top, mid, bot = (44, 58, 92), (70, 74, 104), (30, 32, 44)
    for y in range(h):
        t = y / max(1, h - 1)
        c = mix(top, mid, t / 0.6) if t < 0.6 else mix(mid, bot, (t - 0.6) / 0.4)
        p.px[y * w:(y + 1) * w] = [c + (255,)] * w
    # far hills
    for x in range(w):
        hy = int(h * 0.72 + 6 * math.sin(x * 0.045) + 4 * math.sin(x * 0.11 + 1))
        for y in range(max(0, hy), h):
            p.px[y * w + x] = mix((40, 46, 52), (22, 24, 30), (y - hy) / max(1, h - hy)) + (255,)
    return p

def bar_mock(bg, x0, y0, width, pct, flyer, size, sheet_y, fill_tex, frame_tex):
    """Draw Bar.lua's bar (frame width+8 x 26, status inset 4) and the flyer frame at 'size' px."""
    fw_, fh = width + 8, 26
    sw, sh = fw_ - 8, fh - 8
    for y in range(sh):                                  # dark background behind fill
        for x in range(sw): bg.over(x0 + 4 + x, y0 + 4 + y, (0, 0, 0, 153))
    fill = resize(fill_tex, sw, sh); col = (0.25, 0.6, 1.0)
    for y in range(sh):
        for x in range(int(sw * pct)):
            c = fill.px[y * sw + x]
            bg.over(x0 + 4 + x, y0 + 4 + y, (int(c[0] * col[0]), int(c[1] * col[1]), int(c[2] * col[2]), c[3]))
    cap = 13
    left = resize(crop(frame_tex, 0, 0, 32, 64), cap, fh)
    right = resize(crop(frame_tex, 224, 0, 32, 64), cap, fh)
    mid = resize(crop(frame_tex, 32, 0, 192, 64), fw_ - 2 * cap, fh)
    blit(bg, left, x0, y0); blit(bg, mid, x0 + cap, y0); blit(bg, right, x0 + fw_ - cap, y0)
    if flyer is not None:
        ic = flyer if flyer.w == size else resize(flyer, size, size)
        ix = size / 2 + (sw - size) * pct
        blit(bg, ic, int(round(x0 + 4 + ix - size / 2)), int(round(y0 + 4 - sheet_y - size)))

def frame_of(sheet, i):
    return crop(sheet, i * CELL, 0, CELL, CELL)

def lowest_row(p, w, h):
    lo = 0
    for y in range(h):
        if any(c[3] for c in p.px[y * w:(y + 1) * w]): lo = y
    return lo

def main(previews=False):
    natives = {}; sheets = {}
    for kind, fn, pal in FLYERS:
        frames = [fn(f, pal) for f in range(FR)]
        natives[kind] = frames
        sheet = Pic(CELL * FR, CELL)
        for f, p in enumerate(frames): blit(sheet, p, f * CELL + PADC, PADC)
        sheets[kind] = sheet
        write_tga(os.path.join(OUT, 'flyer_%s.tga' % kind), sheet)
        write_png(os.path.join(OUT, 'flyer_%s.png' % kind), sheet)
        print('drew', kind)
    if not previews:
        return
    fill_tex = read_tga(os.path.join(MEDIA, 'bar_fill.tga'))
    frame_tex = read_tga(os.path.join(MEDIA, 'bar_frame.tga'))
    low = max(lowest_row(frame_of(s, 1), CELL, CELL) for s in sheets.values())
    sy128 = -(CELL - 1 - low) + 2
    print('lowest row in cell', low, '-> SHEET_Y for SHEET_SIZE 128:', sy128)
    Z = 4
    for kind, frames in natives.items():
        pad = 12; w = FR * (N * Z + pad) + pad; h = N * Z + 2 * pad
        p = game_bg(w, h)
        for f, fr in enumerate(frames): blit(p, zoom(fr, Z), pad + f * (N * Z + pad), pad)
        write_png(os.path.join(PREV, '%s_large_4x.png' % kind), p)
        one = game_bg(4 * 170, 140)
        for f in range(FR):
            sub = game_bg(170, 140)
            bar_mock(sub, 6, 104, 150, 0.5, frame_of(sheets[kind], f), 128, sy128, fill_tex, frame_tex)
            blit(one, sub, f * 170, 0)
        write_png(os.path.join(PREV, '%s_bar_1x.png' % kind), one)

if __name__ == '__main__':
    import sys
    main('previews' in sys.argv[1:])
