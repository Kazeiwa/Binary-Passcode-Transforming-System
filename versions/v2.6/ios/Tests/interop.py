"""Run the platform-neutral iOS C++ core against the released Python V2.6 implementation.
Usage: python interop.py CORE_EXECUTABLE OUTPUT_DIRECTORY (PYTHONPATH points to V2.6/deps).
The executable uses Windows CNG for this host test, Apple CryptoKit/CommonCrypto on iOS.
"""
from pathlib import Path
import subprocess,sys,hashlib
from datetime import datetime,timezone
import numpy as np
from PIL import Image
from bip import protocol,dense_transport
from bip.image_transport import encode_array,decode_array
from bip.image_payload import PreparedImage,seal_image,open_image

exe=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
key='01234567'*16;when=datetime.fromtimestamp(1793701842,timezone.utc);passed=[]
def run(op,source,target,*args,valid=True,k=key):
    r=subprocess.run([str(exe),op,str(source),str(target),k,*map(str,args)],capture_output=True,timeout=180)
    assert (r.returncode==0)==valid,(op,r.stdout,r.stderr)
    return r
def case(name):passed.append(name);print('PASS',name,flush=True)
text='Hello, World! 3132 0.5 | \\u日本語 한국어 繁體 @#$^&\' "  \n'
t=out/'text.txt';t.write_text(text,encoding='utf-8',newline='');envfile=out/'env.bin'
run('sealtext',t,envfile);assert envfile.read_bytes()==protocol.seal(text,key,when,bytes([7])*48);case('Text envelope byte-identical to Python')
run('opentext',envfile,out/'opened.txt');assert (out/'opened.txt').read_text('utf-8')==text;case('Unicode, literal backslash-u, modes, whitespace')
bmp=''.join(chr(i) for i in range(65536) if not 0xd800<=i<=0xdfff)
# Chunk to stay within the encoded-unit budget.
for i in range(0,len(bmp),8000):
    t.write_text(bmp[i:i+8000],encoding='utf-8',newline='');run('sealtext',t,envfile)
    assert protocol.open_envelope(envfile.read_bytes(),key).text==bmp[i:i+8000]
case('Every BMP scalar value cross-decoded')
t.write_text('a'*60000,encoding='utf-8',newline='');run('sealtext',t,envfile);assert protocol.open_envelope(envfile.read_bytes(),key).used_units==60000;case('60,000 unit boundary')
t.write_text('a'*60001,encoding='utf-8',newline='');run('sealtext',t,out/'too-long',valid=False);case('Over-limit text rejected')
t.write_text('sample payload',encoding='utf-8',newline='');run('shake',t,out/'shake');assert (out/'shake').read_bytes()==hashlib.shake_256(t.read_bytes()).digest(400);case('SHAKE256 FIPS output')
noise=out/'noise';noise.write_bytes(np.random.default_rng(4).integers(0,256,1300,dtype=np.uint8).tobytes());run('rs',noise,out/'rs');assert (out/'rs').read_bytes()==noise.read_bytes();case('16 damaged bytes per RS block recovered')
cover=np.random.default_rng(6).integers(0,256,(1024,1024,3),dtype=np.uint8)
raw=out/'raw.rgb';encodedraw=out/'encoded.rgb';resultfile=out/'result'
for strong in (False,True):
    env=protocol.seal(text,key,when,bytes(range(48)));envfile.write_bytes(env)
    raw.write_bytes(cover.tobytes());run('encode',raw,encodedraw,1024,1024,envfile,int(strong),0)
    rgb=np.frombuffer(encodedraw.read_bytes(),np.uint8).reshape(cover.shape)
    assert decode_array(rgb,key).text==text;case('C++ text -> Python '+str(strong))
    rgb,_,_=encode_array(cover,text,key,'strong' if strong else 'balanced',when=when)
    raw.write_bytes(rgb.tobytes());run('decode',raw,resultfile,1024,1024);assert resultfile.read_text('utf-8')==text;case('Python text -> C++ '+str(strong))
    for label,data in [('cropped',rgb[100:924,100:924]),('rotated',np.rot90(rgb))]:
        raw.write_bytes(data.tobytes());run('decode',raw,resultfile,data.shape[1],data.shape[0]);assert resultfile.read_text('utf-8')==text;case('C++ '+label+' text '+str(strong))
for png in (False,True):
    p=out/('secret.png' if png else 'secret.jpg');Image.fromarray(np.random.default_rng(9).integers(0,256,(90,140,4 if png else 3),dtype=np.uint8)).save(p,**({} if png else {'quality':80}))
    prep=PreparedImage(p.read_bytes(),140,90,0 if png else 80,(140,90),'PNG' if png else 'JPEG')
    run('sealimage',p,envfile,140,90,int(png),0 if png else 80)
    assert envfile.read_bytes()==seal_image(prep,key,when,bytes([9])*48);case(('PNG' if png else 'JPG')+' AES-GCM envelope byte-identical')
    run('openimage',envfile,resultfile);assert resultfile.read_bytes()==p.read_bytes();case('Image envelope authenticated open '+str(png))
    for strong in ((False,) if png else (False,True)):
        raw.write_bytes(cover.tobytes());run('encode',raw,encodedraw,1024,1024,envfile,int(strong),int(png))
        rgb=np.frombuffer(encodedraw.read_bytes(),np.uint8).reshape(cover.shape);assert decode_array(rgb,key).image_bytes==p.read_bytes();case('C++ image -> Python '+str((png,strong)))
        if png:rgb,_,_=dense_transport.encode(cover,envfile.read_bytes(),key)
        else:rgb,_,_=encode_array(cover,'',key,'strong' if strong else 'balanced',_envelope=envfile.read_bytes())
        raw.write_bytes(rgb.tobytes());run('decode',raw,resultfile,1024,1024);assert resultfile.read_bytes()==p.read_bytes();case('Python image -> C++ '+str((png,strong)))
        variants=[('rotate90',np.rot90(rgb)),('rotate180',np.rot90(rgb,2)),('rotate270',np.rot90(rgb,3))] if png else [('crop',rgb[100:924,100:924])]
        for name,data in variants:
            raw.write_bytes(data.tobytes());run('decode',raw,resultfile,data.shape[1],data.shape[0]);assert resultfile.read_bytes()==p.read_bytes();case('C++ image '+name+' '+str((png,strong)))
    raw.write_bytes(rgb.tobytes());bad=out/('bad'+str(png));run('decode',raw,bad,1024,1024,valid=False,k='9'*128);assert not bad.exists();case('Wrong key releases no plaintext '+str(png))
    badenv=bytearray(envfile.read_bytes());badenv[-1]^=1;envfile.write_bytes(badenv);run('openimage',envfile,bad,valid=False);assert not bad.exists();case('Corrupt AES tag rejected '+str(png))
badtext=bytearray(protocol.seal(text,key,when));badtext[66]^=1;envfile.write_bytes(badtext);run('opentext',envfile,out/'badtext',valid=False);assert not (out/'badtext').exists();case('Corrupt HMAC rejected')
(out/'report.txt').write_text('\n'.join(passed)+'\n',encoding='utf-8',newline='')
print('TOTAL PASS',len(passed))

