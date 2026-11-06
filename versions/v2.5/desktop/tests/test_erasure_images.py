from itertools import combinations
import threading
import numpy as np
from PIL import Image
import pytest
from bip import erasure
from bip.errors import PasscodeError, Cancelled
from bip import image_transport as transport
from bip.protocol import derive_key

KEY = '01234567'*16
TEXT = '中文测试 Hello @#$^&’\n保留原文末尾空格  '

@pytest.fixture(scope='module')
def image():
    rgb = np.random.default_rng(194).integers(0,256,(1024,1024,3),dtype=np.uint8)
    encoded, plan, nonce = transport.encode_array(rgb, TEXT, KEY)
    return rgb, encoded, plan, nonce

def test_any_k_shards():
    data = bytes(range(251))*7
    shards = erasure.encode(data,8,4)
    assert b''.join(shards[:4])[:len(data)] == data
    for subset in combinations(range(8),4):
        assert erasure.decode({i:shards[i] for i in subset},8,4,len(data)) == data

@pytest.mark.parametrize('shape', [(768,768), (743,987), (1152,768), (900,1600), (256,5000)])
def test_shapes(shape):
    h,w=shape
    rgb=np.random.default_rng(w+h).integers(0,256,(h,w,3),dtype=np.uint8)
    encoded, plan, _=transport.encode_array(rgb,TEXT,KEY)
    assert transport.decode_array(encoded,KEY).text==TEXT
    assert len(set(plan.origins))==plan.n
    assert all(x>=plan.margin_x and y>=plan.margin_y and x+128<=w-plan.margin_x and y+128<=h-plan.margin_y for x,y in plan.origins)
    assert np.max(np.abs(encoded.astype(np.int16)-rgb.astype(np.int16)))<=1

def test_lossless_and_crop(image,tmp_path):
    rgb, encoded, plan, _=image
    original=tmp_path/'original.png';target=tmp_path/'encoded.png'
    Image.fromarray(rgb).save(original)
    transport.encode_file(original,target,TEXT,KEY)
    assert transport.decode_file(target,KEY).text==TEXT
    with Image.open(target) as opened:
        opened.save(tmp_path/'recompressed.png',compress_level=9)
    assert transport.decode_file(tmp_path/'recompressed.png',KEY).text==TEXT
    for box in [(102,102,922,922),(154,154,870,870),(256,256,1024,1024),(256,0,1024,1024)]:
        x1,y1,x2,y2=box
        result=transport.decode_array(encoded[y1:y2,x1:x2],KEY)
        assert result.text==TEXT and result.recovered_shards>=plan.k
    with pytest.raises(PasscodeError):
        transport.decode_array(encoded[:,512:],KEY)

def test_strong_half_width():
    rgb=np.random.default_rng(91).integers(0,256,(1024,1024,3),dtype=np.uint8)
    encoded,plan,_=transport.encode_array(rgb,TEXT,KEY,'strong')
    assert plan.k==17 and plan.n==49
    assert transport.decode_array(encoded[:,512:],KEY).text==TEXT

@pytest.mark.parametrize('rotation',[1,2,3])
def test_rotations(image,rotation):
    assert transport.decode_array(np.rot90(image[1],rotation),KEY).text==TEXT

def test_rgb_independent_channels():
    tile=np.zeros((128,128,3),dtype=np.uint8)
    slots=np.array([0,1,2,3,4,5])
    bits=np.array([1,0,1,0,1,0],dtype=np.uint8)
    transport._write_bits(tile,slots,bits)
    assert tile[0,0].tolist()==[1,0,1]
    assert tile[0,1].tolist()==[0,1,0]
    assert transport._read_bytes(tile,np.array([0,1,2,3,4,5,6,7]))==b'\xa8'

def test_inner_correction(image):
    _, encoded, plan, nonce=image
    changed=encoded.copy()
    prefix,pool=transport._header_positions(KEY)
    positions=transport._body_positions(pool,KEY,nonce,0,transport.coded_length(plan.shard_size+16)*8)
    x,y=plan.origins[0]
    for position in list(prefix[::8][:3])+list(positions[::8][:6]):
        pixel,channel=divmod(int(position),3)
        yy,xx=y+pixel//128,x+pixel%128
        changed[yy,xx,channel]^=1
    result=transport.decode_array(changed,KEY)
    assert result.text==TEXT and result.corrected_bytes>=9

