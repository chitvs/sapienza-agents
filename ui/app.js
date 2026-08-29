const ENDPOINTS = {
  orchestrator: "/api/orchestrator/query",
  kg: "/api/kg/query",
  multiapi: "/api/multiapi/query",
  planner: "/api/planner/query",
  plannerStream: "/api/planner/query/stream",
};

const META_KEYS = ["_provenance", "_sources"];

const PROVIDER_LABELS = {
  ollama: "Ollama (locale)",
  gemini: "Gemini",
  openai_compatible: "OpenRouter",
};

const form = document.getElementById("form");
const output = document.getElementById("output");
const submit = document.getElementById("submit");
const modeSelect = document.getElementById("mode");
const kgSelect = document.getElementById("kg");
const newChatBtn = document.getElementById("newChat");
const chatListEl = document.getElementById("chatList");
const plannerBanner = document.getElementById("plannerBanner");
const advProvider = document.getElementById("advProvider");
const advModel = document.getElementById("advModel");
const advContext = document.getElementById("advContext");
const advDomain = document.getElementById("advDomain");
const advConstraints = document.getElementById("advConstraints");
const advToolsWrap = document.getElementById("advToolsWrap");
const advTools = document.getElementById("advTools");

let advPanelLoaded = false;
let allModels = [];

// Funzione di utilità per sincronizzare le checkbox dei tool
function syncContextUI() {
  if (!advToolsWrap || !advContext) return;
  advToolsWrap.style.display = advContext.value === "deterministic" ? "flex" : "none";
}

if (advContext) {
  advContext.addEventListener("change", syncContextUI);
}

// Aggiorna il menu a tendina dei modelli in base al provider
function updateModelDropdown() {
  if (!advModel || !advProvider) return;
  const selectedProvider = advProvider.value;
  advModel.innerHTML = '<option value="">Auto</option>';

  const filteredModels = selectedProvider
    ? allModels.filter(m => m.provider === selectedProvider)
    : allModels;

  for (const m of filteredModels) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.model;
    advModel.appendChild(opt);
  }
}

if (advProvider) {
  advProvider.addEventListener("change", updateModelDropdown);
}

// Caricamento asincrono delle opzioni per il pannello avanzato
async function loadAdvPanelData() {
  if (advPanelLoaded) return;

  try {
    const res = await fetch("/api/planner/models");
    if (res.ok) {
      const data = await res.json();
      allModels = Array.isArray(data.models) ? data.models : [];

      if (advProvider) {
        const uniqueProviders = [...new Set(allModels.map(m => m.provider))];
        advProvider.innerHTML = '<option value="">Auto / Tutti</option>';
        uniqueProviders.forEach(provider => {
          const opt = document.createElement("option");
          opt.value = provider;
          opt.textContent = PROVIDER_LABELS[provider] || provider;
          advProvider.appendChild(opt);
        });
      }

      updateModelDropdown();
    }
  } catch (err) {
    console.error("Errore nel caricamento dei modelli:", err);
  }

  try {
    const res = await fetch("/api/planner/tools");
    if (res.ok && advTools) {
      const tools = await res.json();
      advTools.innerHTML = tools.map(t =>
        `<label><input type="checkbox" value="${escapeAttr(t.name)}" checked> ${escape(t.name)}</label>`
      ).join("");
    }
  } catch (err) {
    console.error("Errore nel caricamento dei tool:", err);
  }

  advPanelLoaded = true;
  syncContextUI();
}

function renderSidebar() {
  if (!chatListEl) return;

  if (!sessionState.sessions.length) {
    chatListEl.innerHTML =
      "<p class='msg' style='margin-top:0'>nessuna chat ancora.</p>";
    return;
  }

  chatListEl.innerHTML = sessionState.sessions.map(s => {
    const active = s.id === sessionState.activeId ? " active" : "";
    const label = s.title || "nuova conversazione";

    return `
      <div class="chat-item${active}" data-id="${escapeAttr(s.id)}">
        <span class="chat-item-title">${escape(label)}</span>
        <button
          type="button"
          class="chat-delete"
          data-delete-id="${escapeAttr(s.id)}"
          aria-label="Elimina conversazione"
          title="Elimina conversazione"
        >×</button>
      </div>
    `;
  }).join("");
}

function renderPlannerBanner() {
  if (!plannerBanner) return;
  const session = activeSession();
  const previousPlan = getLatestPlannerPlan(session);
  if (previousPlan) {
    plannerBanner.textContent = "Questa conversazione ha già un piano: le richieste verranno trattate come modifiche. Per un piano completamente diverso, apri una nuova chat.";
    plannerBanner.hidden = false;
  } else {
    plannerBanner.hidden = true;
  }
}

// ---- Gestione Sessioni ----
const SESSIONS_KEY = "minerva_planner_sessions";

function loadSessionState() {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && Array.isArray(parsed.sessions) ? parsed : { activeId: null, sessions: [] };
  } catch {
    return { activeId: null, sessions: [] };
  }
}

