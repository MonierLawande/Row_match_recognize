"""
Shared value-label helper for the thesis figures.

Static print figures have no tooltip, so a reader can only recover a value
from the axis, the appendix table, or a printed label.  These helpers print
the label and then push overlapping labels apart, so adding values does not
turn a dense chart into unreadable text.

Two ideas do the work:

* a white halo behind the glyphs keeps a label legible where it crosses a
  line or a marker, without drawing a box around it;
* after the figure is laid out, label rectangles are compared in display
  space and nudged along y until they no longer intersect.
"""

import matplotlib.patheffects as pe

__all__ = ["label_points", "declutter", "SERIES_DY", "series_dy"]

_HALO = [pe.withStroke(linewidth=2.2, foreground="white")]

# Thesis-wide label placement, in points, keyed by system.
#
# Oracle and Trino run close together on most linear axes, so their labels
# are pushed away from each other: Oracle above its own line, Trino below
# its own line.  That leaves the narrow band between the two curves empty,
# and no label can be read as belonging to the neighbouring series.  The
# engine's curve is far from both, so its labels stay above.
SERIES_DY = {"engine": 6, "oracle": 8, "trino": -9}


def series_dy(name, default=6):
    """Look up the label offset for a system by a loose name match."""
    key = (name or "").lower()
    if "trino" in key:
        return SERIES_DY["trino"]
    if "oracle" in key:
        return SERIES_DY["oracle"]
    if "engine" in key or "pandas" in key or "proposed" in key:
        return SERIES_DY["engine"]
    return default


def label_points(ax, xs, ys, color, fmt="{:.2f}", fontsize=7.0,
                 dy=6, halo=True, skip=None):
    """
    Annotate each (x, y) pair and return the annotation objects.

    ``fmt`` is either a format string or a callable taking the value.
    ``dy`` is the initial vertical offset in points; negative places the
    label below the marker.  ``skip`` is an optional predicate taking the
    point index and returning True for points that should not be labelled.
    """
    anns = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        if skip is not None and skip(i):
            continue
        if y is None or y != y:          # None or NaN
            continue
        text = fmt(y) if callable(fmt) else fmt.format(y)
        ann = ax.annotate(
            text, (x, y), textcoords="offset points",
            xytext=(0, dy), ha="center",
            va="bottom" if dy >= 0 else "top",
            fontsize=fontsize, color=color, zorder=6,
            annotation_clip=False,
        )
        if halo:
            ann.set_path_effects(_HALO)
        anns.append(ann)
    return anns


def _overlaps(a, b, pad):
    return not (a.xmin - pad > b.xmax or b.xmin - pad > a.xmax
                or a.ymin - pad > b.ymax or b.ymin - pad > a.ymax)


def declutter(fig, anns, step=3.0, rounds=60, pad=1.0, obstacles=None):
    """
    Push overlapping annotations apart along y.

    Runs after the artists exist, measures each label in display space, and
    repeatedly moves the upper label of an intersecting pair further up (or
    the lower one further down) until the pass is clean or ``rounds`` is hit.

    ``obstacles`` is an optional list of fixed artists -- typically
    ``ax.get_xticklabels()`` -- that labels must also avoid.  Without it a
    label pushed downwards can land on the axis furniture, which reads as a
    collision even though no two labels overlap.

    Returns True when it converged.
    """
    if not anns:
        return True
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fixed = list(obstacles or [])

    for _ in range(rounds):
        bbs = [a.get_window_extent(renderer=renderer) for a in anns]
        fixed_bbs = [o.get_window_extent(renderer=renderer) for o in fixed]
        moved = False
        # Label against label.  Only the upper label of a colliding pair is
        # moved, and always upwards, so labels stack above the marks instead
        # of straddling the line -- where two series run close together, a
        # label pushed downwards ends up on the wrong side of its own curve.
        for i in range(len(anns)):
            for j in range(i + 1, len(anns)):
                if not _overlaps(bbs[i], bbs[j], pad):
                    continue
                hi = i if bbs[i].ymin >= bbs[j].ymin else j
                dx, dy = anns[hi].xyann
                anns[hi].xyann = (dx, dy + step)
                anns[hi].set_va("bottom" if dy + step >= 0 else "top")
                moved = True
        # label against fixed furniture: always retreat upwards
        for i, bb in enumerate(bbs):
            if any(_overlaps(bb, f, pad) for f in fixed_bbs):
                dx, dy = anns[i].xyann
                anns[i].xyann = (dx, dy + abs(step))
                anns[i].set_va("bottom" if dy + abs(step) >= 0 else "top")
                moved = True
        # A below-the-line label on a series that hugs the axis floor would
        # sit under the axis rule, among the tick labels.  Flip it above.
        for i, bb in enumerate(bbs):
            ax = anns[i].axes
            if ax is None:
                continue
            ax_bb = ax.get_window_extent(renderer=renderer)
            dx, dy = anns[i].xyann
            if bb.ymin < ax_bb.ymin + pad and dy < 0:
                anns[i].xyann = (dx, abs(dy))
                anns[i].set_va("bottom")
                moved = True
        if not moved:
            return True
        fig.canvas.draw()
    return False
