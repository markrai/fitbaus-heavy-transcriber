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
    $("start").disabled = running || companionBusy || !selected.size || selected.size > 32;
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
            const row = element("p", file.filename + " · " + file.format.toUpperCase() + " · " + file.role + " ");
            result.append(row);
            if (file.format === "epub") {
                for (const mode of ["inventory", "alignment", "assets", "timing", "enrichment"]) {
                    const labels = {inventory: "Inspect EPUB", alignment: "Test alignment", assets: "Find visuals", timing: "Test visual timing", enrichment: "Prepare enrichment"};
                    const inspect = element("button", labels[mode], mode === "enrichment" ? "" : "secondary");
                    inspect.type = "button";
                    const detail = element("p");
                    inspect.addEventListener("click", async () => {
                        if (running || companionBusy || request !== companionRequest) return;
                        companionBusy = true;
                        inspect.disabled = true;
                        updateActions();
                        detail.textContent = mode === "inventory" ? "Downloading and inspecting EPUB…" :
                            mode === "alignment" ? "Comparing EPUB with retained narration…" :
                            mode === "assets" ? "Extracting original EPUB visuals…" :
                            mode === "timing" ? "Associating visuals with narration…" :
                            "Preparing local enrichment artifact…";
                        try {
                            const inventory = await api("/api/epub-" + mode, {
                                method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify({item_id: id, file_id: file.file_id})
                            });
                            if (request !== companionRequest) return;
                            if (mode === "enrichment") {
                                detail.textContent = (inventory.reused ? "Existing artifact verified" : "Local artifact prepared") +
                                    " · " + inventory.timed_count + " timed / " + inventory.untimed_count +
                                    " untimed visuals · " + inventory.unique_asset_count + " unique assets · " +
                                    inventory.artifact_id + " · Not published or playback-qualified";
                                detail.style.overflowWrap = "anywhere";
                                return;
                            }
                            if (mode === "timing") {
                                detail.textContent = inventory.timed_count + " / " + inventory.occurrence_count +
                                    " visuals with bounded timing evidence · " + inventory.untimed_count +
                                    " untimed · Preview only, not playback-qualified";
                                return;
                            }
                            if (mode === "assets") {
                                detail.textContent = inventory.mathml_count + " MathML equations · " +
                                    inventory.raster_count + " raster images · " + inventory.svg_count +
                                    " SVGs · " + inventory.unique_asset_count + " unique assets · " +
                                    inventory.skipped_count + " unsupported references · Not timed or render-qualified";
                                return;
                            }
                            if (mode === "alignment") {
                                detail.textContent = inventory.matched_cue_count + " / " + inventory.cue_count +
                                    " narration cues anchored · " + inventory.eligible_cue_count + " eligible · " +
                                    inventory.matched_section_count + " / " + inventory.section_count +
                                    " reading-order sections · " + inventory.conflicting_cue_count +
                                    " conflicting cues · Edition not verified";
                                return;
                            }
                            detail.textContent = "EPUB " + inventory.version + " · " + inventory.spine_count +
                                " reading-order entries · " + inventory.xhtml_count + " XHTML resources · " +
                                inventory.image_count + " images · Edition not verified";
                            if (inventory.title) detail.textContent += " · " + inventory.title;
                        } catch (error) {
                            if (request === companionRequest) detail.textContent = error.message;
                        } finally {
                            if (request === companionRequest) {
                                companionBusy = false;
                                inspect.disabled = false;
                                updateActions();
                            }
                        }
                    });
                    row.append(inspect);
                    result.append(detail);
                }
            }
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
