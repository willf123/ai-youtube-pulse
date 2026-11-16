// Step 8 — Build the weekly slide deck (.pptx) from deck_data.json with pptxgenjs.
// Native (editable) charts, dark "premium" theme, thumbnails from the run's thumbs/ folder.
//
// Usage: node tools/build_deck.js <run_dir>      -> writes <run_dir>/deck.pptx
"use strict";
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("./lib/apply_theme.js");

const runDir = process.argv[2];
if (!runDir) { console.error("usage: node tools/build_deck.js <run_dir>"); process.exit(1); }
const D = JSON.parse(fs.readFileSync(path.join(runDir, "deck_data.json"), "utf8"));
const M = D.metrics, I = D.insights;

// ------------------------------------------------------------------ design tokens
const C = {
  bg: "0B0F1A", card: "141A29", card2: "1C2436", line: "2A3348",
  text: "F3F4F8", muted: "9AA3B8", faint: "6B7489",
  accent: "9085E9", accentSoft: "2B2752", blue: "3987E5", pos: "199E70", neg: "E66767", warn: "C98500",
};
const THEME = {
  name: "AI YouTube Pulse", headFontFace: "Calibri", bodyFontFace: "Calibri",
  colors: { dk1: C.bg, lt1: C.text, dk2: C.card, lt2: C.muted, accent1: C.accent, accent2: C.blue,
            accent3: C.pos, accent4: C.warn, accent5: "D55181", accent6: C.neg, hlink: C.accent, folHlink: C.muted },
};
const W = 13.333, H = 7.5, MX = 0.6;           // LAYOUT_WIDE canvas & side margin
const CONTENT_Y = 1.95, CONTENT_H = 4.95;       // content band below title + subtitle
const CHART_H = CONTENT_H - 0.4, CAPTION_Y = CONTENT_Y + CONTENT_H - 0.3;  // chart + caption under it
const headroom = vals => Math.max(...vals.filter(v => v !== null && v !== undefined), 0) * 1.18 || undefined;

const notes = Object.fromEntries((I.slide_notes || []).map(n => [n.key, n]));
const runDate = new Date(M.run_date + "T12:00:00");
const dateLabel = runDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

// ------------------------------------------------------------------ helpers
const fmt = n => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "K";
  return String(Math.round(n));
};
const pct = (x, d = 0) => (x === null || x === undefined) ? "—" : (x * 100).toFixed(d) + "%";
const trunc = (s, n) => !s ? "" : (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const exists = p => p && fs.existsSync(p);
const noteFor = (key, fallbackTitle) => notes[key] || { title: fallbackTitle, so_what: "" };

function card(slide, x, y, w, h, fill = C.card, name = "card") {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill }, objectName: name });
}
function chip(slide, text, x, y, opts = {}) {
  const w = opts.w || Math.max(0.9, 0.11 * text.length + 0.35);
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.32, rectRadius: 0.16,
    fill: { color: opts.fill || C.accentSoft }, line: { color: opts.fill || C.accentSoft } });
  slide.addText(text, { x, y, w, h: 0.32, fontSize: 10.5, bold: true, color: opts.color || C.accent,
    align: "center", valign: "middle", margin: 0, isTextBox: true });
  return w;
}
function numberBadge(slide, n, x, y, d = 0.5, fill = C.accent) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  slide.addText(String(n), { x, y, w: d, h: d, fontSize: d > 0.45 ? 16 : 12, bold: true, color: C.bg,
    align: "center", valign: "middle", margin: 0, isTextBox: true });
}
function thumb(slide, p, x, y, w, h) {
  if (exists(p)) slide.addImage({ path: p, x, y, w, h, sizing: { type: "cover", w, h } });
  else {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: C.card2 }, line: { color: C.line } });
    slide.addText("▶", { x, y, w, h, fontSize: 16, color: C.faint, align: "center", valign: "middle", isTextBox: true });
  }
}
function avatar(slide, p, x, y, d, label) {
  if (exists(p)) slide.addImage({ path: p, x, y, w: d, h: d, rounding: true });
  else {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: C.card2 }, line: { color: C.line } });
    slide.addText((label || "?").slice(0, 1).toUpperCase(), { x, y, w: d, h: d, fontSize: 14, bold: true,
      color: C.muted, align: "center", valign: "middle", margin: 0, isTextBox: true });
  }
}
// Shared chart styling so every chart reads the same
function chartBase(extra = {}) {
  return Object.assign({
    showLegend: false, showTitle: false,
    catAxisLabelColor: C.muted, valAxisLabelColor: C.muted,
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: C.line, size: 0.75 }, catGridLine: { style: "none" },
    catAxisLineShow: false, valAxisLineShow: false,
    showValue: true, dataLabelColor: C.text, dataLabelFontSize: 10.5, dataLabelFontFace: "+mn-lt",
    barGapWidthPct: 55,
  }, extra);
}
function contentSlide(section, key, fallbackTitle, kicker) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  const n = noteFor(key, fallbackTitle);
  s.addText(kicker.toUpperCase(), { placeholder: "kicker" });
  s.addText(n.title || fallbackTitle, { placeholder: "title" });
  if (n.so_what) s.addText(n.so_what, { placeholder: "subtitle" });
  return s;
}

