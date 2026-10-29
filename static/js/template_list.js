function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

function deleteTemplate(templateName, iconEl) {
    if (!confirm(`Are you sure you want to delete the template: ${templateName}?`)) {
        return;
    }

    // deleteTemplate is triggered from an <img> icon, not a <button>, so it
    // can't show a spinner the same way — just dim it and block re-clicks
    // for the moment it takes to get a response.
    if (iconEl) {
        iconEl.style.opacity = "0.4";
        iconEl.style.pointerEvents = "none";
    }

    fetch(`/services/delete_template/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()  // Ensure CSRF token for Django
        },
        body: JSON.stringify({ name: templateName })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.reload(); // Refresh the page on success
            } else {
                if (iconEl) { iconEl.style.opacity = ""; iconEl.style.pointerEvents = ""; }
                alert(data.message);
            }
        })
        .catch(error => {
            if (iconEl) { iconEl.style.opacity = ""; iconEl.style.pointerEvents = ""; }
            console.error("Error deleting template:", error);
            alert("Error deleting template. Check the console for details.");
        });
}

document.addEventListener("DOMContentLoaded", function () {

    $('#template_list').DataTable({
        paging: true,
        lengthMenu: [10, 25, 50, 100],
        order: [[0, 'asc']],  // Default sort by "Template Name"
        columnDefs: [
            { orderable: false, targets: [5] } // Disable sorting on Actions
        ],
        language: {
            emptyTable: "No templates found"
        }
    });
});
