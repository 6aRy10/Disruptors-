const state = {
  snapshot: null,
  selectedEventId: null,
  selectedSku: null,
  loading: false,
};

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function money(value) {
  const n = Number(value || 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

function number(value, digits = 0) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
  }).format(Number(value || 0));
}

function shortDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function badgeClass(value) {
  const v = String(value || "").toUpperCase();
  if (["FEASIBLE", "CONFIRMED", "AVAILABLE", "LIVE", "SUCCESS"].some(x => v.includes(x))) return "success";
  if (["SHORTAGE", "REJECT", "UNAVAILABLE", "FAILED", "CRITICAL"].some(x => v.includes(x))) return "danger";
  if (["PROVISIONAL", "PENDING", "REPLAY", "UNKNOWN", "DEGRADED"].some(x => v.includes(x))) return "warning";
  return "blue";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
  if (!response.ok) {
    const detail = body?.detail || body?.raw || response.statusText;
    throw new Error(detail);
  }
  return body;
}

function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    el.className = "toast";
  }, 4200);
}

function setConnection(ok, label = "CONNECTED") {
  const el = $("connectionBadge");
  el.textContent = label;
  el.className = "badge " + (ok ? "success" : "danger");
}

async function loadSnapshot(eventId = state.selectedEventId) {
  if (state.loading) return;
  state.loading = true;
  $("refreshBtn").disabled = true;
  try {
    const params = new URLSearchParams();
    if (eventId) params.set("event_id", eventId);
    params.set("radius_km", "150");
    const snapshot = await api("/dashboard/snapshot?" + params.toString());
    state.snapshot = snapshot;
    state.selectedEventId = snapshot.selected.event_id;
    setConnection(true);
    renderAll();
  } catch (error) {
    console.error(error);
    setConnection(false, "API ERROR");
    toast(error.message, true);
  } finally {
    state.loading = false;
    $("refreshBtn").disabled = false;
  }
}

function renderAll() {
  renderMetrics();
  renderEvents();
  renderMap();
  renderSelectedEvent();
  renderActions();
  renderOperations();
  renderMemory();
  renderTruth();
  syncControlDefaults();
}

function renderMetrics() {
  const m = state.snapshot?.metrics || {};
  $("mState").textContent = number(m.state_version);
  $("mIncidents").textContent = number(m.open_incidents);
  $("mProducts").textContent = number(m.selected_event_products);
  $("mRevenue").textContent = money(m.selected_event_revenue_eur);
  $("mMargin").textContent = money(m.selected_event_margin_eur);
  $("mShortage").textContent = number(m.selected_event_shortage_units);
}

function renderEvents() {
  const events = state.snapshot?.events || [];
  $("eventFeed").innerHTML = events.map(event => {
    const active = event.event_id === state.selectedEventId ? " active" : "";
    return `
      <button class="event-card${active}" data-event-id="${esc(event.event_id)}">
        <div class="event-row">
          <span class="badge ${badgeClass(event.mode)}">${esc(event.mode)}</span>
          <span class="muted">${esc(event.event_type)}</span>
        </div>
        <h3>${esc(event.title || event.event_id)}</h3>
        <p>${esc(event.source)} · ${esc(shortDate(event.occurred_or_effective_at))}</p>
      </button>
    `;
  }).join("") || '<div class="empty-state">No events stored.</div>';

  document.querySelectorAll(".event-card").forEach(el => {
    el.addEventListener("click", () => {
      state.selectedSku = null;
      loadSnapshot(el.dataset.eventId);
    });
  });
}

function project(lon, lat) {
  const x = ((Number(lon) + 180) / 360) * 1000;
  const y = ((90 - Number(lat)) / 180) * 470;
  return [x, y];
}

