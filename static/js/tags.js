document.addEventListener("DOMContentLoaded", function () {
    const tagForm = document.getElementById("tagForm");    // Form to add tags
    const tagInput = document.getElementById("tagInput");  // Input for tag name
    if (!tagForm || !tagInput) return;

    // ✅ Handle New Tag Creation
    tagForm.addEventListener("submit", function (e) {
        e.preventDefault();
        const tagName = tagInput.value.trim();
        if (!tagName) return;  // Ignore empty input

        const submitBtn = tagForm.querySelector('button[type="submit"]');
        window.AppLoading.start(submitBtn, "Adding…");

        fetch("/services/tags/create/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: new URLSearchParams({ name: tagName }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.id) {
                location.reload(); // Refresh so the new tag shows up in the table
            } else {
                window.AppLoading.stop(submitBtn);
                alert("Error creating tag: " + data.error);
            }
        })
        .catch(error => {
            window.AppLoading.stop(submitBtn);
            console.error("Error:", error);
        });
    });

    // ✅ CSRF Token Helper (Required for POST requests in Django)
    function getCSRFToken() {
        return document.querySelector("[name=csrfmiddlewaretoken]").value;
    }

    // ✅ Edit / Save a custom tag's name inline
    document.querySelectorAll(".tag-edit-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            const row = this.closest("tr");
            const nameCell = row.querySelector(".tag-name-text");
            const isSaving = this.dataset.mode === "save";

            if (isSaving) {
                const input = row.querySelector(".tag-name-input");
                const newName = input.value.trim();
                if (!newName) return;

                const saveBtn = this;
                window.AppLoading.start(saveBtn, "Saving…");

                fetch(`/services/tags/${this.dataset.id}/update/`, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCSRFToken(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    body: new URLSearchParams({ name: newName }),
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.id) {
                            location.reload();
                        } else {
                            window.AppLoading.stop(saveBtn);
                            alert("Error updating tag: " + data.error);
                        }
                    })
                    .catch(error => {
                        window.AppLoading.stop(saveBtn);
                        console.error("Error:", error);
                    });
            } else {
                const currentName = nameCell.textContent.trim();
                nameCell.dataset.originalHtml = nameCell.innerHTML;
                nameCell.innerHTML = `<input type="text" class="form-control form-control-sm tag-name-input" value="${currentName}" style="display:inline-block; width:auto;">`;
                this.textContent = "Save";
                this.dataset.mode = "save";

                if (!row.querySelector(".tag-cancel-btn")) {
                    const editBtn = this;
                    const cancelBtn = document.createElement("button");
                    cancelBtn.type = "button";
                    cancelBtn.className = "btn-au-outline btn-sm tag-cancel-btn ms-1";
                    cancelBtn.textContent = "Cancel";
                    cancelBtn.addEventListener("click", function () {
                        nameCell.innerHTML = nameCell.dataset.originalHtml;
                        delete nameCell.dataset.originalHtml;
                        editBtn.textContent = "Edit";
                        editBtn.dataset.mode = "edit";
                        cancelBtn.remove();
                    });
                    editBtn.insertAdjacentElement("afterend", cancelBtn);
                }
            }
        });
    });

    // ✅ Delete a custom tag
    document.querySelectorAll(".tag-delete-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            if (!confirm("Delete this tag? This cannot be undone.")) return;

            const deleteBtn = this;
            window.AppLoading.start(deleteBtn, "Deleting…");

            fetch(`/services/tags/${this.dataset.id}/delete/`, {
                method: "POST",
                headers: { "X-CSRFToken": getCSRFToken() },
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        window.AppLoading.stop(deleteBtn);
                        alert("Error deleting tag: " + data.error);
                    }
                })
                .catch(error => {
                    window.AppLoading.stop(deleteBtn);
                    console.error("Error:", error);
                });
        });
    });
});
