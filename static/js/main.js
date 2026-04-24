// ─── Dark Mode ─────────────────────────────────────────────────────────────
const html       = document.documentElement;
const toggleBtns = document.querySelectorAll('#themeToggle, #themeToggleMobile');
const savedTheme = localStorage.getItem('cv-theme') || 'light';
html.setAttribute('data-theme', savedTheme);
toggleBtns.forEach(btn => {
  const icon = btn.querySelector('.theme-icon');
  if (icon) icon.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
});

toggleBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('cv-theme', next);
    document.querySelectorAll('.theme-icon').forEach(icon => {
      icon.textContent = next === 'dark' ? '☀️' : '🌙';
    });
  });
});

// ─── Mobile Hamburger ───────────────────────────────────────────────────────
const hamburger    = document.getElementById('hamburger');
const mobileDrawer = document.getElementById('mobileDrawer');
const overlay      = document.getElementById('mobileOverlay');

function openMenu() {
  hamburger?.classList.add('open');
  mobileDrawer?.classList.add('open');
  overlay?.classList.add('show');
  document.body.style.overflow = 'hidden';
}
function closeMenu() {
  hamburger?.classList.remove('open');
  mobileDrawer?.classList.remove('open');
  overlay?.classList.remove('show');
  document.body.style.overflow = '';
}
hamburger?.addEventListener('click', () => {
  mobileDrawer?.classList.contains('open') ? closeMenu() : openMenu();
});
// Close drawer on link click
mobileDrawer?.querySelectorAll('.drawer-link').forEach(link => {
  link.addEventListener('click', closeMenu);
});

// ─── Loading Spinner on form submit ────────────────────────────────────────
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', function() {
    const btn = this.querySelector('button[type="submit"]');
    if (btn && !btn.classList.contains('no-spinner')) {
      btn.classList.add('btn-loading');
    }
  });
});

// ─── Upvote AJAX ────────────────────────────────────────────────────────────
document.querySelectorAll('.upvote-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const loginUrl = btn.dataset.login;
    if (loginUrl) { window.location.href = loginUrl; return; }

    const id        = btn.dataset.id;
    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    try {
      const res  = await fetch(`/${id}/upvote/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      if (res.status === 400) { alert('You cannot upvote your own complaint.'); return; }
      const data = await res.json();
      if (res.ok) {
        btn.classList.toggle('active', data.upvoted);
        const cnt = btn.querySelector('.upvote-count');
        if (cnt) cnt.textContent = data.count;
      }
    } catch (err) { console.error('Upvote error:', err); }
  });
});

// ─── Complaint Card Urgency Borders ─────────────────────────────────────────
document.querySelectorAll('.complaint-card[data-hours]').forEach(card => {
  const hours  = parseFloat(card.dataset.hours);
  const status = card.dataset.status;
  if (status === 'resolved') {
    card.classList.add('urgency-resolved');
  } else if (hours < 12) {
    card.classList.add('urgency-fresh');
  } else if (hours < 20) {
    card.classList.add('urgency-approaching');
  } else {
    card.classList.add('urgency-critical');
  }
});

// ─── Auto-dismiss alerts ────────────────────────────────────────────────────
document.querySelectorAll('.alert').forEach(alert => {
  setTimeout(() => {
    alert.style.transition = 'opacity .4s';
    alert.style.opacity    = '0';
    setTimeout(() => alert.remove(), 400);
  }, 4000);
});

// ─── Auto-save complaint draft ──────────────────────────────────────────────
const titleField = document.getElementById('draftTitle');
const descField  = document.getElementById('draftDesc');

if (titleField && descField) {
  // Restore draft
  const saved = localStorage.getItem('cv_complaint_draft');
  if (saved) {
    try {
      const draft = JSON.parse(saved);
      if (draft.title && titleField.value === '') {
        titleField.value = draft.title;
        descField.value  = draft.desc || '';
        const banner = document.getElementById('draftBanner');
        if (banner) banner.style.display = 'flex';
      }
    } catch(e) {}
  }
  // Save draft on input
  [titleField, descField].forEach(field => {
    field.addEventListener('input', () => {
      localStorage.setItem('cv_complaint_draft', JSON.stringify({
        title: titleField.value,
        desc:  descField.value,
      }));
    });
  });
  // Clear draft on successful submit
  document.querySelector('form')?.addEventListener('submit', () => {
    localStorage.removeItem('cv_complaint_draft');
  });
}

function clearDraft() {
  localStorage.removeItem('cv_complaint_draft');
  const banner = document.getElementById('draftBanner');
  if (banner) banner.style.display = 'none';
  if (titleField) titleField.value = '';
  if (descField)  descField.value  = '';
}

// ─── File upload preview ────────────────────────────────────────────────────
const fileInput   = document.getElementById('imageUpload');
const filePreview = document.getElementById('filePreview');

fileInput?.addEventListener('change', function() {
  const file = this.files[0];
  if (!file || !filePreview) return;

  const reader = new FileReader();
  reader.onload = e => {
    filePreview.innerHTML = `
      <div style="display:flex;align-items:center;gap:.75rem;padding:.75rem;
           background:var(--bg-input);border-radius:8px;border:1px solid var(--border);
           margin-top:.5rem;">
        <img src="${e.target.result}" style="width:56px;height:56px;
             object-fit:cover;border-radius:6px;" alt="Preview">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:.85rem;white-space:nowrap;
               overflow:hidden;text-overflow:ellipsis;">${file.name}</div>
          <div style="font-size:.75rem;color:var(--text-muted);">
            ${(file.size/1024).toFixed(1)} KB
          </div>
        </div>
        <button type="button" onclick="clearFile()"
                style="background:none;border:none;cursor:pointer;
                       color:var(--danger);font-size:1.1rem;padding:0 .25rem;">✕</button>
      </div>`;
    filePreview.style.display = 'block';
  };
  reader.readAsDataURL(file);
});

function clearFile() {
  if (fileInput) fileInput.value = '';
  if (filePreview) { filePreview.innerHTML = ''; filePreview.style.display = 'none'; }
}