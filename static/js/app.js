let formDirty = false;
let sortableVisualPages = null;

function toggleTarget(trigger) {
  const target = document.querySelector(trigger.dataset.toggleTarget);
  if (!target) return;
  if (trigger.type === 'checkbox') {
    target.classList.toggle('hidden', !trigger.checked);
  } else {
    target.classList.toggle('hidden');
  }
}

function openModal(selector) {
  const modal = document.querySelector(selector);
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeModal(modal) {
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function initVisualPageSort() {
  const strip = document.getElementById('visual-page-strip');
  if (!strip || typeof Sortable === 'undefined') return;
  if (sortableVisualPages) sortableVisualPages.destroy();
  sortableVisualPages = Sortable.create(strip, {
    animation: 150,
    draggable: '.visual-page-tile',
    delay: window.innerWidth <= 640 ? 180 : 0,
    delayOnTouchOnly: true,
    touchStartThreshold: 8
  });
}

document.addEventListener('change', (event) => {
  const toggle = event.target.closest('[data-toggle-target]');
  if (toggle) toggleTarget(toggle);
  if (event.target.closest('#page-edit-form')) formDirty = true;

  if (event.target.matches('.entry-date-input')) {
    const block = event.target.closest('.entry-block');
    const chip = block?.querySelector('.entry-date-chip');
    if (chip) {
      if (event.target.value) {
        chip.textContent = event.target.value;
        chip.classList.remove('hidden');
      } else {
        chip.textContent = '';
        chip.classList.add('hidden');
      }
    } else if (event.target.value && block) {
      const chipWrap = block.querySelector('.entry-chip-wrap');
      if (chipWrap) {
        const newChip = document.createElement('span');
        newChip.className = 'entry-date-chip';
        newChip.textContent = event.target.value;
        chipWrap.appendChild(newChip);
      }
    }
  }
});

document.addEventListener('input', (event) => {
  if (event.target.closest('#page-edit-form')) formDirty = true;
});

document.addEventListener('submit', (event) => {
  if (event.target.id === 'page-edit-form') formDirty = false;
});

document.addEventListener('click', (event) => {
  const toggle = event.target.closest('[data-toggle-target]');
  if (toggle && toggle.type !== 'checkbox') toggleTarget(toggle);

  const modalOpen = event.target.closest('[data-modal-open]');
  if (modalOpen) openModal(modalOpen.dataset.modalOpen);

  const modalClose = event.target.closest('[data-modal-close]');
  if (modalClose) closeModal(modalClose.closest('.modal'));

  const suggestion = event.target.closest('.fill-suggestion');
  if (suggestion) {
    const target = document.querySelector(suggestion.dataset.target);
    if (target) {
      target.value = suggestion.dataset.value;
      target.dispatchEvent(new Event('change', { bubbles: true }));
      formDirty = true;
    }
  }

  if (event.target.id === 'add-entry-btn') {
    const container = document.getElementById('entries-container');
    if (container) {
      const entryCount = container.querySelectorAll('.entry-block').length + 1;
      const hasTranslation = !container.querySelector('input[name="entry_translation"][type="hidden"]');
      const defaultDate = event.target.dataset.defaultDate || '';
      const block = document.createElement('article');
      block.className = 'entry-block simple-entry-block';
      block.dataset.entryIndex = String(entryCount);
      block.innerHTML = `
        <div class="entry-block-header row-between wrap gap-sm">
          <div class="entry-chip-wrap">
            <span class="entry-chip">Entry ${entryCount}</span>
            ${defaultDate ? `<span class="entry-date-chip">${defaultDate}</span>` : ''}
          </div>
          <button type="button" class="text-link-btn remove-entry-btn">Remove</button>
        </div>
        <label>Date<input type="date" class="entry-date-input" name="entry_date" value="${defaultDate}"></label>
        <details class="entry-details" open>
          <summary>Edit entry</summary>
          <div class="stack entry-details-body">
            ${hasTranslation ? '<label>Translation<textarea name="entry_translation" rows="5"></textarea></label>' : '<input type="hidden" name="entry_translation" value="">'}
            <label>Transcription<textarea name="entry_transcription" rows="6"></textarea></label>
            <label>Comments<textarea name="entry_notes" rows="3"></textarea></label>
          </div>
        </details>
      `;
      container.appendChild(block);
      const dateInput = block.querySelector('.entry-date-input');
      if (dateInput) dateInput.focus();
      formDirty = true;
    }
  }

  const removeEntry = event.target.closest('.remove-entry-btn');
  if (removeEntry) {
    const block = removeEntry.closest('.entry-block');
    if (block) {
      block.remove();
      document.querySelectorAll('#entries-container .entry-block').forEach((entryBlock, index) => {
        const chip = entryBlock.querySelector('.entry-chip');
        if (chip) chip.textContent = `Entry ${index + 1}`;
      });
      formDirty = true;
    }
  }

  const nav = event.target.closest('.guarded-nav');
  if (nav && formDirty) {
    const ok = confirm('You have unsaved changes. If you leave this page now, those changes will be lost. Continue?');
    if (!ok) event.preventDefault();
    else formDirty = false;
  }
});

if (window.location.hash === '#add-pages-modal') {
  openModal('#add-pages-modal');
}

function updateScrolledState() {
  document.body.classList.toggle('scrolled', window.scrollY > 56);
}

window.addEventListener('scroll', updateScrolledState, { passive: true });
window.addEventListener('load', () => {
  updateScrolledState();
  initVisualPageSort();
});

window.addEventListener('beforeunload', (event) => {
  if (!formDirty) return;
  event.preventDefault();
  event.returnValue = '';
});
