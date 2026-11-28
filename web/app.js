const $ = id => document.getElementById(id);
let books = [];
let selected = new Set();
let running = false;
let companionRequest = 0;
let companionBusy = false;
let companionCache = new Map();
let renderedHints = new Map();
let visibleBooks = new Set();
let observer = null;
let visibleWorker = false;

function updateHint(id) {
    const hint = renderedHints.get(id);
    if (!hint) return;
    const book = books.find(row => row.id === id);
    const entry = companionCache.get(id);
    const files = entry?.data?.files;
    if (files) {
        const formats = [...new Set(files.map(file => file.format.toUpperCase()))];
        hint.textContent = formats.length ? formats.join(" / ") + " companion available" : "";
    } else if (book?.ebook_format) {
        hint.textContent = book.ebook_format.toUpperCase() + " companion available";
    } else {
        hint.textContent = entry?.error ? "Ebook availability unknown" : "";
    }
    hint.classList.toggle("ebook-unknown", !!entry?.error && !book?.ebook_format);
}

function lookupCompanions(id) {
    const existing = companionCache.get(id);
    if (existing?.promise) return existing.promise;
    const cache = companionCache;
    const entry = {};
    entry.promise = api("/api/companions/" + encodeURIComponent(id)).then(data => {
        if (data.item_id !== id || !Array.isArray(data.files)) throw new Error("Invalid companion response");
        entry.data = data;
        return data;
    }).catch(error => {
        entry.error = error;
        throw error;
    }).finally(() => {
        if (companionCache === cache) updateHint(id);
    });
    cache.set(id, entry);
    return entry.promise;
}

async function scanVisibleBooks() {
    if (visibleWorker || running) return;
    visibleWorker = true;
    try {
        while (!running) {
            const id = [...visibleBooks].find(key => !companionCache.has(key));
            if (!id) break;
            try {
                await lookupCompanions(id);
            } catch {}
        }
    } finally {
        visibleWorker = false;
    }
}

function observeBooks(rows) {
    observer?.disconnect();
    visibleBooks = new Set();
    if (typeof IntersectionObserver !== "function") return;
    observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
            const id = entry.target.dataset.bookId;
            if (entry.isIntersecting) visibleBooks.add(id);
            else visibleBooks.delete(id);
        }
        scanVisibleBooks();
    });
    for (const row of rows) observer.observe(row);
}

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
    $("include-ebook").disabled = running;
}

function clearCompanions() {
    companionRequest++;
    companionBusy = false;
    $("companion-result").replaceChildren();
    $("companion-summary").textContent = "";
    $("companion-diagnostics").hidden = true;
    $("companion-diagnostics").open = false;
}

function renderBooks() {
    const query = $("search").value.toLowerCase();
    const rows = books.filter(book => (book.title + " " + book.author).toLowerCase().includes(query));
    const fragment = document.createDocumentFragment();
    renderedHints = new Map();
    const observed = [];
    for (const book of rows) {
        const row = element("label", undefined, "book");
        row.dataset.bookId = book.id;
        observed.push(row);
        const box = element("input");
        box.type = "checkbox";
        box.checked = selected.has(book.id);
        box.addEventListener("change", () => {
            if (box.checked) selected.add(book.id);
            else selected.delete(book.id);
            clearCompanions();
            updateActions();
            discoverSelected();
        });
        const cover = element("img");
        cover.src = "/api/cover/" + encodeURIComponent(book.id);
        cover.alt = "";
        cover.loading = "lazy";
        const meta = element("span", undefined, "book-meta");
        meta.append(element("span", book.title, "book-title"),
                    element("span", [book.author, duration(book.duration)].filter(Boolean).join(" · "), "book-info"));
        const hint = element("span", "", "ebook-hint");
        renderedHints.set(book.id, hint);
        meta.append(hint);
        updateHint(book.id);
        row.append(box, cover, meta);
        if (book.previously_imported) row.append(element("span", "Previously imported", "imported"));
        fragment.append(row);
    }
    $("books").replaceChildren(fragment);
    observeBooks(observed);
    if (!rows.length) $("books").append(element("p", "No matching audiobooks."));
    updateActions();
}

async function refresh() {
    $("refresh").disabled = true;
    try {
        books = await api("/api/books");
        companionCache = new Map();
        clearCompanions();
        const ids = new Set(books.map(book => book.id));
        selected = new Set([...selected].filter(id => ids.has(id)));
        renderBooks();
        discoverSelected();
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
            if (job.enrichment_state) row.append(element("p", "Ebook: " + job.enrichment_state));
            if (job.enrichment_error) row.append(element("p", job.enrichment_error, "enrichment-error"));
            if (job.enrichment_artifact) {
                const artifact = job.enrichment_artifact;
                row.append(element("p", artifact.timed_count + " timed / " + artifact.untimed_count +
                    " untimed visuals · Enrichment ID: " + artifact.artifact_id, "artifact-detail"));
            }
            if (job.delivery_candidate) {
                const delivery = job.delivery_candidate;
                row.append(element("p", delivery.candidate_count + " delivery candidates · " +
                    delivery.withheld_count + " withheld · Delivery ID: " + delivery.artifact_id +
                    " · Not published", "artifact-detail"));
            }
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
async function discoverSelected() {
    if (running || companionBusy || selected.size !== 1) return;
    const [id] = selected;
    const request = ++companionRequest;
    companionBusy = true;
    updateActions();
    const result = $("companion-result");
    $("companion-summary").textContent = "Checking companion ebook…";
    try {
        const data = await lookupCompanions(id);
        if (request !== companionRequest || !selected.has(id) || selected.size !== 1) return;
        const epubs = data.files.filter(file => file.format === "epub");
        $("companion-summary").textContent = epubs.length ?
            epubs.length + " EPUB companion" + (epubs.length === 1 ? "" : "s") +
                " detected · Edition not verified" :
            data.files.length ? "Companion ebook found, but no supported EPUB" : "No companion ebooks detected";
        $("companion-diagnostics").hidden = !data.files.length;
        result.replaceChildren();
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
        if (request === companionRequest) {
            companionCache.delete(id);
            $("companion-summary").textContent = "Companion discovery failed: " +
                (error.message === "Not found" ? "Workbench API unavailable. Restart the Python application after updating." : error.message);
        }
    } finally {
        if (request === companionRequest) {
            companionBusy = false;
            updateActions();
        }
    }
}
$("start").addEventListener("click", async () => {
    $("start").disabled = true;
    try {
        await api("/api/start", {method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify({ids: [...selected], include_ebook: $("include-ebook").checked})});
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
