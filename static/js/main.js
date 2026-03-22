// CampusVoice — Main JS

// Dark/Light mode
const html = document.documentElement;
const toggleBtn = document.getElementById('themeToggle');
const themeIcon = toggleBtn?.querySelector('.theme-icon');
const savedTheme = localStorage.getItem('cv-theme') || 'light';
html.setAttribute('data-theme', savedTheme);
if (themeIcon) themeIcon.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
toggleBtn?.addEventListener('click', () => {
  const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('cv-theme', next);
  if (themeIcon) themeIcon.textContent = next === 'dark' ? '☀️' : '🌙';
});

// Upvote — login required
document.querySelectorAll('.upvote-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const complaintId = btn.dataset.id;
    const loginUrl = btn.dataset.login;

    // If not logged in, redirect to login
    if (loginUrl) {
      window.location.href = loginUrl;
      return;
    }

    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    try {
      const res = await fetch(`/${complaintId}/upvote/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (res.status === 400) {
        alert('You cannot upvote your own complaint.');
        return;
      }
      const data = await res.json();
      if (res.ok) {
        btn.classList.toggle('active', data.upvoted);
        const countEl = btn.querySelector('.upvote-count');
        if (countEl) countEl.textContent = data.count;
      }
    } catch (err) {
      console.error('Upvote error:', err);
    }
  });
});

// Auto-dismiss alerts
document.querySelectorAll('.alert').forEach(alert => {
  setTimeout(() => {
    alert.style.transition = 'opacity 0.4s ease';
    alert.style.opacity = '0';
    setTimeout(() => alert.remove(), 400);
  }, 4000);
});
