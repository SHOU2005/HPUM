"use strict";

const $ = (sel) => document.querySelector(sel);
const API = { options: "/api/options", info: "/api/model-info", predict: "/api/predict" };

const AMENITY_PRESETS = {
  none: [],
  basic: ["LiftAvailable", "CarParking", "PowerBackup", "24X7Security", "MaintenanceStaff", "Intercom"],
  gated: ["LiftAvailable", "CarParking", "PowerBackup", "24X7Security", "MaintenanceStaff", "Intercom",
          "Gymnasium", "SwimmingPool", "ClubHouse", "Children'splayarea", "LandscapedGardens",
          "JoggingTrack", "IndoorGames", "RainWaterHarvesting", "Gasconnection"],
  luxury: ["LiftAvailable", "CarParking", "PowerBackup", "24X7Security", "MaintenanceStaff", "Intercom",
           "Gymnasium", "SwimmingPool", "ClubHouse", "Children'splayarea", "LandscapedGardens",
           "JoggingTrack", "IndoorGames", "RainWaterHarvesting", "Gasconnection", "SportsFacility",
           "MultipurposeRoom", "Cafeteria", "StaffQuarter", "AC", "Wifi", "Wardrobe", "VaastuCompliant"],
};
const DEFAULTS = { city: "Mumbai", locality: "Thane West", area: 1050, bhk: 2, preset: "basic" };
const CITY_LABELS = { Delhi: "Delhi NCR", Bangalore: "Bengaluru" };
const FIGURES = [
  ["01_data_quality_audit.png", "Data-quality audit: recorded rows (kept) vs corrupted rows (dropped)"],
  ["03_price_per_sqft_by_city.png", "Price per sq ft by city"],
  ["04_price_vs_area.png", "Price vs area, all cities (log scales)"],
  ["05_top_localities.png", "15 most expensive localities by median ₹/sq ft"],
  ["06_bhk_and_resale.png", "Price by BHK, and new vs resale rates"],
  ["07_amenity_premium.png", "Amenity premium on ₹/sq ft (city-adjusted)"],
  ["02_listings_per_city.png", "Clean listings per city"],
  ["08_predicted_vs_actual.png", "Predicted vs actual price on the test set"],
  ["09_errors.png", "Error distribution and typical error by city"],
];

let options = null;
let hasEstimated = false;
let currentEstimate = null; // { payload, result } of the last successful estimate
let debounceTimer = null;
let requestSeq = 0;

/* ---------- Formatting (Indian system: 1 lakh = 1,00,000; 1 crore = 100 lakh) ---------- */
const inrFull = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const intIN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

