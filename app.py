import asyncio
from datetime import datetime
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from core import (
    DATA, ROOT, SLOT_BY_KIND, Project, Options, assets, asset, ident, read, write, uid, probe,
    executable, source_url, project_folder, find_project_folder, snapshot_project,
    script_groups, ensure_directory, require_screenshots, auto_project_name,
    local_date, infer_crawl_date, parse_url_lines, safe_media_filename,
    media_diagnostics, migrate_project_dict, resolve_media_folder,
    save_media_folder, pick_windows_folder, validate_meme_selection,
)
from speech import public_settings, save_settings, synthesize, narration_options, batch_narration_options
from render import render, card, credit_image, credit_position

pool = ThreadPoolExecutor(max_workers=1)
batch_pool = ThreadPoolExecutor(max_workers=1)
events, batch_events = {}, {}
lock = threading.Lock()
batch_lock = threading.Lock()
crawl_lock = threading.Lock()
project_lock = threading.Lock()
login_process = None


def default_batch_options():
    return Options(provider='elevenlabs', split_mode='comments', comments_per_video=10, video_count=3)


class BulkPreset(BaseModel):
    limit: int = Field(default=30, ge=1, le=120)
    auto_render: bool = True
    options: Options = Field(default_factory=default_batch_options)


def load_preset() -> dict:
    raw = read(DATA / 'preset.json')
    if not isinstance(raw, dict):
        return BulkPreset().model_dump()
    try:
        opts = dict(raw.get('options') or {})
        if opts.get('provider') in ('google', 'edge', 'vbee', None, ''):
            opts['provider'] = 'elevenlabs'
        if opts.get('use_meme_image') and opts.get('use_meme_sound') is False:
            opts['use_meme_sound'] = True
        raw = {**raw, 'options': opts}
        return BulkPreset(**raw).model_dump()
    except Exception:
        return BulkPreset().model_dump()


def save_preset_data(preset: BulkPreset) -> dict:
    opts = preset.options.model_copy(update={'provider': 'elevenlabs'})
    if opts.use_meme_image and not opts.use_meme_sound:
        opts = opts.model_copy(update={'use_meme_sound': True})
    clean = preset.model_copy(update={'options': opts})
    dumped = clean.model_dump()
    write(DATA / 'preset.json', dumped)
    return dumped


@asynccontextmanager
async def lifespan(app):
    for path in (DATA / 'jobs').glob('*/job.json'):
        row = read(path)
        if row and row.get('status') in ('queued', 'running'):
            row.update(status='interrupted', message='Ứng dụng đã tắt giữa lúc dựng. Bấm Render lại để tiếp tục.')
            write(path, row)
    for path in (DATA / 'batches').glob('*.json'):
        row = read(path)
        if row and row.get('status') in ('queued', 'running'):
            for item in row.get('items', []):
                if item.get('status') in ('queued', 'crawling', 'rendering'):
                    item.update(status='interrupted', message='Ứng dụng đã tắt giữa chừng.')
            row.update(status='interrupted', message='Ứng dụng đã tắt giữa lúc chạy lô.')
            write(path, row)
    yield
    for event in events.values():
        event.set()
    for event in batch_events.values():
        event.set()


app = FastAPI(title='CommentCut Studio', lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0]
    origin = request.headers.get('origin')
    if host not in ('127.0.0.1', 'localhost', 'testserver'):
        return JSONResponse({'detail': 'Chỉ truy cập cục bộ.'}, status_code=403)
    if origin and (urlsplit(origin).hostname not in ('127.0.0.1', 'localhost') or urlsplit(origin).netloc != request.headers.get('host')):
        return JSONResponse({'detail': 'Origin không được phép.'}, status_code=403)
    if request.headers.get('sec-fetch-site') == 'cross-site' and not (
            request.method == 'GET' and request.url.path == '/' and request.headers.get('sec-fetch-mode') == 'navigate'):
        return JSONResponse({'detail': 'Không nhận yêu cầu từ website ngoài.'}, status_code=403)
    if int(request.headers.get('content-length', '0') or 0) > 550_000_000:
        return JSONResponse({'detail': 'Tệp vượt giới hạn 500MB.'}, status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    )
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    errors = [{'field': '.'.join(map(str, error['loc'][1:])), 'message': error['msg']}
              for error in exc.errors()]
    write(DATA / 'validation_error.json', {'endpoint': request.url.path, 'errors': errors})
    detail = 'Dữ liệu không hợp lệ: ' + '; '.join(
        error['field'] + ': ' + error['message'] for error in errors[:5])
    return JSONResponse({'detail': detail}, status_code=422)


