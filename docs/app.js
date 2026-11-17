// LME Metals Monitor 画面ロジック（ビルド不要の素のJavaScript）
"use strict";

const PERIODS = [
  { key: "1w", label: "1W", days: 7 },
  { key: "1m", label: "1M", months: 1 },
  { key: "1y", label: "1Y", months: 12 },
  { key: "3y", label: "3Y", months: 36 },
  { key: "5y", label: "5Y", months: 60 },
];
const CHANGE_KEYS = ["1d", "1w", "1m", "1y", "3y", "5y"];

const state = { data: null, metal: "copper", period: "1y", chart: null };

// ---------- 表示用の整形 ----------
const fmtPrice = (v) =>
  v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

function fmtChange(v) {
  if (v == null) return { text: "—", cls: "na" };
  if (v > 0) return { text: `▲${v.toFixed(2)}%`, cls: "up" };
  if (v < 0) return { text: `▼${Math.abs(v).toFixed(2)}%`, cls: "down" };
  return { text: "0.00%", cls: "flat" };
}

function fmtDateJst(iso) {
  const d = new Date(iso);
  const p = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).formatToParts(d);
  const g = (t) => p.find((x) => x.type === t).value;
  return `${g("month")}/${g("day")} ${g("hour")}:${g("minute")}`;
}

// 文字列はすべて textContent で入れる（ニュース本文は外部由来なのでHTMLとして扱わない）
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c) node.append(c);
  return node;
}

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------- 価格一覧 ----------
function renderTable() {
  const tbody = document.getElementById("price-rows");
  tbody.replaceChildren();
  for (const m of state.data.metals) {
    const nameCell = el("th", { scope: "row", class: "col-metal" },
      el("span", { class: "metal-name", text: m.name_ja }),
      el("span", { class: "metal-en", text: m.name_en }));
    const row = el("tr", { "data-metal": m.key, tabindex: "0" }, nameCell,
      el("td", { class: "price", text: fmtPrice(m.cash) }),
      el("td", { text: fmtPrice(m.three_month) }));
    for (const k of CHANGE_KEYS) {
      const c = fmtChange(m.changes[k]);
      row.append(el("td", { class: `chg ${c.cls}`, text: c.text }));
    }
    const choose = () => {
      selectMetal(m.key);
      document.getElementById("chart-section").scrollIntoView({ behavior: "smooth", block: "start" });
    };
    row.addEventListener("click", choose);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter") choose(); });
    tbody.append(row);
  }
}

// ---------- チャート ----------
function renderControls() {
  const tabs = document.getElementById("metal-tabs");
  for (const m of state.data.metals) {
    const b = el("button", { class: "tab", role: "tab", type: "button", "data-metal": m.key, text: m.name_ja });
    b.addEventListener("click", () => selectMetal(m.key));
    tabs.append(b);
  }
  const periods = document.getElementById("period-buttons");
  for (const p of PERIODS) {
    const b = el("button", { class: "period", type: "button", "data-period": p.key, text: p.label });
    b.addEventListener("click", () => { state.period = p.key; update(); });
    periods.append(b);
  }
}

function selectMetal(key) {
  state.metal = key;
  update();
}

// 期間の開始日（最新日から暦でさかのぼる）
function periodStart(lastIso, period) {
  const d = new Date(lastIso + "T00:00:00Z");
  if (period.days) d.setUTCDate(d.getUTCDate() - period.days);
  else {
    const day = d.getUTCDate();
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() - period.months);
    const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
    d.setUTCDate(Math.min(day, last));
  }
  return d.toISOString().slice(0, 10);
}

function sliceSeries() {
  const s = state.data.chart[state.metal];
  const period = PERIODS.find((p) => p.key === state.period);
  const start = periodStart(s.dates[s.dates.length - 1], period);
  // 基準日以前で最も近い営業日から表示する（騰落率の計算ルールと揃える）
  let i = s.dates.findIndex((d) => d > start);
  if (i < 0) i = s.dates.length - 1;
  if (i > 0 && s.dates[i - 1] <= start) i -= 1;
  return { dates: s.dates.slice(i), values: s.cash.slice(i) };
}

function renderSummary(series) {
  const metal = state.data.metals.find((m) => m.key === state.metal);
  const first = series.values[0];
  const last = series.values[series.values.length - 1];
  const chg = fmtChange(first ? Math.round((last / first - 1) * 10000) / 100 : null);
  const hi = Math.max(...series.values);
  const lo = Math.min(...series.values);
  const box = document.getElementById("chart-summary");
  box.replaceChildren(
    el("div", { class: "sub", text: `${metal.name_ja}（現物, USD/t）` }),
    el("div", {},
      el("span", { class: "big", text: fmtPrice(last) }), " ",
      el("span", { class: `chg ${chg.cls}`, text: `${chg.text}` })),
    el("div", { class: "sub" },
      el("span", { class: "nowrap", text: `期間 ${series.dates[0]} 〜 ${series.dates[series.dates.length - 1]}` }), "　",
      el("span", { class: "nowrap", text: `高値 ${fmtPrice(hi)}・安値 ${fmtPrice(lo)}` })),
  );
}

