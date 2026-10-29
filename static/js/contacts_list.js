
const contactFileInput = document.getElementById("contactFileInput");
const contactFileName = document.getElementById("contactFileName");
if (contactFileInput && contactFileName) {
    contactFileInput.addEventListener("change", function () {
        contactFileName.textContent = this.files.length ? this.files[0].name : "No file chosen";
    });
}

// Draw attention to the "Choose File" button when jumping here from "Import Contacts"
const importContactsLink = document.getElementById("importContactsLink");
const chooseFileLabel = document.getElementById("chooseFileLabel");
if (importContactsLink && chooseFileLabel) {
    importContactsLink.addEventListener("click", function () {
        chooseFileLabel.classList.remove("au-highlight");
        // Restart the animation even if it's already playing
        void chooseFileLabel.offsetWidth;
        chooseFileLabel.classList.add("au-highlight");
        setTimeout(() => chooseFileLabel.classList.remove("au-highlight"), 2800);
    });
}

// Show real upload progress instead of a frozen page while the file uploads,
// then reload once the server has finished processing it.
const contactUploadForm = document.getElementById("contactUploadForm");
if (contactUploadForm) {
    contactUploadForm.addEventListener("submit", function (e) {
        e.preventDefault();

        if (!contactFileInput.files.length) {
            contactFileInput.reportValidity();
            return;
        }

        // Build the FormData BEFORE disabling any fields — disabled form
        // controls are silently excluded from FormData, which was dropping
        // the file entirely and made the server treat this as an (invalid)
        // manual entry, bouncing us to the "Add Contact" page.
        const formData = new FormData(contactUploadForm);

        const statusBox = document.getElementById("uploadStatus");
        const fill = document.getElementById("uploadFill");
        const statusText = document.getElementById("uploadStatusText");
        const submitBtn = contactUploadForm.querySelector('button[type="submit"]');

        statusBox.hidden = false;
        fill.classList.remove("au-upload-status__fill--error");
        statusText.textContent = "Uploading… 0%";
        submitBtn.disabled = true;
        contactFileInput.disabled = true;

        let shownPercent = 0;
        let processingTimer = null;

        function setProgress(percent, label) {
            shownPercent = percent;
            fill.style.width = percent + "%";
            statusText.textContent = `${label} ${Math.round(percent)}%`;
        }

        // The network transfer usually finishes in well under a second on a
        // local/fast connection, but the server then still has to parse the
        // file and save every row — with no way to know how far along that
        // is. Once the upload itself hits 100%, keep the number creeping
        // upward (fast at first, slowing as it nears 99%) so the bar reads
        // as one continuous 0→100% climb instead of jumping to a stalled
        // "processing" state.
        function startProcessingCrawl() {
            processingTimer = setInterval(() => {
                if (shownPercent < 99) {
                    setProgress(Math.min(99, shownPercent + (99 - shownPercent) * 0.08), "Processing your file…");
                }
            }, 150);
        }

        const xhr = new XMLHttpRequest();
        xhr.open("POST", contactUploadForm.action, true);

        xhr.upload.addEventListener("progress", function (evt) {
            if (!evt.lengthComputable) return;
            const percent = (evt.loaded / evt.total) * 100;
            if (percent < 100) {
                setProgress(percent, "Uploading…");
            } else {
                setProgress(90, "Processing your file…");
                startProcessingCrawl();
            }
        });

        xhr.addEventListener("load", function () {
            clearInterval(processingTimer);

            // A non-redirect 200 here means the server rejected the request
            // (e.g. missing columns) and rendered a page back at us directly
            // instead of redirecting — reload the contacts list either way
            // so the user always ends up back on this page with fresh data
            // (any Django "messages" will show there).
            setProgress(100, "Done!");
            statusText.textContent = "Done! Refreshing…";
            setTimeout(() => {
                window.location.href = "/services/contacts_list/";
            }, 400);
        });

        xhr.addEventListener("error", function () {
            clearInterval(processingTimer);
            fill.classList.add("au-upload-status__fill--error");
            statusText.textContent = "Upload failed. Please try again.";
            submitBtn.disabled = false;
            contactFileInput.disabled = false;
        });

        xhr.send(formData);
    });
}

document.getElementById("age_filter").addEventListener("change", function () {
    let secondInput = document.getElementById("age_value_2_container");
    secondInput.style.display = this.value === "between" ? "block" : "none";
});

const selectAll = document.getElementById("select-all");
const checkboxes = document.querySelectorAll(".contact-checkbox");
const deleteBtn = document.getElementById("delete-btn");

selectAll.addEventListener("change", function () {
    checkboxes.forEach(checkbox => checkbox.checked = selectAll.checked);
    deleteBtn.disabled = !selectAll.checked;
});

checkboxes.forEach(checkbox => {
    checkbox.addEventListener("change", function () {
        deleteBtn.disabled = !Array.from(checkboxes).some(c => c.checked);
    });
});

