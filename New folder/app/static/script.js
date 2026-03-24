/*
  script.js — ZapShare Client-side JavaScript

  This file handles:
  1. Dark/Light theme toggle
  2. Saving theme preference in localStorage
*/

// ---- Theme Toggle Function ----
function toggleTheme() {
    const body = document.documentElement;
    const btn = document.getElementById('themeToggle');

    // Check current theme and toggle
    if (body.getAttribute('data-theme') === 'dark') {
        // Switch to light mode
        body.removeAttribute('data-theme');
        btn.textContent = '🌙';
        localStorage.setItem('theme', 'light');
    } else {
        // Switch to dark mode
        body.setAttribute('data-theme', 'dark');
        btn.textContent = '☀️';
        localStorage.setItem('theme', 'dark');
    }
}

// ---- Load Saved Theme on Page Load ----
(function () {
    const savedTheme = localStorage.getItem('theme');
    const btn = document.getElementById('themeToggle');

    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        if (btn) btn.textContent = '☀️';
    }
})();
