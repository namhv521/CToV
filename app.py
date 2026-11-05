import asyncio
import json
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

from core import DATA, ROOT, Project, Options, assets, asset, ident, read, write, uid, probe, executable, source_url, project_folder, snapshot_project, script_groups, ensure_directory, require_screenshots
from speech import public_settings, save_settings, synthesize, narration_options
from render import render, card, credit_image, credit_position

pool = ThreadPoolExecutor(max_workers=1)
events, lock = {}, threading.Lock()
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
    yield
    for event in events.values(): event.set()


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


@app.get('/api/projects')
def projects():
    return sorted([{'id': p.stem, 'name': read(p)['name'], 'updated': p.stat().st_mtime}
                   for p in (DATA / 'projects').glob('*.json')], key=lambda p: p['updated'], reverse=True)


@app.post('/api/projects')
def save_project(project: Project):
    with project_lock:
        saved = read(DATA / 'projects' / f'{project.id}.json', {})
        # A tab opened before capture must not erase the captured original.
        if (not project.post_image and saved.get('post_image')
                and project.url == saved.get('url') and project.post == saved.get('post')):
            project.post_image = saved['post_image']
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
    limit: int = Field(default=120, ge=1, le=120)
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
        crawl_state.update(status='done', captured=len(result['comments']), message=result['crawl_note'])
        if body.project_id:
            existing = read(DATA / 'projects' / f'{body.project_id}.json', {})
            existing.update(id=body.project_id, url=result['url'], post=result.get('post', ''),
                            author=result.get('author', ''), post_image=result.get('post_image',''),
                            post_captured_at=result.get('post_captured_at',''), post_capture_error=result.get('post_capture_error',''), comments=result['comments'], crawl_note=result['crawl_note'])
            save_project(Project(**existing))
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
    login_process = subprocess.Popen([sys.executable, str(ROOT / 'collector.py'), platform], cwd=ROOT,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {'message': 'Đăng nhập trong cửa sổ Chrome riêng rồi đóng cửa sổ đó để tiếp tục crawl.'}


@app.get('/api/settings')
def config(): return public_settings()


@app.post('/api/settings')
def config_save(values: dict):
    save_settings(values)
    return public_settings()


class VoiceRequest(BaseModel):
    voice_index: int = Field(default=0, ge=0, le=2)
    text: str = Field(default='Xin chào, cùng đọc bình luận hôm nay nhé.', min_length=1, max_length=250)
    options: Options = Field(default_factory=Options)


@app.post('/api/voice-preview')
def voice_preview(body: VoiceRequest):
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


@app.post('/api/jobs')
def create_job(project: Project):
    script_groups(project.comments, project.options)
    narration_options(project.options)
    require_screenshots(project)
    executable('ffmpeg'); executable('ffprobe')
    save_project(project)
    with lock:
        active = [read(p) for p in (DATA / 'jobs').glob('*/job.json')]
        if sum(j['status'] in ('queued', 'running') for j in active) >= 5:
            raise ValueError('Hàng đợi đã đủ 5 dự án. Chờ hoặc hủy bớt.')
        jid = uid()
        folder = DATA / 'jobs' / jid
        folder.mkdir()
        events[jid] = threading.Event()
        row = {'id': jid, 'project_id': project.id, 'name': project.name, 'status': 'queued', 'progress': 0,
               'message': 'Đang chờ', 'files': [], 'created': time.time()}
        write(folder / 'job.json', row)
    pool.submit(work, jid, project.model_copy(deep=True))
    return row


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


app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.get('/')
def index(): return FileResponse(ROOT / 'static' / 'index.html')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765)
