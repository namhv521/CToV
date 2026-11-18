"""Bounded public collection. Uses a separate profile; no CAPTCHA bypass."""
import asyncio
import sys
import re
import time
from urllib.parse import urlsplit

from core import DATA, ROOT, source_url
from capture import capture_comment, comment_element, dismiss_capture_overlays, TIKTOK_DOM, capture_original_post


def comment_key(row):
    text = str(row.get('text') or '').strip()
    media_id = row.get('comment_url') or row.get('id') or row.get('image')
    content = text or ('media:' + str(media_id) if media_id and (row.get('has_media') or row.get('image')) else '')
    return (str(row.get('author') or 'Người dùng').strip(), content)


def normalize(rows, limit=120):
    result, seen = [], set()
    for row in rows:
        text = str(row.get('text') or '').strip()
        author = str(row.get('author') or 'Người dùng').strip()
        key = comment_key(row)
        if not key[1] or key in seen:
            continue
        seen.add(key)
        likes = row.get('likes') or 0
        try:
            likes = max(0, int(likes))
        except (ValueError, TypeError):
            likes = 0
        result.append({'id': str(row.get('id') or len(result)), 'author': author[:100],
                       'text': text[:1500], 'likes': likes,
                       **{k: row[k] for k in ('image', 'capture_text', 'captured_at', 'source_url',
                                             'comment_url', 'likes_display') if k in row}})
        if len(result) >= limit:
            break
    return result


def top_comments(rows, limit=120):
    """Rank the entire observed set before applying the output cap."""
    unique = normalize(rows, limit=max(1, len(rows)))
    return sorted(unique, key=lambda row: row['likes'], reverse=True)[:limit]


def extract_tiktok(data, video_id=''):
    """Accept comment-list payloads only, not unrelated recommended videos."""
    rows = []
    for c in data.get('comments') or []:
        if not isinstance(c, dict):
            continue
        if video_id and str(c.get('aweme_id', video_id)) != video_id:
            continue
        user = c.get('user') or {}
        rows.append({'id': c.get('cid'), 'author': user.get('nickname') or user.get('unique_id'),
                     'text': c.get('text'), 'likes': c.get('digg_count', 0)})
    return rows


def threads_post(node):
    caption = node.get('caption') or {}
    return {'id': str(node.get('pk') or node.get('id') or ''),
            'author': (node.get('user') or {}).get('username', ''),
            'text': caption.get('text') or node.get('text', ''), 'likes': node.get('like_count', 0)}


def extract_threads(data, code):
    """Read only the exact root and items with an explicit reply relationship."""
    roots, replies = [], []
    def walk(node):
        if isinstance(node, dict):
            if node.get('code') == code and node.get('user'):
                roots.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(data)
    root_ids = {str(n.get('pk') or n.get('id')) for n in roots}
    def contained_posts(thread):
        if not isinstance(thread, dict): return []
        return [item.get('post', {}) for item in thread.get('thread_items', []) if isinstance(item, dict)]
    def reply_walk(node):
        if isinstance(node, dict):
            info = node.get('text_post_app_info') or {}
            parent = node.get('in_reply_to_id') or info.get('reply_to_id') or info.get('direct_reply_to_id')
            parent_post = info.get('reply_to_post') or {}
            if not parent and isinstance(parent_post, dict):
                parent = parent_post.get('pk') or parent_post.get('id')
            if str(parent) in root_ids and node.get('user'):
                replies.append(threads_post(node))
            # Threads GraphQL nests reply_threads alongside containing_thread.
            containing = contained_posts(node.get('containing_thread'))
            if any(p.get('code') == code or str(p.get('pk') or p.get('id')) in root_ids for p in containing):
                for thread in node.get('reply_threads') or []:
                    for reply in contained_posts(thread):
                        if reply.get('user') and reply.get('code') != code:
                            replies.append(threads_post(reply))
            # Explicit target thread containers returned by Threads GraphQL.
            for key in ('reply_threads', 'replies'):
                if key in node and (node.get('code') == code or str(node.get('pk') or node.get('id')) in root_ids):
                    def collect(items):
                        if isinstance(items, dict):
                            if items.get('user') and (items.get('caption') or items.get('text')):
                                replies.append(threads_post(items))
                            else:
                                for v in items.values(): collect(v)
                        elif isinstance(items, list):
                            for v in items: collect(v)
                    collect(node[key])
            for value in node.values(): reply_walk(value)
        elif isinstance(node, list):
            for value in node: reply_walk(value)
    reply_walk(data)
    return (threads_post(roots[0]) if roots else {}), replies


