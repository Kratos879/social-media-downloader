import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader import DownloadQueue
from platforms import normalize, parse_links, resolve_link
from site_adapters import xhs_images


class PlatformRoutingTests(unittest.TestCase):
    def test_nine_platforms_in_one_paste_and_preserve_required_parameters(self):
        text='\n'.join([
            'https://instagram.com/p/ABC/', 'https://x.com/u/status/123',
            'https://www.xiaohongshu.com/explore/674051740000000007027a15?xsec_token=abc%2B123%3D&xsec_source=pc_share',
            'https://www.douyin.com/note/1234', 'https://www.tiktok.com/@u/video/1234',
            'https://www.bilibili.com/video/BV13x41117TL?p=2',
            'https://youtu.be/jNQXAC9IVRw?si=tracking',
            'https://m.weibo.cn/detail/1234', 'https://www.pinterest.com/pin/1234/',
        ])
        links,rejected=parse_links(text)
        self.assertEqual(len(links),9);self.assertFalse(rejected)
        self.assertIn('xsec_token=abc%2B123%3D',links[2]['url'])
        self.assertTrue(links[5]['key'].endswith('_p2'))
        self.assertEqual(links[6]['url'],'https://www.youtube.com/watch?v=jNQXAC9IVRw')

    def test_shortlinks_and_photos_remain_on_their_platform(self):
        for url,platform in [('https://xhslink.com/a/abc123','xiaohongshu'),
                             ('https://v.douyin.com/abc123/','douyin'),
                             ('https://vm.tiktok.com/abc123/','tiktok'),
                             ('https://www.tiktok.com/t/abc123/','tiktok'),
                             ('https://b23.tv/abc123','bilibili'),('https://pin.it/abc123','pinterest')]:
            self.assertEqual(normalize(url)['platform'],platform)
        self.assertIn('/photo/',normalize('https://www.tiktok.com/@u/photo/1234')['url'])

    def test_rejects_homepages_lookalikes_ports_and_arbitrary_playlist_urls(self):
        for url in ['https://www.youtube.com/playlist?list=PLabc','https://youtube.com.evil.test/watch?v=jNQXAC9IVRw',
                    'https://bilibili.com:987/video/BV13x41117TL','https://www.xiaohongshu.com/user/profile/abc',
                    'https://pinterest.com@127.0.0.1/pin/1','https://www.douyin.com/user/abc']:
            with self.subTest(url=url),self.assertRaises(ValueError):normalize(url)

    def test_shortlink_redirect_is_validated_before_second_request(self):
        class Response:
            is_redirect=True
            headers={'Location':'https://127.0.0.1/private'}
            def raise_for_status(self):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
        from unittest.mock import Mock
        session=Mock();session.get.return_value=Response()
        with self.assertRaises(ValueError):resolve_link('https://b23.tv/abc','bilibili',session)
        self.assertEqual(session.get.call_count,1)


