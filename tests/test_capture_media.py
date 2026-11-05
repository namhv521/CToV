"""Browser fixtures verify actual screenshot pixels, without social accounts or network."""
import asyncio
import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from playwright.async_api import async_playwright
import capture
from collector import normalize
from core import Comment, ROOT


def picture(color):
    stream=io.BytesIO()
    Image.new('RGB',(200,150),color).save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


class FullCommentCaptureTests(unittest.TestCase):
    def test_full_image_video_poster_media_only_and_styles(self):
        async def verify():
            with tempfile.TemporaryDirectory(prefix='commentcut-capture-') as temp:
                data=Path(temp);(data/'assets').mkdir()
                async with async_playwright() as p:
                    browser=await p.chromium.launch(headless=True)
                    page=await browser.new_page(viewport={'width':800,'height':600})
                    with patch('capture.DATA',data):
                        # A tall attachment inside clipped comment and scrolling column.
                        await page.set_content(f'''<style>body{{margin:0}}*{{box-sizing:border-box}}</style>
                          <div id="column" style="height:350px;overflow:auto;width:420px">
                            <article id="comment" style="max-height:160px;overflow:hidden;width:400px;background:white">
                              <header>Minh</header><p>Nội dung thật</p>
                              <img src="{picture('red')}" style="display:block;width:400px;height:900px">
                              <footer style="height:50px;background:rgb(0,255,0)">128 · Trả lời</footer>
                            </article>
                            <article style="height:200px;background:purple">Bình luận khác</article>
                          </div>''')
                        row={'id':'one','author':'Minh','text':'Nội dung thật','capture_selector':'#comment'}
                        before=await page.locator('#comment').get_attribute('style')
                        column=await page.locator('#column').get_attribute('style')
                        shot=await capture.capture_comment(page,row,'https://www.threads.com/@a/post/ROOT')
                        with Image.open(data/'assets'/(shot['image']+'.png')) as image:
                            self.assertGreater(image.height,950)
                            self.assertEqual(image.getpixel((10,image.height-10))[:3],(0,255,0))
                        self.assertEqual(await page.locator('#comment').get_attribute('style'),before)
                        self.assertEqual(await page.locator('#column').get_attribute('style'),column)
                        # Poster pixels count as a video frame; no video playback is needed.
                        await page.set_content(f'''<article id="comment" style="width:400px;background:white">
                          <header>Minh</header><video poster="{picture('lime')}" width="400" height="300"></video>
                          <footer>Trả lời</footer></article>''')
                        shot=await capture.capture_comment(page,{**row,'id':'two','text':''},'https://www.threads.com/@a/post/ROOT')
                        self.assertEqual(shot['text'],'')
                        self.assertEqual(Comment(**normalize([shot])[0]).text,'')
                        self.assertTrue(await page.locator('video').evaluate('v=>v.paused'))
                        with Image.open(data/'assets'/(shot['image']+'.png')) as image:
                            self.assertEqual(image.getpixel((200,150))[:3],(0,255,0))
                        # Lazy attachment can receive its src after scrolling begins.
                        await page.set_content('<article id="comment" style="width:400px;background:white">Nội dung thật<img id="lazy" width="400" height="300"></article>')
                        await page.evaluate("src=>setTimeout(()=>document.querySelector('#lazy').src=src,250)",picture('red'))
                        lazy=await capture.capture_comment(page,row,'https://www.threads.com/')
                        with Image.open(data/'assets'/(lazy['image']+'.png')) as image:
                            self.assertEqual(image.getpixel((200,150))[:3],(255,0,0))
                        # An avatar alone is not an attached photo.
                        await page.set_content(f'<article id="comment" style="width:400px"><a href="/@minh">Minh<img src="{picture("blue")}"></a></article>')
                        with self.assertRaisesRegex(ValueError,'Bình luận trống'):
                            await capture.capture_comment(page,{**row,'text':''},'https://www.threads.com/')
                        # A failed image must be retried, never registered as complete.
                        await page.route('https://fixture.invalid/**',lambda route:route.abort())
                        await page.set_content('<article id="comment" style="width:400px">Nội dung thật<img src="https://fixture.invalid/broken.png"></article>')
                        before=set((data/'assets').iterdir())
                        with self.assertRaisesRegex(ValueError,'chưa tải xong'):
                            await capture.capture_comment(page,row,'https://www.threads.com/')
                        self.assertEqual(set((data/'assets').iterdir()),before)
                    await browser.close()
        asyncio.run(verify())

    def test_content_zoom_125_captures_scrolled_full_card_and_larger_text(self):
        from collector import configure_capture_zoom
        from PIL import ImageChops
        async def verify():
            with tempfile.TemporaryDirectory(prefix='commentcut-zoom-') as temp:
                data=Path(temp);(data/'assets').mkdir()
                async with async_playwright() as p:
                    context=await p.chromium.launch_persistent_context(str(data/'profile'),channel='chrome',
                              headless=True,viewport={'width':1280,'height':1000},device_scale_factor=2)
                    try:
                        page=await context.new_page()
                        html='<style>body{margin:0}</style><div style="height:1500px"></div><article id="comment" style="width:400px;background:white"><div style="height:100px;font:20px Arial;color:black">Nội dung thật</div><div style="height:250px;background:red"></div><footer style="height:50px;background:lime">End</footer></article><div style="height:100px;background:purple">Other comment</div>'
                        await page.route('https://zoom-test.invalid/**',lambda route:route.fulfill(body=html,content_type='text/html; charset=utf-8'))
                        await page.goto('https://zoom-test.invalid/')
                        baseline=Image.open(io.BytesIO(await page.locator('#comment > div').first.screenshot())).convert('RGB')
                        baseline_box=ImageChops.difference(baseline,Image.new('RGB',baseline.size,'white')).getbbox()
                        await configure_capture_zoom(context)
                        await page.reload()
                        self.assertAlmostEqual(await page.evaluate('devicePixelRatio'),2)
                        self.assertEqual(await page.evaluate('document.documentElement.style.zoom'),'1.25')
                        with patch('capture.DATA',data):
                            result=await capture.capture_comment(page,{'text':'Nội dung thật','capture_selector':'#comment','capture_zoom':1.25},'https://www.threads.com/')
                        with Image.open(data/'assets'/(result['image']+'.png')) as image:
                            self.assertEqual(image.size,(1000,1000))
                            self.assertEqual(image.getpixel((900,990))[:3],(0,255,0))
                            text=image.convert('RGB').crop((0,0,1000,250))
                            box=ImageChops.difference(text,Image.new('RGB',text.size,'white')).getbbox()
                            self.assertGreater(box[3]-box[1],(baseline_box[3]-baseline_box[1])*1.15)
                    finally:
                        await context.close()
        asyncio.run(verify())

    def test_threads_and_tiktok_keep_media_only_but_not_avatar_only(self):
        async def verify():
            async with async_playwright() as p:
                browser=await p.chromium.launch(headless=True)
                page=await browser.new_page()
                await page.route('https://www.threads.com/**',lambda route:route.fulfill(body='<main></main>',content_type='text/html; charset=utf-8'))
                await page.goto('https://www.threads.com/@root/post/ROOT')
                await page.set_content(f'''<main>
                  <div data-pressable-container="true"><a href="/@root/post/ROOT"><time>1h</time></a></div>
                  <div data-pressable-container="true"><a href="/@minh">Minh<img src="{picture('blue')}"></a>
                    <a href="/@minh/post/PHOTO"><time>1m</time></a><img src="{picture('red')}"></div>
                  <div data-pressable-container="true"><a href="/@minh">Minh</a>
                    <a href="/@minh/post/VIDEO"><time>1m</time></a><video poster="{picture('lime')}"></video></div>
                  <div data-pressable-container="true"><a href="/@minh">Minh<img src="{picture('blue')}"></a>
                    <a href="/@minh/post/EMPTY"><time>1m</time></a></div>
                  </main>''')
                rows=await page.evaluate((ROOT/'threads_dom.js').read_text('utf-8'),'ROOT')
                self.assertEqual([r['id'] for r in rows],['/@minh/post/PHOTO','/@minh/post/VIDEO'])
                self.assertTrue(all(r['has_media'] and not r['text'] for r in rows))
                # Same author + empty text must not merge different attached media.
                self.assertEqual(len(normalize([{**r,'image':f'{i:032x}'} for i,r in enumerate(rows)])),2)
                await page.set_content(f'''<div data-e2e="comment-item" data-comment-id="photo">
                  <a href="/@minh" data-e2e="comment-username-1">Minh</a><img src="{picture('red')}"></div>''')
                rows=await page.locator('[data-e2e="comment-item"]').evaluate_all(capture.TIKTOK_DOM)
                self.assertEqual(rows[0]['id'],'photo')
                self.assertTrue(rows[0]['has_media'])
                self.assertIn('data-comment-id=',rows[0]['capture_selector'])
                self.assertEqual(rows[0]['capture_index'],0)
                await browser.close()
        asyncio.run(verify())


if __name__=='__main__':unittest.main()