function renderMap() {
  const svg = $("networkMap");
  const facilities = state.snapshot?.network?.facilities || [];
  const impact = state.snapshot?.selected?.impact || {};
  const publicExposure = state.snapshot?.selected?.public_exposure || [];
  const impactedOperational = new Set(
    (impact.facilities || []).map(row => row.facility_id).filter(Boolean)
  );

  const selectedPublicIds = new Set(
    publicExposure
      .map(row => row.network_facility_id)
      .filter(Boolean)
  );
  for (const row of facilities) {
    const ids = row.operational_facility_ids || [];
    if (ids.some(id => impactedOperational.has(id))) {
      selectedPublicIds.add(row.network_facility_id);
    }
  }

  let markup = "";
  for (let lon = -180; lon <= 180; lon += 30) {
    const [x] = project(lon, 0);
    markup += `<line x1="${x}" y1="0" x2="${x}" y2="470" stroke="#17312b" stroke-width=".7"/>`;
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const [, y] = project(0, lat);
    markup += `<line x1="0" y1="${y}" x2="1000" y2="${y}" stroke="#17312b" stroke-width=".7"/>`;
  }

  markup += `
    <text x="18" y="26" fill="#45675f" font-size="11">GLOBAL SUPPLY NETWORK · EQUIRECTANGULAR VIEW</text>
    <text x="18" y="445" fill="#36564e" font-size="9">Public supplier coordinates are derived from the loaded public network. Operational links are separate private-demo data.</text>
  `;

  for (const f of facilities) {
    if (f.longitude == null || f.latitude == null) continue;
    const [x, y] = project(f.longitude, f.latitude);
    const exposed = selectedPublicIds.has(f.network_facility_id);
    const linked = !!f.business_linked;
    const fill = exposed ? "#ff7d79" : linked ? "#72f2b6" : "#6fa8ff";
    const radius = exposed ? 5 : linked ? 3.2 : 1.6;
    const opacity = exposed ? 1 : linked ? .92 : .42;
    markup += `
      <circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${radius}"
        fill="${fill}" opacity="${opacity}">
        <title>${esc(f.official_name || f.name)} · ${esc(f.country)}${linked ? " · operationally linked" : ""}${exposed ? " · event path reached" : ""}</title>
      </circle>
    `;
  }
  svg.innerHTML = markup;

  const stats = state.snapshot?.network?.stats || {};
  const scale = state.snapshot?.data_scale || {};
  $("networkStats").innerHTML = `
    <strong>${number(stats.network_facilities)}</strong> public facilities ·
    <strong>${number(stats.official_list_relationships)}</strong> public relationships ·
    <strong>${number(scale.products)}</strong> private SKUs ·
    <strong>${number(scale.bom_lines)}</strong> BOM rows ·
    <strong>${number(scale.material_allocation_edges)}</strong> source edges
  `;

  $("eventTruthBanner").textContent =
    impact.claim_rule ||
    "Select an event. The product separates public exposure from confirmed operational impact.";
}

function selectedEventRecord() {
  return (state.snapshot?.events || []).find(e => e.event_id === state.selectedEventId);
}

function chooseDefaultSku(products) {
  if (state.selectedSku && products.some(p => p.sku === state.selectedSku)) return state.selectedSku;
  const portfolioProducts = state.snapshot?.selected?.portfolio?.products || [];
  const operational = portfolioProducts.find(p => p.operationally_affected);
  if (operational) return operational.sku;
  return products[0]?.sku || null;
}