class MetadataTests(unittest.TestCase):
    def test_f2_adapter_preserves_images_and_uses_playback_video_stream(self):
        from f2_worker import douyin_files
        images=douyin_files({'aweme_id':'123','images':[
            {'url_list':['https://p3.douyinpic.com/a.jpg'],'width':1200,'height':1600},
            {'url_list':['https://p3.douyinpic.com/b.jpg'],'width':1600,'height':1200}]})
        self.assertEqual(len(images),2);self.assertEqual(images[1]['height'],1200)
        video=douyin_files({'aweme_id':'123','video':{'duration':10500,'width':1080,'height':1920,
            'play_addr':{'url_list':['https://v26-web.douyinvod.com/play.mp4']},
            'download_addr':{'url_list':['https://v26-web.douyinvod.com/watermarked.mp4']},
            'cover':{'url_list':['https://p3.douyinpic.com/cover.jpg']}}})
        self.assertEqual(video[0]['duration'],10.5)
        self.assertIn('/play.mp4',video[0]['original_url'])
        self.assertNotIn('watermarked',video[0]['original_url'])

    def test_xhs_image_note_does_not_fetch_originals_or_execute_javascript(self):
        key='674051740000000007027a15'
        data={'note':{'noteDetailMap':{key:{'note':{'type':'normal','imageList':[
            {'width':1200,'height':1800,'urlDefault':'https://sns-webpic-qc.xhscdn.com/original.jpg',
             'urlPre':'https://sns-webpic-qc.xhscdn.com/small.jpg'}]}}}}}
        html='<script>window.__INITIAL_STATE__='+json.dumps(data)+'</script>'
        files=xhs_images(html,key)
        self.assertEqual(len(files),1);self.assertEqual(files[0]['width'],1200)
        self.assertIn('original.jpg',files[0]['preview_url'])

    def test_selected_video_only_calls_engine_for_selected_file_and_hides_source_info(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch('threading.Thread.start'):queue=DownloadQueue(root)
            job,_=queue.submit(normalize('https://youtu.be/jNQXAC9IVRw'))
            files=[{'kind':'video','saved':False,'status':'available','order':i+1,'width':320,'height':240,
                    'original_url':'https://www.youtube.com/watch?v=jNQXAC9IVRw',
                    'video_info':f'video-info/test/{i}.json','source_url':'secret source'} for i in range(2)]
            job.update(files=files,status='ready')
            def save(root,job,index,progress):
                target=queue.downloads/job['folder']/'selected.mp4';target.write_bytes(b'video-file'*20)
                progress(200,200,'完成');return target
            with patch('video_engine.download',side_effect=save) as engine:
                queue._download(job,[1])
            self.assertEqual(engine.call_count,1)
            self.assertFalse(files[0]['saved']);self.assertTrue(files[1]['saved'])
            state=queue.state()[0]['files'][1]
            self.assertNotIn('video_info',state);self.assertNotIn('source_url',state)
            self.assertEqual(sum(p.is_file() for p in queue.downloads.rglob('*')),1)



class TikTokEmbedTests(unittest.TestCase):
    def html(self,key='123',url='https://v45-ch.tiktokcdn.com/video/test.mp4'):
        item={'id':key,'video':{'urls':[url],'videoMeta':{'width':576,'height':1024,'duration':56}},
              'covers':['https://p16.tiktokcdn.com/cover.jpg'],'text':'public sample'}
        data={'source':{'data':{f'/embed/v2/{key}':{'videoData':{'itemInfos':item}}}}}
        return '<script id="__FRONTITY_CONNECT_STATE__">'+json.dumps(data)+'</script>'

    def test_official_embed_extracts_matching_video_only(self):
        from tiktok_embed import parse_embed
        info=parse_embed(self.html(),'123')
        self.assertEqual(info['id'],'123');self.assertEqual(info['duration'],56)
        self.assertEqual(info['width'],576);self.assertTrue(info['_embed_fallback'])
        with self.assertRaises(ValueError):parse_embed(self.html(),'456')

    def test_embed_rejects_arbitrary_resource_hosts(self):
        from tiktok_embed import parse_embed
        for url in ['https://127.0.0.1/private','https://tiktokcdn.com.evil.test/video.mp4','http://v45-ch.tiktokcdn.com/test.mp4']:
            with self.subTest(url=url),self.assertRaises(ValueError):parse_embed(self.html(url=url),'123')

    def test_selected_video_403_uses_official_fallback_and_updates_actual_resolution(self):
        from video_engine import download
        import yt_dlp
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);meta=root/'data/video-info/job';meta.mkdir(parents=True)
            (meta/'0.json').write_text(json.dumps({'id':'123','url':'https://v19.tiktok.com/broken','title':'test','ext':'mp4'}))
            job={'id':'job','key':'123','platform':'tiktok','folder':'test','files':[
                {'kind':'video','video_id':'123','video_info':'video-info/job/0.json','width':1080,'height':1920}]}
            class YDL:
                calls=0
                def __init__(self,opts):self.opts=opts
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def process_info(self,info):
                    YDL.calls+=1
                    if YDL.calls==1:raise yt_dlp.utils.DownloadError('HTTP Error 403: Forbidden')
                    Path(self.opts['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'test video'*30)
            fallback={'id':'123','url':'https://v45-ch.tiktokcdn.com/video/test','width':576,'height':1024,'duration':56}
            with patch('yt_dlp.YoutubeDL',YDL),patch('tiktok_embed.resolve',return_value=fallback) as resolve:
                path=download(root,job,0,lambda *args:None)
            resolve.assert_called_once_with(root,'123')
            self.assertTrue(path.is_file());self.assertEqual(job['files'][0]['width'],576)
            self.assertEqual(job['files'][0]['download_engine'],'TikTok 官方嵌入页')

if __name__=='__main__':unittest.main()
