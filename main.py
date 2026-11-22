#!/usr/bin/env python3
"""Sunday 22 November 2026 - The World in One Day.

A one-page newspaper image summing up 22 November 2026's world news.
Pure Python standard library only: no network, no clock, no randomness.
Reads sibling scene PNGs (original illustrations made for this page) and
glyph data from fonts_data.py, composes the page, writes entry.png.
"""
import base64
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fonts_data import FONTS  # noqa: E402

W, H = 1024, 1024
PAPER = (246, 239, 220)
INK = (22, 22, 22)
RED = (179, 32, 44)
NAVY = (29, 43, 74)
GREY = (90, 84, 70)

# ---------------------------------------------------------------- PNG decode
# Minimal pure-stdlib PNG reader: 8-bit, non-interlaced, colour types
# 0 (grey), 2 (RGB), 3 (palette), 4 (grey+alpha), 6 (RGBA).


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a png: " + path
    pos, w, h, bitdepth, ctype, interlace = 8, 0, 0, 0, 0, 0
    palette, idat = None, bytearray()
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bitdepth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"PLTE":
            palette = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    assert bitdepth == 8, "need 8-bit png"
    assert interlace == 0, "interlaced png unsupported"
    nch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    stride = w * nch
    raw = zlib.decompress(bytes(idat))
    px = bytearray(w * h * 3)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                line[i] = (line[i] + _paeth(a, b, c)) & 255
        elif ft != 0:
            raise ValueError("bad filter %d" % ft)
        prev = line
        for x in range(w):
            o = (y * w + x) * 3
            s = x * nch
            if ctype == 3:
                px[o:o + 3] = palette[line[s]]
            elif ctype == 2 or ctype == 6:
                px[o:o + 3] = line[s:s + 3]
            elif ctype == 0 or ctype == 4:
                px[o] = px[o + 1] = px[o + 2] = line[s]
    return w, h, px


def write_png(path, w, h, px):
    def chunk(typ, body):
        c = struct.pack(">I", len(body)) + typ + body
        return c + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += px[y * w * 3:(y + 1) * w * 3]
    out = b"\x89PNG\r\n\x1a\n"
    out += chunk(b"IHDR", ihdr)
    out += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    out += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        self.rect(0, 0, w, h, bg)

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.px[o:o + 3] = bytes(c)

    def rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            o = (yy * self.w + x0) * 3
            self.px[o:o + len(row)] = row

    def hline(self, x0, x1, y, c):
        self.rect(x0, y, x1 - x0, 1, c)

    def vline(self, x, y0, y1, c):
        self.rect(x, y0, 1, y1 - y0, c)

    def blit(self, x, y, w, h, px):
        for yy in range(h):
            dy = y + yy
            if dy < 0 or dy >= self.h:
                continue
            src = yy * w * 3
            dst = (dy * self.w + x) * 3
            if x >= 0 and x + w <= self.w:
                self.px[dst:dst + w * 3] = px[src:src + w * 3]
            else:
                for xx in range(w):
                    dx = x + xx
                    if 0 <= dx < self.w:
                        o = (dy * self.w + dx) * 3
                        self.px[o:o + 3] = px[src + xx * 3:src + xx * 3 + 3]

    def disc(self, cx, cy, r, c):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.set(xx, yy, c)


# ---------------------------------------------------------------- text
def _unpack(b64, w, h):
    raw = base64.b64decode(b64)
    stride = (w + 7) // 8
    rows = []
    for y in range(h):
        row = bytearray(w)
        base = y * stride
        for x in range(w):
            if raw[base + x // 8] & (0x80 >> (x % 8)):
                row[x] = 1
        rows.append(row)
    return rows


def text_width(font, text):
    f = FONTS[font]
    total = 0
    for ch in text:
        g = f["glyphs"].get(ord(ch))
        if g is not None:
            total += g[0]
    return total


def draw_text(cv, font, x, baseline_y, text, color):
    f = FONTS[font]
    cx = x
    for ch in text:
        g = f["glyphs"].get(ord(ch))
        if g is None:
            continue
        adv, top, w, data = g[0], g[1], g[2], g[3]
        gh = g[4] if len(g) > 4 else 0
        if data and gh:
            rows = _unpack(data, w, gh)
            y0 = baseline_y - f["ascent"] + top
            for yy in range(gh):
                row = rows[yy]
                for xx in range(w):
                    if row[xx]:
                        cv.set(cx + xx, y0 + yy, color)
        cx += adv
    return cx


def wrap(text, font, max_w, max_lines=None):
    """Greedy word wrap. Truncates with an ellipsis if max_lines exceeded."""
    words = text.split(" ")
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    truncated = False
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
        while lines and text_width(font, lines[-1] + "…") > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1] + "…"
    return lines, truncated


