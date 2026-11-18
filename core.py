"""Validated project data, configurable media folders, and atomic local storage."""
import ctypes
from ctypes import wintypes
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('COMMENTCUT_DATA', str(ROOT / 'data'))).resolve()

MEDIA_SLOTS = (
    ('background', 'Vid_nen', {'.mp4', '.mov', '.mkv', '.webm'}),
    ('meme_video', 'vid_meme', {'.mp4', '.mov', '.mkv', '.webm'}),
    ('image', 'img_meme', {'.png', '.jpg', '.jpeg', '.webp'}),
    ('sound', 'mp3_meme', {'.mp3', '.wav', '.ogg', '.m4a'}),
)
SLOT_BY_KIND = {kind: (default_sub, suffixes) for kind, default_sub, suffixes in MEDIA_SLOTS}


def ensure_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


for folder in ('assets', 'projects', 'jobs', 'batches', 'cache', 'profile', 'project', 'output', 'Vid_nen', 'vid_meme', 'img_meme', 'mp3_meme'):
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
            if attempt == 39:
                raise
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
                if attempt == 39:
                    raise
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
    provider: Literal['elevenlabs'] = 'elevenlabs'
    voice: str = Field(default='', max_length=100)
    elevenlabs_voices: tuple[str, ...] = Field(default=('',), min_length=1, max_length=120)
    use_meme_video: bool = False
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


def validate_meme_selection(options: Options):
    if options.use_meme_image and not options.use_meme_sound:
        raise ValueError('Khi chọn Ảnh Meme bắt buộc phải bật kèm Tiếng Meme.')


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


def migrate_project_dict(row: dict) -> dict:
    """Upgrade legacy saved project JSONs cleanly to ElevenLabs-only schema."""
    if not isinstance(row, dict):
        return row
    copied = dict(row)
    opts = dict(copied.get('options') or {})
    if opts.get('provider') in ('google', 'edge', 'vbee', None, ''):
        opts['provider'] = 'elevenlabs'
    if opts.get('use_meme_image') and opts.get('use_meme_sound') is False:
        opts['use_meme_sound'] = True
    copied['options'] = opts
    return copied


def media_folders_config() -> dict[str, str]:
    raw = read(DATA / 'media_folders.json', {})
    if not isinstance(raw, dict):
        raw = {}
    return {kind: str(raw.get(kind) or '').strip() for kind, _, _ in MEDIA_SLOTS}


def resolve_media_folder(kind: str) -> tuple[Path, bool, bool]:
    if kind not in SLOT_BY_KIND:
        raise ValueError('Loại thư mục media không hợp lệ.')
    default_sub, _ = SLOT_BY_KIND[kind]
    custom = media_folders_config().get(kind, '')
    if custom:
        candidate = Path(custom).expanduser()
        exists = candidate.is_dir()
        return (candidate.resolve() if exists else candidate, True, exists)
    default_dir = ensure_directory(DATA / default_sub)
    return (default_dir.resolve(), False, True)


def save_media_folder(kind: str, folder_path: str) -> dict:
    if kind not in SLOT_BY_KIND:
        raise ValueError('Loại thư mục media không hợp lệ.')
    cfg = media_folders_config()
    cleaned = str(folder_path or '').strip()
    if cleaned:
        target = Path(cleaned).expanduser()
        if not target.is_dir():
            raise ValueError(f'Thư mục không tồn tại: {cleaned}')
        cfg[kind] = str(target.resolve())
    else:
        cfg[kind] = ''
    write(DATA / 'media_folders.json', cfg)
    return media_diagnostics()


def natural_key(path):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', path.name)]


def folder_assets():
    rows = []
    for kind, default_sub, suffixes in MEDIA_SLOTS:
        folder, is_custom, exists = resolve_media_folder(kind)
        if not exists or not folder.is_dir():
            continue
        for path in sorted(folder.glob('*'), key=natural_key):
            if path.is_file() and path.suffix.lower() in suffixes:
                namespace_key = f'{kind}:{folder}/{path.name}' if is_custom else f'{default_sub}/{path.name}'
                rows.append({
                    'id': uuid.uuid5(uuid.NAMESPACE_URL, namespace_key).hex,
                    'kind': kind,
                    'name': path.name,
                    'file': path.name,
                    'source_folder': default_sub,
                    'folder_path': str(folder),
                    'is_custom': is_custom,
                    'bytes': path.stat().st_size,
                })
    return rows


