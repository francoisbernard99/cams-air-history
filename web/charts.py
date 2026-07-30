"""Inline SVG charts, generated without a single dependency.

No JavaScript, no charting library, no CDN. Every chart is SVG markup written
into the page, so it renders before any script could run and keeps working
however the page is opened -- including with scripts disabled.

Colours come from CSS custom properties, so light and dark themes swap in one
place (see style.css) rather than being baked into every mark.

The hover layer is native: each data point carries an SVG <title>, which the
browser turns into a tooltip. Values are never gated behind it -- every chart
ships a table view beside it.
"""

from html import escape

# Mark specs, fixed across every chart on the page.
LINE_WIDTH = 2
MARKER_RADIUS = 4
SURFACE_RING = 2
HIT_RADIUS = 7  # bigger than the mark, so hovering does not need precision


def _nice_step(span: float) -> float:
    """A round step (1, 2, 5 x 10^n) covering `span` in about three intervals."""
    if span <= 0:
        return 1.0
    raw = span / 3
    magnitude = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 10 ** -3
    while magnitude * 10 <= raw:
        magnitude *= 10
    for multiple in (1, 2, 5, 10):
        if magnitude * multiple >= raw:
            return magnitude * multiple
    return magnitude * 10


def nice_ticks(low: float, high: float) -> list[float]:
    """Round axis values spanning [low, high], always including a baseline."""
    low = min(0.0, low)
    step = _nice_step(high - low)
    ticks, value = [], low
    while value <= high + step / 2:
        ticks.append(round(value, 6))
        value += step
    return ticks


def format_number(value: float) -> str:
    if value >= 100:
        return f"{value:,.0f}".replace(",", " ")
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def line_chart(
    points: list[tuple[str, float]],
    *,
    band: list[tuple[str, float, float]] | None = None,
    unit: str = "",
    width: int = 280,
    height: int = 150,
    x_tick_every: int = 0,
    aria_label: str = "",
) -> str:
    """One series over time, optionally over a min-max band.

    `points` is [(label, value)]. `band` is [(label, low, high)] and renders as a
    10% wash under the line -- the spread across sites, so a single line never
    passes itself off as a uniform value.
    """
    if not points:
        return '<p class="empty">No data for this period.</p>'

    left, right, top, bottom = 40, 12, 12, 26
    plot_width = width - left - right
    plot_height = height - top - bottom

    values = [value for _, value in points]
    if band:
        values += [low for _, low, _ in band] + [high for _, _, high in band]
    ticks = nice_ticks(min(values), max(values))
    y_min, y_max = ticks[0], ticks[-1]
    y_span = (y_max - y_min) or 1

    def x_of(index: int) -> float:
        if len(points) == 1:
            return left + plot_width / 2
        return left + plot_width * index / (len(points) - 1)

    def y_of(value: float) -> float:
        return top + plot_height * (1 - (value - y_min) / y_span)

    # No preserveAspectRatio override: stretching the viewBox to the container
    # would squash the axis text and turn the round end marker into an ellipse.
    # The aspect ratio is held and CSS lets the height follow the width.
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(aria_label)}">'
    ]

    # Gridlines and y labels: hairline, solid, recessive.
    for tick in ticks:
        y = y_of(tick)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="tick" x="{left - 6}" y="{y + 3.5:.1f}" text-anchor="end">'
            f'{format_number(tick)}</text>'
        )

    if band:
        upper = " ".join(f"{x_of(i):.1f},{y_of(high):.1f}" for i, (_, _, high) in enumerate(band))
        lower = " ".join(
            f"{x_of(i):.1f},{y_of(low):.1f}" for i, (_, low, _) in reversed(list(enumerate(band)))
        )
        parts.append(f'<polygon class="band" points="{upper} {lower}"/>')

    path = " ".join(
        f"{'M' if i == 0 else 'L'}{x_of(i):.1f},{y_of(value):.1f}"
        for i, (_, value) in enumerate(points)
    )
    parts.append(f'<path class="line" d="{path}"/>')

    # X labels, thinned so they never collide. The first and last are anchored
    # inwards: centred on a point sitting at the edge of the box, half the label
    # would fall outside the viewBox and be clipped.
    if x_tick_every:
        for index, (label, _) in enumerate(points):
            if index % x_tick_every and index != len(points) - 1:
                continue
            if index == 0:
                anchor = "start"
            elif index == len(points) - 1:
                anchor = "end"
            else:
                anchor = "middle"
            parts.append(
                f'<text class="tick" x="{x_of(index):.1f}" y="{height - 8}" '
                f'text-anchor="{anchor}">{escape(label)}</text>'
            )

    # End marker, direct-labelled: the endpoint is the value worth naming.
    last_index = len(points) - 1
    last_label, last_value = points[last_index]
    parts.append(
        f'<circle class="marker-ring" cx="{x_of(last_index):.1f}" '
        f'cy="{y_of(last_value):.1f}" r="{MARKER_RADIUS + SURFACE_RING}"/>'
        f'<circle class="marker" cx="{x_of(last_index):.1f}" '
        f'cy="{y_of(last_value):.1f}" r="{MARKER_RADIUS}"/>'
    )

    # Native hover layer: an invisible, generous hit target per point.
    for index, (label, value) in enumerate(points):
        tooltip = f"{label} — {format_number(value)} {unit}".strip()
        parts.append(
            f'<circle class="hit" cx="{x_of(index):.1f}" cy="{y_of(value):.1f}" '
            f'r="{HIT_RADIUS}"><title>{escape(tooltip)}</title></circle>'
        )

    parts.append("</svg>")
    return "".join(parts)


def coverage_strip(days: list[tuple[str, int]], *, width: int = 720) -> str:
    """One mark per archived day: complete, or short of 24 hours.

    Colour carries state, so it is paired with a labelled legend and a count --
    never left to speak on its own.
    """
    if not days:
        return '<p class="empty">Archive still empty.</p>'

    # Here stretching IS correct: the strip holds nothing but rectangles, so it
    # can fill any width without distorting text or a curve.
    height, gap = 34, 1
    span = max((width - gap) / len(days), 0.7)
    parts = [
        f'<svg class="strip" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="none" aria-label="One mark per archived day, '
        f'incomplete days highlighted">'
    ]
    for index, (day, hours) in enumerate(days):
        complete = hours >= 24
        label = f"{day} — {hours}/24 h" + ("" if complete else " (incomplete)")
        parts.append(
            f'<rect class="{"day-ok" if complete else "day-short"}" '
            f'x="{index * span:.2f}" y="0" width="{max(span - gap, 0.6):.2f}" '
            f'height="{height}"><title>{escape(label)}</title></rect>'
        )
    parts.append("</svg>")
    return "".join(parts)


def table(headers: list[str], rows: list[list[str]], *, caption: str = "") -> str:
    """The table view every chart ships with, so no value is hover-only."""
    head = "".join(f"<th scope=\"col\">{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    legend = f"<caption>{escape(caption)}</caption>" if caption else ""
    return f'<table>{legend}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
