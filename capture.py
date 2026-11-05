"""Capture actual rendered comment elements without reconstructing their UI."""
from datetime import datetime, timezone
import re
import time

from PIL import Image, ImageStat

from core import DATA, ROOT, uid, write, ensure_directory


def comment_element(page, row):
    locator = page.locator(row['capture_selector']).nth(row.get('capture_index', 0))
    if row.get('capture_parent'):
        locator = locator.locator('xpath=' + row['capture_parent'])
    return locator


async def dismiss_capture_overlays(page):
    """Dismiss only close/essential-cookie controls, never sign in or react."""
    dialogs = page.get_by_role('dialog')
    for dialog in await dialogs.all():
        close = dialog.get_by_role('button', name=re.compile(r'^(Close|Đóng)$')).first
        if await close.count() and await close.is_visible():
            await close.click(timeout=2000)
        elif await dialog.is_visible():
            await page.keyboard.press('Escape')
            try:
                await dialog.wait_for(state='hidden', timeout=1200)
            except Exception:
                pass  # An undismissable login wall remains blocked, never hidden by CSS.
    cookies = page.get_by_role('button', name=re.compile(
        r'^(Decline optional cookies|Only allow essential cookies|Từ chối cookie không bắt buộc|Chỉ cho phép cookie cần thiết)$'))
    if await cookies.count() and await cookies.first.is_visible():
        await cookies.first.click(timeout=2000)


async def capture_comment(page, row, source, role="comment_capture"):
    """Store pixels and readable text from the same element, at the same time."""
    text = str(row.get('text') or '').strip()
    if len(text) > 1500:
        raise ValueError('Bình luận dài hơn 1500 ký tự; cần chia thủ công.')
    element = comment_element(page, row)
    if not await element.count():
        raise ValueError('Bình luận đã rời vùng hiển thị sau khi cuộn; sẽ thử lại khi xuất hiện trong trang.')
    await element.scroll_into_view_if_needed(timeout=4000)
    rendered = re.sub(r'\s+', ' ', await element.inner_text()).strip()
    if re.sub(r'\s+', ' ', text).strip() not in rendered:
        raise ValueError('Thẻ bình luận đã thay đổi trong lúc chụp. Hãy crawl lại.')
    media = await element.evaluate((ROOT / 'capture_media.js').read_text('utf-8'))
    if isinstance(media, dict) and media.get('missing'):
        raise ValueError('Ảnh hoặc khung video của bình luận chưa tải xong. Hãy thử crawl lại.')
    if not text and not (isinstance(media, dict) and media.get('has_media')):
        raise ValueError('Bình luận trống, không có ảnh/video để chụp.')
    await element.scroll_into_view_if_needed(timeout=4000)
    visible = await element.evaluate('''el => {
      const r=el.getBoundingClientRect();
      const x=Math.max(0,Math.min(innerWidth-1,r.left+r.width*.5));
      const y=Math.max(0,Math.min(innerHeight-1,r.top+r.height*.5));
      const top=document.elementFromPoint(x,y);
      return !!top && (top===el || el.contains(top));
    }''')
    if not visible:
        raise ValueError('Bình luận đang bị hộp thoại che. Đóng hộp thoại hoặc đăng nhập nguồn rồi thử lại.')
    layout = await element.evaluate("""el => {
      const saved=[];
      const change=(node,expand)=>{
        saved.push([node,node.getAttribute('style')]);
        node.style.setProperty('overflow','visible','important');
        if(expand){
          node.style.setProperty('max-height','none','important');
          node.style.setProperty('height','auto','important');
          node.style.setProperty('-webkit-line-clamp','unset','important');
        }
      };
      for(const node of [el,...el.querySelectorAll('*')]){
        const css=getComputedStyle(node);
        if(node.scrollHeight>node.clientHeight+2 &&
           (/hidden|clip|auto|scroll/.test(css.overflowY)||css.webkitLineClamp!=='none'))change(node,true);
      }
      for(let node=el.parentElement;node&&node!==document.body;node=node.parentElement){
        if(/hidden|clip|auto|scroll/.test(getComputedStyle(node).overflowY))change(node,false);
      }
      const token='capture-'+Math.random().toString(36).slice(2);
      window.__commentcutLayouts=window.__commentcutLayouts||new Map();
      window.__commentcutLayouts.set(token,saved);
      return token;
    }""")
    captured_at = datetime.now(timezone.utc).isoformat()
    aid = uid()
    target = ensure_directory(DATA / 'assets') / (aid + '.png')
    try:
        # Recheck the exact card after lazy loading/scrolling, which can recycle rows.
        rendered = re.sub(r'\s+', ' ', await element.inner_text()).strip()
        if text and re.sub(r'\s+', ' ', text).strip() not in rendered:
            raise ValueError('Thẻ bình luận đã thay đổi trong lúc chụp. Hãy crawl lại.')
        await element.screenshot(path=str(target), type='png', animations='disabled', timeout=6000)
        with Image.open(target) as im:
            if im.width < 80 or im.height < 30 or im.width * im.height > 30_000_000:
                raise ValueError('Ảnh bình luận có kích thước không hợp lệ.')
            if max(ImageStat.Stat(im.convert('RGB')).stddev) < 1:
                raise ValueError('Ảnh bình luận trống. Trang đang tải lại vùng hiển thị; hãy thử chụp lại.')
            width, height = im.size
        author = str(row.get('author') or 'Người dùng')[:100]
        image = {'id': aid, 'kind': 'image', 'role': role, 'file': target.name,
                 'name': f'Ảnh bình luận · {author} · {captured_at[:19]}',
                 'bytes': target.stat().st_size, 'width': width, 'height': height, 'zoom': row.get('capture_zoom', 1),
                 'source_url': source, 'comment_url': row.get('comment_url', ''),
                 'captured_at': captured_at, 'text': text, 'author': author,
                 'likes_display': row.get('likes_display', '')}
        write(DATA / 'assets' / (aid + '.json'), image)
        return {k: v for k, v in row.items() if not k.startswith('capture_')} | {
            'text': text, 'image': aid, 'capture_text': text, 'captured_at': captured_at,
            'source_url': source, 'comment_url': row.get('comment_url', '')}
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await page.evaluate('''token => {
          const saved=window.__commentcutLayouts?.get(token)||[];
          for(const [node,style] of saved){
            if(style===null)node.removeAttribute('style');else node.setAttribute('style',style);
          }
          window.__commentcutLayouts?.delete(token);
        }''', layout)


