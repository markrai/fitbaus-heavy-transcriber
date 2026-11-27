const $ = id => document.getElementById(id);
let books = [];
let selected = new Set();
let running = false;

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}

async function api(path, options) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
}

function duration(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "";
    const minutes = Math.floor(value / 60);
    return Math.floor(minutes / 60) + "h " + minutes % 60 + "m";
}

function updateActions() {
    $("count").textContent = selected.size + " selected";
    $("start").disabled = running || !selected.size || selected.size > 32;
}

function renderBooks() {
    const query = $("search").value.toLowerCase();
    const rows = books.filter(book => (book.title + " " + book.author).toLowerCase().includes(query));
    const fragment = document.createDocumentFragment();
    for (const book of rows) {
        const row = element("label", undefined, "book");
        const box = element("input");
        box.type = "checkbox";
        box.checked = selected.has(book.id);
        box.addEventListener("change", () => {
            if (box.checked) selected.add(book.id);
            else selected.delete(book.id);
            updateActions();
        });
        const cover = element("img");
        cover.src = "/api/cover/" + encodeURIComponent(book.id);
        cover.alt = "";
        cover.loading = "lazy";
        const meta = element("span", undefined, "book-meta");
        meta.append(element("span", book.title, "book-title"),
                    element("span", [book.author, duration(book.duration)].filter(Boolean).join(" · "), "book-info"));
        row.append(box, cover, meta);
        if (book.previously_imported) row.append(element("span", "Previously imported", "imported"));
        fragment.append(row);
    }
    $("books").replaceChildren(fragment);
    if (!rows.length) $("books").append(element("p", "No matching audiobooks."));
    updateActions();
}

async function refresh() {
    $("refresh").disabled = true;
    try {
        books = await api("/api/books");
        const ids = new Set(books.map(book => book.id));
        selected = new Set([...selected].filter(id => ids.has(id)));
        renderBooks();
        $("error").textContent = "";
    } catch (error) {
        $("error").textContent = error.message;
    } finally {
        $("refresh").disabled = false;
    }
}

async function status() {
    try {
        const data = await api("/api/status");
        const wasRunning = running;
        running = data.running;
        $("batch-state").textContent = running ? "Running" : "Idle";
        const jobs = Object.entries(data.jobs);
        const fragment = document.createDocumentFragment();
        for (const [id, job] of jobs) {
            const row = element("div", undefined, "job");
            const head = element("div", undefined, "job-head");
            head.append(element("strong", job.title), element("span", job.state, "job-state"));
            const progress = element("progress");
            progress.max = job.total || 1;
            progress.value = job.done || 0;
            row.append(head, progress);
            if (job.error) row.append(element("p", job.error + " · select again to retry from checkpoints"));
            fragment.append(row);
        }
        if (!jobs.length) fragment.append(element("p", "Select books to get started.", "muted"));
        $("jobs").replaceChildren(fragment);
        updateActions();
        if (wasRunning && !running) await refresh();
    } catch (error) {
        $("error").textContent = error.message;
    } finally {
        setTimeout(status, 1000);
    }
}

$("search").addEventListener("input", renderBooks);
$("refresh").addEventListener("click", refresh);
$("start").addEventListener("click", async () => {
    $("start").disabled = true;
    try {
        await api("/api/start", {method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify({ids: [...selected]})});
        running = true;
        selected.clear();
        renderBooks();
        $("error").textContent = "";
    } catch (error) {
        $("error").textContent = error.message;
    } finally {
        updateActions();
    }
});
refresh();
status();