function renderSelectedEvent() {
  const event = selectedEventRecord();
  const impact = state.snapshot?.selected?.impact || {};
  const portfolio = state.snapshot?.selected?.portfolio;
  const products = impact.products || [];

  $("selectedEventTitle").textContent = event?.title || state.selectedEventId || "No event selected";
  $("eventModeBadge").textContent = event?.mode || "—";
  $("eventModeBadge").className = "badge " + badgeClass(event?.mode);

  $("eventMeta").innerHTML = event ? `
    <div><strong>${esc(event.event_type)}</strong> · ${esc(event.source)}</div>
    <div>Occurred/effective: ${esc(event.occurred_or_effective_at || "unknown")}</div>
    <div>Exposure basis: ${esc(impact.exposure_basis || "—")}</div>
    <div>Public facilities within investigation radius: ${number(state.snapshot?.metrics?.public_facilities_potentially_exposed || 0)}</div>
    <div>Status: ${esc(impact.exposure_status || "—")}</div>
  ` : "No event selected.";

  const totals = impact.totals || {};
  $("commercialImpact").innerHTML = [
    ["Products", number(totals.products_impacted)],
    ["Commitment units", number(totals.commitment_units)],
    ["Revenue connected", money(totals.revenue_eur)],
    ["Margin connected", money(totals.gross_margin_eur)],
  ].map(([label, value]) => `
    <div class="commercial-box"><span>${label}</span><strong>${value}</strong></div>
  `).join("");

  state.selectedSku = chooseDefaultSku(products);
  $("productChips").innerHTML = products.map(p => `
    <button class="chip ${p.sku === state.selectedSku ? "active" : ""}" data-sku="${esc(p.sku)}">
      ${esc(p.sku)} · ${esc(p.name || "")}
    </button>
  `).join("") || '<span class="muted">No explicit business dependency reached.</span>';

  document.querySelectorAll("#productChips .chip").forEach(el => {
    el.addEventListener("click", () => {
      state.selectedSku = el.dataset.sku;
      document.querySelectorAll("#productChips .chip").forEach(x => x.classList.toggle("active", x.dataset.sku === state.selectedSku));
      renderProductGraph();
      syncControlDefaults();
    });
  });

  const summary = portfolio?.summary || {};
  const status = portfolio?.portfolio_status || (state.snapshot?.selected?.scenario_id ? "NO_PORTFOLIO" : "AWAITING_OPERATIONAL_EVIDENCE");
  $("planStateBadge").textContent = status;
  $("planStateBadge").className = "badge " + badgeClass(status);
  $("portfolioStatus").innerHTML = `
    <div class="status-line"><span>Scenario</span><strong>${esc(state.snapshot?.selected?.scenario_id || "none")}</strong></div>
    <div class="status-line"><span>Portfolio</span><strong>${esc(status)}</strong></div>
    <div class="status-line"><span>Operationally affected SKUs</span><strong>${number(summary.operationally_affected_sku_count)}</strong></div>
    <div class="status-line"><span>Conservative shortage</span><strong>${number(summary.total_conservative_shortage_units)} units</strong></div>
    <div class="status-line"><span>Net protected margin</span><strong>${money(summary.optimized_net_protected_margin_eur)}</strong></div>
  `;

  renderProductGraph();
}

async function renderProductGraph() {
  const target = $("dependencyGraph");
  const sku = state.selectedSku;
  if (!sku) {
    target.className = "dependency-graph empty-state";
    target.textContent = "Select a product above to trace its dependency graph.";
    return;
  }
  $("graphTitle").textContent = `${sku} dependency graph`;
  target.className = "dependency-graph";
  target.innerHTML = '<div class="empty-state">Loading graph…</div>';

  try {
    const graph = await api(`/products/${encodeURIComponent(sku)}/graph`);
    $("graphRule").textContent = graph.rule || "";
    drawGraph(graph);
  } catch (error) {
    target.className = "dependency-graph empty-state";
    target.textContent = error.message;
  }
}