@app.get('/api/health')
def health():
    try:
        ffmpeg = bool(executable('ffmpeg') and executable('ffprobe'))
    except ValueError:
        ffmpeg = False
    return {'ok': True, 'ffmpeg': ffmpeg, 'data': str(DATA), 'media': media_diagnostics()}


@app.get('/api/preset')
def get_preset():
    return load_preset()


@app.post('/api/preset')
def update_preset(body: BulkPreset):
    return save_preset_data(body)


class MediaFolderUpdateRequest(BaseModel):
    kind: Literal['background', 'meme_video', 'image', 'sound']
    path: str = Field(default='', max_length=1000)


class MediaFolderPickRequest(BaseModel):
    kind: Literal['background', 'meme_video', 'image', 'sound']


@app.get('/api/media-folders')
def get_media_folders():
    return media_diagnostics()


@app.post('/api/media-folders')
def set_media_folder_route(body: MediaFolderUpdateRequest):
    return save_media_folder(body.kind, body.path)


@app.post('/api/media-folders/pick')
def pick_media_folder_route(body: MediaFolderPickRequest):
    titles = {
        'background': 'Chọn thư mục chứa Video nền',
        'meme_video': 'Chọn thư mục chứa Video Meme',
        'image': 'Chọn thư mục chứa Ảnh Meme',
        'sound': 'Chọn thư mục chứa Tiếng Meme (MP3/WAV)',
    }
    current_path, _, exists = resolve_media_folder(body.kind)
    initial = str(current_path) if exists else str(DATA)
    picked = pick_windows_folder(title=titles[body.kind], initial_dir=initial)
    if not picked:
        return {'picked': False, 'media': media_diagnostics()}
    diag = save_media_folder(body.kind, picked)
    return {'picked': True, 'path': picked, 'media': diag}


class OpenFolderRequest(BaseModel):
    target: Literal[
        'output', 'project_output',
        'background', 'meme_video', 'image', 'sound',
        'vid_nen', 'vid_meme', 'img_meme', 'mp3_meme',
    ] = 'output'
    project_id: str | None = None


@app.post('/api/open-folder')
def open_folder(body: OpenFolderRequest):
    alias_to_kind = {
        'vid_nen': 'background',
        'vid_meme': 'meme_video',
        'img_meme': 'image',
        'mp3_meme': 'sound',
        'background': 'background',
        'meme_video': 'meme_video',
        'image': 'image',
        'sound': 'sound',
    }
    if body.target == 'project_output':
        folder = ensure_directory(DATA / 'output')
        if body.project_id:
            pfolder = find_project_folder(ident(body.project_id))
            if pfolder and (DATA / 'output' / pfolder.name).is_dir():
                folder = DATA / 'output' / pfolder.name
    elif body.target == 'output':
        folder = ensure_directory(DATA / 'output')
    else:
        kind = alias_to_kind[body.target]
        eff_path, _, exists = resolve_media_folder(kind)
        if not exists:
            raise ValueError(f'Thư mục "{eff_path}" hiện không tồn tại. Hãy chọn lại thư mục.')
        folder = eff_path
    if hasattr(os, 'startfile'):
        os.startfile(str(folder))
    else:
        subprocess.Popen(['xdg-open', str(folder)])
    return {'ok': True, 'path': str(folder)}


@app.get('/api/assets')
def list_assets():
    return assets()


@app.post('/api/assets/{kind}')
def upload(kind: str, file: UploadFile = File(...)):
    if kind not in SLOT_BY_KIND:
        raise ValueError('Loại tài sản không hợp lệ')
    default_sub, allowed_suffixes = SLOT_BY_KIND[kind]
    safe_name = safe_media_filename(file.filename or '', allowed_suffixes)
    dest_dir, is_custom, exists = resolve_media_folder(kind)
    if not exists:
        raise ValueError(f'Thư mục đích "{dest_dir}" không tồn tại. Hãy chọn lại thư mục.')
    ensure_directory(dest_dir)
    temp = ensure_directory(DATA / 'cache') / (uid() + Path(safe_name).suffix.lower())
    size = 0
    duration_val = None
    try:
        with temp.open('wb') as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 500_000_000:
                    raise ValueError('Tệp vượt giới hạn 500MB')
                out.write(chunk)
        if kind == 'image':
            with Image.open(temp) as im:
                if im.width * im.height > 30_000_000:
                    raise ValueError('Ảnh vượt 30 megapixel')
                im.verify()
        else:
            info = probe(temp)
            required = 'video' if kind in ('background', 'meme_video') else 'audio'
            if not any(s['codec_type'] == required for s in info['streams']):
                raise ValueError('Tệp không có track cần thiết.')
            duration_val = float(info['format']['duration'])
        target = dest_dir / safe_name
        shutil.move(str(temp), str(target))
        namespace_key = f'{kind}:{dest_dir}/{target.name}' if is_custom else f'{default_sub}/{target.name}'
        aid = uuid.uuid5(uuid.NAMESPACE_URL, namespace_key).hex
        row = {
            'id': aid,
            'kind': kind,
            'name': target.name,
            'file': target.name,
            'source_folder': default_sub,
            'folder_path': str(dest_dir),
            'is_custom': is_custom,
            'bytes': size,
        }
        if duration_val is not None:
            row['duration'] = duration_val
        return row
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise ValueError('Ảnh không hợp lệ hoặc quá lớn.') from None
    finally:
        temp.unlink(missing_ok=True)


