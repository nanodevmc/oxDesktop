document.addEventListener('DOMContentLoaded', () => {
  // Syntax highlighting
  if (window.Prism) {
    window.Prism.highlightAll();
  }

  // Mobile drawer navigation
  const toggleBtn = document.getElementById('mobile-menu-toggle');
  const sidebar = document.querySelector('.sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');

  if (toggleBtn && sidebar && backdrop) {
    const toggleMenu = () => {
      const isOpen = sidebar.classList.toggle('open');
      backdrop.classList.toggle('active', isOpen);
      toggleBtn.classList.toggle('active', isOpen);
      document.body.classList.toggle('menu-open', isOpen);
    };

    toggleBtn.addEventListener('click', toggleMenu);
    backdrop.addEventListener('click', toggleMenu);

    sidebar.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        if (sidebar.classList.contains('open')) {
          toggleMenu();
        }
      });
    });
  }

  // Copy button & clean container for code blocks
  document.querySelectorAll('pre').forEach(pre => {
    const code = pre.querySelector('code');
    if (!code) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'code-block-wrapper';
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);

    const header = document.createElement('div');
    header.className = 'code-header';
    let lang = 'code';
    for (const c of code.classList) {
      if (c.startsWith('language-')) {
        lang = c.replace('language-', '');
        break;
      }
    }
    header.innerHTML = `<span>${lang}</span><button class="btn-copy"><svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 21H8V7h11m0-2H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m-3-4H4a2 2 0 0 0-2 2v14h2V3h12V1Z"/></svg><span>Копировать</span></button>`;
    wrapper.insertBefore(header, pre);

    const btn = header.querySelector('.btn-copy');
    const label = btn.querySelector('span');
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(code.innerText).then(() => {
        btn.classList.add('copied');
        label.innerText = 'Скопировано!';
        setTimeout(() => {
          btn.classList.remove('copied');
          label.innerText = 'Копировать';
        }, 2000);
      });
    });
  });

  // Ensure all tables are wrapped in a responsive scroll container
  document.querySelectorAll('table').forEach(table => {
    if (!table.parentElement.classList.contains('table-container')) {
      const container = document.createElement('div');
      container.className = 'table-container';
      table.parentNode.insertBefore(container, table);
      container.appendChild(table);
    }
  });

  // Client-side search filter in sidebar
  const searchInput = document.getElementById('sidebar-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      document.querySelectorAll('.sidebar-links li').forEach(li => {
        const text = li.innerText.toLowerCase();
        if (!q || text.includes(q)) {
          li.style.display = '';
        } else {
          li.style.display = 'none';
        }
      });
    });
  }

  // Highlight active link in sidebar
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.sidebar-links a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === currentPath || (currentPath === '' && href === 'index.html')) {
      a.classList.add('active');
    }
  });

  // Dynamic release version in footer (updated via version.json and cached for 2 hours)
  const initFooterVersion = () => {
    const el = document.getElementById('footer-version') || document.querySelector('.footer-version');
    if (!el) return;

    const CACHE_KEY = 'ox_docs_version_cache';
    const CACHE_TTL_MS = 2 * 60 * 60 * 1000; // 2 hours

    const applyVersion = (data) => {
      if (!data || !data.version) return;
      const url = data.html_url || 'https://github.com/nanodevmc/oxDesktop/releases';
      el.innerHTML = `<a href="${url}" target="_blank" rel="noopener noreferrer">oxDesktop v${data.version}</a>`;
    };

    // Check localStorage cache first
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (Date.now() - parsed.timestamp < CACHE_TTL_MS) {
          applyVersion(parsed.data);
          return;
        }
      }
    } catch (_) {}

    // Fetch version.json from docs site
    fetch('version.json?_t=' + Date.now())
      .then(r => r.ok ? r.json() : Promise.reject())
      .catch(() => {
        // Fallback to GitHub API if version.json is unreachable
        return fetch('https://api.github.com/repos/nanodevmc/oxDesktop/releases?per_page=5')
          .then(r => r.json())
          .then(releases => {
            const rel = releases.find(r => r.tag_name && r.tag_name !== 'ci-cache' && !r.draft);
            if (!rel) return null;
            return {
              version: rel.tag_name.replace(/^[vV]/, ''),
              html_url: rel.html_url
            };
          });
      })
      .then(data => {
        if (data) {
          applyVersion(data);
          try {
            localStorage.setItem(CACHE_KEY, JSON.stringify({ timestamp: Date.now(), data }));
          } catch (_) {}
        }
      })
      .catch(() => {});
  };

  initFooterVersion();
});
