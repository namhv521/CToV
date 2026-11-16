import unittest
from collector import top_comments
from core import Project, Comment
from app import CrawlRequest


class TopCommentTests(unittest.TestCase):
    def rows(self, count):
        return [{'id':str(i),'author':'Nam','text':f'Bình luận {i}','likes':i,
                 'image':f'{i:032x}'} for i in range(count)]

    def test_fewer_than_120_keeps_all_sorted(self):
        rows=top_comments(self.rows(35))
        self.assertEqual(len(rows),35)
        self.assertEqual([r['likes'] for r in rows],list(reversed(range(35))))

    def test_more_than_120_ranks_before_capping(self):
        rows=top_comments(self.rows(200))
        self.assertEqual(len(rows),120)
        self.assertEqual(rows[0]['likes'],199)
        self.assertEqual(rows[-1]['likes'],80)
        self.assertTrue(all(r.get('image') for r in rows))

    def test_exactly_120_and_empty(self):
        self.assertEqual(len(top_comments(self.rows(120))),120)
        self.assertEqual(top_comments([]),[])

    def test_dedup_and_ties_are_stable(self):
        rows=self.rows(3)
        for r in rows: r['likes']=5
        self.assertEqual([r['id'] for r in top_comments(rows+rows)],['0','1','2'])

    def test_api_and_project_accept_120_reject_121(self):
        self.assertEqual(CrawlRequest(url='https://www.tiktok.com/@a/video/1').limit,30)
        self.assertEqual(CrawlRequest(url='https://www.tiktok.com/@a/video/1',limit=120).limit,120)
        with self.assertRaises(ValueError): CrawlRequest(url='https://www.tiktok.com/@a/video/1',limit=121)
        self.assertEqual(len(Project(comments=[Comment(text=str(i)) for i in range(120)]).comments),120)
        with self.assertRaises(ValueError): Project(comments=[Comment(text=str(i)) for i in range(121)])


if __name__=='__main__': unittest.main()