// ------------------------------------------------------------------ presentation + layouts
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = `${D.subject_prefix} — ${dateLabel}`;
pres.author = "YouTube Analysis pipeline";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.bg },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: MX, y: 0.32, w: 9, h: 0.3, fontSize: 11, bold: true,
        color: C.accent, charSpacing: 2, margin: 0, valign: "middle" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.62, w: W - 2 * MX, h: 0.7, fontSize: 30, bold: true,
        color: C.text, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { placeholder: { options: { name: "subtitle", type: "body", x: MX, y: 1.32, w: W - 2 * MX, h: 0.48, fontSize: 14,
        color: C.muted, italic: true, margin: 0, valign: "top" }, text: "" } },
    { text: { text: `${D.subject_prefix}  ·  ${dateLabel}${M.is_demo ? "  ·  SAMPLE DATA" : ""}`, options: { x: MX, y: 7.08, w: 6, h: 0.25, fontSize: 9,
        color: C.faint, margin: 0 } } },
  ],
  slideNumber: { x: W - MX - 0.5, y: 7.08, w: 0.5, h: 0.25, fontSize: 9, color: C.faint, align: "right" },
});
pres.defineSlideMaster({ title: "COVER", background: { color: C.bg }, objects: [] });

// ================================================================== 1. Cover
pres.addSection({ title: "Overview" });
{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: "Overview" });
  s.addShape(pres.shapes.OVAL, { x: 8.6, y: -1.6, w: 6.6, h: 6.6, fill: { color: C.accent, transparency: 82 }, line: { color: C.bg, transparency: 100 } });
  s.addShape(pres.shapes.OVAL, { x: 10.4, y: 3.3, w: 3.8, h: 3.8, fill: { color: C.blue, transparency: 85 }, line: { color: C.bg, transparency: 100 } });
  s.addText(`${D.subject_prefix.toUpperCase()}  ·  WEEK OF ${dateLabel.toUpperCase()}`, { x: MX, y: 1.2, w: 9, h: 0.35,
    fontSize: 13, bold: true, color: C.accent, charSpacing: 2, margin: 0, isTextBox: true });
  if (M.is_demo) chip(s, "SAMPLE DATA · NOT REAL RESULTS", MX, 0.6, { w: 3.3, fill: "3A2A12", color: C.warn });
  s.addText(I.deck_headline, { x: MX, y: 1.7, w: 8.4, h: 2.0, fontSize: 42, bold: true, color: C.text, margin: 0, valign: "top", isTextBox: true });
  s.addText(I.niche_mood, { x: MX, y: 3.85, w: 8.4, h: 1.1, fontSize: 16, color: C.muted, margin: 0, valign: "top", isTextBox: true });
  const k = M.kpis;
  const stats = [[fmt(k.videos_analyzed), "videos analysed"], [fmt(k.channels_tracked), "channels tracked"],
                 [fmt(k.views_window), "views in window"], [fmt(k.outliers_3x), "3x+ outliers"]];
  stats.forEach(([v, l], i) => {
    const x = MX + i * 2.55;
    card(s, x, 5.45, 2.35, 1.2, C.card);
    s.addText(v, { x: x + 0.2, y: 5.55, w: 2.0, h: 0.6, fontSize: 28, bold: true, color: C.text, margin: 0, isTextBox: true });
    s.addText(l, { x: x + 0.2, y: 6.15, w: 2.0, h: 0.35, fontSize: 12, color: C.muted, margin: 0, isTextBox: true });
  });
}

// ================================================================== 2. Executive summary
{
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Overview" });
  s.addText("EXECUTIVE SUMMARY", { placeholder: "kicker" });
  s.addText("What you need to know this week", { placeholder: "title" });
  s.addText(I.niche_mood, { placeholder: "subtitle" });
  const cw = (W - 2 * MX - 0.3) / 2, ch = 2.3;
  (I.exec_summary || []).slice(0, 4).forEach((t, i) => {
    const x = MX + (i % 2) * (cw + 0.3), y = CONTENT_Y + 0.15 + Math.floor(i / 2) * (ch + 0.3);
    card(s, x, y, cw, ch);
    numberBadge(s, i + 1, x + 0.3, y + 0.3);
    s.addText(t.headline, { x: x + 1.0, y: y + 0.28, w: cw - 1.3, h: 0.6, fontSize: 19, bold: true, color: C.text, margin: 0, valign: "middle", isTextBox: true });
    s.addText(t.detail, { x: x + 1.0, y: y + 0.95, w: cw - 1.3, h: 1.15, fontSize: 14, color: C.muted, margin: 0, valign: "top", isTextBox: true });
  });
}

