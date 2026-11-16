import asyncio
from datetime import datetime
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

from core import (DATA, ROOT, Project, Options, assets, asset, ident, read, write, uid, probe,
                  executable, source_url, project_folder, snapshot_project, script_groups,
                  ensure_directory, require_screenshots, auto_project_name, local_date,
                  infer_crawl_date, parse_url_lines)
from speech import public_settings, save_settings, synthesize, narration_options, batch_narration_options
from render import render, card, credit_image, credit_position

pool = ThreadPoolExecutor(max_workers=1)
batch_pool = ThreadPoolExecutor(max_workers=1)
events, batch_events, lock, batch_lock = {}, {}, threading.Lock(), threading.Lock()
crawl_lock = threading.Lock()
project_lock = threading.Lock()
login_process = None
crawl_state = {'status': 'idle', 'seen': 0, 'captured': 0, 'failed': 0}


@asynccontextmanager
async def lifespan(app):
    for path in (DATA / 'jobs').glob('*/job.json'):
        row = read(path)
        if row['status'] in ('queued', 'running'):
            row.update(status='interrupted', message='Ứng dụng đã tắt giữa lúc dựng. Mở dự án rồi dựng lại.')
            write(path, row)
    for path in (DATA / 'batches').glob('*.json'):
        row = read(path)
        if row and row.get('status') in ('queued', 'running'):
            for item in row.get('items', []):
                if item.get('status') in ('queued', 'crawling', 'rendering'):
                    item.update(status='interrupted', message='Ứng dụng đã tắt giữa chừng.')
            row.update(status='interrupted', message='Ứng dụng đã tắt giữa lúc crawl lô.')
            write(path, row)
    yield
    for event in events.values(): event.set()
    for event in batch_events.values(): event.set()


app = FastAPI(title='CommentCut', lifespan=lifespan)


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
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    errors = [{'field': '.'.join(map(str, error['loc'][1:])), 'message': error['msg']}
              for error in exc.errors()]
    # Record field constraints only, never request values or API credentials.
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
    return {'ok': True, 'ffmpeg': ffmpeg, 'data': str(DATA)}


@app.get('/api/assets')
def list_assets():
    return assets()


@app.post('/api/demo-assets')
def demo_assets():
    from demo import make_demo
    return make_demo()


@app.post('/api/assets/{kind}')
def upload(kind: str, file: UploadFile = File(...)):
    if kind not in ('background', 'image', 'sound'):
        raise ValueError('Loại tài sản không hợp lệ')
    suffix = Path(file.filename or '').suffix.lower()
    allowed = {'background': {'.mp4', '.mov', '.mkv', '.webm'},
               'image': {'.png', '.jpg', '.jpeg', '.webp'}, 'sound': {'.mp3', '.wav', '.ogg', '.m4a'}}
    if suffix not in allowed[kind]:
        raise ValueError('Định dạng tệp không hỗ trợ.')
    aid = uid()
    target = ensure_directory(DATA / 'assets') / (aid + suffix)
    size = 0
    try:
        with target.open('wb') as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 500_000_000: raise ValueError('Tệp vượt giới hạn 500MB')
                out.write(chunk)
        row = {'id': aid, 'kind': kind, 'name': Path(file.filename).name[:150], 'file': target.name, 'bytes': size}
        if kind == 'image':
            with Image.open(target) as im:
                if im.width * im.height > 30_000_000: raise ValueError('Ảnh vượt 30 megapixel')
                im.verify()
        else:
            info = probe(target)
            required = 'video' if kind == 'background' else 'audio'
            if not any(s['codec_type'] == required for s in info['streams']): raise ValueError('Tệp không có track cần thiết.')
            row['duration'] = float(info['format']['duration'])
        write(DATA / 'assets' / (aid + '.json'), row)
        return row
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        target.unlink(missing_ok=True)
        raise ValueError('Ảnh không hợp lệ hoặc quá lớn.') from None
    except Exception:
        target.unlink(missing_ok=True)
        raise


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


