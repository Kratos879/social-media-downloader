import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from downloader import DownloadQueue, friendly_error, parse_links
from server import build_selected_archive
from media import allowed_media_url


class LinkTests(unittest.TestCase):
    def test_mixed_share_text_and_alias_deduplication(self):
        links, rejected = parse_links('分享：“https://www.instagram.com/p/Abc_123-/?igsh=abc”。\nhttps://twitter.com/user/status/12345/photo/2?s=20\nhttps://x.com/i/status/12345')
        self.assertEqual([(x['platform'], x['key']) for x in links], [('instagram', 'Abc_123-'), ('twitter', '12345')])
        self.assertEqual(rejected, [])
        self.assertEqual(links[0]['url'], 'https://www.instagram.com/p/Abc_123-/')

    def test_reels_and_user_prefixed_posts(self):
        links, _ = parse_links('https://instagram.com/person/reel/ABC123/ https://instagram.com/p/XYZ https://mobile.twitter.com/user/status/987/video/1')
        self.assertEqual(len(links), 3)

    def test_rejects_lookalike_hosts_credentials_and_non_posts(self):
        links, rejected = parse_links('https://instagram.com.evil.test/p/abc https://x.com@localhost/status/1 https://x.com:8123/a/status/1 https://www.instagram.com/person/ http://127.0.0.1/private https://t.co/abc')
        self.assertEqual(links, [])
        self.assertEqual(len(rejected), 6)

    def test_login_and_network_errors_remain_distinct(self):
        self.assertIn('登录会话', friendly_error('HTTP redirect to login page'))
        self.assertIn('限制', friendly_error('429 Too Many Requests'))
        self.assertIn('网络', friendly_error('Connection timeout'))


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        # Routing/persistence tests never start downloads or contact a platform.
        with patch('threading.Thread.start'):
            self.manager = DownloadQueue(self.root)
        self.item = parse_links('https://x.com/example/status/12345')[0][0]

    def tearDown(self):
        self.temp.cleanup()

    def test_duplicate_active_submission_creates_one_task(self):
        first, duplicate = self.manager.submit(self.item)
        second, duplicate2 = self.manager.submit(self.item)
        self.assertFalse(duplicate)
        self.assertTrue(duplicate2)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.manager.state()), 1)

    def test_restart_preserves_records_and_marks_interrupted_task(self):
        first, _ = self.manager.submit(self.item)
        with patch('threading.Thread.start'):
            reopened = DownloadQueue(self.root)
        self.assertEqual(reopened.get(first['id'])['status'], 'failed')
        self.assertIn('中断', reopened.get(first['id'])['message'])

    def test_retry_preserves_old_files(self):
        first, _ = self.manager.submit(self.item)
        folder = self.manager.downloads / first['folder']
        folder.mkdir(parents=True)
        original = folder / 'original.jpg'
        Image.new('RGB', (40, 20), 'green').save(original)
        files = self.manager._images(folder, first['id'])
        self.manager._update(first, status='completed', files=files, count=1)
        second, duplicate = self.manager.retry(first['id'])
        self.assertFalse(duplicate)
        self.assertNotEqual(first['id'], second['id'])
        self.assertTrue(original.is_file())
        self.assertEqual(files[0]['width'], 40)
        self.assertTrue((self.manager.data / 'thumbs' / first['id'] / '0.jpg').is_file())

    def test_corrupted_file_never_counts_as_downloaded_image(self):
        folder = self.manager.downloads / 'test'
        folder.mkdir()
        (folder / 'bad.jpg').write_bytes(b'not an image')
        self.assertEqual(self.manager._images(folder, 'test'), [])

    def make_completed_job(self, url, colors):
        item = parse_links(url)[0][0]
        job, _ = self.manager.submit(item)
        folder = self.manager.downloads / job['folder']
        folder.mkdir(parents=True)
        for number, color in enumerate(colors):
            Image.new('RGB', (30, 20), color).save(folder / f'{number}.jpg')
        files = self.manager._images(folder, job['id'])
        self.manager._update(job, status='completed', files=files, count=len(files))
        return job

    def test_batch_export_includes_only_selected_originals_across_posts(self):
        a = self.make_completed_job('https://instagram.com/p/ABC/', ['red', 'green'])
        b = self.make_completed_job('https://x.com/example/status/999', ['blue'])
        items = [{'id': a['id'], 'index': 1}, {'id': b['id'], 'index': 0}, {'id': a['id'], 'index': 1}]
        archive, count = build_selected_archive(self.manager, items)
        self.assertEqual(count, 2)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            self.assertEqual(len(z.namelist()), 2)
            contents = [z.read(name) for name in z.namelist()]
        self.assertEqual(contents, [(self.manager.downloads / a['files'][1]['path']).read_bytes(),
                                    (self.manager.downloads / b['files'][0]['path']).read_bytes()])
        self.assertEqual(len(self.manager.state()), 2)

    def test_batch_export_rejects_missing_and_negative_selections(self):
        job = self.make_completed_job('https://instagram.com/p/ABC/', ['red'])
        for items in [[], None, [{'id': job['id'], 'index': -1}], [{'id': job['id'], 'index': 2}],
                      [{'id': 'missing', 'index': 0}], [{'id': job['id'], 'index': True}]]:
            with self.subTest(items=items), self.assertRaises(ValueError):
                build_selected_archive(self.manager, items)

    def test_batch_export_does_not_follow_files_outside_downloads(self):
        job = self.make_completed_job('https://instagram.com/p/ABC/', ['red'])
        outside = self.root / 'outside.txt'
        outside.write_text('private')
        job['files'][0]['path'] = str(outside)
        with self.assertRaises(ValueError):
            build_selected_archive(self.manager, [{'id': job['id'], 'index': 0}])

    def make_preview_job(self):
        job, _ = self.manager.submit(self.item)
        files = [{'order': i+1, 'name': f'{i+1}.jpg', 'original_url': f'https://pbs.twimg.com/media/test{i}?format=jpg&name=orig',
                  'preview_url': f'https://pbs.twimg.com/media/test{i}?format=jpg&name=small', 'width': 60, 'height': 40,
                  'preview_ready': True, 'saved': False, 'status': 'available', 'bytes': 0} for i in range(3)]
        self.manager._merge_parse(job, {'files': files, 'expected': 3, 'preview_count': 3})
        self.manager._update(job, status='ready')
        return job

    def test_resolving_previews_never_creates_original_files(self):
        job = self.make_preview_job()
        self.assertEqual(list(self.manager.downloads.rglob('*')), [])
        self.assertEqual(job['expected'], 3)
        self.assertFalse(any(f.get('saved') for f in job['files']))

    def test_saving_one_selection_requests_and_writes_only_that_original(self):
        job = self.make_preview_job()
        source = io.BytesIO()
        Image.new('RGB', (60,40), 'orange').save(source, format='JPEG')
        content = source.getvalue()
        class Response:
            headers = {'Content-Length': str(len(content))}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def iter_content(self,size): yield content
        with patch('downloader.session_for') as session, patch('downloader.open_media',return_value=Response()) as request:
            self.manager._download(job,[1])
        self.assertEqual(request.call_count,1)
        self.assertEqual(request.call_args.args[1],job['files'][1]['original_url'])
        originals=list(self.manager.downloads.rglob('*.jpg'))
        self.assertEqual(len(originals),1)
        self.assertEqual(originals[0].read_bytes(),content)
        self.assertEqual([f.get('saved') for f in job['files']],[False,True,False])

    def test_invalid_bulk_selection_does_not_queue_any_original(self):
        job = self.make_preview_job()
        with self.assertRaises(ValueError):
            self.manager.enqueue_download([{'id':job['id'],'index':0},{'id':job['id'],'index':999}])
        self.assertTrue(all(f['status']=='available' for f in job['files']))

    def test_unsaved_previews_cannot_be_exported_as_original_files(self):
        job = self.make_preview_job()
        with self.assertRaisesRegex(ValueError,'先保存'):
            build_selected_archive(self.manager,[{'id':job['id'],'index':0}])

    def test_preview_cache_cleanup_preserves_saved_originals(self):
        job = self.make_completed_job('https://instagram.com/p/CACHE/', ['red'])
        original=self.manager.downloads/job['files'][0]['path']
        before=original.read_bytes()
        cached=self.manager.data/'previews'/job['id']/'0.jpg'
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b'preview cache')
        self.assertGreater(self.manager.storage()['preview_bytes'],0)
        result=self.manager.clear_preview_cache()
        self.assertGreater(result['removed_bytes'],0)
        self.assertFalse(cached.exists())
        self.assertEqual(original.read_bytes(),before)

    def test_public_state_does_not_expose_original_cdn_urls(self):
        self.make_preview_job()
        self.assertNotIn('original_url',self.manager.state()[0]['files'][0])

    def test_restart_retains_unsaved_previews_without_creating_originals(self):
        job=self.make_preview_job()
        with patch('threading.Thread.start'):
            reopened=DownloadQueue(self.root)
        restored=reopened.get(job['id'])
        self.assertEqual(restored['status'],'ready')
        self.assertEqual(len(restored['files']),3)
        self.assertFalse(any(f.get('saved') for f in restored['files']))
        self.assertEqual(list(reopened.downloads.rglob('*')),[])

    def test_legacy_carousel_uses_numeric_order_and_keeps_thumbnail_mapping(self):
        legacy={'id':'legacy','platform':'instagram','key':'ABC','url':'https://instagram.com/p/ABC/',
                'status':'completed','folder':'legacy','message':'done','files':[
                    {'name':f'ABC_{i}.jpg','path':f'legacy/ABC_{i}.jpg','bytes':10,'width':100,'height':150}
                    for i in (1,10,2)]}
        self.manager.history_file.write_text(json.dumps([legacy]))
        with patch('threading.Thread.start'):
            reopened=DownloadQueue(self.root)
        self.assertEqual([f['name'] for f in reopened.jobs[0]['files']],['ABC_1.jpg','ABC_2.jpg','ABC_10.jpg'])
        self.assertEqual([f['preview_index'] for f in reopened.jobs[0]['files']],[0,2,1])
        self.assertTrue((self.manager.data/'history-before-selective-preview.json').exists())


class MediaURLTests(unittest.TestCase):
    def test_only_platform_cdn_hosts_are_used(self):
        self.assertTrue(allowed_media_url('https://pbs.twimg.com/media/test?name=small'))
        self.assertTrue(allowed_media_url('https://scontent.cdninstagram.com/example.jpg'))
        for url in ['http://pbs.twimg.com/a','https://pbs.twimg.com.evil.test/a','https://127.0.0.1/a','https://user@pbs.twimg.com/a']:
            self.assertFalse(allowed_media_url(url))


if __name__ == '__main__':
    unittest.main()
