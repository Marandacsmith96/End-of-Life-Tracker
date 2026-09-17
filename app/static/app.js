/* Slider fill, live total, and the one-question-at-a-time check-in. */
(function () {
  var MAX_TOTAL = 70, THRESHOLD = 35;

  function paint(range) {
    var pct = ((range.value - range.min) / (range.max - range.min)) * 100;
    range.style.setProperty("--pct", pct + "%");
    var low = Number(range.value) <= 3;
    range.classList.toggle("low", low);
    var out = range.parentElement.querySelector("output");
    if (out) { out.textContent = range.value; out.classList.toggle("low", low); }
  }

  function updateTotal() {
    var box = document.getElementById("live-total");
    if (!box) return;
    var sum = 0;
    document.querySelectorAll(".scores input[type=range]").forEach(function (r) { sum += Number(r.value); });
    box.querySelector("strong").textContent = sum + " / " + MAX_TOTAL;
    var reading = box.querySelector(".reading");
    if (sum >= 50) reading.textContent = "Scores are in a comfortable range.";
    else if (sum > THRESHOLD) reading.textContent = "Above the scale's usual threshold of " + THRESHOLD + ", but worth watching.";
    else reading.textContent = "At or below the scale's usual threshold of " + THRESHOLD + ". Worth mentioning to your vet.";
    box.classList.toggle("low", sum <= THRESHOLD);
  }

  document.querySelectorAll("input[type=range]").forEach(function (r) {
    paint(r);
    r.addEventListener("input", function () { paint(r); updateTotal(); });
  });
  updateTotal();

  /* ---- Guided check-in ---------------------------------------------------- */
  var form = document.getElementById("entry-form");
  if (!form) return;
  var steps = Array.prototype.slice.call(form.querySelectorAll(".step"));
  var nav = document.getElementById("step-nav");
  var back = document.getElementById("step-back");
  var next = document.getElementById("step-next");
  var progress = document.getElementById("progress");
  var fill = document.getElementById("progress-fill");
  var label = document.getElementById("progress-label");
  var finalActions = document.getElementById("final-actions");
  var toggle = document.getElementById("mode-toggle");
  var reviewList = document.getElementById("review-list");
  var current = 0;

  function prefGuided() {
    try { var v = localStorage.getItem("qol-guided"); if (v !== null) return v === "1"; } catch (e) {}
    return form.dataset.guided === "1";
  }
  function setPref(on) { try { localStorage.setItem("qol-guided", on ? "1" : "0"); } catch (e) {} }

  function buildReview() {
    if (!reviewList) return;
    reviewList.innerHTML = "";
    form.querySelectorAll(".scores .step").forEach(function (s) {
      var r = s.querySelector("input[type=range]");
      var li = document.createElement("li");
      var v = Number(r.value);
      li.innerHTML = "<span>" + s.dataset.title + "</span><strong class='" + (v <= 3 ? "low" : "") + "'>" + v + "</strong>";
      reviewList.appendChild(li);
    });
    var w = form.querySelector("input[name=weight]");
    if (w && w.value) {
      var li = document.createElement("li");
      li.innerHTML = "<span>Weight</span><strong>" + w.value + " " + form.querySelector("select[name=weight_unit]").value + "</strong>";
      reviewList.appendChild(li);
    }
    var a = form.querySelector("input[name=appetite]:checked");
    if (a) {
      var li2 = document.createElement("li");
      li2.innerHTML = "<span>Appetite</span><strong>" + a.parentElement.textContent.trim() + "</strong>";
      reviewList.appendChild(li2);
    }
  }

  function show(i) {
    current = Math.max(0, Math.min(i, steps.length - 1));
    steps.forEach(function (s, idx) { s.hidden = idx !== current; });
    var last = current === steps.length - 1;
    back.disabled = current === 0;
    next.hidden = last;
    finalActions.hidden = !last;
    fill.style.width = ((current + 1) / steps.length * 100) + "%";
    label.textContent = last ? "Review" : "Step " + (current + 1) + " of " + steps.length + " · " + steps[current].dataset.title;
    if (last) buildReview();
    var focus = steps[current].querySelector("input[type=range], input, textarea");
    if (focus && current > 0) focus.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function guided(on) {
    form.classList.toggle("guided", on);
    nav.hidden = !on;
    progress.hidden = !on;
    toggle.hidden = false;
    toggle.textContent = on ? "Show all questions on one page" : "Answer one question at a time";
    if (on) { show(0); }
    else {
      steps.forEach(function (s) { s.hidden = false; });
      finalActions.hidden = false;
      var review = form.querySelector(".step.review");
      if (review) review.hidden = true;
    }
  }

  back.addEventListener("click", function () { show(current - 1); });
  next.addEventListener("click", function () { show(current + 1); });
  toggle.addEventListener("click", function () { var on = !form.classList.contains("guided"); setPref(on); guided(on); });
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && form.classList.contains("guided") && e.target.tagName !== "TEXTAREA" && current < steps.length - 1) {
      e.preventDefault(); show(current + 1);
    }
  });
  // In guided mode, jump straight to review when the server sent back errors.
  guided(prefGuided());
  if (document.querySelector(".flash") && form.classList.contains("guided")) show(steps.length - 1);
})();