async def configure_capture_zoom(context):
    """Magnify source content without native-zoom screenshot coordinate changes."""
    settings_page = await context.new_page()
    try:
        await settings_page.goto('chrome://settings/appearance', wait_until='domcontentloaded')
        await settings_page.evaluate("""() => new Promise((resolve,reject) => {
          chrome.settingsPrivate.setDefaultZoom(1, () => {
            if(chrome.runtime.lastError)reject(Error(chrome.runtime.lastError.message));
            else resolve();
          });
        })""")
    finally:
        await settings_page.close()
    await context.add_init_script("""(() => {
      const apply=()=>{if(document.documentElement)document.documentElement.style.zoom='1.25';};
      apply();
      document.addEventListener('DOMContentLoaded',apply,{once:true});
    })();""")


def browser_options():
    return {'channel': 'chromium' if getattr(sys, 'frozen', False) else 'chrome'}


async def collect(url, limit=30, headless=True, progress=None):
    from playwright.async_api import Error as PlaywrightError, async_playwright
    if not 1 <= limit <= 120:
        raise ValueError('Giới hạn bình luận phải từ 1 đến 120.')
    url = source_url(url)
    platform = 'tiktok' if 'tiktok.com' in urlsplit(url).hostname else 'threads'
    comments, post, pending = [], {}, []
    captured, capture_keys, failures = [], set(), set()
    last_capture_error = ''
    scanned_keys = set()
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(str(DATA / 'profile'), **browser_options(),
                       headless=headless, viewport={'width': 1280, 'height': 1000},
                       device_scale_factor=2, color_scheme='light', accept_downloads=False)
        except Exception:
            raise ValueError('Không mở được trình duyệt hoặc hồ sơ đăng nhập đang được dùng. Đóng cửa sổ Đăng nhập nguồn rồi thử lại.') from None
        try:
            await configure_capture_zoom(context)
            page = await context.new_page()
            # Only social-platform HTTPS navigations; no local-network redirects/subresources.
            async def route(req):
                target = urlsplit(req.request.url)
                host = target.hostname or ''
                allowed = ('tiktok.com', 'tiktokcdn.com', 'tiktokv.com', 'byteoversea.com', 'ibytedtos.com',
                           'ibyteimg.com', 'ttwstatic.com', 'threads.net', 'threads.com', 'instagram.com',
                           'cdninstagram.com', 'fbcdn.net', 'facebook.com')
                if target.scheme == 'https' and any(host == d or host.endswith('.' + d) for d in allowed):
                    await req.continue_()
                else:
                    await req.abort()
            await context.route('**/*', route)
            match = re.search(r'/video/(\d+)', url)
            video_id = match.group(1) if match else ''
            match = re.search(r'/(?:post|t)/([^/?]+)', url)
            code = match.group(1) if match else ''
            async def response(r):
                nonlocal post
                if 'json' not in r.headers.get('content-type', '') and 'graphql' not in r.url:
                    return
                if int(r.headers.get('content-length', '0') or 0) > 8_000_000:
                    return
                try:
                    import json
                    raw = await r.text()
                    data = json.loads(raw.removeprefix('for (;;);'))
                    if not isinstance(data, dict): return
                    if platform == 'tiktok' and '/comment/list' in r.url:
                        comments.extend(extract_tiktok(data, video_id))
                    elif platform == 'threads' and ('graphql' in r.url or '/api/' in r.url):
                        found, rows = extract_threads(data, code)
                        if found: post = found
                        comments.extend(rows)
                except Exception:
                    pass
            def on_response(r):
                task = asyncio.create_task(response(r)); pending.append(task)
            page.on('response', on_response)
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            final = source_url(page.url)
            match = re.search(r'/video/(\d+)', final)
            video_id = match.group(1) if match else ''
            match = re.search(r'/(?:post|t)/([^/?]+)', final)
            code = match.group(1) if match else ''
            original = None
            original_error = ''
            try:
                original = await capture_original_post(page, final)
            except (ValueError, PlaywrightError) as exc:
                original_error = str(exc)
            deadline = time.monotonic() + 600
            previous, stable = 0, 0
            # Do not stop on the first 30: later pages can contain more-liked comments.
            while time.monotonic() < deadline:
                await page.wait_for_timeout(1000)
                await dismiss_capture_overlays(page)
                if platform == 'tiktok':
                    # Visible comment elements only, scoped by platform data-e2e attributes.
                    rows = await page.locator('[data-e2e="comment-item"]').evaluate_all(TIKTOK_DOM)
                    desc = page.locator('[data-e2e="browse-video-desc"]').first
                    if await desc.count(): post['text'] = await desc.inner_text()
                else:
                    # Read SSR JSON using the same exact-root extractor.
                    for raw in await page.locator('script[type="application/json"]').all_text_contents():
                        import json
                        try:
                            found, rows = extract_threads(json.loads(raw), code)
                            if found: post = found
                            comments.extend(rows)
                        except (ValueError, TypeError): pass
                    rows = await page.evaluate((ROOT / 'threads_dom.js').read_text('utf-8'), code)
                # Keep a rolling top set while elements are still available to photograph.
                # Platform sorting is not assumed to be a strict order by likes.
                exact_likes = {(r['author'], r['text']): r['likes']
                               for r in normalize(comments, limit=max(1, len(comments)))}
                for row in rows:
                    key = (str(row.get('author') or '').strip(), str(row.get('text') or '').strip())
                    if key in exact_likes:
                        row['likes'] = exact_likes[key]
                anchor = rows[-1] if rows else None
                # Capture in DOM order so scrolling does not recycle later targets.
                # Ranking is performed by the rolling top set, not capture order.
                for row in rows:
                    if time.monotonic() > deadline: break
                    key = comment_key(row)
                    if key[1]: scanned_keys.add(key)
                    if not key[1] or key in capture_keys: continue
                    if len(captured) >= limit and row.get('likes', 0) <= min(c['likes'] for c in captured):
                        continue
                    try:
                        await dismiss_capture_overlays(page)
                        shot = await capture_comment(page, {**row, 'capture_zoom': 1.25}, final)
                        captured.append(shot)
                        capture_keys.add(key)
                        failures.discard(key)
                        if progress:
                            progress({'seen':len(scanned_keys),'captured':min(len(captured),limit),
                                      'visible_cards':len(rows),'failed':len(failures),'last_error':''})
                        if len(captured) > limit:
                            # Discard only this crawl's unpublished losing capture.
                            loser = min(captured, key=lambda c: c['likes'])
                            captured.remove(loser)
                            capture_keys.discard(comment_key(loser))
                            from core import asset
                            image_path = asset(loser['image'], 'image')
                            image_path.unlink(missing_ok=True)
                            (DATA / 'assets' / (loser['image'] + '.json')).unlink(missing_ok=True)
                    except Exception as exc:
                        failures.add(key)
                        last_capture_error = str(exc)[:240]
                if anchor:
                    try:
                        await comment_element(page, anchor).scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        pass
                if platform == 'tiktok':
                    items = page.locator('[data-e2e="comment-item"]')
                    if await items.count():
                        await items.last.scroll_into_view_if_needed(timeout=3000)
                else:
                    await page.mouse.wheel(0, 650)
                count = len(scanned_keys)
                if progress:
                    progress({'seen':count,'captured':len(captured),'visible_cards':len(rows),
                              'failed':len(failures),'last_error':last_capture_error})
                stable = stable + 1 if count == previous else 0
                previous = count
                if stable >= 8: break
            if not original and platform == 'threads':
                try:
                    await page.goto(final, wait_until='domcontentloaded', timeout=20000)
                    original = await capture_original_post(page, final)
                    original_error = ''
                except (ValueError, PlaywrightError) as exc:
                    original_error = str(exc)
            if pending: await asyncio.gather(*pending, return_exceptions=True)
            if not post.get('text'):
                meta = page.locator('meta[property="og:description"]').first
                if await meta.count(): post['text'] = (await meta.get_attribute('content') or '')[:1500]
            rows = top_comments(captured, limit)
            timed_out = time.monotonic() >= deadline
            note = (f'Đã đọc {len(scanned_keys)} bình luận khác nhau; giữ {len(rows)} ảnh bình luận thật nhiều tim nhất trong số đã chụp, tối đa {limit}. '
                    'Kết quả xếp theo số tim giảm dần; giữ avatar, tên và giao diện tại thời điểm chụp. '
                    f'{len(failures)} bình luận chưa chụp được; không thay bằng ảnh chữ. '
                    'Chữ đọc giọng được lấy từ chính thẻ bình luận, không đọc các nút/tim. Dữ liệu có thể chưa đầy đủ. '
                    'Nền tảng có thể ẩn phản hồi, yêu cầu đăng nhập hoặc đổi cấu trúc. '
                    'Nếu thiếu, dùng Đăng nhập nguồn hoặc nhập JSON/dán văn bản.')
            if last_capture_error and failures:
                note += ' Lỗi chụp gần nhất: ' + last_capture_error
            if timed_out:
                note += ' Đã chạm giới hạn thời gian 10 phút, chưa xác nhận đọc hết nguồn.'
            note += ' Không bảo đảm top tuyệt đối nếu nền tảng ẩn bình luận/số tim hoặc không tải thêm được.'
            if original_error: note += ' ' + original_error
            return {'url': final, 'post': original['text'] if original else str(post.get('text', ''))[:1500],
                    'author': original['author'] if original else post.get('author', ''),
                    'post_image': original['image'] if original else '',
                    'post_captured_at': original['captured_at'] if original else '',
                    'post_capture_error': original_error,
                    'comments': rows, 'crawl_note': note}
        finally:
            for task in pending:
                if not task.done(): task.cancel()
            await context.close()


async def login(platform):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(DATA / 'profile'), **browser_options(), headless=False)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto('https://www.tiktok.com/login' if platform == 'tiktok' else 'https://www.threads.com/login')
        # Keep this explicit login window available until the user closes it.
        while context.pages:
            await asyncio.sleep(1)
        await context.close()


if __name__ == '__main__':
    import sys
    asyncio.run(login(sys.argv[1] if len(sys.argv) > 1 else 'tiktok'))
