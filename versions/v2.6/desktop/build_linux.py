#!/usr/bin/env python3
"""Create a Linux Python source/startup release; not a cross-compiled ELF binary."""
from pathlib import Path
import argparse,hashlib,io,tarfile

HERE=Path(__file__).resolve().parent
ROOT_NAME='binary_image_passcode_v2.6_linux'
SKIP={'__pycache__','.pytest_cache','.venv','.git','.build'}
TOP=['binary_image_passcode.py','run_linux.sh','build_linux.py','requirements.txt',
     'requirements-dev.txt','pyproject.toml','README.md','THIRD_PARTY_NOTICES.md']
TREES=['bip','assets','licenses','tests','examples','docs']

def main():
    parser=argparse.ArgumentParser(description='Package Linux V2.6 Python startup release')
    parser.add_argument('--output',type=Path,default=HERE.parent/(ROOT_NAME+'.tar.gz'))
    args=parser.parse_args();output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    files=[HERE/name for name in TOP]
    for folder in TREES:
        files.extend(p for p in (HERE/folder).rglob('*') if p.is_file()
                     and not any(a in SKIP for a in p.relative_to(HERE).parts)
                     and p.suffix not in {'.pyc','.pyo'})
    files=sorted(set(files));payload={}
    for file in files:
        if not file.is_file() or file.is_symlink():raise RuntimeError('Missing or linked release source: '+str(file))
        if file.suffix.lower() in {'.key','.p12','.pfx','.mobileprovision','.password','.exe','.apk','.ipa'}:
            raise RuntimeError('Unexpected private/platform artifact in release: '+str(file))
        relative=file.relative_to(HERE).as_posix()
        data=file.read_bytes()
        if file.suffix=='.sh':data=data.replace(b'\r\n',b'\n')
        payload[relative]=data
    sums=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in payload.items())
    payload['SHA256SUMS']=sums.encode('ascii')
    with tarfile.open(output,'w:gz',compresslevel=9,format=tarfile.PAX_FORMAT) as archive:
        directories={ROOT_NAME}
        for name in payload:
            parent=Path(name).parent
            while str(parent)!='.':
                directories.add(ROOT_NAME+'/'+parent.as_posix());parent=parent.parent
        for name in sorted(directories):
            info=tarfile.TarInfo(name);info.type=tarfile.DIRTYPE;info.mode=0o755;archive.addfile(info)
        for name,data in payload.items():
            info=tarfile.TarInfo(ROOT_NAME+'/'+name);info.mode=0o755 if name.endswith('.sh') else 0o644
            info.size=len(data);archive.addfile(info,io.BytesIO(data))
    with tarfile.open(output,'r:gz') as archive:
        for member in archive.getmembers():
            if not member.isfile():continue
            data=archive.extractfile(member).read();name=member.name[len(ROOT_NAME)+1:]
            if data!=payload[name]:raise RuntimeError('Archive verification failed: '+name)
        script=archive.getmember(ROOT_NAME+'/run_linux.sh')
        if script.mode!=0o755:raise RuntimeError('Linux launcher is not executable')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name+'.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(output);print('Files:',len(payload),'Bytes:',output.stat().st_size);print('SHA256:',digest)

if __name__=='__main__':main()
