"""The dashboard's visual design system: color tokens, embedded fonts, and
HTML/SVG component builders. Ported from the design pitch explored as a
standalone mockup — see the project conversation history for the rationale
(Sidi-Bou-Said blue as the single accent, condensed Futura for headline
figures, system sans for everything else, a single validated sequential
blue ramp for every choropleth).

Streamlit's own chrome (sidebar, selectboxes, sliders) is themed via
.streamlit/config.toml, not here — this module only covers the custom
HTML/SVG pieces (KPI cards, the map, ranking bars) that replace Streamlit's
defaults.
"""

from __future__ import annotations

import base64
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets"

# Sequential blue ramp (light -> dark), validated for choropleth use.
RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]

COLORS = {
    "ground": "#f4f3ee",
    "surface": "#ffffff",
    "surface_2": "#eeece4",
    "ink": "#161b22",
    "ink_2": "#5b6472",
    "ink_3": "#8b92a0",
    "accent": "#1b4b8f",
    "accent_soft": "#e8eff9",
    "border": "rgba(22,27,34,0.09)",
    "border_strong": "rgba(22,27,34,0.16)",
}


def _font_b64(filename: str) -> str:
    return base64.b64encode((ASSETS_DIR / "fonts" / filename).read_bytes()).decode("ascii")


def load_css() -> str:
    xbd = _font_b64("futura-condensed-xbold.woff")
    med = _font_b64("futura-medium.woff")
    c = COLORS
    return f"""
<style>
@font-face {{
  font-family: "Futura Cond XBd";
  src: url(data:font/woff;base64,{xbd}) format("woff");
  font-weight: 800; font-display: swap;
}}
@font-face {{
  font-family: "Futura Med";
  src: url(data:font/woff;base64,{med}) format("woff");
  font-weight: 500; font-display: swap;
}}

.stApp {{ background: {c['ground']}; }}
[data-testid="stSidebar"] {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}

.tn-eyebrow {{
  font-family: "Futura Med", -apple-system, sans-serif;
  font-size: 11.5px; font-weight: 500; letter-spacing: 0.14em;
  text-transform: uppercase; color: {c['accent']}; margin-bottom: 2px;
}}
.tn-title {{
  font-family: "Futura Cond XBd", -apple-system, sans-serif;
  font-weight: 800; font-size: clamp(30px, 4.4vw, 46px); line-height: 1.03;
  color: {c['ink']}; margin: 0 0 6px 0;
}}
.tn-sub {{ font-size: 14.5px; line-height: 1.5; color: {c['ink_2']}; max-width: 70ch; margin: 0 0 8px 0; }}

.tn-kpi-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 4px 0 18px 0; }}
.tn-kpi {{
  flex: 1; min-width: 160px;
  background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px;
  padding: 16px 18px; box-shadow: 0 1px 2px rgba(22,27,34,0.04), 0 8px 24px -12px rgba(22,27,34,0.12);
}}
.tn-kpi-label {{ font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: {c['ink_3']}; margin-bottom: 6px; }}
.tn-kpi-value-row {{ display: flex; align-items: baseline; gap: 7px; }}
.tn-kpi-value {{
  font-family: "Futura Cond XBd", -apple-system, sans-serif; font-weight: 800;
  font-size: 30px; line-height: 1; color: {c['ink']}; font-variant-numeric: tabular-nums;
}}
.tn-kpi-unit {{ font-size: 12.5px; color: {c['ink_3']}; font-weight: 500; }}
.tn-kpi-meta {{ font-size: 12px; color: {c['ink_3']}; margin-top: 5px; font-variant-numeric: tabular-nums; }}

.tn-card {{
  background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px;
  padding: 18px 20px 20px; box-shadow: 0 1px 2px rgba(22,27,34,0.04), 0 8px 24px -12px rgba(22,27,34,0.12);
  margin-bottom: 14px;
}}
.tn-card-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 10px; }}
.tn-card-title {{ font-size: 14px; font-weight: 700; color: {c['ink']}; }}
.tn-card-note {{ font-size: 11.5px; color: {c['ink_3']}; font-family: Menlo, monospace; }}

.tn-rank-row {{ display: grid; grid-template-columns: 84px 1fr 50px; align-items: center; gap: 10px; padding: 5px 0; }}
.tn-rank-name {{ font-size: 12.5px; color: {c['ink_2']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tn-rank-track {{ height: 7px; background: {c['surface_2']}; border-radius: 4px; overflow: hidden; }}
.tn-rank-fill {{ height: 100%; background: {c['accent']}; border-radius: 4px; }}
.tn-rank-val {{ font-size: 12px; font-variant-numeric: tabular-nums; color: {c['ink']}; text-align: right; font-weight: 600; }}
.tn-rank-scroll {{ max-height: 380px; overflow-y: auto; padding-right: 4px; }}

.tn-dist-row {{ display: flex; align-items: baseline; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid {c['border']}; }}
.tn-dist-row:last-of-type {{ border-bottom: none; }}
.tn-dist-label {{ font-size: 12px; color: {c['ink_3']}; flex: 0 0 64px; }}
.tn-dist-val {{ font-family: "Futura Cond XBd", sans-serif; font-weight: 800; font-size: 19px; color: {c['ink']}; font-variant-numeric: tabular-nums; }}
.tn-dist-name {{ font-size: 11px; color: {c['ink_3']}; text-align: right; flex: 1; }}

.tn-note {{ font-size: 12.5px; line-height: 1.55; color: {c['ink_2']}; margin-top: 4px; }}
</style>
"""


