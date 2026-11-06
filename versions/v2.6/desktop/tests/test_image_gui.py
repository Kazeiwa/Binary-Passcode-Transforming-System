import re
import os
import sys
import subprocess
import time
from pathlib import Path
import tkinter as tk
import numpy as np
from PIL import Image, ImageGrab
import pytest
from bip.gui import App
from bip.vault import KeyVault

@pytest.mark.parametrize('geometry',['920x680','1140x800'])
def test_image_ui_full_flow(tmp_path,monkeypatch,geometry):
    # Tk root interpreters are process-global on Windows: isolate GUI scenarios.
    if os.environ.get('BIP_GUI_CHILD') != geometry:
        env = os.environ.copy(); env['BIP_GUI_CHILD'] = geometry
        result = subprocess.run([sys.executable, '-m', 'pytest', str(Path(__file__).resolve())+'::test_image_ui_full_flow['+geometry+']', '-q', '--tb=short', '--basetemp='+str(tmp_path/'child')], env=env, capture_output=True, timeout=100)
        assert result.returncode == 0, (result.stdout+result.stderr).decode('utf-8',errors='replace')
        return
    vault=KeyVault(tmp_path/'vault');vault.create('password','GUI image password 123')
    vault.add('图片测试','01234567'*16)
    try:app=App(vault,auto_open=False)
    except tk.TclError:pytest.skip('Tk unavailable')
    errors=[]
    monkeypatch.setattr('bip.gui.messagebox.showerror',lambda title,msg,**kw:errors.append(msg))
    source=tmp_path/'source.png';cover=tmp_path/'cover.png';target=tmp_path/'encoded.png';output=tmp_path/'result.jpg'
    Image.fromarray(np.random.default_rng(41).integers(0,256,(1080,1920,3),dtype=np.uint8)).save(source)
    Image.fromarray(np.random.default_rng(42).integers(0,256,(1024,1024,3),dtype=np.uint8)).save(cover)
    def wait():
        deadline=time.monotonic()+40
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
        app.update();assert not app.busy
    try:
        app.geometry(geometry);app.update()
        app.set_image(False,cover)
        app.enc['mode'].set('image');app._switch_payload();app.update()
        monkeypatch.setattr('bip.gui.filedialog.askopenfilename',lambda **kw:str(source))
        app.choose_secret_image();wait()
        assert app.enc['secret_path'].get()==str(source)
        assert app.enc['secret_frame'].winfo_ismapped() and not app.enc['wrapper'].winfo_ismapped()
        assert app.enc['mode_controls'][-1].winfo_height()>25
        monkeypatch.setattr('bip.gui.filedialog.asksaveasfilename',lambda **kw:str(target))
        app.run_crypto(False);wait()
        assert target.exists() and not errors
        assert app.enc['action'].winfo_height()>25
        assert app.enc['action'].winfo_rooty()+app.enc['action'].winfo_height()<app.winfo_rooty()+app.winfo_height()-55
        assert 'JPG' in app.enc['count'].cget('text')
        app.select_page(1);app.set_image(True,target);app.run_crypto(True);wait()
        assert app.decoded_image is not None and not errors
        assert re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',app.dec['count'].cget('text'))
        assert str(app.dec['save_image_button'].cget('state'))=='normal'
        assert str(app.dec['copy_button'].cget('state'))=='disabled'
        assert app.dec['save_image_button'].winfo_height()>25
        monkeypatch.setattr('bip.gui.filedialog.asksaveasfilename',lambda **kw:str(output))
        app.save_decoded_image();assert output.read_bytes()==app.decoded_image.image_bytes
        with Image.open(output) as image:assert image.format=='JPEG'
        if geometry=='1140x800':
            docs=Path(__file__).resolve().parents[1]/'docs';app.lift();app.update();time.sleep(.1)
            ImageGrab.grab(window=app.winfo_id()).save(docs/'ui_image_decrypt.png')
            app.select_page(0);app.update();ImageGrab.grab(window=app.winfo_id()).save(docs/'ui_image_encrypt.png')
        app._clear_result();assert app.decoded_image is None
        assert str(app.dec['save_image_button'].cget('state'))=='disabled'
        app.select_page(0);app.enc['mode'].set('text');app._switch_payload();app.update()
        assert app.enc['wrapper'].winfo_ismapped() and not app.enc['secret_frame'].winfo_ismapped()
        app.select_page(1);app.set_image(True,target);app.run_crypto(True);wait()
        app.toggle_vault();assert app.decoded_image is None and vault.locked
        assert not errors
    finally:app.close()
