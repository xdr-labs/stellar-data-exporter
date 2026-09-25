const $ = (id) => document.getElementById(id);

const state = {
  previewTotal: null,
  estimatedBytes: null,
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

function basePayload() {
  const start = isoFromLocal($("startTime").value);
  const end = isoFromLocal($("endTime").value);
  if (!start || !end) throw new Error("Start and end time are required.");
  if (new Date(end) <= new Date(start)) throw new Error("End time must be later than start time.");
  if (!$("host").value.trim()) throw new Error("Stellar Cyber host is required.");
  if (!$("token").value.trim()) throw new Error("API key / token is required.");
  if (!$("indexName").value.trim()) throw new Error("Index is required.");

  return {
    host: $("host").value.trim(),
    token: $("token").value.trim(),
    verify_tls: $("verifyTls").checked,
    index: $("indexName").value.trim(),
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `HTTP ${response.status}`);
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
  $("summaryIndex").textContent = $("indexName").value.trim() || "—";

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
}

async function testConnection() {
  const button = $("testConnection");
  try {
    if (!$("host").value.trim() || !$("token").value.trim()) throw new Error("Host and token are required.");
    setBusy(button, true, "Testing…");
    setStatus("connectionStatus", "Testing connection…");
    const result = await api("/api/connection/test", {
      method: "POST",
      body: JSON.stringify({
        host: $("host").value.trim(),
        token: $("token").value.trim(),
        verify_tls: $("verifyTls").checked,
        test_index: $("indexName").value.trim() || "aella-ser-*",
      }),
    });
    setStatus("connectionStatus", `Connected. ${result.index} responded${result.took_ms != null ? ` in ${result.took_ms} ms` : ""}.`, "success");
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
    setStatus("queryStatus", `Preview loaded: ${result.rows.length} rows shown.`, "success");
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
}

initialize();
