const $ = (id) => document.getElementById(id);

const state = {
  previewTotal: null,
  estimatedBytes: null,
  sourceCatalog: [],
  indexPlan: null,
  indexPlanKey: null,
  indexPlanRequest: 0,
  previewFields: [],
  selectedFields: [],
};

function isoFromLocal(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

function localInputValue(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 19);
}

function humanBytes(bytes) {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unit]}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function flatten(value, prefix = "", out = {}) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      flatten(child, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out[prefix] = Array.isArray(value) ? JSON.stringify(value) : value;
  }
  return out;
}

function selectedQueryMode() {
  return document.querySelector('input[name="queryMode"]:checked')?.value || "elasticsearch_dsl";
}

function stellarQueryText() {
  const expression = $("stellarQuery").value.trim();
  if (!expression) throw new Error("Stellar Cyber Query cannot be empty.");
  return expression;
}

function parseQuery() {
  if (selectedQueryMode() === "stellar_lucene") {
    return {query: {query_string: {query: stellarQueryText()}}};
  }

  const raw = $("queryDsl").value.trim();
  const query = JSON.parse(raw || "{}");
  if (!query || Array.isArray(query) || typeof query !== "object") {
    throw new Error("Query must be a JSON object.");
  }
  return query;
}

function queryPayloadFields() {
  if (selectedQueryMode() === "stellar_lucene") {
    return {
      query_mode: "stellar_lucene",
      query: {},
      stellar_query: stellarQueryText(),
    };
  }
  return {
    query_mode: "elasticsearch_dsl",
    query: parseQuery(),
    stellar_query: null,
  };
}

function selectedDestinationType() {
  return document.querySelector('input[name="destination"]:checked')?.value || "download";
}

function splitSizeBytes() {
  if (!$("splitFiles").checked) return null;
  const value = Number($("maxFileSizeValue").value);
  const unit = $("maxFileSizeUnit").value;
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error("Max file size must be greater than 0.");
  }
  const multiplier = unit === "gb" ? 1024 * 1024 * 1024 : 1024 * 1024;
  return Math.round(value * multiplier);
}

function recordLimitValue() {
  const mode = document.querySelector('input[name="exportRecords"]:checked')?.value || "all";
  if (mode === "all") return null;
  const value = Number($("recordLimit").value);
  if (!Number.isInteger(value) || value < 1) {
    throw new Error("Export record limit must be a positive whole number.");
  }
  return value;
}

function updateRecordLimitUI() {
  const limited = document.querySelector('input[name="exportRecords"]:checked')?.value === "limit";
  $("recordLimit").disabled = !limited;
}

function outputFilename() {
  const format = document.querySelector('input[name="format"]:checked')?.value || "csv";
  const compressed = $("compress").checked;
  let name = $("filename").value.trim() || "stellar-export";
  if (name.toLowerCase().endsWith(".gz")) name = name.slice(0, -3);
  if (!name.toLowerCase().endsWith(`.${format}`)) name += `.${format}`;
  if (compressed) name += ".gz";
  return name;
}

function numberedExample(filename) {
  const lower = filename.toLowerCase();
  const suffix = lower.endsWith(".csv.gz") ? ".csv.gz"
    : lower.endsWith(".json.gz") ? ".json.gz"
    : lower.endsWith(".csv") ? ".csv"
    : lower.endsWith(".json") ? ".json"
    : "";
  const stem = suffix ? filename.slice(0, -suffix.length) : filename;
  return `${stem}-0001${suffix} · ${stem}-0002${suffix} · …`;
}

function updateSplitUI() {
  const enabled = $("splitFiles").checked;
  $("maxFileSizeValue").disabled = !enabled;
  $("maxFileSizeUnit").disabled = !enabled;
  $("maxFileSizeLabel").classList.toggle("disabled-control", !enabled);
  $("splitExample").classList.toggle("hidden", !enabled);
  $("splitFilenameExample").textContent = numberedExample(outputFilename());
  updateSummary();
}

function selectedSources() {
  return [...document.querySelectorAll('input[name="source"]:checked')].map((el) => el.value);
}

