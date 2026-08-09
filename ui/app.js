const ENDPOINTS = {
  orchestrator: "/api/orchestrator/query",
  kg: "/api/kg/query",
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

function renderMeta(entries) {
  const cells = entries.map(([label, value]) => `<span>${escape(label)}: ${escape(value)}</span>`);
  return `<div class="meta">${cells.join("")}</div>`;
}

function formatSeconds(ms) {
  return ms ? `${(ms / 1000).toFixed(1)}s` : "?";
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
  const uri = row._sources ? row._sources[column] : null;
  return uri
    ? `${text}<a class="src" href="${escape(uri)}" target="_blank" rel="noopener">fonte</a>`
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
  html += renderRaw("agente multiapi", details.multiapi_results);
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
    const raw = await response.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      throw new Error(`errore ${response.status}: ${raw.trim().slice(0, 200) || "risposta vuota"}`);
    }
    if (!response.ok) throw new Error(data.detail || `errore ${response.status}`);
    output.innerHTML = mode === "kg" ? renderKg(data) : renderOrchestrator(data);
  } catch (err) {
    output.innerHTML = `<p class="err">${escape(err.message)}</p>`;
  } finally {
    submit.disabled = false;
  }
});
