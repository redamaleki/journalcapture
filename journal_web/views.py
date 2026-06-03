from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge

from .storage import JournalStore, JOURNAL_MODE_COMPLETE, JOURNAL_MODE_EDITING, journal_is_editing
from . import openrouter_addin

bp = Blueprint('journal', __name__)


def store() -> JournalStore:
    return JournalStore()


def first_uploaded_file(field_name: str):
    for uploaded in request.files.getlist(field_name):
        if uploaded and uploaded.filename:
            return uploaded
    return None


def read_journal_url(journal_id: str, page_slug: str | None = None) -> str:
    url = url_for('journal.read_journal', journal_id=journal_id)
    if page_slug:
        return f'{url}#{page_slug}'
    return url


def journal_overview_url(journal_id: str) -> str:
    return url_for('journal.view_journal', journal_id=journal_id, overview=1)


def redirect_if_not_editing(journal_id: str):
    journal = store().get_journal(journal_id, include_pages=False)
    if journal_is_editing(journal):
        return None
    flash(
        'This journal is complete. Reopen it for editing to add pages, reorder scans, or change images.',
        'error',
    )
    return redirect(read_journal_url(journal_id))


@bp.route('/')
def dashboard():
    journals = store().list_journals()
    return render_template('dashboard.html', journals=journals)


@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    db = store()
    if request.method == 'POST':
        db.save_backup_config({
            'path': request.form.get('path', ''),
            'username': request.form.get('username', ''),
            'password': request.form.get('password', ''),
        })
        flash('Backup settings saved.', 'success')
        return redirect(url_for('journal.settings'))
    return render_template('settings.html', config=db.load_backup_config(), journals=db.list_journals())


@bp.route('/backup/journal/<journal_id>', methods=['POST'])
def backup_journal(journal_id: str):
    try:
        path = store().backup_journal(journal_id)
        flash(f'Journal backed up to {path}', 'success')
    except Exception as exc:
        flash(str(exc), 'error')
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/backup/all', methods=['POST'])
def backup_all():
    try:
        path = store().backup_all()
        flash(f'All journals backed up to {path}', 'success')
    except Exception as exc:
        flash(str(exc), 'error')
    return redirect(url_for('journal.settings'))


