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
    # A gutter is the widest run of empty bins in the central region.
    central = list(range(int(bins * 0.30), int(bins * 0.70)))
    best: tuple[int, int] | None = None
    run_start: int | None = None
    prev: int | None = None
    for b in central:
        if occ[b] == 0:
            if run_start is None:
                run_start = b
        elif run_start is not None:
            run = (run_start, b - 1)
            if best is None or (run[1] - run[0]) > (best[1] - best[0]):
                best = run
            run_start = None
        prev = b
    if run_start is not None and prev is not None:  # run extends to end of central
        run = (run_start, prev)
        if best is None or (run[1] - run[0]) > (best[1] - best[0]):
            best = run
    if best is None or (best[1] - best[0]) < 3:  # gutter < ~3% page width → single col
        return [words]
    split_x = (best[0] + best[1] + 1) / 2 * bw
    left = [w for w in words if (w["x0"] + w["x1"]) / 2 < split_x]
    right = [w for w in words if (w["x0"] + w["x1"]) / 2 >= split_x]
    if not left or not right:
        return [words]
    return [left, right]
