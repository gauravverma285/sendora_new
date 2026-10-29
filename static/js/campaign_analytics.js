
// status changer
document.querySelectorAll(".status-change").forEach(item => {
    item.addEventListener("click", function (event) {
        event.preventDefault();

        const newStatus = this.dataset.status;
        // console.log("newstatus:", newStatus)
        const campaignName = this.dataset.campaign;
        // console.log("campaignName:", campaignName)
        const apiUrl = newStatus === "Live" ? window.CAMPAIGN_CONFIG.startUrl : window.CAMPAIGN_CONFIG.stopUrl;
        console.log(`Sending request to: ${apiUrl} with campaign: ${campaignName}`);

        const csrfToken = window.CAMPAIGN_CONFIG.csrfToken

        fetch(apiUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({ campaign_name: campaignName })
        }).then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(`Campaign ${newStatus} Successfully!`);
                    document.querySelector(`.status-toggle[data-campaign="${campaignName}"]`).textContent = newStatus;
                    document.querySelector(`.status-toggle[data-campaign="${campaignName}"]`).setAttribute("data-status", newStatus);
                } else {
                    alert(`Failed to ${newStatus.toLowerCase()} campaign.`);
                }
            });
    });
});

// Campaign Insights: date-range filter (reloads the page with new range
// params — everything, KPI cards + chart + export link, is computed
// server-side from those params).
document.addEventListener("DOMContentLoaded", function () {
    const rangeSelect = document.getElementById("insightsRange");
    const customInputs = document.getElementById("customRangeInputs");
    const customStart = document.getElementById("customStart");
    const customEnd = document.getElementById("customEnd");
    const applyCustomRange = document.getElementById("applyCustomRange");
    if (!rangeSelect) return; // error state — nothing to wire up

    function goToRange(params) {
        const url = new URL(window.CAMPAIGN_CONFIG.analyticsUrl, window.location.origin);
        url.searchParams.set("campaign_name", window.CAMPAIGN_CONFIG.campaignName);
        Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
        window.location.href = url.toString();
    }

    rangeSelect.addEventListener("change", function () {
        if (this.value === "custom") {
            customInputs.classList.remove("d-none");
            return;
        }
        goToRange({ range: this.value });
    });

    if (applyCustomRange) {
        applyCustomRange.addEventListener("click", function () {
            if (!customStart.value || !customEnd.value) {
                alert("Please choose both a start and end date.");
                return;
            }
            goToRange({ range: "custom", start_date: customStart.value, end_date: customEnd.value });
        });
    }
});

// graph shower
document.addEventListener("DOMContentLoaded", function () {
    let graphData;
    try {
        graphData = JSON.parse(window.CAMPAIGN_CONFIG.graphData);
    } catch (e) {
        return; // error state — nothing to chart
    }
    console.log("graphData-->", graphData)

    // The combined trend chart stays to the 4 headline metrics (matches the
    // reference design); Clicked/Replied still get their own KPI card with
    // its own sparkline below, just not plotted together with the others.
    const chartMetrics = [
        { key: "sent", label: "Sent", color: "#3b7dfb" },
        { key: "delivered", label: "Delivered", color: "#2ecc71" },
        { key: "read", label: "Read", color: "#9b6bf0" },
        { key: "failed", label: "Failed", color: "#ff5a5f" },
    ];

    // Every KPI card's sparkline, including the two not on the main chart.
    const sparkMetrics = chartMetrics.concat([
        { key: "clicked", label: "Clicked", color: "#17a2a4" },
        { key: "replied", label: "Replied", color: "#f39c12" },
    ]);

    const ctx = document.getElementById("campaignPerformanceChart");
    if (ctx) {
        new Chart(ctx.getContext("2d"), {
            type: "line",
            data: {
                labels: graphData.dates,
                datasets: chartMetrics.map(m => ({
                    label: m.label,
                    data: graphData[m.key],
                    borderColor: m.color,
                    backgroundColor: m.color + "22",
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                    fill: true,
                }))
            },
            options: {
                // Sized by the .chart-container wrapper (fixed height, full
                // width) instead of an aspect ratio — stays readable at
                // phone width instead of getting squashed.
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                scales: {
                    x: { ticks: { autoSkip: true, maxRotation: 45, minRotation: 0 } },
                    y: { beginAtZero: true, ticks: { precision: 0 } },
                },
                plugins: {
                    legend: {
                        display: true,
                        position: "top",
                        align: "end",
                        labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 8, padding: 16 },
                    },
                }
            }
        });
    }

    // Mini sparkline per KPI card — same per-day series as the main chart,
    // just rendered with no axes/legend/tooltip.
    sparkMetrics.forEach(m => {
        const canvas = document.getElementById(`spark-${m.key}`);
        if (!canvas) return;
        new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: graphData.dates,
                datasets: [{
                    data: graphData[m.key],
                    borderColor: m.color,
                    backgroundColor: m.color + "22",
                    tension: 0.35,
                    pointRadius: 0,
                    borderWidth: 2,
                    fill: true,
                }]
            },
            options: {
                responsive: false,
                maintainAspectRatio: false,
                elements: { line: { borderJoinStyle: "round" } },
                scales: { x: { display: false }, y: { display: false } },
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
            }
        });
    });
});