function drawGraph(graph) {
  const target = $("dependencyGraph");
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const shared = new Set((graph.shared_upstream_sources || []).map(x => `facility:${x.source_facility_id}`));

  const columns = {
    UPSTREAM_FACILITY: 80,
    MATERIAL: 295,
    ASSEMBLY_FACILITY: 520,
    PRODUCT: 745,
    CUSTOMER_COMMITMENT: 960,
  };
  const groups = {};
  for (const n of nodes) {
    const type = n.node_type || "OTHER";
    if (!groups[type]) groups[type] = [];
    groups[type].push(n);
  }

  const positions = {};
  const rowGap = 62;
  const nodeW = 165;
  const nodeH = 42;
  let maxRows = 1;

  for (const [type, list] of Object.entries(groups)) {
    maxRows = Math.max(maxRows, list.length);
    list.forEach((node, index) => {
      positions[node.id] = {
        x: columns[type] ?? 745,
        y: 38 + index * rowGap,
      };
    });
  }

  const height = Math.max(330, 70 + maxRows * rowGap);
  const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));

  let markup = `<svg class="dependency-svg" viewBox="0 0 1100 ${height}">`;
  markup += `
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
        markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#486b63"></path>
      </marker>
    </defs>
  `;

  for (const edge of edges) {
    const a = positions[edge.source];
    const b = positions[edge.target];
    if (!a || !b) continue;
    const x1 = a.x + nodeW / 2;
    const x2 = b.x - nodeW / 2;
    const y1 = a.y;
    const y2 = b.y;
    const curve = Math.max(40, Math.abs(x2 - x1) * .35);
    const d = `M ${x1} ${y1} C ${x1 + curve} ${y1}, ${x2 - curve} ${y2}, ${x2} ${y2}`;
    const isShared = shared.has(edge.source);
    markup += `<path class="graph-edge ${isShared ? "shared" : ""}" d="${d}" marker-end="url(#arrow)"><title>${esc(edge.edge_type)}</title></path>`;
  }

  for (const node of nodes) {
    const p = positions[node.id];
    if (!p) continue;
    const typeClass = node.node_type === "PRODUCT" ? "product" :
      node.node_type === "CUSTOMER_COMMITMENT" ? "customer" :
      node.node_type === "MATERIAL" ? "material" :
      node.node_type === "UPSTREAM_FACILITY" ? "upstream" : "assembly";
    const label = String(node.label || node.id);
    const short = label.length > 25 ? label.slice(0, 24) + "…" : label;
    const sub = node.country || node.criticality || node.role || node.market || node.node_type;
    markup += `
      <g class="graph-node ${typeClass}" transform="translate(${p.x - nodeW/2},${p.y - nodeH/2})">
        <rect width="${nodeW}" height="${nodeH}"></rect>
        <text x="9" y="17">${esc(short)}</text>
        <text class="sub" x="9" y="31">${esc(sub || "")}</text>
        <title>${esc(label)} · ${esc(node.provenance_class || "")}</title>
      </g>
    `;
  }
  markup += "</svg>";
  target.innerHTML = markup;
}

function renderActions() {
  const portfolio = state.snapshot?.selected?.portfolio;
  const queue = portfolio?.action_queue || [];
  const rejected = portfolio?.rejected_actions || [];

  $("actionQueue").innerHTML = queue.map((row, index) => `
    <div class="action-card">
      <h3>#${index + 1} · ${esc(row.title)}</h3>
      <p>${esc(row.sku)} · risk ${number(row.risk_score, 1)}/100 · margin at risk ${money(row.at_risk_margin_eur)}</p>
      <div class="action-meta">
        <span class="badge ${badgeClass(row.decision)}">${esc(row.decision)}</span>
        ${(row.reasons || []).map(x => `<span class="reason">${esc(x)}</span>`).join("")}
      </div>
    </div>
  `).join("") || '<div class="empty-state muted">No recovery action is required for the selected operational state.</div>';

  $("rejectedActions").innerHTML = rejected.map(row => `
    <div class="action-card rejected">
      <h3>${esc(row.title)}</h3>
      <p>${esc(row.sku)} · deterministic rejection</p>
      <div class="action-meta">
        ${(row.reasons || []).map(x => `<span class="reason">${esc(x)}</span>`).join("")}
      </div>
    </div>
  `).join("") || '<div class="empty-state muted">No rejected actions for the selected event.</div>';
}

