const ENDPOINTS = {
  orchestrator: "/api/orchestrator/query",
  kg: "/api/kg/query",
  multiapi: "/api/multiapi/query",
  planner: "/api/planner/query",
  plannerStream: "/api/planner/query/stream",
};

const META_KEYS = ["_provenance", "_sources"];

const form = document.getElementById("form");
const output = document.getElementById("output");
const submit = document.getElementById("submit");
const modeSelect = document.getElementById("mode");
const kgSelect = document.getElementById("kg");
const newChatBtn = document.getElementById("newChat");
const chatListEl = document.getElementById("chatList");
const plannerBanner = document.getElementById("plannerBanner");
const advModel = document.getElementById("advModel");
const advContext = document.getElementById("advContext");
const advDomain = document.getElementById("advDomain");
const advConstraints = document.getElementById("advConstraints");
const advToolsWrap = document.getElementById("advToolsWrap");
const advTools = document.getElementById("advTools");


let advPanelLoaded = false;

async function loadAdvPanelData() {
  if (advPanelLoaded) return;
  advPanelLoaded = true;

  try {
    const res = await fetch("/api/planner/models");
    const data = await res.json();
    advModel.innerHTML = '<option value="">Auto</option>';
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.id === data.default ? `${m.id} (default)` : m.id;
      advModel.appendChild(opt);
    }
  } catch (err) {
    console.error("errore nel caricamento dei modelli:", err);
  }

  try {
    const res = await fetch("/api/planner/tools");
    const tools = await res.json();
    advTools.innerHTML = tools.map(t =>
      `<label><input type="checkbox" value="${escapeAttr(t.name)}" checked> ${escape(t.name)}</label>`
    ).join("");
  } catch (err) {
    console.error("errore nel caricamento dei tool:", err);
  }
}

advContext.addEventListener("change", () => {
  advToolsWrap.hidden = advContext.value !== "deterministic" && advContext.value !== "react";
});

function renderSidebar() {
  if (!sessionState.sessions.length) {
    chatListEl.innerHTML = "<p class='msg' style='margin-top:0'>nessuna chat ancora.</p>";
    return;
  }
  chatListEl.innerHTML = sessionState.sessions.map(s => {
    const active = s.id === sessionState.activeId ? " active" : "";
    const label = s.title || "nuova conversazione";
    return `<div class="chat-item${active}" data-id="${escapeAttr(s.id)}">${escape(label)}</div>`;
  }).join("");
}

function renderPlannerBanner() {
  const session = activeSession();
  if (session && session.hasPlan) {
    plannerBanner.textContent = "Questa conversazione ha già un piano: le richieste verranno trattate come modifiche. Per un piano completamente diverso, apri una nuova chat.";
    plannerBanner.hidden = false;
  } else {
    plannerBanner.hidden = true;
  }
}

// ---- gestione sessioni planner (Fase 1) ----
// solo metadati lato client (id, titolo, presenza di un piano): la
// conversazione e il piano vero restano lato Planner, indicizzati da session_id.

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

function createSession() {
  const session = { id: crypto.randomUUID(), title: null, hasPlan: false };
  sessionState.sessions.unshift(session);
  sessionState.activeId = session.id;
  saveSessionState();
  output.innerHTML = "";
  document.getElementById("question").value = "";
  renderSidebar();
  renderPlannerBanner();
}

function setActiveSession(id) {
  sessionState.activeId = id;
  saveSessionState();
  output.innerHTML = "";
  document.getElementById("question").value = "";
  renderSidebar();
  renderPlannerBanner();
}

function updateSessionAfterPlannerResponse(question, data) {
  const session = activeSession();
  if (!session) return;
  if (!session.title) session.title = question.length > 42 ? question.slice(0, 42) + "…" : question;
  if (data && data.days && data.days.length) session.hasPlan = true;
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
    
    // Riutilizziamo renderRaw per avere il JSON formattato ed espandibile per l'osservazione
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
  
  // Aggiunta: Rendering della traccia ReAct se presente
  const reactTraceHtml = renderToolCalls(data.tool_calls);
  
  return meta + head + `<div class="plan-days">${days}</div>` + renderContingencyNotes(data.contingency_notes) + reactTraceHtml + renderRaw("dati grezzi", data);
}

function timelineIcon(data) {
  if (data.status === "tool_completed") return data.tool_status === "error" ? "✗" : "✓";
  if (data.status === "correcting") return "⟳";
  if (data.status === "domain_classified" || data.status === "completed") return "✓";
  return "▸";
}