// ================================================================== 3. KPIs
{
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Overview" });
  const k = M.kpis;
  s.addText("THE NUMBERS", { placeholder: "kicker" });
  s.addText("The niche at a glance", { placeholder: "title" });
  s.addText(`${M.window_days}-day window across ${k.channels_tracked} AI & automation channels. "This week" = uploads from the last ${M.this_week_days} days.`, { placeholder: "subtitle" });
  const wow = k.uploads_prev_week ? (k.uploads_this_week / k.uploads_prev_week - 1) : null;
  const tiles = [
    [fmt(k.uploads_this_week), "uploads this week", wow === null ? "" : `${wow >= 0 ? "▲" : "▼"} ${pct(Math.abs(wow))} vs prior week`, wow === null ? C.muted : (wow >= 0 ? C.pos : C.neg)],
    [fmt(k.views_this_week_uploads), "views on this week's uploads", "", C.muted],
    [fmt(k.median_views_long), "median views per long-form video", "", C.muted],
    [pct(k.median_engagement, 1), "median engagement", "(likes + comments) ÷ views", C.muted],
    [pct(k.shorts_share_uploads), "of uploads are Shorts", "", C.muted],
    [fmt(k.outliers_3x), "videos hit 3x+ their channel norm", "the ones worth studying", C.muted],
  ];
  const tw = (W - 2 * MX - 0.6) / 3, th = 2.25;
  tiles.forEach(([v, l, sub, subColor], i) => {
    const x = MX + (i % 3) * (tw + 0.3), y = CONTENT_Y + 0.15 + Math.floor(i / 3) * (th + 0.3);
    card(s, x, y, tw, th);
    s.addText(v, { x: x + 0.35, y: y + 0.3, w: tw - 0.7, h: 0.95, fontSize: 48, bold: true, color: i === 5 ? C.accent : C.text, margin: 0, isTextBox: true });
    s.addText(l, { x: x + 0.35, y: y + 1.3, w: tw - 0.7, h: 0.4, fontSize: 14, color: C.text, margin: 0, isTextBox: true });
    if (sub) s.addText(sub, { x: x + 0.35, y: y + 1.7, w: tw - 0.7, h: 0.35, fontSize: 11.5, color: subColor, margin: 0, isTextBox: true });
  });
}

// ================================================================== 4. Top 10 this week
pres.addSection({ title: "What's working" });
{
  const s = contentSlide("What's working", "top_week", "This week's biggest videos", "Top 10 this week");
  const vids = (M.top_week || []).slice(0, 10);
  const colW = (W - 2 * MX - 0.3) / 2, rowH = 0.92, gap = 0.08;
  vids.forEach((v, i) => {
    const col = Math.floor(i / 5), row = i % 5;
    const x = MX + col * (colW + 0.3), y = CONTENT_Y + row * (rowH + gap);
    card(s, x, y, colW, rowH);
    s.addText(String(i + 1), { x: x + 0.1, y, w: 0.4, h: rowH, fontSize: 16, bold: true, color: C.accent, align: "center", valign: "middle", margin: 0, isTextBox: true });
    thumb(s, v.thumb_path, x + 0.55, y + 0.1, 1.28, 0.72);
    s.addText([{ text: trunc(v.title, 78), options: { hyperlink: { url: v.url }, color: C.text } }],
      { x: x + 1.98, y: y + 0.07, w: colW - 2.1, h: 0.5, fontSize: 12.5, bold: true, margin: 0, valign: "top", isTextBox: true });
    const meta = `${trunc(v.channel, 26)}  ·  ${fmt(v.views)} views${v.outlier ? `  ·  ${v.outlier}x norm` : ""}${v.is_short ? "  ·  Short" : ""}`;
    s.addText(meta, { x: x + 1.98, y: y + 0.58, w: colW - 2.1, h: 0.28, fontSize: 10.5, color: C.muted, margin: 0, isTextBox: true });
  });
}

// ================================================================== 5. Outliers
{
  const s = contentSlide("What's working", "outliers", "Videos that broke out", "Outliers");
  const o = (M.outliers || []).slice(0, 8);
  if (o.length) {
    s.addChart(pres.charts.BAR, [{ name: "Outlier score", labels: o.map(v => trunc(v.title, 42)), values: o.map(v => v.outlier) }],
      chartBase({ x: MX - 0.1, y: CONTENT_Y, w: 7.6, h: CHART_H, barDir: "bar", chartColors: [C.accent],
        catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, dataLabelPosition: "outEnd",
        dataLabelFormatCode: '0.0"x"', catAxisLabelFontSize: 10.5, valAxisMaxVal: headroom(o.map(v => v.outlier)) }));
  }
  const rx = 7.9, rw = W - MX - rx;
  s.addText("Times its channel's median views", { x: MX, y: CAPTION_Y, w: 7, h: 0.25, fontSize: 10, color: C.faint, margin: 0, isTextBox: true });
  o.slice(0, 3).forEach((v, i) => {
    const y = CONTENT_Y + i * 1.68;
    card(s, rx, y, rw, 1.55);
    thumb(s, v.thumb_path, rx + 0.15, y + 0.15, 2.2, 1.24);
    s.addText(`${v.outlier}x`, { x: rx + 2.5, y: y + 0.12, w: rw - 2.6, h: 0.5, fontSize: 24, bold: true, color: C.accent, margin: 0, isTextBox: true });
    s.addText([{ text: trunc(v.title, 60), options: { hyperlink: { url: v.url }, color: C.text } }],
      { x: rx + 2.5, y: y + 0.62, w: rw - 2.65, h: 0.55, fontSize: 11, bold: true, margin: 0, valign: "top", isTextBox: true });
    s.addText(`${trunc(v.channel, 22)} · ${fmt(v.views)} views`, { x: rx + 2.5, y: y + 1.17, w: rw - 2.65, h: 0.28, fontSize: 10, color: C.muted, margin: 0, isTextBox: true });
  });
}