def test_bad_key_no_data(image):
    with pytest.raises(PasscodeError):
        transport.decode_array(image[1],'9'*128)
    with pytest.raises(PasscodeError):
        transport.decode_array(image[0],KEY)

def test_resampling_and_jpeg(image,tmp_path):
    source=Image.fromarray(image[1])
    altered=np.array(source.resize((900,900),Image.Resampling.LANCZOS))
    with pytest.raises(PasscodeError):
        transport.decode_array(altered,KEY)
    source.save(tmp_path/'lossy.jpg',quality=95)
    with pytest.raises(PasscodeError):
        transport.decode_file(tmp_path/'lossy.jpg',KEY)

def test_capacity_cancellation_and_files(image,tmp_path):
    with pytest.raises(PasscodeError):
        transport.plan_layout(512,512)
    with pytest.raises(PasscodeError):
        transport.plan_layout(10,100000)
    event=threading.Event();event.set()
    with pytest.raises(Cancelled):
        transport.encode_array(image[0],TEXT,KEY,cancel=event)
    source=tmp_path/'source.png';Image.fromarray(image[0]).save(source)
    before=source.read_bytes()
    with pytest.raises(PasscodeError):
        transport.encode_file(source,source,TEXT,KEY,overwrite=True)
    assert source.read_bytes()==before
    output=tmp_path/'existing.png';output.write_bytes(b'keep')
    with pytest.raises(PasscodeError):
        transport.encode_file(source,output,TEXT,KEY)
    assert output.read_bytes()==b'keep'

@pytest.mark.parametrize('size,margin', [((1024,1024),.04),((2048,2048),.08),((4096,4096),.12),((8000,6000),.12)])
def test_adaptive_margins(size,margin):
    plan=transport.plan_layout(*size)
    assert plan.margin_fraction==pytest.approx(margin)
    assert all(x>=plan.margin_x and y>=plan.margin_y for x,y in plan.origins)

@pytest.mark.parametrize('size,strength,valid', [((559,560),'balanced',False),((560,560),'balanced',True),((695,696),'strong',False),((696,696),'strong',True)])
def test_minimum_pixels(size,strength,valid):
    if valid:
        assert transport.plan_layout(*size,strength).n>=16
        rgb=np.full((size[1],size[0],3),[91,145,208],dtype=np.uint8)
        encoded,_,_=transport.encode_array(rgb,TEXT,KEY,strength)
        assert transport.decode_array(encoded,KEY).text==TEXT
    else:
        with pytest.raises(PasscodeError,match='最低像素'):
            transport.plan_layout(*size,strength)

@pytest.mark.parametrize('extension,mode', [('jpg','RGB'),('bmp','RGB'),('bmp','P'),('tiff','RGBA'),('webp','RGB')])
def test_input_formats(tmp_path,extension,mode):
    source=tmp_path/f'input_{mode}.{extension}';output=tmp_path/f'output_{mode}_{extension}.png'
    Image.new('RGB',(768,768),(91,145,208)).convert(mode).save(source)
    transport.encode_file(source,output,TEXT,KEY)
    with Image.open(output) as image:
        assert image.format=='PNG' and image.mode=='RGB'
    assert transport.decode_file(output,KEY).text==TEXT

def test_v20_backward_compatibility():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    expected=(root/'examples/v20/demo_message.txt').read_text(encoding='utf-8')
    for name in ['demo_encoded.png','demo_cropped.png']:
        result=transport.decode_file(root/'examples/v20'/name,KEY)
        assert result.text==expected and result.message_format=='2.0'

def test_locator_strip_boundary():
    rgb=np.zeros((600,600,3),dtype=np.uint8)
    origin=(100,247)
    transport._paint_finders(rgb[247:375,100:228])
    assert origin in transport.locate_tiles(rgb[:,:,0]&1)
