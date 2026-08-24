const ENDPOINTS = {
  orchestrator: "/api/orchestrator/query",
  kg: "/api/kg/query",
  multiapi: "/api/multiapi/query",
};

const META_KEYS = ["_provenance", "_sources"];

const form = document.getElementById("form");
const output = document.getElementById("output");
const submit = document.getElementById("submit");
const modeSelect = document.getElementById("mode");
const kgSelect = document.getElementById("kg");

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

  // gli errori dei provider arrivano come risultato con chiave "error"
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

  submit.disabled = true;
  output.innerHTML = "<p class='msg'>interrogazione in corso, può richiedere qualche decina di secondi.</p>";

  try {
    const response = await fetch(ENDPOINTS[mode], {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    // con un agente giù nginx risponde HTML: response.json() nasconderebbe lo stato
    const raw = await response.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      throw new Error(`errore ${response.status}: ${raw.trim().slice(0, 200) || "risposta vuota"}`);
    }
    // sui 422 di FastAPI "detail" è un array: senza formatDetail dà [object Object]
    if (!response.ok) throw new Error(formatDetail(data.detail) || `errore ${response.status}`);
    output.innerHTML = mode === "kg"
      ? renderKg(data)
      : mode === "multiapi"
        ? renderMultiapi(data)
        : renderOrchestrator(data);
  } catch (err) {
    output.innerHTML = `<p class="err">${escape(err.message)}</p>`;
  } finally {
    submit.disabled = false;
  }
});
