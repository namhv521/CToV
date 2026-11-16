"""Validated project data and atomic local storage."""
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('COMMENTCUT_DATA', str(ROOT / 'data'))).resolve()
def ensure_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


for folder in ('assets', 'projects', 'jobs', 'batches', 'cache', 'profile', 'project', 'output', 'Vid_nen', 'img_meme', 'mp3_meme'):
    ensure_directory(DATA / folder)


def uid():
    return uuid.uuid4().hex


def ident(value):
    if not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('ID không hợp lệ')
    return value


def read(path, default=None):
    for attempt in range(40):
        try:
            return json.loads(path.read_text('utf-8'))
        except FileNotFoundError:
            return default
        except PermissionError:
            if attempt == 39: raise
            time.sleep(.025)


def write(path, value):
    ensure_directory(path.parent)
    temp = path.with_name(path.name + '.' + uid() + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
        # Windows readers/virus scanners can briefly hold destination handles.
        for attempt in range(40):
            try:
                temp.replace(path)
                return
            except PermissionError:
                if attempt == 39: raise
                time.sleep(.025)
    finally:
        temp.unlink(missing_ok=True)


def source_url(value):
    p = urlsplit(value.strip())
    allowed = {'tiktok.com', 'www.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
               'threads.net', 'www.threads.net', 'threads.com', 'www.threads.com'}
    if p.scheme != 'https' or p.hostname not in allowed or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Chỉ nhận link HTTPS TikTok hoặc Threads chính thức.')
    return value.strip()


class Comment(BaseModel):
    id: str = Field(default_factory=uid, max_length=200)
    author: str = Field(default='Người dùng', max_length=100)
    text: str = Field(default='', max_length=1500)
    speech: str = Field(default='', max_length=1500)
    likes: int = Field(default=0, ge=0)
    selected: bool = True
    meme: str = ''
    sound: str = ''
    image: str = ''
    capture_text: str = Field(default='', max_length=1500)
    captured_at: str = Field(default='', max_length=100)
    source_url: str = Field(default='', max_length=2000)
    comment_url: str = Field(default='', max_length=2000)
    likes_display: str = Field(default='', max_length=100)
    meme_seconds: float = Field(default=1.2, ge=0.3, le=8)
    @field_validator('text')
    @classmethod
    def nonempty(cls, value):
        return value.strip()

    @model_validator(mode='after')
    def require_content(self):
        if not self.text and not self.image:
            raise ValueError('Bình luận trống: cần chữ hoặc ảnh chụp.')
        return self


class Options(BaseModel):
    provider: Literal['google', 'edge', 'elevenlabs', 'vbee'] = 'google'
    voice: str = Field(default='vi-VN-HoaiMyNeural', max_length=100)
    elevenlabs_voices: tuple[str, ...] = Field(default=('',), min_length=1, max_length=120)
    use_meme_image: bool = True
    use_meme_sound: bool = True
    speed: float = Field(default=1.1, ge=0.6, le=1.8)
    resolution: Literal[360, 720, 1080] = 720
    background: str = ''
    default_meme: str = ''
    default_sound: str = ''
    credit: str = Field(default='CRE: COMMENTCUT', max_length=70)
    card_y: float = Field(default=0.28, ge=0.1, le=0.60)
    max_seconds: int = Field(default=120, ge=15, le=600)
    split_mode: Literal['duration', 'even', 'comments'] = 'duration'
    video_count: int = Field(default=3, ge=1, le=120, strict=True)
    comments_per_video: int = Field(default=10, ge=1, le=120, strict=True)
    read_post: bool = True
    anonymous: bool = False
    meme_volume: float = Field(default=0.65, ge=0, le=1)
    @field_validator('elevenlabs_voices')
    @classmethod
    def valid_voices(cls, values):
        cleaned = tuple(value.strip() for value in values)
        if any(value and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) for value in cleaned):
            raise ValueError('Voice ID ElevenLabs chỉ nhận chữ, số, dấu gạch ngang/gạch dưới; tối đa 100 ký tự.')
        return cleaned


