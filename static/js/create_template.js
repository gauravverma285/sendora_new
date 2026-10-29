const headerSelect = document.getElementById('headerSelect');
const headerInputContainer = document.getElementById('headerInputContainer');
const bodyTextarea = document.getElementById('exampleFormControlTextarea1');
const bodyVariableContainer = document.getElementById('bodyVariableContainer');
const sections = document.getElementById('sections');
const aboveSections = document.getElementById('aboveSections');
const dropdownItems = document.querySelectorAll('.dropdown-item');

let totalButtons = 0; // Track total buttons

const limits = {
  marketing: 1,
  custom: Infinity,
  visit: 2,
  call: 1,
  copy: 1,
};

const counts = {
  marketing: 0,
  custom: 0,
  visit: 0,
  call: 0,
  copy: 0,
};

// Update dropdown items based on limits
function updateDropdown() {
  dropdownItems.forEach((item) => {
    const option = item.getAttribute('data-option');
    const remaining = limits[option] - counts[option];
    const maxLimitSpan = item.querySelector('.max-limit');

    if (remaining <= 0 || totalButtons >= 10) {
      item.classList.add('disabled');
      item.style.pointerEvents = 'none';
    } else {
      item.classList.remove('disabled');
      item.style.pointerEvents = '';
    }

    if (maxLimitSpan) {
      maxLimitSpan.textContent = limits[option] === Infinity
        ? ''
        : `(${remaining} remaining)`;
    }
  });
}

