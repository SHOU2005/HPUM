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
    renderResult(data);
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
  $("#resPrice").textContent = inrShort(r.price);
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
  $("#tiles").innerHTML = tiles.map(([k, v, s]) =>
    `<div class="card tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");

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
    renderModelInfo(await info.json());
    estimate();
  } catch (err) {
    showError(err.message || "Could not reach the prediction server. Is `uvicorn api:app` running?");
  }
}

main();