function selectedSourceLabels() {
  const selected = new Set(selectedSources());
  return state.sourceCatalog.filter((item) => selected.has(item.id)).map((item) => item.label);
}

function selectedSourceIndices() {
  const selected = new Set(selectedSources());
  return state.sourceCatalog.filter((item) => selected.has(item.id)).map((item) => item.index);
}

function buildEffectiveQuery() {
  const raw = parseQuery();
  const start = isoFromLocal($("startTime").value);
  const end = isoFromLocal($("endTime").value);
  const timeField = $("timeField").value.trim() || "timestamp";
  if (!start || !end) throw new Error("Choose start and end time to build the effective DSL.");
  if (new Date(end) <= new Date(start)) throw new Error("End time must be later than start time.");

  const body = JSON.parse(JSON.stringify(raw));
  if (state.previewFields.length && state.selectedFields.length) {
    body._source = [...state.selectedFields];
  }
  delete body.aggs;
  delete body.aggregations;
  delete body.collapse;
  delete body.from;
  delete body.search_after;

  const originalQuery = body.query || {match_all: {}};
  body.query = {
    bool: {
      must: [originalQuery],
      filter: [
        {
          range: {
            [timeField]: {
              gte: start,
              lt: end,
            },
          },
        },
      ],
    },
  };
  return body;
}

function currentIndexPlanKey() {
  const start = isoFromLocal($("startTime").value);
  const end = isoFromLocal($("endTime").value);
  const sources = selectedSources();
  if (!start || !end || !sources.length || new Date(end) <= new Date(start)) return null;
  return JSON.stringify({sources, start, end});
}

function renderIndexPlan() {
  const key = currentIndexPlanKey();
  const plan = key && state.indexPlanKey === key ? state.indexPlan : null;
  const summary = $("resolvedIndexSummary");
  const warningBox = $("indexPlanWarnings");

  if (!selectedSources().length) {
    summary.textContent = "Select at least one data source.";
    $("resolvedIndices").textContent = "No data source selected";
    warningBox.classList.add("hidden");
    warningBox.textContent = "";
    return null;
  }

  if (!key) {
    summary.textContent = "Choose a valid start/end range to build the index plan.";
    $("resolvedIndices").textContent = "Index plan unavailable";
    warningBox.classList.add("hidden");
    warningBox.textContent = "";
    return null;
  }

  if (!plan) {
    summary.textContent = "Planning selected data sources…";
    $("resolvedIndices").textContent = "Planning…";
    warningBox.classList.add("hidden");
    warningBox.textContent = "";
    return null;
  }

  summary.innerHTML = plan.sources.map((item) => {
    const detail = item.mode === "daily"
      ? `${item.day_count} daily range${item.day_count === 1 ? "" : "s"}`
      : "Wildcard fallback";
    return `<div class="resolved-index-item"><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(detail)}</span></div>`;
  }).join("");

  $("resolvedIndices").textContent = plan.target;
  if (plan.warnings?.length) {
    warningBox.textContent = plan.warnings.join(" ");
    warningBox.classList.remove("hidden");
  } else {
    warningBox.textContent = "";
    warningBox.classList.add("hidden");
  }
  return plan;
}

async function refreshIndexPlan() {
  const key = currentIndexPlanKey();
  const requestId = ++state.indexPlanRequest;
  state.indexPlan = null;
  state.indexPlanKey = null;
  renderIndexPlan();
  renderEffectiveRequest();

  if (!key) return;
  const params = JSON.parse(key);
  try {
    const plan = await api("/api/query/index-plan", {
      method: "POST",
      body: JSON.stringify(params),
    });
    if (requestId !== state.indexPlanRequest || key !== currentIndexPlanKey()) return;
    state.indexPlan = plan;
    state.indexPlanKey = key;
  } catch (error) {
    if (requestId !== state.indexPlanRequest) return;
    $("resolvedIndexSummary").textContent = `Index planner error: ${error.message}`;
  }
  renderIndexPlan();
  renderEffectiveRequest();
}