class Project(BaseModel):
    id: str = Field(default_factory=uid)
    name: str = Field(default='Video chưa đặt tên', max_length=120)
    url: str = Field(default='', max_length=2000)
    post: str = Field(default='', max_length=1500)
    post_image: str = ''
    post_captured_at: str = Field(default='', max_length=100)
    post_capture_error: str = Field(default='', max_length=2000)
    author: str = Field(default='', max_length=100)
    comments: list[Comment] = Field(default_factory=list, max_length=120)
    options: Options = Field(default_factory=Options)
    crawl_note: str = Field(default='', max_length=2000)
    crawled_at: str = Field(default='', max_length=100)
    crawl_date: str = Field(default='', max_length=10)
    @field_validator('id')
    @classmethod
    def valid_id(cls, value):
        return ident(value)

    @field_validator('crawl_date')
    @classmethod
    def valid_crawl_date(cls, value):
        if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Ngày crawl phải theo dạng YYYY-MM-DD.')
        return value


def asset(asset_id, kind=None):
    ident(asset_id)
    row = next((a for a in folder_assets() if a['id'] == asset_id), None) or read(DATA / 'assets' / f'{asset_id}.json')
    if not row or (kind and row['kind'] != kind):
        raise ValueError('Tài sản không tồn tại hoặc sai loại.')
    if row.get('source_folder'):
        path = DATA / row['source_folder'] / row['file']
        if path.resolve().parent != (DATA / row['source_folder']).resolve() or not path.is_file():
            raise ValueError('Tệp tài sản không tồn tại')
        return path
    path = DATA / 'assets' / row['file']
    if path.parent != DATA / 'assets' or not path.is_file():
        raise ValueError('Tệp tài sản không tồn tại')
    return path


def assets():
    return folder_assets() + [read(p) for p in sorted((DATA / 'assets').glob('*.json'))]


def executable(name):
    configured = os.environ.get(name.upper() + '_PATH')
    result = configured or shutil.which(name)
    if not result:
        raise ValueError(f'Không tìm thấy {name}. Cài FFmpeg và thêm vào PATH.')
    return result