let allTagsList = [];
try {
    const allTagsData = document.getElementById("allTagsData");
    if (allTagsData) allTagsList = JSON.parse(allTagsData.textContent);
} catch (err) {
    console.error("Could not parse tags data:", err);
}

function enterEditMode(row, editBtn) {
    // Snapshot the current cells so Cancel can restore them exactly.
    const originalCells = [];
    row.querySelectorAll(".editable, .editable-tags").forEach(cell => {
        originalCells.push({ cell, html: cell.innerHTML });
    });
    row._originalCells = originalCells;

    row.querySelectorAll(".editable").forEach(cell => {
        const input = document.createElement("input");
        input.type = "text";
        const displayText = cell.innerText.trim();
        // "-" is just the placeholder shown for a blank age/email; don't
        // carry it into the editable input as if it were real data.
        input.value = (["age", "email"].includes(cell.dataset.field) && displayText === "-") ? "" : displayText;
        input.dataset.field = cell.dataset.field;
        cell.innerHTML = "";
        cell.appendChild(input);
    });

    const tagsCell = row.querySelector(".editable-tags");
    if (tagsCell) {
        const selectedIds = (tagsCell.dataset.tagIds || "")
            .split(",")
            .filter(Boolean)
            .map(id => parseInt(id, 10));

        const select = document.createElement("select");
        select.className = "form-select form-select-sm tags-select";
        select.multiple = true;

        if (allTagsList.length === 0) {
            const opt = document.createElement("option");
            opt.disabled = true;
            opt.textContent = "No tags available";
            select.appendChild(opt);
        } else {
            allTagsList.forEach(tag => {
                const opt = document.createElement("option");
                opt.value = tag.id;
                opt.textContent = tag.name;
                opt.selected = selectedIds.includes(tag.id);
                select.appendChild(opt);
            });
        }

        tagsCell.innerHTML = "";
        tagsCell.appendChild(select);
    }

    editBtn.innerText = "Save";
    editBtn.classList.add("is-editing");

    if (!row.querySelector(".cancel-btn")) {
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "btn-au-outline btn-sm cancel-btn ms-1";
        cancelBtn.textContent = "Cancel";
        cancelBtn.addEventListener("click", function () {
            exitEditMode(row, editBtn);
        });
        editBtn.insertAdjacentElement("afterend", cancelBtn);
    }
}

function exitEditMode(row, editBtn) {
    (row._originalCells || []).forEach(({ cell, html }) => {
        cell.innerHTML = html;
    });
    row._originalCells = null;

    editBtn.innerText = "Edit";
    editBtn.classList.remove("is-editing");

    const cancelBtn = row.querySelector(".cancel-btn");
    if (cancelBtn) cancelBtn.remove();
}

document.querySelectorAll(".edit-btn").forEach(button => {
    button.addEventListener("click", function () {
        const row = document.getElementById(`row-${this.dataset.id}`);
        const isEditing = this.innerText === "Save";

        if (isEditing) {
            const updatedData = {};
            row.querySelectorAll(".editable input").forEach(input => {
                updatedData[input.dataset.field] = input.value;
            });

            const tagsSelect = row.querySelector(".tags-select");
            if (tagsSelect) {
                updatedData.tags = Array.from(tagsSelect.selectedOptions).map(opt => parseInt(opt.value, 10));
            }

            const saveBtn = this;
            window.AppLoading.start(saveBtn, "Saving…");

            fetch(`/services/update_contact/${this.dataset.id}/`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": "{{ csrf_token }}"
                },
                body: JSON.stringify(updatedData)
            }).then(response => {
                if (response.ok) {
                    location.reload();
                } else {
                    window.AppLoading.stop(saveBtn);
                    response.json().then(data => {
                        alert("Could not save contact: " + (data.error || "Unknown error"));
                    }).catch(() => {
                        alert("Could not save contact (unexpected server error).");
                    });
                }
            }).catch(err => {
                window.AppLoading.stop(saveBtn);
                alert("Could not save contact: " + err);
            });
        } else {
            enterEditMode(row, this);
        }
    });
});

document.addEventListener("DOMContentLoaded", function () {
    const optOutToggle = document.getElementById("opt-out-toggle");
    const statusText = document.getElementById("opt-out-status");

    optOutToggle.addEventListener("change", function () {
        fetch(`/services/toggle_opt_out/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": "{{ csrf_token }}"
            },
            body: JSON.stringify({ enabled: this.checked })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log("data->", data)
                statusText.textContent = data.enabled ? "ON" : "OFF";
            }
        })
        .catch(error => console.error("Error:", error));
    });
}); 

document.addEventListener("DOMContentLoaded", function () {

        $('#contact_list').DataTable({
          paging: true,
          lengthMenu: [10, 25, 50, 100],
          order: [[1, 'asc']],  // Default sort by "Name"
          columnDefs: [
            { orderable: false, targets: [0, 6] } // Disable sorting on checkbox + Actions
          ],
          language: {
            emptyTable: "No contacts found"
          }
        });
});