@bp.route('/journals/<journal_id>/delete', methods=['POST'])
def delete_journal(journal_id: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    store().delete_journal(journal_id)
    flash('Journal deleted.', 'success')
    return redirect(url_for('journal.dashboard'))


@bp.route('/journals/create', methods=['POST'])
def create_journal():
    journal_id = store().create_journal(
        title=request.form.get('title', 'Untitled Journal').strip(),
        owner=request.form.get('owner', '').strip(),
        description=request.form.get('description', '').strip(),
        has_translation=request.form.get('has_translation') == 'on',
    )
    flash('Journal created.', 'success')
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>/rename', methods=['POST'])
def rename_journal(journal_id: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    next_url = request.form.get('next') or request.referrer or url_for('journal.view_journal', journal_id=journal_id)
    if not title:
        flash('Journal title cannot be empty.', 'error')
        return redirect(next_url)
    store().rename_journal(journal_id, title, description)
    flash('Journal renamed.', 'success')
    return redirect(next_url)


@bp.route('/journals/<journal_id>/upload', methods=['POST'])
def upload_to_journal(journal_id: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    files = [f for f in request.files.getlist('images') if f and f.filename]
    if not files:
        flash('Choose at least one image to upload.', 'error')
        return _redirect_after_upload(journal_id)

    created, errors = db.create_pages_from_uploads(journal_id, files)
    if created:
        flash(f'Uploaded {len(created)} page(s).', 'success')
    if errors:
        flash(f'{len(errors)} file(s) could not be uploaded. Try those images again in a smaller batch or with smaller files.', 'error')
    return _redirect_after_upload(journal_id)


def _redirect_after_upload(journal_id: str):
    """Safely redirect after upload, preferring a 'next' param if it targets this journal."""
    next_url = request.form.get('next') or request.args.get('next')

    if next_url:
        # Basic safety check: must be internal and for this journal
        expected_prefix = f"/journals/{journal_id}"
        if next_url.startswith(expected_prefix):
            return redirect(next_url)

    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>')
def view_journal(journal_id: str):
    db = store()
    journal = db.get_journal(journal_id, include_pages=False)
    if not journal_is_editing(journal) and request.args.get('overview') != '1':
        return redirect(read_journal_url(journal_id))
    sort_mode = request.args.get('sort', 'page')
    pages = db.list_pages_basic(journal_id)

    grouped = {}
    for page in pages:
        for entry in page.get('entries', []) or []:
            entry_date = (entry.get('entry_date') or '').strip()
            if entry_date:
                grouped.setdefault(entry_date, []).append(page)
                break

    entry_nav = []
    for entry_date, entry_pages in sorted(grouped.items()):
        if not entry_pages:
            continue
        first_slug = entry_pages[0]['slug']
        if journal_is_editing(journal):
            entry_url = url_for('journal.edit_page', journal_id=journal_id, page_slug=first_slug)
        else:
            entry_url = read_journal_url(journal_id, first_slug)
        entry_nav.append({
            'date': entry_date,
            'count': len(entry_pages),
            'page_numbers': ', '.join(str(page.get('page_number') or '') for page in entry_pages),
            'url': entry_url,
        })

    if sort_mode == 'date':
        pages = sorted(pages, key=lambda p: (p.get('entry_date') or '9999-99-99', p.get('page_number') or 999999))

    return render_template(
        'journal_view.html',
        journal=journal,
        pages=pages,
        entry_nav=entry_nav,
        sort_mode=sort_mode,
    )


@bp.route('/journals/<journal_id>/organize-scans', methods=['GET', 'POST'])
def organize_scans(journal_id: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    if request.method == 'POST':
        ordered_slugs = [slug for slug in request.form.getlist('page_slug') if slug]
        if ordered_slugs:
            db.reorder_pages(journal_id, ordered_slugs)
            flash('Scan order saved.', 'success')
        return redirect(url_for('journal.view_journal', journal_id=journal_id))
    journal = db.get_journal(journal_id, include_pages=False)
    pages = db.list_pages_basic(journal_id)
    return render_template('organize_scans.html', journal=journal, pages=pages)


@bp.route('/journals/<journal_id>/mode/complete', methods=['POST'])
def mark_journal_complete(journal_id: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    store().set_journal_mode(journal_id, JOURNAL_MODE_COMPLETE)
    flash('Journal marked complete. Pages and images are now view-only.', 'success')
    return redirect(read_journal_url(journal_id))


@bp.route('/journals/<journal_id>/mode/editing', methods=['POST'])
def reopen_journal_editing(journal_id: str):
    journal = store().get_journal(journal_id, include_pages=False)
    if journal_is_editing(journal):
        return redirect(url_for('journal.view_journal', journal_id=journal_id))
    store().set_journal_mode(journal_id, JOURNAL_MODE_EDITING)
    flash('Journal reopened for editing.', 'success')
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>/cover', methods=['POST'])
def upload_cover(journal_id: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    uploaded = first_uploaded_file('cover_photo')
    if uploaded:
        store().save_cover_photo(journal_id, uploaded)
        flash('Cover photo updated.', 'success')
    else:
        flash('Choose a cover photo first.', 'error')
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>/people', methods=['GET', 'POST'])
def add_person(journal_id: str):
    db = store()
    if request.method == 'POST':
        blocked = redirect_if_not_editing(journal_id)
        if blocked:
            return blocked
        name = request.form.get('name', '').strip()
        if name:
            db.add_person(journal_id, name, request.form.get('relation', '').strip(), request.form.get('notes', '').strip())
            flash(f'Added person {name}.', 'success')
        return redirect(url_for('journal.add_person', journal_id=journal_id))
    journal = db.get_journal(journal_id, include_pages=False)
    return render_template('people_manager.html', journal=journal)


@bp.route('/journals/<journal_id>/pages/<page_slug>', methods=['GET', 'POST'])
def edit_page(journal_id: str, page_slug: str):
    db = store()
    if request.method == 'POST':
        blocked = redirect_if_not_editing(journal_id)
        if blocked:
            return blocked
        errors, new_slug = db.save_page(journal_id, page_slug, request.form)
        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            flash('Page saved.', 'success')
            page_slug = new_slug
        if request.headers.get('HX-Request'):
            page = db.get_page(journal_id, page_slug)
            journal = db.get_journal(journal_id, include_pages=False)
            return render_template('partials/save_status.html', page=page, journal=journal)
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))
    journal = db.get_journal(journal_id, include_pages=False)
    if not journal_is_editing(journal):
        return redirect(read_journal_url(journal_id, page_slug))
    page = db.get_page(journal_id, page_slug)
    nav = db.page_navigation(journal_id, page_slug)
    transcribe_enabled = (
        journal_is_editing(journal)
        and bool(current_app.config.get('TRANSCRIBE_TRANSLATE_ENABLED'))
        and openrouter_addin.enabled()
    )
    read_only = not journal_is_editing(journal)
    return render_template(
        'page_editor.html',
        journal=journal,
        page=page,
        nav=nav,
        transcribe_enabled=transcribe_enabled,
        read_only=read_only,
    )


@bp.route('/journals/<journal_id>/pages/<page_slug>/transcribe-translate/preview', methods=['POST'])
def transcribe_translate_preview(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    if not (current_app.config.get('TRANSCRIBE_TRANSLATE_ENABLED') and openrouter_addin.enabled()):
        flash('Transcribe add-in is not configured.', 'error')
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))
    db = store()
    journal = db.get_journal(journal_id, include_pages=False)
    page = db.get_page(journal_id, page_slug)
    image_path = db.page_image_path(journal_id, page_slug)
    if not image_path.exists():
        flash('This page does not have an image to transcribe.', 'error')
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))
    previous_date_text = request.form.get('previous_date_text', '').strip()
    journal_year = request.form.get('journal_year', '').strip()
    create_adjusted = request.form.get('create_adjusted_image') == 'on'
    try:
        result = openrouter_addin.transcribe_page(
            image_path,
            previous_date_text=previous_date_text,
            journal_year=journal_year,
            include_translation=bool(journal.get('has_translation')),
            ocr_settings=journal.get('ocr_settings') if journal.get('advanced_prompt_tuning_enabled') else None,
            translation_settings=journal.get('translation_settings') if journal.get('advanced_prompt_tuning_enabled') else None,
        )
        adjusted = openrouter_addin.create_adjusted_image(image_path) if create_adjusted else None
        adjusted_artifact_name = ''
        if adjusted and adjusted.get('data_url'):
            artifact_dir = current_app.config['DATA_DIR'] / 'transcribe_artifacts'
            artifact_dir.mkdir(parents=True, exist_ok=True)
            adjusted_artifact_name = f'{uuid4().hex}.jpg'
            (artifact_dir / adjusted_artifact_name).write_bytes(openrouter_addin.decode_data_url(adjusted['data_url']))
            adjusted['artifact_name'] = adjusted_artifact_name
    except Exception as exc:
        flash(str(exc), 'error')
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))
    return render_template(
        'transcribe_preview.html',
        journal=journal,
        page=page,
        result=result,
        adjusted=adjusted,
        previous_date_text=previous_date_text,
        journal_year=journal_year,
    )


