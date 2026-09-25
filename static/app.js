const $ = (id) => document.getElementById(id);

const state = {
  previewTotal: null,
  previewLatencyMs: null,
  previewBytes: null,
  estimatedBytes: null,
  sourceCatalog: [],
  indexPlan: null,
  indexPlanKey: null,
  indexPlanRequest: 0,
  previewFields: [],
  selectedFields: [],
  activeExport: null,
  relativeMinutes: 1440,
  pendingProfileSources: null,
  pendingSelectedFields: null,
};

const PROFILE_STORAGE_KEY = "stellarDataExporter.profiles.v1";
const QUERY_HISTORY_STORAGE_KEY = "stellarDataExporter.queryHistory.v1";

function isoFromLocal(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

function localInputValue(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 19);
}

function readLocalJson(key, fallback = []) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function writeLocalJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function selectedFormat() {
  return document.querySelector('input[name="format"]:checked')?.value || "csv";
}

function csvDelimiterValue() {
  return $("csvDelimiter")?.value === "tab" ? "\t" : ($("csvDelimiter")?.value || ",");
}

function updateFormatOptions() {
  const csv = selectedFormat() === "csv";
  $("csvOptions")?.classList.toggle("hidden", !csv);
}

function updateRelativePresetUI() {
  document.querySelectorAll(".time-preset").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.minutes) === state.relativeMinutes);
  });
}

function applyRelativeMinutes(minutes) {
  const value = Math.max(1, Number(minutes) || 1);
  const end = new Date();
  const start = new Date(end.getTime() - value * 60 * 1000);
  state.relativeMinutes = value;
  $("startTime").value = localInputValue(start);
  $("endTime").value = localInputValue(end);
  updateRelativePresetUI();
  updateSummary();
  refreshIndexPlan();
}

function markAbsoluteTime() {
  state.relativeMinutes = null;
  updateRelativePresetUI();
}

