
document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  let toastTimeout;

  const showToast = (message) => {
    if (!toast) return;

    toast.textContent = message;
    toast.classList.add("visible");

    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toast.classList.remove("visible");
    }, 4000);
  };

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
      courseList.replaceChildren();

      if (data.courses.length === 0) {
        coursesEmpty.classList.remove("hidden");
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

    try {
      const response = await fetch("/api/documents");

      if (!response.ok) {
        throw new Error("Failed to load documents.");
      }

      const data = await response.json();
      docList.replaceChildren();

      if (data.documents.length === 0) {
        docsEmpty.classList.remove("hidden");
        return;
      }

      docsEmpty.classList.add("hidden");

      data.documents.forEach((doc) => {
        // Use "doc" for the database record, preserving the browser's
        // global "document" object for createElement().
        const item = document.createElement("li");

        const details = document.createElement("div");

        const filename = document.createElement("strong");
        filename.textContent = doc.filename;

        const metadata = document.createElement("p");
        metadata.textContent =
          `${formatFileSize(doc.size)} · ` +
          `Uploaded ${new Date(doc.uploaded_at).toLocaleDateString()}`;

        details.append(filename, metadata);

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
  } catch (error) {
    console.error("Document deletion failed:", error);
    showToast("Unable to delete document.");
  }
});


        item.append(details, openLink, deleteButton); 
        docList.appendChild(item);
      });
    } catch (error) {
      console.error("Document loading failed:", error);
      showToast("Unable to load documents.");
    }
  }

  // Load dashboard data on startup
  loadCourses();
  loadCourseOptions();
  loadDocuments();
});
