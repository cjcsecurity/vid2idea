from io import BytesIO
from PIL import Image
from vid2idea.models import EvidenceImage


def test_jpeg_uploads_are_compact_and_strip_source_metadata(tmp_path):
    from vid2idea.media_assets import prepare_image_uploads
    import base64
    path=tmp_path/'source.png'
    Image.new('RGB',(2400,1600),'green').save(path)
    uploads=prepare_image_uploads([EvidenceImage(path=path,caption='Source image')]*4)
    assert len(uploads)==3
    data=base64.b64decode(uploads[0]['data'])
    assert len(data)<=200*1024
    with Image.open(BytesIO(data)) as result:
        assert result.format=='JPEG' and max(result.size)<=1280
        assert not result.getexif()


def test_bad_image_does_not_discard_other_source_images(tmp_path):
    from vid2idea.media_assets import prepare_image_uploads
    good=tmp_path/'good.png';bad=tmp_path/'bad.png'
    Image.new('RGB',(40,40),'blue').save(good);bad.write_text('not image data')
    uploads=prepare_image_uploads([EvidenceImage(path=bad,caption='Bad'),EvidenceImage(path=good,caption='Good')])
    assert len(uploads)==1 and uploads[0]['caption']=='Good'


def test_ocr_prefers_different_named_websites_and_deduplicates_text(tmp_path):
    from vid2idea.ocr import select_frame_evidence
    frames=[]
    for i in range(20):
        path=tmp_path/f'frame-{i:03d}.jpg';path.touch();frames.append(path)
    readings=[(frames[1],1.0,'example.com\nA useful tool'),(frames[2],2.0,'example.com\nA useful tool'),
              (frames[10],10.0,'secondsite.org\nResearch toolkit'),(frames[17],17.0,'thirdsite.io\nData explorer')]
    selected,text,images=select_frame_evidence(frames,readings)
    assert len(selected)<=12
    assert all(path in selected for path in (frames[1],frames[10],frames[17]))
    assert text.count('example.com')==1
    assert len(images)==3
    assert [image.timestamp_seconds for image in images]==[1.0,10.0,17.0]


def test_article_keeps_named_links_and_image_candidates():
    from vid2idea.articles import evidence_from_html, article_image_candidates
    html='<html><head><meta property="og:image" content="/hero.png"></head><main><h1>Research tools</h1><p>A collection of useful tools for investigating published research.</p><a href="https://example.com/tool">Research Tool</a><img src="/chart.png" alt="Research chart"></main></html>'
    evidence=evidence_from_html(html,'https://source.example.org/article')
    assert evidence.links[0].name=='Research Tool'
    assert evidence.links[0].url=='https://example.com/tool'
    assert article_image_candidates(html,'https://source.example.org/article')[0]['url']=='https://source.example.org/hero.png'
def test_video_image_selection_prioritizes_distinct_websites(tmp_path):
    from vid2idea.ocr import select_frame_evidence
    frames = [tmp_path/f'{i}.jpg' for i in range(4)]
    readings = [(frames[0],0,'alpha.com'),(frames[1],1,'alpha.com/features'),(frames[2],2,'beta.com'),(frames[3],3,'gamma.com')]
    _,_,images = select_frame_evidence(frames,readings)
    assert [image.path for image in images] == [frames[0],frames[2],frames[3]]