@app.delete('/api/assets/{aid}')
def delete_asset(aid: str):
    ident(aid)
    matched = next((a for a in assets() if a['id'] == aid), None)
    if not matched:
        raise HTTPException(404, 'Không tìm thấy tệp trong thư viện.')
    folder = Path(matched.get('folder_path') or (DATA / matched['source_folder'])).resolve()
    target = (folder / matched['file']).resolve()
    if target.parent != folder or not target.is_file():
        raise HTTPException(404, 'Tệp không tồn tại.')
    target.unlink(missing_ok=True)
    return {'ok': True, 'media': media_diagnostics()}


@app.get('/api/assets/{aid}/file')
def asset_file(aid: str):
    return FileResponse(asset(aid))


def latest_jobs_by_project():
    latest = {}
    for path in (DATA / 'jobs').glob('*/job.json'):
        row = read(path, {})
        pid = row.get('project_id')
        if pid and row.get('created', 0) >= latest.get(pid, {}).get('created', 0):
            latest[pid] = row
    return latest


def job_public_summary(job_row: dict | None):
    if not job_row:
        return None
    manifest = read(DATA / 'jobs' / job_row['id'] / 'timeline.json', {}) or {}
    return {
        'id': job_row['id'],
        'status': job_row['status'],
        'progress': job_row.get('progress', 0),
        'message': job_row.get('message', ''),
        'output_project': manifest.get('output_project', ''),
        'files': [f for f in job_row.get('files', []) if f.endswith('.mp4')],
    }


def project_summary(path: Path, jobs_map: dict):
    row = read(path, {}) or {}
    comments = row.get('comments') or []
    job_row = jobs_map.get(path.stem)
    thumb = row.get('post_image') or next((c.get('image') for c in comments if isinstance(c, dict) and c.get('image')), '')
    pfolder = find_project_folder(path.stem)
    return {
        'id': path.stem,
        'name': row.get('name', 'Video chưa đặt tên'),
        'url': row.get('url', ''),
        'author': row.get('author', ''),
        'post': row.get('post', '')[:200],
        'thumbnail': thumb,
        'project_folder': pfolder.name if pfolder else '',
        'comment_count': len(comments),
        'selected_count': sum(1 for c in comments if isinstance(c, dict) and c.get('selected', True)),
        'crawled_at': row.get('crawled_at', ''),
        'crawl_date': infer_crawl_date(row),
        'updated': path.stat().st_mtime,
        'job': job_public_summary(job_row),
    }


@app.get('/api/projects')
def projects():
    jobs_map = latest_jobs_by_project()
    return sorted([project_summary(p, jobs_map) for p in (DATA / 'projects').glob('*.json')],
                  key=lambda p: p['updated'], reverse=True)


@app.get('/api/crawl-days')
def crawl_days():
    jobs_map = latest_jobs_by_project()
    grouped = {}
    for path in (DATA / 'projects').glob('*.json'):
        summary = project_summary(path, jobs_map)
        date_key = summary['crawl_date'] or local_date()
        grouped.setdefault(date_key, []).append(summary)
    days = []
    for date in sorted(grouped.keys(), reverse=True):
        items = sorted(grouped[date], key=lambda p: (p['crawled_at'] or '', p['updated']), reverse=True)
        rendered_videos = sum(len(item['job']['files']) for item in items if item.get('job') and item['job']['status'] == 'done')
        days.append({
            'date': date,
            'project_count': len(items),
            'comment_count': sum(item['comment_count'] for item in items),
            'rendered_videos': rendered_videos,
            'projects': items,
        })
    return days


