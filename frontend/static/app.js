// Decomind Agent UI — streaming chat client.
//
// El backend devuelve Server-Sent Events. Aquí los parseamos y renderizamos
// burbujas (user / agent) + cards de tool_call + tool_response + el PDF final.

const $messages = document.getElementById("messages");
const $form     = document.getElementById("form");
const $input    = document.getElementById("input");
const $send     = document.getElementById("send");

const TOOL_ICONS = {
  geocode_address:      "📍",
  find_comparables:     "🏘️",
  estimate_market_value:"💶",
  estimate_room_cost:   "🔨",
  estimate_renovation_plan: "🛠️",
  compute_renovation_roi:   "📈",
  render_dossier_pdf:   "📄",
};

// Cache: tool_call_id (o name+timestamp) -> elemento card en el DOM
const toolCards = new Map();

document.querySelectorAll(".example").forEach((btn) => {
  btn.addEventListener("click", () => {
    $input.value = btn.dataset.prompt;
    $input.focus();
  });
});

$form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $input.value.trim();
  if (!text) return;
  startConversation(text);
});

function startConversation(text) {
  // Borra welcome la primera vez
  const w = document.querySelector(".welcome");
  if (w) w.remove();

  appendUserMessage(text);
  $input.value = "";
  $send.disabled = true;

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, user_id: "web-user" }),
  })
    .then((resp) => readStream(resp.body.getReader()))
    .catch((err) => {
      appendError(err.message);
      $send.disabled = false;
    });
}

function appendUserMessage(text) {
  const div = document.createElement("div");
  div.className = "msg msg-user";
  div.textContent = text;
  $messages.appendChild(div);
  scrollBottom();
}

function appendAgentBubble() {
  const div = document.createElement("div");
  div.className = "msg msg-agent";
  $messages.appendChild(div);
  return div;
}

function appendError(msg) {
  const div = document.createElement("div");
  div.className = "msg msg-agent";
  div.innerHTML = `<p style="color:var(--err)">❌ ${escapeHtml(msg)}</p>`;
  $messages.appendChild(div);
  scrollBottom();
}

async function readStream(reader) {
  const decoder = new TextDecoder();
  let buffer = "";
  let currentTextBubble = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE: chunks delimitados por \n\n
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const ev = parseSse(chunk);
      if (!ev) continue;
      handleEvent(ev, () => {
        if (!currentTextBubble) currentTextBubble = appendAgentBubble();
        return currentTextBubble;
      });
    }
  }
  $send.disabled = false;
}

function parseSse(chunk) {
  const lines = chunk.split("\n");
  let event = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try { return { event, data: JSON.parse(data) }; }
  catch { return { event, data: { raw: data } }; }
}

function handleEvent(ev, getTextBubble) {
  console.log("[sse]", ev.event, ev.data);  // siempre visible en F12
  switch (ev.event) {
    case "session": break; // silent
    case "tool_call":      renderToolCall(ev.data); break;
    case "tool_response":  renderToolResponse(ev.data); break;
    case "text":           appendText(getTextBubble(), ev.data.text); break;
    case "error":          appendError(ev.data.message || "unknown error"); break;
    case "done":           appendDoneMarker(); break;
    case "meta":           renderMeta(ev.data); break;
    default:               renderMeta(ev.data);
  }
  scrollBottom();
}

function renderMeta(data) {
  const div = document.createElement("div");
  div.className = "tool done";
  div.innerHTML = `
    <div class="tool-icon">🔍</div>
    <div class="tool-body">
      <div class="tool-head">
        <span class="tool-name">unrecognized event</span>
        <span class="tool-status">debug</span>
      </div>
      <details class="tool-details" open>
        <summary>raw</summary>
        <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </details>
    </div>`;
  $messages.appendChild(div);
}

function appendDoneMarker() {
  const div = document.createElement("div");
  div.style.cssText = "text-align:center;color:var(--muted);font-size:11px;padding:8px 0;";
  div.textContent = "— end of stream —";
  $messages.appendChild(div);
}

function renderToolCall(data) {
  const name = data.name;
  const icon = TOOL_ICONS[name] || "🔧";
  const div = document.createElement("div");
  div.className = "tool running";
  div.innerHTML = `
    <div class="tool-icon">${icon}</div>
    <div class="tool-body">
      <div class="tool-head">
        <span class="tool-name">${escapeHtml(name)}</span>
        <span class="tool-status">running <span class="dots"><span></span><span></span><span></span></span></span>
      </div>
      <div class="tool-summary">${summarizeArgs(name, data.args)}</div>
      <details class="tool-details">
        <summary>args</summary>
        <pre>${escapeHtml(JSON.stringify(data.args, null, 2))}</pre>
      </details>
    </div>`;
  $messages.appendChild(div);
  toolCards.set(name, div); // último call por name (suficiente para 7-step pipeline)
}

