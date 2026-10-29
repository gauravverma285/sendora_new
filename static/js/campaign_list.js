// Navigate to analytics page when row clicked — every non-draft campaign
// (template, text, image, document) gets its own Campaign Insights page;
// it's built from our own per-message tracking, not Meta's template-only
// analytics endpoint, so it doesn't need a template_id.
document.querySelectorAll('.campaign-row').forEach(row => {
    row.addEventListener('click', function () {
        const campaignName = encodeURIComponent(this.dataset.campaignName);
        window.location.href = `/services/campaign_analytics/?campaign_name=${campaignName}`;
    });
});

// Reopen a draft for editing when its row is clicked
document.querySelectorAll('.draft-row').forEach(row => {
    row.addEventListener('click', function () {
        window.location.href = this.dataset.draftUrl;
    });
});

// Prevent row click when button is clicked
document.querySelectorAll('.stop-campaign, .start-campaign').forEach(button => {
    button.addEventListener('click', function (event) {
        event.stopPropagation(); // ⛔ Prevent row click

        const campaignName = this.dataset.campaign;
        const isStart = this.classList.contains("start-campaign");
        const url = isStart ? "/services/start_campaign/" : "/services/stop_campaign/";

        const csrfToken = window.CAMPAIGN_CONFIG.csrfToken
        const btn = this;
        window.AppLoading.start(btn, isStart ? "Starting…" : "Stopping…");

        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken":  csrfToken
            },
            body: JSON.stringify({ campaign_name: campaignName })
        }).then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    window.AppLoading.stop(btn);
                    alert(`Failed to ${isStart ? "start" : "stop"} campaign.`);
                }
            })
            .catch(err => {
                window.AppLoading.stop(btn);
                console.error("Error:", err);
                alert(`Failed to ${isStart ? "start" : "stop"} campaign.`);
            });
    });
});
