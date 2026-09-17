/* Draws the history charts from the JSON embedded in the page. */
(function () {
  var dataEl = document.getElementById("series-data");
  if (!dataEl || typeof Chart === "undefined") return;
  var series = JSON.parse(dataEl.textContent);
  var css = getComputedStyle(document.documentElement);
  var SERIES = css.getPropertyValue("--series-1").trim() || "#2a78d6";
  var THRESHOLD = css.getPropertyValue("--threshold").trim() || "#8a8a8a";
  var INK = css.getPropertyValue("--text").trim() || "#2b2b2b";
  var MUTED = css.getPropertyValue("--muted").trim() || "#6b6b6b";
  var GRID = css.getPropertyValue("--border").trim() || "#e0ddd5";

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = MUTED;

  function prettyDate(iso) {
    var d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  function longDate(iso) {
    var d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { weekday: "short", month: "long", day: "numeric", year: "numeric" });
  }

  var labels = series.labels;
  var tickLimit = labels.length > 60 ? 8 : labels.length > 20 ? 10 : 14;

  function baseOptions(yMax, yStep) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#ffffff",
          titleColor: INK,
          bodyColor: INK,
          borderColor: GRID,
          borderWidth: 1,
          padding: 10,
          displayColors: false,
          callbacks: { title: function (items) { return longDate(labels[items[0].dataIndex]); } }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: tickLimit, maxRotation: 0, callback: function (v) { return prettyDate(labels[v]); } }
        },
        y: {
          min: 0, max: yMax,
          grid: { color: GRID, drawTicks: false },
          border: { display: false },
          ticks: { stepSize: yStep, padding: 6 }
        }
      }
    };
  }

  function line(values, extra) {
    return Object.assign({
      data: values,
      borderColor: SERIES,
      backgroundColor: SERIES,
      borderWidth: 2,
      pointRadius: labels.length > 60 ? 0 : 3,
      pointHoverRadius: 5,
      pointBorderColor: "#ffffff",
      pointBorderWidth: 1,
      tension: 0.2,
      spanGaps: true
    }, extra || {});
  }

  // Total score with the threshold line.
  var totalEl = document.getElementById("chart-total");
  if (totalEl) {
    var totalOpts = baseOptions(window.QOL.maxTotal, 10);
    totalOpts.plugins.legend = { display: true, position: "bottom", labels: { boxWidth: 18, boxHeight: 2, usePointStyle: false } };
    totalOpts.plugins.tooltip.callbacks.label = function (item) {
      if (item.datasetIndex === 1) return null;
      return "Total " + item.parsed.y + " / " + window.QOL.maxTotal;
    };
    new Chart(totalEl, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          line(series.total, { label: "Total score" }),
          {
            label: "Threshold (" + window.QOL.threshold + ")",
            data: labels.map(function () { return window.QOL.threshold; }),
            borderColor: THRESHOLD, borderWidth: 1.5, borderDash: [6, 4],
            pointRadius: 0, pointHoverRadius: 0, fill: false
          }
        ]
      },
      options: totalOpts
    });
  }

  // One small chart per category.
  series.categories.forEach(function (cat) {
    var el = document.getElementById("chart-" + cat.key);
    if (!el) return;
    var opts = baseOptions(10, 5);
    opts.scales.x.ticks.maxTicksLimit = 4;
    opts.plugins.tooltip.callbacks.label = function (item) { return cat.label + " " + item.parsed.y + " / 10"; };
    new Chart(el, { type: "line", data: { labels: labels, datasets: [line(cat.values, { pointRadius: labels.length > 30 ? 0 : 2 })] }, options: opts });
  });

  // Weight.
  var weightEl = document.getElementById("chart-weight");
  if (weightEl && series.weight.unit) {
    var values = series.weight.values.filter(function (v) { return v !== null; });
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    var pad = Math.max((hi - lo) * 0.25, 0.5);
    var opts = baseOptions(undefined, undefined);
    opts.scales.y.min = Math.max(0, Math.floor((lo - pad) * 10) / 10);
    opts.scales.y.max = Math.ceil((hi + pad) * 10) / 10;
    delete opts.scales.y.ticks.stepSize;
    opts.plugins.tooltip.callbacks.label = function (item) { return item.parsed.y + " " + series.weight.unit; };
    new Chart(weightEl, { type: "line", data: { labels: labels, datasets: [line(series.weight.values)] }, options: opts });
  }
})();