TIKTOK_DOM = '''els => els.map((e,index) => {
  const content=e.querySelector('[data-e2e="comment-level-1"], [data-e2e="comment-level-2"]');
  const user=e.querySelector('[data-e2e="comment-username-1"], [data-e2e="comment-username-2"]');
  const likes=e.querySelector('[data-e2e="comment-like-count"]');
  const raw=likes?.textContent?.trim() || '';
  const n=parseFloat(raw.replace(',','.'));
  const media=Array.from(e.querySelectorAll('img,video')).filter(el=>el.tagName==='VIDEO'||(!el.closest('a[href^="/@"]')&&!el.closest('[data-e2e*="avatar"]')&&!/avatar|profile picture|ảnh đại diện/i.test(el.alt||'')));
  const cid=e.getAttribute('data-comment-id');
  const selector=cid?'[data-e2e="comment-item"][data-comment-id='+JSON.stringify(cid)+']':e.id?'#'+CSS.escape(e.id):'[data-e2e="comment-item"]';
  return {id:cid||e.id||media.map(el=>el.currentSrc||el.poster||el.src).join('|'),has_media:media.length>0,author:user?.textContent || e.querySelector('a')?.textContent,
    text:content?.textContent, likes:Number.isFinite(n)?Math.round(n*(/k/i.test(raw)?1000:/m/i.test(raw)?1000000:1)):0,
    likes_display:raw, capture_selector:selector, capture_index:cid||e.id?0:index};
})'''


async def capture_original_post(page, source, timeout=15000):
    """Capture the root before scrolling through any replies."""
    last_error = 'Không xác định được thẻ bài viết gốc, không dùng thẻ chữ thay thế.'
    deadline = time.monotonic() + timeout / 1000
    attempts = 0
    while time.monotonic() < deadline and attempts < 3:
        await dismiss_capture_overlays(page)
        row = await page.evaluate((ROOT / 'post_dom.js').read_text('utf-8'), source)
        if row:
            attempts += 1
            try:
                return await capture_comment(page, row, source, role='post_capture')
            except Exception as exc:
                last_error = str(exc)
            finally:
                await page.locator('[data-commentcut-original]').evaluate_all("nodes=>nodes.forEach(n=>n.removeAttribute('data-commentcut-original'))")
        await page.wait_for_timeout(500)
    raise ValueError('Chưa chụp được bài viết gốc: ' + last_error)