@app.post('/api/projects')
def save_project(project: Project):
    with project_lock:
        saved = read(DATA / 'projects' / f'{project.id}.json', {}) or {}
        if not project.crawled_at and saved.get('crawled_at'):
            project.crawled_at = saved['crawled_at']
        if not project.crawl_date:
            project.crawl_date = saved.get('crawl_date') or infer_crawl_date(project.model_dump())
        current_source = project.url.split('#', 1)[0].split('?', 1)[0].rstrip('/')
        saved_image = saved.get('post_image')
        metadata = read(DATA / 'assets' / f'{ident(saved_image)}.json', {}) if saved_image else {}
        saved_url = (metadata or {}).get('source_url') or saved.get('url', '')
        saved_source = saved_url.split('#', 1)[0].split('?', 1)[0].rstrip('/')
        if (not project.post_image and saved_image
                and current_source == saved_source
                and (current_source or project.post == saved.get('post'))):
            if project.post_capture_error and project.crawl_note.endswith(project.post_capture_error):
                project.crawl_note = (project.crawl_note.removesuffix(project.post_capture_error).rstrip()
                                      + ' Đã giữ ảnh bài gốc chụp trước đó.').strip()
            project.post = saved['post']
            project.author = saved.get('author', '')
            project.post_image = saved_image
            project.post_captured_at = saved.get('post_captured_at', '')
            project.post_capture_error = ''
        folder = project_folder(project)
        snapshot_project(project, folder)
        write(DATA / 'projects' / f'{project.id}.json', project.model_dump())
    return {'id': project.id, 'folder': folder.name}


@app.get('/api/projects/{pid}')
def get_project(pid: str):
    row = read(DATA / 'projects' / f'{ident(pid)}.json')
    if row is None:
        raise HTTPException(404, 'Không tìm thấy dự án')
    return migrate_project_dict(row)


@app.delete('/api/projects/{pid}')
def delete_project(pid: str):
    target = DATA / 'projects' / f'{ident(pid)}.json'
    if not target.is_file():
        raise HTTPException(404, 'Không tìm thấy dự án')
    target.unlink(missing_ok=True)
    return {'ok': True}


