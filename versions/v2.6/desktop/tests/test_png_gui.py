import os
import sys
import time
import subprocess
from pathlib import Path
from io import BytesIO
import tkinter as tk
from PIL import Image, ImageDraw, ImageGrab
import numpy as np
import pytest
from bip.gui import App
from bip.vault import KeyVault

def test_png_ui_dual_preview_save_and_clear(tmp_path,monkeypatch):
    if os.environ.get('BIP_PNG_GUI_CHILD')!='1':
        env=os.environ.copy();env['BIP_PNG_GUI_CHILD']='1'
        result=subprocess.run([sys.executable,'-m','pytest',str(Path(__file__).resolve())+'::test_png_ui_dual_preview_save_and_clear','-q','--tb=short','--basetemp='+str(tmp_path/'child')],env=env,capture_output=True,timeout=100)
        assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8',errors='replace')
        return
    vault=KeyVault(tmp_path/'vault');vault.create('password','PNG preview password 123');vault.add('无损图片测试','01234567'*16)
    try:app=App(vault,auto_open=False)
    except tk.TclError:pytest.skip('Tk unavailable')
    errors=[];monkeypatch.setattr('bip.gui.messagebox.showerror',lambda title,msg,**kw:errors.append(msg))
    source=tmp_path/'secret.png';cover=tmp_path/'cover.png';target=tmp_path/'message.png';output=tmp_path/'restored.png'
    image=Image.new('RGBA',(640,360),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((20,20,620,340),radius=32,fill=(20,125,115,210))
    draw.ellipse((60,65,260,265),fill=(255,198,58,255));draw.rectangle((300,90,570,140),fill=(255,255,255,255))
    draw.rectangle((300,175,520,215),fill=(181,229,228,255));image.save(source);pixels=np.array(image)
    image=Image.new('RGB',(1536,1024),(80,155,220));draw=ImageDraw.Draw(image)
    draw.ellipse((1050,100,1300,350),fill=(255,215,105));draw.polygon([(0,800),(400,400),(800,800),(1150,500),(1536,900),(1536,1024),(0,1024)],fill=(50,120,90));image.save(cover)
    def wait():
        deadline=time.monotonic()+40
        while app.busy and time.monotonic()<deadline:app.update();time.sleep(.01)
        app.update();assert not app.busy
    try:
        for geometry in ('920x680','1140x800'):
            app.geometry(geometry);app.select_page(0);app.update();app.set_image(False,cover)
            app.enc['mode'].set('image');app._switch_payload()
            app.enc['lossless'].set(True);app._compression_changed();app.update()
            monkeypatch.setattr('bip.gui.filedialog.askopenfilename',lambda **kw:str(source));app.choose_secret_image();wait()
            assert app.enc['preview'].cget('image') and app.enc['secret_preview'].cget('image')
            assert app.enc['png_option'].winfo_height()>20
            assert app.enc['preview'].winfo_height()>20 and app.enc['secret_preview'].winfo_height()>20
            assert str(app.enc['strength_combo'].cget('state'))=='disabled'
            monkeypatch.setattr('bip.gui.filedialog.asksaveasfilename',lambda **kw:str(target));app.run_crypto(False);wait()
            assert target.exists() and not errors
            if geometry=='1140x800':
                docs=Path(__file__).resolve().parents[1]/'docs';app.lift();app.update();time.sleep(.1)
                ImageGrab.grab(window=app.winfo_id()).save(docs/'ui_png_encrypt.png')
            app.select_page(1);app.set_image(True,target);app.run_crypto(True);wait()
            assert app.decoded_image.image_format=='PNG'
            assert app.dec['preview'].cget('image') and app.dec['secret_preview'].cget('image')
            assert app.dec['preview'].winfo_height()>20 and app.dec['secret_preview'].winfo_height()>20
            assert 'PNG' in app.dec['save_image_button'].cget('text')
            monkeypatch.setattr('bip.gui.filedialog.asksaveasfilename',lambda **kw:str(output));app.save_decoded_image()
            with Image.open(output) as restored:assert np.array_equal(np.asarray(restored),pixels)
            if geometry=='1140x800':
                app.update();ImageGrab.grab(window=app.winfo_id()).save(docs/'ui_png_decrypt.png')
            app._clear_result();assert not app.dec['secret_preview'].cget('image')
            assert app.dec['preview'].cget('image')  # Clearing plaintext keeps the selected carrier.
        app.select_page(0);app.enc['mode'].set('text');app._switch_payload()
        assert str(app.enc['strength_combo'].cget('state'))=='readonly'
        assert not errors
    finally:app.close()