function inrShort(x) {
  if (x >= 1e7) return `₹${(x / 1e7).toFixed(x >= 1e9 ? 0 : 2)} Cr`;
  if (x >= 1e5) return `₹${(x / 1e5).toFixed(x >= 1e6 ? 1 : 2)} L`;
  return `₹${intIN.format(x)}`;
}
const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`;
const cityLabel = (c) => CITY_LABELS[c] || c;
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (ch) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

/* ---------- Theme ---------- */
function initTheme() {
  try {
    const saved = localStorage.getItem("theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (_) { /* storage unavailable */ }
  $("#themeToggle").addEventListener("click", () => {
    const root = document.documentElement;
    const isDark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = isDark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (_) { /* ignore */ }
  });
}

/* ---------- Form ---------- */
function radio(name, value, label, checked) {
  return `<label><input type="radio" name="${name}" value="${escapeHtml(value)}"${checked ? " checked" : ""}><span>${escapeHtml(label)}</span></label>`;
}

function buildForm() {
  $("#cityGroup").innerHTML = options.cities
    .map((c) => radio("city", c, cityLabel(c), c === DEFAULTS.city)).join("");

  const [, maxBhk] = options.bhk_range;
  $("#bhkGroup").innerHTML = Array.from({ length: Math.min(maxBhk, 5) }, (_, i) => i + 1)
    .map((b) => radio("bhk", b, b === 5 ? "5+" : `${b}`, b === DEFAULTS.bhk)).join("");

  $("#amenityGroups").innerHTML = Object.entries(options.amenity_groups).map(([group, items], i) => `
    <details class="amenity-group"${i === 0 ? " open" : ""}>
      <summary>${escapeHtml(group)} <span class="muted" data-group-count></span></summary>
      <div class="segmented">
        ${Object.entries(items).map(([key, label]) =>
          `<label><input type="checkbox" name="amenity" value="${escapeHtml(key)}"><span>${escapeHtml(label)}</span></label>`).join("")}
      </div>
    </details>`).join("");

  const [minA, maxA] = options.area_range;
  const slider = $("#areaRange");
  slider.min = Math.max(200, Math.floor(minA / 10) * 10);
  slider.max = Math.min(5000, Math.ceil(maxA / 10) * 10);
  $("#area").value = slider.value = DEFAULTS.area;

  fillLocalities(DEFAULTS.city);
  $("#locality").value = DEFAULTS.locality;
  applyPreset(DEFAULTS.preset);
  updateLocalityHint();
}

function fillLocalities(city) {
  $("#localityList").innerHTML = options.localities[city]
    .map((l) => `<option value="${escapeHtml(l.name)}">${l.listings} listings · ₹${intIN.format(l.median_ppsf)}/sq ft</option>`)
    .join("");
}

function currentCity() { return document.querySelector('input[name="city"]:checked').value; }

function findLocality(city, name) {
  const key = name.trim().toLowerCase();
  return options.localities[city].find((l) => l.name.toLowerCase() === key);
}

function updateLocalityHint() {
  const hint = $("#localityHint");
  const name = $("#locality").value.trim();
  const city = currentCity();
  const loc = name && findLocality(city, name);
  hint.classList.toggle("warn", Boolean(name && !loc));
  if (!name) hint.textContent = `${options.localities[city].length} localities available in ${cityLabel(city)}`;
  else if (loc) hint.textContent = `Median ₹${intIN.format(loc.median_ppsf)}/sq ft · ${loc.listings} listing${loc.listings === 1 ? "" : "s"} in training data`;
  else hint.textContent = `Not in our ${cityLabel(city)} data. Estimate will use city-level pricing.`;
}

function applyPreset(name) {
  const keep = new Set(AMENITY_PRESETS[name]);
  document.querySelectorAll('input[name="amenity"]').forEach((cb) => { cb.checked = keep.has(cb.value); });
  updateAmenityCounts();
}

function updateAmenityCounts() {
  const all = document.querySelectorAll('input[name="amenity"]:checked').length;
  $("#amenityCount").textContent = all ? `· ${all} selected` : "";
  document.querySelectorAll(".amenity-group").forEach((g) => {
    const n = g.querySelectorAll("input:checked").length;
    g.querySelector("[data-group-count]").textContent = n ? `(${n})` : "";
  });
}

function readForm() {
  return {
    city: currentCity(),
    locality: $("#locality").value.trim(),
    area_sqft: Number($("#area").value),
    bhk: Number(document.querySelector('input[name="bhk"]:checked').value),
    resale: document.querySelector('input[name="resale"]:checked').value === "1",
    amenities: [...document.querySelectorAll('input[name="amenity"]:checked')].map((cb) => cb.value),
  };
}

function validate(p) {
  if (p.locality.length < 2) return "Enter a locality.";
  if (!Number.isFinite(p.area_sqft) || p.area_sqft < 200 || p.area_sqft > 20000) return "Area must be between 200 and 20,000 sq ft.";
  return null;
}

function showError(msg) {
  const el = $("#formError");
  el.hidden = !msg;
  el.textContent = msg || "";
}

async function estimate() {
  const payload = readForm();
  const invalid = validate(payload);
  showError(invalid);
  if (invalid) return;

  const seq = ++requestSeq;
  $("#resultCard").classList.add("loading");
  try {
    const res = await fetch(API.predict, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (seq !== requestSeq) return; // a newer request superseded this one
    if (!res.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg.replace(/^Value error, /, "")).join(" ")
        : data.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    hasEstimated = true;
    currentEstimate = { payload, result: data };
    renderResult(data);
    refreshWhatIf(payload);
  } catch (err) {
    if (seq === requestSeq) showError(err.message || "Could not reach the prediction server.");
  } finally {
    if (seq === requestSeq) $("#resultCard").classList.remove("loading");
  }
}

function scheduleEstimate() {
  if (!hasEstimated) return;
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(estimate, 300);
}

/* ---------- Result ---------- */
let lastPrice = 0;

function renderResult(r) {
  $("#resultEmpty").hidden = true;
  $("#resultBody").hidden = false;
  countUp($("#resPrice"), shownPrice, r.price, inrShort);
  shownPrice = r.price;
  $("#resFull").textContent = inrFull.format(r.price);
  $("#resPpsf").textContent = `₹${intIN.format(r.price_per_sqft)} per sq ft`;

  const badge = $("#resVsLocality");
  if (r.locality_median_ppsf) {
    const diff = r.price_per_sqft / r.locality_median_ppsf - 1;
    badge.hidden = false;
    badge.textContent = Math.abs(diff) < 0.02
      ? `≈ ${r.locality} median rate`
      : `${pct(Math.abs(diff), 0)} ${diff > 0 ? "above" : "below"} ${r.locality} median (₹${intIN.format(r.locality_median_ppsf)})`;
  } else {
    badge.hidden = true;
  }

  // range bar: pad the scale either side of the 80% interval
  const lo = r.low * 0.85, hi = r.high * 1.15, span = hi - lo;
  const pos = (v) => `${((v - lo) / span) * 100}%`;
  const band = document.querySelector(".range-band");
  band.style.left = pos(r.low);
  band.style.right = `${100 - ((r.high - lo) / span) * 100}%`;
  document.querySelector(".range-dot").style.left = pos(r.price);
  $("#resLow").textContent = inrShort(r.low);
  $("#resHigh").textContent = inrShort(r.high);
  $("#resRangeNote").textContent =
    `${pct(r.coverage, 0)} likely range: on unseen listings, ${pct(r.coverage, 0)} of actual prices fell inside a range this wide.`;

  $("#resWarnings").innerHTML = r.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");

  lastPrice = r.price;
  $("#emiCard").hidden = false;
  renderEmi();
}

function renderEmi() {
  const down = Number($("#emiDown").value) / 100;
  const annual = Number($("#emiRate").value);
  const years = Number($("#emiYears").value);
  $("#emiDownOut").textContent = `${(down * 100).toFixed(0)}% · ${inrShort(lastPrice * down)}`;
  $("#emiRateOut").textContent = `${annual.toFixed(2)}% p.a.`;
  $("#emiYearsOut").textContent = `${years} years`;

  const principal = lastPrice * (1 - down);
  const r = annual / 12 / 100;
  const n = years * 12;
  const emi = principal * r * (1 + r) ** n / ((1 + r) ** n - 1);
  $("#emiValue").textContent = inrFull.format(Math.round(emi));
  $("#emiLoan").textContent = inrShort(principal);
  $("#emiInterest").textContent = inrShort(emi * n - principal);
}

/* ---------- Charts (HTML bars, single series) ---------- */
const tooltip = $("#tooltip");

function showTip(evt, html) {
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const rect = evt.currentTarget.getBoundingClientRect();
  const x = evt.clientX ?? rect.left + rect.width / 2;
  const y = evt.clientY ?? rect.top;
  const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
  tooltip.style.left = `${Math.min(Math.max(8, x + 14), innerWidth - tw - 8)}px`;
  tooltip.style.top = `${Math.max(8, y - th - 12)}px`;
}
const hideTip = () => { tooltip.hidden = true; };

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * p).find((m) => m >= v);
}

/**
 * rows: [{label, value, tip, emphasis}] — one bar per row, sharing one zero baseline.
 * Emphasised rows use the series colour; others are muted so the comparison reads at a glance.
 */
function barChart(el, rows, { fmt, axisFmt = fmt, highlight = true }) {
  const max = niceMax(Math.max(...rows.map((r) => r.value)));
  el.innerHTML = rows.map((r, i) => `
    <div class="bar-row" tabindex="0" data-i="${i}" aria-label="${escapeHtml(r.label)}: ${escapeHtml(fmt(r.value))}">
      <span class="bar-label${highlight && r.emphasis ? " em" : ""}">${escapeHtml(r.label)}</span>
      <span class="bar-track">
        <span class="bar${highlight && !r.emphasis ? " muted-bar" : ""}" style="width:0"></span>
        <span class="bar-value">${escapeHtml(fmt(r.value))}</span>
      </span>
    </div>`).join("") + `
    <div class="bar-axis" aria-hidden="true"><span></span>
      <span class="bar-axis-scale"><span>0</span><span>${escapeHtml(axisFmt(max / 2))}</span><span>${escapeHtml(axisFmt(max))}</span></span>
    </div>`;

  // value label sits after the bar, so the bar gets at most ~82% of the track
  requestAnimationFrame(() => el.querySelectorAll(".bar").forEach((bar, i) => {
    bar.style.width = `calc(${(rows[i].value / max) * 100}% * 0.82)`;
  }));
  el.querySelectorAll(".bar-row").forEach((row) => {
    const r = rows[Number(row.dataset.i)];
    row.addEventListener("mousemove", (e) => showTip(e, r.tip));
    row.addEventListener("focus", (e) => showTip(e, r.tip));
    row.addEventListener("mouseleave", hideTip);
    row.addEventListener("blur", hideTip);
  });
}

function table(el, head, rows) {
  el.innerHTML = `<table><thead><tr>${head.map((h, i) => `<th${i ? ' class="num"' : ""}>${escapeHtml(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="num"' : ""}>${escapeHtml(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function renderModelInfo(info) {
  const t = info.test_metrics;
  const bind = (k, v) => document.querySelectorAll(`[data-bind="${k}"]`).forEach((el) => { el.textContent = v; });
  const audit = info.data_audit;
  bind("heroMedian", pct(t.median_ape));
  bind("heroWithin20", pct(t.within_20, 0));
  bind("heroR2", t.r2_log.toFixed(3));
  bind("nTest", intIN.format(info.n_test));
  if (audit) {
    bind("nListings", `${intIN.format(audit.final_rows)}`);
    bind("nLocalities", `${intIN.format(audit.localities)}`);
    bind("corrBad", audit.price_area_correlation.amenities_not_recorded.toFixed(2));
    bind("corrGood", audit.price_area_correlation.amenities_recorded.toFixed(2));
    $("#auditSteps").innerHTML = audit.steps.map((s) => `
      <li><b>${intIN.format(s.rows)}</b><span>${escapeHtml(s.step)}${s.removed ? ` <span class="rm">−${intIN.format(s.removed)}</span>` : ""}</span></li>`).join("");
  }

  const tiles = [
    ["Typical error", pct(t.median_ape), "median absolute % error"],
    ["Within ±10%", pct(t.within_10, 0), `${pct(t.within_20, 0)} within ±20%`],
    ["R² (log price)", t.r2_log.toFixed(3), `R² in ₹: ${t.r2_inr.toFixed(3)}`],
    ["80% range hit-rate", pct(t.interval_coverage, 0), "calibrated price range"],
  ];
  $("#tiles").innerHTML = tiles.map(([k, v, s], i) =>
    `<div class="card tile animate-fade-up" style="animation-delay:${i * 90}ms"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");

  const models = [...info.comparison].sort((a, b) => a.median_ape - b.median_ape);
  barChart($("#chartModels"), models.map((m) => ({
    label: m.Model, value: m.median_ape * 100, emphasis: m.Model === info.model_name,
    tip: `<b>${escapeHtml(m.Model)}</b>Median error ${pct(m.median_ape)}<br>Mean error ${pct(m.mape)}<br>Within ±10%: ${pct(m.within_10, 0)}<br>R² (log) ${m.r2_log.toFixed(3)}`,
  })), { fmt: (v) => `${v.toFixed(1)}%`, axisFmt: (v) => `${+v.toFixed(1)}%` });
  table($("#tableModels"), ["Model", "Median err", "Mean err", "±10%", "R² log", "MAE (₹ L)"],
    models.map((m) => [m.Model, pct(m.median_ape), pct(m.mape), pct(m.within_10, 0), m.r2_log.toFixed(3), m.mae_lakh.toFixed(1)]));

  const cities = Object.entries(info.test_metrics_by_city).sort((a, b) => a[1].median_ape - b[1].median_ape);
  barChart($("#chartCities"), cities.map(([c, m]) => ({
    label: cityLabel(c), value: m.median_ape * 100, emphasis: true,
    tip: `<b>${escapeHtml(cityLabel(c))}</b>${m.n} test listings<br>Median error ${pct(m.median_ape)}<br>Within ±10%: ${pct(m.within_10, 0)}<br>R² (log) ${m.r2_log.toFixed(3)}`,
  })), { fmt: (v) => `${v.toFixed(1)}%`, axisFmt: (v) => `${+v.toFixed(1)}%`, highlight: false });
  table($("#tableCities"), ["City", "Listings", "Median err", "±10%", "R² log"],
    cities.map(([c, m]) => [cityLabel(c), m.n, pct(m.median_ape), pct(m.within_10, 0), m.r2_log.toFixed(3)]));

  const groups = info.feature_importance.filter((d) => d.kind === "group");
  const amen = info.feature_importance.filter((d) => d.kind === "amenity").slice(0, 5);
  const imp = [...groups, ...amen.map((d) => ({ ...d, feature: `· ${d.feature}` }))];
  barChart($("#chartImportance"), imp.map((d) => ({
    label: d.feature, value: Math.max(d.importance, 0), emphasis: d.kind === "group",
    tip: `<b>${escapeHtml(d.feature.replace(/^· /, ""))}</b>R² drops by ${d.importance.toFixed(3)} (±${d.std.toFixed(3)}) when shuffled${d.kind === "amenity" ? "<br>Individual amenity" : ""}`,
  })), { fmt: (v) => v.toFixed(v < 0.1 ? 3 : 2), axisFmt: (v) => `${+v.toFixed(2)}` });
  table($("#tableImportance"), ["Feature", "R² drop", "± std"],
    imp.map((d) => [d.feature, d.importance.toFixed(4), d.std.toFixed(4)]));
}

function renderGallery() {
  $("#gallery").innerHTML = FIGURES.map(([file, caption]) => `
    <button type="button" data-src="/figures/${file}" data-caption="${escapeHtml(caption)}">
      <img src="/figures/${file}" alt="${escapeHtml(caption)}" loading="lazy"><span>${escapeHtml(caption)}</span>
    </button>`).join("");
  $("#gallery").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    $("#lightboxImg").src = btn.dataset.src;
    $("#lightboxImg").alt = btn.dataset.caption;
    $("#lightboxCaption").textContent = btn.dataset.caption;
    $("#lightbox").showModal();
  });
  $("#lightbox").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
}