// ================================================================== 6. Topics
pres.addSection({ title: "Trends" });
{
  const s = contentSlide("Trends", "topics", "Where the views are", "Topics");
  const t = (M.topics || []).filter(x => x.topic !== "Other").slice(0, 10);
  s.addChart(pres.charts.BAR, [{ name: "Views", labels: t.map(x => x.topic), values: t.map(x => x.views) }],
    chartBase({ x: MX - 0.1, y: CONTENT_Y, w: 7.6, h: CHART_H, barDir: "bar", chartColors: [C.accent],
      catAxisOrientation: "maxMin", valAxisHidden: true, valGridLine: { style: "none" }, dataLabelPosition: "outEnd",
      dataLabelFormatCode: '[>=1000000]0.0,,"M";[>=1000]0,"K";0', valAxisMaxVal: headroom(t.map(x => x.views)) }));
  const rx = 7.9, rw = W - MX - rx;
  s.addText("Views on videos published in the window, by topic", { x: MX, y: CAPTION_Y, w: 7, h: 0.25, fontSize: 10, color: C.faint, margin: 0, isTextBox: true });
  t.slice(0, 3).forEach((x, i) => {
    const y = CONTENT_Y + i * 1.68;
    card(s, rx, y, rw, 1.55);
    s.addText(x.topic, { x: rx + 0.25, y: y + 0.15, w: rw - 0.5, h: 0.4, fontSize: 16, bold: true, color: C.text, margin: 0, isTextBox: true });
    s.addText(`${x.videos} videos · ${fmt(x.median_views)} median views · ${x.median_outlier ?? "—"}x median outlier`,
      { x: rx + 0.25, y: y + 0.55, w: rw - 0.5, h: 0.3, fontSize: 11, color: C.accent, margin: 0, isTextBox: true });
    s.addText(`Top: ${trunc(x.top_video, 70)}`, { x: rx + 0.25, y: y + 0.88, w: rw - 0.5, h: 0.55, fontSize: 11, color: C.muted, margin: 0, valign: "top", isTextBox: true });
  });
}

// ================================================================== 7. Momentum
{
  const s = contentSlide("Trends", "momentum", "Rising and cooling topics", "Momentum");
  const t = (M.topics || []).filter(x => x.topic !== "Other" && x.momentum !== null).sort((a, b) => b.momentum - a.momentum);
  const shown = t.length > 10 ? [...t.slice(0, 5), ...t.slice(-5)] : t;
  s.addChart(pres.charts.BAR, [
    { name: "Gaining", labels: shown.map(x => x.topic), values: shown.map(x => Math.max(0, x.momentum)) },
    { name: "Cooling", labels: shown.map(x => x.topic), values: shown.map(x => Math.min(0, x.momentum)) },
  ], chartBase({ x: MX - 0.1, y: CONTENT_Y, w: 7.6, h: CHART_H, barDir: "bar", barGrouping: "stacked", chartColors: [C.pos, C.neg],
    catAxisOrientation: "maxMin", catAxisLabelPos: "low", valAxisHidden: true, valGridLine: { style: "none" },
    dataLabelPosition: "inEnd", dataLabelFormatCode: '+0.0"pt";-0.0"pt";;', showLegend: true, legendPos: "t",
    legendColor: C.muted, legendFontSize: 11, legendFontFace: "+mn-lt" }));
  s.addText("Change in share of daily views: this week's uploads vs earlier in the window (percentage points)",
    { x: MX, y: CAPTION_Y, w: 7.3, h: 0.25, fontSize: 10, color: C.faint, margin: 0, isTextBox: true });
  const rx = 7.9, rw = W - MX - rx;
  const block = (label, items, color, y) => {
    card(s, rx, y, rw, 2.35);
    s.addText(label, { x: rx + 0.25, y: y + 0.15, w: rw - 0.5, h: 0.35, fontSize: 12, bold: true, color, charSpacing: 1, margin: 0, isTextBox: true });
    s.addText(items.map((x, i) => ({ text: `${x.topic}  ${x.momentum > 0 ? "+" : ""}${x.momentum.toFixed(1)}pt`,
      options: { bullet: true, breakLine: i < items.length - 1 } })),
      { x: rx + 0.25, y: y + 0.55, w: rw - 0.5, h: 1.65, fontSize: 14, color: C.text, margin: 0, valign: "top", paraSpaceAfter: 6, isTextBox: true });
  };
  block("▲ RISING", t.slice(0, 3), C.pos, CONTENT_Y);
  block("▼ COOLING", t.slice(-3).reverse(), C.neg, CONTENT_Y + 2.55);
}