async function runPlannerStream(body, container) {
  const timeline = document.createElement("div");
  timeline.className = "timeline";
  
  container.appendChild(timeline);

  const response = await fetch(ENDPOINTS.plannerStream, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
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
  let buffer = "";
  let result = null;
  let streamError = null;

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const eventLine = block.split("\n").find(l => l.startsWith("event:"));
      const dataLine = block.split("\n").find(l => l.startsWith("data:"));
      if (!eventLine || !dataLine) continue;
      const eventName = eventLine.slice(6).trim();
      const data = JSON.parse(dataLine.slice(5).trim());

      if (eventName === "progress") {
        const line = document.createElement("div");
        line.className = "timeline-item";
        line.textContent = `${timelineIcon(data)} ${data.message}`;
        timeline.appendChild(line);
      } else if (eventName === "result") {
        result = data;
      } else if (eventName === "error") {
        streamError = data.message || "errore sconosciuto";
      }
    }
  }

  if (streamError) throw new Error(streamError);
  return result;
}

chatListEl.addEventListener("click", event => {
  const item = event.target.closest(".chat-item");
  if (item) setActiveSession(item.dataset.id);
});

newChatBtn.addEventListener("click", createSession);

function syncModeUI() {
  const isPlanner = modeSelect.value === "planner";
  document.body.classList.toggle("mode-planner", isPlanner);
  if (isPlanner) {
    loadAdvPanelData();
    renderPlannerBanner();
  } else {
    plannerBanner.hidden = true;
  }
}

modeSelect.addEventListener("change", syncModeUI);

if (!activeSession()) createSession();
else renderSidebar();
syncModeUI();

function escape(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text) {
  // textContent non tocca gli apici: dentro un attributo servono anche quelli,
  // altrimenti un valore che ne contiene uno chiude l'attributo e ne apre altri
  return escape(text).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function formatDetail(detail) {
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || JSON.stringify(item)).join("; ");
  }
  return typeof detail === "string" ? detail : detail && JSON.stringify(detail);
}

function safeUrl(uri) {
  // gli uri arrivano dal knowledge graph, non da noi: uno schema "javascript:"
  // eseguirebbe codice al clic, quindi si ammettono solo http e https assoluti
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
  // 0 è un tempo misurato, non un dato mancante: solo null/undefined valgono "?"
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

// ---- helper di presentazione per i risultati multiapi ----

const NUM = new Intl.NumberFormat("it-IT");
const DATE_FMT = new Intl.DateTimeFormat("it-IT", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});

// le date arrivano come "AAAA-MM-GG". Costruiamo la data dai singoli pezzi:
// passando la stringa intera a new Date() verrebbe letta come UTC e, a fusi
// negativi, mostrerebbe il giorno precedente.
function formatDate(iso) {
  if (typeof iso !== "string") return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return DATE_FMT.format(new Date(+m[1], +m[2] - 1, +m[3]));
}

// codici WMO -> icona (stessa tabella che il provider usa per il testo)
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

// flagcdn indicizza le bandiere per codice ISO-3166 alpha-2 minuscolo.
function flagUrl(code, size) {
  if (typeof code !== "string" || !/^[A-Za-z]{2}$/.test(code)) return "";
  return `https://flagcdn.com/${size || "w40"}/${code.toLowerCase()}.png`;
}

// quasi tutti i codici valuta ISO-4217 iniziano col codice paese
// (USD -> US, JPY -> JP...): l'euro è l'eccezione che vale la pena gestire.
function currencyFlag(currency) {
  if (typeof currency !== "string" || currency.length < 3) return "";
  if (currency.toUpperCase() === "EUR") return flagUrl("eu");
  return flagUrl(currency.slice(0, 2));
}


// onerror: se flagcdn non ha quella bandiera l'immagine si rimuove da sola,
// invece di lasciare l'icona di risorsa rotta.
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

