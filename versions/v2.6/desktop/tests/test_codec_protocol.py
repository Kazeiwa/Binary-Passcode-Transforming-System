from datetime import datetime, timedelta, timezone
import pytest
from bip import codec, protocol
from bip.errors import AuthenticationError, PasscodeError

KEY = '01234567' * 16

@pytest.mark.parametrize('text', ['Hello, 中文@#$^&’', '\\u4e2d', 'A|b\\u\n9.  ', '\x00\r\t\uffff', '繁體かな한글', 'a'*60000, 'A'*59999, '中'*10000])
def test_exact_text(text):
    when = datetime(2026, 11, 3, 1, 23, 59, tzinfo=protocol.CHINA_TIME)
    envelope = protocol.seal(text, KEY, when)
    assert len(envelope) == 37595
    assert len(protocol.HEADER.unpack(envelope[:protocol.HEADER.size])[-2]) == 48
    opened = protocol.open_envelope(envelope, KEY)
    assert opened.text == text
    assert opened.generated_at == when

def test_bmp_exhaustive():
    for cp in range(65536):
        if 0xd800 <= cp <= 0xdfff:
            continue
        char = chr(cp)
        assert codec.decode_units(codec.logical_units(char)) == char
    assert codec.logical_units('@') == [27,20,0,0,4,0]
    assert codec.logical_units('中') == [27,20,4,14,2,13]
    assert codec.logical_units('\\u') == [27,30,30,20]
    assert codec.logical_units('ABc') == [30,0,1,30,2]

@pytest.mark.parametrize('text', ['', 'a'*60001, 'A'*60000, '中'*10001, '\ud800', '\udfff', '\U0001f642'])
def test_invalid_text(text):
    with pytest.raises(PasscodeError):
        codec.pack_text(text)

def test_authentication_before_decode(monkeypatch):
    original = protocol.seal('test', KEY)
    def never(*args):
        raise AssertionError('plaintext processing before authentication')
    monkeypatch.setattr(protocol, 'unpack_text', never)
    positions = list(range(protocol.HEADER.size)) + [100,1000,12500] + list(range(len(original)-32,len(original)))
    for position in positions:
        changed = bytearray(original); changed[position] ^= 1
        with pytest.raises(AuthenticationError):
            protocol.open_envelope(bytes(changed), KEY)
    with pytest.raises(AuthenticationError):
        protocol.open_envelope(original, '9'*128)
    with pytest.raises(AuthenticationError):
        protocol.open_envelope(original[:-1], KEY)

def test_time_bounds_and_randomization():
    for seconds in [0,1,59,60,86400,2147483648,4294967296,9999999999]:
        when = protocol.EPOCH + timedelta(seconds=seconds)
        out = protocol.open_envelope(protocol.seal('test',KEY,when),KEY)
        assert out.generated_at == when.astimezone(protocol.CHINA_TIME)
    for when in [protocol.EPOCH-timedelta(seconds=1), protocol.EPOCH+timedelta(seconds=10000000000)]:
        with pytest.raises(PasscodeError):
            protocol.seal('test',KEY,when)
    utc = datetime(1970,1,1,0,tzinfo=timezone.utc)
    assert protocol.open_envelope(protocol.seal('test',KEY,utc),KEY).generated_at == protocol.EPOCH.astimezone(protocol.CHINA_TIME)
    precise = datetime(2026,11,3,12,34,56,999999,tzinfo=protocol.CHINA_TIME)
    assert protocol.open_envelope(protocol.seal('test',KEY,precise),KEY).generated_at == precise.replace(microsecond=0)
    assert protocol.seal('test',KEY) != protocol.seal('test',KEY)
