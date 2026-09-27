"""Render the single-file Australia board from the pipeline outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).parent / "output" / "australia_board.html"

CSS = """
:root {
  --paper:#EEF1EC; --surface:#FFFFFF; --surface-2:#F5F7F3;
  --ink:#14201A; --ink-soft:#52604F; --ink-mute:#85937F;
  --turf:#1B6B45; --turf-soft:#DCEDE2; --chalk:#B65420; --chalk-soft:#F3E2D4;
  --line:#D7DED2; --line-strong:#B9C4B4;
  --pitch:#1B3B2C; --pitch-line:rgba(255,255,255,0.5); --pitch-ink:#E6F0E9;
  --gold:#C4841F;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper:#0D1712; --surface:#131F19; --surface-2:#182620;
    --ink:#E9F0E9; --ink-soft:#A3B5A0; --ink-mute:#6F8171;
    --turf:#4CB884; --turf-soft:#1B3C2C; --chalk:#E38A52; --chalk-soft:#3D2A1B;
    --line:#253128; --line-strong:#37453B;
    --pitch:#0C1E15; --gold:#E0A54A;
  }
}
:root[data-theme="dark"] {
  --paper:#0D1712; --surface:#131F19; --surface-2:#182620;
  --ink:#E9F0E9; --ink-soft:#A3B5A0; --ink-mute:#6F8171;
  --turf:#4CB884; --turf-soft:#1B3C2C; --chalk:#E38A52; --chalk-soft:#3D2A1B;
  --line:#253128; --line-strong:#37453B;
  --pitch:#0C1E15; --gold:#E0A54A;
}
* { box-sizing:border-box; }
html,body { margin:0; padding:0; }
body {
  background:var(--paper); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.5; -webkit-font-smoothing:antialiased;
}
.num { font-family:ui-monospace,"SF Mono","Cascadia Mono",Consolas,monospace; font-variant-numeric:tabular-nums; }
.wrap { max-width:1180px; margin:0 auto; padding:0 20px; }

header.mast { border-bottom:1px solid var(--line); background:var(--surface); }
.mast .wrap { padding:22px 20px 18px; }
.mast .kicker { font-size:11.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--turf); font-weight:700; }
.mast h1 { margin:6px 0 8px; font-size:clamp(26px,4vw,38px); line-height:1.05; letter-spacing:-.01em; }
.mast p { margin:0; color:var(--ink-soft); max-width:66ch; font-size:15px; }
.mast .meta { margin-top:12px; display:flex; gap:18px; flex-wrap:wrap; font-size:12.5px; color:var(--ink-mute); }

nav.tabs { position:sticky; top:0; z-index:20; background:var(--surface); border-bottom:1px solid var(--line); }
nav.tabs .wrap { display:flex; gap:2px; overflow-x:auto; padding:0 20px; }
.tab { appearance:none; border:0; background:transparent; color:var(--ink-soft);
  padding:12px 14px; font-size:14px; font-weight:600; cursor:pointer; white-space:nowrap;
  border-bottom:2px solid transparent; }
.tab:hover { color:var(--ink); }
.tab[aria-selected="true"] { color:var(--turf); border-bottom-color:var(--turf); }

main { padding:26px 0 64px; }
section.panel[hidden] { display:none; }
h2 { font-size:19px; margin:30px 0 4px; letter-spacing:-.005em; }
h2:first-child { margin-top:0; }
h3 { font-size:14.5px; margin:22px 0 6px; color:var(--ink); }
p.lede { margin:0 0 14px; color:var(--ink-soft); max-width:78ch; font-size:14px; }
p.cap { margin:8px 0 0; color:var(--ink-mute); font-size:12.5px; max-width:82ch; }
p.cap b { color:var(--ink-soft); }

.card { background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:16px 18px; }
.grid { display:grid; gap:14px; }
.g2 { grid-template-columns:repeat(2,minmax(0,1fr)); }
.g3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
.g4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
@media (max-width:860px) { .g2,.g3,.g4 { grid-template-columns:1fr; } }

.stat { background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:12px 14px; }
.stat .k { font-size:11px; letter-spacing:.07em; text-transform:uppercase; color:var(--ink-mute); font-weight:700; }
.stat .v { font-size:25px; font-weight:650; margin-top:3px; letter-spacing:-.02em; }
.stat .s { font-size:12px; color:var(--ink-soft); margin-top:1px; }

