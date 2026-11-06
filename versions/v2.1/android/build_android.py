"""Build and sign the Android release. Signing material stays outside source archives."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import zipfile
from build_tools import run, resolve_tools, link_resources, align_zip

HERE=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sdk',default=os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME'))
    parser.add_argument('--local-tools',type=Path,default=HERE.parents[2]/'work/toolchain/android')
    parser.add_argument('--aapt2',type=Path)
    parser.add_argument('--work',type=Path,default=HERE.parents[2]/'work/bip-android-build')
    parser.add_argument('--output',type=Path,default=HERE.parent/'binary_image_passcode.apk')
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    tmp=work/'tmp';tmp.mkdir(exist_ok=True)
    for key in ('TMP','TEMP','TMPDIR'):os.environ[key]=str(tmp)
    tools,platform,_=resolve_tools(args.sdk,args.local_tools.resolve())
    java_home=Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else Path(shutil.which('javac')).resolve().parents[1]
    ext='.exe' if os.name=='nt' else ''
    java,javac,keytool=[java_home/'bin'/(name+ext) for name in ('java','javac','keytool')]
    aapt=args.aapt2.resolve() if args.aapt2 else tools/('aapt2'+ext)
    flat=work/'flat';flat.mkdir(exist_ok=True)
    for source in sorted((HERE/'res').rglob('*.xml')):run([aapt,'compile',source,'-o',flat])
    base=work/'base.apk'
    link_resources([aapt,'link','-I',platform,'--manifest',HERE/'AndroidManifest.xml','-o',base,*sorted(flat.glob('*.flat'))],base)
    classes=work/'classes';classes.mkdir(exist_ok=True)
    run([javac,'-encoding','UTF-8','--release','8','-classpath',platform,'-d',classes,*sorted((HERE/'src').rglob('*.java'))])
    jar=work/'classes.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(classes.rglob('*.class')):z.write(p,p.relative_to(classes).as_posix())
    dex=work/'dex';dex.mkdir(exist_ok=True)
    run([java,'-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--release','--min-api','26','--lib',platform,'--output',dex,jar])
    unsigned=work/'unsigned.apk';shutil.copyfile(base,unsigned)
    with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_STORED) as z:z.write(dex/'classes.dex','classes.dex')
    aligned=work/'aligned.apk';align_zip(unsigned,aligned)
    store=Path(os.environ.get('BIP_SIGNING_STORE',str(work.parent/'bip-android-signing/release.p12'))).resolve()
    password=Path(os.environ.get('BIP_SIGNING_PASSWORD_FILE',str(store.with_suffix('.password')))).resolve()
    store.parent.mkdir(parents=True,exist_ok=True)
    if store.exists()!=password.exists():raise RuntimeError('签名证书或密码文件缺失，请恢复原文件。')
    if not store.exists():
        password.write_text(secrets.token_urlsafe(32),encoding='ascii')
        if os.name!='nt':password.chmod(0o600)
        run([keytool,'-genkeypair','-keystore',store,'-storetype','PKCS12','-storepass:file',password,'-alias','binary_image_passcode','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Binary Image Passcode, OU=Release'])
        if os.name!='nt':store.chmod(0o600)
    output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    signer=[java,'-jar',tools/'lib/apksigner.jar']
    run([*signer,'sign','--ks',store,'--ks-key-alias','binary_image_passcode','--ks-pass','file:'+str(password),'--v4-signing-enabled','false','--out',output,aligned])
    run([*signer,'verify','--verbose','--print-certs',output])
    run([tools/('zipalign'+ext),'-c','4',output])
    print('APK:',output)
    print('SHA256:',hashlib.sha256(output.read_bytes()).hexdigest())
    print('Signing files (keep private and back up):',store.parent)
if __name__=='__main__':main()