@app.post('/api/login/{platform}')
def login(platform: str):
    global login_process
    if platform not in ('tiktok', 'threads'):
        raise ValueError('Nguồn không hợp lệ')
    if crawl_lock.locked():
        raise ValueError('Chờ tiến trình crawl hiện tại hoàn tất trước khi mở cửa sổ đăng nhập.')
    if login_process and login_process.poll() is None:
        raise ValueError('Cửa sổ đăng nhập đang mở.')
    if getattr(sys, 'frozen', False):
        command = [sys.executable, '--login', platform]
        env = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
    else:
        command = [sys.executable, str(ROOT / 'collector.py'), platform]
        env = None
    login_process = subprocess.Popen(command, cwd=DATA, env=env,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {'message': f'Đã mở cửa sổ đăng nhập {platform.title()}. Sau khi đăng nhập xong, hãy đóng cửa sổ đó lại để bắt đầu crawl.'}


@app.get('/api/settings')
def config():
    return public_settings()


@app.post('/api/settings')
def config_save(values: dict):
    save_settings(values)
    return public_settings()


class VoiceRequest(BaseModel):
    voice_index: int = Field(default=0, ge=0, le=119)
    use_saved_voices: bool = True
    text: str = Field(default='Xin chào, cùng đọc những bình luận thú vị nhất hôm nay nhé.', min_length=1, max_length=250)
    options: Options = Field(default_factory=Options)


@app.post('/api/voice-preview')
def voice_preview(body: VoiceRequest):
    if body.use_saved_voices:
        body.options = batch_narration_options(body.options)
    if body.voice_index >= len(body.options.elevenlabs_voices):
        raise ValueError('Giọng ElevenLabs được chọn không còn trong danh sách.')
    path = synthesize(body.text, narration_options(body.options, body.voice_index))
    from render import run
    target = ensure_directory(DATA / 'cache') / (uid() + '.wav')
    run(['-i', path, '-af', f'atempo={body.options.speed},loudnorm=I=-16:TP=-1.5:LRA=11',
         '-ar', '48000', '-ac', '2', target], DATA / 'cache', lambda: False, timeout=60)
    from starlette.background import BackgroundTask
    return FileResponse(target, media_type='audio/wav', background=BackgroundTask(target.unlink, missing_ok=True))


@app.post('/api/card-preview')
def card_preview(project: Project):
    selected = next((c for c in project.comments if c.selected), None)
    path = ensure_directory(DATA / 'cache') / (uid() + '.png')
    image_id = project.post_image if project.options.read_post and project.post_image else selected.image if selected else ''
    if image_id:
        card('', '', 0, project.options, path, image_id)
    else:
        w, h = project.options.resolution, project.options.resolution * 16 // 9
        Image.new('RGBA', (w, h), (0, 0, 0, 0)).save(path)
    watermark = credit_image(project.options)
    if watermark is not None:
        with Image.open(path) as preview:
            x, y = credit_position(preview.width, preview.height, watermark.width, watermark.height, 0)
            preview.alpha_composite(watermark, (round(x), round(y)))
            preview.save(path)
    from starlette.background import BackgroundTask
    return FileResponse(path, media_type='image/png', background=BackgroundTask(path.unlink, missing_ok=True))


def job_path(jid):
    return DATA / 'jobs' / ident(jid) / 'job.json'


def update_job(jid, **changes):
    with lock:
        row = read(job_path(jid))
        if not row:
            return
        row.update(changes, updated=time.time())
        write(job_path(jid), row)


def work(jid, project):
    event = events[jid]
    try:
        if event.is_set():
            raise InterruptedError('Đã hủy')
        update_job(jid, status='running', message='Chuẩn bị dựng')

        def progress(percent, message):
            published = read(job_path(jid).parent / 'timeline.json', {}).get('files', [])
            update_job(jid, progress=percent, message=message, files=published)

        files = render(project, job_path(jid).parent, progress, event.is_set)
        if event.is_set():
            raise InterruptedError('Đã hủy')
        update_job(jid, status='done', files=files, progress=100, message='Hoàn tất')
    except InterruptedError:
        update_job(jid, status='cancelled', message='Đã hủy. Dữ liệu đã crawl vẫn được giữ nguyên.')
    except Exception as exc:
        import traceback
        (job_path(jid).parent / 'error.log').write_text(traceback.format_exc(), 'utf-8')
        message = str(exc) if isinstance(exc, ValueError) else f'Lỗi dựng: {type(exc).__name__}. Kiểm tra media và cấu hình.'
        update_job(jid, status='failed', message=message)


def link_job_to_batches(project_id: str, jid: str):
    with batch_lock:
        for bpath in (DATA / 'batches').glob('*.json'):
            brow = read(bpath)
            if not brow:
                continue
            changed = False
            for it in brow.get('items', []):
                if it.get('project_id') == project_id:
                    it['job_id'] = jid
                    changed = True
            if changed:
                write(bpath, brow)


def preflight_media_check(options: Options):
    validate_meme_selection(options)
    all_assets = assets()
    backgrounds = [a for a in all_assets if a.get('kind') == 'background']
    if not options.background and not backgrounds:
        raise ValueError('Chưa có video nền trong thư mục Video nền đã chọn.')
    if options.background and not any(a['id'] == options.background for a in backgrounds):
        raise ValueError('Video nền đã chọn không còn trong thư mục Video nền.')
    if options.use_meme_video and not any(a.get('kind') == 'meme_video' for a in all_assets):
        raise ValueError('Đang bật Video Meme nhưng thư mục Video Meme chưa có video hợp lệ.')
    if options.use_meme_image:
        if not any(a.get('kind') == 'image' for a in all_assets):
            raise ValueError('Đang bật Ảnh Meme nhưng thư mục Ảnh Meme đang trống.')
        if not any(a.get('kind') == 'sound' for a in all_assets):
            raise ValueError('Đang bật Ảnh Meme nhưng thư mục Tiếng Meme đang trống.')
    elif options.use_meme_sound and not any(a.get('kind') == 'sound' for a in all_assets):
        raise ValueError('Đang bật Tiếng Meme nhưng thư mục Tiếng Meme đang trống.')


def enqueue_render_job(project: Project, max_active: int | None = None):
    validate_meme_selection(project.options)
    script_groups(project.comments, project.options)
    require_screenshots(project)
    project.options = batch_narration_options(project.options)
    executable('ffmpeg')
    executable('ffprobe')
    save_project(project)
    with lock:
        if max_active is not None:
            active = [read(p) for p in (DATA / 'jobs').glob('*/job.json')]
            if sum(j and j.get('status') in ('queued', 'running') for j in active) >= max_active:
                raise ValueError(f'Hàng đợi đã đủ {max_active} tác vụ. Chờ hoặc hủy bớt.')
        jid = uid()
        folder = DATA / 'jobs' / jid
        folder.mkdir()
        events[jid] = threading.Event()
        row = {
            'id': jid,
            'project_id': project.id,
            'name': project.name,
            'status': 'queued',
            'progress': 0,
            'message': 'Đang chờ dựng',
            'files': [],
            'created': time.time(),
        }
        write(folder / 'job.json', row)
    link_job_to_batches(project.id, jid)
    pool.submit(work, jid, project.model_copy(deep=True))
    return row


@app.post('/api/jobs')
def create_job(project: Project):
    return enqueue_render_job(project, max_active=100)


class RenderSavedRequest(BaseModel):
    use_preset: bool = True
    options: Options | None = None


def prepare_saved_project_for_render(pid: str, use_preset: bool = True, override_options: Options | None = None) -> Project:
    raw = read(DATA / 'projects' / f'{ident(pid)}.json')
    if raw is None:
        raise HTTPException(404, 'Không tìm thấy bài viết đã crawl.')
    project = Project(**migrate_project_dict(raw))
    if override_options is not None:
        opts = override_options.model_copy(deep=True)
    elif use_preset:
        opts = Options(**load_preset()['options'])
    else:
        opts = project.options.model_copy(deep=True)
    if opts.read_post and not project.post_image:
        opts.read_post = False
    selected = [c for c in project.comments if c.selected]
    if opts.split_mode == 'even' and selected and opts.video_count > len(selected):
        opts.video_count = len(selected)
    project.options = opts
    return project


@app.post('/api/projects/{pid}/render')
def render_saved_project(pid: str, body: RenderSavedRequest = RenderSavedRequest()):
    project = prepare_saved_project_for_render(pid, body.use_preset, body.options)
    return enqueue_render_job(project, max_active=None)


class BulkRenderSavedRequest(BaseModel):
    project_ids: list[str] = Field(min_length=1, max_length=500)
    use_preset: bool = True
    options: Options | None = None


@app.post('/api/projects/render-bulk')
def render_bulk_saved(body: BulkRenderSavedRequest):
    queued, failed = [], []
    for pid in body.project_ids:
        try:
            project = prepare_saved_project_for_render(pid, body.use_preset, body.options)
            row = enqueue_render_job(project, max_active=None)
            queued.append(row)
        except Exception as exc:
            failed.append({'project_id': pid, 'error': str(exc)})
    if not queued and failed:
        raise ValueError(failed[0]['error'])
    return {'queued_count': len(queued), 'failed': failed, 'jobs': queued}


@app.get('/api/jobs')
def jobs():
    rows = [read(p) for p in (DATA / 'jobs').glob('*/job.json')]
    return sorted([r for r in rows if r], key=lambda j: j['created'], reverse=True)[:100]


@app.get('/api/jobs/{jid}')
def job(jid: str):
    row = read(job_path(jid))
    if not row:
        raise HTTPException(404, 'Không tìm thấy job')
    return row


@app.post('/api/jobs/{jid}/cancel')
def cancel(jid: str):
    row = job(jid)
    if row['status'] in ('queued', 'running') and jid in events:
        events[jid].set()
    return {'ok': True}


@app.get('/api/jobs/{jid}/files/{name}')
def output_file(jid: str, name: str):
    row = job(jid)
    if name not in row['files']:
        raise HTTPException(404)
    folder = job_path(jid).parent
    manifest = read(folder / 'timeline.json', {}) or {}
    if name.endswith('.mp4') and manifest.get('output_project'):
        directory = manifest['output_project']
        if not re.fullmatch(r'project[1-9][0-9]*', directory):
            raise HTTPException(404)
        folder = DATA / 'output' / directory
    return FileResponse(folder / name, filename=name)


def batch_path(bid):
    return DATA / 'batches' / f'{ident(bid)}.json'


def update_batch(bid, fn=None, **changes):
    with batch_lock:
        row = read(batch_path(bid))
        if not row:
            return None
        if fn:
            fn(row)
        row.update(changes, updated=time.time())
        write(batch_path(bid), row)
        return row


class BatchCrawlRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=1000)
    limit: int = Field(default=30, ge=1, le=120)
    auto_render: bool = True
    options: Options = Field(default_factory=default_batch_options)


class BatchAppendRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=1000)


def run_batch(bid: str, body: BatchCrawlRequest):
    from collector import collect
    event = batch_events[bid]
    try:
        if event.is_set():
            raise InterruptedError('Đã hủy')
        update_batch(bid, status='running', message='Đang khởi động trình duyệt crawl…')
        index = 0
        while True:
            if event.is_set():
                raise InterruptedError('Đã hủy')
            with batch_lock:
                current_row = read(batch_path(bid), {}) or {}
                items = current_row.get('items', [])
                if index >= len(items):
                    break
                raw_url = items[index]['url']
                total_len = len(items)

            def mark_item(status, idx=index, **extra):
                def apply(row):
                    row['current_index'] = idx
                    row['items'][idx].update(status=status, **extra)
                    row['total'] = len(row['items'])
                    row['completed'] = sum(1 for it in row['items'] if it['status'] in ('done', 'failed'))
                return apply

            update_batch(
                bid,
                fn=mark_item('crawling', message='Đang mở bài viết và chụp thẻ bình luận thật…'),
                message=f'Đang crawl {index + 1}/{total_len}: {raw_url[:80]}',
            )
            if not crawl_lock.acquire(timeout=600):
                update_batch(bid, fn=mark_item('failed', message='Quá thời gian chờ khóa trình duyệt crawl.'))
                index += 1
                continue
            try:
                if event.is_set():
                    raise InterruptedError('Đã hủy')
                if login_process and login_process.poll() is None:
                    raise ValueError('Đóng cửa sổ Đăng nhập nguồn trước khi crawl.')

                def on_progress(state, idx=index):
                    seen = state.get('seen', 0)
                    cap = min(state.get('captured', 0), body.limit)
                    failed_shots = state.get('failed', 0)
                    with batch_lock:
                        r = read(batch_path(bid))
                        if not r:
                            return
                        t_len = len(r.get('items', []))
                    msg = f'Đã quét {seen} cmt · giữ {cap}/{body.limit} ảnh nhiều tim nhất'
                    if failed_shots:
                        msg += f' ({failed_shots} bỏ qua)'
                    update_batch(
                        bid,
                        fn=mark_item('crawling', idx=idx, seen=seen, captured=cap, message=msg),
                        message=f'Đang crawl {idx + 1}/{t_len} · {msg}',
                    )

                result = asyncio.run(collect(raw_url, body.limit, progress=on_progress))
                now_iso = datetime.now().astimezone().isoformat()
                today = local_date(now_iso)
                name = auto_project_name(result.get('post', ''), result.get('author', ''), result.get('url', raw_url))
                opts = body.options.model_copy(deep=True)
                if opts.read_post and not result.get('post_image'):
                    opts.read_post = False
                if opts.split_mode == 'even' and result['comments'] and opts.video_count > len(result['comments']):
                    opts.video_count = len(result['comments'])
                project = Project(
                    name=name,
                    url=result['url'],
                    post=result.get('post', ''),
                    author=result.get('author', ''),
                    post_image=result.get('post_image', ''),
                    post_captured_at=result.get('post_captured_at', ''),
                    post_capture_error=result.get('post_capture_error', ''),
                    comments=result['comments'],
                    options=opts,
                    crawl_note=result['crawl_note'],
                    crawled_at=now_iso,
                    crawl_date=today,
                )
                save_project(project)
                job_id = ''
                item_msg = f'Đã chụp {len(project.comments)} bình luận.'
                if body.auto_render:
                    if not project.comments:
                        item_msg = 'Không chụp được bình luận nào nên bỏ qua dựng video.'
                    else:
                        try:
                            job_row = enqueue_render_job(project, max_active=None)
                            job_id = job_row['id']
                            expected = len(script_groups(project.comments, project.options))
                            item_msg = f'Đã chụp {len(project.comments)} cmt · xếp hàng dựng {expected} video MP4.'
                        except Exception as render_exc:
                            item_msg = f'Đã crawl ({len(project.comments)} cmt), lỗi xếp hàng dựng: {render_exc}'
                update_batch(
                    bid,
                    fn=mark_item(
                        'done',
                        project_id=project.id,
                        name=project.name,
                        comment_count=len(project.comments),
                        job_id=job_id,
                        message=item_msg,
                    ),
                )
            except InterruptedError:
                raise
            except Exception as exc:
                err_msg = str(exc) if isinstance(exc, ValueError) else f'Không đọc được nguồn ({type(exc).__name__}).'
                update_batch(bid, fn=mark_item('failed', message=err_msg))
            finally:
                crawl_lock.release()
            index += 1

        final_row = read(batch_path(bid), {}) or {}
        items_final = final_row.get('items', [])
        ok_count = sum(1 for it in items_final if it['status'] == 'done')
        fail_count = sum(1 for it in items_final if it['status'] == 'failed')
        summary = f'Hoàn tất crawl {ok_count}/{len(items_final)} URL' + (f' · {fail_count} lỗi.' if fail_count else '.')
        update_batch(bid, status='done', message=summary)
    except InterruptedError:
        def cancel_remaining(row):
            for it in row.get('items', []):
                if it['status'] in ('queued', 'crawling'):
                    it.update(status='cancelled', message='Đã dừng theo yêu cầu.')
        update_batch(bid, fn=cancel_remaining, status='cancelled', message='Đã dừng lô crawl. Các bài đã xong vẫn được giữ nguyên.')
    except Exception as exc:
        update_batch(bid, status='failed', message=f'Lỗi tiến trình lô: {exc}')