def draw_lines(cv, font, x, first_baseline, leading, lines, color):
    y = first_baseline
    for ln in lines:
        draw_text(cv, font, x, y, ln, color)
        y += leading
    return y

# ---------------------------------------------------------------- data
# All facts are 22 November 2026 news as reported that day; headlines and
# copy below are written for this page. Same story selection and order as
# the day's leading front pages: 3 heroes, 10 mids, 22 briefs, 6 regions.

KICKER = "THE WORLD IN ONE DAY  ·  35 STORIES  ·  6 REGIONS  ·  EVERY ONE DATED SUNDAY 22 NOVEMBER 2026"
MASTHEAD = "Sunday 22 November 2026"
SUBHEAD = "Climate deal in sight at COP31  ·  Russia\u2019s 400-drone barrage on Ukraine  ·  Iran hits US bases in Bahrain"

STATS = [
    ("~200", "NATIONS AT COP31"),
    ("03:00", "GMT OBJECTION DEADLINE"),
    ("400+", "DRONES AT UKRAINE"),
    ("110", "MISSILES THAT NIGHT"),
    ("8", "KILLED IN KYIV"),
    ("2", "US BASES IN BAHRAIN"),
]

REGIONS = [
    ("EUROPE", 9, (43, 94, 167), 240),
    ("MIDDLE EAST", 8, (179, 32, 44), 215),
    ("AMERICAS", 6, (61, 139, 79), 165),
    ("ASIA-PACIFIC", 5, (200, 147, 42), 140),
    ("AFRICA", 1, (138, 109, 59), 60),
    ("WORLD", 6, (122, 74, 158), 176),
]

# (scene, kicker, source, place, headline, body)
HEROES = [
    ("hero1-cop31", "COP31: DEAL CLOSE", "Summit president",
     "1  ANTALYA, TURKEY  ·  CLIMATE",
     "COP31 climate talks close in on a final deal",
     "A fresh package lands after a fossil-fuel fight; objections close 03:00 GMT. (Reuters, BBC)"),
    ("hero2-kyiv", "UKRAINE: BARRAGE", "Officials\u2019 count",
     "2  KYIV, UKRAINE  ·  WAR",
     "Russia fires 400 drones and 110 missiles",
     "One of the war\u2019s largest overnight attacks; eight killed in Kyiv, three bridges hit. (Al Jazeera)"),
    ("hero3-bahrain", "BAHRAIN: STRUCK", "Bahrain gov",
     "3  MANAMA, BAHRAIN  ·  IRAN WAR",
     "Iran strikes US bases in Bahrain",
     "An industrial site burns, no injuries; tankers are hit in Hormuz. (Al Jazeera, CNA)"),
]

