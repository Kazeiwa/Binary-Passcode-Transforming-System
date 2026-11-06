"""Build the signed V1.1 APK using installed Android SDK/NDK and JDK 17+."""
import argparse
import hashlib
import os
import pathlib
import secrets
import shutil
import subprocess
import struct
import sys
import zipfile
import zlib

HERE = pathlib.Path(__file__).resolve().parent
PROJECT = HERE.parent

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
    for path in [tools, platform, ndk]:
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', default=os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME'))
    parser.add_argument('--aapt2', type=pathlib.Path)
    parser.add_argument('--work', type=pathlib.Path, default=PROJECT.parent / 'work' / 'android-build')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    temporary = work/'tmp'
    temporary.mkdir(exist_ok=True)
    for name in ['TMP','TEMP','TMPDIR']: os.environ[name] = str(temporary)
    tools, platform, ndk = resolve_tools(args.sdk, PROJECT.parent / 'work' / 'toolchain' / 'android')
    java_home = pathlib.Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else pathlib.Path(shutil.which('javac')).resolve().parents[1]
    is_windows = os.name == 'nt'
    exe = '.exe' if is_windows else ''
    aapt2 = args.aapt2.resolve() if args.aapt2 else tools/('aapt2'+exe)
    java, javac, keytool = [java_home/'bin'/(name+exe) for name in ['java','javac','keytool']]
    host = 'windows-x86_64' if is_windows else ('darwin-x86_64' if sys.platform == 'darwin' else 'linux-x86_64')
    clang = ndk/'toolchains'/'llvm'/'prebuilt'/host/'bin'/('clang++'+exe)
    packages = work/'package'
    packages.mkdir(exist_ok=True)
    for abi, target in [('arm64-v8a','aarch64-linux-android26'), ('armeabi-v7a','armv7a-linux-androideabi26'), ('x86_64','x86_64-linux-android26')]:
        out = packages/'lib'/abi/'libbinary_passcode_terminal.so'
        out.parent.mkdir(parents=True,exist_ok=True)
        run([clang,'--target='+target,'-std=c++17','-O2','-shared','-fPIC','-fvisibility=hidden','-static-libstdc++',
             '-Wl,-z,max-page-size=16384','-Wl,--build-id=sha1',PROJECT/'binary_passcode_terminal.cpp','-o',out])
        print('Built', abi, flush=True)
    resources = work/'resources.zip'
    flat = work/'flat'
    flat.mkdir(exist_ok=True)
    for source in sorted((HERE/'res').rglob('*.xml')):
        run([aapt2,'compile',source,'-o',flat])
    with zipfile.ZipFile(resources,'w',zipfile.ZIP_STORED) as archive:
        for path in sorted(flat.glob('*.flat')): archive.write(path,path.name)
    base = work/'base.apk'
    link_resources([aapt2,'link','-I',platform,'--manifest',HERE/'AndroidManifest.xml','-o',base,*sorted(flat.glob('*.flat'))],base)
    classes = work/'classes'
    classes.mkdir(exist_ok=True)
    sources = sorted((HERE/'src').rglob('*.java'))
    run([javac,'-encoding','UTF-8','--release','8','-classpath',platform,'-d',classes,*sources])
    classfiles = sorted(classes.rglob('*.class'))
    jar = work/'classes.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in classfiles: archive.write(path,path.relative_to(classes).as_posix())
    dex = work/'dex'
    dex.mkdir(exist_ok=True)
    run([java,'-cp',tools/'lib'/'d8.jar','com.android.tools.r8.D8','--release','--min-api','26','--lib',platform,'--output',dex,jar])
    unsigned = work/'unsigned.apk'
    shutil.copyfile(base,unsigned)
    with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_STORED) as archive:
        archive.write(dex/'classes.dex','classes.dex')
        for path in sorted((packages/'lib').rglob('*.so')): archive.write(path,path.relative_to(packages).as_posix())
        archive.write(PROJECT/'binary_passcode_terminal_notices.txt','assets/binary_passcode_terminal_notices.txt',compress_type=zipfile.ZIP_DEFLATED)
    aligned = work/'aligned.apk'
    align_zip(unsigned,aligned)
    run([tools/('zipalign'+exe),'-c','-P','16','4',aligned])
    store = pathlib.Path(os.environ.get('BPT_SIGNING_STORE', str(work.parent/'android-signing'/'release.p12'))).resolve()
    password = pathlib.Path(os.environ.get('BPT_SIGNING_PASSWORD_FILE', str(store.with_suffix('.password')))).resolve()
    store.parent.mkdir(parents=True,exist_ok=True)
    if store.exists() != password.exists():
        raise RuntimeError('签名文件不完整，请恢复原有签名证书及密码文件，勿生成新证书覆盖。')
    if not store.exists():
        password.write_text(secrets.token_urlsafe(32),encoding='ascii')
        if os.name != 'nt': password.chmod(0o600)
        run([keytool,'-genkeypair','-keystore',store,'-storetype','PKCS12','-storepass:file',password,
             '-alias','binary_passcode_terminal','-keyalg','RSA','-keysize','3072','-validity','10000',
             '-dname','CN=Binary Passcode Terminal, OU=Local Release'])
        if os.name != 'nt': store.chmod(0o600)
    apk = PROJECT/'binary_passcode_terminal.apk'
    signer = [java,'-jar',tools/'lib'/'apksigner.jar']
    run([*signer,'sign','--ks',store,'--ks-key-alias','binary_passcode_terminal','--ks-pass','file:'+str(password),
         '--v4-signing-enabled','false','--out',apk,aligned])
    run([*signer,'verify','--verbose','--print-certs',apk])
    run([tools/('zipalign'+exe),'-c','-P','16','4',apk])
    print('APK:',apk)
    print('SHA256:',hashlib.sha256(apk.read_bytes()).hexdigest())
    print('请备份本地签名证书和密码文件，以保持后续APK升级兼容：',store.parent)

if __name__ == '__main__': main()
