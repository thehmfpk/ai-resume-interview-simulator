(function () {
  const input = document.getElementById("resumeInput");
  const dropzone = document.getElementById("dropzone");
  const filenameEl = document.getElementById("dzFilename");
  const form = document.getElementById("uploadForm");
  const startBtn = document.getElementById("startBtn");

  if (!dropzone) return;

  function showFilename(file) {
    if (file) filenameEl.textContent = "✓ " + file.name;
  }

  input.addEventListener("change", () => {
    if (input.files && input.files[0]) showFilename(input.files[0]);
  });

  ["dragenter", "dragover"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) {
      input.files = e.dataTransfer.files;
      showFilename(file);
    }
  });

  // Choice pills (radio groups styled as pills)
  document.querySelectorAll(".choice-row").forEach((row) => {
    row.querySelectorAll(".choice-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        row.querySelectorAll(".choice-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        pill.querySelector("input").checked = true;
      });
    });
  });

  form.addEventListener("submit", () => {
    if (!input.files.length) return;
    startBtn.disabled = true;
    startBtn.textContent = "Analyzing your resume…";
  });
})();
