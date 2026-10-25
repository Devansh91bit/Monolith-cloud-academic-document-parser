
document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  let toastTimeout;
  let courseCache = [];

  const showToast = (message) => {
    if (!toast) return;

    toast.textContent = message;
    toast.classList.add("visible");

    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toast.classList.remove("visible");
    }, 4000);
  };

  // Global dashboard search
  const globalSearchInput = document.getElementById("globalSearchInput");
  const searchStatus = document.createElement("p");

  searchStatus.textContent = "No matching results.";
  searchStatus.hidden = true;
  searchStatus.setAttribute("role", "status");

  globalSearchInput?.parentElement?.insertAdjacentElement(
    "afterend",
    searchStatus
  );

  function applyGlobalSearch() {
    if (!globalSearchInput) return;

    const query = globalSearchInput.value.trim().toLowerCase();

    const selectors = [
      "#courseList .course-card",
      "#deadlineList .deadline-card",
      "#docList .document-card",
    ];

    let totalCards = 0;
    let matchingCards = 0;

    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((card) => {
        totalCards++;

        const matches = card.textContent.toLowerCase().includes(query);

        card.style.display = matches ? "" : "none";

        if (matches) matchingCards++;
      });
    });

    searchStatus.hidden =
      !query || totalCards === 0 || matchingCards > 0;
  }

  globalSearchInput?.addEventListener("input", applyGlobalSearch);

  // Logout
  const logoutBtn = document.getElementById("logoutBtn");

  logoutBtn?.addEventListener("click", () => {
    window.location.href = "/auth/logout";
  });

  // Fetch authenticated user information
  fetch("/api/me")
    .then((response) => {
      if (!response.ok) throw new Error("Unauthorized");
      return response.json();
    })
    .then((data) => {
      if (data.authenticated && data.user) {
        const usernameDisplay = document.getElementById("usernameDisplay");
        const userEmailDisplay = document.getElementById("userEmailDisplay");

        if (usernameDisplay) {
          usernameDisplay.textContent =
            data.user.name || data.user.nickname || "User";
        }

        if (userEmailDisplay && data.user.email) {
          userEmailDisplay.textContent = data.user.email;
        }
      }
    })
    .catch((error) => {
      console.warn("User info fetch failed:", error);
    });

  // Course modal controls
  const courseModalOverlay = document.getElementById("courseModalOverlay");

  const openCourseModal = () => {
    courseModalOverlay?.setAttribute("aria-hidden", "false");
  };

  const closeCourseModal = () => {
    courseModalOverlay?.setAttribute("aria-hidden", "true");
  };

  ["openCourseModalBtn", "openCourseHeaderBtn"].forEach((id) => {
    document.getElementById(id)?.addEventListener("click", openCourseModal);
  });

  document.getElementById("cancelCourseBtn")?.addEventListener(
    "click",
    closeCourseModal
  );

  // Create course
  const courseForm = document.getElementById("courseForm");

  courseForm?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const courseData = {
      course_name: document.getElementById("courseName").value.trim(),
      course_code: document.getElementById("courseCode").value.trim(),
      instructor:
        document.getElementById("courseInstructor").value.trim() || null,
    };

    try {
      const response = await fetch("/api/courses", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(courseData),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Failed to save course.");
      }

      courseForm.reset();
      closeCourseModal();
      showToast("Course saved successfully!");

      await loadCourses();
      await loadCourseOptions();
    } catch (error) {
      console.error("Course submission failed:", error);
      showToast(error.message || "Unable to save course.");
    }
  });

  // Load courses
  async function loadCourses() {
    const courseList = document.getElementById("courseList");
    const coursesEmpty = document.getElementById("coursesEmpty");

    if (!courseList || !coursesEmpty) return;

    try {
      const response = await fetch("/api/courses");

      if (!response.ok) {
        throw new Error("Failed to load courses.");
      }

      const data = await response.json();
      courseCache = data.courses;
      courseList.replaceChildren();

      if (data.courses.length === 0) {
        coursesEmpty.classList.remove("hidden");
        applyGlobalSearch();
        return;
      }

      coursesEmpty.classList.add("hidden");

      data.courses.forEach((course) => {
        const card = document.createElement("div");
        card.className = "course-card";

        const title = document.createElement("h3");
        title.textContent = course.course_name;

        const code = document.createElement("p");
        code.textContent = course.course_code;

        card.append(title, code);

        if (course.instructor) {
          const instructor = document.createElement("p");
          instructor.textContent = `Instructor: ${course.instructor}`;
          card.appendChild(instructor);
        }

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "btn-plain";
        deleteBtn.textContent = "Delete Course";
        deleteBtn.addEventListener("click", () => deleteCourse(course.id));
        card.appendChild(deleteBtn);

        const goToCourseBtn = document.createElement("button");
        goToCourseBtn.type = "button";
        goToCourseBtn.className = "btn-primary";
        goToCourseBtn.textContent = "Go to Course →";
        goToCourseBtn.disabled = true;
        card.appendChild(goToCourseBtn);

        courseList.appendChild(card);
      });

      applyGlobalSearch();
    } catch (error) {
      console.error("Course loading failed:", error);
      showToast("Unable to load courses.");
    }
  }

  // Delete course
  async function deleteCourse(courseId) {
    const confirmed = window.confirm(
      "Are you sure you want to delete this course?"
    );

    if (!confirmed) return;

    try {
      const response = await fetch(
        `/api/courses/${encodeURIComponent(courseId)}`,
        { method: "DELETE" }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Failed to delete course.");
      }

      showToast("Course deleted successfully!");

      await loadCourses();
      await loadCourseOptions();
    } catch (error) {
      console.error("Course deletion failed:", error);
      showToast(error.message || "Unable to delete course.");
    }
  }

  // Upload modal controls
  const uploadModalOverlay = document.getElementById("uploadModalOverlay");
  const uploadForm = document.getElementById("uploadForm");
  const fileInput = document.getElementById("fileInput");
  const filePickerBtn = document.getElementById("filePickerBtn");
  const chipList = document.getElementById("chipList");
  const confirmUploadBtn = document.getElementById("confirmUploadBtn");

  const openUploadModal = () => {
    uploadModalOverlay?.setAttribute("aria-hidden", "false");
  };

  const closeUploadModal = () => {
    uploadModalOverlay?.setAttribute("aria-hidden", "true");
  };

  ["openUploadModalBtn", "openUploadHeaderBtn"].forEach((id) => {
    document.getElementById(id)?.addEventListener("click", openUploadModal);
  });

  document.getElementById("cancelUploadBtn")?.addEventListener("click", () => {
    closeUploadModal();
    uploadForm?.reset();

    if (chipList) chipList.replaceChildren();
  });

  // Open file picker
  filePickerBtn?.addEventListener("click", () => {
    fileInput?.click();
  });

  // Show selected file
  fileInput?.addEventListener("change", () => {
    if (!chipList) return;

    chipList.replaceChildren();

    const file = fileInput.files[0];
    if (!file) return;

    const fileLabel = document.createElement("span");
    fileLabel.textContent = `${file.name} (${formatFileSize(file.size)})`;
    chipList.appendChild(fileLabel);
  });

  // Populate course selector
  async function loadCourseOptions() {
    const courseSelect = document.getElementById("courseSelect");
    if (!courseSelect) return;

    try {
      const response = await fetch("/api/courses");

      if (!response.ok) {
        throw new Error("Failed to load courses.");
      }

      const data = await response.json();
      const selectedValue = courseSelect.value;

      courseSelect.replaceChildren();

      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = "-- Select Course --";
      courseSelect.appendChild(defaultOption);

      data.courses.forEach((course) => {
        const option = document.createElement("option");
        option.value = course.id;
        option.textContent = `${course.course_code} — ${course.course_name}`;
        courseSelect.appendChild(option);
      });

      courseSelect.value = selectedValue;
    } catch (error) {
      console.error("Course options loading failed:", error);
    }
  }

  // Upload document; FastAPI stores the file in Backblaze B2.
  confirmUploadBtn?.addEventListener("click", async () => {
    const file = fileInput?.files[0];

    if (!file) {
      showToast("Please select a document first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    confirmUploadBtn.disabled = true;
    confirmUploadBtn.textContent = "Uploading...";

    try {
      const response = await fetch("/api/documents", {
        method: "POST",
        body: formData,
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Document upload failed.");
      }

      uploadForm?.reset();

      if (chipList) chipList.replaceChildren();

      closeUploadModal();
      showToast("Document uploaded successfully!");

      await loadDocuments();
      await loadStorageUsage();
    } catch (error) {
      console.error("Document upload failed:", error);
      showToast(error.message || "Unable to upload document.");
    } finally {
      confirmUploadBtn.disabled = false;
      confirmUploadBtn.textContent = "Upload Document";
    }
  });

  // Format file size
  function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;

    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // Load uploaded documents
  async function loadDocuments() {
    const docList = document.getElementById("docList");
    const docsEmpty = document.getElementById("docsEmpty");

    if (!docList || !docsEmpty) return;

    function renderParsedData(details, parsedData, parsedAt) {
      const section = document.createElement("div");
      section.className = "parsed-results";

      const heading = document.createElement("strong");
      heading.textContent = "Parsed Results";

      const parsedDate = document.createElement("p");
      parsedDate.textContent =
        `Parsed ${new Date(parsedAt).toLocaleString()}`;

      const summaryHeading = document.createElement("strong");
      summaryHeading.textContent = "Summary";

      const summary = document.createElement("p");
      summary.textContent = parsedData.summary;

      section.append(heading, parsedDate, summaryHeading, summary);

      const coursesHeading = document.createElement("strong");
      coursesHeading.textContent = "Courses";
      section.appendChild(coursesHeading);

      if (parsedData.courses.length) {
        const coursesList = document.createElement("ul");

        parsedData.courses.forEach((course) => {
          const li = document.createElement("li");
          li.textContent = course;
          coursesList.appendChild(li);
        });

        section.appendChild(coursesList);
      } else {
        const noCourses = document.createElement("p");
        noCourses.textContent = "No courses identified.";
        section.appendChild(noCourses);
      }

      const deadlinesHeading = document.createElement("strong");
      deadlinesHeading.textContent = "Deadlines";
      section.appendChild(deadlinesHeading);

      if (parsedData.deadlines.length) {
        const deadlinesList = document.createElement("ul");

        parsedData.deadlines.forEach((deadline) => {
          const li = document.createElement("li");

          const title = document.createElement("strong");
          title.textContent = deadline.title;

          const dueDate = document.createElement("p");
          dueDate.textContent = deadline.due_date
            ? `Due: ${deadline.due_date}`
            : "Due date: Not identified";

          const evidence = document.createElement("p");
          evidence.textContent = deadline.evidence
            ? `Evidence: ${deadline.evidence}`
            : "No supporting text provided.";

          li.append(title, dueDate, evidence);
          deadlinesList.appendChild(li);
        });

        section.appendChild(deadlinesList);
      } else {
        const noDeadlines = document.createElement("p");
        noDeadlines.textContent = "No deadlines identified.";
        section.appendChild(noDeadlines);
      }

      details.appendChild(section);
    }

    try {
      const response = await fetch("/api/documents");

      if (!response.ok) {
        throw new Error("Failed to load documents.");
      }

      const data = await response.json();
      docList.replaceChildren();

      if (data.documents.length === 0) {
        docsEmpty.classList.remove("hidden");
        applyGlobalSearch();
        return;
      }

      docsEmpty.classList.add("hidden");

      data.documents.forEach((doc) => {
        const item = document.createElement("li");
        item.className = "document-card";

        const details = document.createElement("div");

        const filename = document.createElement("strong");
        filename.textContent = doc.filename;

        const metadata = document.createElement("p");
        metadata.textContent =
          `${formatFileSize(doc.size)} · ` +
          `Uploaded ${new Date(doc.uploaded_at).toLocaleDateString()}`;

        details.append(filename, metadata);

        // Show saved parsed results after every page load.
        if (doc.is_parsed && doc.parsed_data) {
          renderParsedData(details, doc.parsed_data, doc.parsed_at);
        }

        // Show Parse only if no saved result exists.
        let parseButton = null;

        if (!doc.is_parsed) {
          parseButton = document.createElement("button");
          parseButton.className = "btn-secondary-outline";
          parseButton.textContent = "Parse";
          parseButton.type = "button";
          parseButton.setAttribute(
            "aria-label",
            `Parse ${doc.filename}`
          );

          parseButton.addEventListener("click", async () => {
            parseButton.disabled = true;
            parseButton.textContent = "Parsing…";

            try {
              const response = await fetch(
                `/api/documents/${encodeURIComponent(doc.id)}/parse`,
                { method: "POST" }
              );

              if (!response.ok) {
                throw new Error("Failed to parse document.");
              }

              const result = await response.json();

              parseButton.remove();

              renderParsedData(
                details,
                result.parsed_data,
                result.parsed_at || new Date().toISOString()
              );

              applyGlobalSearch();
              showToast("Document parsed successfully.");
            } catch (error) {
              console.error("Document parsing failed:", error);
              parseButton.disabled = false;
              parseButton.textContent = "Parse";
              showToast("Unable to parse document.");
            }
          });
        }

        const openLink = document.createElement("a");
        openLink.className = "btn-secondary-outline";
        openLink.href =
          `/api/documents/${encodeURIComponent(doc.id)}/download`;
        openLink.target = "_blank";
        openLink.rel = "noopener noreferrer";
        openLink.textContent = "Open / Download";
        openLink.setAttribute(
          "aria-label",
          `Open or download ${doc.filename}`
        );

        const deleteButton = document.createElement("button");
        deleteButton.className = "btn-secondary-outline btn-delete";
        deleteButton.textContent = "Delete";
        deleteButton.type = "button";
        deleteButton.setAttribute(
          "aria-label",
          `Delete ${doc.filename}`
        );

        deleteButton.addEventListener("click", async () => {
          const confirmed = confirm(
            `Are you sure you want to delete "${doc.filename}"?`
          );

          if (!confirmed) return;

          try {
            const response = await fetch(
              `/api/documents/${encodeURIComponent(doc.id)}`,
              { method: "DELETE" }
            );

            if (!response.ok) {
              throw new Error("Failed to delete document.");
            }

            showToast("Document deleted successfully.");
            await loadDocuments();
            await loadStorageUsage();
          } catch (error) {
            console.error("Document deletion failed:", error);
            showToast("Unable to delete document.");
          }
        });

        item.append(details);

        if (parseButton) {
          item.appendChild(parseButton);
        }

        item.append(openLink, deleteButton);
        docList.appendChild(item);
      });

      applyGlobalSearch();
    } catch (error) {
      console.error("Document loading failed:", error);
      showToast("Unable to load documents.");
    }
  }

  // Load storage usage
  async function loadStorageUsage() {
    const usageText = document.getElementById("storageUsageText");
    const usagePercentage = document.getElementById("storageUsagePercentage");
    const usageBar = document.getElementById("storageUsageBar");
    const progress = document.getElementById("storageUsageProgress");

    if (!usageText || !usagePercentage || !usageBar || !progress) return;

    try {
      const response = await fetch("/api/storage");

      if (!response.ok) {
        throw new Error("Failed to load storage usage.");
      }

      const data = await response.json();
      const usedBytes = data.used_bytes;
      const limitBytes = data.limit_bytes;
      const percentage = Math.min(
        100,
        Math.max(0, data.used_percent)
      );

      const formatStorage = (bytes) => {
        if (bytes < 1024 * 1024) {
          return `${(bytes / 1024).toFixed(1)} KB`;
        }

        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
      };

      let color = "#22c55e";

      if (percentage >= 90) {
        color = "#ef4444";
      } else if (percentage >= 80) {
        color = "#f97316";
      } else if (percentage >= 50) {
        color = "#eab308";
      }

      usagePercentage.textContent = `${percentage.toFixed(1)}%`;
      usagePercentage.style.color = color;

      usageText.textContent =
        `Total storage usage: ${formatStorage(usedBytes)} / ` +
        `${formatStorage(limitBytes)}`;

      usageBar.style.width = `${percentage}%`;
      usageBar.style.backgroundColor = color;
      progress.setAttribute("aria-valuenow", percentage.toFixed(1));
    } catch (error) {
      console.error("Storage usage loading failed:", error);
      usageText.textContent = "Storage usage unavailable";
    }
  }

  // Deadline modal: created dynamically; dashboard.html needs no changes.
  const deadlineModalOverlay = document.createElement("div");
  deadlineModalOverlay.className = "modal-overlay";
  deadlineModalOverlay.id = "deadlineModalOverlay";
  deadlineModalOverlay.setAttribute("aria-hidden", "true");

  deadlineModalOverlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true"
         aria-labelledby="deadlineModalTitle">
      <h3 id="deadlineModalTitle">Add Deadline</h3>

      <form id="deadlineForm">
        <div class="field">
          <label for="deadlineTitle">Title</label>
          <input type="text" id="deadlineTitle" required maxlength="200"
                 placeholder="e.g. Data Structures Assignment">
        </div>

        <div class="field">
          <label for="deadlineDescription">Description (Optional)</label>
          <textarea id="deadlineDescription" rows="3"
                    placeholder="What needs to be completed?"></textarea>
        </div>

        <div class="field">
          <label for="deadlineDueAt">Due date and time</label>
          <input type="datetime-local" id="deadlineDueAt" required>
        </div>

        <div class="field">
          <label for="deadlineCourseId">Course (Optional)</label>
          <select id="deadlineCourseId">
            <option value="">-- No Course --</option>
          </select>
        </div>

        <div class="field">
          <label for="deadlineStatus">Status</label>
          <select id="deadlineStatus" required>
            <option value="not_started">Not started</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
          </select>
        </div>

        <div class="modal-actions">
          <button type="button" class="btn-plain" id="cancelDeadlineBtn">
            Cancel
          </button>
          <button type="submit" class="btn-primary" id="saveDeadlineBtn">
            Save Deadline
          </button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(deadlineModalOverlay);

  const deadlineForm = document.getElementById("deadlineForm");
  const deadlineTitleInput = document.getElementById("deadlineTitle");
  const deadlineDescriptionInput =
    document.getElementById("deadlineDescription");
  const deadlineDueAtInput = document.getElementById("deadlineDueAt");
  const deadlineCourseSelect = document.getElementById("deadlineCourseId");
  const deadlineStatusSelect = document.getElementById("deadlineStatus");
  const saveDeadlineBtn = document.getElementById("saveDeadlineBtn");

  let editingDeadlineId = null;

  // Open create/edit deadline modal
  const openDeadlineModal = async (deadline = null) => {
    editingDeadlineId = deadline?.id || null;

    document.getElementById("deadlineModalTitle").textContent =
      deadline ? "Edit Deadline" : "Add Deadline";

    saveDeadlineBtn.textContent =
      deadline ? "Update Deadline" : "Save Deadline";

    deadlineForm.reset();

    try {
      const response = await fetch("/api/courses");

      if (!response.ok) {
        throw new Error("Failed to load courses.");
      }

      const data = await response.json();
      courseCache = data.courses;

      deadlineCourseSelect.replaceChildren();

      const noCourseOption = document.createElement("option");
      noCourseOption.value = "";
      noCourseOption.textContent = "-- No Course --";
      deadlineCourseSelect.appendChild(noCourseOption);

      courseCache.forEach((course) => {
        const option = document.createElement("option");
        option.value = course.id;
        option.textContent =
          `${course.course_code} — ${course.course_name}`;

        deadlineCourseSelect.appendChild(option);
      });
    } catch (error) {
      console.error("Deadline course options loading failed:", error);
      showToast("Unable to load courses.");
      return;
    }

    if (deadline) {
      deadlineTitleInput.value = deadline.title || "";
      deadlineDescriptionInput.value = deadline.description || "";
      deadlineDueAtInput.value = toLocalDateTimeInput(deadline.due_at);
      deadlineCourseSelect.value = deadline.course_id || "";
      deadlineStatusSelect.value = deadline.status || "not_started";
    } else {
      deadlineStatusSelect.value = "not_started";
    }

    deadlineModalOverlay.setAttribute("aria-hidden", "false");
    deadlineTitleInput.focus();
  };

  const closeDeadlineModal = () => {
    deadlineModalOverlay.setAttribute("aria-hidden", "true");
    editingDeadlineId = null;
  };

  // Convert an ISO datetime into the browser's local datetime input format.
  function toLocalDateTimeInput(value) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "";

    const localDate = new Date(
      date.getTime() - date.getTimezoneOffset() * 60000
    );

    return localDate.toISOString().slice(0, 16);
  }

  // Open the existing Quick Add Task modal.
  document
    .getElementById("createDeadlineModalBtn")
    ?.addEventListener("click", () => {
      openDeadlineModal();
    });

  document
    .getElementById("cancelDeadlineBtn")
    .addEventListener("click", closeDeadlineModal);

  deadlineModalOverlay.addEventListener("click", (event) => {
    if (event.target === deadlineModalOverlay) {
      closeDeadlineModal();
    }
  });

  // Create or update a deadline.
  deadlineForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const dueDate = new Date(deadlineDueAtInput.value);

    if (Number.isNaN(dueDate.getTime())) {
      showToast("Please enter a valid due date and time.");
      return;
    }

    const deadlineData = {
      title: deadlineTitleInput.value.trim(),
      description: deadlineDescriptionInput.value.trim(),
      due_at: dueDate.toISOString(),
      course_id: deadlineCourseSelect.value || null,
      status: deadlineStatusSelect.value,
    };

    saveDeadlineBtn.disabled = true;

    try {
      const isEditing = Boolean(editingDeadlineId);

      const response = await fetch(
        isEditing
          ? `/api/deadlines/${encodeURIComponent(editingDeadlineId)}`
          : "/api/deadlines",
        {
          method: isEditing ? "PUT" : "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(deadlineData),
        }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Failed to save deadline.");
      }

      closeDeadlineModal();

      showToast(
        isEditing
          ? "Deadline updated successfully!"
          : "Deadline created successfully!"
      );

      await loadDeadlines();
    } catch (error) {
      console.error("Deadline save failed:", error);
      showToast(error.message || "Unable to save deadline.");
    } finally {
      saveDeadlineBtn.disabled = false;
    }
  });

  // Load and render deadlines as individual cards.
  async function loadDeadlines() {
    const deadlineList = document.getElementById("deadlineList");
    const deadlinesEmpty = document.getElementById("deadlinesEmpty");

    if (!deadlineList || !deadlinesEmpty) return;

    try {
      const response = await fetch("/api/deadlines");
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Failed to load deadlines.");
      }

      deadlineList.replaceChildren();

      if (!data.deadlines || data.deadlines.length === 0) {
        deadlinesEmpty.classList.remove("hidden");
        applyGlobalSearch();
        return;
      }

      deadlinesEmpty.classList.add("hidden");

      const statusLabels = {
        not_started: "Not started",
        in_progress: "In progress",
        completed: "Completed",
      };

      // Preserve the order returned by the backend.
      data.deadlines.forEach((deadline) => {
        const item = document.createElement("li");
        item.className = "deadline-card";

        const dueDate = new Date(deadline.due_at);
        const remainingMs = dueDate.getTime() - Date.now();
        const remainingDays = remainingMs / (1000 * 60 * 60 * 24);

        let urgency = "green";

        if (remainingDays <= 1) {
          urgency = "red";
        } else if (remainingDays < 3) {
          urgency = "orange";
        } else if (remainingDays < 7) {
          urgency = "yellow";
        }

        item.classList.add(`deadline-${urgency}`);

        // Card heading and urgency indicator
        const heading = document.createElement("div");
        heading.className = "deadline-card-heading";

        const titleGroup = document.createElement("div");
        titleGroup.className = "deadline-title-group";

        const dot = document.createElement("span");
        dot.className = `deadline-urgency-dot urgency-${urgency}`;
        dot.setAttribute("aria-label", `${urgency} urgency`);
        dot.setAttribute("role", "img");

        const title = document.createElement("h3");
        title.className = "deadline-title";
        title.textContent = deadline.title;

        titleGroup.append(dot, title);
        heading.appendChild(titleGroup);

        // Deadline information
        const details = document.createElement("div");
        details.className = "deadline-card-details";

        const description = document.createElement("p");
        description.textContent =
          deadline.description || "No description";

        const metadata = document.createElement("p");
        metadata.textContent =
          `Due ${
            Number.isNaN(dueDate.getTime())
              ? "date unavailable"
              : dueDate.toLocaleString()
          } · ${deadline.time_left || ""}`;

        const status = document.createElement("p");
        status.textContent =
          `Status: ${statusLabels[deadline.status] || deadline.status}`;

        details.append(description, metadata, status);

        const course = courseCache.find(
          (entry) => entry.id === deadline.course_id
        );

        if (course) {
          const courseLabel = document.createElement("p");
          courseLabel.textContent =
            `Course: ${course.course_code} — ${course.course_name}`;

          details.appendChild(courseLabel);
        }

        // Card-specific actions
        const actions = document.createElement("div");
        actions.className = "deadline-card-actions";

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "btn-secondary-outline";
        editButton.textContent = "Edit";
        editButton.addEventListener("click", () => {
          openDeadlineModal(deadline);
        });

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className =
          "btn-secondary-outline deadline-delete-btn";
        deleteButton.textContent = "Delete";

        deleteButton.addEventListener("click", async () => {
          if (!confirm(`Delete deadline "${deadline.title}"?`)) return;

          deleteButton.disabled = true;

          try {
            const deleteResponse = await fetch(
              `/api/deadlines/${encodeURIComponent(deadline.id)}`,
              { method: "DELETE" }
            );

            const result = await deleteResponse.json();

            if (!deleteResponse.ok) {
              throw new Error(
                result.detail || "Failed to delete deadline."
              );
            }

            showToast("Deadline deleted successfully!");
            await loadDeadlines();
          } catch (error) {
            console.error("Deadline deletion failed:", error);
            showToast(error.message || "Unable to delete deadline.");
            deleteButton.disabled = false;
          }
        });

        actions.append(editButton, deleteButton);
        item.append(heading, details, actions);
        deadlineList.appendChild(item);
      });

      applyGlobalSearch();
    } catch (error) {
      console.error("Deadline loading failed:", error);
      showToast(error.message || "Unable to load deadlines.");
    }
  }

  // Load dashboard data on startup.
  loadCourses().then(() => loadDeadlines());
  loadCourseOptions();
  loadDocuments();
  loadStorageUsage();
});
