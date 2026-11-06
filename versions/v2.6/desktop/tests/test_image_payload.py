from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import threading
import numpy as np
from PIL import Image
import pytest
from bip import image_payload as payload
from bip import image_transport as transport
from bip.errors import AuthenticationError, Cancelled, PasscodeError

KEY = '01234567' * 16

@pytest.mark.parametrize('fmt,mode', [('PNG','RGBA'),('BMP','RGB'),('JPEG','RGB'),('TIFF','RGB'),('WEBP','RGB')])
def test_input_formats_and_exact_jpeg_output(tmp_path, fmt, mode):
    source = tmp_path/('source.'+fmt.lower())
    Image.new(mode,(2100,1200),(30,120,210,120) if mode=='RGBA' else (30,120,210)).save(source,format=fmt)
    image = payload.prepare_image(source)
    assert max(image.width,image.height)<=1920 and min(image.width,image.height)<=1080
    assert image.width*image.height<=1920*1080 and len(image.data)<=payload.MAX_JPEG_BYTES
    with Image.open(BytesIO(image.data)) as jpg:
        assert jpg.format=='JPEG' and jpg.mode=='RGB'
    when = datetime(2026,11,4,13,12,11,tzinfo=timezone.utc)
    envelope = payload.seal_image(image,KEY,when,bytes(range(48)))
    restored = payload.open_image(envelope,KEY)
    assert restored.image.data==image.data and restored.generated_at==when
    assert restored.generated_at.second==11
    with pytest.raises(AuthenticationError):payload.open_image(envelope,'9'*128)
    for pos in [0,8,56,65,len(envelope)-1]:
        altered=bytearray(envelope);altered[pos]^=1
        with pytest.raises(AuthenticationError):payload.open_image(bytes(altered),KEY)

def test_portrait_noise_capacity_resize_alpha_and_cancel(tmp_path):
    source=tmp_path/'noise.png'
    Image.fromarray(np.random.default_rng(42).integers(0,256,(2200,1300,3),dtype=np.uint8)).save(source)
    image=payload.prepare_image(source,41033)
    assert image.width<=1080 and image.height<=1920 and len(image.data)<=41033
    assert image.original_size==(1300,2200)
    assert image.width<1080  # Deliberately tight byte budget forces an additional resize.
    transparent=tmp_path/'alpha.png';Image.new('RGBA',(50,50),(1,2,3,0)).save(transparent)
    prepared=payload.prepare_image(transparent)
    with Image.open(BytesIO(prepared.data)) as jpg:assert jpg.getpixel((10,10))==(255,255,255)
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):payload.prepare_image(source,cancel=cancel)
    with pytest.raises(PasscodeError):payload.prepare_image(source,100)

@pytest.mark.parametrize('strength,size', [('balanced',560),('balanced',1024),('strong',1024),('balanced',1536)])
def test_image_transport_and_save(tmp_path,strength,size):
    source=tmp_path/'secret.png';cover=tmp_path/'cover.bmp';target=tmp_path/'message.png'
    Image.fromarray(np.random.default_rng(3).integers(0,256,(1080,1920,3),dtype=np.uint8)).save(source)
    Image.fromarray(np.random.default_rng(4).integers(0,256,(size,size,3),dtype=np.uint8)).save(cover)
    encoded=payload.encode_image_file(cover,target,source,KEY,strength)
    result=transport.decode_file(target,KEY)
    assert result.image_bytes==encoded.image.data and result.text=='' and result.message_format=='2.5'
    assert result.image_size==(encoded.image.width,encoded.image.height)
    assert len(result.image_bytes)<=payload.jpeg_capacity(size,size,strength)
    assert source.exists() and cover.exists()
    if size==1024:
        with Image.open(target) as rgb:
            cropped=tmp_path/'crop.png';rgb.crop((100,100,924,924)).save(cropped)
            rotated=tmp_path/'rotate.png';rgb.transpose(Image.Transpose.ROTATE_90).save(rotated)
        assert transport.decode_file(cropped,KEY).image_bytes==result.image_bytes
        assert transport.decode_file(rotated,KEY).image_bytes==result.image_bytes
    output=tmp_path/'restored.jpg';payload.save_image_result(result,output)
    assert output.read_bytes()==encoded.image.data
    with pytest.raises(PasscodeError):payload.save_image_result(result,output)
    with pytest.raises(PasscodeError):payload.save_image_result(result,target,overwrite=True)
    with pytest.raises(PasscodeError):payload.save_image_result(result,output,overwrite=True,protected_paths=(output,))
    with pytest.raises(PasscodeError):payload.encode_image_file(cover,source,source,KEY,overwrite=True)
    with pytest.raises(AuthenticationError):transport.decode_file(target,'9'*128)

def test_corrupt_unsupported_and_time_boundaries(tmp_path):
    bad=tmp_path/'bad';bad.write_bytes(b'not an image')
    with pytest.raises(PasscodeError):payload.prepare_image(bad)
    source=tmp_path/'valid.png';Image.new('RGB',(32,32)).save(source)
    image=payload.prepare_image(source)
    with pytest.raises(PasscodeError):payload.seal_image(replace(image,quality=49),KEY)
    with pytest.raises(PasscodeError):payload.seal_image(replace(image,width=1930),KEY)
    from bip.protocol import EPOCH
    from datetime import timedelta
    for seconds in [0,2147483648,4294967296,9999999999]:
        when=EPOCH+timedelta(seconds=seconds)
        assert payload.open_image(payload.seal_image(image,KEY,when),KEY).generated_at==when
    with pytest.raises(PasscodeError):payload.seal_image(image,KEY,EPOCH-timedelta(seconds=1))
    assert payload.seal_image(image,KEY)!=payload.seal_image(image,KEY)

def test_unrestricted_source_dimensions_and_threshold_restore(tmp_path,monkeypatch):
    source=tmp_path/'wide.png'
    Image.new('RGB',(24000,128),(20,110,210)).save(source)
    original_threshold=Image.MAX_IMAGE_PIXELS
    with monkeypatch.context() as patch:
        patch.setattr(Image,'MAX_IMAGE_PIXELS',100)
        image=payload.prepare_image(source)
        assert Image.MAX_IMAGE_PIXELS==100
    assert Image.MAX_IMAGE_PIXELS==original_threshold
    assert image.original_size==(24000,128)
    assert image.width<=1920 and image.height<=1080
    payload.open_image(payload.seal_image(image,KEY),KEY)

def test_large_jpeg_draft_and_exif_orientation(tmp_path):
    source=tmp_path/'oriented.jpg'
    exif=Image.Exif();exif[274]=6
    with Image.new('RGB',(4000,2000),(80,160,210)) as image:
        image.save(source,quality=85,exif=exif)
    prepared=payload.prepare_image(source)
    assert prepared.original_size==(2000,4000)
    assert (prepared.width,prepared.height)==(960,1920)
    with Image.open(BytesIO(prepared.data)) as jpg:
        assert jpg.getexif().get(274) is None