# (num, scene, kicker, source, place, headline, body)
MIDS = [
    (4, "mid4-ship", "SHIP ABLAZE", "Finnish forces", "GULF OF FINLAND",
     "Cargo ship burns after drone strike",
     "Finland says Ukraine was likely behind it. (BBC)"),
    (5, "mid5-kryvyi", "2 DEAD, 60 HURT", "Officials\u2019 count", "KRYVYI RIH",
     "Strike hits Zelensky\u2019s home city",
     "Russian strike on the central Ukrainian city. (Al Jazeera)"),
    (6, "mid6-boat", "24 DEAD", "Emergency agency", "BAYELSA, NIGERIA",
     "Boat carrying mourners capsizes",
     "Passengers were going to a funeral. (DW, Sky News)"),
    (7, "mid7-jerusalem", "COALITION TALKS", "Party statement", "JERUSALEM",
     "Eisenkot invites Likud to talks",
     "He seeks the broadest possible government. (Straits Times)"),
    (8, "mid8-gaza", "3 KILLED", "Witnesses", "GAZA",
     "Strike hits food aid vehicle",
     "Three Palestinians die in an air attack. (Al Jazeera, Reuters)"),
    (9, "mid9-chapo", "11 DEAD", "Officials\u2019 count", "SINALOA, MEXICO",
     "\u2018El Chapo Isidro\u2019 caught",
     "FBI top-ten fugitive held after a shoot-out. (Sky News, BBC)"),
    (10, "mid10-tehran", "POWER CUTS", "Officials", "TEHRAN, IRAN",
     "Iran to ration electricity",
     "War damage hits the energy network. (Straits Times)"),
    (11, "mid11-nvidia", "SEC PROBE", "Media report", "WASHINGTON",
     "Nvidia faces US accounting probe",
     "The SEC inquiry is at an early stage. (Straits Times)"),
    (12, "mid12-bolsonaro", "BOLSONARO: ICU", "Hospital", "BRASILIA, BRAZIL",
     "Bolsonaro in intensive care",
     "Ex-president stable, breathing unaided. (Al Jazeera, Reuters)"),
    (13, "mid13-aukus", "AUKUS ROW", "Minister", "CANBERRA",
     "Marles rejects US AUKUS report",
     "He says the budget office is wrong. (ABC, Reuters)"),
]

# (lead, rest) — lead in bold red, rest in regular ink
BRIEFS = [
    ("14  US:", "FBI looks into apparent hack of its crime database (BBC)"),
    ("15  US:", "Teen gamer and mother help FBI rescue a girl (BBC)"),
    ("16  US:", "Midterm loss corners Vance as 2028 field widens (ST)"),
    ("17  Saudi Arabia:", "Air defences down a missile (Investing.com)"),
    ("18  Lebanon:", "Aoun demands Israeli withdrawal (Al Jazeera)"),
    ("19  Iran:", "President warns of a \u2018silent economic war\u2019 (Al Jazeera)"),
    ("20  Hormuz:", "Lewis Pugh swims strait as tanker is struck (BBC)"),
    ("21  Moldova:", "Reports a Russian airspace breach (Kyiv Ind.)"),
    ("22  Belgium:", "Air traffic to halt in 23 Nov national strike (ST)"),
    ("23  Germany:", "IG Metall widens auto, shipyard strikes (Reuters)"),
    ("24  Portugal:", "Lisbon marches over living costs (Reuters)"),
    ("25  Denmark:", "Expels Russian attach\u00e9 in rapper plot (Guardian)"),
    ("26  Bangladesh:", "30 Awami League homes set on fire (TOI)"),
    ("27  Australia:", "Fred Nile, ex-NSW MP, dies aged 92 (ABC)"),
    ("28  Australia:", "Bystanders pull driver from burning car (ABC)"),
    ("29  Melbourne:", "70 years since the 1956 Olympics opened (ABC)"),
    ("30  Trade:", "EU and Indonesia sign deal after 10 years (DW)"),
    ("31  Rugby:", "England beat New Zealand 33-12 (Reuters)"),
    ("32  Rugby:", "France beat Argentina to reach the final (Reuters)"),
    ("33  Football:", "Arsenal 2-2 Newcastle; Leeds 4-1 at Chelsea (BBC)"),
    ("34  Tennis:", "Zverev v Alcaraz in today\u2019s ATP Finals final (TOI)"),
    ("35  Football:", "Liverpool host Man United today (Al Jazeera)"),
]

DATE_CHECK = ("DATE CHECK",
              "Wires read up to 00:50 UTC, Sunday 22 November 2026; every story here was reported "
              "or still developing on 22 November in at least one time zone. Left out as other days\u2019 "
              "news: the Peru earthquake (20 Nov local), Russian missiles landing in Poland (19 Nov), "
              "the Kerch Bridge strikes (earlier this week) and the Shenzhen summit (19 Nov).")

