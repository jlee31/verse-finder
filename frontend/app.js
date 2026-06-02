// Where the FastAPI backend lives.
const API_URL = "http://localhost:8000/api/verses/search";

const form = document.getElementById("form");
const promptEl = document.getElementById("prompt");
const submitEl = document.getElementById("submit");
const output = document.getElementById("output");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  submitEl.disabled = true;
  submitEl.textContent = "Thinking…";
  output.innerHTML = "";

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mainPrompt: prompt }),
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const data = await res.json();
    render(data);
  } catch (err) {
    output.innerHTML = `<p class="error">${err.message}. Is the backend running on :8000?</p>`;
  } finally {
    submitEl.disabled = false;
    submitEl.textContent = "Reflect";
  }
});

function render({ reflection, sources }) {
  const sourceHtml = sources
    .map(
      (s) => `
        <div class="source">
          “${s.text}” <span class="author">— ${s.author}</span>
          <div class="score">similarity: ${s.score.toFixed(3)}</div>
        </div>`
    )
    .join("");

  output.innerHTML = `
    <div class="reflection">${reflection}</div>
    <div class="sources">
      <h2>Quotes it drew on</h2>
      ${sourceHtml}
    </div>`;
}
