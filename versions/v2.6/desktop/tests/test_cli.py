import importlib.util
from pathlib import Path
import pytest
from bip.vault import KeyVault

def test_cli_utf8_and_line_endings(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('bip_cli',root/'binary_image_passcode.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    password='cli master password 2026'
    vault=KeyVault(tmp_path/'vault');vault.create('password',password);vault.add('cli','01234567'*16);vault.lock()
    monkeypatch.setattr(cli,'getpass',lambda prompt:password)
    text='中文\r\n@#$^&’\n末尾空格  '
    source=tmp_path/'message.txt';source.write_bytes(text.encode('utf-8'))
    encoded=tmp_path/'encoded.png';decoded=tmp_path/'decoded.txt'
    assert cli.main(['encode',str(root/'examples/demo_cover.png'),'--output',str(encoded),'--text-file',str(source),'--vault',str(vault.path),'--key','cli'])==0
    assert cli.main(['decode',str(encoded),'--output',str(decoded),'--vault',str(vault.path),'--key','cli'])==0
    assert decoded.read_bytes().decode('utf-8')==text
    assert cli.main(['encode',str(root/'examples/demo_cover.png'),'--output',str(encoded),'--text-file',str(source),'--vault',str(vault.path)])==1
