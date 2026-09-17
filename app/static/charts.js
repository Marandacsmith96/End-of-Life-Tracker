/* Charts: honest about uncertainty. Raw points always visible; smoothed line
   only where the 7-day window has enough observations; lighter when data is limited. */
(function () {
  if (typeof Chart === "undefined") return;
  var css = getComputedStyle(document.documentElement);
  var v = function (name, fallback) { return css.getPropertyValue(name).trim() || fallback; };
  var SERIES = v("--series-1", "#3d64c4"), MUTED = v("--muted", "#5c6b84"), GRID = v("--border", "#dfe5f0"),
      FAINT = v("--faint", "#9aa7bd"), INK = v("--text", "#1d2637"),
      GOOD = v("--good", "#2f7d5b"), MIXED = v("--mixed", "#8a6d1f"), BAD = v("--bad", "#b6485f");
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = MUTED;

  function d(iso) { return new Date(iso + "T00:00:00"); }
  function fmt(iso, long) {
    return d(iso).toLocaleDateString(undefined, long ? { weekday: "short", month: "long", day: "numeric", year: "numeric" } : { month: "short", day: "numeric" });
  }
  /* Vertical event markers drawn behind the data. */
  var eventLines = {
    id: "eventLines",
    beforeDatasetsDraw: function (chart, _args, opts) {
      var events = opts.events || [];
      if (!events.length) return;
      var x = chart.scales.x, area = chart.chartArea, ctx = chart.ctx;
      ctx.save();
      var sorted = events.slice().sort(function (a, b) { return a.date < b.date ? -1 : 1; });
      var lastPx = -Infinity, row = 0;
      sorted.forEach(function (ev) {
        var px = x.getPixelForValue(d(ev.date).getTime());
        if (px < area.left || px > area.right) return;
        ctx.strokeStyle = FAINT; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(px, area.top); ctx.lineTo(px, area.bottom); ctx.stroke();
        ctx.setLineDash([]);
        row = (px - lastPx < 140) ? (row + 1) % 3 : 0;   // stagger labels that would collide
        lastPx = px;
        var text = ev.title.length > 22 ? ev.title.slice(0, 21) + "…" : ev.title;
        ctx.font = "600 10px " + Chart.defaults.font.family; ctx.textAlign = "left";
        var w = ctx.measureText(text).width, ty = area.top + 10 + row * 12;
        ctx.fillStyle = "rgba(255,255,255,.85)"; ctx.fillRect(px + 2, ty - 9, w + 4, 12);
        ctx.fillStyle = MUTED; ctx.fillText(text, px + 4, ty);
      });
      ctx.restore();
    }
  };
  Chart.register(eventLines);

  /* A linear axis over epoch milliseconds: no date adapter needed, and gaps
     between logged days stay visible as gaps. */
  var DAY = 864e5;
  function timeAxis(startIso, endIso) {
    var span = Math.max(1, (d(endIso) - d(startIso)) / DAY);
    var stepDays = span > 200 ? 30 : span > 60 ? 14 : span > 20 ? 7 : span > 8 ? 2 : 1;
    return {
      type: "linear", min: d(startIso).getTime() - DAY / 2, max: d(endIso).getTime() + DAY / 2,
      grid: { display: false },
      ticks: { maxRotation: 0, stepSize: stepDays * DAY, includeBounds: false, maxTicksLimit: 9,
        callback: function (val) { return new Date(val).toLocaleDateString(undefined, { month: "short", day: "numeric" }); } }
    };
  }
  function yAxis(max, step) {
    return { min: 0, max: max, grid: { color: GRID, drawTicks: false }, border: { display: false }, ticks: { stepSize: step, padding: 6 } };
  }
  function tooltip(extra) {
    return Object.assign({ backgroundColor: "#fff", titleColor: INK, bodyColor: INK, borderColor: GRID, borderWidth: 1, padding: 10, displayColors: false,
      callbacks: { title: function (items) { return items.length ? fmt(items[0].raw.iso, true) : ""; } } }, extra || {});
  }
  function pts(dates, values) { return dates.map(function (iso, i) { return { x: d(iso).getTime(), y: values[i], iso: iso }; }); }

  function scoreChart(el, s, opts) {
    opts = opts || {};
    var limited = s.sufficiency && s.sufficiency !== "adequate";
    var datasets = [
      { type: "scatter", label: "Daily score", data: pts(s.dates, s.values), backgroundColor: "rgba(61,100,196,.45)", borderColor: "rgba(61,100,196,.45)", pointRadius: s.dates.length > 120 ? 2 : 3.5, pointHoverRadius: 6, order: 2 },
      { type: "line", label: "7-day average", data: pts(s.dates, s.smoothed), borderColor: limited ? "rgba(61,100,196,.4)" : SERIES, borderWidth: limited ? 1.5 : 2.5, pointRadius: 0, pointHoverRadius: 0, tension: 0.25, spanGaps: false, order: 1 }
    ];
    var base = s.baseline && (typeof s.baseline === "object" ? s.baseline.value : s.baseline);
    if (base !== null && base !== undefined) {
      datasets.push({ type: "line", label: "Owner-estimated baseline", data: [{ x: d(s.start).getTime(), y: base }, { x: d(s.end).getTime(), y: base }], borderColor: FAINT, borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 0, order: 3 });
    }
    new Chart(el, {
      data: { datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, parsing: false, normalized: true,
        interaction: { mode: "nearest", intersect: false },
        plugins: {
          legend: { display: false },
          eventLines: { events: s.events || [] },
          tooltip: tooltip({ callbacks: {
            title: function (items) { return items.length && items[0].raw.iso ? fmt(items[0].raw.iso, true) : ""; },
            label: function (item) {
              if (item.dataset.label === "Owner-estimated baseline") return "Owner-estimated baseline " + item.parsed.y.toFixed(1);
              if (item.parsed.y === null) return null;
              return item.dataset.label + ": " + item.parsed.y.toFixed(item.dataset.type === "scatter" && opts.integer ? 0 : 1) + " / 10";
            } } })
        },
        scales: { x: timeAxis(s.start, s.end), y: yAxis(10, opts.spark ? 5 : 2) }
      }
    });
  }

  function sparkChart(el, s) {
    var base = s.baseline;
    var datasets = [
      { type: "scatter", data: pts(s.dates, s.values), backgroundColor: "rgba(61,100,196,.35)", pointRadius: 2, pointHoverRadius: 4, order: 2 },
      { type: "line", data: pts(s.dates, s.smoothed), borderColor: SERIES, borderWidth: 2, pointRadius: 0, tension: 0.25, spanGaps: false, order: 1 }
    ];
    var parent = el.closest("[data-series]");
    var range = JSON.parse(parent.parentElement.closest("section").querySelector("[data-chart=overall]") ? parent.parentElement.closest("section").querySelector("[data-chart=overall]").dataset.series : "{}");
    var start = s.dates[0] || (range.start), end = s.dates[s.dates.length - 1] || range.end;
    if (window.__qolRange) { start = window.__qolRange.start; end = window.__qolRange.end; }
    if (base !== null && base !== undefined) datasets.push({ type: "line", data: [{ x: d(start).getTime(), y: base }, { x: d(end).getTime(), y: base }], borderColor: FAINT, borderWidth: 1, borderDash: [4, 4], pointRadius: 0, order: 3 });
    new Chart(el, { data: { datasets: datasets }, options: {
      responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
      plugins: { legend: { display: false }, tooltip: tooltip({ callbacks: { label: function (i) { return i.parsed.y === null ? null : i.parsed.y.toFixed(i.dataset.type === "scatter" ? 0 : 1); } } }) },
      scales: { x: Object.assign(timeAxis(start, end), { ticks: { display: false } }), y: yAxis(10, 5) }
    } });
  }

  function weeksChart(el, weeks) {
    var labels = weeks.map(function (w) { return fmt(w.week); });
    new Chart(el, { type: "bar", data: { labels: labels, datasets: [
      { label: "Good", data: weeks.map(function (w) { return w.good; }), backgroundColor: GOOD, borderRadius: 3 },
      { label: "Mixed", data: weeks.map(function (w) { return w.mixed; }), backgroundColor: MIXED, borderRadius: 3 },
      { label: "Bad", data: weeks.map(function (w) { return w.bad; }), backgroundColor: BAD, borderRadius: 3 }
    ] }, options: { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: true, position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } }, tooltip: tooltip({ callbacks: { title: function (items) { return "Week of " + items[0].label; } } }) },
      scales: { x: { stacked: true, grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } }, y: { stacked: true, min: 0, max: 7, ticks: { stepSize: 1 }, grid: { color: GRID, drawTicks: false }, border: { display: false } } } } });
  }

  function weightChart(el, s) {
    var vals = s.values.filter(function (x) { return x !== null; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = Math.max((hi - lo) * 0.25, 0.5);
    new Chart(el, { type: "line", data: { datasets: [{ data: pts(s.dates, s.values), borderColor: SERIES, backgroundColor: SERIES, borderWidth: 2, pointRadius: 3, tension: 0.2 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
        plugins: { legend: { display: false }, tooltip: tooltip({ callbacks: { label: function (i) { return i.parsed.y + " " + s.unit; } } }) },
        scales: { x: timeAxis(s.dates[0], s.dates[s.dates.length - 1]), y: { min: Math.max(0, Math.floor((lo - pad) * 10) / 10), max: Math.ceil((hi + pad) * 10) / 10, grid: { color: GRID, drawTicks: false }, border: { display: false } } } } });
  }

  function markersChart(el, data) {
    var palette = [SERIES, "#7a5cc6", "#2f8f8a", "#c07a2c", "#8c5a7a"];
    new Chart(el, { type: "line", data: { labels: data.weeks.map(function (w) { return fmt(w); }), datasets: data.series.map(function (s, i) {
      return { label: s.label, data: s.values, borderColor: palette[i % palette.length], backgroundColor: palette[i % palette.length], borderWidth: 2, pointRadius: 3, tension: 0.2, spanGaps: true };
    }) }, options: { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: true, position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } }, tooltip: tooltip({ callbacks: { title: function (items) { return "Week of " + items[0].label; }, label: function (i) { return i.dataset.label + ": " + (i.parsed.y === null ? "no answers" : i.parsed.y + "%"); } } }) },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } }, y: { min: 0, max: 100, ticks: { stepSize: 25, callback: function (val) { return val + "%"; } }, grid: { color: GRID, drawTicks: false }, border: { display: false } } } } });
  }

  var overall = document.querySelector("[data-chart=overall]");
  if (overall) { var os = JSON.parse(overall.dataset.series); window.__qolRange = { start: os.start, end: os.end }; }

  document.querySelectorAll("[data-chart]").forEach(function (wrap) {
    var kind = wrap.dataset.chart, s = JSON.parse(wrap.dataset.series), canvas = wrap.querySelector("canvas");
    if (kind === "overall") scoreChart(canvas, Object.assign({}, s.overall, { start: s.start, end: s.end, baseline: s.baseline, events: s.events }));
    else if (kind === "category") scoreChart(canvas, s, { integer: true });
    else if (kind === "spark") sparkChart(canvas, s);
    else if (kind === "weeks") weeksChart(canvas, s);
    else if (kind === "weight") weightChart(canvas, s);
    else if (kind === "markers") markersChart(canvas, s);
  });
})();