let sessionState = loadSessionState();

function saveSessionState() {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessionState));
}

function activeSession() {
  return sessionState.sessions.find(s => s.id === sessionState.activeId) || null;
}

function getLatestPlannerPlan(session) {
  if (!session || !Array.isArray(session.messages)) {
    return null;
  }

  for (let i = session.messages.length - 1; i >= 0; i--) {
    const message = session.messages[i];

    if (
      message &&
      message.role === "assistant" &&
      message.type === "planner" &&
      message.data &&
      Array.isArray(message.data.days) &&
      message.data.days.length > 0
    ) {
      return message.data;
    }
  }

  return null;
}

function addSessionMessage(message) {
  const session = activeSession();
  if (!session) return;

  if (!Array.isArray(session.messages)) {
    session.messages = [];
  }

  session.messages.push(message);

  if (
    message.role === "user" &&
    !session.title &&
    message.content
  ) {
    session.title =
      message.content.length > 42
        ? message.content.slice(0, 42) + "…"
        : message.content;
  }

  saveSessionState();
  renderSidebar();
}

function renderConversation(session) {
  if (!output) return;

  output.innerHTML = "";

  if (!session || !Array.isArray(session.messages)) {
    return;
  }

  for (const message of session.messages) {
    if (message.role === "user") {
      const userMsg = document.createElement("div");
      userMsg.className = "chat-msg user-msg";
      userMsg.innerHTML = `<div class="msg-content">${escape(message.content || "")}</div>`;
      output.appendChild(userMsg);
      continue;
    }

    if (message.role === "assistant") {
      const assistantMsg = document.createElement("div");
      assistantMsg.className = "chat-msg assistant-msg";

      if (message.type === "planner") {
        assistantMsg.innerHTML = renderPlanner(message.data);
      } else if (message.type === "kg") {
        assistantMsg.innerHTML = renderKg(message.data);
      } else if (message.type === "multiapi") {
        assistantMsg.innerHTML = renderMultiapi(message.data);
      } else if (message.type === "orchestrator") {
        assistantMsg.innerHTML = renderOrchestrator(message.data);
      } else if (message.type === "error") {
        assistantMsg.innerHTML =
          `<p class="err">${escape(message.content || "errore sconosciuto")}</p>`;
      } else {
        assistantMsg.innerHTML =
          `<div class="msg-content">${escape(message.content || "")}</div>`;
      }

      output.appendChild(assistantMsg);
    }
  }

  output.scrollTop = output.scrollHeight;
}

function createSession() {
  const session = {
    id: crypto.randomUUID(),
    title: null,
    messages: []
  };

  sessionState.sessions.unshift(session);
  sessionState.activeId = session.id;

  saveSessionState();

  if (output) output.innerHTML = "";

  const q = document.getElementById("question");
  if (q) q.value = "";

  renderSidebar();
  renderPlannerBanner();
}

function setActiveSession(id) {
  const session = sessionState.sessions.find(s => s.id === id);
  if (!session) return;

  sessionState.activeId = id;
  saveSessionState();

  const q = document.getElementById("question");
  if (q) q.value = "";

  renderSidebar();
  renderPlannerBanner();
  renderConversation(session);
}

function deleteSession(id) {
  const index = sessionState.sessions.findIndex(s => s.id === id);
  if (index === -1) return;

  const wasActive = sessionState.activeId === id;

  sessionState.sessions.splice(index, 1);

  if (wasActive) {
    if (sessionState.sessions.length) {
      sessionState.activeId = sessionState.sessions[0].id;
    } else {
      sessionState.activeId = null;
    }
  }

  saveSessionState();

  if (!sessionState.sessions.length) {
    createSession();
    return;
  }

  renderSidebar();
  renderConversation(activeSession());
  renderPlannerBanner();

  const q = document.getElementById("question");
  if (q) q.value = "";
}

function updateSessionAfterPlannerResponse(question, data) {
  const session = activeSession();
  if (!session) return;

  if (!Array.isArray(session.messages)) {
    session.messages = [];
  }

  if (!session.title) {
    session.title =
      question.length > 42
        ? question.slice(0, 42) + "…"
        : question;
  }

  session.messages.push({
    role: "assistant",
    type: "planner",
    data: data
  });

  saveSessionState();
  renderSidebar();
  renderPlannerBanner();
}

function renderToolCalls(trace) {
  if (!trace || !trace.length) return "";
  
  const steps = trace.map(t => {
    const thought = t.thought ? `<div><strong>Ragionamento:</strong> ${escape(t.thought)}</div>` : "";
    const action = t.tool ? `<div><strong>Azione:</strong> <code>${escape(t.tool)}(${escape(t.tool_input)})</code></div>` : "";
    const obsObj = t.observation || {};
    const obsTitle = obsObj.error ? "Errore" : "Osservazione (Dati Ricevuti)";
    const obsBody = renderRaw(obsTitle, obsObj);
    
    return `<div class="react-step">
      <div class="react-step-header">Step ${t.step}</div>
      <div class="react-step-body">
        ${thought}
        ${action}
        ${obsBody}
      </div>
    </div>`;
  }).join("");

  return `<details class="react-inspector">
    <summary> Ispettore di Ragionamento (ReAct Trace)</summary>
    <div class="react-trace">${steps}</div>
  </details>`;
}

