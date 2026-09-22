/* Slider fill, guided check-in steps, marker setup counter, baseline "unsure", share button. */
(function () {
  function paint(range) {
    var pct = ((range.value - range.min) / (range.max - range.min)) * 100;
    range.style.setProperty("--pct", pct + "%");
    var out = range.parentElement.querySelector("output");
    if (out) out.textContent = range.classList.contains("unset") ? "\u2013" : range.value;
  }
  function markSet(range) {
    range.classList.remove("unset");
    var flag = range.dataset.setFlag && document.getElementById(range.dataset.setFlag);
    if (flag) flag.value = "1";
  }
  document.querySelectorAll("input[type=range]").forEach(function (r) {
    paint(r);
    r.addEventListener("input", function () { markSet(r); paint(r); });
    r.addEventListener("change", function () { markSet(r); paint(r); });
  });

  /* Baseline: "unsure" checkboxes blank the score. */
  document.querySelectorAll("input.unsure").forEach(function (box) {
    var range = document.getElementById(box.dataset.for);
    function apply() { range.disabled = box.checked; range.classList.toggle("unsure", box.checked); }
    box.addEventListener("change", apply); apply();
  });

  /* Marker setup: live count against the maximum. */
  var mform = document.getElementById("markers-form");
  if (mform) {
    var max = Number(mform.dataset.max), counter = document.getElementById("marker-count");
    function count() {
      var n = 0;
      mform.querySelectorAll("input[name=labels]").forEach(function (i) {
        if ((i.type === "checkbox" && i.checked) || (i.type === "text" && i.value.trim())) n++;
      });
      counter.textContent = n + " of " + max + " chosen";
    }
    mform.addEventListener("input", count); mform.addEventListener("change", count); count();
  }

  /* Confirm dialogs: the text lives in a data attribute so pet names with
     apostrophes can't break an inline script. */
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });
  document.querySelectorAll("button[data-confirm]").forEach(function (b) {
    b.addEventListener("click", function (e) { if (!confirm(b.dataset.confirm)) e.preventDefault(); });
  });

  /* Share button (Web Share API when available). */
  var share = document.getElementById("share-button");
  if (share && navigator.share) {
    share.hidden = false;
    share.addEventListener("click", function () {
      navigator.share({ title: share.dataset.title, url: share.dataset.url }).catch(function () {});
    });
  }

  /* ---- Guided check-in ---------------------------------------------------- */
  var form = document.getElementById("entry-form");
  if (!form) return;
  var steps = Array.prototype.slice.call(form.querySelectorAll(".step"));
  var nav = document.getElementById("step-nav"), back = document.getElementById("step-back"), next = document.getElementById("step-next");
  var progress = document.getElementById("progress"), fill = document.getElementById("progress-fill"), label = document.getElementById("progress-label");
  var finalActions = document.getElementById("final-actions"), toggle = document.getElementById("mode-toggle");
  var reviewList = document.getElementById("review-list"), scoresIncluded = document.getElementById("scores-included");
  var skip = document.getElementById("skip-scores");
  var current = 0, skippingScores = false;

  function prefGuided() {
    try { var v = localStorage.getItem("qol-guided"); if (v !== null) return v === "1"; } catch (e) {}
    return form.dataset.guided === "1";
  }
  function setPref(on) { try { localStorage.setItem("qol-guided", on ? "1" : "0"); } catch (e) {} }

  function visibleSteps() {
    return steps.filter(function (s) { return !(skippingScores && s.classList.contains("score-step")); });
  }
  function buildReview() {
    if (!reviewList) return;
    reviewList.innerHTML = "";
    function add(k, v, wide) { var li = document.createElement("li"); if (wide) li.className = "wide"; li.innerHTML = "<span>" + k + "</span><strong>" + v + "</strong>"; reviewList.appendChild(li); }
    var status = form.querySelector("input[name=day_status]:checked");
    add("Today", status ? status.parentElement.textContent.trim() : "Not rated", true);
    var done = [], all = form.querySelectorAll("input[name=markers]");
    all.forEach(function (i) { if (i.checked) done.push(i.parentElement.textContent.trim()); });
    if (all.length) add("Behaviors", done.length ? done.join(", ") : "None today", true);
    if (scoresIncluded.value !== "0") {
      var sum = 0, n = 0, any = false;
      form.querySelectorAll(".score-step").forEach(function (s) {
        var r = s.querySelector("input[type=range]"), set = !r.classList.contains("unset");
        add(s.dataset.title, set ? r.value : "\u2013"); if (set) { sum += Number(r.value); n++; any = true; }
      });
      if (n) add("Average of scored", (sum / n).toFixed(1) + " / 10", true);
      if (!any) add("Scores", "None set today", true);
    } else {
      add("Scores", "Skipped today", true);
    }
    var notes = form.querySelector("textarea[name=notes]");
    if (notes && notes.value.trim()) add("Note", notes.value.trim(), true);
  }
  function show(i) {
    var list = visibleSteps();
    current = Math.max(0, Math.min(i, list.length - 1));
    steps.forEach(function (s) { s.hidden = true; });
    list[current].hidden = false;
    var last = current === list.length - 1;
    back.disabled = current === 0; next.hidden = last; finalActions.hidden = !last;
    fill.style.width = ((current + 1) / list.length * 100) + "%";
    label.textContent = last ? "Review" : "Step " + (current + 1) + " of " + list.length + " · " + list[current].dataset.title;
    if (last) buildReview();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function guided(on) {
    form.classList.toggle("guided", on);
    nav.hidden = !on; progress.hidden = !on; toggle.hidden = false;
    toggle.textContent = on ? "Show all questions on one page" : "Answer one question at a time";
    if (on) {
      var startKey = form.dataset.start === "scores" ? "hurt" : "";
      var idx = 0;
      if (startKey) visibleSteps().forEach(function (s, i) { if (s.dataset.step === startKey) idx = i; });
      show(idx);
    } else {
      steps.forEach(function (s) { s.hidden = false; });
      finalActions.hidden = false;
      form.querySelector(".step.review").hidden = true;
    }
  }
  if (skip) skip.addEventListener("click", function () {
    skippingScores = true; scoresIncluded.value = "0";
    show(current); // re-index without the score steps
  });
  form.querySelectorAll(".score-step input[type=range]").forEach(function (r) {
    r.addEventListener("input", function () { scoresIncluded.value = "1"; skippingScores = false; });
  });
  back.addEventListener("click", function () { show(current - 1); });
  next.addEventListener("click", function () { show(current + 1); });
  toggle.addEventListener("click", function () { var on = !form.classList.contains("guided"); setPref(on); guided(on); });
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && form.classList.contains("guided") && e.target.tagName !== "TEXTAREA" && current < visibleSteps().length - 1) { e.preventDefault(); show(current + 1); }
  });
  guided(prefGuided());
  if (document.querySelector(".flash") && form.classList.contains("guided")) show(visibleSteps().length - 1);
})();
