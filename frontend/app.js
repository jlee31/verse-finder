// Where the FastAPI backend lives.
const API_BASE = "http://localhost:8000";

// The one-shot pipeline and the two agent loops. The agents return an extra
// `trace` — the searches they chose to run — which is the only reason the
// rendering differs at all.
const MODES = {
  baseline: { url: "/api/verses/search", pending: "Thinking…" },
  handrolled: {
    url: "/api/verses/search/agentic?implementation=handrolled",
    pending: "Searching…",
  },
  langgraph: {
    url: "/api/verses/search/agentic?implementation=langgraph",
    pending: "Searching…",
  },
};

const form = document.getElementById("form");
const promptEl = document.getElementById("prompt");
const submitEl = document.getElementById("submit");
const output = document.getElementById("output");

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

// Everything below is interpolated into innerHTML. Quote text is ours, but the
// trace carries model-written queries and error strings that can echo back
// whatever was typed into the textarea.
function esc(value) {
  return String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  const mode = MODES[selectedMode()];

  submitEl.disabled = true;
  submitEl.textContent = mode.pending;
  output.innerHTML = "";

  try {
    const res = await fetch(API_BASE + mode.url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mainPrompt: prompt }),
    });
    if (!res.ok) {
      // The agent endpoint sends a reason (bad prompt, upstream failure); the
      // status code alone doesn't say which.
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail ?? `API error ${res.status}`);
    }
    render(await res.json());
  } catch (err) {
    output.innerHTML = `<p class="error">${esc(err.message)}. Is the backend running on :8000?</p>`;
  } finally {
    submitEl.disabled = false;
    submitEl.textContent = "Reflect";
  }
});

function render({ reflection, sources, trace, implementation, stopped_early }) {
  const sourceHtml = sources
    .map(
      (s) => `
        <div class="source">
          “${esc(s.text)}” <span class="author">— ${esc(s.author)}</span>
          <div class="score">similarity: ${s.score.toFixed(3)}</div>
        </div>`
    )
    .join("");

  output.innerHTML = `
    <div class="reflection">${esc(reflection)}</div>
    ${renderTrace(trace, implementation, stopped_early)}
    <div class="sources">
      <h2>Quotes it drew on</h2>
      ${sourceHtml}
    </div>`;
}

// Collapsed by default — the reflection is the answer, this is the working out.
// The one-shot endpoint sends no trace, so this renders nothing for it.
function renderTrace(trace, implementation, stoppedEarly) {
  if (!trace?.length) return "";

  const steps = trace
    .map((t) => {
      const detail = t.error
        ? `<span class="failed">${esc(t.error)}</span>`
        : `${t.returned} quote${t.returned === 1 ? "" : "s"}` +
          (t.top_score === null ? "" : ` · best ${t.top_score.toFixed(3)}`);
      return `
        <li>
          <span class="q">${t.query === null ? "—" : `“${esc(t.query)}”`}</span>
          <span class="meta">${detail}</span>
        </li>`;
    })
    .join("");

  const cut = stoppedEarly
    ? `<p class="cut">Ran out of search budget — this reflection was written from
       what it had already found.</p>`
    : "";

  return `
    <details class="trace">
      <summary>How it searched · ${trace.length} search${
        trace.length === 1 ? "" : "es"
      } <span class="impl">${esc(implementation)}</span></summary>
      ${cut}
      <ol>${steps}</ol>
    </details>`;
}