def probe(path):
    p = subprocess.run([executable('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                       capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if p.returncode:
        raise ValueError('Không đọc được tệp media. Hãy dùng MP4/MP3/WAV hợp lệ.')
    return json.loads(p.stdout)


def duration(path):
    return float(probe(path)['format']['duration'])


def natural_key(path):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', path.name)]


def folder_assets():
    rows = []
    for directory, kind, suffixes in (
        ('Vid_nen', 'background', {'.mp4', '.mov', '.mkv', '.webm'}),
        ('img_meme', 'image', {'.png', '.jpg', '.jpeg', '.webp'}),
        ('mp3_meme', 'sound', {'.mp3', '.wav', '.ogg', '.m4a'}),
    ):
        for path in sorted((DATA / directory).glob('*'), key=natural_key):
            if path.is_file() and path.suffix.lower() in suffixes:
                rows.append({'id': uuid.uuid5(uuid.NAMESPACE_URL, directory + '/' + path.name).hex,
                             'kind': kind, 'name': path.name, 'file': path.name, 'source_folder': directory, 'bytes': path.stat().st_size})
    return rows


def project_folder(project):
    # mkdir reserves the next number atomically, including concurrent requests.
    for path in (DATA / 'project').glob('project*'):
        if read(path / 'identity.json', {}).get('id') == project.id:
            return path
    number = 1
    while True:
        path = DATA / 'project' / f'project{number}'
        try:
            path.mkdir()
            write(path / 'identity.json', {'id': project.id})
            return path
        except FileExistsError:
            number += 1


def snapshot_project(project, folder):
    for name in ('images', 'comments', 'audio', 'renders'):
        (folder / name).mkdir(exist_ok=True)
    write(folder / 'project.json', project.model_dump())
    write(folder / 'comments' / 'comments.json', [c.model_dump() for c in project.comments])
    write(folder / 'post.json', {'text': project.post, 'author': project.author, 'url': project.url, 'image': project.post_image, 'captured_at': project.post_captured_at})
    for image_id in [project.post_image, *(comment.image for comment in project.comments)]:
        if image_id:
            source = asset(image_id, 'image')
            target = folder / 'images' / source.name
            if not target.exists():
                shutil.copy2(source, target)


def auto_project_name(post='', author='', url=''):
    for line in str(post or '').splitlines():
        cleaned = ' '.join(line.split()).strip()
        if cleaned:
            return cleaned[:120]
    handle = str(author or '').strip().lstrip('@')
    code = ''
    if url:
        path = urlsplit(url).path.rstrip('/')
        match = re.search(r'/(?:video|post|t)/([^/?#]+)', path)
        if match:
            code = match.group(1)
        elif path:
            code = path.split('/')[-1]
        if not handle:
            user_match = re.search(r'/@([^/?#]+)', path)
            if user_match:
                handle = user_match.group(1)
    if handle and code:
        return f'@{handle} · {code}'[:120]
    if handle:
        return f'@{handle}'[:120]
    if code:
        return f'Bài viết {code}'[:120]
    return 'Video chưa đặt tên'


def local_date(iso_stamp=''):
    if iso_stamp:
        try:
            dt = datetime.fromisoformat(iso_stamp.replace('Z', '+00:00'))
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return datetime.now().astimezone().strftime('%Y-%m-%d')


def infer_crawl_date(row):
    explicit = str(row.get('crawl_date') or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', explicit):
        return explicit
    for stamp in (row.get('crawled_at'), row.get('post_captured_at'),
                  *(c.get('captured_at') for c in (row.get('comments') or []) if isinstance(c, dict))):
        if stamp:
            return local_date(str(stamp))
    return ''


def parse_url_lines(text):
    urls, invalid, seen = [], [], set()
    for line_no, raw in enumerate(str(text or '').lstrip('﻿').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        try:
            clean = source_url(line)
        except ValueError as exc:
            invalid.append({'line': line_no, 'url': line[:200], 'error': str(exc)})
            continue
        if clean not in seen:
            seen.add(clean)
            urls.append(clean)
    return urls, invalid


def video_title(project):
    title = project.post.strip().splitlines()[0] if project.post.strip() else project.name
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:100].rstrip(' .') or 'Video'
    if title.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}:
        title = '_' + title
    return title


def script_groups(comments, options):
    """Partition selected comments without dropping, repeating, or reordering them."""
    selected = [c for c in comments if c.selected]
    if not selected:
        raise ValueError('Chọn ít nhất một bình luận.')
    if options.split_mode == 'even':
        if options.video_count > len(selected):
            raise ValueError('Số video không được vượt số bình luận đang chọn.')
        size, extra = divmod(len(selected), options.video_count)
        groups, start = [], 0
        for index in range(options.video_count):
            stop = start + size + (index < extra)
            groups.append(selected[start:stop])
            start = stop
        return groups
    if options.split_mode == 'comments':
        size = options.comments_per_video
        return [selected[start:start + size] for start in range(0, len(selected), size)]
    return [selected]


def require_screenshots(project):
    if project.options.read_post and (project.post.strip() or project.post_image or project.url.strip()):
        if not project.post_image:
            raise ValueError('Thiếu ảnh chụp bài viết gốc. Crawl lại hoặc tắt Đọc bài viết; không dựng thẻ chữ thay thế.')
        asset(project.post_image, 'image')
    for index, comment in enumerate(project.comments, 1):
        if comment.selected:
            if not comment.image:
                raise ValueError(f'Bình luận {index} thiếu ảnh chụp. Crawl lại hoặc chọn ảnh thật; không dựng thẻ chữ thay thế.')
            asset(comment.image, 'image')
