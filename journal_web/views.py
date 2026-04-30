from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from .storage import JournalStore

bp = Blueprint('journal', __name__)


def store() -> JournalStore:
    return JournalStore()


def first_uploaded_file(field_name: str):
    for uploaded in request.files.getlist(field_name):
        if uploaded and uploaded.filename:
            return uploaded
    return None


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
    db = store()
    files = [f for f in request.files.getlist('images') if f and f.filename]
    if not files:
        flash('Choose at least one image to upload.', 'error')
        return redirect(url_for('journal.view_journal', journal_id=journal_id))
    for uploaded in files:
        db.create_page_from_upload(journal_id, uploaded)
    flash(f'Uploaded {len(files)} page(s).', 'success')
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>')
def view_journal(journal_id: str):
    db = store()
    journal = db.get_journal(journal_id)
    sort_mode = request.args.get('sort', 'page')
    view_mode = request.args.get('view', 'visual')
    pages = journal['pages']
    if sort_mode == 'date':
        pages = sorted(pages, key=lambda p: (p.get('entry_date') or '9999-99-99', p.get('page_number') or 999999))
    return render_template('journal_view.html', journal=journal, pages=pages, sort_mode=sort_mode, view_mode=view_mode)


@bp.route('/journals/<journal_id>/reorder', methods=['POST'])
def reorder_pages(journal_id: str):
    ordered_slugs = [slug for slug in request.form.getlist('page_slug') if slug]
    if ordered_slugs:
        store().reorder_pages(journal_id, ordered_slugs)
        flash('Page order updated.', 'success')
    return redirect(url_for('journal.view_journal', journal_id=journal_id, view='visual'))


@bp.route('/journals/<journal_id>/cover', methods=['POST'])
def upload_cover(journal_id: str):
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
    journal = db.get_journal(journal_id)
    page = db.get_page(journal_id, page_slug)
    nav = db.page_navigation(journal_id, page_slug)
    return render_template('page_editor.html', journal=journal, page=page, nav=nav)


@bp.route('/journals/<journal_id>/pages/<page_slug>/autosave', methods=['POST'])
def autosave_page(journal_id: str, page_slug: str):
    db = store()
    errors, new_slug = db.save_page(journal_id, page_slug, request.form)
    page = db.get_page(journal_id, new_slug)
    journal = db.get_journal(journal_id, include_pages=False)
    if errors:
        return render_template('partials/save_status.html', page=page, journal=journal, errors=errors), 400
    return render_template('partials/save_status.html', page=page, journal=journal, autosaved=True)


@bp.route('/journals/<journal_id>/pages/<page_slug>/delete', methods=['POST'])
def delete_page(journal_id: str, page_slug: str):
    db = store()
    nav = db.page_navigation(journal_id, page_slug)
    db.delete_page(journal_id, page_slug)
    flash('Page deleted.', 'success')
    if nav.get('prev'):
        return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=nav['prev']['slug']))
    return redirect(url_for('journal.view_journal', journal_id=journal_id))


@bp.route('/journals/<journal_id>/pages/<page_slug>/image', methods=['POST'])
def replace_page_image(journal_id: str, page_slug: str):
    uploaded = first_uploaded_file('page_image')
    if uploaded:
        store().replace_page_image(journal_id, page_slug, uploaded)
        flash('Page image updated.', 'success')
    else:
        flash('Choose a page image first.', 'error')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/pages/<page_slug>/scrapbook', methods=['POST'])
def add_scrapbook_item(journal_id: str, page_slug: str):
    uploaded = request.files.get('scrapbook_image')
    if uploaded and uploaded.filename:
        store().add_scrapbook_item(journal_id, page_slug, uploaded)
        flash('Scrapbook item added.', 'success')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/pages/<page_slug>/scrapbook/remove', methods=['POST'])
def remove_scrapbook_item(journal_id: str, page_slug: str):
    filename = request.form.get('filename', '')
    store().remove_scrapbook_item(journal_id, page_slug, filename)
    flash('Scrapbook item removed.', 'success')
    return redirect(url_for('journal.edit_page', journal_id=journal_id, page_slug=page_slug))


@bp.route('/journals/<journal_id>/assets/<path:filename>')
def page_asset(journal_id: str, filename: str):
    path = current_app.config['JOURNALS_DIR'] / journal_id / 'pages' / filename
    return send_file(path)


@bp.route('/thumbnails/<journal_id>/<path:filename>')
def thumbnail(journal_id: str, filename: str):
    path = current_app.config['THUMBS_DIR'] / journal_id / filename
    return send_file(path)


@bp.route('/healthz')
def healthz():
    return jsonify({'ok': True})