function renderOperations() {
  const ops = state.snapshot?.operations || {};
  $("supplierRequests").innerHTML = (ops.supplier_requests || []).map(row => `
    <div class="compact-row">
      <div>
        <strong>${esc(row.facility_name)} · ${esc(row.sku)}</strong>
        <span>${esc(row.field_requested)} · ${esc(shortDate(row.requested_at))}</span>
      </div>
      <span class="badge ${badgeClass(row.status)}">${esc(row.status)}</span>
    </div>
  `).join("") || '<div class="muted">No active supplier requests.</div>';

  const pending = ops.pending_approvals || [];
  const approved = ops.approved_actions_waiting_execution || [];
  const rows = [
    ...pending.map(row => `
      <div class="compact-row approval-row">
        <div>
          <strong>${esc(row.action_type)} · ${esc(row.sku || "")}</strong>
          <span>${esc(row.reason)} · ${esc(shortDate(row.requested_at))}</span>
          <div class="mini-actions">
            <button class="mini-button approve-btn" data-request-id="${esc(row.request_id)}">Approve</button>
            <button class="mini-button reject-btn" data-request-id="${esc(row.request_id)}">Reject</button>
          </div>
        </div>
        <span class="badge warning">${esc(row.status)}</span>
      </div>
    `),
    ...approved.map(row => `
      <div class="compact-row approval-row">
        <div>
          <strong>${esc(row.action_type)} · ${esc(row.sku || "")}</strong>
          <span>Approved by ${esc(row.decided_by || "planner")} · waiting for explicit execution</span>
          <div class="mini-actions">
            <button class="mini-button execute-btn" data-request-id="${esc(row.request_id)}">Execute approved action</button>
          </div>
        </div>
        <span class="badge success">APPROVED</span>
      </div>
    `)
  ];
  $("approvals").innerHTML = rows.join("") || '<div class="muted">No pending approvals or approved actions waiting for execution.</div>';

  document.querySelectorAll(".approve-btn").forEach(btn => {
    btn.addEventListener("click", () => decideApproval(btn.dataset.requestId, "APPROVED"));
  });
  document.querySelectorAll(".reject-btn").forEach(btn => {
    btn.addEventListener("click", () => decideApproval(btn.dataset.requestId, "REJECTED"));
  });
  document.querySelectorAll(".execute-btn").forEach(btn => {
    btn.addEventListener("click", () => executeApproval(btn.dataset.requestId));
  });
}