function humanBytes(bytes) {
  if (bytes == null || !Number.isFinite(Number(bytes))) return "—";
  if (Number(bytes) === 0) return "0 B";
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

function isAdvancedMode() {
  return document.body.classList.contains("mode-advanced");
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

function resetAdvancedDefaults() {
  $("verifyTls").checked = true;
  $("timeField").value = "timestamp";
  if (state.previewFields.length) {
    state.selectedFields = [...state.previewFields];
  }
  document.querySelector('input[name="exportRecords"][value="all"]').checked = true;
  $("recordLimit").value = "100000";
  $("filename").value = "stellar-export";
  $("compress").checked = false;
  $("splitFiles").checked = false;
  $("csvDelimiter").value = ",";
  $("csvHeader").checked = true;
  $("csvBom").checked = false;
  $("csvFlatten").checked = true;
  $("maxFileSizeValue").value = "250";
  $("maxFileSizeUnit").value = "mb";
  $("s3PathStyle").checked = false;
  $("sftpVerifyHostKey").checked = true;
  $("targetRecords").value = "5000";
  $("minimumSlice").value = "1";
  $("resolvedIndices").classList.add("hidden");
  $("toggleActualIndices").textContent = "Show actual indices";
  updateRecordLimitUI();
  updateSplitUI();
  renderFieldSelector();
}

function setUiMode(mode, reset = false) {
  const advanced = mode === "advanced";
  document.body.classList.toggle("mode-basic", !advanced);
  document.body.classList.toggle("mode-advanced", advanced);
  $("basicMode").classList.toggle("active", !advanced);
  $("advancedMode").classList.toggle("active", advanced);
  if (!advanced && reset) resetAdvancedDefaults();
  updateSummary();
}

function outputFilename() {
  const format = selectedFormat();
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
    : lower.endsWith(".ndjson.gz") ? ".ndjson.gz"
    : lower.endsWith(".csv") ? ".csv"
    : lower.endsWith(".json") ? ".json"
    : lower.endsWith(".ndjson") ? ".ndjson"
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
  if (isAdvancedMode() && state.previewFields.length && state.selectedFields.length) {
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

function effectiveExportRecordCount() {
  if (state.previewTotal == null) return null;
  const total = Number(state.previewTotal);
  try {
    const limit = recordLimitValue();
    return limit == null ? total : Math.min(total, limit);
  } catch {
    return total;
  }
}

function estimatedOutputBytes() {
  const records = effectiveExportRecordCount();
  if (records == null || state.estimatedBytes == null || state.previewTotal == null) return null;
  const total = Number(state.previewTotal);
  if (total <= 0) return 0;
  return Math.round(Number(state.estimatedBytes) * (records / total));
}

function renderInspector(plan, target) {
  const requestPath = $("requestPath").textContent;
  const host = $("host").value.trim().replace(/\/$/, "");
  $("finalEndpoint").textContent = host ? `${host}${requestPath}` : requestPath;
  $("inspectorResolvedIndices").textContent = target || "Planning…";
  $("inspectorMatchedRecords").textContent =
    state.previewTotal == null ? "Preview required" : Number(state.previewTotal).toLocaleString();
  $("inspectorPreviewLatency").textContent =
    state.previewLatencyMs == null ? "—" : `${state.previewLatencyMs} ms`;
  $("inspectorPreviewBytes").textContent = humanBytes(state.previewBytes);
  $("inspectorEstimatedOutputSize").textContent = humanBytes(estimatedOutputBytes());

  const selected = state.previewFields.length
    ? state.selectedFields
    : [];
  const selectedText = state.previewFields.length
    ? (selected.length ? `${selected.length}: ${selected.join(", ")}` : "None")
    : "All source fields";
  $("inspectorSelectedFields").textContent = selectedText;
  $("inspectorSelectedFields").title = selectedText;

  let limitText = "All matching records";
  try {
    const limit = recordLimitValue();
    if (limit != null) limitText = `First ${limit.toLocaleString()} records`;
  } catch {
    limitText = "Invalid limit";
  }
  $("inspectorExportLimit").textContent = limitText;

  const targetRecords = Number($("targetRecords").value || 5000);
  $("inspectorAdaptiveSlicing").textContent = "Enabled · time-range bisect";
  $("inspectorTargetRecords").textContent = Number.isFinite(targetRecords)
    ? targetRecords.toLocaleString()
    : "—";

  const exportRecords = effectiveExportRecordCount();
  $("inspectorEstimatedSlices").textContent =
    exportRecords == null || !Number.isFinite(targetRecords) || targetRecords < 1
      ? "Preview required"
      : `~${Math.max(1, Math.ceil(exportRecords / targetRecords)).toLocaleString()}`;

  let maxBytes = null;
  if ($("splitFiles").checked) {
    try {
      maxBytes = splitSizeBytes();
      $("inspectorMaxFileSize").textContent = humanBytes(maxBytes);
    } catch {
      $("inspectorMaxFileSize").textContent = "Invalid";
    }
  } else {
    $("inspectorMaxFileSize").textContent = "No split";
  }

  const outputBytes = estimatedOutputBytes();
  $("inspectorEstimatedFiles").textContent =
    maxBytes && outputBytes != null
      ? `~${Math.max(1, Math.ceil(outputBytes / maxBytes)).toLocaleString()}`
      : "1";
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
  renderInspector(plan, target);
}

function shellQuote(value) {
  return "'" + String(value).split("'").join("'\"'\"'") + "'";
}

function buildRedactedCurl() {
  const host = $("host").value.trim().replace(/\/$/, "") || "<STELLAR-HOST>";
  const endpoint = `${host}${$("requestPath").textContent}`;
  let body = $("effectiveDsl").value.trim();
  if (!body.startsWith("{")) body = "{}";
  const insecure = $("verifyTls").checked ? "" : " -k";
  return [
    `curl${insecure} -X GET ${shellQuote(endpoint)}`,
    `  -H ${shellQuote("Authorization: Bearer <REDACTED>")}`,
    `  -H ${shellQuote("Content-Type: application/json")}`,
    `  --data-raw ${shellQuote(body)}`,
  ].join(" \\\n");
}

async function copyInspectorText(value, label) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    const area = document.createElement("textarea");
    area.value = value;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  $("copyStatus").textContent = `${label} copied`;
  setTimeout(() => {
    if ($("copyStatus").textContent === `${label} copied`) $("copyStatus").textContent = "";
  }, 1800);
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

function setRadioValue(name, value) {
  const input = document.querySelector(`input[name="${name}"][value="${CSS.escape(String(value))}"]`);
  if (input) input.checked = true;
}

function applySourceSelection(sources) {
  const desired = new Set(sources || []);
  const inputs = [...document.querySelectorAll('input[name="source"]')];
  if (!inputs.length) {
    state.pendingProfileSources = [...desired];
    return;
  }
  inputs.forEach((input) => {
    input.checked = desired.has(input.value);
    input.closest(".source-option")?.classList.toggle("selected", input.checked);
  });
  state.pendingProfileSources = null;
}

function nonSecretDestinationProfile() {
  const type = selectedDestinationType();
  if (type === "download") return {type: "download"};
  if (type === "s3") {
    return {
      type: "s3",
      endpoint_url: $("s3Endpoint").value.trim(),
      region: $("s3Region").value.trim(),
      bucket: $("s3Bucket").value.trim(),
      prefix: $("s3Prefix").value.trim(),
      force_path_style: $("s3PathStyle").checked,
    };
  }
  return {
    type: "sftp",
    host: $("sftpHost").value.trim(),
    port: Number($("sftpPort").value || 22),
    username: $("sftpUsername").value.trim(),
    auth_method: $("sftpAuthMethod").value,
    remote_path: $("sftpRemotePath").value.trim() || "/",
    verify_host_key: $("sftpVerifyHostKey").checked,
  };
}

function exportProfileSnapshot() {
  return {
    version: 1,
    host: $("host").value.trim(),
    verify_tls: $("verifyTls").checked,
    sources: selectedSources(),
    time_field: $("timeField").value.trim() || "timestamp",
    time: state.relativeMinutes
      ? {mode: "relative", minutes: state.relativeMinutes}
      : {mode: "absolute", start: $("startTime").value, end: $("endTime").value},
    query_mode: selectedQueryMode(),
    query_dsl: $("queryDsl").value,
    stellar_query: $("stellarQuery").value,
    selected_fields: [...state.selectedFields],
    record_limit: recordLimitValue(),
    format: selectedFormat(),
    compress: $("compress").checked,
    filename: $("filename").value.trim() || "stellar-export",
    split_files: $("splitFiles").checked,
    max_file_size_value: $("maxFileSizeValue").value,
    max_file_size_unit: $("maxFileSizeUnit").value,
    csv_delimiter: $("csvDelimiter").value,
    csv_include_header: $("csvHeader").checked,
    csv_bom: $("csvBom").checked,
    csv_flatten_nested: $("csvFlatten").checked,
    destination: nonSecretDestinationProfile(),
    target_records_per_slice: Number($("targetRecords").value || 5000),
    minimum_slice_ms: Number($("minimumSlice").value || 1),
  };
}

function renderProfiles(selectedId = "") {
  const profiles = readLocalJson(PROFILE_STORAGE_KEY, []);
  $("profileSelect").innerHTML = profiles.length
    ? profiles.map((profile) =>
        `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name)}</option>`
      ).join("")
    : '<option value="">No saved profiles</option>';
  if (selectedId && profiles.some((item) => item.id === selectedId)) {
    $("profileSelect").value = selectedId;
  }
}

function saveProfile() {
  const name = $("profileName").value.trim();
  if (!name) {
    setStatus("profileStatus", "Enter a profile name.", "warning");
    return;
  }
  let snapshot;
  try {
    snapshot = exportProfileSnapshot();
  } catch (error) {
    setStatus("profileStatus", error.message, "error");
    return;
  }
  const profiles = readLocalJson(PROFILE_STORAGE_KEY, []);
  const existing = profiles.find((item) => item.name.toLowerCase() === name.toLowerCase());
  const id = existing?.id || `profile-${Date.now()}`;
  const next = profiles.filter((item) => item.id !== id);
  next.unshift({id, name, updated_at: new Date().toISOString(), settings: snapshot});
  writeLocalJson(PROFILE_STORAGE_KEY, next.slice(0, 30));
  renderProfiles(id);
  setStatus("profileStatus", "Profile saved locally without credentials.", "success");
}

function applyProfileSettings(settings) {
  if (!settings) return;
  $("host").value = settings.host || "";
  $("verifyTls").checked = settings.verify_tls !== false;
  $("timeField").value = settings.time_field || "timestamp";
  applySourceSelection(settings.sources || ["alerts"]);

  if (settings.time?.mode === "relative" && settings.time.minutes) {
    applyRelativeMinutes(settings.time.minutes);
  } else if (settings.time) {
    state.relativeMinutes = null;
    $("startTime").value = settings.time.start || $("startTime").value;
    $("endTime").value = settings.time.end || $("endTime").value;
    updateRelativePresetUI();
  }

  setRadioValue("queryMode", settings.query_mode || "elasticsearch_dsl");
  $("queryDsl").value = settings.query_dsl || '{"query":{"match_all":{}}}';
  $("stellarQuery").value = settings.stellar_query || "";
  state.pendingSelectedFields = Array.isArray(settings.selected_fields)
    ? [...settings.selected_fields]
    : null;

  if (settings.record_limit == null) {
    setRadioValue("exportRecords", "all");
  } else {
    setRadioValue("exportRecords", "limit");
    $("recordLimit").value = String(settings.record_limit);
  }

  setRadioValue("format", settings.format || "csv");
  $("compress").checked = !!settings.compress;
  $("filename").value = settings.filename || "stellar-export";
  $("splitFiles").checked = !!settings.split_files;
  $("maxFileSizeValue").value = settings.max_file_size_value || "250";
  $("maxFileSizeUnit").value = settings.max_file_size_unit || "mb";
  $("csvDelimiter").value = settings.csv_delimiter || ",";
  $("csvHeader").checked = settings.csv_include_header !== false;
  $("csvBom").checked = !!settings.csv_bom;
  $("csvFlatten").checked = settings.csv_flatten_nested !== false;

  const destination = settings.destination || {type: "download"};
  setRadioValue("destination", destination.type || "download");
  if (destination.type === "s3") {
    $("s3Endpoint").value = destination.endpoint_url || "";
    $("s3Region").value = destination.region || "";
    $("s3Bucket").value = destination.bucket || "";
    $("s3Prefix").value = destination.prefix || "";
    $("s3PathStyle").checked = !!destination.force_path_style;
  } else if (destination.type === "sftp") {
    $("sftpHost").value = destination.host || "";
    $("sftpPort").value = String(destination.port || 22);
    $("sftpUsername").value = destination.username || "";
    $("sftpAuthMethod").value = destination.auth_method || "private_key";
    $("sftpRemotePath").value = destination.remote_path || "/";
    $("sftpVerifyHostKey").checked = destination.verify_host_key !== false;
  }

  $("targetRecords").value = String(settings.target_records_per_slice || 5000);
  $("minimumSlice").value = String(settings.minimum_slice_ms || 1);

  updateRecordLimitUI();
  updateSplitUI();
  updateFormatOptions();
  updateQueryModeUI();
  updateSftpAuthUI();
  updateDestinationUI();
  updateSummary();
  refreshIndexPlan();
}

function loadSelectedProfile() {
  const id = $("profileSelect").value;
  const profile = readLocalJson(PROFILE_STORAGE_KEY, []).find((item) => item.id === id);
  if (!profile) {
    setStatus("profileStatus", "Select a saved profile.", "warning");
    return;
  }
  $("profileName").value = profile.name;
  applyProfileSettings(profile.settings);
  setStatus("profileStatus", "Profile loaded. Credentials remain session-only.", "success");
}

function deleteSelectedProfile() {
  const id = $("profileSelect").value;
  if (!id) return;
  const next = readLocalJson(PROFILE_STORAGE_KEY, []).filter((item) => item.id !== id);
  writeLocalJson(PROFILE_STORAGE_KEY, next);
  renderProfiles();
  setStatus("profileStatus", "Profile deleted.", "success");
}

function currentHistoryEntry() {
  return {
    query_mode: selectedQueryMode(),
    query_dsl: $("queryDsl").value,
    stellar_query: $("stellarQuery").value,
    sources: selectedSources(),
    time_field: $("timeField").value.trim() || "timestamp",
  };
}

function historySignature(entry) {
  return JSON.stringify({
    query_mode: entry.query_mode,
    query_dsl: entry.query_dsl,
    stellar_query: entry.stellar_query,
    sources: entry.sources,
    time_field: entry.time_field,
  });
}

function renderQueryHistory(selectedId = "") {
  const items = readLocalJson(QUERY_HISTORY_STORAGE_KEY, []);
  $("queryHistorySelect").innerHTML = items.length
    ? items.map((item) => {
        const raw = item.query_mode === "stellar_lucene" ? item.stellar_query : item.query_dsl;
        const compact = String(raw || "").replace(/\s+/g, " ").slice(0, 80);
        const label = `${item.favorite ? "★ " : ""}${compact || "(empty query)"}`;
        return `<option value="${escapeHtml(item.id)}">${escapeHtml(label)}</option>`;
      }).join("")
    : '<option value="">No query history</option>';
  if (selectedId && items.some((item) => item.id === selectedId)) {
    $("queryHistorySelect").value = selectedId;
  }
  const selected = items.find((item) => item.id === $("queryHistorySelect").value);
  $("favoriteQueryHistory").textContent = selected?.favorite ? "Unfavorite" : "Favorite";
}

function rememberCurrentQuery() {
  const entry = currentHistoryEntry();
  const signature = historySignature(entry);
  const items = readLocalJson(QUERY_HISTORY_STORAGE_KEY, []);
  const existing = items.find((item) => historySignature(item) === signature);
  const id = existing?.id || `query-${Date.now()}`;
  const next = items.filter((item) => item.id !== id);
  next.unshift({
    ...entry,
    id,
    favorite: !!existing?.favorite,
    used_at: new Date().toISOString(),
  });
  writeLocalJson(QUERY_HISTORY_STORAGE_KEY, next.slice(0, 50));
  renderQueryHistory(id);
}

function loadSelectedQueryHistory() {
  const id = $("queryHistorySelect").value;
  const item = readLocalJson(QUERY_HISTORY_STORAGE_KEY, []).find((entry) => entry.id === id);
  if (!item) return;
  setRadioValue("queryMode", item.query_mode || "elasticsearch_dsl");
  $("queryDsl").value = item.query_dsl || '{"query":{"match_all":{}}}';
  $("stellarQuery").value = item.stellar_query || "";
  applySourceSelection(item.sources || ["alerts"]);
  $("timeField").value = item.time_field || "timestamp";
  updateQueryModeUI();
  updateSummary();
  refreshIndexPlan();
}

function toggleSelectedHistoryFavorite() {
  const id = $("queryHistorySelect").value;
  if (!id) return;
  const items = readLocalJson(QUERY_HISTORY_STORAGE_KEY, []);
  const target = items.find((item) => item.id === id);
  if (!target) return;
  target.favorite = !target.favorite;
  items.sort((a, b) => Number(b.favorite) - Number(a.favorite) ||
    String(b.used_at).localeCompare(String(a.used_at)));
  writeLocalJson(QUERY_HISTORY_STORAGE_KEY, items);
  renderQueryHistory(id);
}

function clearQueryHistory() {
  writeLocalJson(QUERY_HISTORY_STORAGE_KEY, []);
  renderQueryHistory();
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

  if (state.pendingSelectedFields) {
    const availableSet = new Set(available);
    state.selectedFields = state.pendingSelectedFields.filter((field) => availableSet.has(field));
    state.pendingSelectedFields = null;
  } else if (!state.previewFields.length) {
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

  const format = selectedFormat();
  const formatLabel = format === "json" ? "JSON Array" : format.toUpperCase();
  $("summaryOutput").textContent = `${formatLabel}${$("compress").checked ? " · gzip" : ""}`;
  $("summarySplit").textContent = $("splitFiles").checked
    ? `${$("maxFileSizeValue").value || "?"} ${$("maxFileSizeUnit").value.toUpperCase()} parts`
    : "Single file";
  $("splitFilenameExample").textContent = numberedExample(outputFilename());
  document.querySelectorAll(".choice").forEach((el) => {
    const radio = el.querySelector('input[name="format"]');
    el.classList.toggle("selected", !!radio?.checked);
  });
  updateFormatOptions();
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
    state.previewLatencyMs = result.took_ms;
    state.previewBytes = result.preview_bytes;
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
    rememberCurrentQuery();
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

function humanDuration(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  if (value < 60) return `${value}s`;
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function renderExportProgress(status) {
  $("exportProgress").classList.remove("hidden");
  $("progressStatus").textContent = status.status || "pending";
  $("progressRecords").textContent = Number(status.records_exported || 0).toLocaleString();
  $("progressBytes").textContent = humanBytes(status.bytes_sent || 0);
  $("progressFiles").textContent = Number(status.files_completed || 0).toLocaleString();
  $("progressQueries").textContent = Number(status.query_count || 0).toLocaleString();
  $("progressRetries").textContent = Number(status.retry_count || 0).toLocaleString();
  $("progressElapsed").textContent = humanDuration(status.elapsed_seconds);
  const rate = Number(status.rate_records_per_second || 0);
  $("progressRate").textContent = `${rate.toFixed(rate >= 10 ? 1 : 2)} rec/s`;
  $("progressRange").textContent =
    status.current_slice_start && status.current_slice_end
      ? `${status.current_slice_start} → ${status.current_slice_end}`
      : "Waiting to start";

  const terminal = ["completed", "failed", "cancelled"].includes(status.status);
  $("cancelExport").disabled = terminal || !!status.cancel_requested || !state.activeExport;
  $("cancelExport").textContent = status.cancel_requested && !terminal ? "Cancelling…" : "Cancel";
}

async function cancelExport() {
  if (!state.activeExport?.cancelUrl) return;
  const button = $("cancelExport");
  try {
    button.disabled = true;
    button.textContent = "Cancelling…";
    const status = await api(state.activeExport.cancelUrl, {method: "POST"});
    renderExportProgress(status);
    if (status.status === "cancelled") {
      setStatus("runStatus", "Export cancelled.", "warning");
    } else {
      setStatus("runStatus", "Cancellation requested. Finishing the current operation safely…", "warning");
    }
  } catch (error) {
    setStatus("runStatus", error.message, "error");
    button.disabled = false;
    button.textContent = "Cancel";
  }
}

async function pollExport(statusUrl) {
  for (;;) {
    const status = await api(statusUrl);
    renderExportProgress(status);
    if (status.status === "completed") {
      setStatus(
        "runStatus",
        `Completed: ${status.result || "export finished"} · ${Number(status.records_exported || 0).toLocaleString()} records · ${humanBytes(status.bytes_sent)} transferred.`,
        "success",
      );
      return status;
    }
    if (status.status === "cancelled") {
      setStatus("runStatus", "Export cancelled.", "warning");
      return status;
    }
    if (status.status === "failed") {
      throw new Error(status.error || "Export failed.");
    }
    const verb = status.cancel_requested ? "Cancelling" : status.status === "pending" ? "Preparing" : "Exporting";
    setStatus(
      "runStatus",
      `${verb}… ${Number(status.records_exported || 0).toLocaleString()} records · ${humanBytes(status.bytes_sent)} transferred.`,
    );
    await wait(500);
  }
}

function formatHistoryDate(epochSeconds) {
  if (!epochSeconds) return "—";
  return new Date(Number(epochSeconds) * 1000).toLocaleString();
}

function formatHistoryRange(summary = {}) {
  if (!summary.start || !summary.end) return "—";
  const start = new Date(summary.start);
  const end = new Date(summary.end);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "—";
  return `${start.toLocaleString()} → ${end.toLocaleString()}`;
}

function renderExportHistory(items) {
  const body = $("exportHistoryBody");
  if (!body) return;
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="8" class="muted">No export jobs yet.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const summary = item.summary || {};
    const sources = Array.isArray(summary.sources) ? summary.sources.join(", ") : "—";
    const output = `${String(summary.format || "—").toUpperCase()}${summary.compress ? " + gzip" : ""}`;
    const destination = String(summary.destination_type || "—").toUpperCase();
    const result = item.error || item.result || "—";
    const status = String(item.status || "unknown");
    const created = formatHistoryDate(item.created_at);
    const range = formatHistoryRange(summary);
    return `<tr>
      <td title="${escapeHtml(created)}">${escapeHtml(created)}</td>
      <td><span class="history-status history-${escapeHtml(status)}">${escapeHtml(status)}</span></td>
      <td title="${escapeHtml(sources)}">${escapeHtml(sources)}</td>
      <td title="${escapeHtml(range)}">${escapeHtml(range)}</td>
      <td>${escapeHtml(output)}</td>
      <td>${escapeHtml(destination)}</td>
      <td>${Number(item.records_exported || 0).toLocaleString()} / ${escapeHtml(humanBytes(item.bytes_sent || 0))}</td>
      <td title="${escapeHtml(result)}">${escapeHtml(result)}</td>
    </tr>`;
  }).join("");
}

async function loadExportHistory() {
  const body = $("exportHistoryBody");
  if (!body) return;
  try {
    const response = await api("/api/export/history?limit=50");
    renderExportHistory(response.jobs || []);
  } catch (error) {
    body.innerHTML = `<tr><td colspan="8" class="status error">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function runExport() {
  const button = $("runExport");
  try {
    setBusy(button, true, "Running export…");
    setStatus("runStatus", "Creating export job…");
    if (isAdvancedMode() && state.previewFields.length && !state.selectedFields.length) {
      throw new Error("Select at least one export field.");
    }
    const payload = {
      ...basePayload(),
      selected_fields: isAdvancedMode() && state.previewFields.length ? [...state.selectedFields] : null,
      record_limit: recordLimitValue(),
      format: selectedFormat(),
      compress: $("compress").checked,
      filename: $("filename").value.trim() || "stellar-export",
      max_file_size_bytes: splitSizeBytes(),
      csv_delimiter: csvDelimiterValue(),
      csv_include_header: $("csvHeader").checked,
      csv_bom: $("csvBom").checked,
      csv_flatten_nested: $("csvFlatten").checked,
      destination: destinationPayload(),
    };
    const result = await api("/api/export/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    state.activeExport = {
      jobId: result.job_id,
      statusUrl: result.status_url,
      cancelUrl: result.cancel_url,
    };
    renderExportProgress({
      status: "pending",
      records_exported: 0,
      bytes_sent: 0,
      files_completed: 0,
      query_count: 0,
      retry_count: 0,
      elapsed_seconds: 0,
      rate_records_per_second: 0,
    });

    if (result.mode === "download") {
      $("downloadFrame").src = result.download_url;
      setStatus("runStatus", "Download started. Tracking export progress…");
    }
    await pollExport(result.status_url);
  } catch (error) {
    setStatus("runStatus", error.message, "error");
  } finally {
    state.activeExport = null;
    $("cancelExport").disabled = true;
    setBusy(button, false);
    await loadExportHistory();
  }
}

function renderSources(items) {
  const grid = $("sourceGrid");
  const desired = new Set(state.pendingProfileSources || ["alerts"]);
  grid.innerHTML = items.map((item, index) => {
    const checked = desired.has(item.id) ? "checked" : "";
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
  state.pendingProfileSources = null;
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
  state.relativeMinutes = 1440;
  updateRelativePresetUI();

  $("basicMode").addEventListener("click", () => setUiMode("basic", true));
  $("advancedMode").addEventListener("click", () => setUiMode("advanced"));
  $("testConnection").addEventListener("click", testConnection);
  $("testDestination").addEventListener("click", () => testRemoteDestination("destinationStatus", "testDestination"));
  $("testSftpDestination").addEventListener("click", () => testRemoteDestination("sftpDestinationStatus", "testSftpDestination"));
  $("validateQuery").addEventListener("click", validateQuery);
  $("previewQuery").addEventListener("click", previewQuery);
  $("copyDsl").addEventListener("click", () => copyInspectorText($("effectiveDsl").value, "DSL"));
  $("copyRequestPath").addEventListener("click", () => copyInspectorText($("requestPath").textContent, "Request path"));
  $("copyCurl").addEventListener("click", () => copyInspectorText(buildRedactedCurl(), "cURL"));
  $("runExport").addEventListener("click", runExport);
  $("cancelExport").addEventListener("click", cancelExport);
  $("refreshExportHistory").addEventListener("click", loadExportHistory);
  $("saveProfile").addEventListener("click", saveProfile);
  $("loadProfile").addEventListener("click", loadSelectedProfile);
  $("deleteProfile").addEventListener("click", deleteSelectedProfile);
  $("loadQueryHistory").addEventListener("click", loadSelectedQueryHistory);
  $("favoriteQueryHistory").addEventListener("click", toggleSelectedHistoryFavorite);
  $("clearQueryHistory").addEventListener("click", clearQueryHistory);
  $("queryHistorySelect").addEventListener("change", () => renderQueryHistory($("queryHistorySelect").value));
  $("splitFiles").addEventListener("change", updateSplitUI);
  document.querySelectorAll('input[name="format"]').forEach((radio) => {
    radio.addEventListener("change", updateFormatOptions);
  });
  document.querySelectorAll(".time-preset").forEach((button) => {
    button.addEventListener("click", () => applyRelativeMinutes(Number(button.dataset.minutes)));
  });
  $("applyRelative").addEventListener("click", () => {
    const value = Number($("relativeValue").value);
    const unit = $("relativeUnit").value;
    const multiplier = unit === "days" ? 1440 : unit === "hours" ? 60 : 1;
    if (!Number.isFinite(value) || value < 1) {
      setStatus("queryStatus", "Relative time must be a positive number.", "warning");
      return;
    }
    applyRelativeMinutes(value * multiplier);
  });
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
    $(id).addEventListener("input", () => {
      markAbsoluteTime();
      refreshIndexPlan();
    });
    $(id).addEventListener("change", () => {
      markAbsoluteTime();
      refreshIndexPlan();
    });
  }

  document.querySelectorAll("input,textarea,select").forEach((el) => {
    el.addEventListener("input", updateSummary);
    el.addEventListener("change", updateSummary);
  });

  document.querySelectorAll('input[name="destination"]').forEach((radio) => {
    radio.addEventListener("change", updateDestinationUI);
  });

  renderProfiles();
  renderQueryHistory();
  updateSftpAuthUI();
  updateRecordLimitUI();
  updateFormatOptions();
  updateQueryModeUI();
  setUiMode("basic");
  updateSummary();
  loadDataSources();
  loadExportHistory();
}

initialize();