def asset(asset_id, kind=None):
    ident(asset_id)
    row = next((a for a in folder_assets() if a['id'] == asset_id), None) or read(DATA / 'assets' / f'{asset_id}.json')
    if not row or (kind and row['kind'] != kind):
        raise ValueError('Tài sản không tồn tại hoặc sai loại.')
    if row.get('folder_path'):
        base = Path(row['folder_path']).resolve()
        path = (base / row['file']).resolve()
        if path.parent != base or not path.is_file():
            raise ValueError('Tệp tài sản không tồn tại')
        return path
    if row.get('source_folder'):
        base = (DATA / row['source_folder']).resolve()
        path = (base / row['file']).resolve()
        if path.parent != base or not path.is_file():
            raise ValueError('Tệp tài sản không tồn tại')
        return path
    path = DATA / 'assets' / row['file']
    if path.parent != DATA / 'assets' or not path.is_file():
        raise ValueError('Tệp tài sản không tồn tại')
    return path


def assets():
    """Return reusable media library files across configured folders (excluding crawled screenshots)."""
    return folder_assets()


def safe_media_filename(filename: str, allowed_suffixes: set[str]) -> str:
    raw_name = Path(filename or '').name.strip()
    suffix = Path(raw_name).suffix.lower()
    if suffix not in allowed_suffixes:
        raise ValueError('Định dạng tệp không hỗ trợ.')
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(raw_name).stem).strip(' .')[:110] or uid()[:8]
    if stem.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{n}' for n in range(1, 10)), *(f'LPT{n}' for n in range(1, 10))}:
        stem = '_' + stem
    return stem + suffix


def media_diagnostics(rows=None):
    items = rows if rows is not None else folder_assets()
    backgrounds = [a for a in items if a['kind'] == 'background']
    meme_videos = [a for a in items if a['kind'] == 'meme_video']
    images = [a for a in items if a['kind'] == 'image']
    sounds = [a for a in items if a['kind'] == 'sound']

    sound_stems = {Path(s['file']).stem.casefold() for s in sounds}
    paired = sum(1 for img in images if Path(img['file']).stem.casefold() in sound_stems)
    unpaired_images = [img['name'] for img in images if Path(img['file']).stem.casefold() not in sound_stems]

    folders = {}
    counts_by_kind = {
        'background': len(backgrounds),
        'meme_video': len(meme_videos),
        'image': len(images),
        'sound': len(sounds),
    }
    for kind, default_sub, _ in MEDIA_SLOTS:
        eff_path, is_custom, exists = resolve_media_folder(kind)
        folders[kind] = {
            'kind': kind,
            'default_sub': default_sub,
            'path': str(eff_path),
            'display_path': str(eff_path) if is_custom else f'data/{default_sub}',
            'is_custom': is_custom,
            'exists': exists,
            'count': counts_by_kind[kind],
        }

    return {
        'background_count': len(backgrounds),
        'meme_video_count': len(meme_videos),
        'meme_image_count': len(images),
        'meme_sound_count': len(sounds),
        'paired_meme_count': paired,
        'random_paired_count': len(images) - paired if sounds else 0,
        'missing_sounds': unpaired_images[:20] if not sounds else [],
        'unpaired_images': unpaired_images[:20],
        'folders': folders,
    }


# Keep alias for existing imports
meme_diagnostics = media_diagnostics


class _GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_str(cls, text: str):
        u = uuid.UUID(text)
        d1, d2, d3 = u.fields[:3]
        raw = u.bytes[8:]
        arr = (ctypes.c_ubyte * 8)(*raw)
        return cls(d1, d2, d3, arr)