function renderToolResponse(data) {
  const name = data.name;
  const card = toolCards.get(name);
  if (card) {
    card.classList.remove("running");
    card.classList.add("done");
    card.querySelector(".tool-status").innerHTML = "done ✓";
    const details = card.querySelector(".tool-details");
    if (details) {
      const respPre = document.createElement("pre");
      respPre.textContent = JSON.stringify(data.response, null, 2);
      const respLabel = document.createElement("summary");
      respLabel.textContent = "response";
      const respDetails = document.createElement("details");
      respDetails.className = "tool-details";
      respDetails.appendChild(respLabel);
      respDetails.appendChild(respPre);
      card.querySelector(".tool-body").appendChild(respDetails);
    }
    enrichSummary(card, name, data.response);
  }

  // si es el PDF, render preview card
  if (name === "render_dossier_pdf") {
    const url = (data.response && data.response.url) || null;
    if (url) renderPdfCard(url, data.response);
  }
}

function enrichSummary(card, name, response) {
  const summary = card.querySelector(".tool-summary");
  if (!summary || !response) return;
  if (name === "geocode_address" && response.found) {
    summary.innerHTML = `Found: <code>${escapeHtml(response.municipality || "?")}</code> · ${escapeHtml(response.city_district || response.suburb || "")} · lat ${response.lat}, lon ${response.lon}`;
  } else if (name === "find_comparables") {
    summary.innerHTML = `Median <b>${response.median_price_eur_per_m2} €/m²</b> · source <code>${escapeHtml(response.data_source || "?")}</code> · ${response.count} comps`;
  } else if (name === "estimate_market_value") {
    summary.innerHTML = `Value: <b>${formatEur(response.value_eur)}</b> · <code>${escapeHtml(response.assumptions?.condition || "")}</code>`;
  } else if (name === "estimate_renovation_plan") {
    summary.innerHTML = `Total: <b>${formatEur(response.totals?.integral)}</b> · ${response.rooms_count} rooms · tier <code>${escapeHtml(response.tier)}</code>`;
  } else if (name === "compute_renovation_roi") {
    summary.innerHTML = `Net gain <b>${formatEur(response.net_gain_eur)}</b> · payback <b>${response.payback_ratio}x</b> · <code>${escapeHtml(response.recommendation)}</code>`;
  } else if (name === "render_dossier_pdf") {
    summary.innerHTML = `PDF generated · ${response.size_bytes ? Math.round(response.size_bytes / 1024) + " KB" : ""}`;
  }
}

function summarizeArgs(name, args) {
  if (!args) return "";
  if (name === "geocode_address")
    return `<code>${escapeHtml(args.address || "")}, ${escapeHtml(args.locality || "")}</code>`;
  if (name === "find_comparables")
    return `<code>${escapeHtml(args.municipality || "")}, ${escapeHtml(args.province || "")}</code>`;
  return "";
}

function renderPdfCard(url, response) {
  const div = document.createElement("div");
  div.className = "pdf-card";
  div.innerHTML = `
    <div class="icon">📄</div>
    <div class="info">
      <b>Dossier ready</b><br/>
      <span>${response.bucket ? "GCS · " + escapeHtml(response.bucket) : "local"} · expires in 24h</span>
    </div>
    <a class="btn" href="${url}" target="_blank" rel="noopener">Open PDF →</a>`;
  $messages.appendChild(div);
}

function appendText(bubble, text) {
  bubble.innerHTML = renderMarkdown((bubble.dataset.raw || "") + text);
  bubble.dataset.raw = (bubble.dataset.raw || "") + text;
}

function renderMarkdown(md) {
  // Mini renderer — suficiente para tablas, bold, links que devuelve Gemini.
  let html = escapeHtml(md);
  html = html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  html = html.replace(/__(.+?)__/g, "<b>$1</b>");
  html = html.replace(/\*(.+?)\*/g, "<i>$1</i>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Solo renderiza como enlace si el href es una URL http real (evita
  // placeholders rotos tipo {url} que el modelo pueda escribir).
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, href) =>
    /^https?:\/\//.test(href) ? `<a href="${href}" target="_blank">${text}</a>` : text);
  // tablas markdown (simple)
  html = html.replace(/^(\|.+\|)\n\|[-:| ]+\|\n((?:\|.+\|\n?)+)/gm, (m, header, body) => {
    const ths = header.split("|").filter(Boolean).map((c) => `<th>${c.trim()}</th>`).join("");
    const trs = body.trim().split("\n").map((r) => {
      const tds = r.split("|").filter(Boolean).map((c) => `<td>${c.trim()}</td>`).join("");
      return `<tr>${tds}</tr>`;
    }).join("");
    return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });
  html = html.replace(/\n/g, "<br/>");
  return html;
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatEur(v) {
  if (v == null || isNaN(v)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v) + " €";
}

function scrollBottom() {
  $messages.scrollTop = $messages.scrollHeight;
}