@bp.route('/journals/<journal_id>/pages/<page_slug>/transcribe-translate/accept', methods=['POST'])
def transcribe_translate_accept(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    entries = []
    dates = request.form.getlist('entry_date')
    transcriptions = request.form.getlist('entry_transcription')
    translations = request.form.getlist('entry_translation')
    notes = request.form.getlist('entry_notes')
    total = max(len(dates), len(transcriptions), len(translations), len(notes), 0)
    for idx in range(total):
        entries.append({
            'entry_date': dates[idx] if idx < len(dates) else '',
            'transcription': transcriptions[idx] if idx < len(transcriptions) else '',
            'translation': translations[idx] if idx < len(translations) else '',
            'notes': notes[idx] if idx < len(notes) else '',
        })
    adjusted_bytes = None
    artifact_name = request.form.get('adjusted_artifact_name', '').strip()
    if artifact_name and ('/' in artifact_name or '\\' in artifact_name or not artifact_name.endswith('.jpg')):
        flash('Invalid adjusted image artifact.', 'error')
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))
    artifact_path = current_app.config['DATA_DIR'] / 'transcribe_artifacts' / artifact_name if artifact_name else None
    if request.form.get('replace_with_adjusted_image') == 'on' and artifact_path:
        try:
            adjusted_bytes = artifact_path.read_bytes()
        except Exception as exc:
            flash(f'Could not load adjusted image: {exc}', 'error')
            return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))
    db.apply_transcribed_entries(journal_id, page_slug, entries, adjusted_image_bytes=adjusted_bytes)
    if artifact_path and artifact_path.exists():
        artifact_path.unlink()
    journal = db.get_journal(journal_id, include_pages=False)
    action = "Transcription and translation" if journal.get('has_translation') else "Transcription"
    flash(f'{action} accepted.', 'success')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/pages/<page_slug>/autosave', methods=['POST'])
