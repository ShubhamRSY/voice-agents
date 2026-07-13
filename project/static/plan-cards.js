/** Click-to-select glow on pricing / deploy plan cards (landing + pricing pages). */
(function () {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const initPlanCards = (gridSelector, cardSelector) => {
    const grid = $(gridSelector);
    if (!grid) return;
    const cards = $$(cardSelector, grid);
    if (!cards.length) return;

    const syncCard = (card, active) => {
      card.classList.toggle('featured', active);
      card.setAttribute('aria-pressed', active ? 'true' : 'false');

      const btn = card.querySelector('.pricing-btn');
      if (btn) {
        btn.classList.toggle('btn-primary', active);
        btn.classList.toggle('btn-ghost', !active);
      }

      const amount = card.querySelector('.pricing-amount, .deploy-price');
      if (amount && amount.classList.contains('enquire')) {
        const keepAccent = active && !amount.classList.contains('warm') && !amount.classList.contains('free');
        amount.classList.toggle('accent', keepAccent);
      }
    };

    const selectCard = (card) => {
      cards.forEach((c) => syncCard(c, c === card));
    };

    cards.forEach((card) => {
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');

      card.addEventListener('click', (e) => {
        if (e.target.closest('a')) return;
        selectCard(card);
      });

      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          selectCard(card);
        }
      });
    });

    const planParam = new URLSearchParams(window.location.search).get('plan');
    const fromParam = planParam && cards.find((c) => c.dataset.plan === planParam);
    const initial = fromParam || cards.find((c) => c.classList.contains('featured')) || cards[0];
    selectCard(initial);
  };

  initPlanCards('.pricing-grid', '.pricing-card');
  initPlanCards('.deploy-grid', '.deploy-card');
})();
