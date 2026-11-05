import unittest
from unittest.mock import Mock
from capture import comment_element


class StableCommentLocatorTests(unittest.TestCase):
    def test_threads_uses_permalink_and_closest_card(self):
        page=Mock()
        row={'capture_selector':'a[href="/@nam/post/ABC"]:has(time)', 'capture_index':0,
             'capture_parent':'ancestor::*[@data-pressable-container="true"][1]'}
        result=comment_element(page,row)
        page.locator.assert_called_once_with(row['capture_selector'])
        card=page.locator.return_value.nth.return_value
        card.locator.assert_called_once_with('xpath='+row['capture_parent'])
        self.assertIs(result,card.locator.return_value)

    def test_legacy_tiktok_locator_is_preserved(self):
        page=Mock()
        row={'capture_selector':'[data-e2e="comment-item"]','capture_index':7}
        result=comment_element(page,row)
        page.locator.return_value.nth.assert_called_once_with(7)
        self.assertIs(result,page.locator.return_value.nth.return_value)