// ================================================================== 8. Channels
{
  const s = contentSlide("Trends", "channels", "Channels with momentum", "Channels");
  const subMode = M.channel_growth_mode === "subscriber_delta";
  const rows = (M.channels_top_growth || []).slice(0, 8);
  const val = r => subMode ? (r.sub_delta || 0) : (r.views_per_sub || 0);
  const maxV = Math.max(...rows.map(val), 1e-9);
  const rowH = 0.56, lw = 7.6;
  s.addText(subMode ? "New subscribers since last report" : "Views on new uploads ÷ subscribers (punching above their weight)",
    { x: MX, y: CONTENT_Y - 0.05, w: lw, h: 0.28, fontSize: 10.5, color: C.faint, margin: 0, isTextBox: true });
  rows.forEach((r, i) => {
    const y = CONTENT_Y + 0.3 + i * (rowH + 0.04);
    avatar(s, r.thumb_path, MX, y + 0.05, 0.46, r.title);
    s.addText(trunc(r.title, 26), { x: MX + 0.6, y, w: 2.6, h: 0.32, fontSize: 13, bold: true, color: C.text, margin: 0, isTextBox: true });
    s.addText(`${fmt(r.subscribers)} subs · ${r.uploads} uploads`, { x: MX + 0.6, y: y + 0.3, w: 2.6, h: 0.24, fontSize: 10, color: C.muted, margin: 0, isTextBox: true });
    const bx = MX + 3.35, bw = 3.2 * (val(r) / maxV);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: bx, y: y + 0.13, w: Math.max(bw, 0.06), h: 0.3, rectRadius: 0.06, fill: { color: C.accent }, line: { color: C.accent } });
    s.addText(subMode ? `+${fmt(val(r))}` : `${val(r).toFixed(2)}x`, { x: bx + Math.max(bw, 0.06) + 0.1, y: y + 0.1, w: 1.0, h: 0.36, fontSize: 12, bold: true, color: C.text, margin: 0, valign: "middle", isTextBox: true });
  });
  const rx = 8.6, rw = W - MX - rx;
  card(s, rx, CONTENT_Y, rw, CONTENT_H);
  s.addText("MOST VIEWS IN WINDOW", { x: rx + 0.25, y: CONTENT_Y + 0.2, w: rw - 0.5, h: 0.3, fontSize: 11, bold: true, color: C.accent, charSpacing: 1, margin: 0, isTextBox: true });
  (M.channels_top_views || []).slice(0, 7).forEach((r, i) => {
    const y = CONTENT_Y + 0.65 + i * 0.6;
    avatar(s, r.thumb_path, rx + 0.25, y, 0.42, r.title);
    s.addText(trunc(r.title, 22), { x: rx + 0.8, y, w: rw - 2.0, h: 0.42, fontSize: 12.5, color: C.text, margin: 0, valign: "middle", isTextBox: true });
    s.addText(fmt(r.views_window), { x: rx + rw - 1.2, y, w: 0.95, h: 0.42, fontSize: 12.5, bold: true, color: C.text, align: "right", margin: 0, valign: "middle", isTextBox: true });
  });
}

// ================================================================== 9. Formats
{
  const s = contentSlide("Trends", "formats", "Shorts vs long-form", "Formats");
  const f = M.formats || [];
  s.addChart(pres.charts.DOUGHNUT, [{ name: "View share", labels: f.map(x => x.format), values: f.map(x => x.views) }], {
    x: MX, y: CONTENT_Y, w: 4.6, h: CONTENT_H - 0.3, holeSize: 62, chartColors: [C.accent, C.blue],
    showPercent: true, showValue: false, showLegend: true, legendPos: "b", legendColor: C.muted, legendFontSize: 12, legendFontFace: "+mn-lt",
    dataLabelColor: C.text, dataLabelFontSize: 13, dataLabelFontFace: "+mn-lt", showTitle: false,
  });
  s.addText("Share of total views", { x: MX, y: CONTENT_Y + CONTENT_H - 0.25, w: 4.6, h: 0.25, fontSize: 10, color: C.faint, align: "center", margin: 0, isTextBox: true });
  const metrics = [["Uploads", x => fmt(x.videos)], ["Median views", x => fmt(x.median_views)],
                   ["Median views / day", x => fmt(x.median_vpd)], ["Median engagement", x => pct(x.median_engagement, 1)]];
  const cx = 5.6, cw = (W - MX - cx - 0.3) / 2;
  f.forEach((x, i) => {
    const X = cx + i * (cw + 0.3);
    card(s, X, CONTENT_Y, cw, CONTENT_H);
    s.addShape(pres.shapes.OVAL, { x: X + 0.3, y: CONTENT_Y + 0.33, w: 0.22, h: 0.22, fill: { color: i === 0 ? C.accent : C.blue }, line: { color: i === 0 ? C.accent : C.blue } });
    s.addText(x.format, { x: X + 0.62, y: CONTENT_Y + 0.22, w: cw - 0.9, h: 0.45, fontSize: 20, bold: true, color: C.text, margin: 0, valign: "middle", isTextBox: true });
    metrics.forEach(([lab, fn], j) => {
      const y = CONTENT_Y + 0.95 + j * 0.95;
      s.addText(fn(x), { x: X + 0.3, y, w: cw - 0.6, h: 0.55, fontSize: 28, bold: true, color: C.text, margin: 0, isTextBox: true });
      s.addText(lab, { x: X + 0.3, y: y + 0.52, w: cw - 0.6, h: 0.3, fontSize: 12, color: C.muted, margin: 0, isTextBox: true });
    });
  });
}