@app.post('/api/batch-crawl/parse')
async def parse_batch_file(file: UploadFile = File(...)):
    raw = await file.read(2_000_000)
    if len(raw) >= 2_000_000:
        raise ValueError('Tệp .txt vượt giới hạn 2MB.')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('latin-1')
    urls, invalid = parse_url_lines(text)
    return {'urls': urls, 'invalid': invalid, 'count': len(urls)}


@app.post('/api/batch-crawl')
def start_batch_crawl(body: BatchCrawlRequest):
    cleaned = []
    seen = set()
    for u in body.urls:
        valid = source_url(u)
        if valid not in seen:
            seen.add(valid)
            cleaned.append(valid)
    if not cleaned:
        raise ValueError('Không có URL TikTok/Threads hợp lệ để crawl.')
    validate_meme_selection(body.options)
    body.urls = cleaned
    body.options = body.options.model_copy(update={'provider': 'elevenlabs'})
    save_preset_data(BulkPreset(limit=body.limit, auto_render=body.auto_render, options=body.options))
    if body.auto_render:
        body.options = batch_narration_options(body.options)
        executable('ffmpeg')
        executable('ffprobe')
        preflight_media_check(body.options)
    with batch_lock:
        ensure_directory(DATA / 'batches')
        active = [read(p) for p in (DATA / 'batches').glob('*.json')]
        if sum(1 for b in active if b and b.get('status') in ('queued', 'running')) >= 20:
            raise HTTPException(409, 'Hàng đợi lô đã đầy (tối đa 20 lô).')
        bid = uid()
        batch_events[bid] = threading.Event()
        row = {
            'id': bid,
            'status': 'queued',
            'created': time.time(),
            'updated': time.time(),
            'crawl_date': local_date(),
            'limit': body.limit,
            'auto_render': body.auto_render,
            'split_mode': body.options.split_mode,
            'comments_per_video': body.options.comments_per_video,
            'video_count': body.options.video_count,
            'total': len(cleaned),
            'completed': 0,
            'current_index': 0,
            'message': f'Đang chờ xử lý {len(cleaned)} URL…',
            'items': [
                {
                    'url': u,
                    'status': 'queued',
                    'message': 'Đang chờ trong hàng đợi',
                    'project_id': '',
                    'name': '',
                    'comment_count': 0,
                    'job_id': '',
                }
                for u in cleaned
            ],
        }
        write(batch_path(bid), row)
    batch_pool.submit(run_batch, bid, body.model_copy(deep=True))
    return row


