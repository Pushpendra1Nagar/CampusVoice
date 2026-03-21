// CampusVoice — Main JS

// ─── Dark / Light Mode Toggle ────────────────────────────────────────────
const html = document.documentElement;
const toggleBtn = document.getElementById('themeToggle');
const themeIcon = toggleBtn?.querySelector('.theme-icon');

const savedTheme = localStorage.getItem('cv-theme') || 'light';
html.setAttribute('data-theme', savedTheme);
if (themeIcon) themeIcon.textContent = savedTheme === 'dark' ? '☀️' : '🌙';

toggleBtn?.addEventListener('click', () => {
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('cv-theme', next);
  if (themeIcon) themeIcon.textContent = next === 'dark' ? '☀️' : '🌙';
});

// ─── Upvote (AJAX) ────────────────────────────────────────────────────────
document.querySelectorAll('.upvote-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const complaintId = btn.dataset.id;
    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

    try {
      const res = await fetch(`/${complaintId}/upvote/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json' },
      });
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

// ─── Auto-dismiss alerts ────────────────────────────────────────────────
document.querySelectorAll('.alert').forEach(alert => {
  setTimeout(() => {
    alert.style.transition = 'opacity 0.4s ease';
    alert.style.opacity = '0';
    setTimeout(() => alert.remove(), 400);
  }, 4000);
});
