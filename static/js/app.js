let formDirty = false;
let sortableVisualPages = null;
let mobileHeaderCollapsed = false;

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

function openLightbox(url) {
  if (!url) return;
  const modal = document.getElementById('page-lightbox');
  const image = document.getElementById('page-lightbox-image');
  if (!modal || !image) return;
  image.src = url;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeLightbox() {
  const modal = document.getElementById('page-lightbox');
  const image = document.getElementById('page-lightbox-image');
  if (!modal || !image) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  image.src = '';
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

function initEntryNavigator() {
  const root = document.querySelector('[data-entry-navigator]');
  if (!root) return;
  const dataScript = root.querySelector('[data-entry-nav-json]');
  const select = root.querySelector('[data-entry-select]');
  const slider = root.querySelector('[data-entry-slider]');
  const openLink = root.querySelector('[data-entry-open]');
  const date = root.querySelector('[data-entry-date]');
  const pages = root.querySelector('[data-entry-pages]');
  let entries = [];
  try { entries = JSON.parse(dataScript?.textContent || '[]'); } catch { entries = []; }
  if (!entries.length || !select || !slider || !openLink || !date || !pages) return;

  function setEntry(index) {
    const safeIndex = Math.max(0, Math.min(entries.length - 1, Number(index) || 0));
    const entry = entries[safeIndex];
    select.value = String(safeIndex);
    slider.value = String(safeIndex);
    openLink.href = entry.url;
    date.textContent = entry.date;
    pages.textContent = `Page ${entry.page_numbers}${entry.count > 1 ? ` · ${entry.count} pages` : ''}`;
  }

  select.addEventListener('change', () => setEntry(select.value));
  slider.addEventListener('input', () => setEntry(slider.value));
  setEntry(0);
}

document.addEventListener('toggle', (event) => {
  if (event.target.matches('.entry-details')) updateEntrySummary(event.target);
}, true);

document.addEventListener('change', (event) => {
  const toggle = event.target.closest('[data-toggle-target]');
  if (toggle) toggleTarget(toggle);
  if (event.target.closest('#page-edit-form')) formDirty = true;

  if (event.target.matches('input[type="file"][name="cover_photo"], input[type="file"][name="page_image"]')) {
    const form = event.target.closest('[data-cover-upload-form]');
    const saveButton = form?.querySelector('[data-cover-save]');
    if (saveButton) saveButton.classList.toggle('hidden', !event.target.files?.length);
  }

  if (event.target.matches('[data-file-input]')) {
    const form = event.target.closest('[data-scrapbook-upload-form]');
    const label = form?.querySelector('[data-file-label]');
    const filePill = event.target.closest('.file-pill');
    const uploadButton = form?.querySelector('[data-scrapbook-upload-button]');
    const fileName = event.target.files?.[0]?.name || '';
    if (label) label.textContent = fileName ? `Selected: ${fileName}` : 'Add item';
    if (filePill) filePill.classList.toggle('has-file', Boolean(fileName));
    if (uploadButton) uploadButton.disabled = !fileName;
  }

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

  if (event.target.matches('[data-processing-form]')) {
    const modal = document.getElementById('processing-modal');
    if (modal) {
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
    }
    const submitButton = event.target.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = 'Processing…';
    }
  }
});

document.addEventListener('click', (event) => {
  const toggle = event.target.closest('[data-toggle-target]');
  if (toggle && toggle.type !== 'checkbox') toggleTarget(toggle);

  const modalOpen = event.target.closest('[data-modal-open]');
  if (modalOpen) openModal(modalOpen.dataset.modalOpen);

  const modalClose = event.target.closest('[data-modal-close]');
  if (modalClose) closeModal(modalClose.closest('.modal'));

  const lightboxTrigger = event.target.closest('[data-lightbox-src]');
  if (lightboxTrigger) openLightbox(lightboxTrigger.dataset.lightboxSrc);

  const lightboxClose = event.target.closest('[data-lightbox-close]');
  if (lightboxClose) closeLightbox();

  const coverPicker = event.target.closest('[data-cover-picker]');
  if (coverPicker) {
    const input = document.getElementById(coverPicker.dataset.coverPicker);
    if (input) input.click();
  }

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
          <summary>Collapse entry</summary>
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

function updateEntrySummary(details) {
  const summary = details?.querySelector('summary');
  if (summary) summary.textContent = details.open ? 'Collapse entry' : 'Expand entry';
}

function initEntrySummaries() {
  document.querySelectorAll('.entry-details').forEach(updateEntrySummary);
}

window.addEventListener('load', () => {
  initVisualPageSort();
  initEntryNavigator();
  initEntrySummaries();
});

window.addEventListener('beforeunload', (event) => {
  if (!formDirty) return;
  event.preventDefault();
  event.returnValue = '';
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeLightbox();
});

// Toggle for the compact "More" actions on journal overview mobile sticky header
function toggleJournalMore(btn) {
  const container = btn.closest('.mobile-sticky-header');
  const secondary = container ? container.querySelector('#journal-secondary-actions') : null;
  if (!secondary) return;

  const isOpen = secondary.classList.toggle('show');
  btn.textContent = isOpen ? '×' : '⋯';
  btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
}