def masthead_html(title: str, subtitle: str) -> str:
    return f"""
<div class="tn-eyebrow">Institut National de la Statistique &middot; Live Dashboard</div>
<div class="tn-title">{title}</div>
<div class="tn-sub">{subtitle}</div>
"""


def kpi_row_html(value: str, unit: str, year, delta_text: str, coverage_text: str) -> str:
    return f"""
<div class="tn-kpi-row">
  <div class="tn-kpi">
    <div class="tn-kpi-label">Latest value</div>
    <div class="tn-kpi-value-row"><span class="tn-kpi-value">{value}</span><span class="tn-kpi-unit">{unit}</span></div>
    <div class="tn-kpi-meta">{year}</div>
  </div>
  <div class="tn-kpi">
    <div class="tn-kpi-label">Change</div>
    <div class="tn-kpi-value-row"><span class="tn-kpi-value" style="font-size:22px">{delta_text}</span></div>
    <div class="tn-kpi-meta">vs. prior period</div>
  </div>
  <div class="tn-kpi">
    <div class="tn-kpi-label">Coverage</div>
    <div class="tn-kpi-value-row"><span class="tn-kpi-value" style="font-size:19px">{coverage_text}</span></div>
    <div class="tn-kpi-meta">granularity actually available</div>
  </div>
</div>
"""


def card_open(title: str, note: str = "") -> str:
    note_html = f'<span class="tn-card-note">{note}</span>' if note else ""
    return f'<div class="tn-card"><div class="tn-card-head"><span class="tn-card-title">{title}</span>{note_html}</div>'


CARD_CLOSE = "</div>"


def ranking_html(rows: list[tuple[str, float]], value_fmt: str = "{:.1f}") -> str:
    if not rows:
        return '<div class="tn-note">No regional breakdown to rank.</div>'
    mx = max(v for _, v in rows) or 1
    out = ['<div class="tn-rank-scroll">']
    for name, v in rows:
        pct = round(v / mx * 100, 1)
        out.append(
            f'<div class="tn-rank-row"><span class="tn-rank-name">{name}</span>'
            f'<div class="tn-rank-track"><div class="tn-rank-fill" style="width:{pct}%"></div></div>'
            f'<span class="tn-rank-val">{value_fmt.format(v)}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def distribution_html(lowest: tuple[str, float], median_val: float, highest: tuple[str, float], value_fmt: str = "{:.1f}") -> str:
    lo_name, lo_val = lowest
    hi_name, hi_val = highest
    return f"""
<div class="tn-dist-row"><span class="tn-dist-label">Lowest</span><span class="tn-dist-val">{value_fmt.format(lo_val)}</span><span class="tn-dist-name">{lo_name}</span></div>
<div class="tn-dist-row"><span class="tn-dist-label">Median</span><span class="tn-dist-val">{value_fmt.format(median_val)}</span><span class="tn-dist-name">&mdash;</span></div>
<div class="tn-dist-row"><span class="tn-dist-label">Highest</span><span class="tn-dist-val">{value_fmt.format(hi_val)}</span><span class="tn-dist-name">{hi_name}</span></div>
"""
