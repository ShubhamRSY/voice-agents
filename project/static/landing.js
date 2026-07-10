(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // ── Spotlight cursor (throttled, desktop only) ──
  const spotlight = $('#spotlight');
  const finePointer = window.matchMedia('(pointer: fine)').matches;
  if (spotlight && finePointer && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    let mx = 0;
    let my = 0;
    let scheduled = false;
    document.addEventListener('mousemove', (e) => {
      mx = e.clientX;
      my = e.clientY;
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        spotlight.style.setProperty('--mx', `${mx}px`);
        spotlight.style.setProperty('--my', `${my}px`);
        scheduled = false;
      });
    }, { passive: true });
  } else if (spotlight) {
    spotlight.style.display = 'none';
  }

  // ── Nav scroll state + progress ──
  const nav = $('.nav');
  const progress = $('.scroll-progress');
  const onScroll = () => {
    const y = window.scrollY;
    nav?.classList.toggle('scrolled', y > 24);
    if (progress) {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      progress.style.width = h > 0 ? `${(y / h) * 100}%` : '0%';
    }
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ── Mobile menu ──
  const toggle = $('.nav-toggle');
  const mobileMenu = $('.mobile-menu');
  toggle?.addEventListener('click', () => {
    const open = toggle.classList.toggle('open');
    mobileMenu?.classList.toggle('open', open);
    document.body.style.overflow = open ? 'hidden' : '';
  });
  $$('.mobile-menu a').forEach((a) => {
    a.addEventListener('click', () => {
      toggle?.classList.remove('open');
      mobileMenu?.classList.remove('open');
      document.body.style.overflow = '';
    });
  });

  // ── Smooth anchor scroll ──
  $$('a[href^="#"]').forEach((a) => {
    a.addEventListener('click', (e) => {
      const id = a.getAttribute('href');
      if (!id || id === '#') return;
      const target = $(id);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  // ── Rotating hero words ──
  const rotateEl = $('.hero-rotate');
  const words = ['Chat', 'Voice', 'Email', 'WhatsApp', 'SMS', 'Social'];
  let wordIdx = 0;
  if (rotateEl) {
    const cycle = () => {
      rotateEl.style.opacity = '0';
      rotateEl.style.transform = 'translateY(8px)';
      setTimeout(() => {
        wordIdx = (wordIdx + 1) % words.length;
        rotateEl.textContent = words[wordIdx];
        rotateEl.style.opacity = '1';
        rotateEl.style.transform = 'none';
      }, 280);
    };
    rotateEl.style.transition = 'opacity .28s ease, transform .28s ease';
    setInterval(cycle, 2800);
  }

  // ── Animated counters ──
  const animateCounter = (el) => {
    const raw = el.dataset.count;
    if (!raw) return;
    const match = raw.match(/^([^0-9]*)([0-9.]+)(.*)$/);
    if (!match) {
      el.textContent = raw;
      return;
    }
    const [, prefix, numStr, suffix] = match;
    const target = parseFloat(numStr);
    const isFloat = numStr.includes('.');
    const duration = 1600;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - (1 - t) ** 3;
      const val = target * eased;
      el.textContent = prefix + (isFloat ? val.toFixed(1) : Math.round(val)) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  // ── Intersection observer (reveal + counters) ──
  const revealObs = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        e.target.classList.add('visible');
        if (e.target.classList.contains('stat-num') && !e.target.dataset.animated) {
          e.target.dataset.animated = '1';
          animateCounter(e.target);
        }
        revealObs.unobserve(e.target);
      });
    },
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  );
  $$('.reveal, .stat-num[data-count]').forEach((el) => revealObs.observe(el));

  // ── Channel cards spotlight + active state ──
  $$('.channel-card').forEach((card) => {
    card.addEventListener('mousemove', (e) => {
      const r = card.getBoundingClientRect();
      card.style.setProperty('--cx', `${((e.clientX - r.left) / r.width) * 100}%`);
      card.style.setProperty('--cy', `${((e.clientY - r.top) / r.height) * 100}%`);
    });
    card.addEventListener('click', () => {
      $$('.channel-card').forEach((c) => c.classList.remove('active'));
      card.classList.add('active');
    });
  });

  // ── Product showcase tabs + lazy images ──
  const tabs = $$('.showcase-tab');
  const slides = $$('.showcase-slide');
  let autoTab = 0;
  let tabTimer = null;

  const loadSlideImage = (idx) => {
    const img = slides[idx]?.querySelector('img[data-src]');
    if (!img || img.src) return;
    img.src = img.dataset.src;
    img.removeAttribute('data-src');
  };

  const setTab = (idx) => {
    tabs.forEach((t, i) => {
      const on = i === idx;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    slides.forEach((s, i) => s.classList.toggle('active', i === idx));
    loadSlideImage(idx);
    autoTab = idx;
  };

  tabs.forEach((tab, i) => tab.addEventListener('click', () => setTab(i)));

  const showcaseSection = $('#showcase');
  if (showcaseSection && slides.length) {
    const showcaseObs = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        loadSlideImage(0);
        showcaseObs.disconnect();
        tabTimer = window.setInterval(() => setTab((autoTab + 1) % tabs.length), 6000);
      },
      { rootMargin: '120px' }
    );
    showcaseObs.observe(showcaseSection);
  }

  // ── Architecture layer explorer ──
  const archDetails = {
    ui: 'Static HTML/CSS/JS with SSE & WebSocket streaming. Embeddable widget, mobile SDKs, and agent copilot UI — all real-time.',
    edge: 'Caddy terminates TLS with automatic Let\'s Encrypt, applies rate limiting, security headers, and reverse-proxies to Nexus.',
    api: 'FastAPI serves REST, WebSocket, and static assets. JWT auth, multi-tenant isolation, audit logging, and OIDC SSO.',
    orch: 'LangGraph orchestrator routes agents, executes 62 integration tools, runs RAG retrieval, and calls OpenAI, Claude, or Gemini.',
    data: 'PostgreSQL 16 for persistence, Redis 7 for cache/queues, ChromaDB for vectors. Twilio & Meta Graph for channels.',
  };
  const archDetail = $('#arch-detail');
  $$('.arch-layer').forEach((layer) => {
    layer.addEventListener('click', () => {
      const key = layer.dataset.layer;
      const active = layer.classList.contains('active');
      $$('.arch-layer').forEach((l) => l.classList.remove('active'));
      if (!active && key && archDetails[key]) {
        layer.classList.add('active');
        archDetail.textContent = archDetails[key];
        archDetail.style.opacity = '1';
      } else {
        archDetail.textContent = 'Click a layer to explore how data flows through Nexus.';
        archDetail.style.opacity = '.7';
      }
    });
  });

  // ── Deploy card tilt ──
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    $$('.deploy-card').forEach((card) => {
      card.addEventListener('mousemove', (e) => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(800px) rotateY(${x * 8}deg) rotateX(${-y * 8}deg) translateY(-8px)`;
      });
      card.addEventListener('mouseleave', () => {
        card.style.transform = '';
      });
    });
  }

  // ── Duplicate marquee items when visible ──
  const initMarquees = () => {
    $$('.marquee').forEach((track) => {
      if (track.dataset.cloned) return;
      track.dataset.cloned = '1';
      const items = [...track.children];
      items.forEach((item) => track.appendChild(item.cloneNode(true)));
    });
  };
  const integrationsSection = $('#integrations');
  if (integrationsSection) {
    const marqueeObs = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        initMarquees();
        marqueeObs.disconnect();
      },
      { rootMargin: '80px' }
    );
    marqueeObs.observe(integrationsSection);
  }
})();