function renderPlanner(data) {
  if (!data) return "";
  if (data.error) return `<p class="err">agente planner non raggiungibile: ${escape(data.error)}</p>`;
  const meta = renderMeta([
    ["dominio", data.domain || "?"],
    ["giorni", (data.days || []).length],
    ["confidenza", (data.confidence ?? 0).toFixed(2)],
    ["tempo", formatSeconds(data.execution_time_ms)],
    ...(data.replanned ? [["stato", "piano aggiornato"]] : []),
  ]);
  if (!data.days || !data.days.length) {
    return meta + `<p class='msg'>${escape(data.summary || "nessun piano generato.")}</p>`;
  }
  const head = `<div class="panel"><strong>${escape(data.title)}</strong>` +
    (data.summary ? `<p>${escape(data.summary)}</p>` : "") + `</div>`;
  const days = data.days.map(renderPlanDay).join("");
  const legend = renderCategoryLegend(data.days);
  const reactTraceHtml = renderToolCalls(data.tool_calls);
  
  return meta + head + legend + `<div class="plan-days">${days}</div>` + renderContingencyNotes(data.contingency_notes) + reactTraceHtml + renderRaw("dati grezzi", data);
}

function timelineIcon(data) {
  if (data.status === "tool_completed") return data.tool_status === "error" ? "✗" : "✓";
  if (data.status === "correcting") return "⟳";
  if (data.status === "domain_classified" || data.status === "completed") return "✓";
  return "▸";
}

