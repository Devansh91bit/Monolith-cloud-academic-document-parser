document.addEventListener("DOMContentLoaded", () => {
  const logoutBtn = document.getElementById("logoutBtn");

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      window.location.href = "/auth/logout";
    });
  }

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
          usernameDisplay.textContent = data.user.name || data.user.nickname || "User";
        }
        if (userEmailDisplay && data.user.email) {
          userEmailDisplay.textContent = data.user.email;
        }
      }
    })
    .catch((err) => {
      console.warn("User info fetch failed:", err);
    });
});