// ================================================================== 10. Hooks (data)
pres.addSection({ title: "Packaging" });
{
  const s = contentSlide("Packaging", "hooks", "Which title angles win", "Hooks & titles");
  const h = (M.hooks || []).slice(0, 9);
  if (h.length) s.addChart(pres.charts.BAR, [{ name: "Median outlier", labels: h.map(x => x.hook_type), values: h.map(x => x.median_outlier) }],
    chartBase({ x: MX - 0.1, y: CONTENT_Y, w: 6.9, h: CHART_H, barDir: "bar", chartColors: [C.accent], catAxisOrientation: "maxMin",
      valAxisHidden: true, valGridLine: { style: "none" }, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.00"x"',
      valAxisMinVal: 0, valAxisMaxVal: headroom(h.map(x => x.median_outlier)) }));
  s.addText("Median outlier score by title angle (long-form; 1.0x = channel norm)", { x: MX, y: CAPTION_Y, w: 7, h: 0.25, fontSize: 10, color: C.faint, margin: 0, isTextBox: true });
  const rx = 7.7, rw = W - MX - rx;
  card(s, rx, CONTENT_Y, rw, CONTENT_H);
  s.addText("TITLE FEATURES: LIFT IN OUTLIER SCORE", { x: rx + 0.25, y: CONTENT_Y + 0.2, w: rw - 0.5, h: 0.3, fontSize: 11, bold: true, color: C.accent, charSpacing: 1, margin: 0, isTextBox: true });
  const tf = (M.title_features || []);
  const showTf = tf.length > 6 ? [...tf.slice(0, 3), ...tf.slice(-3)] : tf;
  showTf.forEach((x, i) => {
    const y = CONTENT_Y + 0.65 + i * 0.68;
    const up = (x.lift || 0) >= 0;
    s.addText(`${up ? "+" : ""}${Math.round((x.lift || 0) * 100)}%`, { x: rx + 0.25, y, w: 1.15, h: 0.5, fontSize: 20, bold: true, color: up ? C.pos : C.neg, margin: 0, valign: "middle", isTextBox: true });
    s.addText([{ text: x.feature, options: { bold: true, color: C.text, breakLine: true } },
               { text: `${(+x.with).toFixed(2)}x with vs ${(+x.without).toFixed(2)}x without · n=${x.n_with}`, options: { color: C.muted, fontSize: 10.5 } }],
      { x: rx + 1.45, y, w: rw - 1.7, h: 0.58, fontSize: 13, margin: 0, valign: "middle", isTextBox: true });
  });
}

// ================================================================== 11. Hook lessons
{
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Packaging" });
  s.addText("PACKAGING PLAYBOOK", { placeholder: "kicker" });
  s.addText("Patterns the top videos are using", { placeholder: "title" });
  s.addText(`Drawn from the titles and opening ${I.sampled_transcripts || 0} transcripts of this week's best performers`, { placeholder: "subtitle" });
  const cw = (W - 2 * MX - 0.3) / 2, ch = 2.3;
  (I.hook_lessons || []).slice(0, 4).forEach((h, i) => {
    const x = MX + (i % 2) * (cw + 0.3), y = CONTENT_Y + 0.1 + Math.floor(i / 2) * (ch + 0.3);
    card(s, x, y, cw, ch);
    chip(s, h.pattern, x + 0.3, y + 0.28);
    s.addText(`"${trunc(h.example_title, 90)}"`, { x: x + 0.3, y: y + 0.75, w: cw - 0.6, h: 0.75, fontSize: 15, italic: true, bold: true, color: C.text, margin: 0, valign: "top", isTextBox: true });
    s.addText(h.why_it_works, { x: x + 0.3, y: y + 1.5, w: cw - 0.6, h: 0.65, fontSize: 13, color: C.muted, margin: 0, valign: "top", isTextBox: true });
  });
}

// ================================================================== 12. Timing
{
  const s = contentSlide("Packaging", "timing", "Length and timing", "Length & timing");
  const d = (M.durations || []);
  s.addChart(pres.charts.BAR, [{ name: "Median outlier", labels: d.map(x => x.bucket), values: d.map(x => x.median_outlier || 0) }],
    chartBase({ x: MX - 0.1, y: CONTENT_Y + 0.3, w: 5.6, h: CONTENT_H - 0.6, barDir: "col", chartColors: [C.accent],
      valAxisHidden: true, valGridLine: { style: "none" }, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.00"x"',
      valAxisMinVal: 0, valAxisMaxVal: headroom(d.map(x => x.median_outlier)) }));
  s.addText("VIDEO LENGTH → MEDIAN OUTLIER", { x: MX, y: CONTENT_Y - 0.05, w: 5.4, h: 0.3, fontSize: 11, bold: true, color: C.accent, charSpacing: 1, margin: 0, isTextBox: true });
  s.addText(d.map(x => `${x.bucket}: n=${x.videos}`).join("   "), { x: MX, y: CONTENT_Y + CONTENT_H - 0.25, w: 5.5, h: 0.25, fontSize: 9.5, color: C.faint, margin: 0, isTextBox: true });

  // heatmap: day × 4h block, sequential single hue (violet), empty = too few videos
  const hm = M.heatmap, hx = 6.75, hy = CONTENT_Y + 0.55, cw = 0.86, chh = 0.52, g = 0.05;
  s.addText(`PUBLISH TIME → MEDIAN OUTLIER (${M.timezone})`, { x: hx, y: CONTENT_Y - 0.05, w: 6, h: 0.3, fontSize: 11, bold: true, color: C.accent, charSpacing: 1, margin: 0, isTextBox: true });
  const vals = hm.cells.flat().map(c => c.median_outlier).filter(v => v !== null);
  const lo = Math.min(...vals, 1), hi = Math.max(...vals, 1.0001);
  const mix = (a, b, t) => { const p = h => [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
    const A = p(a), B = p(b); return A.map((x, i) => Math.round(x + (B[i] - x) * t).toString(16).padStart(2, "0")).join("").toUpperCase(); };
  hm.blocks.forEach((b, j) => s.addText(b, { x: hx + 0.55 + j * (cw + g), y: hy - 0.3, w: cw, h: 0.25, fontSize: 10, color: C.muted, align: "center", margin: 0, isTextBox: true }));
  hm.days.forEach((dname, i) => {
    s.addText(dname, { x: hx, y: hy + i * (chh + g), w: 0.5, h: chh, fontSize: 11, color: C.muted, valign: "middle", margin: 0, isTextBox: true });
    hm.cells[i].forEach((c, j) => {
      const x = hx + 0.55 + j * (cw + g), y = hy + i * (chh + g);
      const v = c.median_outlier;
      const t = v === null ? 0 : (v - lo) / (hi - lo);
      const fill = v === null ? C.card : mix("2B2752", "B9B1FF", t);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: chh, rectRadius: 0.05, fill: { color: fill }, line: { color: C.bg, width: 0.5 } });
      if (v !== null) s.addText(`${v.toFixed(1)}x`, { x, y, w: cw, h: chh, fontSize: 10.5, bold: true, color: t > 0.55 ? C.bg : C.text, align: "center", valign: "middle", margin: 0, isTextBox: true });
    });
  });
  s.addText("Blank = fewer than 2 videos. Brighter = stronger relative performance.", { x: hx, y: hy + 7 * (chh + g) + 0.02, w: 6, h: 0.25, fontSize: 9.5, color: C.faint, margin: 0, isTextBox: true });
}