async function runPlannerStream(body, container) {
  const wrap = document.createElement("div");
  const timeline = document.createElement("div");
  timeline.className = "timeline";
  wrap.appendChild(timeline);
  container.appendChild(wrap);

  const response = await fetch(ENDPOINTS.plannerStream, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok || !(response.headers.get("content-type") || "").includes("text/event-stream")) {
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); } catch {
      throw new Error(`errore ${response.status}: ${raw.trim().slice(0, 200) || "risposta vuota"}`);
    }
    throw new Error(formatDetail(data.detail) || `errore ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", result = null, streamError = null, stepCount = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const eventLine = block.split("\n").find(l => l.startsWith("event:"));
      const dataLine = block.split("\n").find(l => l.startsWith("data:"));
      if (!eventLine || !dataLine) continue;
      const data = JSON.parse(dataLine.slice(5).trim());
      const evt = eventLine.slice(6).trim();

      if (evt === "progress") {
        stepCount++;
        const line = document.createElement("div");
        line.className = "timeline-item";
        line.innerHTML = `<span class="timeline-icon">${timelineIcon(data)}</span><span>${escape(data.message)}</span>`;
        timeline.appendChild(line);
        if (output) output.scrollTop = output.scrollHeight;
      } else if (evt === "result") {
        result = data;
      } else if (evt === "error") {
        streamError = data.message || "errore sconosciuto";
      }
    }
  }

  const details = document.createElement("details");
  details.className = "timeline-details";
  const summary = document.createElement("summary");
  if (streamError) {
    summary.textContent = `✗ elaborazione interrotta — ${stepCount} passaggi`;
    details.open = true;
  } else {
    const time = result ? formatSeconds(result.execution_time_ms) : "";
    summary.textContent = `✓ piano generato${time ? ` in ${time}` : ""} — ${stepCount} passaggi`;
    details.open = false;
  }
  details.appendChild(summary);
  wrap.insertBefore(details, timeline);
  details.appendChild(timeline);

  if (streamError) throw new Error(streamError);
  return result;
}

if (chatListEl) {
  chatListEl.addEventListener("click", event => {
    const deleteButton = event.target.closest(".chat-delete");

    if (deleteButton) {
      event.stopPropagation();

      const id = deleteButton.dataset.deleteId;

      if (confirm("Eliminare questa conversazione?")) {
        deleteSession(id);
      }

      return;
    }

    const item = event.target.closest(".chat-item");

    if (item) {
      setActiveSession(item.dataset.id);
    }
  });
}

if (newChatBtn) {
  newChatBtn.addEventListener("click", createSession);
}

function syncModeUI() {
  const mode = modeSelect ? modeSelect.value : "orchestrator";
  const isPlanner = mode === "planner";

  document.body.dataset.mode = mode;

  if (isPlanner) {
    loadAdvPanelData();
    renderPlannerBanner();
    syncContextUI();
  } else {
    if (plannerBanner) plannerBanner.hidden = true;
  }
}

if (modeSelect) {
  modeSelect.addEventListener("change", syncModeUI);
}

function escape(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text) {
  return escape(text).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function formatDetail(detail) {
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || JSON.stringify(item)).join("; ");
  }
  return typeof detail === "string" ? detail : detail && JSON.stringify(detail);
}

function safeUrl(uri) {
  try {
    const parsed = new URL(String(uri));
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function renderMeta(entries) {
  const cells = entries.map(([label, value]) => `<span>${escape(label)}: ${escape(value)}</span>`);
  return `<div class="meta">${cells.join("")}</div>`;
}

function formatSeconds(ms) {
  return typeof ms === "number" ? `${(ms / 1000).toFixed(1)}s` : "?";
}

function columnsOf(rows) {
  const seen = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!META_KEYS.includes(key) && !seen.includes(key)) seen.push(key);
    }
  }
  return seen;
}

function renderCell(row, column) {
  const value = row[column];
  if (value === null || value === undefined) return "";
  const text = escape(String(value));
  const uri = row._sources ? safeUrl(row._sources[column]) : null;
  return uri
    ? `${text}<a class="src" href="${escapeAttr(uri)}" target="_blank" rel="noopener">fonte</a>`
    : text;
}

function renderTable(rows) {
  const columns = columnsOf(rows);
  if (!columns.length) return "<p class='msg'>nessun valore restituito.</p>";
  const head = columns.map(c => `<th>${escape(c)}</th>`).join("");
  const body = rows.map(row =>
    "<tr>" + columns.map(c => `<td>${renderCell(row, c)}</td>`).join("") + "</tr>"
  ).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderRaw(title, data) {
  if (!data) return "";
  return `<details><summary>${escape(title)}</summary><pre>${escape(JSON.stringify(data, null, 2))}</pre></details>`;
}

function renderKg(data) {
  if (!data) return "";
  if (data.error) return `<p class="err">agente kg non raggiungibile: ${escape(data.error)}</p>`;

  const meta = renderMeta([
    ["fonte", data.target_kg || "?"],
    ["risultati", data.count ?? 0],
    ["confidenza", (data.confidence ?? 0).toFixed(2)],
    ["tempo", formatSeconds(data.execution_time_ms)],
    ...(data.cached ? [["cache", "risultato riusato"]] : []),
  ]);
  const table = (data.count && data.results)
    ? renderTable(data.results)
    : "<p class='msg'>nessun risultato.</p>";
  const query = data.generated_query
    ? `<details><summary>query generata</summary><pre>${escape(data.generated_query)}</pre></details>`
    : "";
  return meta + table + query;
}

const NUM = new Intl.NumberFormat("it-IT");
const DATE_FMT = new Intl.DateTimeFormat("it-IT", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});

function formatDate(iso) {
  if (typeof iso !== "string") return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return DATE_FMT.format(new Date(+m[1], +m[2] - 1, +m[3]));
}

function weatherIcon(code) {
  if (code === 0) return "☀️";
  if (code === 1) return "🌤️";
  if (code === 2) return "⛅";
  if (code === 3) return "☁️";
  if (code === 45 || code === 48) return "🌫️";
  if (code >= 51 && code <= 57) return "🌦️";
  if (code >= 61 && code <= 67) return "🌧️";
  if (code >= 71 && code <= 77) return "❄️";
  if (code >= 80 && code <= 82) return "🌧️";
  if (code === 85 || code === 86) return "🌨️";
  if (code >= 95) return "⛈️";
  return "🌡️";
}

function flagUrl(code, size) {
  if (typeof code !== "string" || !/^[A-Za-z]{2}$/.test(code)) return "";
  return `https://flagcdn.com/${size || "w40"}/${code.toLowerCase()}.png`;
}

function currencyFlag(currency) {
  if (typeof currency !== "string" || currency.length < 3) return "";
  if (currency.toUpperCase() === "EUR") return flagUrl("eu");
  return flagUrl(currency.slice(0, 2));
}

// onerror: una bandiera assente su flagcdn si rimuove invece di restare rotta
function flagImg(url, alt, cls) {
  if (!url) return "";
  return `<img class="${cls || "flag"}" src="${escape(url)}" alt="${escape(alt)}" onerror="this.remove()">`;
}

function cardHead(title, subtitle, flag) {
  return `<div class="card-head">${flag || ""}<div class="card-head-text">` +
    `<div class="card-name">${escape(title)}</div>` +
    (subtitle ? `<div class="card-sub">${escape(subtitle)}</div>` : "") +
    `</div></div>`;
}

function statList(stats) {
  const cells = stats
    .filter(([, value]) => value !== "" && value !== null && value !== undefined)
    .map(([label, value]) =>
      `<div class="stat"><span class="stat-label">${escape(label)}</span>` +
      `<span class="stat-value">${escape(String(value))}</span></div>`);
  return cells.length ? `<div class="stats">${cells.join("")}</div>` : "";
}