// Campaign Recipients: per-status table + selection + Retarget.
document.addEventListener("DOMContentLoaded", function () {
    const table = document.getElementById("recipientsTable");
    if (!table) return; // error state — nothing to wire up
    const cfg = window.CAMPAIGN_CONFIG;

    const AVATAR_COLORS = ["#7c8cf8", "#22c1a1", "#f2994a", "#eb5757", "#9b6bf0", "#2f80ed"];
    const TIMESTAMP_HEADERS = { read: "Read At", delivered: "Delivered At", clicked: "Clicked At", replied: "Replied At", failed: "Failed At" };
    const STATUS_CHIP_CLASS = { read: "status-chip--read", delivered: "status-chip--delivered", clicked: "status-chip--clicked", replied: "status-chip--replied", failed: "status-chip--failed" };

    const state = { status: "read", q: "", page: 1, pageSize: 50, selected: new Set(), rows: [] };

    function initials(name, phone) {
        const src = (name || phone || "?").trim();
        const parts = src.split(/\s+/).filter(Boolean);
        if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
        return src.slice(0, 2).toUpperCase();
    }

    function avatarColor(seed) {
        let hash = 0;
        for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
        return AVATAR_COLORS[hash % AVATAR_COLORS.length];
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str || "";
        return div.innerHTML;
    }

    function updateRetargetButton() {
        document.getElementById("retargetSelectedCount").textContent = state.selected.size;
        document.getElementById("retargetSelectedBtn").classList.toggle("d-none", state.selected.size === 0);
    }

    function renderRows(data) {
        state.rows = data.rows;
        document.getElementById("recipientsTimestampHeader").textContent = TIMESTAMP_HEADERS[state.status] || "Timestamp";

        const tbody = document.getElementById("recipientsTableBody");
        if (!data.rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">No contacts in this segment.</td></tr>';
        } else {
            tbody.innerHTML = data.rows.map(row => {
                const checked = state.selected.has(row.id) ? "checked" : "";
                let retryBadge = "";
                if (row.is_retryable === true) retryBadge = '<span class="retry-badge retry-badge--yes ms-2">Retryable</span>';
                else if (row.is_retryable === false) retryBadge = '<span class="retry-badge retry-badge--no ms-2">Permanent</span>';
                return `
                    <tr>
                        <td><input type="checkbox" class="recipient-row-check" data-id="${row.id}" ${checked}></td>
                        <td>
                            <div class="contact-cell">
                                <span class="contact-avatar" style="background:${avatarColor(row.mobile_number)}">${initials(row.name, row.mobile_number)}</span>
                                <span>${escapeHtml(row.name) || "—"}</span>
                            </div>
                        </td>
                        <td>${escapeHtml(row.mobile_number)}</td>
                        <td class="message-preview-cell" title="${escapeHtml(row.message_preview)}">${escapeHtml(row.message_preview)}</td>
                        <td>${row.timestamp || "—"}</td>
                        <td>
                            <span class="status-chip ${STATUS_CHIP_CLASS[row.status_key] || 'status-chip--queued'}" title="${escapeHtml(row.error_details || row.error_message)}">${escapeHtml(row.status)}</span>${retryBadge}
                        </td>
                        <td class="text-end"><button type="button" class="btn btn-sm btn-outline-secondary view-recipient-btn" data-id="${row.id}">View</button></td>
                    </tr>`;
            }).join("");
        }

        const start = data.total === 0 ? 0 : (data.page - 1) * data.page_size + 1;
        const end = Math.min(data.page * data.page_size, data.total);
        document.getElementById("recipientsPagerInfo").textContent = `${start}–${end} of ${data.total}`;
        document.getElementById("recipientsPrev").disabled = data.page <= 1;
        document.getElementById("recipientsNext").disabled = end >= data.total;
        document.getElementById("recipientsSelectAll").checked =
            data.rows.length > 0 && data.rows.every(r => state.selected.has(r.id));

        updateRetargetButton();

        tbody.querySelectorAll(".recipient-row-check").forEach(cb => {
            cb.addEventListener("change", function () {
                const id = Number(this.dataset.id);
                if (this.checked) state.selected.add(id); else state.selected.delete(id);
                document.getElementById("recipientsSelectAll").checked =
                    state.rows.length > 0 && state.rows.every(r => state.selected.has(r.id));
                updateRetargetButton();
            });
        });
        tbody.querySelectorAll(".view-recipient-btn").forEach(btn => {
            btn.addEventListener("click", function () {
                const row = state.rows.find(r => r.id === Number(this.dataset.id));
                if (row) openContactDrawer(row);
            });
        });
    }

    function loadRecipients() {
        const url = new URL(cfg.recipientsUrl, window.location.origin);
        url.searchParams.set("campaign_name", cfg.campaignName);
        url.searchParams.set("status", state.status);
        if (state.q) url.searchParams.set("q", state.q);
        url.searchParams.set("page", state.page);
        url.searchParams.set("page_size", state.pageSize);
        // Same date range as the KPI cards/chart above (window.CAMPAIGN_CONFIG
        // is set from the page's own ?range=/&start_date=/&end_date= — changing
        // the range dropdown reloads the whole page, so this always matches).
        url.searchParams.set("range", cfg.insightRange);
        if (cfg.insightRange === "custom") {
            url.searchParams.set("start_date", cfg.periodStart);
            url.searchParams.set("end_date", cfg.periodEnd);
        }

        fetch(url)
            .then(r => r.json())
            .then(data => {
                Object.entries(data.counts || {}).forEach(([key, n]) => {
                    const el = document.getElementById(`count-${key}`);
                    if (el) el.textContent = n;
                });
                renderRows(data);
            })
            .catch(err => console.error("Error loading recipients:", err));
    }

    function sendRetarget(messageIds, triggerBtn) {
        if (!messageIds.length) return;
        if (triggerBtn) triggerBtn.disabled = true;
        fetch(cfg.retargetUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
            body: JSON.stringify({ campaign_name: cfg.campaignName, message_ids: messageIds }),
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    window.location.href = data.redirect_url;
                } else {
                    alert(data.message || "Could not start retargeting.");
                    if (triggerBtn) triggerBtn.disabled = false;
                }
            })
            .catch(err => {
                console.error("Retarget error:", err);
                alert("Something went wrong. Please try again.");
                if (triggerBtn) triggerBtn.disabled = false;
            });
    }

    // -- Contact Details drawer --
    function openContactDrawer(row) {
        document.getElementById("contactDrawerName").textContent = row.name || "Unknown";
        document.getElementById("contactDrawerPhone").textContent = row.mobile_number;
        const avatar = document.getElementById("contactDrawerAvatar");
        avatar.textContent = initials(row.name, row.mobile_number);
        avatar.style.background = avatarColor(row.mobile_number);
        document.getElementById("contactDrawerStatus").textContent = row.status;
        document.getElementById("contactDrawerMessage").textContent = row.message_preview || "—";

        const errSection = document.getElementById("contactDrawerErrorSection");
        if (row.status_key === "failed" && (row.error_message || row.error_details)) {
            errSection.style.display = "";
            document.getElementById("contactDrawerError").textContent = row.error_message || "Message failed";
            document.getElementById("contactDrawerErrorDetails").textContent = row.error_details || "";
        } else {
            errSection.style.display = "none";
        }

        document.getElementById("contactDrawerRetargetBtn").dataset.id = row.id;
        document.getElementById("contactDrawer").classList.add("show");
        document.getElementById("contactDrawerBackdrop").classList.add("show");
    }

    function closeContactDrawer() {
        document.getElementById("contactDrawer").classList.remove("show");
        document.getElementById("contactDrawerBackdrop").classList.remove("show");
    }

    document.getElementById("contactDrawerClose").addEventListener("click", closeContactDrawer);
    document.getElementById("contactDrawerBackdrop").addEventListener("click", closeContactDrawer);
    document.getElementById("contactDrawerRetargetBtn").addEventListener("click", function () {
        sendRetarget([Number(this.dataset.id)], this);
    });

    // -- Tabs / search / paging / bulk selection --
    document.querySelectorAll(".recipients-tab").forEach(tab => {
        tab.addEventListener("click", function () {
            document.querySelectorAll(".recipients-tab").forEach(t => t.classList.remove("active"));
            this.classList.add("active");
            state.status = this.dataset.status;
            state.page = 1;
            state.selected.clear();
            loadRecipients();
        });
    });

    let searchDebounce;
    document.getElementById("recipientsSearch").addEventListener("input", function () {
        clearTimeout(searchDebounce);
        const value = this.value;
        searchDebounce = setTimeout(() => {
            state.q = value.trim();
            state.page = 1;
            loadRecipients();
        }, 300);
    });

    document.getElementById("recipientsPageSize").addEventListener("change", function () {
        state.pageSize = Number(this.value);
        state.page = 1;
        loadRecipients();
    });
    document.getElementById("recipientsPrev").addEventListener("click", function () {
        if (state.page > 1) { state.page -= 1; loadRecipients(); }
    });
    document.getElementById("recipientsNext").addEventListener("click", function () {
        state.page += 1;
        loadRecipients();
    });
    document.getElementById("recipientsSelectAll").addEventListener("change", function () {
        if (this.checked) state.rows.forEach(r => state.selected.add(r.id));
        else state.rows.forEach(r => state.selected.delete(r.id));
        tbodyCheckboxSync();
        updateRetargetButton();
    });
    function tbodyCheckboxSync() {
        document.querySelectorAll(".recipient-row-check").forEach(cb => {
            cb.checked = state.selected.has(Number(cb.dataset.id));
        });
    }
    document.getElementById("retargetSelectedBtn").addEventListener("click", function () {
        sendRetarget(Array.from(state.selected), this);
    });

    loadRecipients();
});
