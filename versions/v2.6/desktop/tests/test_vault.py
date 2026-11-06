import json
import os
from unittest.mock import patch
import pytest
from bip.errors import PasscodeError
from bip.vault import KeyVault

PASSWORD='A correct master password 2026'
BACKUP_PASSWORD='A separate backup password 2026'
KEY='01234567'*16

def test_crud_restart_and_encrypted_backup(tmp_path):
    path=tmp_path/'vault'
    vault=KeyVault(path);vault.create('password',PASSWORD)
    first=vault.add('联系人一',KEY);second=vault.add('联系人二')
    second_key=vault.get(second)
    assert KEY.encode() not in path.read_bytes() and '联系人一'.encode() not in path.read_bytes()
    assert vault.default_id==first
    vault.set_default(second);vault.rename(first,'家人')
    with pytest.raises(PasscodeError):vault.add('重复密钥',KEY)
    with pytest.raises(PasscodeError):vault.rename(first,'联系人二')
    backup=vault.export_backup(BACKUP_PASSWORD)
    assert KEY.encode() not in backup
    vault.lock()
    with pytest.raises(PasscodeError):vault.get(first)
    with pytest.raises(PasscodeError):vault.unlock('a wrong password value')
    assert vault.locked
    again=KeyVault(path);again.unlock(PASSWORD)
    assert again.get(first)==KEY and again.default_id==second
    again.delete(second);assert again.default_id==first
    other=KeyVault(tmp_path/'other');other.create('password',PASSWORD)
    other.add('家人')
    assert other.import_backup(backup,BACKUP_PASSWORD)==2
    assert other.import_backup(backup,BACKUP_PASSWORD)==0
    assert len({r['name'] for r in other.list_keys()})==3
    empty=KeyVault(tmp_path/'empty');empty.create('password',PASSWORD)
    empty.import_backup(backup,BACKUP_PASSWORD)
    assert empty.get(empty.default_id)==second_key
    with pytest.raises(PasscodeError):other.import_backup(backup,'a wrong backup password')
    broken=json.loads(backup);broken['ciphertext']=broken['ciphertext'][:-4]+'AAAA'
    with pytest.raises(PasscodeError):other.import_backup(json.dumps(broken).encode(),BACKUP_PASSWORD)

def test_concurrent_revision_and_atomic_failure(tmp_path,monkeypatch):
    path=tmp_path/'vault';first=KeyVault(path);first.create('password',PASSWORD)
    second=KeyVault(path);second.unlock(PASSWORD)
    first.add('new')
    with pytest.raises(PasscodeError,match='另一个窗口'):
        second.add('stale')
    before=path.read_bytes()
    def fail(*args):raise OSError('simulated disk failure')
    with monkeypatch.context() as scoped:
        scoped.setattr('bip.vault.os.replace',fail)
        with pytest.raises(PasscodeError):first.add('not saved')
    assert path.read_bytes()==before and len(first.list_keys())==1

@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI only')
def test_native_windows(tmp_path):
    path=tmp_path/'vault';vault=KeyVault(path);vault.create()
    identity=vault.add('native',KEY);vault.lock()
    again=KeyVault(path);again.unlock()
    assert again.get(identity)==KEY
    assert KEY.encode() not in path.read_bytes()

def test_linux_secret_service_dispatch(tmp_path,monkeypatch):
    store={}
    def service(identity,secret=None):
        if secret is not None:store[identity]=secret
        else:return store[identity]
    monkeypatch.setattr('bip.vault._secret_service',service)
    monkeypatch.setattr('bip.vault._system_mode',lambda:'linux')
    vault=KeyVault(tmp_path/'linux');vault.create()
    identity=vault.add('linux key',KEY);vault.lock();vault.unlock()
    assert vault.mode=='linux' and vault.get(identity)==KEY
    # The actual subprocess contract is tested independently of host path classes.
    import subprocess
    calls=[]
    def run(arguments,**options):
        calls.append((arguments,options))
        return subprocess.CompletedProcess(arguments,0,'ab'*32+'\n','')
    from bip import vault as module
    monkeypatch.undo()
    with patch('bip.vault.subprocess.run',side_effect=run):
        assert module._secret_service('id')==bytes.fromhex('ab'*32)
        module._secret_service('id',bytes.fromhex('ab'*32))
    assert calls[0][0][-4:]==['application','binary_image_passcode','vault','id']
    assert 'ab'*32 not in calls[1][0]
    assert calls[1][1]['input']=='ab'*32+'\n'