// ホバー位置に縦線を引くプラグイン
const crosshair = {
  id: "crosshair",
  afterDatasetsDraw(chart) {
    const active = chart.tooltip?.getActiveElements?.() || [];
    if (!active.length) return;
    const { ctx, chartArea } = chart;
    const x = active[0].element.x;
    ctx.save();
    ctx.strokeStyle = cssVar("--text-3");
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.stroke();
    ctx.restore();
  },
};

function tickLabel(iso) {
  const [y, m, d] = iso.split("-");
  return ["1w", "1m"].includes(state.period) ? `${+m}/${+d}` : `${y}/${m}`;
}

function renderChart(series) {
  const color = cssVar("--accent");
  const textColor = cssVar("--text-3");
  const grid = cssVar("--grid");
  const surface = cssVar("--surface");
  const few = series.values.length <= 31;
  // 目盛りラベルが重ならないよう、チャート幅に応じて数を決める（1ラベル約80px）
  const width = document.querySelector(".chart-box").clientWidth;
  const maxTicks = Math.max(3, Math.min(few ? 7 : 6, Math.floor((width - 60) / 80)));

  const config = {
    type: "line",
    data: {
      labels: series.dates,
      datasets: [{
        data: series.values,
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        pointRadius: few ? 3 : 0,
        pointHoverRadius: 5,
        pointBorderColor: surface,
        pointHoverBorderWidth: 2,
        tension: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      layout: { padding: { right: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          backgroundColor: cssVar("--text"),
          titleColor: surface,
          bodyColor: surface,
          padding: 8,
          callbacks: {
            title: (items) => items[0].label,
            label: (item) => `${fmtPrice(item.parsed.y)} USD/t`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: grid },
          ticks: {
            color: textColor, maxRotation: 0, autoSkip: true, autoSkipPadding: 12, maxTicksLimit: maxTicks,
            callback(value) { return tickLabel(this.getLabelForValue(value)); },
          },
        },
        y: {
          position: "right",
          grid: { color: grid },
          border: { display: false },
          ticks: { color: textColor, maxTicksLimit: 6, callback: (v) => v.toLocaleString("en-US") },
        },
      },
    },
    plugins: [crosshair],
  };

  if (state.chart) state.chart.destroy();
  state.chart = new Chart(document.getElementById("price-chart"), config);
}

function update() {
  for (const b of document.querySelectorAll(".tab")) {
    b.setAttribute("aria-selected", String(b.dataset.metal === state.metal));
  }
  for (const b of document.querySelectorAll(".period")) {
    b.setAttribute("aria-pressed", String(b.dataset.period === state.period));
  }
  for (const r of document.querySelectorAll("#price-rows tr")) {
    r.classList.toggle("selected", r.dataset.metal === state.metal);
  }
  const series = sliceSeries();
  renderSummary(series);
  if (window.Chart) renderChart(series);
}

// ---------- ニュース ----------
function renderNews(listId, items) {
  const list = document.getElementById(listId);
  list.replaceChildren();
  if (!items.length) {
    list.append(el("li", { class: "empty", text: "直近の記事はありません" }));
    return;
  }
  for (const a of items) {
    const high = a.importance === "高";
    list.append(el("li", { class: `news-item${high ? " high" : ""}` },
      el("div", { class: "news-tags" },
        el("span", { class: `tag${high ? " high" : ""}`, text: `重要度 ${a.importance}` }),
        el("span", { class: "tag", text: a.category })),
      el("h3", { text: a.title_ja }),
      el("p", { text: a.summary_ja }),
      el("div", { class: "news-foot" },
        el("span", { text: a.source }),
        el("span", { text: fmtDateJst(a.published) }),
        el("a", { href: a.link, target: "_blank", rel: "noopener noreferrer", title: a.title_en, text: "元記事（英語）↗" }))));
  }
}

// ---------- 起動 ----------
async function main() {
  try {
    const res = await fetch("data/site_data.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
  } catch (e) {
    document.querySelector("main").prepend(el("p", { class: "error", text: `データを読み込めませんでした（${e.message}）` }));
    return;
  }
  document.getElementById("as-of").textContent = state.data.as_of;
  document.getElementById("generated-at").textContent = state.data.generated_at;
  renderTable();
  renderControls();
  update();
  renderNews("news-nickel", state.data.news.nickel);
  renderNews("news-nonferrous", state.data.news.nonferrous);

  // ライト／ダークが切り替わったらチャートの色を塗り直す
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", update);
  // 画面幅が変わったら目盛りの数を計算し直す
  let resizeTimer;
  addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(update, 200); });
}

main();