/* ---------- Motion ---------- */
const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)");
let shownPrice = 0;
let toastTimer = null;

/** Replay a CSS animation class on an element (remove, reflow, re-add). */
function restartAnimation(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
}

/** Tween a number from one value to another, formatting each frame. */
function countUp(el, from, to, format, ms = 700) {
  if (REDUCED_MOTION.matches || from === to) { el.textContent = format(to); return; }
  const start = performance.now();
  const frame = (now) => {
    const t = Math.min((now - start) / ms, 1);
    el.textContent = format(from + (to - from) * (1 - (1 - t) ** 3));
    if (t < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

/** Short message that slides up from the bottom of the screen. */
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("opacity-0", "translate-y-3");
  el.classList.add("opacity-100", "translate-y-0");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.remove("opacity-100", "translate-y-0");
    el.classList.add("opacity-0", "translate-y-3");
  }, 2400);
}

/** Fade sections and cards in as they scroll into view. */
function setupReveal() {
  if (REDUCED_MOTION.matches || !("IntersectionObserver" in window)) return;
  const targets = document.querySelectorAll(".section, .tool-card, .chart-card");
  targets.forEach((el) => el.classList.add("reveal"));
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-in");
      io.unobserve(entry.target);
    });
  }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
  targets.forEach((el) => io.observe(el));
}

