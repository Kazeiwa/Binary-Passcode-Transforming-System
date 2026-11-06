"""V2.6 full-file PNG payload transport. No crop recovery; authenticated RGB parity."""
from dataclasses import dataclass
import math
import hashlib
import hmac
import struct
import numpy as np
from .errors import PasscodeError, AuthenticationError, checkpoint
from .protocol import AUTH_FAILURE, validate_key

HEADER = struct.Struct('>4sBBBB48sI')
COPY_BYTES = HEADER.size + 32
PREFIX_BITS = COPY_BYTES * 8 * 3
CHUNK = 262144

def geometry(w, h):
    mx, my = math.ceil(w*.04), math.ceil(h*.04)
    iw, ih = w-2*mx, h-2*my
    return mx, my, iw, ih, max(0, iw)*max(0, ih)*3

def capacity(w, h):
    from .image_payload import OVERHEAD, MAX_PNG_BYTES
    return max(0, min(MAX_PNG_BYTES, (geometry(w,h)[4]-PREFIX_BITS)//8-OVERHEAD))

def square_required(size):
    from .image_transport import MAX_SIDE, MAX_PIXELS
    side=max(32, math.ceil(math.sqrt(((size+87)*8+PREFIX_BITS)/(3*.92**2))))
    while capacity(side,side)<size and side<MAX_SIDE:
        side+=1
    return (side,side) if side*side<=MAX_PIXELS and capacity(side,side)>=size else None

def _indices(logical,w,h):
    mx,my,iw,ih,slots=geometry(w,h)
    pixels=logical//3
    return my+pixels//iw, mx+pixels%iw, logical%3

def _write(rgb,logical,bits):
    ys,xs,cs=_indices(logical,rgb.shape[1],rgb.shape[0])
    rgb[ys,xs,cs]=(rgb[ys,xs,cs]&254)|bits

def _read(rgb,logical):
    ys,xs,cs=_indices(logical,rgb.shape[1],rgb.shape[0])
    return np.packbits(rgb[ys,xs,cs]&1,bitorder='big').tobytes()

def _order(key,nonce,count):
    from .image_payload import _derive
    seed=hmac.digest(_derive(key,b'dense-positions',nonce),b'positions','sha256')
    start=int.from_bytes(seed[:8],'big')%count
    step=int.from_bytes(seed[8:16],'big')%count or 1
    while math.gcd(step,count)!=1:
        step=(step+1)%count or 1
    return start,step

@dataclass(frozen=True)
class DenseLayout:
    width:int
    height:int
    selected_fraction:float
    margin_fraction:float=.04
    n:int=1
    k:int=1

def encode(rgb,envelope,key,cancel=None,progress=None):
    from .image_payload import _derive
    validate_key(key)
    h,w=rgb.shape[:2]
    available=geometry(w,h)[4]-PREFIX_BITS
    if available<len(envelope)*8:
        raise PasscodeError('底图空间不足，无法写入PNG无损图片。请使用更大的底图。')
    nonce=envelope[8:56]
    header=HEADER.pack(b'BIPD',1,4,0,0,nonce,len(envelope))
    prefix=header+hmac.digest(_derive(key,b'dense-header',nonce),header,'sha256')
    out=rgb.copy()
    _write(out,np.arange(PREFIX_BITS),np.tile(np.unpackbits(np.frombuffer(prefix,dtype=np.uint8)),3))
    start,step=_order(key,nonce,available)
    for bit in range(0,len(envelope)*8,CHUNK):
        checkpoint(cancel)
        end=min(bit+CHUNK,len(envelope)*8)
        logical=PREFIX_BITS+(start+step*np.arange(bit,end,dtype=np.int64))%available
        bits=np.unpackbits(np.frombuffer(envelope[bit//8:end//8],dtype=np.uint8))
        _write(out,logical,bits)
        if progress:progress(.05+.9*end/(len(envelope)*8),'正在写入PNG无损图片…')
    return out,DenseLayout(w,h,(len(envelope)*8+PREFIX_BITS)/(w*h*3)),nonce

def decode(rgb,key,cancel=None,progress=None):
    from .image_payload import _derive, open_image, MAX_ENVELOPE
    from .image_transport import DecodeResult
    validate_key(key)
    recognized=False
    for rotation in range(4):
        checkpoint(cancel)
        image=np.rot90(rgb,rotation)
        h,w=image.shape[:2]
        available=geometry(w,h)[4]-PREFIX_BITS
        if available<=0:continue
        valid=[]
        for copy in range(3):
            offset=copy*COPY_BYTES*8
            data=_read(image,np.arange(offset,offset+COPY_BYTES*8))
            if data[:4]!=b'BIPD':continue
            recognized=True
            header,tag=data[:HEADER.size],data[HEADER.size:]
            magic,version,profile,flags,reserved,nonce,total=HEADER.unpack(header)
            if (version,profile,flags,reserved)!=(1,4,0,0) or not 87<total<=MAX_ENVELOPE or total*8>available:continue
            if hmac.compare_digest(tag,hmac.digest(_derive(key,b'dense-header',nonce),header,'sha256')):
                valid.append((nonce,total))
        if not valid:continue
        if any(item!=valid[0] for item in valid):raise AuthenticationError(AUTH_FAILURE)
        nonce,total=valid[0];start,step=_order(key,nonce,available)
        output=bytearray()
        for bit in range(0,total*8,CHUNK):
            checkpoint(cancel)
            end=min(bit+CHUNK,total*8)
            logical=PREFIX_BITS+(start+step*np.arange(bit,end,dtype=np.int64))%available
            output.extend(_read(image,logical))
            if progress:progress(.05+.9*end/(total*8),'正在恢复PNG无损图片…')
        message=open_image(bytes(output),key)
        if message.nonce!=nonce or message.image.format!='PNG':raise AuthenticationError(AUTH_FAILURE)
        return DecodeResult('',message.generated_at,nonce.hex(),1,1,1,0,rotation*90,0,'2.6',
                            message.image.data,(message.image.width,message.image.height),0,'PNG')
    if recognized:raise AuthenticationError(AUTH_FAILURE)
    return None
