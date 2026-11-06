from io import BytesIO
from datetime import datetime, timezone
import threading
import numpy as np
from PIL import Image
import pytest
from bip.image_payload import prepare_image, encode_image_file, save_image_result, seal_image, open_image
from bip.image_transport import decode_file, decode_array
from bip import dense_transport as dense
from bip.errors import AuthenticationError, PasscodeError, Cancelled

KEY='01234567'*16

def test_rgba_lossless_pixels_transparency_time_and_save(tmp_path):
    pixels=np.random.default_rng(14).integers(0,256,(300,400,4),dtype=np.uint8)
    secret=tmp_path/'alpha.png';Image.fromarray(pixels).save(secret)
    prepared=prepare_image(secret,lossless=True)
    assert prepared.format=='PNG' and prepared.quality==0
    with Image.open(BytesIO(prepared.data)) as image:assert np.array_equal(np.asarray(image),pixels)
    when=datetime(2026,11,4,3,2,1,tzinfo=timezone.utc)
    assert open_image(seal_image(prepared,KEY,when),KEY).generated_at==when
    carrier=tmp_path/'cover.png';target=tmp_path/'message.png'
    Image.new('RGB',(1500,1500),(50,100,150)).save(carrier)
    result=encode_image_file(carrier,target,secret,KEY,lossless=True,when=when)
    decoded=decode_file(target,KEY)
    assert decoded.image_format=='PNG' and decoded.image_bytes==result.image.data
    assert decoded.generated_at==when
    output=tmp_path/'restored.png';save_image_result(decoded,output)
    with Image.open(output) as image:assert np.array_equal(np.asarray(image),pixels)
    with pytest.raises(PasscodeError):save_image_result(decoded,tmp_path/'wrong.jpg')
    with pytest.raises(AuthenticationError):decode_file(target,'9'*128)

def test_dense_header_redundancy_damage_rotation_and_crop(tmp_path):
    source=tmp_path/'secret.png';Image.new('RGB',(200,120),(40,110,220)).save(source)
    prepared=prepare_image(source,lossless=True)
    envelope=seal_image(prepared,KEY)
    rgb=np.full((600,700,3),127,dtype=np.uint8)
    encoded,layout,nonce=dense.encode(rgb,envelope,KEY)
    assert np.max(np.abs(encoded.astype(int)-rgb.astype(int)))<=1
    for rotation in range(4):
        assert decode_array(np.rot90(encoded,rotation),KEY).image_bytes==prepared.data
    # Lose one authenticated header copy; the other copies still work.
    modified=encoded.copy();ys,xs,cs=dense._indices(np.array([0]),700,600)
    modified[ys,xs,cs]^=1
    assert decode_array(modified,KEY).image_bytes==prepared.data
    # Body corruption is detected, never passed on as an apparently valid PNG.
    available=dense.geometry(700,600)[4]-dense.PREFIX_BITS
    start,step=dense._order(KEY,nonce,available)
    ys,xs,cs=dense._indices(np.array([dense.PREFIX_BITS+start]),700,600)
    modified=encoded.copy();modified[ys,xs,cs]^=1
    with pytest.raises(AuthenticationError):decode_array(modified,KEY)
    with pytest.raises(PasscodeError):decode_array(encoded[5:-5,5:-5],KEY)
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):dense.encode(rgb,envelope,KEY,cancel)

def test_no_extra_resize_when_png_does_not_fit(tmp_path):
    source=tmp_path/'noise.png'
    Image.fromarray(np.random.default_rng(81).integers(0,256,(500,700,3),dtype=np.uint8)).save(source)
    with pytest.raises(PasscodeError,match='不会继续缩小'):
        prepare_image(source,max_bytes=10000,lossless=True)
    image=prepare_image(source,lossless=True)
    assert (image.width,image.height)==(700,500)
    required=dense.square_required(len(image.data))
    assert required and dense.capacity(*required)>=len(image.data)

def test_full_hd_noise_png_real_transport(tmp_path):
    source=tmp_path/'hd.png';cover=tmp_path/'large_cover.png';target=tmp_path/'message.png'
    pixels=np.random.default_rng(50).integers(0,256,(1080,1920,3),dtype=np.uint8)
    Image.fromarray(pixels).save(source)
    Image.new('RGB',(4800,4800),(55,120,200)).save(cover)
    encoded=encode_image_file(cover,target,source,KEY,lossless=True)
    decoded=decode_file(target,KEY)
    assert decoded.image_bytes==encoded.image.data and decoded.image_size==(1920,1080)
    with Image.open(BytesIO(decoded.image_bytes)) as image:assert np.array_equal(np.asarray(image),pixels)
