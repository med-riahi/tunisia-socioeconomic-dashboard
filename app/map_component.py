"""Self-contained HTML/SVG choropleth for st.components.v1.html.

Renders inside a sandboxed iframe (no access to the parent page's CSS or
JS), so this builds a complete tiny HTML document: inline styles, the SVG
paths, and a hover-tooltip script. The iframe reports its own rendered
height back to Streamlit via postMessage so it doesn't get clipped or
leave dead space — a fixed-height iframe was exactly the kind of sizing
bug that made the folium/Leaflet version unreliable.
"""

from __future__ import annotations

from tn_dashboard.geo.svg import VIEWBOX_H, VIEWBOX_W

RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]


def color_for_value(value: float, lo: float, hi: float) -> str:
    if hi <= lo:
        return RAMP[len(RAMP) // 2]
    t = (value - lo) / (hi - lo)
    idx = round(t * (len(RAMP) - 1))
    return RAMP[max(0, min(idx, len(RAMP) - 1))]


def render_choropleth_html(
    paths: dict[str, str],
    values: dict[str, float],
    unit: str,
    stroke: str = "#ffffff",
    unmatched_fill: str = "#e8e8e2",
) -> str:
    """Build the iframe document. `values` may be a subset of `paths`'
    keys — regions without a value render in `unmatched_fill`."""
    numeric = [v for v in values.values() if v is not None]
    lo, hi = (min(numeric), max(numeric)) if numeric else (0, 1)

    path_elems = []
    for name, d in paths.items():
        val = values.get(name)
        fill = color_for_value(val, lo, hi) if val is not None else unmatched_fill
        val_attr = f"{val:.3g}" if val is not None else ""
        path_elems.append(
            f'<path class="gov" data-name="{name}" data-value="{val_attr}" '
            f'fill="{fill}" d="{d}"></path>'
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0; background: transparent; font-family: -apple-system, sans-serif;
  }}
  .wrap {{ position: relative; }}
  svg {{ width: 100%; height: auto; display: block; }}
  path.gov {{
    stroke: {stroke}; stroke-width: 1.4; stroke-linejoin: round;
    cursor: pointer; transition: filter 100ms ease;
  }}
  path.gov:hover {{ filter: brightness(0.88); }}
  .tooltip {{
    position: absolute; pointer-events: none; background: #161b22; color: #f4f3ee;
    font-size: 12px; font-weight: 600; padding: 6px 10px; border-radius: 6px;
    transform: translate(-50%, -130%); opacity: 0; transition: opacity 100ms ease;
    white-space: nowrap; z-index: 5;
  }}
  .tooltip.show {{ opacity: 1; }}
  .tooltip .u {{ font-weight: 400; opacity: 0.75; margin-left: 4px; }}
</style></head>
<body>
<div class="wrap" id="wrap">
  <svg viewBox="0 0 {VIEWBOX_W} {VIEWBOX_H}" xmlns="http://www.w3.org/2000/svg">
    {"".join(path_elems)}
  </svg>
  <div class="tooltip" id="tooltip"></div>
</div>
<script>
  var wrap = document.getElementById('wrap');
  var tip = document.getElementById('tooltip');
  document.querySelectorAll('.gov').forEach(function(p) {{
    p.addEventListener('mousemove', function(e) {{
      var rect = wrap.getBoundingClientRect();
      tip.style.left = (e.clientX - rect.left) + 'px';
      tip.style.top = (e.clientY - rect.top) + 'px';
      var v = p.dataset.value;
      var valueHtml = v
        ? '<span class="u">' + v + ' {unit}</span>'
        : '<span class="u">no data</span>';
      tip.innerHTML = p.dataset.name + valueHtml;
      tip.classList.add('show');
    }});
    p.addEventListener('mouseleave', function() {{ tip.classList.remove('show'); }});
  }});
  function sendHeight() {{
    var h = document.documentElement.scrollHeight;
    window.parent.postMessage({{type: "streamlit:setFrameHeight", height: h}}, "*");
  }}
  window.addEventListener('load', sendHeight);
  window.addEventListener('resize', sendHeight);
  sendHeight();
  setTimeout(sendHeight, 150);
</script>
</body></html>"""