function renderEffectiveRequest() {
  const plan = renderIndexPlan();
  const target = plan?.target;
  $("requestPath").textContent = `/connect/api/data/${target || "{planning-index-plan}"}/_search`;

  try {
    $("effectiveDsl").value = JSON.stringify(buildEffectiveQuery(), null, 2);
  } catch (error) {
    $("effectiveDsl").value = `Effective DSL unavailable: ${error.message}`;
  }
}

function basePayload() {
  const start = isoFromLocal($("startTime").value);
  const end = isoFromLocal($("endTime").value);
  if (!start || !end) throw new Error("Start and end time are required.");
  if (new Date(end) <= new Date(start)) throw new Error("End time must be later than start time.");
  if (!$("host").value.trim()) throw new Error("Stellar Cyber host is required.");
  if (!$("email").value.trim()) throw new Error("Stellar Cyber account email is required.");
  if (!$("token").value.trim()) throw new Error("All-Access Token is required.");
  const sources = selectedSources();
  if (!sources.length) throw new Error("Select at least one data source.");

  return {
    host: $("host").value.trim(),
    email: $("email").value.trim(),
    token: $("token").value.trim(),
    verify_tls: $("verifyTls").checked,
    sources,
    time_field: $("timeField").value.trim() || "timestamp",
    start,
    end,
    ...queryPayloadFields(),
    preview_limit: 100,
    target_records_per_slice: Number($("targetRecords").value || 5000),
    minimum_slice_ms: Number($("minimumSlice").value || 1),
  };
}

function destinationPayload() {
  const type = selectedDestinationType();
  if (type === "download") return {type: "download"};

  if (type === "s3") {
    if (!$("s3Bucket").value.trim()) throw new Error("S3 bucket is required.");
    if (!$("s3AccessKey").value.trim()) throw new Error("S3 access key is required.");
    if (!$("s3SecretKey").value.trim()) throw new Error("S3 secret key is required.");
    return {
      type: "s3",
      endpoint_url: $("s3Endpoint").value.trim() || null,
      region: $("s3Region").value.trim() || null,
      bucket: $("s3Bucket").value.trim(),
      prefix: $("s3Prefix").value.trim(),
      access_key: $("s3AccessKey").value.trim(),
      secret_key: $("s3SecretKey").value,
      force_path_style: $("s3PathStyle").checked,
    };
  }

  if (!$("sftpHost").value.trim()) throw new Error("SFTP host is required.");
  if (!$("sftpUsername").value.trim()) throw new Error("SFTP username is required.");
  const authMethod = $("sftpAuthMethod").value;
  if (authMethod === "password" && !$("sftpPassword").value) {
    throw new Error("SFTP password is required.");
  }
  if (authMethod === "private_key" && !$("sftpPrivateKey").value.trim()) {
    throw new Error("SFTP private key is required.");
  }
  return {
    type: "sftp",
    host: $("sftpHost").value.trim(),
    port: Number($("sftpPort").value || 22),
    username: $("sftpUsername").value.trim(),
    auth_method: authMethod,
    password: authMethod === "password" ? $("sftpPassword").value : null,
    private_key: authMethod === "private_key" ? $("sftpPrivateKey").value : null,
    remote_path: $("sftpRemotePath").value.trim() || "/",
    verify_host_key: $("sftpVerifyHostKey").checked,
  };
}

function setStatus(id, message, type = "") {
  const el = $(id);
  el.textContent = message;
  el.className = `status ${type}`.trim();
}

function setBusy(button, busy, busyText) {
  if (busy) {
    button.dataset.original = button.textContent;
    button.textContent = busyText;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.original || button.textContent;
    button.disabled = false;
  }
}