/** Thin bar at the top of the page showing how far the visitor has scrolled. */
function setupScrollProgress() {
  const bar = $("#scrollProgress");
  const root = document.documentElement;
  const update = () => {
    const max = root.scrollHeight - root.clientHeight;
    bar.style.transform = `scaleX(${max > 0 ? root.scrollTop / max : 0})`;
  };
  addEventListener("scroll", update, { passive: true });
  update();
}

/* ---------- Decision tools ---------- */
const COMPARE_KEY = "hv-compare";
const MAX_COMPARE = 6;
const postJson = (url, body) => fetch(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const apiError = (data, fallback) => (Array.isArray(data.detail)
  ? data.detail.map((d) => d.msg.replace(/^Value error, /, "")).join(" ")
  : data.detail) || fallback;

/** Put a set of property fields on the form (any missing key is left as it is), then re-estimate. */
function setFormValues(p) {
  if (p.city) {
    const radio = document.querySelector(`input[name="city"][value="${p.city}"]`);
    if (radio) { radio.checked = true; fillLocalities(p.city); }
  }
  if (p.locality) $("#locality").value = p.locality;
  if (p.area_sqft) { $("#area").value = p.area_sqft; $("#areaRange").value = p.area_sqft; }
  if (p.bhk) {
    const radio = document.querySelector(`input[name="bhk"][value="${p.bhk}"]`);
    if (radio) radio.checked = true;
  }
  if (typeof p.resale === "boolean") {
    document.querySelector(`input[name="resale"][value="${p.resale ? 1 : 0}"]`).checked = true;
  }
  if (Array.isArray(p.amenities)) {
    const keep = new Set(p.amenities);
    document.querySelectorAll('input[name="amenity"]').forEach((cb) => { cb.checked = keep.has(cb.value); });
    updateAmenityCounts();
  }
  updateLocalityHint();
  estimate();
}

/* Deal check: asking price vs the model's fair range */
async function checkDeal(e) {
  e.preventDefault();
  const lakh = Number($("#askingLakh").value);
  const hint = $("#dealHint");
  if (!currentEstimate) { hint.textContent = "Estimate a property first, then check its asking price."; return; }
  if (!(lakh > 0)) { hint.textContent = "Enter the asking price in lakh, for example 125 for ₹1.25 crore."; return; }
  try {
    const res = await postJson("/api/valuate", { property: currentEstimate.payload, asking_price: lakh * 1e5 });
    const data = await res.json();
    if (!res.ok) throw new Error(apiError(data, "Could not check this price."));
    renderDeal(data);
  } catch (err) {
    hint.textContent = err.message;
  }
}

function renderDeal(d) {
  const box = $("#dealResult");
  $("#dealHint").textContent = "";
  box.hidden = false;
  const verdict = $("#dealVerdict");
  verdict.textContent = d.verdict;
  verdict.className = `verdict ${d.tone}`;
  restartAnimation(verdict, "animate-pop-in");
  const sign = d.gap_pct > 0 ? "+" : "";
  $("#dealGap").textContent = `Asking ${inrShort(d.asking_price)} is ${sign}${d.gap_pct}% against a fair value of ${inrShort(d.fair_price)}.`;

  const lo = Math.min(d.low, d.asking_price) * 0.9;
  const hi = Math.max(d.high, d.asking_price) * 1.1;
  const span = hi - lo;
  const pos = (v) => `${((v - lo) / span) * 100}%`;
  const band = box.querySelector(".range-band");
  band.style.left = pos(d.low);
  band.style.right = `${100 - ((d.high - lo) / span) * 100}%`;
  box.querySelector(".range-dot.fair").style.left = pos(d.fair_price);
  box.querySelector(".range-dot.ask").style.left = pos(d.asking_price);
  $("#dealLow").textContent = inrShort(d.low);
  $("#dealFair").textContent = `fair ${inrShort(d.fair_price)}`;
  $("#dealHigh").textContent = inrShort(d.high);
  $("#dealNote").textContent = d.note;
}

/* What-if: how the price moves with each change */
async function refreshWhatIf(payload) {
  const list = $("#whatIfList");
  try {
    const res = await postJson("/api/what-if", payload);
    const data = await res.json();
    if (!res.ok) throw new Error(apiError(data, "Scenarios are unavailable."));
    const rows = [...data.scenarios].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 10);
    if (!rows.length) { list.innerHTML = '<li class="muted">No scenarios to show for these inputs.</li>'; return; }
    list.innerHTML = rows.map((s, i) => `
      <li class="whatif-row animate-slide-in" style="animation-delay:${i * 45}ms">
        <span class="whatif-label">${escapeHtml(s.label)}</span>
        <span class="whatif-delta ${s.delta >= 0 ? "up" : "down"}">${s.delta >= 0 ? "+" : "−"}${inrShort(Math.abs(s.delta))} (${s.delta_pct >= 0 ? "+" : ""}${s.delta_pct}%)</span>
        <button type="button" class="chip-btn small" data-scenario="${i}">Apply</button>
      </li>`).join("");
    list.querySelectorAll("[data-scenario]").forEach((btn) => btn.addEventListener("click", () => {
      setFormValues(rows[Number(btn.dataset.scenario)].change);
    }));
  } catch (err) {
    list.innerHTML = `<li class="muted">${escapeHtml(err.message)}</li>`;
  }
}

