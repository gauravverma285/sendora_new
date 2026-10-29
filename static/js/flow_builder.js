(function () {
    "use strict";

    const cfg = window.FLOW_CONFIG || {};
    const canvas = document.getElementById("flowCanvas");
    if (!canvas) return;

    const nodesLayer = document.getElementById("flowNodesLayer");
    const svg = document.getElementById("flowConnectors");

    function getCsrfToken() {
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    let nextKeySeq = 1;
    function makeKey() {
        return "n" + Date.now().toString(36) + (nextKeySeq++);
    }

    // Headers/body/response-mapping are stored server-side as plain
    // objects, but edited here as ordered {key,value} row lists (so typing
    // a duplicate key mid-edit doesn't silently clobber another row) —
    // converted back to objects only when saving.
    function dictToPairs(dict, keyField, valField) {
        return Object.entries(dict || {}).map(([k, v]) => ({ [keyField]: k, [valField]: v == null ? "" : String(v) }));
    }
    function pairsToDict(pairs, keyField, valField) {
        const out = {};
        (pairs || []).forEach(p => {
            const k = (p[keyField] || "").trim();
            if (k) out[k] = p[valField] || "";
        });
        return out;
    }

    const SPECIAL_BUTTON_SETS = {
        capture: [{ text: "Next", kind: "next" }],
        api_call: [{ text: "✓ Success", kind: "success" }, { text: "✗ Failure", kind: "failure" }],
    };

    const data = window.FLOW_DATA || { nodes: [] };
    let nodes = (data.nodes || []).map(n => ({
        client_key: n.client_key || makeKey(),
        title: n.title || "",
        message_type: n.message_type || "text",
        body_text: n.body_text || "",
        media_id: n.media_id || "",
        media_filename: n.media_filename || "",
        pos_x: n.pos_x != null ? n.pos_x : 40,
        pos_y: n.pos_y != null ? n.pos_y : 40,
        is_end: !!n.is_end,
        is_start: !!n.is_start,
        capture_variable: n.capture_variable || "",
        capture_sensitive: !!n.capture_sensitive,
        api_url: n.api_url || "",
        api_method: n.api_method || "POST",
        api_body_type: n.api_body_type || "json",
        api_headers: dictToPairs(n.api_headers, "key", "value"),
        api_body: dictToPairs(n.api_body, "key", "value"),
        api_response_mapping: dictToPairs(n.api_response_mapping, "variable", "path"),
        buttons: (n.buttons || []).map(b => ({ text: b.text, kind: b.kind || "reply", next_client_id: b.next_client_id || null })),
    }));

    if (!nodes.length) {
        nodes.push({
            client_key: makeKey(), title: "Welcome", message_type: "text",
            body_text: "Hi! Welcome. How can we help you today?",
            media_id: "", media_filename: "", pos_x: 60, pos_y: 60,
            is_end: false, is_start: true,
            capture_variable: "", capture_sensitive: false,
            api_url: "", api_method: "POST", api_body_type: "json", api_headers: [], api_body: [], api_response_mapping: [],
            buttons: [],
        });
    }
    if (!nodes.some(n => n.is_start)) nodes[0].is_start = true;

    let selectedKey = null;
    let dirty = false;
    let zoom = 1;
    const ZOOM_MIN = 0.4;
    const ZOOM_MAX = 1.5;
    const ZOOM_STEP = 0.1;

    function markDirty() {
        dirty = true;
        document.getElementById("flowSaveStatus").textContent = "Unsaved changes";
    }

    function findNode(key) {
        return nodes.find(n => n.client_key === key);
    }

    // ------------------------------------------------------------------
    // Rendering nodes
    // ------------------------------------------------------------------
    const TYPE_ICON = {
        text: "message-text-outline", image: "image-outline", video: "video-outline", document: "file-document-outline",
        capture: "comment-question-outline", api_call: "api",
    };

    function nodeLabel(n, idx) {
        return n.title.trim() || ("Message " + (idx + 1));
    }

    function renderNodes() {
        nodesLayer.innerHTML = "";
        nodes.forEach((n, idx) => {
            const el = document.createElement("div");
            el.className = "flow-node" + (n.client_key === selectedKey ? " is-selected" : "");
            el.dataset.key = n.client_key;
            el.style.left = n.pos_x + "px";
            el.style.top = n.pos_y + "px";

            let bodyPreviewHtml;
            let mediaBadgeHtml = '';
            if (n.message_type === "api_call") {
                bodyPreviewHtml = n.api_url
                    ? `<code>${escapeHtml(n.api_method)} ${escapeHtml(n.api_url.slice(0, 60))}</code>`
                    : '<em class="flow-node__placeholder">No API URL set yet — click to edit</em>';
            } else if (n.message_type === "capture") {
                bodyPreviewHtml = n.body_text
                    ? escapeHtml(n.body_text.slice(0, 80))
                    : '<em class="flow-node__placeholder">No question yet — click to edit</em>';
                if (n.capture_variable) {
                    mediaBadgeHtml = `<div class="flow-node__media"><i class="mdi mdi-content-save-outline"></i> saves as {{${escapeHtml(n.capture_variable)}}}</div>`;
                }
            } else {
                bodyPreviewHtml = n.body_text
                    ? escapeHtml(n.body_text.slice(0, 80))
                    : '<em class="flow-node__placeholder">No message text yet — click to edit</em>';
                mediaBadgeHtml = n.media_filename
                    ? `<div class="flow-node__media"><i class="mdi mdi-paperclip"></i> ${escapeHtml(n.media_filename)}</div>`
                    : '';
            }
            const buttonsHtml = n.buttons.map((b, bi) => `<div class="flow-node__btn"><span>${b.text ? escapeHtml(b.text) : '<em class="flow-node__placeholder">Button text</em>'}</span><span class="flow-node__port" data-port-index="${bi}"></span></div>`).join("");

            el.innerHTML = `
                <div class="flow-node__head">
                    <span class="mdi mdi-drag"></span>
                    <span class="mdi mdi-${TYPE_ICON[n.message_type] || 'message-text-outline'}"></span>
                    <span class="flow-node__title">${escapeHtml(nodeLabel(n, idx))}</span>
                    ${n.is_start ? '<span class="au-pill au-pill--green flow-node__badge">Start</span>' : ''}
                    ${n.is_end ? '<span class="au-pill au-pill--gray flow-node__badge">End</span>' : ''}
                </div>
                <div class="flow-node__body">${bodyPreviewHtml}${mediaBadgeHtml}</div>
                ${buttonsHtml ? `<div class="flow-node__buttons">${buttonsHtml}</div>` : ''}
                <div class="flow-node__inport" data-inport="1" title="Incoming connections land here"></div>
            `;
            nodesLayer.appendChild(el);
        });
        drawConnectors();
    }

    function escapeHtml(str) {
        const d = document.createElement("div");
        d.textContent = str == null ? "" : String(str);
        return d.innerHTML;
    }

    // ------------------------------------------------------------------
    // Connectors (SVG bezier lines from a button port to a node's inport)
    // ------------------------------------------------------------------
    function drawConnectors() {
        const canvasRect = canvas.getBoundingClientRect();
        svg.setAttribute("width", nodesLayer.scrollWidth + 400);
        svg.setAttribute("height", nodesLayer.scrollHeight + 400);
        let html = `<defs>
            <marker id="flowArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
                <path d="M0,0 L8,3 L0,6 Z" fill="#22c55e"></path>
            </marker>
        </defs>`;

        nodes.forEach(n => {
            n.buttons.forEach((b, bi) => {
                if (!b.next_client_id) return;
                const fromEl = nodesLayer.querySelector(`.flow-node[data-key="${cssEscape(n.client_key)}"] .flow-node__port[data-port-index="${bi}"]`);
                const toEl = nodesLayer.querySelector(`.flow-node[data-key="${cssEscape(b.next_client_id)}"] .flow-node__inport`);
                if (!fromEl || !toEl) return;
                const fromRect = fromEl.getBoundingClientRect();
                const toRect = toEl.getBoundingClientRect();
                // getBoundingClientRect() returns post-zoom screen pixels; the
                // svg is itself inside the zoomed .flow-canvas, so its own
                // coordinates must be expressed pre-zoom (divide by zoom) or
                // the transform would scale the paths a second time.
                const x1 = (fromRect.left - canvasRect.left + fromRect.width / 2) / zoom;
                const y1 = (fromRect.top - canvasRect.top + fromRect.height / 2) / zoom;
                const x2 = (toRect.left - canvasRect.left + toRect.width / 2) / zoom;
                const y2 = (toRect.top - canvasRect.top + toRect.height / 2) / zoom;
                const dx = Math.max(60, Math.abs(x2 - x1) / 2);
                html += `<path d="M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}" fill="none" stroke="#22c55e" stroke-width="2" marker-end="url(#flowArrow)"></path>`;
            });
        });

        // Live connector being dragged
        if (connectDrag) {
            html += `<path d="M ${connectDrag.x1} ${connectDrag.y1} L ${connectDrag.x2} ${connectDrag.y2}" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6,4"></path>`;
        }

        svg.innerHTML = html;
    }

    function cssEscape(s) {
        return String(s).replace(/[^a-zA-Z0-9_-]/g, m => "\\" + m);
    }

    // ------------------------------------------------------------------
    // Drag to move nodes
    // ------------------------------------------------------------------
    let dragState = null;

    // The header is the only drag handle — dragging from the body used to
    // fight with clicking the body to edit it, so they're now split across
    // two regions instead of relying on a click/double-click distinction.
    nodesLayer.addEventListener("mousedown", function (e) {
        const portEl = e.target.closest(".flow-node__port");
        if (portEl) {
            startConnectDrag(e, portEl);
            return;
        }
        const headEl = e.target.closest(".flow-node__head");
        if (!headEl) return;
        const nodeEl = headEl.closest(".flow-node");
        if (!nodeEl) return;
        const key = nodeEl.dataset.key;
        setSelected(key);
        const n = findNode(key);
        dragState = {
            key, startX: e.clientX, startY: e.clientY,
            origX: n.pos_x, origY: n.pos_y, moved: false,
        };
        e.preventDefault();
    });

    nodesLayer.addEventListener("click", function (e) {
        if (e.target.closest(".flow-node__port")) return;
        if (e.target.closest(".flow-node__head")) return;
        const nodeEl = e.target.closest(".flow-node");
        if (!nodeEl) return;
        selectNode(nodeEl.dataset.key);
    });

    document.addEventListener("mousemove", function (e) {
        if (dragState) {
            // Divide by zoom: node positions are stored/rendered in
            // pre-zoom canvas coordinates, but mouse deltas are real screen
            // pixels, so at e.g. 50% zoom a node must move twice as far in
            // local coordinates to visually track the cursor 1:1.
            const dx = (e.clientX - dragState.startX) / zoom;
            const dy = (e.clientY - dragState.startY) / zoom;
            if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragState.moved = true;
            const n = findNode(dragState.key);
            n.pos_x = Math.max(0, dragState.origX + dx);
            n.pos_y = Math.max(0, dragState.origY + dy);
            const el = nodesLayer.querySelector(`.flow-node[data-key="${cssEscape(n.client_key)}"]`);
            if (el) { el.style.left = n.pos_x + "px"; el.style.top = n.pos_y + "px"; }
            drawConnectors();
        } else if (connectDrag) {
            const canvasRect = canvas.getBoundingClientRect();
            connectDrag.x2 = (e.clientX - canvasRect.left) / zoom;
            connectDrag.y2 = (e.clientY - canvasRect.top) / zoom;
            drawConnectors();
        }
    });

    document.addEventListener("mouseup", function (e) {
        if (dragState) {
            if (dragState.moved) markDirty();
            dragState = null;
        }
        if (connectDrag) {
            finishConnectDrag(e);
        }
    });

    // ------------------------------------------------------------------
    // Drag from a button port to another node to connect them
    // ------------------------------------------------------------------
    let connectDrag = null;

    function startConnectDrag(e, portEl) {
        e.preventDefault();
        e.stopPropagation();
        const nodeEl = portEl.closest(".flow-node");
        const canvasRect = canvas.getBoundingClientRect();
        const portRect = portEl.getBoundingClientRect();
        connectDrag = {
            fromKey: nodeEl.dataset.key,
            portIndex: parseInt(portEl.dataset.portIndex, 10),
            x1: (portRect.left - canvasRect.left + portRect.width / 2) / zoom,
            y1: (portRect.top - canvasRect.top + portRect.height / 2) / zoom,
            x2: 0, y2: 0,
        };
        connectDrag.x2 = connectDrag.x1;
        connectDrag.y2 = connectDrag.y1;
    }

    function finishConnectDrag(e) {
        const targetNodeEl = e.target.closest(".flow-node");
        if (targetNodeEl && targetNodeEl.dataset.key !== connectDrag.fromKey) {
            const n = findNode(connectDrag.fromKey);
            const btn = n.buttons[connectDrag.portIndex];
            if (btn) {
                btn.next_client_id = targetNodeEl.dataset.key;
                markDirty();
            }
        }
        connectDrag = null;
        renderNodes();
    }

    // ------------------------------------------------------------------
    // Node selection -> open editor panel
    // ------------------------------------------------------------------
    const overlay = document.getElementById("nodeEditorOverlay");
    const panel = document.getElementById("nodeEditorPanel");
    const titleInput = document.getElementById("nodeTitleInput");
    const isStartInput = document.getElementById("nodeIsStartInput");
    const isEndInput = document.getElementById("nodeIsEndInput");
    const typeTabs = document.getElementById("nodeTypeTabs");
    const mediaField = document.getElementById("nodeMediaField");
    const mediaFile = document.getElementById("nodeMediaFile");
    const mediaFileLabel = document.getElementById("nodeMediaFileLabel");
    const mediaStatus = document.getElementById("nodeMediaStatus");
    const mediaVariableInput = document.getElementById("nodeMediaVariableInput");
    const mediaFilenameInput = document.getElementById("nodeMediaFilenameInput");
    const bodyField = document.getElementById("nodeBodyField");
    const bodyLabel = document.getElementById("nodeBodyLabel");
    const bodyInput = document.getElementById("nodeBodyInput");
    const buttonsField = document.getElementById("nodeButtonsField");
    const buttonsList = document.getElementById("nodeButtonsList");
    const captureFields = document.getElementById("nodeCaptureFields");
    const captureVariableInput = document.getElementById("nodeCaptureVariableInput");
    const captureSensitiveInput = document.getElementById("nodeCaptureSensitiveInput");
    const apiFields = document.getElementById("nodeApiFields");
    const apiUrlInput = document.getElementById("nodeApiUrlInput");
    const apiMethodInput = document.getElementById("nodeApiMethodInput");
    const apiBodyTypeTabs = document.getElementById("nodeApiBodyTypeTabs");
    const apiHeadersList = document.getElementById("nodeApiHeadersList");
    const apiBodyList = document.getElementById("nodeApiBodyList");
    const apiResponseList = document.getElementById("nodeApiResponseList");

    function setSelected(key) {
        selectedKey = key;
        renderNodes();
    }

    function selectNode(key) {
        setSelected(key);
        openEditor(key);
    }

    // File input types are Chrome/Firefox-blocked from being set
    // programmatically, so switching nodes must explicitly clear whatever
    // the browser is still natively displaying from a previous pick —
    // otherwise node B's editor can visually show node A's chosen filename.
    const MEDIA_ACCEPT = {
        image: "image/*",
        video: "video/*",
        document: ".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.csv,application/pdf,application/msword,"
            + "application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,"
            + "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-powerpoint,"
            + "application/vnd.openxmlformats-officedocument.presentationml.presentation,text/plain,text/csv",
    };

    function refreshMediaField(n) {
        mediaFile.value = "";
        mediaFile.accept = MEDIA_ACCEPT[n.message_type] || "";
        mediaFileLabel.textContent = n.media_filename || "No file chosen";
        mediaStatus.textContent = "";
        mediaVariableInput.value = n.media_id || "";
        mediaFilenameInput.value = n.media_filename || "";
    }

    // Shows/hides the right field groups for the node's current type, and
    // (re)populates them from the node — shared by opening the editor and
    // by switching the type tab while it's already open.
    function refreshTypeFields(n) {
        const isMedia = n.message_type === "image" || n.message_type === "video" || n.message_type === "document";
        const isCapture = n.message_type === "capture";
        const isApiCall = n.message_type === "api_call";

        mediaField.hidden = !isMedia;
        if (isMedia) refreshMediaField(n);

        bodyField.hidden = isApiCall;
        bodyLabel.textContent = n.message_type === "text" ? "Message text"
            : n.message_type === "capture" ? "Question to ask"
            : "Caption (optional)";
        bodyInput.value = n.body_text;

        buttonsField.hidden = isCapture || isApiCall;
        if (!isCapture && !isApiCall) renderButtonsList(n);

        captureFields.hidden = !isCapture;
        if (isCapture) {
            captureVariableInput.value = n.capture_variable;
            captureSensitiveInput.checked = n.capture_sensitive;
        }

        apiFields.hidden = !isApiCall;
        if (isApiCall) {
            apiUrlInput.value = n.api_url;
            apiMethodInput.value = n.api_method || "POST";
            apiBodyTypeTabs.querySelectorAll(".msg-type-tab").forEach(t => t.classList.toggle("is-active", t.dataset.bodyType === (n.api_body_type || "json")));
            renderKvList(apiHeadersList, n.api_headers, "key", "value", "Header name", "Value or {{variable}}");
            renderKvList(apiBodyList, n.api_body, "key", "value", "Field name", "Value or {{variable}}");
            renderKvList(apiResponseList, n.api_response_mapping, "variable", "path", "Save as", "e.g. label:Payable Salary");
        }
    }

    function openEditor(key) {
        const n = findNode(key);
        if (!n) return;
        titleInput.value = n.title;
        isStartInput.checked = n.is_start;
        isEndInput.checked = n.is_end;
        setActiveType(n.message_type);
        refreshTypeFields(n);
        overlay.hidden = false;
        panel.hidden = false;
        panel.classList.add("is-open");
    }

    function closeEditor() {
        panel.classList.remove("is-open");
        overlay.hidden = true;
        panel.hidden = true;
        selectedKey = null;
        renderNodes();
    }

    document.getElementById("closeNodeEditorBtn").addEventListener("click", closeEditor);
    overlay.addEventListener("click", closeEditor);

    function setActiveType(type) {
        typeTabs.querySelectorAll(".msg-type-tab").forEach(t => t.classList.toggle("is-active", t.dataset.type === type));
    }

    typeTabs.addEventListener("click", function (e) {
        const btn = e.target.closest(".msg-type-tab");
        if (!btn || !selectedKey) return;
        const n = findNode(selectedKey);
        const newType = btn.dataset.type;
        if (n.message_type !== newType) {
            // A media_id uploaded for one message type isn't meaningful
            // under a different one — drop it so the editor never shows a
            // leftover filename that doesn't actually belong to this type.
            n.media_id = "";
            n.media_filename = "";

            const wasSpecial = !!SPECIAL_BUTTON_SETS[n.message_type];
            const willBeSpecial = !!SPECIAL_BUTTON_SETS[newType];
            if (willBeSpecial) {
                // "Ask & Save" gets exactly one "Next" connector, "API Call"
                // gets exactly "Success"/"Failure" — these replace whatever
                // reply buttons (or the other special set) were there.
                n.buttons = SPECIAL_BUTTON_SETS[newType].map(b => ({ text: b.text, kind: b.kind, next_client_id: null }));
            } else if (wasSpecial) {
                n.buttons = [];
            }
        }
        n.message_type = newType;
        setActiveType(n.message_type);
        refreshTypeFields(n);
        renderNodes();
        markDirty();
    });

    titleInput.addEventListener("input", function () {
        if (!selectedKey) return;
        findNode(selectedKey).title = this.value;
        renderNodes();
        markDirty();
    });

    bodyInput.addEventListener("input", function () {
        if (!selectedKey) return;
        findNode(selectedKey).body_text = this.value;
        renderNodes();
        markDirty();
    });

    isStartInput.addEventListener("change", function () {
        if (!selectedKey) return;
        if (this.checked) {
            nodes.forEach(n => n.is_start = (n.client_key === selectedKey));
        } else {
            findNode(selectedKey).is_start = false;
        }
        renderNodes();
        markDirty();
    });

    isEndInput.addEventListener("change", function () {
        if (!selectedKey) return;
        findNode(selectedKey).is_end = this.checked;
        renderNodes();
        markDirty();
    });

    mediaFile.addEventListener("change", function () {
        if (!selectedKey || !this.files.length) return;
        const file = this.files[0];
        const n = findNode(selectedKey);
        mediaStatus.textContent = "Uploading...";
        const formData = new FormData();
        formData.append("file", file);
        fetch(`${cfg.uploadMediaUrl}?button=process`, {
            method: "POST",
            body: formData,
            headers: { "X-CSRFToken": getCsrfToken() },
        })
            .then(r => r.json())
            .then(res => {
                if (res.media_id) {
                    n.media_id = res.media_id;
                    n.media_filename = file.name;
                    mediaFileLabel.textContent = file.name;
                    mediaVariableInput.value = res.media_id;
                    mediaFilenameInput.value = file.name;
                    mediaStatus.textContent = "Uploaded";
                    renderNodes();
                    markDirty();
                } else {
                    mediaStatus.textContent = "Upload failed";
                }
            })
            .catch(() => { mediaStatus.textContent = "Upload failed"; });
    });

    mediaVariableInput.addEventListener("input", function () {
        if (!selectedKey) return;
        findNode(selectedKey).media_id = this.value;
        mediaFileLabel.textContent = findNode(selectedKey).media_filename || "No file chosen";
        markDirty();
    });

    mediaFilenameInput.addEventListener("input", function () {
        if (!selectedKey) return;
        findNode(selectedKey).media_filename = this.value;
        mediaFileLabel.textContent = this.value || "No file chosen";
        markDirty();
    });

    // ------------------------------------------------------------------
    // "Ask & Save" fields
    // ------------------------------------------------------------------
    captureVariableInput.addEventListener("input", function () {
        if (!selectedKey) return;
        // Keep it a safe identifier ({{name}} placeholders elsewhere rely on this).
        const clean = this.value.replace(/[^a-zA-Z0-9_]/g, "");
        if (clean !== this.value) this.value = clean;
        findNode(selectedKey).capture_variable = clean;
        renderNodes();
        markDirty();
    });

    captureSensitiveInput.addEventListener("change", function () {
        if (!selectedKey) return;
        findNode(selectedKey).capture_sensitive = this.checked;
        markDirty();
    });

    // ------------------------------------------------------------------
    // "API Call" fields
    // ------------------------------------------------------------------
    apiUrlInput.addEventListener("input", function () {
        if (!selectedKey) return;
        findNode(selectedKey).api_url = this.value;
        renderNodes();
        markDirty();
    });

    apiMethodInput.addEventListener("change", function () {
        if (!selectedKey) return;
        findNode(selectedKey).api_method = this.value;
        renderNodes();
        markDirty();
    });

    apiBodyTypeTabs.addEventListener("click", function (e) {
        const btn = e.target.closest(".msg-type-tab");
        if (!btn || !selectedKey) return;
        findNode(selectedKey).api_body_type = btn.dataset.bodyType;
        apiBodyTypeTabs.querySelectorAll(".msg-type-tab").forEach(t => t.classList.toggle("is-active", t === btn));
        markDirty();
    });

    // Generic editable key/value row list, used for API headers, body
    // fields, and the response -> variable mapping.
    function renderKvList(containerEl, pairs, keyField, valField, keyPlaceholder, valPlaceholder) {
        containerEl.innerHTML = "";
        containerEl.dataset.keyField = keyField;
        containerEl.dataset.valField = valField;
        if (keyPlaceholder) containerEl.dataset.keyPlaceholder = keyPlaceholder;
        if (valPlaceholder) containerEl.dataset.valPlaceholder = valPlaceholder;
        keyPlaceholder = containerEl.dataset.keyPlaceholder || "";
        valPlaceholder = containerEl.dataset.valPlaceholder || "";
        pairs.forEach((p, i) => {
            const row = document.createElement("div");
            row.className = "node-kv-row";
            row.innerHTML = `
                <input type="text" class="form-control node-kv-key" placeholder="${escapeHtml(keyPlaceholder)}" value="${escapeHtml(p[keyField])}" data-idx="${i}" data-role="key">
                <input type="text" class="form-control node-kv-value" placeholder="${escapeHtml(valPlaceholder)}" value="${escapeHtml(p[valField])}" data-idx="${i}" data-role="value">
                <button type="button" class="au-icon-btn node-kv-remove" data-idx="${i}" title="Remove"><i class="mdi mdi-close"></i></button>
            `;
            containerEl.appendChild(row);
        });
    }

    function wireKvList(containerEl, getPairs, addBtnId) {
        containerEl.addEventListener("input", function (e) {
            if (!selectedKey || !e.target.matches("input[data-idx]")) return;
            const pairs = getPairs();
            const idx = parseInt(e.target.dataset.idx, 10);
            const field = e.target.dataset.role === "key" ? containerEl.dataset.keyField : containerEl.dataset.valField;
            pairs[idx][field] = e.target.value;
            markDirty();
        });
        containerEl.addEventListener("click", function (e) {
            const rm = e.target.closest(".node-kv-remove");
            if (!rm || !selectedKey) return;
            const pairs = getPairs();
            pairs.splice(parseInt(rm.dataset.idx, 10), 1);
            renderKvList(containerEl, pairs, containerEl.dataset.keyField, containerEl.dataset.valField, "", "");
            markDirty();
        });
        document.getElementById(addBtnId).addEventListener("click", function () {
            if (!selectedKey) return;
            const pairs = getPairs();
            pairs.push({ [containerEl.dataset.keyField]: "", [containerEl.dataset.valField]: "" });
            renderKvList(containerEl, pairs, containerEl.dataset.keyField, containerEl.dataset.valField, "", "");
            markDirty();
        });
    }

    wireKvList(apiHeadersList, () => findNode(selectedKey).api_headers, "addApiHeaderBtn");
    wireKvList(apiBodyList, () => findNode(selectedKey).api_body, "addApiBodyBtn");
    wireKvList(apiResponseList, () => findNode(selectedKey).api_response_mapping, "addApiResponseBtn");

    function renderButtonsList(n) {
        buttonsList.innerHTML = "";
        n.buttons.forEach((b, i) => {
            const row = document.createElement("div");
            row.className = "node-button-row";
            const linked = !!b.next_client_id;
            row.innerHTML = `
                <div class="node-button-row__main">
                    <input type="text" class="form-control" maxlength="20" placeholder="Button text" value="${escapeHtml(b.text)}" data-idx="${i}">
                    <button type="button" class="au-icon-btn node-button-remove" data-idx="${i}" title="Remove button"><i class="mdi mdi-close"></i></button>
                </div>
                <div class="node-button-row__status${linked ? ' is-linked' : ''}" title="${linked ? 'Connected to another message' : 'Drag from the dot on this button (on the node itself) to another message to connect it'}">
                    <i class="mdi mdi-${linked ? 'link-variant' : 'link-variant-off'}"></i>
                    ${linked ? 'Connected' : 'Not connected yet'}
                </div>
            `;
            buttonsList.appendChild(row);
        });
        document.getElementById("addNodeButtonBtn").disabled = n.buttons.length >= 3;
    }

    buttonsList.addEventListener("input", function (e) {
        if (!e.target.matches("input[data-idx]") || !selectedKey) return;
        const n = findNode(selectedKey);
        const idx = parseInt(e.target.dataset.idx, 10);
        n.buttons[idx].text = e.target.value;
        markDirty();
    });

    buttonsList.addEventListener("click", function (e) {
        const rm = e.target.closest(".node-button-remove");
        if (!rm || !selectedKey) return;
        const n = findNode(selectedKey);
        const idx = parseInt(rm.dataset.idx, 10);
        n.buttons.splice(idx, 1);
        renderButtonsList(n);
        renderNodes();
        markDirty();
    });

    document.getElementById("addNodeButtonBtn").addEventListener("click", function () {
        if (!selectedKey) return;
        const n = findNode(selectedKey);
        if (n.buttons.length >= 3) return;
        n.buttons.push({ text: "", kind: "reply", next_client_id: null });
        renderButtonsList(n);
        renderNodes();
        markDirty();
    });

    document.getElementById("deleteNodeBtn").addEventListener("click", function () {
        if (!selectedKey) return;
        if (!confirm("Delete this message? Any buttons pointing to it will be disconnected.")) return;
        nodes = nodes.filter(n => n.client_key !== selectedKey);
        nodes.forEach(n => n.buttons.forEach(b => { if (b.next_client_id === selectedKey) b.next_client_id = null; }));
        if (!nodes.some(n => n.is_start) && nodes.length) nodes[0].is_start = true;
        closeEditor();
        markDirty();
    });

    // ------------------------------------------------------------------
    // Add new node
    // ------------------------------------------------------------------
    document.getElementById("addNodeBtn").addEventListener("click", function () {
        const key = makeKey();
        const offset = (nodes.length % 6) * 24;
        nodes.push({
            client_key: key, title: "", message_type: "text", body_text: "",
            media_id: "", media_filename: "", pos_x: 60 + offset, pos_y: 60 + offset,
            is_end: false, is_start: false,
            capture_variable: "", capture_sensitive: false,
            api_url: "", api_method: "POST", api_body_type: "json", api_headers: [], api_body: [], api_response_mapping: [],
            buttons: [],
        });
        renderNodes();
        selectNode(key);
        markDirty();
    });

    // ------------------------------------------------------------------
    // Save
    // ------------------------------------------------------------------
    document.getElementById("saveFlowBtn").addEventListener("click", function () {
        const btn = this;
        window.AppLoading && window.AppLoading.start ? window.AppLoading.start(btn, "Saving...") : null;

        const payload = {
            name: document.getElementById("flowNameInput").value.trim() || "Untitled Flow",
            trigger_keywords: document.getElementById("flowTriggerKeywords").value.split(",").map(s => s.trim()).filter(Boolean),
            trigger_any_message: document.getElementById("flowTriggerAny").checked,
            is_active: document.getElementById("flowIsActive").checked,
            nodes: nodes.map(n => ({
                client_key: n.client_key,
                title: n.title,
                message_type: n.message_type,
                body_text: n.body_text,
                media_id: n.media_id,
                media_filename: n.media_filename,
                pos_x: n.pos_x,
                pos_y: n.pos_y,
                is_end: n.is_end,
                is_start: n.is_start,
                capture_variable: n.capture_variable,
                capture_sensitive: n.capture_sensitive,
                api_url: n.api_url,
                api_method: n.api_method,
                api_body_type: n.api_body_type,
                api_headers: pairsToDict(n.api_headers, "key", "value"),
                api_body: pairsToDict(n.api_body, "key", "value"),
                api_response_mapping: pairsToDict(n.api_response_mapping, "variable", "path"),
                buttons: n.buttons.filter(b => b.text.trim()).map(b => ({ text: b.text, kind: b.kind || "reply", next_client_id: b.next_client_id })),
            })),
        };

        fetch(cfg.saveUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
            body: JSON.stringify(payload),
        })
            .then(r => r.json())
            .then(res => {
                const statusEl = document.getElementById("flowSaveStatus");
                if (res.success) {
                    dirty = false;
                    statusEl.textContent = "Saved";
                    setTimeout(() => { if (!dirty) statusEl.textContent = ""; }, 2000);
                } else {
                    const msg = res.error || "Failed to save";
                    statusEl.textContent = msg;
                    alert(msg);
                }
            })
            .catch(() => { document.getElementById("flowSaveStatus").textContent = "Failed to save"; })
            .finally(() => {
                if (window.AppLoading && window.AppLoading.stop) window.AppLoading.stop(btn);
            });
    });

    document.getElementById("flowNameInput").addEventListener("input", markDirty);
    document.getElementById("flowTriggerKeywords").addEventListener("input", markDirty);
    document.getElementById("flowTriggerAny").addEventListener("change", markDirty);
    document.getElementById("flowIsActive").addEventListener("change", markDirty);

    window.addEventListener("beforeunload", function (e) {
        if (dirty) { e.preventDefault(); e.returnValue = ""; }
    });

    window.addEventListener("resize", drawConnectors);

    // ------------------------------------------------------------------
    // Zoom controls
    // ------------------------------------------------------------------
    const zoomLevelLabel = document.getElementById("zoomLevelLabel");

    function applyZoom() {
        canvas.style.transform = `scale(${zoom})`;
        zoomLevelLabel.textContent = Math.round(zoom * 100) + "%";
        drawConnectors();
    }

    document.getElementById("zoomInBtn").addEventListener("click", function () {
        zoom = Math.min(ZOOM_MAX, Math.round((zoom + ZOOM_STEP) * 100) / 100);
        applyZoom();
    });
    document.getElementById("zoomOutBtn").addEventListener("click", function () {
        zoom = Math.max(ZOOM_MIN, Math.round((zoom - ZOOM_STEP) * 100) / 100);
        applyZoom();
    });
    document.getElementById("zoomResetBtn").addEventListener("click", function () {
        zoom = 1;
        applyZoom();
    });

    renderNodes();
})();