SOURCES = ("Sources: Reuters, BBC, Al Jazeera, DW, Straits Times, Sky News, CNA, ABC, "
           "Times of India, Guardian, Kyiv Independent. Every story names its outlet. "
           "Pictures: original illustrations made for this page.")

# Coarse continent outlines (lon, lat), drawn from general geography.
CONTINENTS = [
    [(-168, 66), (-140, 70), (-120, 72), (-95, 80), (-80, 73), (-75, 62), (-65, 60),
     (-60, 47), (-70, 42), (-75, 35), (-80, 32), (-90, 30), (-97, 26), (-105, 22),
     (-110, 24), (-115, 30), (-125, 40), (-125, 49), (-140, 60), (-155, 58), (-165, 60)],
    [(-55, 60), (-40, 64), (-30, 68), (-22, 70), (-30, 76), (-55, 76), (-60, 70)],
    [(-80, 10), (-75, 5), (-80, -3), (-78, -10), (-72, -18), (-70, -30), (-65, -45),
     (-68, -52), (-65, -55), (-55, -35), (-48, -28), (-40, -22), (-35, -8), (-45, -3),
     (-55, 5), (-62, 9), (-70, 11)],
    [(-10, 36), (-9, 43), (-2, 48), (-5, 50), (0, 51), (5, 53), (8, 57), (10, 59),
     (18, 56), (20, 54), (24, 58), (28, 60), (30, 62), (25, 65), (20, 70), (15, 70),
     (10, 64), (5, 60), (-2, 57), (-8, 52), (-10, 44)],
    [(-17, 15), (-15, 27), (-10, 31), (-5, 35), (10, 37), (20, 32), (30, 31),
     (35, 28), (32, 20), (38, 18), (43, 12), (48, 11), (51, 10), (44, 2), (40, -5),
     (38, -15), (35, -25), (32, -29), (28, -33), (20, -35), (15, -30), (12, -18),
     (9, -2), (8, 4), (-8, 5), (-13, 8), (-17, 12)],
    [(30, 62), (40, 68), (55, 70), (70, 72), (90, 75), (110, 76), (130, 72), (150, 70),
     (170, 66), (178, 65), (162, 60), (158, 52), (142, 50), (140, 40), (135, 35),
     (128, 33), (122, 30), (120, 22), (110, 20), (105, 10), (100, 8), (98, 15),
     (92, 20), (88, 22), (80, 15), (75, 10), (72, 20), (65, 25), (60, 25), (55, 26),
     (52, 28), (48, 30), (44, 29), (40, 32), (35, 36), (30, 36), (28, 40), (25, 42),
     (28, 45), (30, 50)],
    [(95, 5), (100, 0), (105, -2), (110, -5), (115, -8), (120, -10), (125, -8),
     (130, -5), (135, -2), (140, 0), (135, 5), (125, 8), (115, 10), (105, 8)],
    [(114, -22), (114, -30), (115, -35), (120, -34), (125, -32), (130, -32),
     (135, -35), (140, -38), (145, -38), (150, -37), (153, -32), (153, -27),
     (150, -22), (146, -19), (142, -15), (142, -11), (137, -12), (135, -15),
     (132, -12), (130, -13), (126, -14), (122, -17), (118, -20)],
    [(-5, 50), (-3, 53), (-5, 56), (-3, 58), (-1, 57), (0, 53), (1, 51)],
    [(130, 31), (132, 33), (135, 34), (138, 35), (140, 37), (141, 40), (142, 43),
     (144, 44), (142, 42), (140, 39), (137, 37), (134, 35), (131, 33)],
    [(167, -45), (170, -42), (173, -40), (175, -38), (177, -38), (174, -41),
     (171, -44), (168, -46)],
]

