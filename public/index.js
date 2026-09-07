document.addEventListener('DOMContentLoaded', () => {
    // Mobile Navbar Elements
    const mobileToggle = document.getElementById('mobileToggle');
    const navContainer = document.getElementById('navContainer');

    // Authentication Action Buttons
    const navLoginBtn = document.getElementById('navLoginBtn');
    const navSignupBtn = document.getElementById('navSignupBtn');
    const heroSignupBtn = document.getElementById('heroSignupBtn');

    // Handle Mobile Menu Toggle
    if (mobileToggle && navContainer) {
        mobileToggle.addEventListener('click', () => {
            navContainer.classList.toggle('active');
        });

        // Close mobile drawer when clicking navigation links
        document.querySelectorAll('.nav-links a, .nav-actions a').forEach(link => {
            link.addEventListener('click', () => {
                navContainer.classList.remove('active');
            });
        });
    }

    // Handle Login Button Click (Navbar)
    if (navLoginBtn) {
        navLoginBtn.addEventListener('click', (event) => {
            event.preventDefault();
            window.location.href = '/auth/login';
        });
    }

    // Handle Sign Up Button Click (Navbar)
    if (navSignupBtn) {
        navSignupBtn.addEventListener('click', (event) => {
            event.preventDefault();
            window.location.href = '/auth/login';
        });
    }

    // Handle Sign Up Free Button Click (Hero Section)
    if (heroSignupBtn) {
        heroSignupBtn.addEventListener('click', (event) => {
            event.preventDefault();
            window.location.href = '/auth/login';
        });
    }
});