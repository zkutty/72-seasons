import math

# ── Landing wheel (480×480) ────────────────────────────────────────────────────
WHEEL_SIZE = 480
CTR        = WHEEL_SIZE / 2        # 240

# Kō ring (inner): 72 arcs
R_KO_OUT = 172
R_KO_IN  = 130
PAD      = 0.006

# Sekki ring (outer): 24 arcs
R_SEKKI_OUT = 208
R_SEKKI_IN  = 180
PAD_SEKKI   = 0.008

# Label radii
R_SEKKI_LABEL    = 222      # kanji just outside the sekki ring
R_CARDINAL_LABEL = 236      # SPR / SUM / AUT / WIN

# Back-compat aliases (older templates referenced these)
R_OUT = R_KO_OUT
R_IN  = R_KO_IN


def _wedge(r_out: float, r_in: float, a0: float, a1: float, cx: float, cy: float) -> str:
    p1 = (cx + r_out * math.cos(a0), cy + r_out * math.sin(a0))
    p2 = (cx + r_out * math.cos(a1), cy + r_out * math.sin(a1))
    p3 = (cx + r_in  * math.cos(a1), cy + r_in  * math.sin(a1))
    p4 = (cx + r_in  * math.cos(a0), cy + r_in  * math.sin(a0))
    return (
        f"M {p1[0]:.2f} {p1[1]:.2f} "
        f"A {r_out} {r_out} 0 0 1 {p2[0]:.2f} {p2[1]:.2f} "
        f"L {p3[0]:.2f} {p3[1]:.2f} "
        f"A {r_in} {r_in} 0 0 0 {p4[0]:.2f} {p4[1]:.2f} Z"
    )


def arc_path(i: int) -> str:
    """Path for the i-th kō arc (0..71) on the main wheel."""
    a0 = (i / 72) * 2 * math.pi - math.pi / 2
    a1 = ((i + 1) / 72) * 2 * math.pi - math.pi / 2
    return _wedge(R_KO_OUT, R_KO_IN, a0 + PAD, a1 - PAD, CTR, CTR)


def sekki_arc_path(i: int) -> str:
    """Path for the i-th sekki arc (0..23) on the main wheel."""
    a0 = (i / 24) * 2 * math.pi - math.pi / 2
    a1 = ((i + 1) / 24) * 2 * math.pi - math.pi / 2
    return _wedge(R_SEKKI_OUT, R_SEKKI_IN, a0 + PAD_SEKKI, a1 - PAD_SEKKI, CTR, CTR)


def sekki_ring(seasons: list) -> list:
    """
    Return 24 sekki entries with pre-computed geometry for the main wheel:
      {index, sekki, sekki_jp, sekki_en, major_season, arc_d, label_x, label_y}
    `seasons` is the 72-kō list; sekki metadata is read from the first kō of each.
    """
    result = []
    seen = []
    for s in seasons:
        if s['sekki'] not in seen:
            seen.append(s['sekki'])
    # Rebuild in natural (seasons.json) order — `seen` preserves insertion order.
    for i, name in enumerate(seen):
        first = next(s for s in seasons if s['sekki'] == name)
        mid_angle = ((i + 0.5) / 24) * 2 * math.pi - math.pi / 2
        result.append({
            'index':        i,
            'sekki':        first['sekki'],
            'sekki_jp':     first['sekki_jp'],
            'sekki_en':     first.get('sekki_en', ''),
            'major_season': first['major_season'],
            'arc_d':        sekki_arc_path(i),
            'label_x':      round(CTR + R_SEKKI_LABEL * math.cos(mid_angle), 1),
            'label_y':      round(CTR + R_SEKKI_LABEL * math.sin(mid_angle), 1),
        })
    return result


# ── Archive-page ring (140×140) ────────────────────────────────────────────────
RING        = 140
RC          = RING / 2         # 70

R_KO_OUT_SM    = 50
R_KO_IN_SM     = 40
R_SEKKI_OUT_SM = 58
R_SEKKI_IN_SM  = 53
PAD_SM         = 0.004
PAD_SEKKI_SM   = 0.006

# Back-compat
R_OUT_SM = R_KO_OUT_SM
R_IN_SM  = R_KO_IN_SM


def ring_path(i: int) -> str:
    """Path for the i-th kō arc on the small archive-page ring."""
    a0 = (i / 72) * 2 * math.pi - math.pi / 2
    a1 = ((i + 1) / 72) * 2 * math.pi - math.pi / 2
    return _wedge(R_KO_OUT_SM, R_KO_IN_SM, a0 + PAD_SM, a1 - PAD_SM, RC, RC)


def sekki_ring_path_sm(i: int) -> str:
    """Path for the i-th sekki arc on the small archive-page ring."""
    a0 = (i / 24) * 2 * math.pi - math.pi / 2
    a1 = ((i + 1) / 24) * 2 * math.pi - math.pi / 2
    return _wedge(R_SEKKI_OUT_SM, R_SEKKI_IN_SM, a0 + PAD_SEKKI_SM, a1 - PAD_SEKKI_SM, RC, RC)


def sekki_ring_small(seasons: list) -> list:
    """24 sekki entries with geometry for the small archive-page ring (no labels)."""
    result = []
    seen = []
    for s in seasons:
        if s['sekki'] not in seen:
            seen.append(s['sekki'])
    for i, name in enumerate(seen):
        first = next(s for s in seasons if s['sekki'] == name)
        result.append({
            'index':        i,
            'sekki':        first['sekki'],
            'major_season': first['major_season'],
            'arc_d':        sekki_ring_path_sm(i),
        })
    return result


# ── Cardinal labels (pre-computed x/y for the main wheel) ─────────────────────
def cardinal_labels() -> list:
    """Return the four cardinal season labels with pre-computed SVG coordinates."""
    defs = [
        {'idx': 0,  'label': 'SPR', 'sub': 'Feb'},
        {'idx': 18, 'label': 'SUM', 'sub': 'May'},
        {'idx': 36, 'label': 'AUT', 'sub': 'Aug'},
        {'idx': 54, 'label': 'WIN', 'sub': 'Nov'},
    ]
    result = []
    for c in defs:
        angle = ((c['idx'] + 9) / 72) * 2 * math.pi - math.pi / 2
        result.append({
            **c,
            'x': round(CTR + R_CARDINAL_LABEL * math.cos(angle), 1),
            'y': round(CTR + R_CARDINAL_LABEL * math.sin(angle), 1),
        })
    return result


# ── Season augmentation ────────────────────────────────────────────────────────
def augment_seasons(seasons: list) -> list:
    """Add arc_d, ring_d, and url to every season dict."""
    return [
        {
            **s,
            'arc_d':  arc_path(i),
            'ring_d': ring_path(i),
            'url':    f"/archive/{s['id']:02d}-{s['slug']}.html",
        }
        for i, s in enumerate(seasons)
    ]