@app.post('/api/batch-crawl/{bid}/append')
def append_batch_urls(bid: str, body: BatchAppendRequest):
    cleaned = []
    seen_new = set()
    for u in body.urls:
        valid = source_url(u)
        if valid not in seen_new:
            seen_new.add(valid)
            cleaned.append(valid)
    if not cleaned:
        raise ValueError('Không có URL hợp lệ để thêm.')
    with batch_lock:
        row = read(batch_path(bid))
        if not row:
            raise HTTPException(404, 'Không tìm thấy lô crawl.')
        if row.get('status') not in ('queued', 'running'):
            raise ValueError('Lô này đã kết thúc. Hãy bấm Bắt đầu sản xuất để tạo lô mới.')
        existing_urls = {it['url'] for it in row.get('items', [])}
        added = [u for u in cleaned if u not in existing_urls]
        if len(row.get('items', [])) + len(added) > 1000:
            raise ValueError('Mỗi lô tối đa 1000 URL.')
        for u in added:
            row['items'].append({
                'url': u,
                'status': 'queued',
                'message': 'Mới thêm vào hàng đợi',
                'project_id': '',
                'name': '',
                'comment_count': 0,
                'job_id': '',
            })
        row['total'] = len(row['items'])
        row['updated'] = time.time()
        write(batch_path(bid), row)
    return {'added': len(added), 'skipped_duplicates': len(cleaned) - len(added), 'total': row['total']}


@app.get('/api/batch-crawl')
def list_batches():
    rows = [read(p) for p in (DATA / 'batches').glob('*.json')]
    return sorted([r for r in rows if r], key=lambda b: b['created'], reverse=True)[:30]


@app.get('/api/batch-crawl/{bid}')
def get_batch(bid: str):
    row = read(batch_path(bid))
    if not row:
        raise HTTPException(404, 'Không tìm thấy lô crawl.')
    jobs_map = {j['id']: j for j in (read(p) for p in (DATA / 'jobs').glob('*/job.json')) if j}
    for item in row.get('items', []):
        jid = item.get('job_id')
        if jid and jid in jobs_map:
            item['job'] = job_public_summary(jobs_map[jid])
    return row


@app.post('/api/batch-crawl/{bid}/cancel')
def cancel_batch(bid: str):
    row = read(batch_path(bid))
    if not row:
        raise HTTPException(404, 'Không tìm thấy lô crawl.')
    if row['status'] in ('queued', 'running') and bid in batch_events:
        batch_events[bid].set()
    return {'ok': True}


app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765)