table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { text-align:right; padding:6px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
th:first-child,td:first-child { text-align:left; }
th { font-size:11px; letter-spacing:.05em; text-transform:uppercase; color:var(--ink-mute);
  font-weight:700; border-bottom:1px solid var(--line-strong); position:sticky; top:45px;
  background:var(--paper); z-index:2; }
.card th { background:var(--surface); }
/* Inside a scroll container, sticky resolves against the container, not the
   page, so the nav offset must not be applied again. */
.tall th { top:0; }
tbody tr:hover { background:var(--surface-2); }
td.dim { color:var(--ink-mute); }
.scroll { overflow-x:auto; }
.tall { max-height:560px; overflow-y:auto; }

.pill { display:inline-block; font-size:11px; font-weight:700; padding:1px 7px; border-radius:9px;
  border:1px solid var(--line-strong); color:var(--ink-soft); }
.pill.W { background:var(--turf-soft); color:var(--turf); border-color:transparent; }
.pill.L { background:var(--chalk-soft); color:var(--chalk); border-color:transparent; }
.pill.D { background:var(--surface-2); }

.seg { display:inline-flex; border:1px solid var(--line-strong); border-radius:5px; overflow:hidden; flex-wrap:wrap; }
.seg button { appearance:none; border:0; background:var(--surface); color:var(--ink-soft);
  padding:6px 12px; font-size:12.5px; font-weight:600; cursor:pointer; border-right:1px solid var(--line); }
.seg button:last-child { border-right:0; }
.seg button[aria-pressed="true"] { background:var(--turf); color:#fff; }
:root[data-theme="dark"] .seg button[aria-pressed="true"] { color:#0B1811; }
.controls { display:flex; gap:16px; flex-wrap:wrap; align-items:center; margin:0 0 14px; }
.controls .lbl { font-size:11px; letter-spacing:.07em; text-transform:uppercase; color:var(--ink-mute); font-weight:700; margin-right:6px; }

svg { display:block; width:100%; height:auto; }
.bar { fill:var(--turf); }
.bar.alt { fill:var(--chalk); }
.axis { stroke:var(--line-strong); }
.glab { font-size:10.5px; fill:var(--ink-mute); }
.gval { font-size:11px; fill:var(--ink-soft); font-weight:600; }

.zsel { display:grid; grid-template-columns:repeat(6,1fr); gap:3px; max-width:420px; }
.zsel button { appearance:none; border:1px solid var(--line-strong); background:var(--surface);
  color:var(--ink-mute); font-size:10.5px; font-weight:700; padding:7px 0; cursor:pointer; border-radius:3px; }
.zsel button[aria-pressed="true"] { background:var(--turf); color:#fff; border-color:var(--turf); }
.zsel button:disabled { opacity:.32; cursor:not-allowed; }

.note { border-left:3px solid var(--gold); background:var(--surface); padding:12px 14px;
  border-radius:0 5px 5px 0; font-size:13.5px; color:var(--ink-soft); }
.note b { color:var(--ink); }
footer { border-top:1px solid var(--line); margin-top:40px; padding:20px 0 40px; color:var(--ink-mute); font-size:12.5px; }
footer .wrap { display:flex; gap:20px; justify-content:space-between; flex-wrap:wrap; }
a { color:var(--turf); }
.bar-row { display:flex; align-items:center; gap:8px; }
.bar-track { flex:1; height:7px; background:var(--surface-2); border-radius:4px; overflow:hidden; min-width:60px; }
.bar-fill { height:100%; background:var(--turf); }
"""


def build() -> None:
    out = Path(__file__).parent / "output"
    data = {name: json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("campaigns", "shape360", "compare", "players", "pathway")}

    # Header figures are derived, not typed, so a rerun on new data stays true.
    n_matches = len(data["campaigns"]["matches"])
    n_frames = sum(c["quality"]["frames_aligned"] for c in data["shape360"]["campaigns"].values())
    n_players = len({r["player_id"] for r in data["players"]["players"]})
    n_seasons = len(data["pathway"]["seasons"])

    html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Australia Football Board</title>
<style>{CSS}</style>
<body>
<header class="mast"><div class="wrap">
  <div class="kicker">National teams &middot; measured positional data</div>
  <h1>Australia Football Board</h1>
  <p>Eleven Socceroos and Matildas matches from the 2022 and 2023 World Cups, built on
  StatsBomb 360 &mdash; event data <em>plus</em> the measured position of every player the
  broadcast camera could see. The club boards in this portfolio have no positional data at
  all. This one does, so it is used for two things: to show the Australian sides' shape as
  it actually was, and to put an error bar on every positional estimate the other boards make.</p>
  <div class="meta">
    <span><b>{n_matches}</b> matches</span>
    <span><b>{n_frames:,}</b> validated freeze frames</span>
    <span><b>{n_players}</b> Australian internationals</span>
    <span><b>{n_seasons}</b> A-League seasons for the pathway layer</span>
  </div>
</div></header>

<nav class="tabs"><div class="wrap" role="tablist">
  <button class="tab" role="tab" data-tab="campaigns" aria-selected="true">Campaigns</button>
  <button class="tab" role="tab" data-tab="shape" aria-selected="false">Measured shape</button>
  <button class="tab" role="tab" data-tab="compare" aria-selected="false">Event data vs 360</button>
  <button class="tab" role="tab" data-tab="players" aria-selected="false">Australians</button>
  <button class="tab" role="tab" data-tab="pathway" aria-selected="false">Pathway</button>
</div></nav>

<main><div class="wrap">
  <section class="panel" id="p-campaigns"></section>
  <section class="panel" id="p-shape" hidden></section>
  <section class="panel" id="p-compare" hidden></section>
  <section class="panel" id="p-players" hidden></section>
  <section class="panel" id="p-pathway" hidden></section>
</div></main>

<footer><div class="wrap">
  <span>Jun Park &middot; built from StatsBomb open data and FBref. Aggregated statistics only.</span>
  <span>xG is StatsBomb's own value. No model is fitted on this board.</span>
</div></footer>

<script>
const DATA = {json.dumps(data, separators=(",", ":"))};
{JS}
</script>
</body></html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.name}  {OUT.stat().st_size / 1024:.0f} KB")


JS = r"""
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
const nf = (v, d=2) => (v===null||v===undefined) ? '&ndash;' : Number(v).toFixed(d);
const pc = (v, d=1) => (v===null||v===undefined) ? '&ndash;' : Number(v).toFixed(d)+'%';
const CAMPS = ['matildas','socceroos'];
const CAMP_NAME = {matildas:'Matildas', socceroos:'Socceroos'};

/* ---------------------------------------------------------------- pitch ---- */
const PW = 120, PH = 80;
function pitchSvg(w, h, inner) {
  // Direct coordinate mapping: x rightward (attacking), y downward. y=0 is the
  // attacking team's LEFT touchline, so the left back sits at the top - the
  // physically correct bird's-eye view and StatsBomb's own plot orientation.
  const pad = 2;
  return `<svg viewBox="${-pad} ${-pad} ${PW+2*pad} ${PH+2*pad}" style="max-height:${h}px">
    <rect x="0" y="0" width="${PW}" height="${PH}" fill="var(--pitch)"/>
    ${inner}
    <g fill="none" stroke="var(--pitch-line)" stroke-width="0.4">
      <rect x="0" y="0" width="${PW}" height="${PH}"/>
      <line x1="60" y1="0" x2="60" y2="${PH}"/>
      <circle cx="60" cy="40" r="9.15"/>
      <rect x="0" y="18" width="18" height="44"/><rect x="102" y="18" width="18" height="44"/>
      <rect x="0" y="30" width="6" height="20"/><rect x="114" y="30" width="6" height="20"/>
    </g>
    <g fill="var(--pitch-ink)" opacity="0.62">
      <text x="2" y="4.8" style="font-size:2.4px">left channel</text>
      <text x="2" y="77.6" style="font-size:2.4px">right channel</text>
      <text x="118" y="4.8" text-anchor="end" style="font-size:2.4px">own goal left &middot; attacking right &rarr;</text>
    </g>
  </svg>`;
}

/* ------------------------------------------------------------ campaigns ---- */
function renderCampaigns() {
  const d = DATA.campaigns;
  let h = `<h2>Two campaigns, eleven matches</h2>
  <p class="lede">Event-only metrics, directly comparable with the club boards. Goals are
  reconciled against the real scorelines: the penalty shootout against France is excluded
  (its penalties are ordinary shot events carrying real xG) and the Enzo Fern&aacute;ndez own
  goal is added back, because own goals are their own event type and carry no xG.</p>`;

  h += '<div class="grid g2">';
  for (const camp of CAMPS) {
    const a = d.campaigns[camp];
    h += `<div class="card">
      <div class="kicker" style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--turf);font-weight:700">${esc(CAMP_NAME[camp])}</div>
      <h3 style="margin:4px 0 10px">${esc(a.label)}</h3>
      <div class="grid g2" style="gap:10px">
        <div class="stat"><div class="k">Record</div><div class="v num">${a.w}&ndash;${a.d}&ndash;${a.l}</div>
          <div class="s">${a.matches} matches, ${Math.round(a.minutes)} minutes</div></div>
        <div class="stat"><div class="k">Goals</div><div class="v num">${a.aus.goals}&ndash;${a.opp.goals}</div>
          <div class="s">xG ${nf(a.aus.xg)} &ndash; ${nf(a.opp.xg)}</div></div>
        <div class="stat"><div class="k">Possession</div><div class="v num">${nf(a.aus.possession,1)}%</div>
          <div class="s">field tilt ${nf(a.aus.field_tilt,1)}%</div></div>
        <div class="stat"><div class="k">xG per 90</div><div class="v num">${nf(a.aus.xg_p90)}</div>
          <div class="s">conceded ${nf(a.opp.xg_p90)}</div></div>
      </div>
      <table style="margin-top:12px">
        <tbody>
        <tr><td>Passes, completion</td><td class="num">${a.aus.passes} &middot; ${nf(a.aus.pass_pct,1)}%</td></tr>
        <tr><td>Share of passes made under pressure</td><td class="num">${nf(a.aus.pressed_share,1)}%</td></tr>
        <tr><td>Completion when pressed</td><td class="num">${nf(a.aus.pass_pct_pressed,1)}%</td></tr>
        <tr><td>Final-third entries per 90</td><td class="num">${nf(a.aus.entries_f3_p90,1)}</td></tr>
        <tr><td>Box entries per 90</td><td class="num">${nf(a.aus.entries_box_p90,1)}</td></tr>
        <tr><td>PPDA (opponent passes per pressure)</td><td class="num">${nf(a.aus.ppda,2)}</td></tr>
        <tr><td>Set-piece share of own xG</td><td class="num">${pc(100*a.aus.xg_sp/Math.max(a.aus.xg,0.01))}</td></tr>
        </tbody>
      </table>
    </div>`;
  }
  h += '</div>';

  h += `<h2>Match by match</h2>
  <p class="lede">All figures are Australia's except <b>xG vs</b>, which is the opponent's.
  Formations are StatsBomb's own formation events, including in-match shifts &mdash; not shapes
  inferred from average positions.</p>
  <div class="scroll"><table><thead><tr>
    <th>Date</th><th>Opponent</th><th>Stage</th><th></th><th>Score</th>
    <th>xG</th><th>xG vs</th><th>Poss</th><th>Tilt</th><th>Box entries</th>
    <th>Pressed</th><th>PPDA</th><th>Shape</th></tr></thead><tbody>`;
  for (const m of d.matches) {
    const forms = m.aus.formations.map(f => f[1]).filter((v,i,a) => a.indexOf(v)===i)
      .map(v => String(v).split('').join('-')).join(' → ');
    h += `<tr>
      <td class="num dim">${esc(m.date)}</td>
      <td>${esc(m.opponent.replace(" Women's",''))}</td>
      <td class="dim">${esc(m.stage)}</td>
      <td><span class="pill ${m.result}">${m.result}</span></td>
      <td class="num">${m.gf}&ndash;${m.ga}</td>
      <td class="num">${nf(m.aus.xg)}</td><td class="num dim">${nf(m.opp.xg)}</td>
      <td class="num">${nf(m.aus.possession,1)}%</td>
      <td class="num">${nf(m.aus.field_tilt,1)}%</td>
      <td class="num">${m.aus.entries_box}</td>
      <td class="num">${nf(m.aus.pressed_share,1)}%</td>
      <td class="num">${nf(m.aus.ppda,2)}</td>
      <td class="dim">${esc(forms)}</td></tr>`;
  }
  h += '</tbody></table></div>';
  h += `<p class="cap">The two campaigns are not comparable to each other and are not presented
  as if they were: different tournament, different opposition, different squad, seven matches
  against four. Each is a description of one campaign.</p>`;
  $('#p-campaigns').innerHTML = h;
}

/* ---------------------------------------------------------------- shape ---- */
const shapeState = { camp:'matildas', phase:'in_possession', zone:8, layer:'diff' };

function zoneLabel(z) {
  const cols = DATA.shape360.zones.cols;
  const row = Math.floor(z / cols), col = z % cols;
  return ['L','C','R'][row] + (col + 1);
}

function renderShape() {
  const S = DATA.shape360, st = shapeState;
  const camp = S.campaigns[st.camp];
  const blk = camp.phases[st.phase];
  const zones = S.zones, grid = S.grid;

  let h = `<h2>Measured shape, not estimated shape</h2>
  <p class="lede">Pick where the ball was. The pitch below shows where players actually stood
  at that moment, averaged over every validated freeze frame with the ball in that zone.
  This is the one thing event data cannot give you: with events alone you know who touched
  the ball and where, and nothing about the other twenty players.</p>`;

  h += `<div class="controls">
    <span><span class="lbl">Side</span><span class="seg">` +
    CAMPS.map(k => `<button data-set="camp" data-val="${k}" aria-pressed="${st.camp===k}">${CAMP_NAME[k]}</button>`).join('') +
    `</span></span>
    <span><span class="lbl">Phase</span><span class="seg">
      <button data-set="phase" data-val="in_possession" aria-pressed="${st.phase==='in_possession'}">Australia on the ball</button>
      <button data-set="phase" data-val="out_of_possession" aria-pressed="${st.phase==='out_of_possession'}">Australia defending</button>
    </span></span>
    <span><span class="lbl">Layer</span><span class="seg">
      <button data-set="layer" data-val="diff" aria-pressed="${st.layer==='diff'}">Who outnumbers whom</button>
      <button data-set="layer" data-val="own" aria-pressed="${st.layer==='own'}">Team on the ball</button>
      <button data-set="layer" data-val="opp" aria-pressed="${st.layer==='opp'}">Team defending</button>
    </span></span>
  </div>`;

  // zone picker
  h += `<div class="grid g2"><div>
    <h3>Where the ball was</h3><div class="zsel">`;
  for (let r = 0; r < zones.rows; r++) {
    for (let col = 0; col < zones.cols; col++) {
      const z = r * zones.cols + col;
      const n = blk.frames[z], live = !!blk.grids[z];
      h += `<button data-set="zone" data-val="${z}" aria-pressed="${st.zone===z}" ${live?'':'disabled'}
        title="${n} frames">${zoneLabel(z)}<br><span class="num" style="font-weight:400;font-size:9.5px">${n}</span></button>`;
    }
  }
  h += `</div><p class="cap">Rows are channels as the team on the ball sees them:
  <b>L</b> left, <b>C</b> central, <b>R</b> right. Columns run from that team's own goal (1)
  to the goal they attack (6). The small number is the frame count; a zone with fewer than
  ${S.thresholds.min_frames_zone} frames is greyed out rather than drawn.</p></div>`;

  // metrics for the selected zone
  const M = blk.metrics, z = st.zone;
  const rows = [
    ['Distance from the ball to the nearest opponent', M.nearest_opponent_m?.[z], ' m'],
    ['Share of moments with an opponent inside 5 m', M.pressed_within_5m?.[z], '%'],
    ['Opponents within 10 m of the ball', M.opponents_within_10m?.[z], ''],
    ['Team-mates within 10 m of the ball', M.support_within_10m?.[z], ''],
    ['Opponents ahead of the ball', M.opponents_ahead_of_ball?.[z], ''],
    ['Team-mates ahead of the ball', M.teammates_ahead_of_ball?.[z], ''],
    ['Players visible in the frame, of 22', M.visible_players?.[z], ''],
  ];
  h += `<div><h3>Measured in zone ${zoneLabel(z)} &middot; ${blk.frames[z]} frames</h3>
    <table><tbody>` +
    rows.map(([k, v, u]) => `<tr><td>${k}</td><td class="num">${v===null||v===undefined?'&ndash;':nf(v,2)+u}</td></tr>`).join('') +
    `</tbody></table>
    <p class="cap">A dash means the measurement was refused, not that it is zero.
    <b>Ahead of the ball</b> is only counted when the camera actually covered the space
    between the ball and the goal it was attacking &mdash; tested per frame against the
    broadcast visible-area polygon.</p></div></div>`;

  // density pitch
  const g = blk.grids[z];
  let cells = '';
  if (g) {
    const cw = PW / grid.cols, ch = PH / grid.rows;
    let peak = 0;
    for (let i = 0; i < g.own.length; i++) {
      for (const v of [g.own[i], g.opp[i]]) if (v !== null) peak = Math.max(peak, v);
    }
    const peakDiff = Math.max(...g.own.map((v,i) => (v===null||g.opp[i]===null)?0:Math.abs(v-g.opp[i])), 0.01);
    for (let i = 0; i < g.own.length; i++) {
      const col = Math.floor(i / grid.rows), row = i % grid.rows;
      const x = col * cw, y = row * ch;
      const own = g.own[i], opp = g.opp[i];
      let fill = 'none', op = 0;
      if (own === null || opp === null) {
        cells += `<rect x="${x}" y="${y}" width="${cw}" height="${ch}" fill="url(#hatch)" opacity="0.5"/>`;
        continue;
      }
      if (st.layer === 'own') { fill = 'var(--turf)'; op = Math.min(1, own / (peak||1)) * 0.86; }
      else if (st.layer === 'opp') { fill = 'var(--chalk)'; op = Math.min(1, opp / (peak||1)) * 0.86; }
      else {
        const d = own - opp;
        fill = d >= 0 ? 'var(--turf)' : 'var(--chalk)';
        op = Math.min(1, Math.abs(d) / peakDiff) * 0.86;
      }
      cells += `<rect x="${x}" y="${y}" width="${cw}" height="${ch}" fill="${fill}" opacity="${op.toFixed(3)}"/>`;
    }
    // outline the selected ball zone
    const zw = PW / zones.cols, zh = PH / zones.rows;
    const zc = z % zones.cols, zr = Math.floor(z / zones.cols);
    cells += `<rect x="${zc*zw}" y="${zr*zh}" width="${zw}" height="${zh}" fill="none"
      stroke="var(--gold)" stroke-width="0.8" stroke-dasharray="2 1.5"/>`;
  }
  const defs = `<defs><pattern id="hatch" width="3" height="3" patternUnits="userSpaceOnUse"
    patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="3" stroke="var(--pitch-line)" stroke-width="0.6"/></pattern></defs>`;

  const onBall = st.phase === 'in_possession' ? CAMP_NAME[st.camp] : camp.phases ? 'the opponent' : '';
  const defending = st.phase === 'in_possession' ? 'the opponent' : CAMP_NAME[st.camp];
  h += `<h3 style="margin-top:26px">Where players stood &middot; ball in zone ${zoneLabel(z)}</h3>
  <div class="card" style="padding:12px">${pitchSvg(1180, 520, defs + cells)}</div>
  <p class="cap"><b>Green</b> is the team on the ball (${esc(onBall)}), <b>orange</b> the team
  defending (${esc(defending)}). Attacking left to right, so the top of the image is the left
  channel. Hatched cells are refused: the broadcast camera covered them in fewer than
  ${S.thresholds.min_vis_cell} of this zone's frames, and a cell the camera never showed would
  otherwise read as "nobody stands here", which is a camera fact rather than a football one.
  Every cell has its own denominator &mdash; players seen there divided by the number of frames
  in which that cell was genuinely inside the visible area.</p>`;

  const q = camp.quality;
  h += `<div class="note" style="margin-top:18px"><b>What this layer is honest about.</b>
  A 360 frame holds only the players the broadcast camera could see &mdash; a median of
  ${(q.visible_players/q.visible_frames).toFixed(1)} of 22 in this campaign. Frames keyed to
  secondary events (ball receipts, duels, dispossessions) are captured at the related primary
  action rather than the event they are attached to, so every frame is checked first: the player
  on the ball must be standing on the event, within ${S.thresholds.actor_tol_m} m.
  ${q.frames_aligned.toLocaleString()} of ${q.frames_primary.toLocaleString()} frames on primary
  on-ball actions passed that check; ${q.frames_used.toLocaleString()} open-play frames are used here.
  Block height and block width are deliberately not computed anywhere on this board: the camera
  follows the ball, so any average of visible defenders' positions measures where the camera
  pointed as much as where the defence stood.</div>`;

  $('#p-shape').innerHTML = h;
}

/* -------------------------------------------------------------- compare ---- */
function hbars(rows, unit, maxOverride) {
  const max = maxOverride || Math.max(...rows.map(r => r[1] || 0)) * 1.15;
  const rowH = 26, w = 560, labW = 96, h = rows.length * rowH + 8;
  let s = `<svg viewBox="0 0 ${w} ${h}" style="max-height:${h+10}px">`;
  rows.forEach((r, i) => {
    const y = i * rowH + 4;
    const bw = Math.max(0, (r[1] || 0) / max) * (w - labW - 76);
    s += `<text class="glab" x="0" y="${y+13}">${esc(r[0])}</text>
      <rect class="bar${r[2]?' alt':''}" x="${labW}" y="${y+4}" width="${bw.toFixed(1)}" height="13" rx="2"/>
      <text class="gval" x="${labW + bw + 6}" y="${y+14}">${nf(r[1],2)}${unit}${r[3]?' <tspan class="glab">'+esc(r[3])+'</tspan>':''}</text>`;
  });
  return s + '</svg>';
}

function renderCompare() {
  const C = DATA.compare;
  const lo = C.leave_one_out, se = C.estimate_error;
  let h = `<h2>What positional data is actually worth</h2>
  <p class="lede">The other boards in this portfolio have no positional data, so off-ball
  positions there are <em>estimated</em> from each player's own touches, interpolated between
  the events either side of the moment. These eleven matches have both, so that estimate can be
  scored against measured truth. This is the error bar those boards should be read with.</p>`;

  h += `<div class="grid g4">
    <div class="stat"><div class="k">On the ball, &lt;5 s old</div>
      <div class="v num">${nf(lo.by_staleness['0-5s'].median,1)} m</div><div class="s">median error</div></div>
    <div class="stat"><div class="k">On the ball, 40&ndash;60 s old</div>
      <div class="v num">${nf(lo.by_staleness['40-60s'].median,1)} m</div><div class="s">median error</div></div>
    <div class="stat"><div class="k">Off-ball players</div>
      <div class="v num">${nf(se.all.median,1)} m</div><div class="s">median, and a lower bound</div></div>
    <div class="stat"><div class="k">Assume everyone is on the centre spot</div>
      <div class="v num">${nf(se.baseline_pitch_centre.median,1)} m</div><div class="s">the naive baseline</div></div>
  </div>
  <p class="cap">The headline: an event-only position estimate is good for the player on the
  ball in the seconds around a touch, and close to worthless for everybody else. Estimating
  off-ball positions from events beat "assume all eleven stand on the centre spot" by about
  ${nf(se.baseline_pitch_centre.median - se.all.median,1)} m.</p>`;

  h += `<h2>Identity-true test: the player on the ball</h2>
  <p class="lede">Leave-one-out. Hide the touch we are standing on, estimate that player's
  position from their other touches, and compare with where they really were &mdash; which we
  know exactly, because it is the event's own location. ${lo.all.n.toLocaleString()} estimates scored.</p>
  <div class="grid g2"><div class="card"><h3 style="margin-top:0">Error by how stale the estimate is</h3>
  ${hbars(Object.entries(lo.by_staleness).filter(([,v])=>v).map(([k,v]) => [k, v.median, false, 'n='+v.n.toLocaleString()]), ' m')}
  <p class="cap">Staleness is the gap to the nearer of the two touches the estimate interpolates
  between. Beyond ${se.gap_max_s} s the estimate is dropped rather than stretched further.</p></div>
  <div class="card"><h3 style="margin-top:0">Error by role</h3>
  ${hbars(Object.entries(lo.by_role).sort((a,b)=>a[1].median-b[1].median).map(([k,v]) => [k, v.median, false, 'n='+v.n.toLocaleString()]), ' m')}
  <p class="cap">Centre backs are the most predictable and wide midfielders the least, which is
  the ordering you would expect and a reason to trust the method more for some roles than others.</p></div></div>`;

  h += `<h2>Set-level test: everybody else</h2>
  <p class="lede">A freeze frame carries no player identities, so the estimated set of positions
  is matched to the measured set at minimum total cost. That gives the estimate every benefit of
  the doubt &mdash; it is free to pair each measured player with whichever estimate happens to sit
  closest &mdash; so the real per-player error is worse than this. It is a lower bound.</p>
  <div class="card">${hbars(
    Object.entries(se.by_staleness).filter(([,v])=>v).map(([k,v]) => [k, v.median, true, 'n='+v.n.toLocaleString()])
      .concat([['centre-spot baseline', se.baseline_pitch_centre.median, false, '']]), ' m')}</div>
  <p class="cap">${se.all.n.toLocaleString()} estimate-to-measurement pairs. Median
  ${nf(se.all.median,2)} m, p90 ${nf(se.all.p90,1)} m. This is why the club boards in this
  portfolio confidence-tier their positional estimates and refuse to infer team shape from
  events: at this error, a drawn "shape" would be decoration.</p>`;

  const pf = C.pressure_flag, dis = pf.disagreement;
  h += `<h2>What "under pressure" is worth</h2>
  <p class="lede">Event data carries a binary <span class="num">under_pressure</span> flag.
  A freeze frame gives the actual distance to the nearest opponent, so the flag can be graded.</p>
  <div class="grid g2"><div class="card">
  ${hbars([['flagged', pf.flagged.median, false, 'n='+pf.flagged.n.toLocaleString()],
           ['not flagged', pf.not_flagged.median, true, 'n='+pf.not_flagged.n.toLocaleString()]], ' m')}
  <p class="cap">Median distance to the nearest opponent. The flag is real and it separates
  cleanly: ${nf(pf.flagged.median,2)} m against ${nf(pf.not_flagged.median,2)} m.</p></div>
  <div class="card"><h3 style="margin-top:0">Where the flag and the tape measure disagree</h3>
  <table><tbody>
    <tr><td>Flagged, but the nearest opponent was over 5 m away</td><td class="num">${pc(dis.flagged_but_over_5m)}</td></tr>
    <tr><td>Not flagged, but an opponent was inside 5 m</td><td class="num">${pc(dis.not_flagged_but_under_5m)}</td></tr>
  </tbody></table>
  <p class="cap">The second row is the one that matters. Two in five unpressured touches had an
  opponent within five metres, so "not flagged" does not mean "in space" &mdash; it means nobody
  was actively closing. Treating the flag as a proxy for space, which is tempting when it is all
  you have, would be wrong about 42% of the time.</p></div></div>`;

  const ps = C.pass_space;
  h += `<h2>Passing into space</h2>
  <p class="lede">Event data knows where a pass ended. It cannot know whether anybody was there.
  Measured below: the distance from the pass's end point to the nearest opponent standing at the
  moment the pass was played.</p>
  <div class="card">${hbars([
    ['completed', ps.complete.median, false, 'n='+ps.complete.n.toLocaleString()],
    ['incomplete', ps.incomplete.median, true, 'n='+ps.incomplete.n.toLocaleString()]], ' m')}</div>
  <p class="cap">Completed passes ended a median ${nf(ps.complete.median,1)} m from the nearest
  opponent; incomplete ones ${nf(ps.incomplete.median,1)} m. Unsurprising as a direction, but it
  is a quantity, and quantities are what let you separate a bad pass from a pass into a closed door.</p>`;

  $('#p-compare').innerHTML = h;
}

/* -------------------------------------------------------------- players ---- */
const playerState = { camp:'matildas', sort:'minutes', desc:true };
const P_COLS = [
  ['name','Player',0], ['role','Role',0], ['minutes','Min',1], ['apps','Apps',0],
  ['starts','St',0], ['goals','G',0], ['assists','A',0], ['xg','xG',2], ['xa','xA',2],
  ['progressive_p90','Prog/90',1], ['carries_prog_p90','Carries+/90',1],
  ['pressures_p90','Press/90',1], ['duel_pct','Duel%',0],
  ['space_median_m','Space m',2], ['pressed_pct','Pressed%',0],
];

function renderPlayers() {
  const st = playerState;
  const rows = DATA.players.players.filter(r => r.campaign === st.camp);
  rows.sort((a, b) => {
    const va = a[st.sort], vb = b[st.sort];
    if (va === null || va === undefined) return 1;
    if (vb === null || vb === undefined) return -1;
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
    return st.desc ? -cmp : cmp;
  });

  let h = `<h2>Every Australian who played</h2>
  <p class="lede">Australia's senior internationals across the two campaigns, all listed as
  Australian in StatsBomb's own lineup data. The last two columns are the ones a club board
  built on event data cannot produce.</p>
  <div class="controls"><span><span class="lbl">Squad</span><span class="seg">` +
  CAMPS.map(k => `<button data-set="pcamp" data-val="${k}" aria-pressed="${st.camp===k}">${CAMP_NAME[k]}</button>`).join('') +
  `</span></span></div>
  <div class="scroll tall"><table><thead><tr>` +
  P_COLS.map(([k,lab]) => `<th data-sort="${k}" style="cursor:pointer">${esc(lab)}${st.sort===k?(st.desc?' ▾':' ▴'):''}</th>`).join('') +
  `</tr></thead><tbody>`;
  for (const r of rows) {
    h += '<tr>' + P_COLS.map(([k,,d]) => {
      const v = r[k];
      if (k === 'name') return `<td>${esc(v)} <span class="dim num" style="font-size:11px">${r.jersey}</span></td>`;
      if (k === 'role') return `<td class="dim">${esc(v)}</td>`;
      if (v === null || v === undefined) return '<td class="num dim">&ndash;</td>';
      return `<td class="num">${typeof v === 'number' ? Number(v).toFixed(d) : esc(v)}</td>`;
    }).join('') + '</tr>';
  }
  h += `</tbody></table></div>
  <p class="cap"><b>Space m</b> is the median measured distance to the nearest opponent at the
  moment this player was on the ball. <b>Pressed%</b> is the share of those moments with an
  opponent inside five metres. Both come from validated freeze frames and both are blank where
  a player had fewer than 25 such moments. Players under
  ${DATA.players.min_minutes} minutes are left out entirely.</p>

  <div class="note" style="margin-top:6px"><b>Read the space column as a role description, not a
  ranking.</b> A goalkeeper has fourteen metres because nobody presses them; a centre forward has
  two because that is the job. It is useful for comparing players in the same role, and for
  seeing which of Australia's build-up routes were genuinely free &mdash; not for saying one
  player was better than another. Eleven matches is a small sample and two tournaments a year
  apart are not one population.</div>`;

  $('#p-players').innerHTML = h;
}

/* -------------------------------------------------------------- pathway ---- */
const pathState = { comp:'men' };

function renderPathway() {
  const PA = DATA.pathway, st = pathState;
  const comp = PA.competitions[st.comp];
  const seasons = Object.keys(comp.by_season);
  const latest = seasons[seasons.length - 1];
  const p = comp.by_season[latest];

  let h = `<h2>Where A-League minutes go</h2>
  <p class="lede">Football Australia's own stated priority, under Principle 5 of the XI
  Principles and in the National Talent Development Scheme, is youth match minutes and a
  clearer pathway. That is a measurable claim, so here it is measured: the share of A-League
  minutes going to young Australian-listed players, by club and by season.</p>
  <div class="controls"><span><span class="lbl">Competition</span><span class="seg">
    <button data-set="pathcomp" data-val="men" aria-pressed="${st.comp==='men'}">A-League Men</button>
    <button data-set="pathcomp" data-val="women" aria-pressed="${st.comp==='women'}">A-League Women</button>
  </span></span></div>`;

  h += `<div class="grid g4">
    <div class="stat"><div class="k">Australian-listed minutes</div><div class="v num">${nf(p.aus_share,1)}%</div>
      <div class="s">${latest}</div></div>
    <div class="stat"><div class="k">To Australians aged ${PA.youth_max_age} or under</div>
      <div class="v num">${nf(p.young_aus_share,1)}%</div><div class="s">of all minutes</div></div>
    <div class="stat"><div class="k">Young Australian regulars</div>
      <div class="v num">${p.young_aus_regulars}</div>
      <div class="s">over ${PA.regular_minutes} minutes</div></div>
    <div class="stat"><div class="k">Minute-weighted age</div><div class="v num">${nf(p.minute_weighted_age,1)}</div>
      <div class="s">${p.players} players used</div></div>
  </div>`;

  h += `<h2>Two seasons</h2><div class="scroll"><table><thead><tr>
    <th>Season</th><th>Matches in table</th><th>Players</th><th>Australian-listed</th>
    <th>U${PA.youth_max_age+1} Australians</th><th>Regulars</th><th>Weighted age</th>
    </tr></thead><tbody>`;
  for (const s of seasons) {
    const q = comp.by_season[s];
    h += `<tr><td>${esc(s)}</td><td class="num dim">${q.matches_implied}</td><td class="num">${q.players}</td>
      <td class="num">${nf(q.aus_share,1)}%</td><td class="num">${nf(q.young_aus_share,1)}%</td>
      <td class="num">${q.young_aus_regulars}</td><td class="num">${nf(q.minute_weighted_age,1)}</td></tr>`;
  }
  h += `</tbody></table></div>
  <p class="cap">The two seasons hold different numbers of matches in FBref's tables, so the
  comparison is of <b>shares</b>, not volumes, and the implied match count is shown so that is
  visible rather than buried.</p>`;

  h += `<h2>Minutes by age band &middot; ${esc(latest)}</h2>
  <div class="card">${hbars(PA.age_bands.map(b => [b, p.bands[b].share, false,
    'of which Australian-listed ' + nf(p.bands[b].aus_share,1) + '%']), '%')}</div>
  <p class="cap">Green is each band's share of all minutes; the grey note is how much of the
  league total went to Australian-listed players in that band.</p>`;

  const clubs = comp.clubs[latest] || {};
  const order = Object.keys(clubs).sort((a,b) => clubs[b].young_aus_share - clubs[a].young_aus_share);
  h += `<h2>By club &middot; ${esc(latest)}</h2>
  <p class="lede">Ranked by the share of their own minutes given to Australian-listed players
  aged ${PA.youth_max_age} or under.</p>
  <div class="scroll"><table><thead><tr><th>Club</th><th>U${PA.youth_max_age+1} Australians</th>
    <th></th><th>Australian-listed</th><th>Weighted age</th><th>Players</th></tr></thead><tbody>`;
  const top = Math.max(...order.map(k => clubs[k].young_aus_share || 0), 1);
  for (const k of order) {
    const q = clubs[k];
    h += `<tr><td>${esc(k)}</td><td class="num">${nf(q.young_aus_share,1)}%</td>
      <td style="width:150px"><div class="bar-row"><div class="bar-track">
        <div class="bar-fill" style="width:${(100*(q.young_aus_share||0)/top).toFixed(0)}%"></div></div></div></td>
      <td class="num">${nf(q.aus_share,1)}%</td><td class="num">${nf(q.minute_weighted_age,1)}</td>
      <td class="num dim">${q.players}</td></tr>`;
  }
  h += '</tbody></table></div>';

  if (comp.top_young.length) {
    h += `<h2>Most-played young Australians &middot; ${esc(latest)}</h2>
    <div class="scroll"><table><thead><tr><th>Player</th><th>Club</th><th>Age</th><th>Pos</th>
      <th>Minutes</th><th>Starts</th><th>G</th><th>A</th></tr></thead><tbody>`;
    for (const r of comp.top_young) {
      h += `<tr><td>${esc(r.player)}</td><td class="dim">${esc(r.team)}</td><td class="num">${r.age}</td>
        <td class="dim">${esc(r.pos)}</td><td class="num">${r.minutes.toLocaleString()}</td>
        <td class="num">${r.starts}</td><td class="num">${r.goals}</td><td class="num">${r.assists}</td></tr>`;
    }
    h += '</tbody></table></div>';
  }

  h += `<div class="note" style="margin-top:18px"><b>What "Australian" means here.</b> FBref lists
  one international nationality per player, so this counts that field &mdash; not eligibility.
  Dual nationals and players yet to commit are counted wherever FBref puts them, which will
  understate the genuinely available pool. A federation would run this off its own registration
  data instead, which is exactly why the column is labelled Australian-<em>listed</em>.</div>`;

  $('#p-pathway').innerHTML = h;
}

/* ----------------------------------------------------------------- wiring -- */
const RENDER = { campaigns:renderCampaigns, shape:renderShape, compare:renderCompare,
                 players:renderPlayers, pathway:renderPathway };

document.addEventListener('click', ev => {
  const tab = ev.target.closest('.tab');
  if (tab) {
    for (const t of document.querySelectorAll('.tab')) t.setAttribute('aria-selected', String(t === tab));
    for (const p of document.querySelectorAll('.panel')) p.hidden = p.id !== 'p-' + tab.dataset.tab;
    RENDER[tab.dataset.tab]();
    return;
  }
  const btn = ev.target.closest('[data-set]');
  if (btn && !btn.disabled) {
    const k = btn.dataset.set, v = btn.dataset.val;
    if (k === 'zone') { shapeState.zone = Number(v); renderShape(); }
    else if (k === 'camp' || k === 'phase' || k === 'layer') {
      shapeState[k] = v;
      if (k === 'camp' || k === 'phase') {
        const blk = DATA.shape360.campaigns[shapeState.camp].phases[shapeState.phase];
        if (!blk.grids[shapeState.zone]) {
          const first = blk.grids.findIndex(Boolean);
          if (first >= 0) shapeState.zone = first;
        }
      }
      renderShape();
    }
    else if (k === 'pcamp') { playerState.camp = v; renderPlayers(); }
    else if (k === 'pathcomp') { pathState.comp = v; renderPathway(); }
    return;
  }
  const th = ev.target.closest('th[data-sort]');
  if (th) {
    const k = th.dataset.sort;
    if (playerState.sort === k) playerState.desc = !playerState.desc;
    else { playerState.sort = k; playerState.desc = k !== 'name'; }
    renderPlayers();
  }
});

renderCampaigns();
"""

if __name__ == "__main__":
    build()
