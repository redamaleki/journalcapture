import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from PIL import Image, ImageOps


PAGE_RE = re.compile(r'^page-(\d{3})$')


def load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ''
    text = path.read_text(encoding='utf-8')
    if not text.strip():
        return {}, ''
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            data = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip('\n')
            return data, body
    data = yaml.safe_load(text) or {}
    return data, ''


def dump_frontmatter(data: dict[str, Any], body: str = '') -> str:
    yaml_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    content = f"---\n{yaml_text}---\n"
    if body:
        content += body.rstrip() + '\n'
    return content


def save_frontmatter(path: Path, data: dict[str, Any], body: str = '') -> None:
    path.write_text(dump_frontmatter(data, body), encoding='utf-8')


def save_yaml_only(path: Path, data: dict[str, Any]) -> None:
    yaml_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{yaml_text}---\n", encoding='utf-8')


def slugify(value: str) -> str:
    value = re.sub(r'[^a-zA-Z0-9]+', '-', value.strip().lower())
    return value.strip('-') or 'journal'


def journal_uuid() -> str:
    return str(uuid4())


def now_iso_date() -> str:
    return date.today().isoformat()


def sort_key_page_name(path: Path) -> tuple[int, str]:
    match = PAGE_RE.match(path.stem)
    if match:
        return int(match.group(1)), path.name
    return 999999, path.name


def ensure_people_file(path: Path) -> None:
    if not path.exists():
        path.write_text('[]\n', encoding='utf-8')


def read_people(path: Path) -> list[dict[str, str]]:
    ensure_people_file(path)
    import json
    return json.loads(path.read_text(encoding='utf-8') or '[]')


def write_people(path: Path, people: list[dict[str, str]]) -> None:
    import json
    path.write_text(json.dumps(people, indent=2), encoding='utf-8')


def copy_file(src, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(src, 'read'):
        if hasattr(src, 'seek'):
            src.seek(0)
        with open(dst, 'wb') as out_f:
            shutil.copyfileobj(src, out_f)
        return
    with open(src, 'rb') as in_f, open(dst, 'wb') as out_f:
        shutil.copyfileobj(in_f, out_f)


def _normalized_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB",):
        image = image.convert("RGB")
    return image


def save_uploaded_image_as_jpeg(src, dst: Path, *, quality: int = 90) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(src, 'seek'):
        src.seek(0)
    with Image.open(src) as image:
        normalized = _normalized_image(image)
        normalized.save(dst, format='JPEG', quality=quality)


def make_thumbnail(source: Path, dest: Path, size=(480, 480)) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        im = _normalized_image(im)
        im.thumbnail(size)
        im.save(dest, format='JPEG', quality=85)


def update_last_modified(journal_meta: dict[str, Any]) -> dict[str, Any]:
    journal_meta['last_modified'] = now_iso_date()
    return journal_meta


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ''


def valid_date(value: str) -> bool:
    if not value:
        return True
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return True
    except ValueError:
        return False
