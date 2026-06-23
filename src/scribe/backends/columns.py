from __future__ import annotations


def segment_columns(
    words: list[dict], page_width: float, page_height: float
) -> list[list[dict]]:
    """Detect a 1-2 column layout via a vertical-gutter scan over word x-extents.
    Returns columns left-to-right; each a list of the original word dicts.
    A single column is returned as a list of length 1."""
    if len(words) < 6 or page_width <= 0:
        return [words]
    bins = 100
    bw = page_width / bins
    occ = [0] * bins
    for w in words:
        lo = max(0, int(w["x0"] / bw))
        hi = min(bins - 1, int(w["x1"] / bw))
        for b in range(lo, hi + 1):
            occ[b] += 1

    # Find the lowest-occupancy bin in the central band — a candidate gutter.
    lo_b, hi_b = int(bins * 0.35), int(bins * 0.65)
    valley_bin = min(range(lo_b, hi_b), key=lambda b: occ[b])
    valley = occ[valley_bin]

    # Compare the valley to the column peaks on each side. A real two-column
    # gutter sits well below both peaks even when a figure/equation occasionally
    # spans it (so we don't require a perfectly empty gutter).
    left_peak = max(occ[int(bins * 0.10) : valley_bin], default=0)
    right_peak = max(occ[valley_bin : int(bins * 0.90)], default=0)
    if min(left_peak, right_peak) == 0 or valley >= 0.45 * min(left_peak, right_peak):
        return [words]

    split_x = (valley_bin + 0.5) * bw
    left = [w for w in words if (w["x0"] + w["x1"]) / 2 < split_x]
    right = [w for w in words if (w["x0"] + w["x1"]) / 2 >= split_x]
    # Require both sides to be substantially populated (guards against splitting a
    # single narrow column whose centre happens to be empty).
    if len(left) < 0.15 * len(words) or len(right) < 0.15 * len(words):
        return [words]
    return [left, right]