function tagGroup(label, values) {
  const list = (values || []).filter(v => v !== null && v !== undefined && v !== "");
  if (!list.length) return "";
  const tags = list.map(v => `<span class="tag">${escape(String(v))}</span>`).join("");
  return `<div class="tag-row"><span class="stat-label">${escape(label)}</span><div>${tags}</div></div>`;
}

// ---- una card dedicata per ogni tipo di risposta ----

// oltre dopodomani i nomi relativi diventano ambigui: si usa la data
function dayLabel(daysAhead, iso) {
  const nomi = ["oggi", "domani", "dopodomani"];
  if (typeof daysAhead === "number" && nomi[daysAhead]) return nomi[daysAhead];
  return formatDate(iso);
}

function cardWeather(r) {
  const flag = flagImg(flagUrl(r.country_code), r.country || "");
  const isForecast = r.kind === "forecast";

  // senza il giorno, una previsione sembrerebbe il meteo attuale
  const sub = isForecast
    ? [r.country, dayLabel(r.days_ahead, r.date)].filter(Boolean).join(" · ")
    : (r.country || "");
  const head = cardHead(r.city || "località", sub, flag);

  const heroValue = isForecast ? r.temperature_max_c : r.temperature_c;
  const hero = `<div class="hero">` +
    `<span class="hero-icon">${weatherIcon(r.weather_code)}</span>` +
    `<div class="hero-text">` +
    `<div class="hero-value">${heroValue === null || heroValue === undefined ? "?" : escape(String(heroValue))}<span class="hero-unit">&deg;C</span></div>` +
    `<div class="hero-label">${escape(r.condition || "")}</div>` +
    `</div></div>`;

  const stats = isForecast
    ? statList([
        ["minima", r.temperature_min_c != null ? `${r.temperature_min_c} °C` : ""],
        ["massima", r.temperature_max_c != null ? `${r.temperature_max_c} °C` : ""],
        ["prob. pioggia", r.precipitation_probability_percent != null ? `${r.precipitation_probability_percent} %` : ""],
        ["alba", r.sunrise || ""],
        ["tramonto", r.sunset || ""],
      ])
    : statList([
        ["percepita", r.apparent_temperature_c != null ? `${r.apparent_temperature_c} °C` : ""],
        ["umidità", r.humidity_percent != null ? `${r.humidity_percent} %` : ""],
        ["vento", r.wind_speed_kmh != null ? `${r.wind_speed_kmh} km/h` : ""],
      ]);

  return `<div class="card">${head}${hero}${stats}</div>`;
}

function cardExchange(r) {
  const base = r.base || "?";
  const quote = r.quote || "";
  const head = `<div class="card-head">` +
    flagImg(currencyFlag(base), base) +
    `<div class="card-head-text">` +
    `<div class="card-name">${escape(base)}${quote ? " &rarr; " + escape(quote) : ""}</div>` +
    `<div class="card-sub">tasso di cambio</div></div>` +
    flagImg(currencyFlag(quote), quote) + `</div>`;
  // con un importo il dato principale è la conversione, non il tasso
  const amount = typeof r.amount === "number" ? r.amount : 1;
  const isConversion = amount !== 1 && typeof r.converted === "number";
  const heroValue = isConversion ? r.converted : (r.rates ?? "?");
  const heroLabel = isConversion
    ? `${NUM.format(amount)} ${base}`
    : `per 1 ${base}`;

  const hero = `<div class="hero">` +
    `<div class="hero-text">` +
    `<div class="hero-value">${escape(String(heroValue))}` +
    (quote ? `<span class="hero-unit">${escape(quote)}</span>` : "") + `</div>` +
    `<div class="hero-label">${escape(heroLabel)}</div>` +
    `</div></div>`;

  const stats = statList([
    ...(isConversion ? [["tasso", `1 ${base} = ${r.rates} ${quote}`]] : []),
    // la data usata può differire da quella chiesta (giorni senza fixing)
    ...(r.requested_date ? [["richiesto per", formatDate(r.requested_date)]] : []),
    ["aggiornato al", formatDate(r.date)],
  ]);
  return `<div class="card">${head}${hero}${stats}</div>`;
}