def pick_windows_folder(title: str = 'Chọn thư mục Media', initial_dir: str = '') -> str | None:
    """Open native modern Windows 10/11 Explorer folder picker via COM IFileOpenDialog."""
    if os.name != 'nt':
        return None
    result_holder = {'path': None, 'error': None}

    def run_sta():
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        COINIT_APARTMENTTHREADED = 0x2
        CLSCTX_INPROC_SERVER = 0x1
        FOS_PICKFOLDERS = 0x20
        FOS_FORCEFILESYSTEM = 0x40
        FOS_NOCHANGEDIR = 0x8
        SIGDN_FILESYSPATH = 0x80058000
        ERROR_CANCELLED_HRESULT = -2147023673  # 0x800704C7

        clsid_dialog = _GUID.from_str('DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7')
        iid_dialog = _GUID.from_str('d57c7288-d4ad-4768-be02-9d969532d960')
        iid_shell_item = _GUID.from_str('43826d1e-e718-42ee-bc55-a1e261c37bfe')

        hr_init = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        dialog = ctypes.c_void_p()
        try:
            hr = ole32.CoCreateInstance(
                ctypes.byref(clsid_dialog),
                None,
                CLSCTX_INPROC_SERVER,
                ctypes.byref(iid_dialog),
                ctypes.byref(dialog),
            )
            if hr < 0 or not dialog.value:
                result_holder['error'] = f'CoCreateInstance failed: {hr:#x}'
                return

            vtable = ctypes.cast(dialog, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

            Release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
            Show = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND)(vtable[3])
            SetOptions = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD)(vtable[9])
            GetOptions = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))(vtable[10])
            SetFolder = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(vtable[12])
            SetTitle = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR)(vtable[17])
            GetResult = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable[20])

            try:
                opts = wintypes.DWORD()
                if GetOptions(dialog, ctypes.byref(opts)) >= 0:
                    SetOptions(dialog, opts.value | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_NOCHANGEDIR)
                if title:
                    SetTitle(dialog, title)

                if initial_dir and Path(initial_dir).is_dir():
                    SHCreateItemFromParsingName = shell32.SHCreateItemFromParsingName
                    SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
                    SHCreateItemFromParsingName.restype = ctypes.c_long
                    init_item = ctypes.c_void_p()
                    if SHCreateItemFromParsingName(str(Path(initial_dir).resolve()), None, ctypes.byref(iid_shell_item), ctypes.byref(init_item)) >= 0 and init_item.value:
                        SetFolder(dialog, init_item)
                        item_vtbl = ctypes.cast(init_item, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                        ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(item_vtbl[2])(init_item)

                hwnd = user32.GetForegroundWindow()
                hr_show = Show(dialog, hwnd)
                if hr_show == ERROR_CANCELLED_HRESULT or hr_show < 0:
                    return

                result_item = ctypes.c_void_p()
                if GetResult(dialog, ctypes.byref(result_item)) >= 0 and result_item.value:
                    item_vtbl = ctypes.cast(result_item, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                    ItemRelease = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(item_vtbl[2])
                    GetDisplayName = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))(item_vtbl[5])
                    try:
                        psz = wintypes.LPWSTR()
                        if GetDisplayName(result_item, SIGDN_FILESYSPATH, ctypes.byref(psz)) >= 0 and psz.value:
                            result_holder['path'] = psz.value
                            ole32.CoTaskMemFree(psz)
                    finally:
                        ItemRelease(result_item)
            finally:
                Release(dialog)
        finally:
            if hr_init >= 0:
                ole32.CoUninitialize()

    t = threading.Thread(target=run_sta, daemon=True)
    t.start()
    t.join(timeout=300)
    if result_holder['error']:
        raise ValueError(result_holder['error'])
    return result_holder['path']


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


def find_project_folder(project_id: str) -> Path | None:
    folder_root = DATA / 'project'
    if not folder_root.is_dir():
        return None
    for path in folder_root.glob('project*'):
        if read(path / 'identity.json', {}).get('id') == project_id:
            return path
    return None


def project_folder(project):
    existing = find_project_folder(project.id)
    if existing is not None:
        return existing
    ensure_directory(DATA / 'project')
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
    for line_no, raw in enumerate(str(text or '').lstrip('\ufeff').splitlines(), 1):
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
    if title.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(n) for n in range(1, 10)), *('LPT' + str(n) for n in range(1, 10))}:
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