function apiErrorMessage(body, status) {
  const detail = body?.detail ?? body?.message ?? body;
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") return item.msg || item.message || item.detail;
        return null;
      })
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }

  if (detail && typeof detail === "object") {
    const message = detail.msg || detail.message || detail.error || detail.detail;
    if (typeof message === "string") return message;
  }

  if (status === 401) return "Authentication failed. Check the account email and All-Access Token.";
  if (status === 403) return "Connected, but the account does not have permission to query the selected data sources.";
  if (status >= 500) return "Connection failed. Check the host address, network path, and TLS settings.";
  return `Request failed (HTTP ${status}).`;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
  } catch (error) {
    throw new Error("The exporter service could not be reached. Check the server connection.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(apiErrorMessage(body, response.status));
  }
  return body;
}

function renderPreview(rows) {
  const table = $("previewTable");
  if (!rows.length) {
    table.innerHTML = '<thead><tr><th>No records</th></tr></thead><tbody><tr><td class="muted">The query returned no data in this range.</td></tr></tbody>';
    return;
  }

  const flattened = rows.slice(0, 100).map((row) => flatten(row));
  const columns = [];
  for (const row of flattened) {
    for (const key of Object.keys(row)) {
      if (!columns.includes(key) && columns.length < 16) columns.push(key);
    }
  }

  const thead = `<thead><tr>${columns.map((c) => `<th title="${escapeHtml(c)}">${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${flattened.map((row) => {
    return `<tr>${columns.map((c) => {
      const text = String(row[c] ?? "");
      const safe = escapeHtml(text);
      return `<td title="${safe}">${safe}</td>`;
    }).join("")}</tr>`;
  }).join("")}</tbody>`;
  table.innerHTML = thead + tbody;
}

function updateDiscoveredFields(fields) {
  const previousKnown = new Set(state.previewFields);
  const available = [...new Set((fields || []).filter(Boolean))];

  if (!state.previewFields.length) {
    state.selectedFields = [...available];
  } else {
    const availableSet = new Set(available);
    const preserved = state.selectedFields.filter((field) => availableSet.has(field));
    const newlyDiscovered = available.filter((field) => !previousKnown.has(field));
    state.selectedFields = [...preserved, ...newlyDiscovered];
  }
  state.previewFields = available;
  renderFieldSelector();
}

function moveSelectedField(field, direction) {
  const index = state.selectedFields.indexOf(field);
  const next = index + direction;
  if (index < 0 || next < 0 || next >= state.selectedFields.length) return;
  [state.selectedFields[index], state.selectedFields[next]] = [
    state.selectedFields[next],
    state.selectedFields[index],
  ];
  renderFieldSelector();
  renderEffectiveRequest();
}

function renderFieldSelector() {
  const container = $("fieldSelector");
  const list = $("fieldList");
  if (!state.previewFields.length) {
    container.classList.add("hidden");
    list.innerHTML = "";
    $("selectedFieldCount").textContent = "0 selected";
    return;
  }

  container.classList.remove("hidden");
  const search = $("fieldSearch").value.trim().toLowerCase();
  const selectedSet = new Set(state.selectedFields);
  const ordered = [
    ...state.selectedFields,
    ...state.previewFields.filter((field) => !selectedSet.has(field)),
  ].filter((field) => !search || field.toLowerCase().includes(search));

  $("selectedFieldCount").textContent =
    `${state.selectedFields.length} selected`;

  if (!ordered.length) {
    list.innerHTML = '<div class="field-empty">No fields match this search.</div>';
    return;
  }

  list.innerHTML = ordered.map((field) => {
    const selectedIndex = state.selectedFields.indexOf(field);
    const checked = selectedIndex >= 0;
    return `<div class="field-row" data-field="${escapeHtml(field)}">
      <input class="field-check" type="checkbox" ${checked ? "checked" : ""} aria-label="Export ${escapeHtml(field)}" />
      <code title="${escapeHtml(field)}">${escapeHtml(field)}</code>
      <span class="field-order">${checked ? selectedIndex + 1 : "—"}</span>
      <button class="field-move field-up" type="button" ${!checked || selectedIndex === 0 ? "disabled" : ""} aria-label="Move ${escapeHtml(field)} up">↑</button>
      <button class="field-move field-down" type="button" ${!checked || selectedIndex === state.selectedFields.length - 1 ? "disabled" : ""} aria-label="Move ${escapeHtml(field)} down">↓</button>
    </div>`;
  }).join("");

  list.querySelectorAll(".field-row").forEach((row) => {
    const field = row.dataset.field;
    row.querySelector(".field-check").addEventListener("change", (event) => {
      if (event.target.checked) {
        if (!state.selectedFields.includes(field)) state.selectedFields.push(field);
      } else {
        state.selectedFields = state.selectedFields.filter((item) => item !== field);
      }
      renderFieldSelector();
      renderEffectiveRequest();
    });
    row.querySelector(".field-up").addEventListener("click", () => moveSelectedField(field, -1));
    row.querySelector(".field-down").addEventListener("click", () => moveSelectedField(field, 1));
  });
}

function updateDestinationUI() {
  const type = selectedDestinationType();
  $("s3Panel").classList.toggle("hidden", type !== "s3");
  $("sftpPanel").classList.toggle("hidden", type !== "sftp");
  document.querySelectorAll(".destination").forEach((el) => {
    const radio = el.querySelector('input[name="destination"]');
    el.classList.toggle("selected", !!radio?.checked);
  });

  const labels = {
    download: "Browser download",
    s3: "S3-compatible",
    sftp: "SFTP",
  };
  $("summaryDestination").textContent = labels[type];
}

function updateSftpAuthUI() {
  const isPassword = $("sftpAuthMethod").value === "password";
  $("sftpPasswordLabel").classList.toggle("hidden", !isPassword);
  $("sftpKeyLabel").classList.toggle("hidden", isPassword);
}

function updateSummary() {
  const host = $("host").value.trim();
  $("summaryHost").textContent = host ? host.replace(/^https?:\/\//, "") : "Not set";
  const labels = selectedSourceLabels();
  $("summarySources").textContent = labels.length ? labels.join(", ") : "None";
  $("selectedSourceCount").textContent = `${labels.length} source${labels.length === 1 ? "" : "s"}`;

  const start = $("startTime").value;
  const end = $("endTime").value;
  $("summaryRange").textContent = start && end ? `${start.replace("T", " ")} → ${end.replace("T", " ")}` : "—";
  $("summaryRecords").textContent = state.previewTotal == null ? "Preview required" : Number(state.previewTotal).toLocaleString();

  const format = document.querySelector('input[name="format"]:checked')?.value || "csv";
  $("summaryOutput").textContent = `${format.toUpperCase()}${$("compress").checked ? " · gzip" : ""}`;
  $("summarySplit").textContent = $("splitFiles").checked
    ? `${$("maxFileSizeValue").value || "?"} ${$("maxFileSizeUnit").value.toUpperCase()} parts`
    : "Single file";
  $("splitFilenameExample").textContent = numberedExample(outputFilename());
  document.querySelectorAll(".choice").forEach((el) => {
    const radio = el.querySelector('input[name="format"]');
    el.classList.toggle("selected", !!radio?.checked);
  });
  updateDestinationUI();
  renderEffectiveRequest();
}

async function testConnection() {
  const button = $("testConnection");
  try {
    if (!$("host").value.trim() || !$("email").value.trim() || !$("token").value.trim()) {
      throw new Error("Host, account email, and All-Access Token are required.");
    }
    const sources = selectedSources();
    if (!sources.length) throw new Error("Select at least one data source.");
    setBusy(button, true, "Testing…");
    setStatus("connectionStatus", "Testing connection…");
    const result = await api("/api/connection/test", {
      method: "POST",
      body: JSON.stringify({
        host: $("host").value.trim(),
        email: $("email").value.trim(),
        token: $("token").value.trim(),
        verify_tls: $("verifyTls").checked,
        sources,
      }),
    });
    const names = result.sources?.join(", ") || `${sources.length} selected source(s)`;
    setStatus("connectionStatus", `Connected. Access confirmed for: ${names}${result.took_ms != null ? ` (${result.took_ms} ms)` : ""}.`, "success");
  } catch (error) {
    setStatus("connectionStatus", error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

async function testRemoteDestination(statusId, buttonId) {
  const button = $(buttonId);
  try {
    setBusy(button, true, "Testing…");
    setStatus(statusId, "Testing destination…");
    const result = await api("/api/destination/test", {
      method: "POST",
      body: JSON.stringify({destination: destinationPayload()}),
    });
    setStatus(statusId, result.message || "Destination is reachable.", "success");
  } catch (error) {
    setStatus(statusId, error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function validateQuery() {
  try {
    parseQuery();
    if (selectedQueryMode() === "stellar_lucene") {
      setStatus("queryStatus", "Stellar Cyber Query is ready. Lucene syntax is validated by Stellar Cyber when Preview runs.", "success");
    } else {
      setStatus("queryStatus", "Valid JSON. Time range will be injected as a non-overlapping filter.", "success");
    }
  } catch (error) {
    setStatus("queryStatus", error.message, "error");
  }
}

function updateQueryModeUI() {
  const stellar = selectedQueryMode() === "stellar_lucene";
  $("elasticQueryPanel").classList.toggle("hidden", stellar);
  $("stellarQueryPanel").classList.toggle("hidden", !stellar);
  $("validateQuery").textContent = stellar ? "Validate Query" : "Validate JSON";
  document.querySelectorAll(".query-mode").forEach((label) => {
    const radio = label.querySelector('input[name="queryMode"]');
    label.classList.toggle("selected", !!radio?.checked);
  });
  updateSummary();
}

async function previewQuery() {
  const button = $("previewQuery");
  try {
    setBusy(button, true, "Loading preview…");
    setStatus("queryStatus", "Running preview…");
    const result = await api("/api/query/preview", {
      method: "POST",
      body: JSON.stringify(basePayload()),
    });
    state.previewTotal = result.total;
    state.estimatedBytes = result.estimated_bytes;
    if (result.index_plan) {
      state.indexPlan = result.index_plan;
      state.indexPlanKey = currentIndexPlanKey();
    }
    $("recordCount").textContent = Number(result.total).toLocaleString();
    $("estimatedSize").textContent = humanBytes(result.estimated_bytes);
    $("queryTime").textContent = result.took_ms == null ? "—" : `${result.took_ms} ms`;
    renderPreview(result.rows);
    updateDiscoveredFields(result.fields || []);
    if (result.warnings?.length) {
      setStatus(
        "queryStatus",
        `Preview loaded: ${result.rows.length} rows shown. Warning: ${result.warnings.join(" ")}`,
        "warning",
      );
    } else {
      setStatus("queryStatus", `Preview loaded: ${result.rows.length} rows shown.`, "success");
    }
    updateSummary();
  } catch (error) {
    setStatus("queryStatus", error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollExport(statusUrl) {
  for (;;) {
    const status = await api(statusUrl);
    if (status.status === "completed") {
      setStatus("runStatus", `Completed: ${status.result} · ${humanBytes(status.bytes_sent)} streamed.`, "success");
      return;
    }
    if (status.status === "failed") {
      throw new Error(status.error || "Remote export failed.");
    }
    setStatus("runStatus", `Uploading… ${humanBytes(status.bytes_sent)} streamed.`);
    await wait(1000);
  }
}

async function runExport() {
  const button = $("runExport");
  try {
    setBusy(button, true, "Running export…");
    setStatus("runStatus", "Creating export job…");
    if (state.previewFields.length && !state.selectedFields.length) {
      throw new Error("Select at least one export field.");
    }
    const payload = {
      ...basePayload(),
      selected_fields: state.previewFields.length ? [...state.selectedFields] : null,
      record_limit: recordLimitValue(),
      format: document.querySelector('input[name="format"]:checked')?.value || "csv",
      compress: $("compress").checked,
      filename: $("filename").value.trim() || "stellar-export",
      max_file_size_bytes: splitSizeBytes(),
      destination: destinationPayload(),
    };
    const result = await api("/api/export/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (result.mode === "download") {
      $("downloadFrame").src = result.download_url;
      setStatus("runStatus", "Download started. Large ranges will be sliced automatically.", "success");
    } else {
      await pollExport(result.status_url);
    }
  } catch (error) {
    setStatus("runStatus", error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function renderSources(items) {
  const grid = $("sourceGrid");
  grid.innerHTML = items.map((item, index) => {
    const checked = item.id === "alerts" ? "checked" : "";
    return `<label class="source-option ${checked ? "selected" : ""}">
      <input type="checkbox" name="source" value="${escapeHtml(item.id)}" ${checked} />
      <span>
        <b>${escapeHtml(item.label)}</b>
        <code class="source-index">${escapeHtml(item.index)}</code>
        <small>${escapeHtml(item.description)}</small>
      </span>
    </label>`;
  }).join("");

  grid.querySelectorAll('input[name="source"]').forEach((input) => {
    input.addEventListener("change", () => {
      input.closest(".source-option")?.classList.toggle("selected", input.checked);
      updateSummary();
      refreshIndexPlan();
    });
  });
  updateSummary();
  refreshIndexPlan();
}

async function loadDataSources() {
  try {
    const items = await api("/api/data-sources");
    state.sourceCatalog = items;
    renderSources(items);
  } catch (error) {
    $("sourceGrid").innerHTML = `<div class="status error">${escapeHtml(error.message)}</div>`;
  }
}

function setAllSources(checked) {
  document.querySelectorAll('input[name="source"]').forEach((input) => {
    input.checked = checked;
    input.closest(".source-option")?.classList.toggle("selected", checked);
  });
  updateSummary();
  refreshIndexPlan();
}

function initialize() {
  const now = new Date();
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  $("startTime").value = localInputValue(yesterday);
  $("endTime").value = localInputValue(now);

  $("testConnection").addEventListener("click", testConnection);
  $("testDestination").addEventListener("click", () => testRemoteDestination("destinationStatus", "testDestination"));
  $("testSftpDestination").addEventListener("click", () => testRemoteDestination("sftpDestinationStatus", "testSftpDestination"));
  $("validateQuery").addEventListener("click", validateQuery);
  $("previewQuery").addEventListener("click", previewQuery);
  $("runExport").addEventListener("click", runExport);
  $("splitFiles").addEventListener("change", updateSplitUI);
  document.querySelectorAll('input[name="exportRecords"]').forEach((radio) => {
    radio.addEventListener("change", updateRecordLimitUI);
  });
  $("selectAllSources").addEventListener("click", () => setAllSources(true));
  $("clearSources").addEventListener("click", () => setAllSources(false));
  $("fieldSearch").addEventListener("input", renderFieldSelector);
  $("selectAllFields").addEventListener("click", () => {
    state.selectedFields = [...state.previewFields];
    renderFieldSelector();
    renderEffectiveRequest();
  });
  $("clearFields").addEventListener("click", () => {
    state.selectedFields = [];
    renderFieldSelector();
    renderEffectiveRequest();
  });
  $("sftpAuthMethod").addEventListener("change", updateSftpAuthUI);
  document.querySelectorAll('input[name="queryMode"]').forEach((radio) => {
    radio.addEventListener("change", updateQueryModeUI);
  });
  $("toggleActualIndices").addEventListener("click", () => {
    const target = $("resolvedIndices");
    const showing = !target.classList.contains("hidden");
    target.classList.toggle("hidden", showing);
    $("toggleActualIndices").textContent = showing ? "Show actual indices" : "Hide actual indices";
  });
  for (const id of ["startTime", "endTime"]) {
    $(id).addEventListener("input", refreshIndexPlan);
    $(id).addEventListener("change", refreshIndexPlan);
  }

  document.querySelectorAll("input,textarea,select").forEach((el) => {
    el.addEventListener("input", updateSummary);
    el.addEventListener("change", updateSummary);
  });

  document.querySelectorAll('input[name="destination"]').forEach((radio) => {
    radio.addEventListener("change", updateDestinationUI);
  });

  updateSftpAuthUI();
  updateRecordLimitUI();
  updateQueryModeUI();
  updateSummary();
  loadDataSources();
}

initialize();