function cardCountry(r) {
  const flag = flagImg(r.flag_png, `bandiera ${r.name || ""}`, "flag flag-lg");
  const native = r.native_name && r.native_name !== r.name ? r.native_name : "";
  const area = [r.subregion, r.region].filter(Boolean)[0] || "";
  const head = `<div class="card-head">${flag}<div class="card-head-text">` +
    `<div class="card-name card-name-lg">${escape(r.name || "paese")}</div>` +
    (native ? `<div class="card-sub">${escape(native)}</div>` : "") +
    (area ? `<div class="card-sub">${escape(area)}</div>` : "") +
    `</div></div>`;
  const capital = Array.isArray(r.capital) ? r.capital.join(", ") : (r.capital || "");
  const stats = statList([
    ["capitale", capital],
    ["popolazione", r.population ? NUM.format(r.population) : ""],
    ["superficie", r.area_km2 ? `${NUM.format(r.area_km2)} km²` : ""],
  ]);
  const currencies = (r.currencies || []).map(c =>
    typeof c === "string" ? c : [c.code, c.symbol ? `(${c.symbol})` : ""].filter(Boolean).join(" "));
  const tags = tagGroup("lingue", r.languages) +
    tagGroup("valute", currencies) +
    tagGroup("fusi orari", r.timezones) +
    tagGroup("confini", r.borders);
  return `<div class="card">${head}${stats}${tags}</div>`;
}

function cardTime(r) {
  const head = cardHead(r.city || "località", "", flagImg(flagUrl(r.country_code), r.city || ""));
  const hero = `<div class="hero">` +
    `<span class="hero-icon">🕒</span>` +
    `<div class="hero-text">` +
    `<div class="hero-value hero-clock">${escape(r.time || "--:--:--")}</div>` +
    `<div class="hero-label">${escape(formatDate(r.date))}</div>` +
    `</div></div>`;
  const stats = statList([
    ["fuso orario", r.timezone || ""],
    ["offset UTC", r.utc_offset || ""],
    ["sigla", r.abbreviation || ""],
    ["ora legale", r.dst ? "sì" : "no"],
  ]);
  return `<div class="card">${head}${hero}${stats}</div>`;
}

const CARD_BY_INTENT = {
  weather: cardWeather,
  exchange_rate: cardExchange,
  country_info: cardCountry,
  time_info: cardTime,
};

function renderMultiapi(data) {
  if (!data) return "";
  // "error" senza risultati = agente irraggiungibile; con risultati = provider falliti
  if (data.error && !(data.results || []).length) {
    return `<p class="err">agente multiapi non raggiungibile: ${escape(data.error)}</p>`;
  }

  const intentLabels = {
    weather: "🌤 Meteo",
    exchange_rate: "💱 Cambio valute",
    country_info: "🌍 Info paese",
    time_info: "🕒 Ora locale",
    unknown: "❓ Intent non riconosciuto",
  };

  const intentLabel = intentLabels[data.intent] || data.intent || "risultato";
  const meta = renderMeta([
    ["tipo", intentLabel],
    ["risultati", data.count ?? 0],
    ["confidenza", (data.confidence ?? 0).toFixed(2)],
    ["tempo", formatSeconds(data.execution_time_ms)],
  ]);

  // la pipeline risponde a un intent per volta: gli altri vanno dichiarati
  const etichette = {
    weather: "meteo", exchange_rate: "cambio valute",
    country_info: "informazioni sul paese", time_info: "ora locale",
  };
  const ignorati = (data.ignored_intents || []).map(i => etichette[i] || i);
  const avviso = ignorati.length
    ? `<p class="msg">Ho risposto solo alla parte su <strong>${escape(etichette[data.intent] || data.intent)}</strong>. ` +
      `Non ho trattato: ${escape(ignorati.join(", "))}. Prova a chiederlo in una domanda separata.</p>`
    : "";

  const results = data.results || [];
  if (!results.length) return meta + avviso + "<p class='msg'>nessun risultato trovato.</p>";

  const failed = results.filter(r => r && r.error);
  if (failed.length === results.length) {
    return meta + avviso + failed.map(r => `<p class="err">${escape(r.error)}</p>`).join("");
  }

  // la card si sceglie per singolo risultato: una domanda su più temi produce
  // risultati di forma diversa, ognuno con il proprio "intent"
  const content = results.map(r => {
    if (r && r.error) return `<p class="err">${escape(r.error)}</p>`;
    const card = CARD_BY_INTENT[(r && r.intent) || data.intent];
    return card ? card(r) : renderTable([r]);
  }).join("");

  // i campi non mostrati nelle card restano comunque consultabili
  return meta + avviso + content + renderRaw("dati grezzi", results);
}

const CATEGORY_PALETTE = ["#4c6ef5", "#f76707", "#37b24d", "#e64980", "#7048e8", "#12b886", "#f59f00", "#495057"];  

function categoryColor(category) {
  if (!category) return null;
  let hash = 0;
  for (let i = 0; i < category.length; i++) hash = (hash * 31 + category.charCodeAt(i)) | 0;
  return CATEGORY_PALETTE[Math.abs(hash) % CATEGORY_PALETTE.length];
}

function collectCategories(days) {
  const set = new Set();
  (days || []).forEach(d => (d.slots || []).forEach(s => { if (s.category) set.add(s.category); }));
  return [...set];
}

function renderCategoryLegend(days) {
  const categories = collectCategories(days);
  if (!categories.length) return "";
  const items = categories.map(c =>
    `<span class="legend-item" style="--cat-color:${categoryColor(c)}"><span class="legend-dot"></span>${escape(c)}</span>`
  ).join("");
  return `<div class="plan-legend">${items}</div>`;
}