function cardWeather(r) {
  const head = cardHead(r.city || "località", r.country || "", flagImg(flagUrl(r.country_code), r.country || ""));
  const temp = r.temperature_c;
  const hero = `<div class="hero">` +
    `<span class="hero-icon">${weatherIcon(r.weather_code)}</span>` +
    `<div class="hero-text">` +
    `<div class="hero-value">${temp === null || temp === undefined ? "?" : escape(String(temp))}<span class="hero-unit">&deg;C</span></div>` +
    `<div class="hero-label">${escape(r.condition || "")}</div>` +
    `</div></div>`;
  const stats = statList([
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
  const hero = `<div class="hero">` +
    `<div class="hero-text">` +
    `<div class="hero-value">${escape(String(r.rates ?? "?"))}` +
    (quote ? `<span class="hero-unit">${escape(quote)}</span>` : "") + `</div>` +
    `<div class="hero-label">per 1 ${escape(base)}</div>` +
    `</div></div>`;
  return `<div class="card">${head}${hero}${statList([["aggiornato al", formatDate(r.date)]])}</div>`;
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
  // niente sottotitolo: il fuso orario è già fra le stat qui sotto
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
  if (data.error) return `<p class="err">agente multiapi non raggiungibile: ${escape(data.error)}</p>`;

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

  const results = data.results || [];
  if (!results.length) return meta + "<p class='msg'>nessun risultato trovato.</p>";

  // gli errori dei provider arrivano come risultato con chiave "error"
  const failed = results.filter(r => r && r.error);
  if (failed.length === results.length) {
    return meta + failed.map(r => `<p class="err">${escape(r.error)}</p>`).join("");
  }

  const card = CARD_BY_INTENT[data.intent];
  const content = card
    ? results.map(r => (r && r.error) ? `<p class="err">${escape(r.error)}</p>` : card(r)).join("")
    : renderTable(results);

  // i campi non mostrati nelle card restano comunque consultabili
  return meta + content + renderRaw("dati grezzi", results);
}

function formatMinutes(min) {
  if (typeof min !== "number") return "";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h}h ${m}min` : `${h}h`;
}

function renderSlot(slot) {
  const time = slot.start_time
    ? `<span class="slot-time">${escape(slot.start_time)}</span>`
    : `<span class="slot-time slot-time-empty">—</span>`;
  const duration = `<span class="slot-duration">${formatMinutes(slot.duration_minutes)}</span>`;
  const category = slot.category ? `<span class="slot-category">${escape(slot.category)}</span>` : "";
  const subtasks = (slot.subtasks || []).length
    ? `<ul class="slot-subtasks">${slot.subtasks.map(s => `<li>${escape(s)}</li>`).join("")}</ul>`
    : "";
  const notes = slot.notes ? `<p class="slot-notes">${escape(slot.notes)}</p>` : "";
  return `<div class="slot">
    <div class="slot-time-col">${time}${duration}</div>
    <div class="slot-body">
      <div class="slot-head"><span>${escape(slot.task)}</span>${category}</div>
      ${subtasks}${notes}
    </div>
  </div>`;
}

function renderPlanDay(day) {
  const dateLabel = day.date ? formatDate(day.date) : `Giorno ${day.day_index}`;
  const heading = day.label ? `${escape(dateLabel)} — ${escape(day.label)}` : escape(dateLabel);
  const slots = (day.slots || []).length
    ? day.slots.map(renderSlot).join("")
    : "<p class='msg'>nessuna attività per questo giorno.</p>";
  return `<div class="plan-day"><h3>${heading}</h3><div class="plan-slots">${slots}</div></div>`;
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

form.addEventListener("submit", async event => {
  event.preventDefault();
  const question = document.getElementById("question").value.trim();
  if (!question) return;

  const mode = modeSelect.value;
  const body = {question, target_kg: kgSelect.value};
  if (mode === "planner") {
    if (!activeSession()) createSession();
    body.session_id = activeSession().id;
    if (advModel.value) body.llm_model = advModel.value;
    if (advContext.value) body.context_mode = advContext.value;
    if (advDomain.value) body.domain_hint = advDomain.value;
    const constraints = advConstraints.value.trim();
    if (constraints) body.constraints = constraints;
    if (!advToolsWrap.hidden) {
      const boxes = [...advTools.querySelectorAll("input[type=checkbox]")];
      const checked = boxes.filter(b => b.checked).map(b => b.value);
      if (checked.length < boxes.length) body.allowed_tools = checked;
    }
  }

  // Svuota l'input dell'utente subito dopo l'invio
  document.getElementById("question").value = "";
  submit.disabled = true;

  // 1. Crea e aggiungi il messaggio dell'utente all'output
  const userMsg = document.createElement("div");
  userMsg.className = "chat-msg user-msg";
  userMsg.innerHTML = `<div class="msg-content">${escape(question)}</div>`;
  output.appendChild(userMsg);

  // 2. Crea e aggiungi il contenitore per la risposta dell'assistente
  const assistantMsg = document.createElement("div");
  assistantMsg.className = "chat-msg assistant-msg";
  output.appendChild(assistantMsg);

  // Scrolla la pagina per mostrare il nuovo blocco
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });

  if (mode !== "planner") {
    assistantMsg.innerHTML = "<p class='msg'>interrogazione in corso, può richiedere qualche decina di secondi.</p>";
  }

  try {
    if (mode === "planner") {
      // Passa il contenitore 'assistantMsg' alla funzione stream
      const data = await runPlannerStream(body, assistantMsg);
      updateSessionAfterPlannerResponse(question, data);
      
      // Aggiungi il piano generato sotto la timeline all'interno dello stesso blocco
      assistantMsg.innerHTML += renderPlanner(data);
    } else {
      const response = await fetch(ENDPOINTS[mode], {
        method: "POST",
        headers: {"Content-Type": "application/json"},
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
      
      // Inietta il risultato direttamente nel blocco dell'assistente
      assistantMsg.innerHTML = mode === "kg" ? renderKg(data) : mode === "multiapi" ? renderMultiapi(data) : renderOrchestrator(data);
    }
  } catch (err) {
    assistantMsg.innerHTML = `<p class="err">${escape(err.message)}</p>`;
  } finally {
    submit.disabled = false;
    // Auto-scroll finale per assicurarsi che l'esito della generazione sia visibile
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }
});
