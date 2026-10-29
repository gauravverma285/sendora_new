const headerSelect = document.getElementById('headerSelect');
const headerInputContainer = document.getElementById('headerInputContainer');
const bodyTextarea = document.getElementById('exampleFormControlTextarea1');
const bodyVariableContainer = document.getElementById('bodyVariableContainer');
const sections = document.getElementById('sections');
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
  section.className = 'option-section border p-3 rounded mb-3';
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
        <input type="text" name="button_text[]" class="form-control" value="Visit website">
      </div>
      <div class="mb-3">
        <label class="form-label">Website URL</label>
        <input type="url" id="urlTextInput" name="button_url[]" class="form-control" placeholder="https://example.com">
        <div id="urlVariableInputs"></div>
      </div>`;
  } else if (option === 'call') {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="PHONE_NUMBER">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" value="Call phone number">
      </div>
      <div class="mb-3">
        <label class="form-label">Phone Number</label>
        <input type="tel" name="button_phone_number[]" class="form-control" placeholder="+1234567890">
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
        <input type="text" name="button_example[]" class="form-control" placeholder="PROMO123">
      </div>`;
  } else {
    content += `
      <div class="mb-3">
      <input type="hidden" name="button_type[]" value="QUICK_REPLY">
        <label class="form-label">Button Text</label>
        <input type="text" name="button_text[]" class="form-control" placeholder="Enter button text">
      </div>`;
  }

  content += `<button class="btn btn-danger btn-sm mt-2 remove-section">Cancel</button>`;
  section.innerHTML = content;

  return section;
}

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
  } else if (option === 'image') {
    headerInputContainer.innerHTML = `
      <div class="mb-3">
        <h6>Samples for header content</h6>
            <p>To help us review your content, provide examples of the variables or media in the header. Do not include any customer information. Cloud API hosted by Meta reviews templates and variable parameters to protect the security and integrity of our services.</p>
            <label for="headerImageInput" class="form-label">Choose an Image</label>
            <input type="file" class="form-control" name="sample_values_headers" id="headerImageInput" accept=".png, .jpg, .jpeg">
      </div>`;
  } else if (option === 'video') {
    headerInputContainer.innerHTML = `
      <div class="mb-3">
      <h6>Samples for header content</h6>
              <p>To help us review your content, provide examples of the variables or media in the header. Do not include any customer information. Cloud API hosted by Meta reviews templates and variable parameters to protect the security and integrity of our services.</p>
            <label for="headerVideoInput" class="form-label">Choose a Video</label>
            <input type="file" class="form-control" name="sample_values_headers" id="headerVideoInput" accept="video/*">
      </div>`;
      
  } else if (option === 'document') {
    headerInputContainer.innerHTML = `
        <div class="mb-3">
         <h6>Samples for header content</h6>
              <p>To help us review your content, provide examples of the variables or media in the header. Do not include any customer information. Cloud API hosted by Meta reviews templates and variable parameters to protect the security and integrity of our services.</p>
            <label for="headerDocInput" class="form-label">Choose a Document</label>
            <input type="file" class="form-control" name="sample_values_headers" id="headerDocInput" accept=".pdf, .doc, .docx">
        </div>`;
  }
  
});

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
          inputDiv.innerHTML = `<label>{{${value}}} - Enter content for {{${value}}}: </label>
                                <input type="text" id="input_${value}" class="form-control" name="sample_values_body" placeholder="Enter content for {{${value}}}">`;
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

      // Find matches and create input fields
      const matches = new Set([...headerTextInput.value.matchAll(regex)].map(m => m[1]));
      headerVariableInputs.innerHTML = ""; // Clear previous inputs

      matches.forEach(value => {
          const inputDiv = document.createElement("div");
          inputDiv.innerHTML = `<label>{{${value}}} - Enter content for {{${value}}}: </label>
                                <input type="text" id="input_header_${value}" class="form-control" name="sample_values_headers" placeholder="Enter content for {{${value}}}">`;
          headerVariableInputs.appendChild(inputDiv);
      });
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
  function updateUrlVariables() {
      const urlTextInput = document.getElementById("urlTextInput");
      const urlVariableInputs = document.getElementById("urlVariableInputs");

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

      // Find matches and create input fields
      const matches = new Set([...urlTextInput.value.matchAll(regex)].map(m => m[1]));
      urlVariableInputs.innerHTML = ""; // Clear previous inputs

      matches.forEach(value => {
          const inputDiv = document.createElement("div");
          inputDiv.innerHTML = `<label>((${value})) - Enter content for ((${value})): </label>
                                <input type="text" id="input_url_${value}" name="button_example_${value}[]" class="form-control" name="sample_values_url" placeholder="Enter content for ((${value}))">`;
          urlVariableInputs.appendChild(inputDiv);
      });
  }

  // Listen for input changes in the URL text field
  document.addEventListener("input", function (event) {
      if (event.target.id === "urlTextInput") {
          updateUrlVariables();
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
  }
});

// Initial dropdown update
updateDropdown();