# (story number, lon, lat, dx, dy) — dx/dy nudge pins apart in the cluster.
PINS = [
    (1, 30.7, 36.9, 0, -2),
    (2, 30.5, 50.4, -3, -3),
    (3, 50.6, 26.2, 8, -2),
    (4, 24.0, 59.5, -6, -4),
    (5, 33.4, 47.9, 8, 4),
    (6, 6.3, 4.9, 0, 3),
    (7, 35.2, 31.8, -6, 3),
    (8, 34.5, 31.5, 6, 6),
    (9, -107.4, 24.8, 0, 0),
    (10, 51.4, 35.7, 6, -4),
    (11, -77.0, 38.9, -4, -3),
    (12, -47.9, -15.8, 0, 0),
    (13, 149.1, -35.3, 0, 0),
]

# ---------------------------------------------------------------- layout
WARN = []


def chip(cv, x, y, text, font, bg, fg):
    tw = text_width(font, text)
    h = 15 if font in ("sans9", "sans10") else 17
    cv.rect(x, y, tw + 10, h, bg)
    draw_text(cv, font, x + 5, y + h - 4, text, fg)
    return tw + 10


def point_in_poly(px, py, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def draw_map(cv, x0, y0, mw, mh):
    lon0, lon1, lat0, lat1 = -170.0, 190.0, 75.0, -55.0

    def proj(lon, lat):
        return (x0 + (lon - lon0) / (lon1 - lon0) * mw,
                y0 + (lat0 - lat) / (lat0 - lat1) * mh)

    polys = [[proj(lon, lat) for lon, lat in poly] for poly in CONTINENTS]
    dot = (168, 140, 95)
    step = 6
    for gy in range(y0, y0 + mh, step):
        for gx in range(x0, x0 + mw, step):
            cx, cy = gx + 2, gy + 2
            hit = False
            for poly in polys:
                if point_in_poly(cx, cy, poly):
                    hit = True
                    break
            if hit:
                cv.rect(gx + 1, gy + 1, 3, 3, dot)
    for num, lon, lat, dx, dy in PINS:
        px, py = proj(lon, lat)
        cx, cy = int(px) + dx, int(py) + dy
        cv.disc(cx, cy, 5, RED)
        label = str(num)
        tw = text_width("sans9", label)
        draw_text(cv, "sans9", cx - tw // 2, cy + 3, label, (255, 255, 255))


def scene(cv, name, x, y):
    w, h, px = read_png(os.path.join(HERE, "scenes", name + ".png"))
    cv.blit(x, y, w, h, px)


def build():
    cv = Canvas(W, H, PAPER)
    # kicker bar
    cv.rect(0, 0, W, 20, NAVY)
    tw = text_width("sans10", KICKER)
    draw_text(cv, "sans10", (W - tw) // 2, 14, KICKER, (255, 255, 255))
    # masthead + subhead
    draw_text(cv, "masthead", 14, 82, MASTHEAD, INK)
    draw_text(cv, "subhead", 14, 110, SUBHEAD, RED)
    cv.hline(14, 1010, 118, INK)
    # stat strip
    for i, (num, label) in enumerate(STATS):
        cx = 14 + i * 166
        draw_text(cv, "statnum", cx, 148, num, RED)
        draw_text(cv, "sans9", cx, 163, label, INK)
        if i:
            cv.vline(cx - 8, 124, 162, (200, 190, 165))
    cv.hline(14, 1010, 168, INK)
    # region bar
    rx = 14
    for name, count, color, wseg in REGIONS:
        cv.rect(rx, 172, wseg, 16, color)
        label = "%s %d" % (name, count)
        tw = text_width("sans10", label)
        draw_text(cv, "sans10", rx + (wseg - tw) // 2, 184, label, (255, 255, 255))
        rx += wseg
    # heroes
    hx = [14, 360, 706]
    for (name, kicker, source, place, head, body), x in zip(HEROES, hx):
        scene(cv, name, x, 192)
        chip(cv, x, 192, kicker, "sans9", RED, (255, 255, 255))
        sw = text_width("sans9", source)
        cv.rect(x, 341 - 15, sw + 10, 15, (20, 20, 20))
        draw_text(cv, "sans9", x + 5, 341 - 4, source, (255, 255, 255))
        draw_text(cv, "sans11", x, 357, place, RED)
        lines, tr = wrap(head, "hero_head", 304, 2)
        if tr:
            WARN.append("hero head truncated: " + head)
        draw_lines(cv, "hero_head", x, 381, 23, lines, INK)
        lines, tr = wrap(body, "hero_body", 304, 2)
        if tr:
            WARN.append("hero body truncated: " + body)
        draw_lines(cv, "hero_body", x, 419, 15, lines, INK)
    # mids, two rows of five
    mx = [14, 216, 419, 621, 824]
    for row in range(2):
        yimg = 446 + row * 184
        for j in range(5):
            num, name, kicker, source, place, head, body = MIDS[row * 5 + j]
            x = mx[j]
            scene(cv, name, x, yimg)
            chip(cv, x, yimg, kicker, "sans9", RED, (255, 255, 255))
            cv.disc(x + 186 - 11, yimg + 11, 8, RED)
            label = str(num)
            tw = text_width("sans9", label)
            draw_text(cv, "sans9", x + 186 - 11 - tw // 2, yimg + 14, label, (255, 255, 255))
            sw = text_width("sans9", source)
            cv.rect(x, yimg + 96 - 14, sw + 10, 14, (20, 20, 20))
            draw_text(cv, "sans9", x + 5, yimg + 96 - 3, source, (255, 255, 255))
            draw_text(cv, "sans10", x, yimg + 111, place, RED)
            lines, tr = wrap(head, "mid_head", 186, 2)
            if tr:
                WARN.append("mid head truncated: " + head)
            draw_lines(cv, "mid_head", x, yimg + 129, 17, lines, INK)
            lines, tr = wrap(body, "mid_body", 186, 2)
            if tr:
                WARN.append("mid body truncated: " + body)
            draw_lines(cv, "mid_body", x, yimg + 162, 13, lines, INK)
    # bottom headers
    draw_text(cv, "sans11", 14, 824, "WHERE IT HAPPENED", INK)
    draw_text(cv, "bold11", 330, 824, "ALSO ON SUNDAY 22 NOVEMBER \u2014 22 MORE STORIES", RED)
    draw_text(cv, "sans9", 14, 836, "pins match story numbers", GREY)
    # map + briefs
    draw_map(cv, 14, 840, 306, 126)
    for col in range(2):
        bx = 330 + col * 342
        for i in range(11):
            lead, rest = BRIEFS[col * 11 + i]
            y = 852 + i * 11
            lw = text_width("bold11", lead)
            lines, tr = wrap(rest, "brief", 338 - lw - 3, 1)
            if tr:
                WARN.append("brief truncated: " + lead + " " + rest)
            draw_text(cv, "bold11", bx, y, lead, RED)
            draw_text(cv, "brief", bx + lw + 3, y, lines[0] if lines else "", INK)
    # date check
    cv.rect(14, 970, 996, 2, RED)
    cv.rect(14, 970, 2, 34, RED)
    cv.rect(14, 1002, 996, 2, RED)
    cv.rect(1008, 970, 2, 34, RED)
    title, text = DATE_CHECK
    tw = text_width("bold11", title)
    draw_text(cv, "bold11", 22, 986, title, RED)
    lines, tr = wrap(text, "brief", 996 - 22 - tw - 12, 2)
    if tr:
        WARN.append("date check truncated")
    if lines:
        draw_text(cv, "brief", 22 + tw + 8, 986, lines[0], INK)
    if len(lines) > 1:
        draw_text(cv, "brief", 22, 997, lines[1], INK)
    # sources + footer
    lines, tr = wrap(SOURCES, "sans9", 996, 1)
    if tr:
        WARN.append("sources truncated")
    draw_text(cv, "sans9", 14, 1013, lines[0] if lines else "", GREY)
    draw_text(cv, "sans9", 14, 1021, "THE WORLD IN ONE DAY", INK)
    foot = "SUNDAY 22 NOVEMBER 2026  ·  ONE PAGE"
    tw = text_width("sans9", foot)
    draw_text(cv, "sans9", 1010 - tw, 1021, foot, INK)
    return cv


def main():
    out = "/output/entry.png" if os.path.isdir("/output") else "entry.png"
    cv = build()
    write_png(out, W, H, cv.px)
    for w in WARN:
        print("WARN:", w)
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
