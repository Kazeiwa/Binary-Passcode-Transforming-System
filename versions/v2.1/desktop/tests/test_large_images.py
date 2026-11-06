"""Opt-in memory/performance integration tests: BIP_RUN_LARGE=1 pytest."""
import os
import time
import numpy as np
import pytest
from bip.image_transport import encode_array,decode_array

@pytest.mark.skipif(os.environ.get('BIP_RUN_LARGE')!='1',reason='Set BIP_RUN_LARGE=1 for 24/48 MP tests')
@pytest.mark.parametrize('width,height',[(6000,4000),(8000,6000)])
def test_large_margin_and_ten_percent_crop(width,height):
    rgb=np.full((height,width,3),[92,151,210],dtype=np.uint8)
    text='高清图片 V2.1 @#$^&’'
    start=time.perf_counter()
    encoded,plan,_=encode_array(rgb,text,'01234567'*16)
    assert plan.margin_fraction==.12 and plan.n==196
    mx,my=width//10,height//10
    result=decode_array(encoded[my:height-my,mx:width-mx],'01234567'*16)
    assert result.text==text and result.recovered_shards==plan.n
    assert result.message_format=='2.1'
    print(f'{width}x{height}: {time.perf_counter()-start:.2f}s, 12% margins, crop retains {result.recovered_shards}/{plan.n}')
