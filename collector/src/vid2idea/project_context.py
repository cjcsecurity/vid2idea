"""Read-only, bounded project descriptions; never load source trees or env files."""
import base64
import json
import re
import subprocess
import time
from pathlib import Path


def clean_description(text):
    lines = [line.strip() for line in text.splitlines() if not re.search(r'(?i)(password|secret|token|api[_ -]?key|authorization|credential|private.key|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})',line)]
    text = ' '.join(lines)
    text = re.sub(r'https?://[^\s]+', '', text)
    return text[:1800]


def local_projects(roots):
    result=[]
    for root_text in roots.split(':'):
        if not root_text:
            continue
        root=Path(root_text).expanduser()
        try:
            if not root.is_dir() or root.is_symlink():
                continue
            directories=sorted(root.iterdir())
        except OSError:
            continue
        for directory in directories:
            try:
                eligible=directory.is_dir() and not directory.is_symlink() and not directory.name.startswith('.')
            except OSError:
                continue
            if not eligible:
                continue
            description=''
            for name in ('README.md','README.rst','README.txt'):
                path=directory/name
                try:
                    if path.is_file() and not path.is_symlink():
                        with path.open('rb') as file:
                            description=clean_description(file.read(8192).decode(errors='replace'))
                        break
                except OSError:
                    continue
            manifest=directory/'package.json'
            try:
                if manifest.is_file() and not manifest.is_symlink() and manifest.stat().st_size<=32768:
                    data=json.loads(manifest.read_text())
                    description=clean_description(str(data.get('description','')))+' '+description
            except (OSError,ValueError):
                pass
            if description.strip():
                result.append({'name':directory.name[:160],'description':description.strip()[:1800],'location':'local'})
            if len(result)>=24:
                return result
    return result


def github_projects(owner):
    if not owner:
        return []
    try:
        response=subprocess.run(['gh','repo','list',owner,'--limit','30','--json','name,description,url,isArchived,isFork'],capture_output=True,text=True,timeout=30,check=True)
        repositories=json.loads(response.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):
        return []
    result=[]
    for repository in repositories:
        if repository.get('isArchived') or repository.get('isFork'):
            continue
        name=repository.get('name','')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',name):
            continue
        description=clean_description(repository.get('description') or '')
        # Fetch a few READMEs only when repository metadata does not describe it.
        if not description and len(result)<8:
            try:
                readme=subprocess.run(['gh','api',f'repos/{owner}/{name}/readme'],capture_output=True,text=True,timeout=15,check=True)
                payload=json.loads(readme.stdout)
                if payload.get('size',0)<=128*1024:
                    description=clean_description(base64.b64decode(payload.get('content',''))[:8192].decode(errors='replace'))
            except (OSError,ValueError,subprocess.SubprocessError):
                pass
        if description:
            result.append({'name':name,'description':description[:1800],'location':'github','url':repository['url']})
    return result


def load_project_context(settings, *, cache_only=False):
    key=settings.project_roots+'|'+settings.github_owner
    cache=settings.data_dir/'project-context.json'
    try:
        saved=json.loads(cache.read_text())
        if saved.get('key')==key and time.time()-saved['created_at']<21600:
            return saved['projects']
    except (OSError,ValueError,KeyError):
        pass
    if cache_only:
        # Optional research must not repeat slow GitHub discovery after generation
        # or proceed without the catalog needed to exclude private project names.
        raise OSError('Project context cache unavailable')
    projects=local_projects(settings.project_roots)
    known={project['name'] for project in projects}
    projects.extend(project for project in github_projects(settings.github_owner) if project['name'] not in known)
    # Keep the total prompt contribution bounded even across many repositories.
    selected=[]; size=0
    for project in projects[:32]:
        size+=len(json.dumps(project))
        if size>24000:
            break
        selected.append(project)
    try:
        cache.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        cache.touch(mode=0o600,exist_ok=True);cache.chmod(0o600)
        cache.write_text(json.dumps({'key':key,'created_at':time.time(),'projects':selected}))
    except OSError:
        pass
    return selected