/* Listing import: OCR a photo in the browser, then parse the text on the server */
let tesseractPromise = null;

function loadTesseract() {
  if (window.Tesseract) return Promise.resolve(window.Tesseract);
  if (!tesseractPromise) {
    tesseractPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
      s.onload = () => resolve(window.Tesseract);
      s.onerror = () => {
        tesseractPromise = null;
        reject(new Error("Could not load the text reader. Check your connection, or paste the text instead."));
      };
      document.head.append(s);
    });
  }
  return tesseractPromise;
}

async function readPhoto(file) {
  const status = $("#ocrStatus");
  status.textContent = "Loading the text reader…";
  try {
    const T = await loadTesseract();
    status.textContent = "Reading text from the photo…";
    const { data } = await T.recognize(file, "eng", {
      logger: (m) => {
        if (m.status === "recognizing text") status.textContent = `Reading text… ${Math.round(m.progress * 100)}%`;
      },
    });
    const text = (data.text || "").trim();
    $("#listingText").value = text;
    if (!text) { status.textContent = "No text found. Try a clearer, well-lit photo, or paste the text."; return; }
    status.textContent = "Text read. Checking it for property details…";
    await parseListing();
  } catch (err) {
    status.textContent = err.message || "Could not read the photo.";
  }
}

const PARSED_LABELS = {
  city: ["City", (v) => cityLabel(v)],
  locality: ["Locality", (v) => v],
  area_sqft: ["Area", (v) => `${intIN.format(v)} sq ft`],
  bhk: ["Bedrooms", (v) => `${v} BHK`],
  asking_price: ["Asking price", (v) => inrShort(v)],
  resale: ["Type", (v) => (v ? "Resale" : "New")],
};

