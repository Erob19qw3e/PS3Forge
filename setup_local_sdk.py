"""Install an isolated local PS3 SDK in a dedicated WSL distribution.

Run explicitly; never downloads or installs on app startup. Existing SDKs are
not replaced. Official download URLs and checksums are recorded locally.
"""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = ROOT/'local-sdk'
DISTRO = 'PS3Forge'


def fetch(url, path, expected=None, size=None):
    if not path.exists():
        print('Downloading '+path.name, flush=True)
        if size and size>100*1024*1024:
            from concurrent.futures import ThreadPoolExecutor
            import shutil
            def part(index):
                start=size*index//8;end=size*(index+1)//8-1
                target=path.with_name(path.name+'.chunk'+str(index))
                if target.exists() and target.stat().st_size==end-start+1:return target
                request=urllib.request.Request(url,headers={'User-Agent':'PS3Forge-local-setup','Range':f'bytes={start}-{end}'})
                with urllib.request.urlopen(request,timeout=60) as source,target.open('wb') as output:
                    if source.status!=206 or source.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':
                        raise RuntimeError('Server did not honor the download range')
                    while chunk:=source.read(1024*1024): output.write(chunk)
                if target.stat().st_size!=end-start+1:raise RuntimeError('Incomplete SDK download')
                print('SDK download part '+str(index+1)+'/8 complete',flush=True)
                return target
            with ThreadPoolExecutor(max_workers=8) as pool: parts=list(pool.map(part,range(8)))
            with path.with_suffix(path.suffix+'.assembled').open('wb') as output:
                for item in parts:
                    with item.open('rb') as source:shutil.copyfileobj(source,output)
            path.with_suffix(path.suffix+'.assembled').replace(path)
        else:
            request=urllib.request.Request(url,headers={'User-Agent':'PS3Forge-local-setup'})
            with urllib.request.urlopen(request, timeout=60) as source, path.with_suffix(path.suffix+'.part').open('wb') as target:
                while chunk:=source.read(1024*1024): target.write(chunk)
            path.with_suffix(path.suffix+'.part').replace(path)
    digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    if expected and digest!=expected: raise RuntimeError('Checksum mismatch: '+path.name)
    return digest


def wsl(command, timeout=600):
    subprocess.run(['wsl','--distribution',DISTRO,'--user','root','--exec','bash','-lc',command],check=True,timeout=timeout)


def install_cg():
    import tarfile
    import shlex
    url='https://developer.download.nvidia.com/cg/Cg_3.1/Cg-3.1_April2012_x86_64.tgz'
    archive=HOME/'Cg-3.1_April2012_x86_64.tgz'
    digest=fetch(url,archive)
    folder=HOME/'cg';folder.mkdir(exist_ok=True)
    with tarfile.open(archive) as source:
        member=next(m for m in source.getmembers() if m.name.endswith('/libCg.so') and m.isfile())
        with source.extractfile(member) as data,(folder/'libCg.so').open('wb') as target:target.write(data.read())
        for member in source.getmembers():
            if member.isfile() and ('license' in member.name.lower() or 'copyright' in member.name.lower()):
                with source.extractfile(member) as data:(folder/Path(member.name).name).write_bytes(data.read())
    (folder/'provenance.json').write_text(json.dumps({'url':url,'sha256':digest},indent=2),encoding='utf8')
    result=subprocess.run(['wsl','-d',DISTRO,'--exec','wslpath','-a',str(folder/'libCg.so')],capture_output=True,check=True)
    wsl('set -e; mkdir -p /opt/ps3dev/lib; test -e /opt/ps3dev/lib/libCg.so || cp '+shlex.quote(result.stdout.decode().strip())+' /opt/ps3dev/lib/libCg.so')


def main():
    HOME.mkdir(exist_ok=True)
    base='https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/'
    name='ubuntu-base-24.04.3-base-amd64.tar.gz'
    sums=urllib.request.urlopen(base+'SHA256SUMS',timeout=30).read().decode()
    expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*')==name)
    ubuntu_hash=fetch(base+name,HOME/name,expected)
    request=urllib.request.Request('https://api.github.com/repos/ps3dev/ps3dev/releases/tags/nightly-2026-10-12',headers={'User-Agent':'PS3Forge'})
    release=json.load(urllib.request.urlopen(request,timeout=30))
    asset=next(a for a in release['assets'] if a['name']=='ps3dev-linux-X64.tar.gz')
    expected_sdk=(asset.get('digest') or '').removeprefix('sha256:') or None
    sdk_hash=fetch(asset['browser_download_url'],HOME/asset['name'],expected_sdk,asset['size'])
    (HOME/'provenance.json').write_text(json.dumps({'ubuntu':base+name,'ubuntuSha256':ubuntu_hash,
        'sdk':asset['browser_download_url'],'sdkSha256':sdk_hash,'sdkPublisherDigest':expected_sdk},indent=2),encoding='utf8')
    result=subprocess.run(['wsl','--list','--quiet'],capture_output=True,check=True)
    distros=result.stdout.decode('utf-16le','replace').replace('\x00','').split()
    if DISTRO not in distros:
        subprocess.run(['wsl','--import',DISTRO,str(HOME/'distro'),str(HOME/name),'--version','2'],check=True,timeout=180)
    wsl('set -e; apt-get -o Acquire::Languages=none update; DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y make python3 libstdc++6 libgmp10 libmpfr6 libmpc3 zlib1g libelf1t64 libssl3t64 ca-certificates curl',900)
    import shlex
    # wslpath is used rather than assuming drive mappings or shell-escaping paths.
    result=subprocess.run(['wsl','-d',DISTRO,'--exec','wslpath','-a',str(HOME/asset['name'])],capture_output=True,check=True)
    archive=result.stdout.decode().strip()
    wsl('set -e; if [ ! -e /opt/ps3dev ]; then mkdir -p /opt/ps3dev; tar -xzf '+shlex.quote(archive)+' -C /opt/ps3dev --strip-components=1; fi; /opt/ps3dev/ppu/bin/ppu-gcc --version')
    install_cg()
    print('Local SDK ready in WSL '+DISTRO,flush=True)


if __name__=='__main__': main()
