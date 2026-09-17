/* Small enhancements: slider fill, live total on the log form. */
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
})();