def project_summary(path: Path, jobs_map: dict):
    row = read(path, {})
    comments = row.get('comments') or []
    job_row = jobs_map.get(path.stem)
    return {
        'id': path.stem,
        'name': row.get('name', 'Video chưa đặt tên'),
        'url': row.get('url', ''),
        'author': row.get('author', ''),
        'post': row.get('post', '')[:200],
        'comment_count': len(comments),
        'selected_count': sum(1 for c in comments if c.get('selected', True)),
        'crawled_at': row.get('crawled_at', ''),
        'crawl_date': infer_crawl_date(row),
        'updated': path.stat().st_mtime,
        'job': ({
            'id': job_row['id'],
            'status': job_row['status'],
            'progress': job_row.get('progress', 0),
            'message': job_row.get('message', ''),
            'files': [f for f in job_row.get('files', []) if f.endswith('.mp4')],
        } if job_row else None),
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
        if not summary['crawl_date']:
            continue
        grouped.setdefault(summary['crawl_date'], []).append(summary)
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
        saved = read(DATA / 'projects' / f'{project.id}.json', {})
        if not project.crawled_at and saved.get('crawled_at'):
            project.crawled_at = saved['crawled_at']
        if not project.crawl_date:
            project.crawl_date = saved.get('crawl_date') or infer_crawl_date(project.model_dump())
        # A failed recrawl or a stale tab can submit empty capture fields.
        current_source = project.url.split('#', 1)[0].split('?', 1)[0].rstrip('/')
        saved_image = saved.get('post_image')
        metadata = read(DATA / 'assets' / f'{ident(saved_image)}.json', {}) if saved_image else {}
        saved_url = metadata.get('source_url') or saved.get('url', '')
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
    if row is None: raise HTTPException(404, 'Không tìm thấy dự án')
    return row


class CrawlRequest(BaseModel):
    url: str = Field(max_length=2000)
    limit: int = Field(default=30, ge=1, le=120)
    project_id: str | None = None


@app.post('/api/crawl')
def crawl(body: CrawlRequest):
    from collector import collect
    source_url(body.url)
    if body.project_id: ident(body.project_id)
    if not crawl_lock.acquire(blocking=False): raise HTTPException(409, 'Đang lấy dữ liệu nguồn khác.')
    try:
        if login_process and login_process.poll() is None:
            raise ValueError('Đóng cửa sổ Đăng nhập nguồn trước khi crawl.')
        crawl_state.update(status='running', seen=0, captured=0, failed=0,
                           last_error='', limit=body.limit, started=time.time())
        result = asyncio.run(collect(body.url, body.limit, progress=crawl_state.update))
        now_iso = datetime.now().astimezone().isoformat()
        today = local_date(now_iso)
        suggested_name = auto_project_name(result.get('post', ''), result.get('author', ''), result.get('url', body.url))
        result.update(crawled_at=now_iso, crawl_date=today, suggested_name=suggested_name)
        if body.project_id:
            existing = read(DATA / 'projects' / f'{body.project_id}.json', {})
            current_name = str(existing.get('name') or '').strip()
            if not current_name or current_name == 'Video chưa đặt tên':
                existing['name'] = suggested_name
            existing.update(id=body.project_id, url=result['url'], post=result.get('post', ''),
                            author=result.get('author', ''), post_image=result.get('post_image',''),
                            post_captured_at=result.get('post_captured_at',''), post_capture_error=result.get('post_capture_error',''),
                            comments=result['comments'], crawl_note=result['crawl_note'],
                            crawled_at=now_iso, crawl_date=today)
            project = Project(**existing)
            save_project(project)
            result['name'] = project.name
            if project.post_image and not result.get('post_image'):
                result.update(post=project.post, author=project.author, post_image=project.post_image,
                              post_captured_at=project.post_captured_at, post_capture_error='',
                              crawl_note=project.crawl_note)
        crawl_state.update(status='done', captured=len(result['comments']), message=result['crawl_note'])
        return result
    except ValueError as exc:
        crawl_state.update(status='failed', message=str(exc))
        raise
    except Exception as exc:
        crawl_state.update(status='failed', message=f'Không đọc được nguồn ({type(exc).__name__}).')
        raise ValueError(f'Không đọc được nguồn ({type(exc).__name__}). Dùng Đăng nhập nguồn hoặc nhập bình luận thủ công.') from None
    finally:
        crawl_lock.release()


@app.get('/api/crawl-status')
def crawl_status():
    return dict(crawl_state)


@app.post('/api/login/{platform}')
def login(platform: str):
    global login_process
    if platform not in ('tiktok', 'threads'): raise ValueError('Nguồn không hợp lệ')
    if crawl_lock.locked(): raise ValueError('Chờ crawl hoàn thành trước khi đăng nhập.')
    if login_process and login_process.poll() is None: raise ValueError('Cửa sổ đăng nhập đang mở.')
    if getattr(sys, 'frozen', False):
        command = [sys.executable, '--login', platform]
        env = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
    else:
        command = [sys.executable, str(ROOT / 'collector.py'), platform]
        env = None
    login_process = subprocess.Popen(command, cwd=DATA, env=env,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {'message': 'Đăng nhập trong cửa sổ Chrome riêng rồi đóng cửa sổ đó để tiếp tục crawl.'}


@app.get('/api/settings')
def config(): return public_settings()


@app.post('/api/settings')
def config_save(values: dict):
    save_settings(values)
    return public_settings()


class VoiceRequest(BaseModel):
    voice_index: int = Field(default=0, ge=0, le=119)
    text: str = Field(default='Xin chào, cùng đọc bình luận hôm nay nhé.', min_length=1, max_length=250)
    options: Options = Field(default_factory=Options)


@app.post('/api/voice-preview')
def voice_preview(body: VoiceRequest):
    if body.options.provider == 'elevenlabs' and body.voice_index >= len(body.options.elevenlabs_voices):
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
        Image.new('RGBA', (project.options.resolution, project.options.resolution*16//9)).save(path)
    watermark = credit_image(project.options)
    if watermark is not None:
        with Image.open(path) as preview:
            x, y = credit_position(preview.width, preview.height, watermark.width, watermark.height, 0)
            preview.alpha_composite(watermark, (round(x), round(y)))
            preview.save(path)
    return FileResponse(path, media_type='image/png', background=__import__('starlette.background', fromlist=['BackgroundTask']).BackgroundTask(path.unlink, missing_ok=True))


def job_path(jid): return DATA / 'jobs' / ident(jid) / 'job.json'


def update_job(jid, **changes):
    with lock:
        row = read(job_path(jid))
        row.update(changes, updated=time.time())
        write(job_path(jid), row)


def work(jid, project):
    event = events[jid]
    try:
        if event.is_set(): raise InterruptedError('Đã hủy')
        update_job(jid, status='running', message='Chuẩn bị dựng')
        def progress(percent, message):
            published = read(job_path(jid).parent / 'timeline.json', {}).get('files', [])
            update_job(jid, progress=percent, message=message, files=published)
        files = render(project, job_path(jid).parent, progress, event.is_set)
        if event.is_set(): raise InterruptedError('Đã hủy')
        update_job(jid, status='done', files=files, progress=100, message='Hoàn tất')
    except InterruptedError:
        update_job(jid, status='cancelled', message='Đã hủy. Dự án vẫn được lưu.')
    except Exception as exc:
        import traceback
        (job_path(jid).parent / 'error.log').write_text(traceback.format_exc(), 'utf-8')
        message = str(exc) if isinstance(exc, ValueError) else f'Lỗi dựng: {type(exc).__name__}. Kiểm tra media và cấu hình.'
        update_job(jid, status='failed', message=message)


def enqueue_render_job(project: Project, max_active: int | None = 5):
    script_groups(project.comments, project.options)
    require_screenshots(project)
    project.options = batch_narration_options(project.options)
    executable('ffmpeg'); executable('ffprobe')
    save_project(project)
    with lock:
        if max_active is not None:
            active = [read(p) for p in (DATA / 'jobs').glob('*/job.json')]
            if sum(j['status'] in ('queued', 'running') for j in active) >= max_active:
                raise ValueError(f'Hàng đợi đã đủ {max_active} dự án. Chờ hoặc hủy bớt.')
        jid = uid()
        folder = DATA / 'jobs' / jid
        folder.mkdir()
        events[jid] = threading.Event()
        row = {'id': jid, 'project_id': project.id, 'name': project.name, 'status': 'queued', 'progress': 0,
               'message': 'Đang chờ', 'files': [], 'created': time.time()}
        write(folder / 'job.json', row)
    pool.submit(work, jid, project.model_copy(deep=True))
    return row


@app.post('/api/jobs')
def create_job(project: Project):
    return enqueue_render_job(project, max_active=5)


@app.get('/api/jobs')
def jobs():
    return sorted([read(p) for p in (DATA / 'jobs').glob('*/job.json')], key=lambda j: j['created'], reverse=True)[:50]


@app.get('/api/jobs/{jid}')
def job(jid: str):
    row = read(job_path(jid))
    if not row: raise HTTPException(404, 'Không tìm thấy job')
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
    if name not in row['files']: raise HTTPException(404)
    folder = job_path(jid).parent
    manifest = read(folder / 'timeline.json', {})
    if name.endswith('.mp4') and manifest.get('output_project'):
        directory = manifest['output_project']
        if not __import__('re').fullmatch(r'project[1-9][0-9]*', directory): raise HTTPException(404)
        folder = DATA / 'output' / directory
    return FileResponse(folder / name, filename=name)


def batch_path(bid):
    return DATA / 'batches' / f'{ident(bid)}.json'


def update_batch(bid, fn=None, **changes):
    with batch_lock:
        row = read(batch_path(bid))
        if fn:
            fn(row)
        row.update(changes, updated=time.time())
        write(batch_path(bid), row)
        return row


def default_batch_options():
    return Options(provider='elevenlabs', split_mode='comments', comments_per_video=10, video_count=3)


class BatchCrawlRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=200)
    limit: int = Field(default=30, ge=1, le=120)
    auto_render: bool = True
    options: Options = Field(default_factory=default_batch_options)


def run_batch(bid: str, body: BatchCrawlRequest):
    from collector import collect
    event = batch_events[bid]
    try:
        if event.is_set():
            raise InterruptedError('Đã hủy')
        update_batch(bid, status='running', message=f'Đang chuẩn bị crawl {len(body.urls)} link…')
        for index, raw_url in enumerate(body.urls):
            if event.is_set():
                raise InterruptedError('Đã hủy')
            def mark_item(status, **extra):
                def apply(row):
                    row['current_index'] = index
                    row['items'][index].update(status=status, **extra)
                    row['completed'] = sum(1 for it in row['items'] if it['status'] in ('done', 'failed'))
                return apply

            update_batch(bid, fn=mark_item('crawling', message='Đang mở nguồn và chụp bình luận…'),
                         message=f'Đang crawl {index + 1}/{len(body.urls)}: {raw_url[:70]}')
            if not crawl_lock.acquire(timeout=600):
                update_batch(bid, fn=mark_item('failed', message='Quá thời gian chờ khóa trình duyệt crawl.'))
                continue
            try:
                if event.is_set():
                    raise InterruptedError('Đã hủy')
                if login_process and login_process.poll() is None:
                    raise ValueError('Đóng cửa sổ Đăng nhập nguồn trước khi crawl.')
                crawl_state.update(status='running', seen=0, captured=0, failed=0,
                                   last_error='', limit=body.limit, started=time.time(),
                                   batch_id=bid, batch_index=index + 1, batch_total=len(body.urls))
                def on_progress(state):
                    crawl_state.update(state)
                    seen = crawl_state.get('seen', 0)
                    cap = min(crawl_state.get('captured', 0), body.limit)
                    update_batch(bid, fn=mark_item('crawling',
                                 seen=seen, captured=cap,
                                 message=f'Đã đọc {seen} cmt · giữ {cap}/{body.limit} ảnh'))
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
                crawl_state.update(status='done', captured=len(project.comments), message=result['crawl_note'])
                job_id = ''
                item_msg = f'Đã lấy {len(project.comments)} bình luận.'
                if body.auto_render:
                    if not project.comments:
                        item_msg = 'Chưa có bình luận chụp được nên bỏ qua dựng video.'
                    else:
                        try:
                            job_row = enqueue_render_job(project, max_active=None)
                            job_id = job_row['id']
                            expected = len(script_groups(project.comments, project.options))
                            item_msg = f'Đã lấy {len(project.comments)} bình luận · đang dựng {expected} video.'
                        except Exception as render_exc:
                            item_msg = f'Đã crawl ({len(project.comments)} cmt), lỗi xếp hàng dựng: {render_exc}'
                update_batch(bid, fn=mark_item('done',
                             project_id=project.id, name=project.name,
                             comment_count=len(project.comments), job_id=job_id, message=item_msg))
            except InterruptedError:
                crawl_state.update(status='idle')
                raise
            except Exception as exc:
                err_msg = str(exc) if isinstance(exc, ValueError) else f'Không đọc được nguồn ({type(exc).__name__}).'
                crawl_state.update(status='failed', message=err_msg)
                update_batch(bid, fn=mark_item('failed', message=err_msg))
            finally:
                crawl_lock.release()
        final_row = read(batch_path(bid), {})
        ok_count = sum(1 for it in final_row.get('items', []) if it['status'] == 'done')
        fail_count = sum(1 for it in final_row.get('items', []) if it['status'] == 'failed')
        summary = f'Hoàn tất {ok_count}/{len(body.urls)} link' + (f' ({fail_count} lỗi).' if fail_count else '.')
        update_batch(bid, status='done', message=summary)
    except InterruptedError:
        def cancel_remaining(row):
            for it in row.get('items', []):
                if it['status'] in ('queued', 'crawling'):
                    it.update(status='cancelled', message='Đã hủy theo yêu cầu.')
        update_batch(bid, fn=cancel_remaining, status='cancelled', message='Đã dừng crawl hàng loạt. Các dự án đã xong vẫn được giữ.')
    except Exception as exc:
        update_batch(bid, status='failed', message=f'Lỗi lô crawl: {exc}')


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
    body.urls = cleaned
    body.options = body.options.model_copy(update={'provider': 'elevenlabs'})
    if body.auto_render:
        body.options = batch_narration_options(body.options)
        executable('ffmpeg'); executable('ffprobe')
        backgrounds = [a for a in assets() if a.get('source_folder') == 'Vid_nen']
        if not body.options.background and not backgrounds:
            raise ValueError('Thêm ít nhất một video nền vào data/Vid_nen trước khi bật tự động render.')
    with batch_lock:
        ensure_directory(DATA / 'batches')
        active = [read(p) for p in (DATA / 'batches').glob('*.json')]
        if any(b and b.get('status') in ('queued', 'running') for b in active):
            raise HTTPException(409, 'Đang có một tiến trình crawl hàng loạt đang chạy.')
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
            'message': f'Đang chờ xử lý {len(cleaned)} link…',
            'items': [{'url': u, 'status': 'queued', 'message': 'Đang chờ', 'project_id': '', 'name': '', 'comment_count': 0, 'job_id': ''}
                      for u in cleaned],
        }
        write(batch_path(bid), row)
    batch_pool.submit(run_batch, bid, body.model_copy(deep=True))
    return row


@app.get('/api/batch-crawl')
def list_batches():
    rows = [read(p) for p in (DATA / 'batches').glob('*.json')]
    return sorted([r for r in rows if r], key=lambda b: b['created'], reverse=True)[:20]


@app.get('/api/batch-crawl/{bid}')
def get_batch(bid: str):
    row = read(batch_path(bid))
    if not row:
        raise HTTPException(404, 'Không tìm thấy lô crawl.')
    jobs_map = {j['id']: j for j in (read(p) for p in (DATA / 'jobs').glob('*/job.json')) if j}
    for item in row.get('items', []):
        jid = item.get('job_id')
        if jid and jid in jobs_map:
            j = jobs_map[jid]
            item['job'] = {
                'id': j['id'],
                'status': j['status'],
                'progress': j.get('progress', 0),
                'message': j.get('message', ''),
                'files': [f for f in j.get('files', []) if f.endswith('.mp4')],
            }
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
def index(): return FileResponse(ROOT / 'static' / 'index.html')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765)
