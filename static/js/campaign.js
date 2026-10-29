(function () {
    "use strict";

    const cfg = window.CAMPAIGN_CONFIG || {};
    const form = document.getElementById("campaignForm");
    if (!form) return;

    const state = {
        messageType: "text",
        campaignType: "broadcast",
        audienceMode: "all",
        scheduleType: "now",
        selectedTags: [],
        selectedContacts: {}, // id -> {name, mobile_number}
        totalContacts: cfg.totalContacts || 0,
        templateData: null,
        isSubmitting: false,
    };

    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }

    function markStepDone(n) {
        document.querySelectorAll(".campaign-step").forEach(el => {
            const step = parseInt(el.dataset.step, 10);
            el.classList.toggle("is-done", step < n);
            el.classList.toggle("is-active", step === n);
        });
    }

    // ------------------------------------------------------------------
    // Campaign name
    // ------------------------------------------------------------------
    const campaignNameInput = document.getElementById("campaignNameInput");
    const campaignNameCount = document.getElementById("campaignNameCount");
    campaignNameInput.addEventListener("input", function () {
        campaignNameCount.textContent = `${this.value.length}/100`;
        markStepDone(this.value.trim() ? 2 : 1);
    });

    // ------------------------------------------------------------------
    // Campaign type cards
    // ------------------------------------------------------------------
    document.querySelectorAll(".campaign-type-card").forEach(card => {
        card.addEventListener("click", function () {
            document.querySelectorAll(".campaign-type-card").forEach(c => c.classList.remove("is-active"));
            this.classList.add("is-active");
            this.querySelector("input[type=radio]").checked = true;
            state.campaignType = this.querySelector("input[type=radio]").value;
            updatePreview();
        });
    });

    // ------------------------------------------------------------------
    // Message type tabs
    // ------------------------------------------------------------------
    document.querySelectorAll(".msg-type-tab[data-msg-type]").forEach(tab => {
        tab.addEventListener("click", function () {
            document.querySelectorAll(".msg-type-tab[data-msg-type]").forEach(t => t.classList.remove("is-active"));
            this.classList.add("is-active");
            state.messageType = this.dataset.msgType;

            document.querySelectorAll(".msg-type-panel").forEach(panel => {
                panel.hidden = panel.dataset.panel !== state.messageType;
            });

            // A media_id from a previous image/document selection must not
            // silently carry over to a different message type.
            document.getElementById("mediaIdInput").value = "";
            document.getElementById("mediaFilenameInput").value = "";
            state.localMediaPreviewUrl = null;

            if (state.messageType === "template") {
                markStepDone(3);
                refreshTemplateIfNeeded();
            }
            updatePreview();
        });
    });

    const messageText = document.getElementById("messageText");
    const messageTextCount = document.getElementById("messageTextCount");
    messageText.addEventListener("input", function () {
        messageTextCount.textContent = `${this.value.length}/1024`;
        updatePreview();
    });

    document.querySelectorAll('[data-media-caption]').forEach(el => {
        el.addEventListener("input", updatePreview);
    });

    // ------------------------------------------------------------------
    // Media upload (image / document message types)
    // ------------------------------------------------------------------
    function uploadFileGetMediaId(file, statusEl) {
        statusEl.textContent = "Uploading...";
        const formData = new FormData();
        formData.append("file", file);
        return fetch(`${cfg.uploadMediaUrl}?button=process`, {
            method: "POST",
            body: formData,
            headers: { "X-CSRFToken": getCsrfToken() },
        })
            .then(r => r.json())
            .then(data => {
                if (data.media_id) {
                    statusEl.textContent = "Uploaded";
                    statusEl.classList.add("au-cell-title");
                    return data.media_id;
                }
                statusEl.textContent = "Upload failed";
                return null;
            })
            .catch(err => {
                console.error("Upload error:", err);
                statusEl.textContent = "Upload failed";
                return null;
            });
    }

    ["image", "document"].forEach(kind => {
        const fileInput = document.getElementById(`media${kind[0].toUpperCase()}${kind.slice(1)}File`);
        const label = document.getElementById(`media${kind[0].toUpperCase()}${kind.slice(1)}Label`);
        const filenameEl = label.querySelector("[data-media-filename]");
        const btn = document.querySelector(`[data-upload-media="${kind}"]`);
        const statusEl = btn.parentElement.querySelector("[data-media-status]");

        fileInput.addEventListener("change", function () {
            filenameEl.textContent = this.files.length ? this.files[0].name : "No file chosen";
            statusEl.textContent = "";
            document.getElementById("mediaIdInput").value = "";
            document.getElementById("mediaFilenameInput").value = this.files.length ? this.files[0].name : "";
            state.localMediaPreviewUrl = this.files.length ? URL.createObjectURL(this.files[0]) : null;
            updatePreview();
        });

        btn.addEventListener("click", function () {
            if (!fileInput.files.length) {
                statusEl.textContent = "Choose a file first";
                return;
            }
            uploadFileGetMediaId(fileInput.files[0], statusEl).then(mediaId => {
                if (mediaId) {
                    document.getElementById("mediaIdInput").value = mediaId;
                    markStepDone(3);
                }
            });
        });
    });

    // ------------------------------------------------------------------
    // Schedule type
    // ------------------------------------------------------------------
    const scheduleTimeWrap = document.getElementById("scheduleTimeWrap");
    document.querySelectorAll(".msg-type-tab[data-schedule]").forEach(tab => {
        tab.addEventListener("click", function () {
            document.querySelectorAll(".msg-type-tab[data-schedule]").forEach(t => t.classList.remove("is-active"));
            this.classList.add("is-active");
            state.scheduleType = this.dataset.schedule;
            scheduleTimeWrap.hidden = state.scheduleType !== "later";
        });
    });

    // ------------------------------------------------------------------
    // Additional options
    // ------------------------------------------------------------------
    document.getElementById("unsubscribeToggle").addEventListener("change", function () {
        document.getElementById("unsubscribeInput").value = this.checked ? "1" : "0";
        updatePreview();
    });
    document.getElementById("trackStatusToggle").addEventListener("change", function () {
        document.getElementById("trackStatusInput").value = this.checked ? "1" : "0";
    });

    // ------------------------------------------------------------------
    // Audience: mode tabs
    // ------------------------------------------------------------------
    const audienceTagPanel = document.getElementById("audienceTagPanel");
    const audienceManualPanel = document.getElementById("audienceManualPanel");

    function setAudienceMode(mode) {
        state.audienceMode = mode;
        document.getElementById("audienceModeInput").value = mode;
        document.querySelectorAll(".msg-type-tab[data-audience-mode]").forEach(t => {
            t.classList.toggle("is-active", t.dataset.audienceMode === mode);
        });
        audienceTagPanel.hidden = mode !== "tag";
        audienceManualPanel.hidden = mode !== "manual";
        recomputeAudienceStats();
        markStepDone(mode ? 3 : 2);
    }

    document.querySelectorAll(".msg-type-tab[data-audience-mode]").forEach(tab => {
        tab.addEventListener("click", function () { setAudienceMode(this.dataset.audienceMode); });
    });

    function renderTagChips() {
        const box = document.getElementById("selectedTagsChips");
        box.innerHTML = "";
        state.selectedTags.forEach(tag => {
            const chip = document.createElement("span");
            chip.className = "chip";
            chip.innerHTML = `${tag} <button type="button" aria-label="Remove">&times;</button>`;
            chip.querySelector("button").addEventListener("click", () => {
                state.selectedTags = state.selectedTags.filter(t => t !== tag);
                document.getElementById("tagsInput").value = state.selectedTags.join(",");
                renderTagChips();
                recomputeAudienceStats();
            });
            box.appendChild(chip);
        });
    }

    function addTag(tagName) {
        if (!tagName || state.selectedTags.includes(tagName)) return;
        state.selectedTags.push(tagName);
        document.getElementById("tagsInput").value = state.selectedTags.join(",");
        renderTagChips();
        recomputeAudienceStats();
    }

    document.getElementById("tagPicker").addEventListener("change", function () {
        addTag(this.value);
        this.value = "";
    });

    document.getElementById("clearTagsLink").addEventListener("click", function (e) {
        e.preventDefault();
        state.selectedTags = [];
        document.getElementById("tagsInput").value = "";
        renderTagChips();
        recomputeAudienceStats();
    });

    // ------------------------------------------------------------------
    // Audience: manual contact picker
    // ------------------------------------------------------------------
    const manualContactSearch = document.getElementById("manualContactSearch");
    const manualContactList = document.getElementById("manualContactList");
    let manualSearchTimer = null;

    function renderManualResults(contacts) {
        manualContactList.innerHTML = "";
        if (!contacts.length) {
            manualContactList.innerHTML = '<div class="au-empty" style="padding:20px;"><i class="mdi mdi-account-search-outline"></i>No contacts found</div>';
            return;
        }
        contacts.forEach(c => {
            const row = document.createElement("div");
            row.className = "manual-contact-row";
            const isSelected = !!state.selectedContacts[c.id];
            row.innerHTML = `
                <input type="checkbox" ${isSelected ? "checked" : ""}>
                <span class="manual-contact-row__name">${c.name}</span>
                <span class="au-cell-sub">${c.mobile_number}</span>
            `;
            row.addEventListener("click", function (e) {
                e.preventDefault();
                const checkbox = row.querySelector("input");
                if (state.selectedContacts[c.id]) {
                    delete state.selectedContacts[c.id];
                    checkbox.checked = false;
                } else {
                    state.selectedContacts[c.id] = c;
                    checkbox.checked = true;
                }
                syncSelectedContacts();
            });
            manualContactList.appendChild(row);
        });
    }

    function syncSelectedContacts() {
        const ids = Object.keys(state.selectedContacts);
        document.getElementById("contactIdsInput").value = ids.join(",");

        const box = document.getElementById("selectedContactsChips");
        box.innerHTML = "";
        ids.forEach(id => {
            const c = state.selectedContacts[id];
            const chip = document.createElement("span");
            chip.className = "chip";
            chip.innerHTML = `${c.name} <button type="button" aria-label="Remove">&times;</button>`;
            chip.querySelector("button").addEventListener("click", () => {
                delete state.selectedContacts[id];
                syncSelectedContacts();
                // Uncheck it in the results list too, if it's currently shown.
                manualContactList.querySelectorAll(".manual-contact-row").forEach(row => {
                    if (row.querySelector(".manual-contact-row__name").textContent === c.name
                        && row.querySelector(".au-cell-sub").textContent === c.mobile_number) {
                        row.querySelector("input").checked = false;
                    }
                });
            });
            box.appendChild(chip);
        });
        recomputeAudienceStats();
    }

    manualContactSearch.addEventListener("input", function () {
        clearTimeout(manualSearchTimer);
        const q = this.value.trim();
        manualSearchTimer = setTimeout(() => {
            fetch(`${cfg.searchContactsUrl}?q=${encodeURIComponent(q)}`)
                .then(r => r.json())
                .then(data => renderManualResults(data.contacts || []))
                .catch(() => {});
        }, 300);
    });
    // Load an initial batch so the list isn't empty on first open
    manualContactSearch.addEventListener("focus", function () {
        if (!manualContactList.children.length) {
            fetch(`${cfg.searchContactsUrl}?q=`)
                .then(r => r.json())
                .then(data => renderManualResults(data.contacts || []))
                .catch(() => {});
        }
    }, { once: true });

    // ------------------------------------------------------------------
    // Audience stats
    // ------------------------------------------------------------------
    let audienceRefreshTimer = null;

    function recomputeAudienceStats() {
        if (state.audienceMode === "all") {
            setAudienceStats(state.totalContacts, state.totalContacts, 0);
            return;
        }
        if (state.audienceMode === "manual") {
            const n = Object.keys(state.selectedContacts).length;
            setAudienceStats(state.totalContacts, n, Math.max(state.totalContacts - n, 0));
            return;
        }
        // "tag" mode needs the server to know how many contacts match
        clearTimeout(audienceRefreshTimer);
        audienceRefreshTimer = setTimeout(() => refreshFromServer(), 350);
    }

    function setAudienceStats(total, selected, unselected) {
        document.getElementById("statTotal").textContent = total;
        document.getElementById("statSelected").textContent = selected;
        document.getElementById("statUnselected").textContent = unselected;
    }

    // ------------------------------------------------------------------
    // Server refresh (template details + tag-based audience counts)
    // ------------------------------------------------------------------
    function buildFormData(action) {
        const fd = new FormData(form);
        fd.set("action", action);
        fd.set("message_type", state.messageType);
        return fd;
    }

    function refreshFromServer() {
        return fetch(cfg.createCampaignUrl, {
            method: "POST",
            body: buildFormData("refresh"),
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(r => r.json())
            .then(data => {
                // "manual" mode's true selected count is just how many
                // contacts are checked client-side (recomputeAudienceStats
                // already keeps it accurate) — it never needs the server's
                // number. Applying it here anyway caused a race: this
                // request is built from whatever audience_mode was set the
                // moment THIS call was fired, so a template refresh kicked
                // off before the audience mode/contact ids were restored
                // (e.g. loading a draft/retarget prefill) would ask with
                // "all" and then clobber the correct manual count whenever
                // its response happened to land after the real one.
                if (typeof data.audience_total === "number" && state.audienceMode !== "manual") {
                    setAudienceStats(data.audience_total, data.audience_selected, data.audience_unselected);
                }
                if (data.template_data) {
                    state.templateData = data.template_data;
                    renderTemplateDetails(data.template_data, cfg.prebuiltTags || []);
                    // When resuming a draft, its saved variable values can only
                    // be applied once these inputs actually exist in the DOM.
                    if (state.pendingRestoreFinalData) {
                        applyFinalDataToTemplateInputs(state.pendingRestoreFinalData);
                        state.pendingRestoreFinalData = null;
                    }
                }
                updatePreview();
                return data;
            })
            .catch(err => console.error("Error refreshing campaign details:", err));
    }

    function applyFinalDataToTemplateInputs(finalData) {
        ["headerExample", "bodyExample", "buttonExample"].forEach(divId => {
            const section = finalData[
                divId === "headerExample" ? "header_info" : divId === "bodyExample" ? "body_info" : "buttons_info"
            ] || {};
            const container = document.getElementById(divId);
            Object.keys(section).forEach(name => {
                const input = container.querySelector(`[name="${name}"]`);
                if (input) input.value = section[name];
            });
        });
        saveFinalDataAndPreview();
    }

    const templateSelect = document.getElementById("template_name");
    function refreshTemplateIfNeeded() {
        if (state.messageType === "template" && templateSelect.value) {
            refreshFromServer();
        }
    }
    templateSelect.addEventListener("change", function () {
        state.templateData = null;
        document.getElementById("finalDataInput").value = "{}";
        document.getElementById("headerExample").innerHTML = "";
        document.getElementById("bodyExample").innerHTML = "";
        document.getElementById("buttonExample").innerHTML = "";
        if (this.value) {
            markStepDone(3);
            refreshFromServer();
        } else {
            document.getElementById("templateDetailsContainer").style.display = "none";
            updatePreview();
        }
    });

    // ------------------------------------------------------------------
    // Template variable form + preview data (ported from the legacy
    // multi-step flow, adapted to render straight into the new layout)
    // ------------------------------------------------------------------
    function collectFinalData() {
        return {
            header_info: getInputsData("headerExample"),
            body_info: getInputsData("bodyExample"),
            buttons_info: getInputsData("buttonExample"),
        };
    }

    function getInputsData(divId) {
        const container = document.getElementById(divId);
        const inputs = container.querySelectorAll("input, select");
        const data = {};
        inputs.forEach(input => { data[input.name] = input.value; });
        return data;
    }

    function saveFinalDataAndPreview() {
        document.getElementById("finalDataInput").value = JSON.stringify(collectFinalData());
        updatePreview();
    }

    function renderTemplateDetails(tpl, prebuiltTags) {
        document.getElementById("templateDetailsContainer").style.display = "block";
        const headerExample = document.getElementById("headerExample");
        const bodyExample = document.getElementById("bodyExample");
        const buttonExample = document.getElementById("buttonExample");
        headerExample.innerHTML = "";
        bodyExample.innerHTML = "";
        buttonExample.innerHTML = "";
        headerExample.style.display = "none";
        bodyExample.style.display = "none";
        buttonExample.style.display = "none";

        const tagOptions = (selectedTag) => {
            let html = '<option value="">Type value instead</option>';
            prebuiltTags.forEach(tag => {
                html += `<option value="${tag}" ${tag === selectedTag ? "selected" : ""}>${tag}</option>`;
            });
            return html;
        };

        // HEADER
        const headerComponent = (tpl.components || []).find(c => c.type === "HEADER");
        if (headerComponent && headerComponent.example) {
            headerExample.style.display = "block";
            if (headerComponent.format === "TEXT" || !headerComponent.format) {
                const htext = headerComponent.example.header_text || [];
                let html = '<h6 class="mb-2">Header variables</h6>';
                for (let i = 0; i < htext.length; i++) {
                    html += `
                        <div class="mb-2">
                            <label class="form-label small">Value ${i + 1}</label>
                            <div class="d-flex gap-2">
                                <input type="text" name="header_value_${i + 1}" class="form-control form-control-sm" placeholder="Value ${i + 1}">
                                <select name="header_tag_${i + 1}" class="form-select form-select-sm" style="max-width:180px;">${tagOptions()}</select>
                            </div>
                        </div>`;
                }
                headerExample.innerHTML = html;
            } else if (["IMAGE", "VIDEO", "DOCUMENT"].includes(headerComponent.format)) {
                const accept = headerComponent.format === "IMAGE" ? "image/*" : headerComponent.format === "VIDEO" ? "video/*" : ".pdf,.doc,.docx";
                const isDocument = headerComponent.format === "DOCUMENT";
                let html = `
                    <h6 class="mb-2">Header media (${headerComponent.format.toLowerCase()})</h6>
                    <div class="d-flex gap-2 align-items-center flex-wrap">
                        <input type="file" id="headerFileInput" accept="${accept}" class="form-control form-control-sm" style="max-width:220px;">
                        <button type="button" id="uploadHeaderMediaBtn" class="btn-au-outline btn-sm">Upload</button>
                        <span id="headerUploadStatus" class="au-cell-sub"></span>
                    </div>
                    <input type="hidden" name="header_value" id="headerValue">`;
                // The document Cloud API payload needs a filename to show
                // the recipient — captured from whatever file gets uploaded.
                if (isDocument) {
                    html += `<input type="hidden" name="header_file_name" id="headerFileName">`;
                }
                headerExample.innerHTML = html;
                document.getElementById("uploadHeaderMediaBtn").addEventListener("click", function () {
                    const fileInput = document.getElementById("headerFileInput");
                    const statusEl = document.getElementById("headerUploadStatus");
                    if (!fileInput.files.length) { statusEl.textContent = "Choose a file first"; return; }
                    if (isDocument) {
                        document.getElementById("headerFileName").value = fileInput.files[0].name;
                    }
                    uploadFileGetMediaId(fileInput.files[0], statusEl).then(mediaId => {
                        if (mediaId) {
                            document.getElementById("headerValue").value = mediaId;
                            saveFinalDataAndPreview();
                        }
                    });
                });
            }
        }

        // BODY
        const bodyComponent = (tpl.components || []).find(c => c.type === "BODY");
        if (bodyComponent && bodyComponent.example) {
            bodyExample.style.display = "block";
            const btext = (bodyComponent.example.body_text && bodyComponent.example.body_text[0]) || [];
            let html = '<h6 class="mb-2">Body variables</h6>';
            for (let i = 0; i < btext.length; i++) {
                html += `
                    <div class="mb-2">
                        <label class="form-label small">Value ${i + 1}</label>
                        <div class="d-flex gap-2">
                            <input type="text" name="body_value_${i + 1}" class="form-control form-control-sm" placeholder="Value ${i + 1}">
                            <select name="body_tag_${i + 1}" class="form-select form-select-sm" style="max-width:180px;">${tagOptions()}</select>
                        </div>
                    </div>`;
            }
            bodyExample.innerHTML = html;
        }

        // BUTTONS
        const buttonsComponent = (tpl.components || []).find(c => c.type === "BUTTONS");
        if (buttonsComponent && Array.isArray(buttonsComponent.buttons)) {
            let html = "";
            buttonsComponent.buttons.forEach((button, index) => {
                if (button.type === "URL" && button.example) {
                    html += `
                        <div class="mb-2">
                            <label class="form-label small">"${button.text}" link variable</label>
                            <input type="text" name="button_value_${index}_URL" class="form-control form-control-sm" placeholder="Enter value">
                        </div>`;
                } else if (button.type === "COPY_CODE") {
                    const example = button.example ? button.example[0] : "";
                    html += `
                        <div class="mb-2">
                            <label class="form-label small">"${button.text}" coupon code</label>
                            <input type="text" name="button_value_COPY_CODE" value="${example}" class="form-control form-control-sm">
                        </div>`;
                }
            });
            if (html) {
                buttonExample.style.display = "block";
                buttonExample.innerHTML = `<h6 class="mb-2">Button variables</h6>${html}`;
            }
        }

        headerExample.querySelectorAll("input, select").forEach(el => el.addEventListener("input", saveFinalDataAndPreview));
        headerExample.querySelectorAll("select").forEach(el => el.addEventListener("change", saveFinalDataAndPreview));
        bodyExample.querySelectorAll("input, select").forEach(el => el.addEventListener("input", saveFinalDataAndPreview));
        bodyExample.querySelectorAll("select").forEach(el => el.addEventListener("change", saveFinalDataAndPreview));
        buttonExample.querySelectorAll("input").forEach(el => el.addEventListener("input", saveFinalDataAndPreview));

        saveFinalDataAndPreview();
    }

    // ------------------------------------------------------------------
    // Live preview
    // ------------------------------------------------------------------
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str || "";
        return div.innerHTML;
    }

    function personalizedSample(text) {
        return (text || "").replace(/\{\{\s*name\s*\}\}/gi, "John");
    }

    function unsubscribeButtonHtml() {
        return document.getElementById("unsubscribeToggle").checked
            ? '<span class="wa-bubble__button"><i class="mdi mdi-reply-outline"></i> Unsubscribe</span>'
            : "";
    }

    function updatePreview() {
        const target = document.getElementById("wa-preview-content");
        const isPersonalized = state.campaignType === "personalized";

        if (state.messageType === "text") {
            const text = messageText.value.trim();
            target.innerHTML = escapeHtml(isPersonalized ? personalizedSample(text) : text).replace(/\n/g, "<br>") || '<span class="au-cell-sub">Start typing your message to see a preview here.</span>';
        } else if (state.messageType === "image" || state.messageType === "document") {
            // Image has no caption field — only Document does.
            const captionField = document.querySelector(`[data-media-caption="${state.messageType}"]`);
            const caption = captionField ? captionField.value.trim() : "";
            const captionHtml = caption ? escapeHtml(isPersonalized ? personalizedSample(caption) : caption).replace(/\n/g, "<br>") : "";
            if (state.messageType === "image" && state.localMediaPreviewUrl) {
                target.innerHTML = `<img src="${state.localMediaPreviewUrl}" alt="">${captionHtml}`;
            } else if (state.messageType === "document") {
                target.innerHTML = `<div class="d-flex align-items-center gap-2 mb-2"><i class="mdi mdi-file-document-outline" style="font-size:28px;color:#98a2b3;"></i><span class="au-cell-sub">Document attached</span></div>${captionHtml}`;
            } else {
                target.innerHTML = captionHtml || '<span class="au-cell-sub">Upload a file to see a preview here.</span>';
            }
        } else if (state.messageType === "template") {
            target.innerHTML = buildTemplatePreviewHtml();
        }

        // Append the unsubscribe affordance to non-template previews when enabled
        const bubble = document.getElementById("wa-preview-bubble");
        let btnSlot = bubble.querySelector(".wa-bubble__button");
        if (btnSlot) btnSlot.remove();
        if (state.messageType !== "template" && document.getElementById("unsubscribeToggle").checked) {
            bubble.querySelector(".wa-bubble__time").insertAdjacentHTML("beforebegin", unsubscribeButtonHtml());
        }
    }

    function buildTemplatePreviewHtml() {
        if (!state.templateData) return '<span class="au-cell-sub">Select a template to see a preview here.</span>';
        const tpl = state.templateData;
        const finalData = collectFinalData();
        let html = "";

        const headerComponent = (tpl.components || []).find(c => c.type === "HEADER");
        if (headerComponent) {
            if (headerComponent.format === "TEXT" || !headerComponent.format) {
                html += `<div style="font-weight:700;margin-bottom:4px;">${escapeHtml(headerComponent.text || "")}</div>`;
            } else if (headerComponent.format === "IMAGE") {
                html += `<div class="d-flex align-items-center gap-2 mb-2"><i class="mdi mdi-image-outline" style="font-size:28px;color:#98a2b3;"></i><span class="au-cell-sub">Image header</span></div>`;
            } else if (headerComponent.format === "DOCUMENT") {
                html += `<div class="d-flex align-items-center gap-2 mb-2"><i class="mdi mdi-file-document-outline" style="font-size:28px;color:#98a2b3;"></i><span class="au-cell-sub">Document header</span></div>`;
            } else if (headerComponent.format === "VIDEO") {
                html += `<div class="d-flex align-items-center gap-2 mb-2"><i class="mdi mdi-video-outline" style="font-size:28px;color:#98a2b3;"></i><span class="au-cell-sub">Video header</span></div>`;
            }
        }

        const bodyComponent = (tpl.components || []).find(c => c.type === "BODY");
        if (bodyComponent) {
            let bodyText = bodyComponent.text || "";
            let i = 1;
            while (bodyText.includes(`{{${i}}}`)) {
                const tagVal = finalData.body_info[`body_tag_${i}`];
                const manualVal = finalData.body_info[`body_value_${i}`];
                const shown = tagVal ? `[${tagVal}]` : (manualVal || `{{${i}}}`);
                bodyText = bodyText.split(`{{${i}}}`).join(shown);
                i++;
            }
            html += `<div>${escapeHtml(bodyText).replace(/\n/g, "<br>")}</div>`;
        }

        const footerComponent = (tpl.components || []).find(c => c.type === "FOOTER");
        if (footerComponent) {
            html += `<div class="au-cell-sub mt-1">${escapeHtml(footerComponent.text || "")}</div>`;
        }

        const buttonsComponent = (tpl.components || []).find(c => c.type === "BUTTONS");
        if (buttonsComponent && Array.isArray(buttonsComponent.buttons)) {
            buttonsComponent.buttons.slice(0, 3).forEach(button => {
                const icon = button.type === "URL" ? "mdi-open-in-new" : button.type === "PHONE_NUMBER" ? "mdi-phone-outline" : button.type === "COPY_CODE" ? "mdi-content-copy" : "mdi-reply-outline";
                html += `<span class="wa-bubble__button"><i class="mdi ${icon}"></i> ${escapeHtml(button.text || "Button")}</span>`;
            });
        }

        return html || '<span class="au-cell-sub">No content in this template.</span>';
    }

    // ------------------------------------------------------------------
    // Test send
    // ------------------------------------------------------------------
    function showTestStatus(text, isError) {
        const el = document.getElementById("testStatus");
        el.textContent = text;
        el.className = "au-toast mt-2 " + (isError ? "au-toast--error" : "au-toast--success");
        el.style.display = "block";
    }

    document.getElementById("test-btn").addEventListener("click", function () {
        if (state.isSubmitting) return;
        const testNumber = document.getElementById("test_number").value.trim();
        if (!testNumber) { showTestStatus("Please enter a test number.", true); return; }

        state.isSubmitting = true;
        window.AppLoading.start(this, "Sending…");
        const testBtn = this;
        const fd = buildFormData("test");
        fd.set("test_number", testNumber);
        fetch(cfg.createCampaignUrl, {
            method: "POST",
            body: fd,
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(r => r.json())
            .then(data => {
                if (data.errors && data.errors.length) {
                    showTestStatus(data.errors.join(" "), true);
                } else {
                    showTestStatus(data.test_success || "Test message sent!", false);
                }
            })
            .catch(err => {
                console.error("Error sending test message:", err);
                showTestStatus("Could not send test message.", true);
            })
            .finally(() => {
                state.isSubmitting = false;
                window.AppLoading.stop(testBtn);
            });
    });

    function messageReadyForSend() {
        if (state.messageType === "text") return !!messageText.value.trim();
        if (state.messageType === "template") return !!templateSelect.value;
        if (state.messageType === "image" || state.messageType === "document") return !!document.getElementById("mediaIdInput").value;
        return false;
    }

    // ------------------------------------------------------------------
    // Send campaign / save as draft
    // ------------------------------------------------------------------
    function showTopLevelError(msg) {
        const el = document.getElementById("formTopLevelError");
        el.textContent = msg;
        el.style.display = "block";
        el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    function hideTopLevelError() {
        document.getElementById("formTopLevelError").style.display = "none";
    }

    function submitCampaign(sendMode) {
        if (state.isSubmitting) return;
        hideTopLevelError();

        const name = campaignNameInput.value.trim();
        if (!name) { showTopLevelError("Campaign name is required."); return; }
        if (sendMode !== "draft" && !messageReadyForSend()) { showTopLevelError("Please finish setting up your message before sending."); return; }

        document.getElementById("sendMode").value = sendMode;
        if (sendMode === "schedule" && !document.getElementById("scheduledTimeInput").value) {
            showTopLevelError("Please choose a date and time to schedule this campaign.");
            return;
        }

        state.isSubmitting = true;
        const sendBtn = document.getElementById("sendCampaignBtn");
        const draftBtn = document.getElementById("saveDraftBtn");
        const clickedBtn = sendMode === "draft" ? draftBtn : sendBtn;
        const otherBtn = sendMode === "draft" ? sendBtn : draftBtn;
        window.AppLoading.start(clickedBtn, sendMode === "draft" ? "Saving…" : sendMode === "schedule" ? "Scheduling…" : "Sending…");
        otherBtn.disabled = true;

        fetch(cfg.createCampaignUrl, {
            method: "POST",
            body: buildFormData("submit"),
            headers: { "X-Requested-With": "XMLHttpRequest" },
            redirect: "manual",
        })
            .then(response => {
                // A same-origin redirect (opaqueredirect under redirect:"manual")
                // means the server issued redirect('campaign_list') -> success.
                if (response.type === "opaqueredirect" || response.status === 0) {
                    window.location.href = cfg.campaignListUrl;
                    return null;
                }
                return response.json();
            })
            .then(data => {
                if (!data) return;
                const errorText = (data.errors && data.errors.length)
                    ? data.errors.join(" ")
                    : "Could not create the campaign. Please check the form and try again.";
                showTopLevelError(errorText);
            })
            .catch(err => {
                console.error("Error submitting campaign:", err);
                showTopLevelError("Something went wrong. Please try again.");
            })
            .finally(() => {
                state.isSubmitting = false;
                window.AppLoading.stop(clickedBtn);
                otherBtn.disabled = false;
            });
    }

    document.getElementById("sendCampaignBtn").addEventListener("click", function () {
        submitCampaign(state.scheduleType === "later" ? "schedule" : "now");
    });
    document.getElementById("saveDraftBtn").addEventListener("click", function () {
        submitCampaign("draft");
    });

    // ------------------------------------------------------------------
    // Resume an existing draft (?draft_id=... on the page load)
    // ------------------------------------------------------------------
    function loadDraft(draft) {
        document.getElementById("draftIdInput").value = draft.id;

        campaignNameInput.value = draft.campaign_name || "";
        campaignNameCount.textContent = `${campaignNameInput.value.length}/100`;

        const typeRadio = document.querySelector(`.campaign-type-card input[value="${draft.campaign_type}"]`);
        if (typeRadio) typeRadio.closest(".campaign-type-card").click();

        const msgTab = document.querySelector(`.msg-type-tab[data-msg-type="${draft.message_type}"]`);
        if (msgTab) msgTab.click();

        // Audience mode is restored before the message-type branch below
        // (which, for a template, fires a server refresh) so that request
        // — and anything else reading the audience hidden inputs in the
        // meantime — sees the real audience_mode/contact_ids instead of
        // the "all contacts" default the form still had a moment earlier.
        if (draft.audience_mode === "tag" && draft.audience_tags && draft.audience_tags.length) {
            setAudienceMode("tag");
            draft.audience_tags.forEach(addTag);
        } else if (draft.audience_mode === "manual" && draft.audience_contact_ids && draft.audience_contact_ids.length) {
            setAudienceMode("manual");
            fetch(`${cfg.searchContactsUrl}?ids=${draft.audience_contact_ids.join(",")}`)
                .then(r => r.json())
                .then(data => {
                    (data.contacts || []).forEach(c => { state.selectedContacts[c.id] = c; });
                    syncSelectedContacts();
                })
                .catch(err => console.error("Error restoring selected contacts:", err));
        }

        if (draft.message_type === "text") {
            messageText.value = draft.message_text || "";
            messageTextCount.textContent = `${messageText.value.length}/1024`;
        } else if (draft.message_type === "image" || draft.message_type === "document") {
            const captionEl = document.querySelector(`[data-media-caption="${draft.message_type}"]`);
            if (captionEl) captionEl.value = draft.media_caption || "";
            if (draft.media_id) {
                document.getElementById("mediaIdInput").value = draft.media_id;
                document.getElementById("mediaFilenameInput").value = draft.media_filename || "";
                const kind = draft.message_type;
                const label = document.getElementById(`media${kind[0].toUpperCase()}${kind.slice(1)}Label`);
                label.querySelector("[data-media-filename]").textContent = draft.media_filename || "Previously uploaded file";
            }
        } else if (draft.message_type === "template" && draft.template_name) {
            templateSelect.value = draft.template_name;
            state.pendingRestoreFinalData = draft.final_data || {};
            refreshFromServer();
        }

        if (draft.add_unsubscribe_button) {
            document.getElementById("unsubscribeToggle").checked = true;
            document.getElementById("unsubscribeInput").value = "1";
        }
        if (draft.track_status) {
            document.getElementById("trackStatusToggle").checked = true;
            document.getElementById("trackStatusInput").value = "1";
        }

        if (draft.is_scheduled && draft.scheduled_time) {
            document.querySelector('.msg-type-tab[data-schedule="later"]').click();
            document.getElementById("scheduledTimeInput").value = draft.scheduled_time;
        }

        updatePreview();
    }

    // ------------------------------------------------------------------
    // Init
    // ------------------------------------------------------------------
    setAudienceStats(state.totalContacts, state.totalContacts, 0);
    updatePreview();
    if (cfg.draft) loadDraft(cfg.draft);
    // Retargeting a previous campaign's recipients (see campaign_retarget)
    // reuses loadDraft() to prefill the audience/template — this just
    // additionally tags the eventual submit with where it came from, so
    // the new campaign records "Retry of: <original>".
    if (cfg.retargetedFromId) {
        document.getElementById("retargetedFromInput").value = cfg.retargetedFromId;
    }
})();
