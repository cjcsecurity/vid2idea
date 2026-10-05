"""Native blocks and the manifest's narrowly owned page properties."""
from datetime import datetime, timezone

from .notion_api import PublicationError


def rich_text(value,link=None):
    value=str(value or '')
    chunks=[]; text=''; units=0
    for char in value:
        width=2 if ord(char)>0xffff else 1
        if units+width>2000:
            chunks.append(text); text=''; units=0
        text+=char; units+=width
    if text:
        chunks.append(text)
    if len(chunks)>100:
        raise PublicationError('notion_value_limit')
    return [{'type':'text','text':{'content':s,**({'link':{'url':link}} if link and len(link)<=2000 else {})}} for s in chunks]


def block(kind,text='',link=None):
    return {'object':'block','type':kind,kind:{'rich_text':rich_text(text,link)}}


def page_properties(record,payload,*,create=False,project_page_id=None,content_hash=None):
    brief=payload.get('brief') or {}
    status=payload.get('processing_status','queued')
    if status not in {'queued','processing','ready','partial','blocked','failed'}:
        raise PublicationError('local_invalid_status')
    url=record['canonical_url']
    props={'Name':{'title':rich_text(payload.get('title') or 'Saved idea')},
        'Origin':{'select':{'name':'vid2idea'}},'Source URL':{'url':url if len(url)<=2000 else None},
        'Summary':{'rich_text':rich_text(brief.get('summary',''))},
        'Topics':{'multi_select':[{'name':x} for x in payload.get('tags',[])]},
        'Processing status':{'select':{'name':status.capitalize()}},
        'Error code':{'rich_text':rich_text(payload.get('error_code') or '')},
        'External ID':{'rich_text':rich_text('vid2idea:idea:'+record['id'])}}
    if content_hash:
        props['Content hash']={'rich_text':rich_text(content_hash)}
        props['Last published']={'date':{'start':datetime.now(timezone.utc).isoformat()}}
    if create:
        initial=record.get('initial',{})
        props.update({'Kind':{'select':{'name':'Article'}},'Saved at':{'date':{'start':record['saved_at']} if record['saved_at'] else None},
            'Review status':{'select':{'name':'Unread'}},'Stage':{'select':{'name':initial.get('stage','saved').capitalize()}},
            'Favorite':{'checkbox':bool(initial.get('favorite',False))},
            'Personal notes':{'rich_text':rich_text(initial.get('personal_notes',''))},
            'Projects':{'relation':[{'id':project_page_id}] if project_page_id else []}})
    return props


def render_article(payload,shares,upload_ids):
    brief=payload.get('brief') or {}; blocks=[]
    for resource in brief.get('resources',[]):
        blocks.append(block('heading_2',resource['name'],resource.get('url')))
        if resource.get('url'):
            blocks.append(block('paragraph',resource['url'],resource['url']))
        blocks.append(block('paragraph',resource.get('summary','')))
    if brief.get('summary'):
        blocks.extend([block('heading_2','Summary'),block('paragraph',brief['summary'])])
    for image,file_id in zip(payload.get('image_uploads',[]),upload_ids,strict=True):
        caption=image.get('caption','Source image')
        if image.get('timestamp_seconds') is not None:
            caption+=f" · {image['timestamp_seconds']:g}s"
        blocks.append({'object':'block','type':'image','image':{'type':'file_upload','file_upload':{'id':file_id},'caption':rich_text(caption)}})
    for label,key in [('Useful details','details'),('First steps','suggested_steps')]:
        if brief.get(key):
            blocks.append(block('heading_2',label))
            blocks.extend(block('numbered_list_item' if key=='suggested_steps' else 'bulleted_list_item',x) for x in brief[key])
    if brief.get('use_cases'):
        blocks.append(block('heading_2','Ways to use this'))
        for use in brief['use_cases']:
            blocks.append(block('heading_3',use['title']))
            blocks.append(block('paragraph',use.get('description','')))
            if use.get('project'):
                blocks.append(block('paragraph','Fits with '+use['project']))
    if brief.get('question_answers'):
        blocks.append(block('heading_2','Research'))
        for answer in brief['question_answers']:
            blocks.append(block('heading_3',answer['question']))
            blocks.append(block('paragraph',answer['answer']))
            blocks.append(block('paragraph',f"{answer['status'].replace('_',' ').capitalize()} · Checked {answer['checked_at']}"))
            blocks.extend(block('bulleted_list_item',source['title']+' — '+source['url'],source['url']) for source in answer.get('sources',[]))
    if brief.get('open_questions'):
        blocks.append(block('heading_2','Still to figure out'))
        blocks.extend(block('bulleted_list_item',x) for x in brief['open_questions'])
    if payload.get('evidence_gaps') or payload.get('error_code'):
        blocks.append(block('heading_2','Coverage notes'))
        if payload.get('error_code'):
            blocks.append(block('paragraph',f"{payload.get('processing_status','blocked').capitalize()}: {payload['error_code']}"))
        blocks.extend(block('bulleted_list_item',x) for x in payload.get('evidence_gaps',[]))
    blocks.append(block('heading_2','Source'))
    if payload.get('evidence_kinds'):
        blocks.append(block('paragraph','Evidence: '+', '.join(x.replace('_',' ') for x in payload['evidence_kinds'])))
    for share in shares:
        blocks.append(block('paragraph',share['original_url'],share['original_url']))
        blocks.append(block('paragraph',f"Saved {share['shared_at']} · Discord {share['channel_id']}/{share['message_id']}"))
        if share.get('note'):
            blocks.append(block('paragraph',share['note']))
    if not shares:
        blocks.append(block('paragraph','No source sharing metadata was available in the imported record.'))
    return blocks