async function decideApproval(requestId, decision) {
  const reason = prompt(
    decision === "APPROVED"
      ? "Why are you approving this action?"
      : "Why are you rejecting this action?",
    decision === "APPROVED"
      ? "Approved after reviewing deterministic evidence."
      : "Rejected after reviewing deterministic evidence."
  );
  if (reason === null) return;
  try {
    await api(`/approvals/${encodeURIComponent(requestId)}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        decided_by: "Judge / Planner",
        decision_reason: reason,
      }),
    });
    toast(`Action ${decision.toLowerCase()}.`);
    await loadSnapshot(state.selectedEventId);
  } catch (error) {
    toast(error.message, true);
  }
}

async function executeApproval(requestId) {
  if (!confirm("Execute this approved operational action now? This can change state and invalidate existing plans.")) return;
  try {
    const result = await api(`/approvals/${encodeURIComponent(requestId)}/execute`, {
      method: "POST",
      body: JSON.stringify({ executed_by: "Judge / Planner" }),
    });
    const version = result?.result?.state_update?.state_version;
    toast(`Approved action executed${version != null ? ` · state version ${version}` : ""}.`);
    await loadSnapshot(state.selectedEventId);
  } catch (error) {
    toast(error.message, true);
  }
}

function renderMemory() {
  const rows = state.snapshot?.operations?.memory_hypotheses || [];
  $("memoryHypotheses").innerHTML = rows.map(row => `
    <div class="memory-card">
      <div class="memory-head">
        <div>
          <strong>${esc(row.summary)}</strong>
          <span>${esc(row.similarity_reason)} · relevance ${number(row.similarity_score)}/100 · ${esc(row.provenance_class)}</span>
        </div>
        <span class="badge ${row.success ? "success" : "warning"}">${row.success ? "SUCCESS" : "FAILED / PARTIAL"}</span>
      </div>
      <p>${esc(row.lesson)}</p>
      <div class="memory-metrics">
        <span>delay <b>${row.actual_supplier_delay_days == null ? "—" : number(row.actual_supplier_delay_days) + "d"}</b></span>
        <span>shortage <b>${row.actual_shortage_units == null ? "—" : number(row.actual_shortage_units)}</b></span>
        <span>cost <b>${row.actual_cost_eur == null ? "—" : money(row.actual_cost_eur)}</b></span>
      </div>
      <div class="memory-rule">${esc(row.usage_rule)}</div>
    </div>
  `).join("") || '<div class="muted">No closed same-type incident memory is available yet.</div>';
}


function renderTruth() {
  const truth = state.snapshot?.truth_model || {};
  $("truthModel").innerHTML = Object.entries(truth).map(([key, value]) => `
    <div class="truth-card"><strong>${esc(key)}</strong><p>${esc(value)}</p></div>
  `).join("");

  $("claimRules").innerHTML = (state.snapshot?.claim_rules || []).map(rule => `
    <div class="claim-rule">${esc(rule)}</div>
  `).join("");
}

function getPortfolioProduct(sku = state.selectedSku) {
  return (state.snapshot?.selected?.portfolio?.products || []).find(p => p.sku === sku);
}

function setInput(formId, name, value) {
  const form = $(formId);
  const input = form?.elements?.namedItem(name);
  if (input && value != null && value !== "") input.value = value;
}

function syncControlDefaults() {
  const scenarioId = state.snapshot?.selected?.scenario_id;
  const product = getPortfolioProduct();
  if (!product) return;

  const sku = product.sku;
  const backup = product.conservative_plan?.selected_backup;
  const candidates = product.candidates || [];
  const po = candidates.find(x => x.plan_type === "PO_EXPEDITE");
  const substitute = candidates.find(x => x.plan_type === "MATERIAL_SUBSTITUTION");

  ["capacityForm", "leadTimeForm", "poForm"].forEach(id => setInput(id, "sku", sku));
  setInput("inventoryForm", "item_id", sku);
  if (scenarioId) {
    ["capacityForm", "facilityForm", "leadTimeForm", "poForm"].forEach(id => setInput(id, "scenario_id", scenarioId));
  }
  if (backup?.facility_id) {
    setInput("capacityForm", "facility_id", backup.facility_id);
    setInput("facilityForm", "facility_id", backup.facility_id);
    setInput("leadTimeForm", "facility_id", backup.facility_id);
  }
  if (po?.evidence?.po_id) setInput("poForm", "po_id", po.evidence.po_id);
  if (substitute?.evidence?.material_id) {
    setInput("substitutionForm", "material_id", substitute.evidence.material_id);
    setInput("substitutionForm", "substitute_material_id", substitute.evidence.substitute_material_id);
  }
}

async function submitEdit(label, path, body) {
  const result = $("controlResult");
  result.textContent = `${label}: submitting…`;
  try {
    const response = await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const version =
      response?.update?.state_version ??
      response?.state_version ??
      response?.capacity_update?.state_version;
    result.textContent = `${label}: accepted${version != null ? ` · state version ${version}` : ""}. Refreshing recovery state…`;
    toast(`${label} applied. Old plans are now stale if state changed.`);
    await loadSnapshot(state.selectedEventId);
  } catch (error) {
    result.textContent = `${label}: ${error.message}`;
    toast(error.message, true);
  }
}

function wireControls() {
  $("capacityForm").addEventListener("submit", event => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    submitEdit("Supplier capacity", "/suppliers/capacity/confirm", {
      facility_id: f.get("facility_id"),
      sku: f.get("sku"),
      capacity_units: Number(f.get("capacity_units")),
      valid_until: null,
      source_channel: "Judge control surface",
      raw_message: "Capacity changed by judge during interactive demo.",
      scenario_id: f.get("scenario_id") || null,
      release_safety_stock: false,
    });
  });

  $("inventoryForm").addEventListener("submit", event => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    submitEdit("Inventory", "/state/inventory", {
      site_id: f.get("site_id"),
      item_type: "finished_good",
      item_id: f.get("item_id"),
      qty_on_hand: Number(f.get("qty_on_hand")),
      qty_reserved: 0,
      safety_stock: Number(f.get("safety_stock")),
      scenario_id: state.snapshot?.selected?.scenario_id || null,
      sku: f.get("item_id"),
    });
  });

  $("facilityForm").addEventListener("submit", event => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    submitEdit("Facility state", "/state/facility", {
      scenario_id: f.get("scenario_id"),
      facility_id: f.get("facility_id"),
      status: f.get("status"),
      capacity_multiplier: Number(f.get("capacity_multiplier")),
      confirmed: true,
      source_type: "JUDGE_EDIT",
      reason: "Judge changed facility operational state.",
      sku: state.selectedSku,
    });
  });

  $("leadTimeForm").addEventListener("submit", event => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    submitEdit("Setup lead time", "/state/lead-time", {
      sku: f.get("sku"),
      facility_id: f.get("facility_id"),
      setup_lead_days: Number(f.get("setup_lead_days")),
      scenario_id: f.get("scenario_id") || null,
    });
  });

  $("poForm").addEventListener("submit", event => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    submitEdit("Purchase-order ETA", "/state/purchase-order-eta", {
      po_id: f.get("po_id"),
      eta: f.get("eta"),
      scenario_id: f.get("scenario_id") || null,
      sku: f.get("sku") || null,
    });
  });

  $("substitutionForm").addEventListener("submit", event => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    submitEdit("Substitution", "/state/substitution", {
      material_id: f.get("material_id"),
      substitute_material_id: f.get("substitute_material_id"),
      approved: f.get("approved") === "true",
      engineering_status: f.get("engineering_status"),
      scenario_id: state.snapshot?.selected?.scenario_id || null,
      sku: state.selectedSku,
    });
  });

  $("refreshBtn").addEventListener("click", () => loadSnapshot(state.selectedEventId));

  $("resetBtn").addEventListener("click", async () => {
    if (!confirm("Reset the deterministic demo state to seed values?")) return;
    try {
      await api("/demo/reset", { method: "POST", body: "{}" });
      state.selectedSku = null;
      toast("Demo state reset.");
      await loadSnapshot(state.selectedEventId);
    } catch (error) {
      toast(error.message, true);
    }
  });

  $("runAgentsBtn").addEventListener("click", async () => {
    if (!state.selectedEventId) return;
    const btn = $("runAgentsBtn");
    const old = btn.textContent;
    btn.textContent = "Agents running…";
    btn.disabled = true;
    try {
      const result = await api(`/agents/run-event/${encodeURIComponent(state.selectedEventId)}`, {
        method: "POST",
        body: JSON.stringify({
          radius_km: 150,
          model: null,
          persist: true,
        }),
      });
      toast(`Agent chain: ${result.status}`);
      await loadSnapshot(state.selectedEventId);
    } catch (error) {
      toast(error.message, true);
    } finally {
      btn.textContent = old;
      btn.disabled = false;
    }
  });
}

wireControls();
loadSnapshot();

setInterval(() => {
  if ($("autoRefresh").checked && !document.hidden) {
    loadSnapshot(state.selectedEventId);
  }
}, 10000);
