import os, pathlib, subprocess, struct, zipfile, zlib
HERE=pathlib.Path(__file__).resolve().parent
def run(command, **options):
    arguments=[]
    for index,item in enumerate(command):
        if index and isinstance(item,pathlib.Path):
            try: item=os.path.relpath(item)
            except ValueError: pass
        arguments.append(str(item))
    subprocess.run(arguments, check=True, **options)

def resolve_tools(sdk, local):
    if sdk:
        sdk = pathlib.Path(sdk).resolve()
        tools = sdk / 'build-tools' / '36.0.0'
        platform = sdk / 'platforms' / 'android-36' / 'android.jar'
        ndk = sdk / 'ndk' / '30.0.16248370'
    else:
        tools = local / 'build-tools' / 'android-16'
        platform = local / 'platform' / 'android-36' / 'android.jar'
        ndk = local / 'ndk' / 'android-ndk-r30'
    for path in [tools, platform]:
        if not path.exists():
            raise RuntimeError('缺少构建工具：' + str(path) + '\n请指定 --sdk（SDK需安装build-tools;36.0.0、platforms;android-36、ndk;30.0.16248370）。')
    return tools, platform, ndk

def link_resources(command, destination):
    try:
        run(command)
        return
    except subprocess.CalledProcessError as error:
        # Some restricted Windows hosts crash during native ZIP finalization.
        # Recover only complete local entries with verified lengths and CRCs.
        if error.returncode not in (3221225477, -1073741819) or not destination.exists(): raise
        raw=destination.read_bytes();offset=0;entries=[]
        while offset < len(raw):
            if raw[offset:offset+4] != b'PK\x03\x04': raise RuntimeError('资源包损坏，不能恢复。') from error
            header=struct.unpack_from('<IHHHHHIIIHH',raw,offset)
            _,_,flags,method,_,_,crc,packed,size,name_size,extra_size=header
            if flags or method not in (0,8): raise RuntimeError('资源包格式无法安全恢复。') from error
            start=offset+30;name=raw[start:start+name_size].decode('utf-8')
            start+=name_size+extra_size;end=start+packed
            if end>len(raw): raise RuntimeError('资源条目不完整。') from error
            payload=raw[start:end]
            decoded=zlib.decompress(payload,-15) if method==8 else payload
            if len(decoded)!=size or zlib.crc32(decoded)!=crc: raise RuntimeError('资源条目校验失败。') from error
            entries.append((name,decoded,method));offset=end
        expected={'AndroidManifest.xml','resources.arsc'}|{'res/'+p.relative_to(HERE/'res').as_posix() for p in (HERE/'res').rglob('*.xml') if p.parent.name!='values'}
        if {name for name,_,_ in entries} != expected: raise RuntimeError('资源条目缺失。') from error
        with zipfile.ZipFile(destination,'w') as archive:
            for name,data,method in entries: archive.writestr(name,data,compress_type=method)
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None: raise RuntimeError('资源包恢复校验失败。') from error
        print('Recovered resource ZIP finalization; all entries and CRCs validated.',flush=True)

def align_zip(source, destination):
    # Alignment is a ZIP layout property; the official zipalign reader verifies it below.
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination,'w') as dest:
        for item in src.infolist():
            info=zipfile.ZipInfo(item.filename,(2000,1,1,0,0,0))
            info.compress_type=item.compress_type
            if info.compress_type==zipfile.ZIP_STORED:
                alignment=16384 if item.filename.endswith('.so') else 4
                offset=dest.fp.tell()+30+len(item.filename.encode('utf-8'))
                padding=(-offset)%alignment
                if padding:
                    if padding<4: padding+=alignment
                    info.extra=struct.pack('<HH',0xCAFE,padding-4)+bytes(padding-4)
            dest.writestr(info,src.read(item.filename))