async function parseListing() {
  const text = $("#listingText").value.trim();
  const status = $("#ocrStatus");
  if (text.length < 3) { status.textContent = "Paste or photograph a listing first."; return; }
  try {
    const res = await postJson("/api/parse-listing", { text });
    const data = await res.json();
    if (!res.ok) throw new Error(apiError(data, "Could not read this text."));

    $("#parsedChips").innerHTML = data.found.length
      ? data.found.map((k) => `<span class="chip">${PARSED_LABELS[k][0]}: ${escapeHtml(PARSED_LABELS[k][1](data[k]))}</span>`).join("")
      : '<span class="muted">No property details found. Include the area, BHK, price and locality.</span>';

    const fields = {};
    ["city", "locality", "area_sqft", "bhk", "resale"].forEach((k) => { if (data[k] != null) fields[k] = data[k]; });
    if (data.asking_price) $("#askingLakh").value = +(data.asking_price / 1e5).toFixed(2);
    if (data.found.length) {
      status.textContent = "Filled the form from the listing. Check the values before you rely on them.";
      setFormValues(fields);
    } else {
      status.textContent = "";
    }
  } catch (err) {
    status.textContent = err.message;
  }
}

/* Compare shortlist, saved in this browser only */
let compareNote = "";

function loadCompare() {
  try { return JSON.parse(localStorage.getItem(COMPARE_KEY) || "[]"); } catch (_) { return []; }
}

