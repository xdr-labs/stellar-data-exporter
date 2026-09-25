const $ = (id) => document.getElementById(id);

const state = {
  previewTotal: null,
  estimatedBytes: null,
  sourceCatalog: [],
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

function parseQuery() {
  const raw = $("queryDsl").value.trim();
  const query = JSON.parse(raw || "{}");
  if (!query || Array.isArray(query) || typeof query !== "object") {
    throw new Error("Query must be a JSON object.");
  }
  return query;
}

function selectedDestinationType() {
  return document.querySelector('input[name="destination"]:checked')?.value || "download";
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

function renderEffectiveRequest() {
  const indices = selectedSourceIndices();
  $("requestPath").textContent = `/connect/api/data/${indices.length ? indices.join(",") : "{select-data-source}"}/_search`;

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
    query: parseQuery(),
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
    setStatus("queryStatus", "Valid JSON. Time range will be injected as a non-overlapping filter.", "success");
  } catch (error) {
    setStatus("queryStatus", error.message, "error");
  }
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
    $("recordCount").textContent = Number(result.total).toLocaleString();
    $("estimatedSize").textContent = humanBytes(result.estimated_bytes);
    $("queryTime").textContent = result.took_ms == null ? "—" : `${result.took_ms} ms`;
    renderPreview(result.rows);
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
    const payload = {
      ...basePayload(),
      format: document.querySelector('input[name="format"]:checked')?.value || "csv",
      compress: $("compress").checked,
      filename: $("filename").value.trim() || "stellar-export",
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
      <span><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.description)}</small></span>
    </label>`;
  }).join("");

  grid.querySelectorAll('input[name="source"]').forEach((input) => {
    input.addEventListener("change", () => {
      input.closest(".source-option")?.classList.toggle("selected", input.checked);
      updateSummary();
    });
  });
  updateSummary();
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
  $("selectAllSources").addEventListener("click", () => setAllSources(true));
  $("clearSources").addEventListener("click", () => setAllSources(false));
  $("sftpAuthMethod").addEventListener("change", updateSftpAuthUI);

  document.querySelectorAll("input,textarea,select").forEach((el) => {
    el.addEventListener("input", updateSummary);
    el.addEventListener("change", updateSummary);
  });

  document.querySelectorAll('input[name="destination"]').forEach((radio) => {
    radio.addEventListener("change", updateDestinationUI);
  });

  updateSftpAuthUI();
  updateSummary();
  loadDataSources();
}

initialize();