// ================================================================== 13. Tools
pres.addSection({ title: "Audience" });
{
  const s = contentSlide("Audience", "tools", "The tools people are watching", "Tools & platforms");
  const t = (M.tools || []).slice(0, 10);
  if (t.length) s.addChart(pres.charts.BAR, [{ name: "Views", labels: t.map(x => x.tool), values: t.map(x => x.views) }],
    chartBase({ x: MX - 0.1, y: CONTENT_Y, w: 7.6, h: CHART_H, barDir: "bar", chartColors: [C.blue], catAxisOrientation: "maxMin",
      valAxisHidden: true, valGridLine: { style: "none" }, dataLabelPosition: "outEnd", dataLabelFormatCode: '[>=1000000]0.0,,"M";[>=1000]0,"K";0',
      valAxisMaxVal: headroom(t.map(x => x.views)) }));
  s.addText("Views on videos centred on each tool/model", { x: MX, y: CAPTION_Y, w: 7, h: 0.25, fontSize: 10, color: C.faint, margin: 0, isTextBox: true });
  const rx = 7.9, rw = W - MX - rx;
  card(s, rx, CONTENT_Y, rw, CONTENT_H);
  s.addText("MOST-COVERED THIS WEEK", { x: rx + 0.25, y: CONTENT_Y + 0.2, w: rw - 0.5, h: 0.3, fontSize: 11, bold: true, color: C.accent, charSpacing: 1, margin: 0, isTextBox: true });
  [...(M.tools || [])].sort((a, b) => b.videos_this_week - a.videos_this_week).slice(0, 6).forEach((x, i) => {
    const y = CONTENT_Y + 0.7 + i * 0.68;
    s.addText(x.tool, { x: rx + 0.25, y, w: rw - 2.0, h: 0.5, fontSize: 15, bold: true, color: C.text, margin: 0, valign: "middle", isTextBox: true });
    s.addText(`${x.videos_this_week} new videos`, { x: rx + rw - 1.85, y, w: 1.6, h: 0.5, fontSize: 12, color: C.muted, align: "right", margin: 0, valign: "middle", isTextBox: true });
  });
}

// ================================================================== 14. Audience pulse
{
  const s = contentSlide("Audience", "audience", "What viewers are saying", "Audience pulse");
  const a = I.audience;
  s.addChart(pres.charts.DOUGHNUT, [{ name: "Sentiment", labels: ["Positive", "Neutral", "Negative"], values: [a.positive_pct, a.neutral_pct, a.negative_pct] }], {
    x: MX, y: CONTENT_Y, w: 3.9, h: 2.9, holeSize: 60, chartColors: [C.pos, "6B7489", C.neg], showPercent: true, showValue: false,
    showLegend: true, legendPos: "r", legendColor: C.muted, legendFontSize: 11, legendFontFace: "+mn-lt",
    dataLabelColor: C.text, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt", showTitle: false,
  });
  s.addText(`Sentiment of ${I.sampled_comments || 0} top comments`, { x: MX, y: CONTENT_Y + 2.9, w: 3.9, h: 0.25, fontSize: 10, color: C.faint, margin: 0, isTextBox: true });
  s.addText(a.mood_summary, { x: MX, y: CONTENT_Y + 3.3, w: 3.9, h: 1.6, fontSize: 14, italic: true, color: C.text, margin: 0, valign: "top", isTextBox: true });
  const rx = 4.85, rw = W - MX - rx;
  const list = (label, items, x, y, w, h, color) => {
    card(s, x, y, w, h);
    s.addText(label, { x: x + 0.25, y: y + 0.18, w: w - 0.5, h: 0.3, fontSize: 11, bold: true, color, charSpacing: 1, margin: 0, isTextBox: true });
    s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })),
      { x: x + 0.25, y: y + 0.55, w: w - 0.5, h: h - 0.7, fontSize: 13, color: C.text, margin: 0, valign: "top", paraSpaceAfter: 5, isTextBox: true });
  };
  list("TOP QUESTIONS", a.top_questions.slice(0, 5), rx, CONTENT_Y, rw, 2.35, C.accent);
  const hw = (rw - 0.3) / 2;
  list("PAIN POINTS", a.pain_points.slice(0, 4), rx, CONTENT_Y + 2.55, hw, 2.4, C.neg);
  list("THEY'RE ASKING FOR", a.requests.slice(0, 4), rx + hw + 0.3, CONTENT_Y + 2.55, hw, 2.4, C.pos);
}

