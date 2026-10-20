document.addEventListener("DOMContentLoaded", () => {
  const logoutBtn = document.getElementById("logoutBtn");

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      window.location.href = "/auth/logout";
    });
  }

  // Fetch authenticated user information
  fetch("/api/me")
    .then((res) => {
      if (!res.ok) throw new Error("Unauthorized");
      return res.json();
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
    .catch((err) => {
      console.warn("User info fetch failed:", err);
    });

  // Course modal controls
  const courseModalOverlay = document.getElementById("courseModalOverlay");

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

  const openCourseModal = () => {
    if (courseModalOverlay) {
      courseModalOverlay.setAttribute("aria-hidden", "false");
    }
  };

  const closeCourseModal = () => {
    if (courseModalOverlay) {
      courseModalOverlay.setAttribute("aria-hidden", "true");
    }
  };

  ["openCourseModalBtn", "openCourseHeaderBtn"].forEach((id) => {
    const button = document.getElementById(id);

    if (button) {
      button.addEventListener("click", openCourseModal);
    }
  });

  const cancelCourseBtn = document.getElementById("cancelCourseBtn");

  if (cancelCourseBtn) {
    cancelCourseBtn.addEventListener("click", closeCourseModal);
  }

  // Submit course
  const courseForm = document.getElementById("courseForm");

  if (courseForm) {
    courseForm.addEventListener("submit", async (event) => {
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
      } catch (error) {
        console.error("Course submission failed:", error);
        alert(error.message || "Something went wrong while saving the course.");
      }
    });
  }
  
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
  }
}

loadCourses();


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
  } catch (error) {
    console.error("Course deletion failed:", error);
    showToast(error.message || "Unable to delete course.");
  }
}

});