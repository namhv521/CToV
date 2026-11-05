import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from PIL import Image, ImageDraw

from core import DATA, Comment, read
from collector import normalize
from capture import capture_comment


class CaptureTests(unittest.TestCase):
    def page(self, fail=False):
        element=Mock()
        element.count=AsyncMock(return_value=1)
        element.scroll_into_view_if_needed=AsyncMock()
        element.inner_text=AsyncMock(return_value='Minh\nNội dung thật\n128\nTrả lời')
        element.evaluate=AsyncMock(return_value=True)
        async def screenshot(**kwargs):
            image=Image.new('RGB',(600,200),'white')
            ImageDraw.Draw(image).rectangle((10,10,100,100),fill='black')
            image.save(kwargs['path'])
            if fail: raise RuntimeError('screenshot failed')
        element.screenshot=screenshot
        page=Mock()
        page.evaluate=AsyncMock()
        page.locator.return_value.nth.return_value=element
        return page,element

    def test_real_image_metadata_survives_project(self):
        page,el=self.page()
        row={'id':'comment-1','author':'Minh','text':'Nội dung thật','likes':128,
             'likes_display':'128','capture_selector':'.comment','capture_index':0}
        captured=asyncio.run(capture_comment(page,row,'https://www.threads.com/@a/post/ABC'))
        normal=normalize([captured])[0]
        restored=Comment(**normal).model_dump()
        self.assertEqual(restored['capture_text'],'Nội dung thật')
        self.assertEqual(restored['image'],captured['image'])
        self.assertEqual(restored['likes_display'],'128')
        self.assertEqual(read(DATA/'assets'/(captured['image']+'.json'))['role'],'comment_capture')
        self.assertEqual(el.scroll_into_view_if_needed.await_count,2)

    def test_failed_screenshot_not_registered(self):
        page,el=self.page(fail=True)
        before=set((DATA/'assets').iterdir())
        with self.assertRaises(RuntimeError):
            asyncio.run(capture_comment(page,{'text':'Nội dung thật','capture_selector':'.comment','capture_index':0},'https://www.threads.com/'))
        self.assertEqual(set((DATA/'assets').iterdir()),before)

    def test_capture_recreates_missing_assets_directory(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        page,element=self.page()
        with tempfile.TemporaryDirectory() as temp,patch('capture.DATA',Path(temp)):
            result=asyncio.run(capture_comment(page,{'text':'Nội dung thật','capture_selector':'.comment'},'https://www.threads.com/'))
            self.assertTrue((Path(temp)/'assets'/(result['image']+'.png')).exists())

    def test_blank_capture_is_not_registered(self):
        page,element=self.page()
        async def blank(**kwargs):Image.new('RGB',(600,200),'white').save(kwargs['path'])
        element.screenshot=blank
        before=set((DATA/'assets').iterdir())
        with self.assertRaisesRegex(ValueError,'Ảnh bình luận trống'):
            asyncio.run(capture_comment(page,{'text':'Nội dung thật','capture_selector':'.comment'},'https://www.threads.com/'))
        self.assertEqual(set((DATA/'assets').iterdir()),before)

    def test_removed_comment_does_not_wait_for_scroll_timeout(self):
        page,element=self.page()
        element.count=AsyncMock(return_value=0)
        with self.assertRaisesRegex(ValueError,'đã rời vùng hiển thị'):
            asyncio.run(capture_comment(page,{'text':'Nội dung thật','capture_selector':'.comment'},'https://www.threads.com/'))
        element.scroll_into_view_if_needed.assert_not_awaited()

    def test_recycled_element_not_paired_with_wrong_text(self):
        page,el=self.page()
        with self.assertRaisesRegex(ValueError,'thay đổi'):
            asyncio.run(capture_comment(page,{'text':'Một bình luận khác','capture_selector':'.comment','capture_index':0},'https://www.threads.com/'))

    def test_overlay_is_rejected_before_screenshot(self):
        page,el=self.page()
        el.evaluate=AsyncMock(side_effect=[None,False])
        with self.assertRaisesRegex(ValueError,'che'):
            asyncio.run(capture_comment(page,{'text':'Nội dung thật','capture_selector':'.comment','capture_index':0},'https://www.threads.com/'))


if __name__=='__main__': unittest.main()
