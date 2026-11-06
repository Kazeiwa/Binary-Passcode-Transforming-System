import time
import re
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from PIL import Image
import numpy as np
import pytest
from bip.gui import App
from bip.vault import KeyVault

def test_gui_encrypt_crop_decode_and_compact_layout(tmp_path,monkeypatch):
    vault=KeyVault(tmp_path/'vault');vault.create('password','test master password 2026')
    vault.add('GUI测试','01234567'*16)
    try:
        app=App(vault,auto_open=False)
    except tk.TclError:
        pytest.skip('No GUI display / Tk runtime available')
    errors=[]
    monkeypatch.setattr(messagebox,'showerror',lambda title,msg,**kw:errors.append(msg))
    source=tmp_path/'cover.png';target=tmp_path/'encoded.png'
    Image.fromarray(np.random.default_rng(42).integers(0,256,(768,768,3),dtype=np.uint8)).save(source)
    sample='GUI测试 @#$^&’\n原始末尾空格  '
    def wait():
        end=time.monotonic()+15
        while app.busy and time.monotonic()<end:
            app.update();time.sleep(.01)
        app.update();assert not app.busy
    try:
        app.geometry('920x680');app.update()
        app.set_image(False,source)
        app.enc['text'].insert('1.0',sample)
        monkeypatch.setattr('bip.gui.filedialog.asksaveasfilename',lambda **kw:str(target))
        app.run_crypto(False);wait()
        assert target.exists() and not errors
        assert app.enc['action'].winfo_height()>25
        assert app.enc['action'].winfo_rooty()+app.enc['action'].winfo_height()<app.winfo_rooty()+app.winfo_height()-55
        app.select_page(1);app.set_image(True,target);app.run_crypto(True);wait()
        assert app.dec['text'].get('1.0','end-1c')==sample and not errors
        assert re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',app.dec['count'].cget('text'))
        assert 'Unix' not in app.dec['count'].cget('text') and '时间戳' not in app.dec['count'].cget('text')
        app.set_image(True,target)
        assert app.dec['text'].get('1.0','end-1c')==''
        too_small=tmp_path/'small.bmp';Image.new('RGB',(512,512)).save(too_small)
        previous=app.enc['path'].get()
        app.set_image(False,too_small)
        assert errors and '最低像素' in errors[-1]
        assert app.enc['path'].get()==previous
        app.toggle_vault();assert vault.locked
        assert not app.key_choices
    finally:
        app.close()
