(() => {
  let modal;
  let stage;
  let label;
  let scale = 1;

  function ensureModal() {
    if (modal) return;
    modal = document.createElement('div');
    modal.className = 'sod-mermaid-modal';
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML = `
      <div class="sod-mermaid-toolbar">
        <button type="button" data-action="out" aria-label="Diminuir zoom">−</button>
        <span class="sod-mermaid-zoom-label">100%</span>
        <button type="button" data-action="in" aria-label="Aumentar zoom">+</button>
        <button type="button" data-action="reset">Reset</button>
        <button type="button" data-action="close">Fechar</button>
      </div>
      <div class="sod-mermaid-stage"></div>`;
    document.body.appendChild(modal);
    stage = modal.querySelector('.sod-mermaid-stage');
    label = modal.querySelector('.sod-mermaid-zoom-label');

    modal.addEventListener('click', (event) => {
      const action = event.target?.dataset?.action;
      if (action === 'in') setScale(Math.min(3, scale + 0.2));
      if (action === 'out') setScale(Math.max(0.4, scale - 0.2));
      if (action === 'reset') setScale(1);
      if (action === 'close') closeModal();
      if (event.target === modal) closeModal();
    });

    document.addEventListener('keydown', (event) => {
      if (!modal.classList.contains('is-open')) return;
      if (event.key === 'Escape') closeModal();
      if (event.key === '+' || event.key === '=') setScale(Math.min(3, scale + 0.2));
      if (event.key === '-') setScale(Math.max(0.4, scale - 0.2));
      if (event.key === '0') setScale(1);
    });
  }

  function setScale(next) {
    scale = next;
    const svg = stage?.querySelector('svg');
    if (svg) svg.style.transform = `scale(${scale})`;
    if (label) label.textContent = `${Math.round(scale * 100)}%`;
  }

  function openDiagram(diagram) {
    const svg = diagram.querySelector('svg');
    if (!svg) return;
    ensureModal();
    stage.innerHTML = '';
    const clone = svg.cloneNode(true);
    clone.removeAttribute('style');
    stage.appendChild(clone);
    scale = 1;
    setScale(1);
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('sod-no-scroll');
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('sod-no-scroll');
    stage.innerHTML = '';
  }

  function bind() {
    document.querySelectorAll('.mermaid').forEach((diagram) => {
      if (diagram.dataset.sodZoomBound === 'true') return;
      diagram.dataset.sodZoomBound = 'true';
      diagram.classList.add('sod-mermaid-zoomable');
      diagram.title = 'Clique para ampliar o diagrama';
      diagram.addEventListener('click', (event) => {
        if (window.getSelection()?.toString()) return;
        event.preventDefault();
        openDiagram(diagram);
      });
    });
  }

  if (typeof document$ !== 'undefined') {
    document$.subscribe(() => window.setTimeout(bind, 150));
  } else {
    document.addEventListener('DOMContentLoaded', () => window.setTimeout(bind, 150));
  }
})();