// Create a section for buttons
function createSection(option) {
  if (totalButtons >= 10) return; // Prevent adding more than 10 buttons

  const section = document.createElement('div');
  section.className = 'option-section p-3 rounded mb-3';
  section.setAttribute('data-option', option);

  let content = `<h5>${option.charAt(0).toUpperCase() + option.slice(1)}</h5>`;

  if (option === 'marketing') {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="QUICK_REPLY">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" value="Stop promotions" readonly>
      </div>
      <div class="mb-3">
        <label class="form-label">Footer Text</label>
        <input type="text" class="form-control" value="Not interested? Tap Stop promotions" readonly>
      </div>`;
  } else if (option === 'visit') {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="URL">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" value="Visit website" required>
      </div>
      <div class="mb-3">
        <label class="form-label">Website URL</label>
        <input type="url" id="urlTextInput" name="button_url[]" class="form-control" placeholder="https://example.com" required>
        <div id="urlVariableInputs"></div>
      </div>`;
  } else if (option === 'call') {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="PHONE_NUMBER">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" value="Call phone number" required>
      </div>
      <div class="mb-3">
        <label class="form-label">Phone Number</label>
        <input type="tel" name="button_phone_number[]" class="form-control" placeholder="+1234567890" required>
      </div>`;
  } else if (option === 'copy') {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="COPY_CODE">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" value="Copy offer code" readonly>
      </div>
      <div class="mb-3">
        <label class="form-label">Offer Code</label>
        <input type="text" name="button_copy_example" class="form-control" placeholder="PROMO123" required>
      </div>`;
  } else {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="QUICK_REPLY">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" placeholder="Enter button text" required>
      </div>`;
  }

  content += `<button class="btn btn-danger btn-sm mt-2 remove-section">Cancel</button>`;
  section.innerHTML = content;

  return section;
}



// Handle header selection
// Handle header selection
headerSelect.addEventListener('change', (e) => {
  headerInputContainer.innerHTML = '';
  const option = e.target.value;

  if (option === 'text') {
      headerInputContainer.innerHTML = `
          <div class="mb-3">
              <label for="headerTextInput" class="form-label">Header Text</label>
              <input type="text" name="header_text" class="form-control" id="headerTextInput" placeholder="Enter header text" required>
              <div id="headerVariableInputs"></div>
          </div>`;
  }

  if (["image", "video", "document"].includes(option)) {
      let acceptTypes = option === "image" ? ".png, .jpg, .jpeg"
                      : option === "video" ? "video/*"
                      : ".pdf, .doc, .docx";
      let label = option.charAt(0).toUpperCase() + option.slice(1);

      headerInputContainer.innerHTML = `
          <div class="mb-3">
              <h6>Samples for header content</h6>
              <p>To help us review your content, provide examples of the variables or media in the header. Do not include any customer information.</p>
              <label for="headerFileInput" class="form-label">Choose a ${label}</label>
              <input type="file" class="form-control" id="headerFileInput" accept="${acceptTypes}" required>
              <button type="button" id="uploadMediaBtn" class="btn btn-primary mt-2">Upload ${label}</button>
              <input type="hidden" name="sample_values_headers" id="sampleValuesHeaders">
              <p id="uploadStatus" class="mt-2 text-success"></p>
          </div>`;

      // Attach event listener to the dynamically created upload button
      document.getElementById("uploadMediaBtn").addEventListener("click", uploadMedia);
  }
});

// Function to upload media and get "h" value
function uploadMedia() {
  const fileInput = document.getElementById("headerFileInput");
  const uploadStatus = document.getElementById("uploadStatus");

  if (!fileInput.files.length) {
      uploadStatus.textContent = "Please select a file to upload.";
      uploadStatus.classList.add("text-danger");
      return;
  }

  let formData = new FormData();
  formData.append("file", fileInput.files[0]);
  
  fetch("/services/upload-media/?button=upload", {
      method: "POST",
      body: formData,
      headers: {
          "X-CSRFToken": getCsrfToken()  // Ensure CSRF token is included
      }
  })
  .then(response => response.json())
  .then(data => {
      if (data.h) {
          document.getElementById("sampleValuesHeaders").value = data.h; // Store "h" value in hidden input
          uploadStatus.textContent = "Upload successful!";
          uploadStatus.classList.add("text-success");
      } else {
          uploadStatus.textContent = "Upload failed!";
          uploadStatus.classList.add("text-danger");
      }
  })
  .catch(error => {
      console.error("Upload Error:", error);
      uploadStatus.textContent = "An error occurred while uploading.";
      uploadStatus.classList.add("text-danger");
  });
} 

// Function to get CSRF token from Django (if needed)
function getCsrfToken() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || "";
}


// Handle body variables

document.addEventListener("DOMContentLoaded", function () {
  const textArea = document.getElementById("exampleFormControlTextarea1");
  const selectVariable = document.querySelector(".enterVariable");
  const inputContainer = document.createElement("div");
  textArea.parentNode.appendChild(inputContainer);
  
  function updateInputs() {
      const selectedValue = selectVariable.value;
      let regex;
      
      if (selectedValue === "Name") {
          regex = /\{\{([a-zA-Z_]+)\}\}/g; // Matches {{variable_name}}
      } else {
          regex = /\{\{(\d+)\}\}/g; // Matches both {{number}}
      }
      
      const matches = new Set([...textArea.value.matchAll(regex)].map(m => m[1]));
      inputContainer.innerHTML = ""; // Clear previous inputs
      
      matches.forEach(value => {
          const inputDiv = document.createElement("div");
          inputDiv.innerHTML = `<h6>Samples for body content</h6>
            <p>To help us review your message template, please add an example for each variable in your body text. Do not use real customer information. Cloud API hosted by Meta reviews templates and variable parameters to protect the security and integrity of our services.</p>
    
                                <input type="text" id="input_${value}" class="form-control" name="sample_values_body" placeholder="Enter content for {{${value}}}" required>`;
          inputContainer.appendChild(inputDiv);
      });
  }
  
  textArea.addEventListener("input", updateInputs);
  selectVariable.addEventListener("change", updateInputs);
});

// header text to add sample value

document.addEventListener("DOMContentLoaded", function () {
  // Function to update header variables based on selected variable type
  function updateHeaderVariables() {
      const headerTextInput = document.getElementById("headerTextInput");
      const headerVariableInputs = document.getElementById("headerVariableInputs");

      if (!headerTextInput || !headerVariableInputs) return;

      const selectVariable = document.querySelector(".enterVariable");
      const selectedValue = selectVariable.value;
      let regex;

      // Set regex based on selected variable type
      if (selectedValue === "Name") {
          regex = /\{\{([a-zA-Z_]+)\}\}/g; // Matches {{variable_name}}
      } else {
          regex = /\{\{(\d+)\}\}/g; // Matches {{1}}, {{2}}, etc.
      }

      // Find matches
      const matches = [...headerTextInput.value.matchAll(regex)];

      // Restrict to only one variable
      if (matches.length > 1) {
          // Keep the first match, remove others
          headerTextInput.value = headerTextInput.value.replace(regex, (match, p1, offset, string) => {
              return string.indexOf(match) === string.search(regex) ? match : "";
          });
      }

      // Clear previous inputs
      headerVariableInputs.innerHTML = "";

      if (matches.length > 0) {
          const value = matches[0][1];
          const inputDiv = document.createElement("div");
          inputDiv.innerHTML = `<h6>Samples for header content</h6>
                                <strong><label>Note: Your title can't include more than one variable</label></strong>
                                <p>To help us review your content, provide examples of the variables or media in the header. Do not include any customer information. Cloud API hosted by Meta reviews templates and variable parameters to protect the security and integrity of our services.</p>
                                <input type="text" id="input_header_${value}" class="form-control" name="sample_values_headers" placeholder="Enter content for {{${value}}}" required>`;
          headerVariableInputs.appendChild(inputDiv);
      }
  }

  // Listen for input changes in header text field
  document.addEventListener("input", function (event) {
      if (event.target.id === "headerTextInput") {
          updateHeaderVariables();
      }
  });

  // Listen for changes in the variable type dropdown
  const selectVariable = document.querySelector(".enterVariable");
  selectVariable.addEventListener("change", function () {
      updateHeaderVariables(); // Update header input based on new variable type
  });
});


// Function to update URL variable inputs dynamically
document.addEventListener("DOMContentLoaded", function () {
  function updateUrlVariables(event) {
    const urlTextInput = event.target; // Get the current input field
    const urlVariableInputs = urlTextInput.nextElementSibling; // Find the corresponding variable inputs div


      if (!urlTextInput || !urlVariableInputs) return;

      const selectVariable = document.querySelector(".enterVariable");
      const selectedValue = selectVariable.value;
      let regex;

      // Set regex based on selected variable type
      if (selectedValue === "Name") {
          regex = /\{\{([a-zA-Z_]+)\}\}/g; // Matches {{variable_name}}
      } else {
          regex = /\{\{(\d+)\}\}/g; // Matches {{1}}, {{2}}, etc.
      }

      // Find matches
      const matches = [...urlTextInput.value.matchAll(regex)];

      // Restrict to only one variable
    if (matches.length > 1) {
      urlTextInput.value = urlTextInput.value.replace(regex, (match, p1, offset, string) => {
          return string.indexOf(match) === string.search(regex) ? match : "";
      });
  }
      // Clear previous inputs
      urlVariableInputs.innerHTML = ""; // Clear previous inputs

      if (matches.length > 0) {
        const value = matches[0][1];
        const inputDiv = document.createElement("div");
        inputDiv.innerHTML = `<strong><label>Note: Only one variable can be added to the end of a URL.</label></strong>
                              
                              <input type="text" id="input_url_${value}" name="button_example_${value}[]" class="form-control" placeholder="Enter content for ((${value}))" required>`;
        urlVariableInputs.appendChild(inputDiv);
    }
  }

 // Listen for input changes in all dynamically added URL fields
 document.addEventListener("input", function (event) {
  if (event.target.matches("input[name='button_url[]']")) {
      updateUrlVariables(event);
  }
});
  // Listen for changes in the variable type dropdown
  const selectVariable = document.querySelector(".enterVariable");
  selectVariable.addEventListener("change", function () {
      updateUrlVariables(); // Update header input based on new variable type
  });
});


// Add button click event handler
dropdownItems.forEach(item => {
  item.addEventListener('click', function(e) {
    e.preventDefault();

    const option = e.target.getAttribute('data-option');

    if (totalButtons < 10 && !this.classList.contains('disabled')) {
      sections.appendChild(createSection(option));
      updateAboveSectionsVisibility(); // 👈 Add this
      counts[option]++;
      totalButtons++;
    }

    updateDropdown();
  });
});

// Handle remove section
sections.addEventListener('click', function(e) {
  if (e.target.classList.contains('remove-section')) {
    const section = e.target.closest('.option-section');
    section.remove();
    const option = section.getAttribute('data-option');
    counts[option]--;
    totalButtons--;
    updateDropdown();
    updateAboveSectionsVisibility(); // 👈 Add this here too
  }
});

// Initial dropdown update
updateDropdown();


// back ground of button sections
function updateAboveSectionsVisibility() {
  if (sections.children.length === 0) {
    aboveSections.style.display = "none";
  } else {
    aboveSections.style.display = "block";
  }
}


                  // Below is to view template page 

let template = null; // Declare in outer scope
const footerInput = document.getElementById('exampleFormControlTextarea2');

document.addEventListener("DOMContentLoaded", () => {
  const script = document.getElementById("template-data");
  console.log("script-->", script);
  if (!script) {
    console.error("Script tag with id='template-data' not found.");
    return;
  }

  try {
    template = JSON.parse(script.textContent); // ✅ FIXED HERE
    initTemplate();
  } catch (error) {
    console.error("Failed to parse template JSON:", error, script.textContent);
    return;
  }


  function fillPlaceholders(text, examples) {
  let result = text;
  examples.forEach((example, i) => {
    const placeholder = `{{${i + 1}}}`;
    result = result.replaceAll(placeholder, example);
  });
  return result;
}

// ✅ Add this utility function before your `fillHeader` and `fillButtons` functions
function triggerManuallyInputListeners(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.dispatchEvent(new Event('input', { bubbles: true })); // ensures input event is dispatched globally
}

  if (!template || !template.components) return;
  
  // Load header
       // ✅ Patch fillHeader to use manual triggering properly
function fillHeader(comp) {
  const type = comp.format?.toLowerCase?.() || "none";
  headerSelect.value = type;
  headerSelect.dispatchEvent(new Event("change"));

  waitForElement("headerTextInput", (input) => {
    input.value = comp.text;
    triggerManuallyInputListeners("headerTextInput"); // Trigger input event

    const match = comp.text.match(/\{\{(\d+)\}\}/);
    const exampleVal = comp.example?.header_text?.[0] || "";
    if (match && exampleVal) {
      waitForElement(`input_header_${match[1]}`, (sampleInput) => {
        sampleInput.value = exampleVal;
      });
    }
  });
}


  // Load body
  function fillBody(comp) {
  if (!bodyTextarea) return;

  bodyTextarea.value = comp.text;
  bodyTextarea.dispatchEvent(new Event('input')); // Trigger your listener to generate sample fields

  const sampleValues = comp.example?.body_text?.[0] || [];

  // Wait for dynamic inputs to render
  setTimeout(() => {
    sampleValues.forEach((value, index) => {
      const input = document.getElementById(`input_${index + 1}`);
      if (input) input.value = value;
    });
  }, 100); // Adjust delay if needed
}




  // Load footer
  function fillFooter(comp) {
    if (footerInput) footerInput.value = comp.text;
  }

  // Map button types
  function mapButtonType(button) {
    if (button.type === 'QUICK_REPLY' && button.text === 'Stop promotions') return 'marketing';
    if (button.type === 'QUICK_REPLY') return 'custom';
    if (button.type === 'URL') return 'visit';
    if (button.type === 'PHONE_NUMBER') return 'call';
    if (button.type === 'COPY_CODE') return 'copy';
    return 'custom';
  }

  // Load buttons
  function fillButtons(comp) {
    comp.buttons.forEach(button => {
      const option = mapButtonType(button);
      const section = createSection(option); // Uses your existing logic

      if (option === 'visit') {
          const urlInput = section.querySelector("input[name='button_url[]']");
      urlInput.value = button.url;

      // 👉 Must add section before triggering input so DOM exists
      sections.appendChild(section);
      totalButtons++;
      counts[option]++;

      triggerManuallyInputListeners("urlTextInput");

      const match = button.url.match(/\{\{(\d+)\}\}/);
      const exampleVal = button.example?.[0] || "";
      if (match && exampleVal) {
        waitForElement(`input_url_${match[1]}`, (sampleInput) => {
          sampleInput.value = exampleVal;
        });
      }


      } else if (option === 'call') {
        section.querySelector("input[name='button_text[]']").value = button.text;
        section.querySelector("input[name='button_phone_number[]']").value = button.phone_number;
      } else if (option === 'copy') {
        section.querySelector("input[name='button_copy_example']").value = button.example?.[0] || '';
      } else {
        section.querySelector("input[name='button_text[]']").value = button.text;
      }

      sections.appendChild(section);
      totalButtons++;
      counts[option]++;
    });
  }

  // Wait for dynamic element (e.g., headerTextInput) to appear
  function waitForElement(id, callback) {
    const el = document.getElementById(id);
    if (el) return callback(el);
    setTimeout(() => waitForElement(id, callback), 100);
  }

  // Initialize entire template UI
  function initTemplate() {
    template.components.forEach(comp => {
      if (comp.type === 'HEADER') fillHeader(comp);
      if (comp.type === 'BODY') fillBody(comp);
      if (comp.type === 'FOOTER') fillFooter(comp);
      if (comp.type === 'BUTTONS') fillButtons(comp);
    });

    updateDropdown();
    updateAboveSectionsVisibility();
  }

  // initTemplate(); // finally call the initializer
});
