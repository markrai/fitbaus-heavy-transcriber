const $ = id => document.getElementById(id);
let books = [];
let selected = new Set();
let running = false;
let companionRequest = 0;
let companionBusy = false;

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
    $("companions").disabled = running || companionBusy || selected.size !== 1;
}

function clearCompanions() {
    companionRequest++;
    companionBusy = false;
    $("companion-result").replaceChildren();
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
            clearCompanions();
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
        clearCompanions();
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
$("companions").addEventListener("click", async () => {
    if (running || companionBusy || selected.size !== 1) return;
    const [id] = selected;
    const request = ++companionRequest;
    companionBusy = true;
    updateActions();
    const result = $("companion-result");
    result.replaceChildren(element("p", "Checking attached files…"));
    try {
        const data = await api("/api/companions/" + encodeURIComponent(id));
        if (request !== companionRequest || !selected.has(id) || selected.size !== 1) return;
        result.replaceChildren(element("p", data.files.length ? "Companion files detected (edition not verified)" : "No companion ebooks detected."));
        for (const file of data.files) {
            result.append(element("p", file.filename + " · " + file.format.toUpperCase() + " · " + file.role));
        }
    } catch (error) {
        if (request === companionRequest) result.replaceChildren(element("p", "Companion discovery failed. Check Audiobookshelf access."));
    } finally {
        if (request === companionRequest) {
            companionBusy = false;
            updateActions();
        }
    }
});
$("start").addEventListener("click", async () => {
    $("start").disabled = true;
    try {
        await api("/api/start", {method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify({ids: [...selected]})});
        running = true;
        selected.clear();
        clearCompanions();
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
