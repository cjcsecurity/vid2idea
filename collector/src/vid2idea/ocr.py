"""Dense local frame OCR; a small selection still feeds Codex vision."""
import contextlib
import io
import logging
from urllib.parse import urlsplit
from .models import EvidenceImage
from .resources import observed_urls


def select_frame_evidence(frames, readings):
    selected=[]; images=[]; seen_urls=set(); seen_lines=set(); blocks=[]
    for path,seconds,text in readings:
        lines=[line.strip() for line in text.splitlines() if line.strip()]
        unique=[line for line in lines if line.casefold() not in seen_lines]
        seen_lines.update(line.casefold() for line in lines)
        if unique:
            blocks.append(f'[{seconds:.1f}s] '+'\n'.join(unique))
        urls={urlsplit(url).hostname for url in observed_urls(text)}
        if any(url not in seen_urls for url in urls):
            if len(selected)<12 and path not in selected:
                selected.append(path)
            if len(images)<3:
                images.append(EvidenceImage(path=path,caption=f'Source video, about {seconds:.0f} seconds',timestamp_seconds=seconds))
            seen_urls.update(urls)
    if frames:
        for index in range(min(12,len(frames))):
            path=frames[round(index*(len(frames)-1)/max(min(12,len(frames))-1,1))]
            if path not in selected and len(selected)<12:
                selected.append(path)
        for path in selected:
            if len(images)>=3:
                break
            if not any(image.path==path for image in images):
                reading=next((item for item in readings if item[0]==path),None)
                seconds=reading[1] if reading else None
                images.append(EvidenceImage(path=path,caption='Still from the source video',timestamp_seconds=seconds))
    return selected,'\n\n'.join(blocks)[:24000],images


def scan_frame_text(frames, interval):
    readings=[];gaps=[]
    try:
        from rapidocr import RapidOCR
        logging.getLogger('RapidOCR').setLevel(logging.ERROR)
        # Library/model setup cannot write progress into the pipeline's JSON stdout.
        with contextlib.redirect_stdout(io.StringIO()):
            engine=RapidOCR(params={'Global.log_level':'error','EngineConfig.onnxruntime.intra_op_num_threads':4,'EngineConfig.onnxruntime.inter_op_num_threads':1})
            for index,path in enumerate(frames[:90]):
                output=engine(str(path))
                texts=getattr(output,'txts',None)
                scores=getattr(output,'scores',None)
                if texts:
                    text='\n'.join(value for value,score in zip(texts,scores) if score>=0.65)
                    if text:
                        readings.append((path,index*interval,text))
    except Exception:
        gaps.append('On-screen text could not be fully read.')
    selected,text,images=select_frame_evidence(frames,readings)
    return selected,text,images,gaps