function formatMinutes(min) {
  if (typeof min !== "number") return "";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h}h ${m}min` : `${h}h`;
}

function renderSlot(slot) {
  const color = categoryColor(slot.category);
  const time = slot.start_time
    ? `<span class="slot-time">${escape(slot.start_time)}</span>`
    : `<span class="slot-time slot-time-empty">—</span>`;
  const duration = slot.duration_minutes
    ? `<span class="slot-duration">${formatMinutes(slot.duration_minutes)}</span>`
    : "";
  const category = slot.category
    ? `<span class="slot-category">${escape(slot.category)}</span>`
    : "";
  const subtasks = (slot.subtasks || []).length
    ? `<ul class="slot-subtasks">${slot.subtasks.map(s => `<li>${escape(s)}</li>`).join("")}</ul>`
    : "";
  const notes = slot.notes ? `<p class="slot-notes">${escape(slot.notes)}</p>` : "";
  return `<div class="slot" style="${color ? `--cat-color:${color}` : ""}">
    <div class="slot-time-col">${time}${duration}</div>
    <div class="slot-body">
      <div class="slot-head"><span class="slot-task">${escape(slot.task)}</span>${category}</div>
      ${subtasks}${notes}
    </div>
  </div>`;
}

function timeToMinutes(timeStr) {
  if (!timeStr) return 0;
  const [h, m] = timeStr.split(":").map(Number);
  return h * 60 + m;
}

function formatHour(minutes) {
  const h = Math.floor(minutes / 60);
  return `${h.toString().padStart(2, '0')}:00`;
}

function formatMinutesToTime(min) {
  const h = Math.floor(min / 60) % 24;
  const m = min % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`;
}

function assignLanes(slots) {
  const sorted = [...slots].sort((a, b) => a.startMin - b.startMin);
  const laneEnds = [];
  return sorted.map(s => {
    let lane = laneEnds.findIndex(end => s.startMin >= end);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(s.endMin); }
    else { laneEnds[lane] = s.endMin; }
    return { ...s, lane };
  });
}

function renderDayTimeline(slots) {
  const timedSlots = (slots || []).filter(s => s.start_time && s.duration_minutes > 0).map(s => {
    const start = timeToMinutes(s.start_time);
    return { ...s, startMin: start, endMin: start + s.duration_minutes };
  });
  if (!timedSlots.length) return "";

  const minTime = Math.min(...timedSlots.map(s => s.startMin));
  const maxTime = Math.max(...timedSlots.map(s => s.endMin));
  const axisStart = Math.floor(minTime / 60) * 60;
  const axisEnd = Math.ceil(maxTime / 60) * 60;
  const totalMinutes = axisEnd - axisStart;
  if (totalMinutes <= 0) return "";

  const laned = assignLanes(timedSlots);
  const laneCount = Math.max(...laned.map(s => s.lane)) + 1;

  const blocksHtml = laned.map(s => {
    const leftPct = ((s.startMin - axisStart) / totalMinutes) * 100;
    const widthPct = (s.duration_minutes / totalMinutes) * 100;
    const color = categoryColor(s.category);
    const style = [
      `left:${leftPct}%`, `width:${widthPct}%`,
      `top:calc(${s.lane} * (100% / ${laneCount}))`, `height:calc(100% / ${laneCount})`,
      color ? `--cat-color:${color}` : "",
    ].filter(Boolean).join(";");
    const range = `${s.start_time}–${formatMinutesToTime(s.endMin)}`;
    return `<div class="tl-block" style="${style}" title="${escapeAttr(`${s.task} (${range})`)}">
              <span class="tl-block-label">${escape(s.task)}</span>
            </div>`;
  }).join("");

  const gridHtml = [], labelsHtml = [];
  for (let m = axisStart; m <= axisEnd; m += 60) {
    const leftPct = ((m - axisStart) / totalMinutes) * 100;
    gridHtml.push(`<div class="tl-gridline" style="left:${leftPct}%"></div>`);
    labelsHtml.push(`<div class="tl-hour" style="left:${leftPct}%">${formatHour(m)}</div>`);
  }

  return `
    <div class="day-timeline">
      <div class="tl-track" style="--lane-count:${laneCount}">${gridHtml.join("")}${blocksHtml}</div>
      <div class="tl-axis">${labelsHtml.join("")}</div>
    </div>`;
}

function renderPlanDay(day) {
  const dateLabel = day.date ? formatDate(day.date) : `Giorno ${day.day_index}`;
  const heading = day.label ? `${escape(dateLabel)} — ${escape(day.label)}` : escape(dateLabel);
  
  const timelineHtml = renderDayTimeline(day.slots || []);
  
  const slots = (day.slots || []).length
    ? day.slots.map(renderSlot).join("")
    : "<p class='msg'>nessuna attività per questo giorno.</p>";
    
  return `<div class="plan-day">
            <h3>${heading}</h3>
            ${timelineHtml}
            <div class="plan-slots">${slots}</div>
          </div>`;
}