function saveCompare(list) {
  try { localStorage.setItem(COMPARE_KEY, JSON.stringify(list)); } catch (_) { /* storage unavailable */ }
}

function saveCurrent() {
  const list = loadCompare();
  if (!currentEstimate) toast("Estimate a property first, then save it");
  else if (list.length >= MAX_COMPARE) toast(`You can compare up to ${MAX_COMPARE} properties. Remove one first`);
  else {
    const { city, locality, area_sqft, bhk, resale, amenities } = currentEstimate.payload;
    list.push({ city, locality, area_sqft, bhk, resale, amenities });
    saveCompare(list);
    toast(`Saved ${locality} · ${list.length} to compare`);
  }
  renderCompare();
}

async function renderCompare() {
  const list = loadCompare();
  const body = $("#compareBody");
  const note = compareNote ? `<p class="hint">${escapeHtml(compareNote)}</p>` : "";
  compareNote = "";
  if (!list.length) {
    body.innerHTML = `${note}<p class="muted">No properties saved yet.</p>`;
    return;
  }
  if (list.length < 2) {
    body.innerHTML = `${note}<p class="hint">Save one more property to compare them.</p>
      <ul class="compare-list">${list.map((p, i) => `<li>${escapeHtml(p.locality)} · ${p.bhk} BHK · ${intIN.format(p.area_sqft)} sq ft
        <button type="button" class="link-btn" data-remove="${i}">Remove</button></li>`).join("")}</ul>`;
    return;
  }
  try {
    const res = await postJson("/api/compare", { properties: list });
    const rows = await res.json();
    if (!res.ok) throw new Error(apiError(rows, "Could not compare these properties."));
    body.innerHTML = `${note}<div class="table-scroll"><table class="compare-table">
      <thead><tr><th>Rank</th><th>Property</th><th class="num">Estimate</th><th class="num">₹ / sq ft</th>
        <th class="num">80% range</th><th></th></tr></thead>
      <tbody>${rows.map((r, i) => `<tr class="animate-fade-in ${r.rank === 1 ? "best" : ""}" style="animation-delay:${i * 70}ms">
        <td>${r.rank === 1 ? "🏆 " : ""}${r.rank}</td>
        <td><b>${escapeHtml(r.locality)}</b><br><span class="muted">${escapeHtml(cityLabel(r.city))} · ${r.bhk} BHK · ${r.area_sqft ? intIN.format(r.area_sqft) : ""} sq ft · ${r.resale ? "resale" : "new"}</span></td>
        <td class="num">${inrShort(r.estimate.price)}</td>
        <td class="num">₹${intIN.format(r.estimate.price_per_sqft)}</td>
        <td class="num">${inrShort(r.estimate.low)} – ${inrShort(r.estimate.high)}</td>
        <td><button type="button" class="link-btn" data-remove="${r.index}">Remove</button></td>
      </tr>`).join("")}</tbody></table></div>
      <p class="hint">Ranked by estimated price per sq ft, lowest first. A lower rate usually means more area for the money, but check the locality and amenities too.</p>`;
  } catch (err) {
    body.innerHTML = `${note}<p class="hint warn">${escapeHtml(err.message)}</p>`;
  }
}

