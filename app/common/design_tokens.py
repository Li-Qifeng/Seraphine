"""
Design tokens for consistent UI spacing, radius, and animation timing.

Apple Design principle: every spacing, timing, and alignment value
is a deliberate choice you can defend.
"""

# ── Spacing scale (4pt base) ──────────────────────────────
SPACING = {
    'xxs':  2,
    'xs':   4,
    'sm':   8,
    'md':   12,
    'lg':   16,
    'xl':   24,
    'xxl':  32,
    'section': 48,
}

# ── Border radius ─────────────────────────────────────────
RADIUS = {
    'sm':   4,
    'md':   6,
    'lg':   8,
    'xl':   12,
    'pill': 20,
}

# ── Animation durations (ms) ──────────────────────────────
# Apple: micro-interactions 150-300ms, complex < 400ms
ANIM = {
    'instant':    0,
    'press':      100,
    'fast':       160,
    'normal':     200,
    'slow':       300,
    'complex':    400,
}

# ── Font sizes (pt) ───────────────────────────────────────
FONT = {
    'caption':    11,
    'body':       13,
    'body_large': 14,
    'subtitle':   16,
    'title':      20,
    'heading':    24,
    'display':    32,
}

# ── Opacity levels ────────────────────────────────────────
OPACITY = {
    'disabled':   0.38,
    'hint':       0.5,
    'secondary':  0.7,
    'primary':    1.0,
}