// ================================================================== 15-16. Video ideas
pres.addSection({ title: "Action" });
const ideas = (I.video_ideas || []).slice(0, 8);
[0, 1].forEach(page => {
  const chunk = ideas.slice(page * 4, page * 4 + 4);
  if (!chunk.length) return;
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Action" });
  s.addText("WHAT TO MAKE NEXT", { placeholder: "kicker" });
  s.addText(page === 0 ? "Video ideas backed by this week's data" : "More video ideas", { placeholder: "title" });
  s.addText("Ranked by strength of evidence. Working titles follow the packaging patterns that are winning right now.", { placeholder: "subtitle" });
  const cw = (W - 2 * MX - 0.3) / 2, ch = 2.3;
  chunk.forEach((idea, i) => {
    const n = page * 4 + i + 1;
    const x = MX + (i % 2) * (cw + 0.3), y = CONTENT_Y + 0.1 + Math.floor(i / 2) * (ch + 0.3);
    card(s, x, y, cw, ch);
    numberBadge(s, n, x + 0.25, y + 0.25, 0.42);
    s.addText(idea.title, { x: x + 0.85, y: y + 0.2, w: cw - 1.1, h: 0.62, fontSize: 16, bold: true, color: C.text, margin: 0, valign: "middle", isTextBox: true });
    let cx = x + 0.85;
    cx += chip(s, idea.format, cx, y + 0.9, { fill: idea.format === "Short" ? "16304F" : C.accentSoft, color: idea.format === "Short" ? C.blue : C.accent }) + 0.12;
    chip(s, trunc(idea.topic, 28), cx, y + 0.9, { fill: C.card2, color: C.muted });
    s.addText(idea.angle, { x: x + 0.85, y: y + 1.3, w: cw - 1.1, h: 0.45, fontSize: 13, color: C.text, margin: 0, valign: "top", isTextBox: true });
    s.addText([{ text: "Why now: ", options: { bold: true, color: C.accent } }, { text: idea.why_now, options: { color: C.muted } }],
      { x: x + 0.85, y: y + 1.75, w: cw - 1.1, h: 0.48, fontSize: 11.5, margin: 0, valign: "top", isTextBox: true });
  });
});

// ================================================================== 17. Watch list + method
{
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Action" });
  s.addText("NEXT WEEK", { placeholder: "kicker" });
  s.addText("What to watch", { placeholder: "title" });
  (I.watch_list || []).slice(0, 3).forEach((w, i) => {
    const y = CONTENT_Y + i * 1.05;
    card(s, MX, y, 6.9, 0.9);
    numberBadge(s, i + 1, MX + 0.22, y + 0.2, 0.5);
    s.addText(w, { x: MX + 0.95, y, w: 5.75, h: 0.9, fontSize: 14.5, color: C.text, margin: 0, valign: "middle", isTextBox: true });
  });
  const rx = 7.85, rw = W - MX - rx, k = M.kpis;
  card(s, rx, CONTENT_Y, rw, CONTENT_H, C.card);
  s.addText("HOW THIS REPORT WORKS", { x: rx + 0.25, y: CONTENT_Y + 0.2, w: rw - 0.5, h: 0.3, fontSize: 11, bold: true, color: C.accent, charSpacing: 1, margin: 0, isTextBox: true });
  const method = [
    `${k.videos_analyzed} in-niche videos from ${k.channels_tracked} channels, published in the last ${M.window_days} days (YouTube Data API).`,
    `${k.videos_filtered_off_niche} off-topic videos removed by an AI relevance check.`,
    "Outlier score = a video's views ÷ the median views of that channel's same-format videos in the window.",
    "Momentum = change in a topic's share of daily views between this week's uploads and earlier ones.",
    `Topics, hooks and tools were tagged by Claude; insights drew on ${I.sampled_transcripts || 0} transcripts and ${I.sampled_comments || 0} comments.`,
    "All figures are computed in code; the AI writes commentary only.",
  ];
  s.addText(method.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < method.length - 1 } })),
    { x: rx + 0.25, y: CONTENT_Y + 0.6, w: rw - 0.5, h: CONTENT_H - 0.8, fontSize: 12, color: C.muted, margin: 0, valign: "top", paraSpaceAfter: 6, isTextBox: true });
}

// ------------------------------------------------------------------ write + theme
(async () => {
  const outFile = path.join(runDir, "deck.pptx");
  await pres.writeFile({ fileName: outFile });
  await applyTheme(outFile, THEME);
  console.log("Deck written:", outFile);
})().catch(e => { console.error(e); process.exit(1); });