function wireTools() {
  $("#dealForm").addEventListener("submit", checkDeal);
  $("#listingPhoto").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) readPhoto(f); });
  $("#parseBtn").addEventListener("click", parseListing);
  $("#saveCompare").addEventListener("click", saveCurrent);
  $("#clearCompare").addEventListener("click", () => { saveCompare([]); toast("Comparison cleared"); renderCompare(); });
  $("#compareBody").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    const list = loadCompare();
    list.splice(Number(btn.dataset.remove), 1);
    saveCompare(list);
    toast("Removed from comparison");
    renderCompare();
  });
  renderCompare();
}

/* ---------- Wiring ---------- */
function wire() {
  const form = $("#estimateForm");
  form.addEventListener("submit", (e) => { e.preventDefault(); estimate(); });

  form.addEventListener("change", (e) => {
    if (e.target.name === "city") {
      fillLocalities(currentCity());
      const top = options.localities[currentCity()][0];
      $("#locality").value = top ? top.name : "";
      updateLocalityHint();
    }
    if (e.target.name === "amenity") updateAmenityCounts();
    scheduleEstimate();
  });
  $("#locality").addEventListener("input", () => { updateLocalityHint(); scheduleEstimate(); });
  $("#areaRange").addEventListener("input", (e) => { $("#area").value = e.target.value; scheduleEstimate(); });
  $("#area").addEventListener("input", (e) => { $("#areaRange").value = e.target.value; scheduleEstimate(); });
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    applyPreset(b.dataset.preset);
    scheduleEstimate();
  }));
  ["#emiDown", "#emiRate", "#emiYears"].forEach((s) => $(s).addEventListener("input", renderEmi));
  addEventListener("scroll", hideTip, { passive: true });
}

async function main() {
  initTheme();
  renderGallery();
  try {
    const [opt, info] = await Promise.all([fetch(API.options), fetch(API.info)]);
    if (!opt.ok || !info.ok) throw new Error("The model is not trained yet. Run the training scripts first.");
    options = await opt.json();
    buildForm();
    wire();
    wireTools();
    renderModelInfo(await info.json());
    setupScrollProgress();
    setupReveal();
    estimate();
  } catch (err) {
    showError(err.message || "Could not reach the prediction server. Is `uvicorn api:app` running?");
  }
}

main();
