(() => {
  let modal;
  let stage;
  let canvas;
  let label;
  let scale = 1;
  let baseWidth = 0;
  let baseHeight = 0;
  let lastFocus = null;

  const MIN_SCALE = 0.4;
  const MAX_SCALE = 3;
  const STEP = 0.2;

  function clamp(value) {
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
  }

  function ensureModal() {
    if (modal) return;

    modal = document.createElement('div');
    modal.className = 'sod-mermaid-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Visualização ampliada do diagrama');
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML = `
      <div class="sod-mermaid-toolbar">
        <button type="button" data-action="out" aria-label="Diminuir zoom">−</button>
        <span class="sod-mermaid-zoom-label" aria-live="polite">100%</span>
        <button type="button" data-action="in" aria-label="Aumentar zoom">+</button>
        <button type="button" data-action="reset">Reset</button>
        <button type="button" data-action="close">Fechar</button>
      </div>
      <div class="sod-mermaid-stage">
        <div class="sod-mermaid-canvas"></div>
      </div>`;

    document.body.appendChild(modal);
    stage = modal.querySelector('.sod-mermaid-stage');
    canvas = modal.querySelector('.sod-mermaid-canvas');
    label = modal.querySelector('.sod-mermaid-zoom-label');

    modal.addEventListener('click', (event) => {
      const action = event.target?.dataset?.action;
      if (action === 'in') setScale(scale + STEP);
      if (action === 'out') setScale(scale - STEP);
      if (action === 'reset') setScale(1);
      if (action === 'close') closeModal();
    });

    stage.addEventListener(
      'wheel',
      (event) => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        setScale(scale + (event.deltaY < 0 ? STEP : -STEP));
      },
      { passive: false }
    );
  }

  function getSvgSize(svg) {
    const viewBox = (svg.getAttribute('viewBox') || '')
      .trim()
      .split(/[ ,]+/)
      .map(Number);

    if (
      viewBox.length === 4 &&
      viewBox.every(Number.isFinite) &&
      viewBox[2] > 0 &&
      viewBox[3] > 0
    ) {
      return { width: viewBox[2], height: viewBox[3] };
    }

    const rect = svg.getBoundingClientRect();
    return {
      width: Math.max(rect.width || 0, 320),
      height: Math.max(rect.height || 0, 180),
    };
  }

  function setScale(next) {
    if (!canvas) return;

    scale = clamp(next);
    const svg = canvas.querySelector('svg');

    canvas.style.width = `${baseWidth * scale}px`;
    canvas.style.height = `${baseHeight * scale}px`;

    if (svg) {
      svg.style.transform = `scale(${scale})`;
    }

    if (label) {
      label.textContent = `${Math.round(scale * 100)}%`;
    }
  }

  function openDiagram(diagram) {
    const svg = diagram.querySelector('svg');

    if (!svg) {
      window.setTimeout(() => {
        const renderedSvg = diagram.querySelector('svg');
        if (renderedSvg) openDiagram(diagram);
      }, 250);
      return;
    }

    ensureModal();
    lastFocus = document.activeElement;

    const clone = svg.cloneNode(true);
    const size = getSvgSize(svg);

    baseWidth = size.width;
    baseHeight = size.height;

    clone.removeAttribute('style');
    clone.style.width = `${baseWidth}px`;
    clone.style.height = `${baseHeight}px`;

    canvas.innerHTML = '';
    canvas.appendChild(clone);

    scale = 1;
    setScale(1);

    stage.scrollTop = 0;
    stage.scrollLeft = 0;

    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('sod-no-scroll');

    modal.querySelector('[data-action="close"]')?.focus();
  }

  function closeModal() {
    if (!modal) return;

    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('sod-no-scroll');
    canvas.innerHTML = '';

    if (lastFocus && typeof lastFocus.focus === 'function') {
      lastFocus.focus();
    }
  }

  function decorate() {
    document.querySelectorAll('.mermaid').forEach((diagram) => {
      diagram.classList.add('sod-mermaid-zoomable');
      diagram.title = 'Clique para ampliar o diagrama';
      diagram.setAttribute('role', 'button');
      diagram.setAttribute('tabindex', '0');
      diagram.setAttribute('aria-label', 'Clique para ampliar o diagrama');
    });
  }

  document.addEventListener(
    'click',
    (event) => {
      if (modal?.contains(event.target)) return;

      const diagram = event.target?.closest?.('.mermaid');
      if (!diagram) return;
      if (window.getSelection()?.toString()) return;

      event.preventDefault();
      openDiagram(diagram);
    },
    true
  );

  document.addEventListener('keydown', (event) => {
    const modalOpen = modal?.classList.contains('is-open');

    if (modalOpen) {
      if (event.key === 'Escape') closeModal();
      if (event.key === '+' || event.key === '=') setScale(scale + STEP);
      if (event.key === '-') setScale(scale - STEP);
      if (event.key === '0') setScale(1);
      return;
    }

    if (
      (event.key === 'Enter' || event.key === ' ') &&
      document.activeElement?.matches?.('.mermaid')
    ) {
      event.preventDefault();
      openDiagram(document.activeElement);
    }
  });

  const observer = new MutationObserver(() => decorate());

  function start() {
    decorate();

    if (document.body) {
      observer.observe(document.body, {
        childList: true,
        subtree: true,
      });
    }
  }

  if (typeof document$ !== 'undefined') {
    document$.subscribe(() => {
      window.setTimeout(start, 0);
      window.setTimeout(decorate, 300);
    });
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