function renderContingencyNotes(notes) {
  if (!notes || !notes.length) return "";
  return `<div class="plan-notes"><h3>⚠ Note e Piani B</h3><ul>${notes.map(n => `<li>${escape(n)}</li>`).join("")}</ul></div>`;
}

function renderOrchestrator(data) {
  const agents = (data.selected_agents || []).length
    ? data.selected_agents.map(a => `<span class="tag">${escape(a)}</span>`).join("")
    : "<span class='tag'>nessuno</span>";

  let html = `<div class="panel">${escape(data.response || "(nessuna risposta)")}</div>`;
  html += `<h2>agenti coinvolti</h2>${agents}`;

  const details = data.details || {};
  if (details.kg_results) {
    html += "<h2>agente kg</h2>" + renderKg(details.kg_results);
  }
  html += renderRaw("agente planner", details.planner_results);
  if (details.multiapi_results) {
    html += "<h2>agente multiapi</h2>" + renderMultiapi(details.multiapi_results);
  }
  return html;
}

// ---- Invio Form ----
if (form) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const qInput = document.getElementById("question");
    const question = qInput ? qInput.value.trim() : "";
    if (!question) return;

    const mode = modeSelect.value;
    const body = { question, target_kg: kgSelect.value };

    if (mode === "planner") {
      if (!activeSession()) createSession();

      const session = activeSession();
      const previousPlan = getLatestPlannerPlan(session);

      if (previousPlan) {
        body.previous_plan = previousPlan;

        if (previousPlan.domain) {
          body.previous_domain = previousPlan.domain;
        }
      }

      if (advModel && advModel.value) body.llm_model = advModel.value;
      if (advContext && advContext.value) body.context_mode = advContext.value;
      if (advDomain && advDomain.value) body.domain_hint = advDomain.value;

      const constraints = advConstraints ? advConstraints.value.trim() : "";
      if (constraints) body.constraints = constraints;

      // Invia allowed_tools in modalità deterministic basandosi sulle checkbox attive
      if (advContext && advContext.value === "deterministic" && advTools) {
        const boxes = [...advTools.querySelectorAll("input[type=checkbox]")];
        const checked = boxes.filter(b => b.checked).map(b => b.value);
        body.allowed_tools = checked;
      }
    }

    if (qInput) qInput.value = "";
    if (submit) submit.disabled = true;

    const userMsg = document.createElement("div");
    userMsg.className = "chat-msg user-msg";
    userMsg.innerHTML = `<div class="msg-content">${escape(question)}</div>`;
    if (output) output.appendChild(userMsg);

    addSessionMessage({
      role: "user",
      type: "text",
      content: question
    });

    const assistantMsg = document.createElement("div");
    assistantMsg.className = "chat-msg assistant-msg";
    if (output) output.appendChild(assistantMsg);

    if (output) output.scrollTop = output.scrollHeight;

    if (mode !== "planner") {
      assistantMsg.innerHTML = "<p class='msg'>interrogazione in corso, può richiedere qualche decina di secondi.</p>";
    }

    try {
      if (mode === "planner") {
        const data = await runPlannerStream(body, assistantMsg);
        updateSessionAfterPlannerResponse(question, data);
        assistantMsg.innerHTML += renderPlanner(data);
      } else {
        const response = await fetch(ENDPOINTS[mode], {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const raw = await response.text();
        let data;
        try {
          data = JSON.parse(raw);
        } catch {
          throw new Error(`errore ${response.status}: ${raw.trim().slice(0, 200) || "risposta vuota"}`);
        }
        if (!response.ok) throw new Error(formatDetail(data.detail) || `errore ${response.status}`);
        
        if (mode === "kg") {
          assistantMsg.innerHTML = renderKg(data);

          addSessionMessage({
            role: "assistant",
            type: "kg",
            data: data
          });

        } else if (mode === "multiapi") {
          assistantMsg.innerHTML = renderMultiapi(data);

          addSessionMessage({
            role: "assistant",
            type: "multiapi",
            data: data
          });

        } else {
          assistantMsg.innerHTML = renderOrchestrator(data);

          addSessionMessage({
            role: "assistant",
            type: "orchestrator",
            data: data
          });
        }
      }
    } catch (err) {
      assistantMsg.innerHTML =
        `<p class="err">${escape(err.message)}</p>`;

      addSessionMessage({
        role: "assistant",
        type: "error",
        content: err.message
      });
    } finally {
      if (submit) submit.disabled = false;
      if (output) output.scrollTop = output.scrollHeight;
    }
  });
}

// Avvio applicazione
if (!activeSession()) {
  createSession();
} else {
  renderSidebar();
  renderPlannerBanner();
  renderConversation(activeSession());
}

syncModeUI();