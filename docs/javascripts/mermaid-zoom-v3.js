(() => {
  const DIALOG_ID = 'sod-mermaid-zoom-dialog-v3';
  const MIN_SCALE = 0.5;
  const MAX_SCALE = 3;
  const STEP = 0.2;

  let dialog;
  let viewport;
  let canvas;
  let zoomLabel;
  let scale = 1.35;
  let baseWidth = 0;
  let baseHeight = 0;

  function clamp(value) {
    return Math.max(MIN_SCALE, Math.min(MAX_SCALE, value));
  }

  function ensureDialog() {
    if (dialog) return;

    dialog = document.createElement('dialog');
    dialog.id = DIALOG_ID;
    dialog.className = 'sod-zoom-dialog-v3';
    dialog.innerHTML = `
      <div class="sod-zoom-shell-v3">
        <div class="sod-zoom-toolbar-v3">
          <span class="sod-zoom-title-v3">Diagrama ampliado</span>
          <div class="sod-zoom-actions-v3">
            <button type="button" data-action="out" aria-label="Diminuir zoom">−</button>
            <span class="sod-zoom-label-v3" aria-live="polite">135%</span>
            <button type="button" data-action="in" aria-label="Aumentar zoom">+</button>
            <button type="button" data-action="reset">Reset</button>
            <button type="button" data-action="close">Fechar</button>
          </div>
        </div>
        <div class="sod-zoom-viewport-v3">
          <div class="sod-zoom-canvas-v3"></div>
        </div>
      </div>`;

    document.body.appendChild(dialog);
    viewport = dialog.querySelector('.sod-zoom-viewport-v3');
    canvas = dialog.querySelector('.sod-zoom-canvas-v3');
    zoomLabel = dialog.querySelector('.sod-zoom-label-v3');

    dialog.addEventListener('click', (event) => {
      const action = event.target?.dataset?.action;
      if (!action) return;

      if (action === 'in') setScale(scale + STEP);
      if (action === 'out') setScale(scale - STEP);
      if (action === 'reset') setScale(1.35);
      if (action === 'close') dialog.close();
    });

    dialog.addEventListener('close', () => {
      if (canvas) canvas.innerHTML = '';
      document.body.classList.remove('sod-no-scroll');
    });

    dialog.addEventListener('cancel', () => {
      document.body.classList.remove('sod-no-scroll');
    });

    viewport.addEventListener(
      'wheel',
      (event) => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        setScale(scale + (event.deltaY < 0 ? STEP : -STEP));
      },
      { passive: false }
    );
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

    if (zoomLabel) {
      zoomLabel.textContent = `${Math.round(scale * 100)}%`;
    }
  }

  function openDiagram(diagram) {
    const sourceSvg = diagram.querySelector('svg');
    if (!sourceSvg) return;

    ensureDialog();

    const rect = sourceSvg.getBoundingClientRect();
    const viewBox = sourceSvg.viewBox?.baseVal;

    baseWidth = Math.max(
      rect.width || 0,
      viewBox?.width || 0,
      640
    );

    baseHeight = Math.max(
      rect.height || 0,
      viewBox?.height || 0,
      320
    );

    const clone = sourceSvg.cloneNode(true);
    clone.removeAttribute('style');
    clone.style.width = `${baseWidth}px`;
    clone.style.height = `${baseHeight}px`;

    canvas.innerHTML = '';
    canvas.appendChild(clone);

    scale = 1.35;
    setScale(scale);

    viewport.scrollTop = 0;
    viewport.scrollLeft = 0;

    if (!dialog.open) {
      dialog.showModal();
    }

    document.body.classList.add('sod-no-scroll');
    dialog.querySelector('[data-action="close"]')?.focus();
  }

  function decorateDiagrams() {
    document.querySelectorAll('.mermaid').forEach((diagram) => {
      diagram.classList.add('sod-mermaid-zoomable-v3');
      diagram.setAttribute('role', 'button');
      diagram.setAttribute('tabindex', '0');
      diagram.setAttribute('aria-label', 'Abrir diagrama ampliado');
      diagram.title = 'Clique para ampliar o diagrama';
    });
  }

  document.addEventListener(
    'click',
    (event) => {
      const diagram = event.target?.closest?.('.mermaid');
      if (!diagram) return;
      if (dialog?.contains(event.target)) return;
      if (window.getSelection()?.toString()) return;

      event.preventDefault();
      event.stopPropagation();
      openDiagram(diagram);
    },
    true
  );

  document.addEventListener('keydown', (event) => {
    if (dialog?.open) {
      if (event.key === '+' || event.key === '=') {
        event.preventDefault();
        setScale(scale + STEP);
      } else if (event.key === '-') {
        event.preventDefault();
        setScale(scale - STEP);
      } else if (event.key === '0') {
        event.preventDefault();
        setScale(1.35);
      }
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

  const observer = new MutationObserver(decorateDiagrams);

  function start() {
    decorateDiagrams();
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