def autosave_page(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    errors, new_slug = db.save_page(journal_id, page_slug, request.form)
    page = db.get_page(journal_id, new_slug)
    journal = db.get_journal(journal_id, include_pages=False)
    if errors:
        return render_template('partials/save_status.html', page=page, journal=journal, errors=errors), 400
    return render_template('partials/save_status.html', page=page, journal=journal, autosaved=True)


@bp.route('/journals/<journal_id>/pages/<page_slug>/delete', methods=['POST'])
def delete_page(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    nav = db.page_navigation(journal_id, page_slug)
    db.delete_page(journal_id, page_slug)
    flash('Page deleted.', 'success')
    if nav.get('prev'):
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=nav['prev']['slug']))
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>/pages/<page_slug>/image', methods=['POST'])
def replace_page_image(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    uploaded = first_uploaded_file('page_image')
    if uploaded:
        store().replace_page_image(journal_id, page_slug, uploaded)
        flash('Page image updated.', 'success')
    else:
        flash('Choose a page image first.', 'error')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/pages/<page_slug>/scrapbook', methods=['POST'])
def add_scrapbook_item(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    uploaded = request.files.get('scrapbook_image')
    if uploaded and uploaded.filename:
        store().add_scrapbook_item(journal_id, page_slug, uploaded)
        flash('Scrapbook item added.', 'success')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/pages/<page_slug>/scrapbook/remove', methods=['POST'])
def remove_scrapbook_item(journal_id: str, page_slug: str):
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    filename = request.form.get('filename', '')
    store().remove_scrapbook_item(journal_id, page_slug, filename)
    flash('Scrapbook item removed.', 'success')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/assets/<path:filename>')
def page_asset(journal_id: str, filename: str):
    # Read-only page/scrapbook asset access. send_from_directory keeps requests
    # inside the journal's pages directory and avoids path traversal.
    directory = current_app.config['JOURNALS_DIR'] / journal_id / 'pages'
    return send_from_directory(directory, filename)


@bp.route('/journals/<journal_id>/cover-photo')
def cover_asset(journal_id: str):
    journal_dir = current_app.config['JOURNALS_DIR'] / journal_id
    cover_name = store().get_journal_meta(journal_id).get('cover_photo') or ''
    if not cover_name or '/' in cover_name or '\\' in cover_name:
        return ('Not found', 404)
    return send_from_directory(journal_dir, cover_name)


@bp.route('/thumbnails/<journal_id>/<path:filename>')
def thumbnail(journal_id: str, filename: str):
    path = current_app.config['THUMBS_DIR'] / journal_id / filename
    return send_file(path)



@bp.route('/journals/<journal_id>/read')
def read_journal(journal_id: str):
    db = store()
    journal = db.get_journal(journal_id)
    if journal.get('cover_photo'):
        journal['cover_url'] = url_for('journal.cover_asset', journal_id=journal_id)

    # Flatten fresh entries from all pages, keeping track of page origin. This
    # also lets the read-only reader summarize the date range without writing
    # anything back to the journal directory.
    all_entries = []
    for page in journal['pages']:
        page_entries = page.get('entries') or []
        if not page_entries and any((page.get('entry_date'), page.get('transcription'), page.get('translation'), page.get('notes'))):
            page_entries = [{
                'entry_date': page.get('entry_date', ''),
                'transcription': page.get('transcription', ''),
                'translation': page.get('translation', ''),
                'notes': page.get('notes', ''),
            }]
        for entry in page_entries:
            all_entries.append({
                **entry,
                'page_slug': page['slug'],
                'page_number': page['page_number'],
                'page_image_url': page.get('image_url'),
                'scrapbook_urls': page.get('scrapbook_urls', []),
            })

    # Sort by date, fallback to page number.
    sorted_entries = sorted(all_entries, key=lambda e: (e.get('entry_date') or '9999-99-99', e.get('page_number') or 0))
    dated_entries = [entry.get('entry_date') for entry in sorted_entries if entry.get('entry_date')]
    date_range = ''
    if dated_entries:
        date_range = dated_entries[0] if dated_entries[0] == dated_entries[-1] else f'{dated_entries[0]} – {dated_entries[-1]}'

    response = make_response(render_template(
        'read_journal.html',
        journal=journal,
        entries=sorted_entries,
        date_range=date_range,
        dashboard_url=url_for('journal.dashboard'),
    ))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response



# =============================================================================
# Per-Journal Prompt Tuning (Advanced)
# =============================================================================

@bp.route('/journals/<journal_id>/prompt-tuning', methods=['GET', 'POST'])
def prompt_tuning(journal_id: str):
    db = store()
    journal = db.get_journal(journal_id, include_pages=False)

    if request.method == 'POST':
        blocked = redirect_if_not_editing(journal_id)
        if blocked:
            return blocked
        enabled = True

        ocr_settings = {
            'custom_instructions': request.form.get('ocr_custom_instructions', ''),
            'date_and_structure_hints': request.form.get('ocr_date_and_structure_hints', ''),
        }
        translation_settings = {
            'custom_instructions': request.form.get('translation_custom_instructions', ''),
            'terminology_and_style_notes': request.form.get('translation_terminology_and_style_notes', ''),
        }
        tuning_desc = request.form.get('prompt_tuning_description', '') or request.form.get('description', '')
        if not tuning_desc:
            tuning_desc = journal.get('prompt_tuning_description', '')

        db.save_prompt_tuning(journal_id, enabled, ocr_settings, translation_settings, tuning_desc)
        flash('Prompt tuning settings saved.', 'success')
        return redirect(url_for('journal.prompt_tuning', journal_id=journal_id))

    # GET: show current values
    return render_template(
        'prompt_tuning.html',
        journal=journal,
        ocr_settings=journal.get('ocr_settings', {}),
        translation_settings=journal.get('translation_settings', {}),
        advanced_enabled=journal.get('advanced_prompt_tuning_enabled', False),
    )


@bp.route('/journals/<journal_id>/prompt-tuning/help-me-tune', methods=['POST'])
def prompt_tuning_help_me_tune(journal_id: str):
    """Call the translation model to suggest values for the four tuning fields."""
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    journal = db.get_journal(journal_id, include_pages=False)

    user_description = request.form.get('description', '').strip()

    title = journal.get('title', '')
    existing_desc = journal.get('description', '')

    try:
        suggestions = openrouter_addin.generate_prompt_tuning_suggestions(
            title=title,
            description=existing_desc,
            user_description=user_description,
        )

        # Save suggestions directly as the current settings (as a draft the user can review/edit).
        # This avoids brittle long query strings in the URL and browser history.
        db.save_prompt_tuning(
            journal_id,
            journal.get('advanced_prompt_tuning_enabled', False),
            {
                'custom_instructions': suggestions.get('ocr_custom_instructions', ''),
                'date_and_structure_hints': suggestions.get('ocr_date_and_structure_hints', ''),
            },
            {
                'custom_instructions': suggestions.get('translation_custom_instructions', ''),
                'terminology_and_style_notes': suggestions.get('translation_terminology_and_style_notes', ''),
            },
            user_description
        )

        flash('Suggestions generated and loaded below. Review and adjust, then Save Tuning Settings.', 'success')
        return redirect(url_for('journal.prompt_tuning', journal_id=journal_id))

    except Exception as exc:
        flash(f'Could not generate suggestions: {exc}', 'error')
        return redirect(url_for('journal.prompt_tuning', journal_id=journal_id))



@bp.route('/journals/<journal_id>/toggle-advanced', methods=['POST'])
def toggle_advanced_prompt_tuning(journal_id: str):
    """Quick toggle for Advanced Prompt Tuning from the dashboard."""
    blocked = redirect_if_not_editing(journal_id)
    if blocked:
        return blocked
    db = store()
    journal = db.get_journal(journal_id, include_pages=False)
    current = bool(journal.get('advanced_prompt_tuning_enabled'))
    new_state = not current

    # Preserve existing settings
    db.save_prompt_tuning(
        journal_id,
        new_state,
        journal.get('ocr_settings', {}),
        journal.get('translation_settings', {}),
        journal.get('prompt_tuning_description', '')
    )
    flash(f'Advanced Prompt Tuning {"enabled" if new_state else "disabled"} for this journal.', 'success')
    return redirect(request.referrer or url_for('journal.dashboard'))


@bp.errorhandler(RequestEntityTooLarge)
def upload_too_large(error):
    flash('That upload was too large for one request. Try fewer images at once, or reduce the image size.', 'error')
    return redirect(request.referrer or url_for('journal.dashboard'))


@bp.route('/healthz')
def healthz():
    return jsonify({'ok': True})
