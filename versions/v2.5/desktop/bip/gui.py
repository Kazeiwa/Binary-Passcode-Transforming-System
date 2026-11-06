"""Tk desktop client. Protocol, image transport and key storage remain independent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from io import BytesIO
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter import font as tkfont
from PIL import Image, ImageOps, ImageTk
from . import APP_NAME, __version__
from .codec import logical_units
from .errors import PasscodeError, Cancelled
from .image_transport import encode_file, decode_file, plan_layout, MAX_PIXELS, MAX_SIDE, MIN_PIXELS
from .vault import KeyVault, atomic_write
from .image_payload import encode_image_file, jpeg_capacity, save_image_result

BG = '#f3f6f8'
CARD = '#ffffff'
INK = '#182635'
MUTED = '#5d6c7c'
ACCENT = '#0e7065'
RED = '#a9322f'

class FormDialog(tk.Toplevel):
    def __init__(self, parent, title, fields, submit_text='确定', note=None, on_submit=None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.configure(bg=CARD)
        self.resizable(False, False)
        self.result = None
        self.on_submit = on_submit
        frame = tk.Frame(self, bg=CARD, padx=24, pady=20)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text=title, bg=CARD, fg=INK, font=(parent.font_family, 16, 'bold')).pack(anchor='w', pady=(0, 14))
        if note:
            tk.Label(frame, text=note, bg=CARD, fg=MUTED, justify='left', wraplength=460).pack(anchor='w', pady=(0, 12))
        self.inputs = []
        for label, initial, secret in fields:
            tk.Label(frame, text=label, bg=CARD, fg=INK).pack(anchor='w', pady=(5, 4))
            entry = ttk.Entry(frame, width=52, show='●' if secret else '')
            entry.insert(0, initial)
            entry.pack(fill='x', ipady=5)
            self.inputs.append(entry)
        self.error = tk.Label(frame, text='', bg=CARD, fg=RED, wraplength=460, justify='left')
        self.error.pack(anchor='w', pady=(10, 0))
        buttons = tk.Frame(frame, bg=CARD)
        buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='取消', command=self.destroy).pack(side='right')
        ttk.Button(buttons, text=submit_text, style='Accent.TButton', command=self.submit).pack(side='right', padx=(0, 8))
        self.bind('<Return>', lambda e: self.submit())
        self.bind('<Escape>', lambda e: self.destroy())
        self.update_idletasks()
        self.geometry(f'+{parent.winfo_rootx()+80}+{parent.winfo_rooty()+90}')
        self.grab_set()
        if self.inputs:
            self.inputs[0].focus_set()

    def submit(self):
        values = [entry.get() for entry in self.inputs]
        try:
            self.result = self.on_submit(values) if self.on_submit else values
        except Exception as error:
            self.error.configure(text=str(error) if isinstance(error, PasscodeError) else '操作未完成，请检查输入后重试。')
            return
        for entry in self.inputs:
            entry.delete(0, 'end')
        self.destroy()

class App(tk.Tk):
    def __init__(self, vault=None, auto_open=True):
        super().__init__()
        self.title('binary_image_passcode · ' + APP_NAME)
        self.geometry('1140x800')
        self.minsize(920, 680)
        self.configure(bg=BG)
        self.vault = vault or KeyVault()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='bip-worker')
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.active_page = 0
        self.key_choices = {}
        self.preview_images = {}
        self.decoded_image = None
        self._count_after = None
        self._styles()
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets'
        if (assets / 'binary_image_passcode.png').exists():
            self._app_icon = tk.PhotoImage(file=str(assets / 'binary_image_passcode.png'))
            self.iconphoto(True, self._app_icon)
        self._build()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(60, self._poll)
        self.refresh_keys()
        if auto_open and self.vault.locked:
            self.after(250, self.open_vault)

    def _styles(self):
        families = set(tkfont.families(self))
        self.font_family = next((name for name in ('Microsoft YaHei UI', 'Microsoft YaHei', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans') if name in families), 'sans-serif')
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont'):
            tkfont.nametofont(name).configure(family=self.font_family, size=10)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=(self.font_family, 10), background=BG, foreground=INK)
        style.configure('TButton', padding=(13, 8), background=CARD, borderwidth=0)
        style.map('TButton', background=[('active', '#e5eeec')])
        style.configure('Accent.TButton', background=ACCENT, foreground='white')
        style.map('Accent.TButton', background=[('active', '#095b52'), ('disabled', '#94b3ad')], foreground=[('disabled', '#edf2f1')])
        style.configure('TCombobox', padding=5, fieldbackground='white')
        style.configure('TEntry', padding=5, fieldbackground='white')
        style.configure('Treeview', rowheight=34, background=CARD, fieldbackground=CARD, borderwidth=0)
        style.configure('Treeview.Heading', padding=8, background='#e9efef', font=(self.font_family, 10, 'bold'))
        style.map('Treeview', background=[('selected', ACCENT)], foreground=[('selected', 'white')])
        style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor='#dde7e5', borderwidth=0)

    def label(self, parent, text='', size=11, color=INK, bold=False, bg=CARD, **kwargs):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=(self.font_family, size, 'bold' if bold else 'normal'), **kwargs)

    def _build(self):
        header = tk.Frame(self, bg=BG, padx=24, pady=18)
        header.pack(fill='x')
        logo = tk.Canvas(header, width=42, height=42, bg=BG, highlightthickness=0)
        logo.create_rectangle(1, 1, 41, 41, fill=ACCENT, outline=ACCENT)
        logo.create_text(21, 21, text='>_', fill='white', font=('TkFixedFont', 17, 'bold'))
        logo.pack(side='left', padx=(0, 12))
        titles = tk.Frame(header, bg=BG)
        titles.pack(side='left')
        self.label(titles, APP_NAME, 20, bold=True, bg=BG).pack(anchor='w')
        self.label(titles, f'binary_image_passcode  /  V{__version__}  /  本地处理', 10, MUTED, bg=BG).pack(anchor='w', pady=(4, 0))
        self.vault_button = ttk.Button(header, text='解锁密钥库', command=self.toggle_vault)
        self.vault_button.pack(side='right')
        self.vault_status = self.label(header, '', 10, MUTED, bg=BG)
        self.vault_status.pack(side='right', padx=12)
        nav = tk.Frame(self, bg=BG, padx=24)
        nav.pack(fill='x')
        self.nav_buttons = []
        for i, name in enumerate(('图片加密', '图片解密', '密钥管理', '使用说明')):
            button = ttk.Button(nav, text=name, command=lambda index=i: self.select_page(index))
            button.pack(side='left', padx=(0, 10))
            self.nav_buttons.append(button)
        self.content = tk.Frame(self, bg=BG, padx=24, pady=18)
        self.content.pack(fill='both', expand=True)
        self.pages = [self._crypto_page(False), self._crypto_page(True), self._key_page(), self._help_page()]
        footer = tk.Frame(self, bg=BG, padx=24, pady=10)
        footer.pack(side='bottom', fill='x', before=self.content)
        self.progress = ttk.Progressbar(footer, mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=(0, 6))
        self.status = self.label(footer, '就绪。', 10, MUTED, bg=BG, anchor='w')
        self.status.configure(width=1, wraplength=880)
        self.status.pack(side='left', fill='x', expand=True)
        self.cancel_button = ttk.Button(footer, text='取消操作', command=self.cancel.set, state='disabled')
        self.cancel_button.pack(side='right')
        self.select_page(0)

    def _text(self, parent, height=12, readonly=False):
        wrapper = tk.Frame(parent, bg=CARD)
        text = tk.Text(wrapper, height=height, wrap='word', relief='flat', borderwidth=0, bg='#f6f8fa',
                       fg=INK, insertbackground=ACCENT, padx=12, pady=12, font=(self.font_family, 11), undo=not readonly)
        scrollbar = ttk.Scrollbar(wrapper, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        if readonly:
            text.configure(state='disabled')
        return wrapper, text

    def _crypto_page(self, decrypting):
        page = tk.Frame(self.content, bg=BG)
        page.columnconfigure(0, weight=3, minsize=450)
        page.columnconfigure(1, weight=2, minsize=310)
        page.rowconfigure(0, weight=1)
        left = tk.Frame(page, bg=CARD, padx=20, pady=18)
        right = tk.Frame(page, bg=CARD, padx=18, pady=18)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        right.grid(row=0, column=1, sticky='nsew')
        self.label(left, '从图片恢复消息' if decrypting else '把消息写入图片', 17, bold=True).pack(anchor='w')
        self.label(left, '', 1, MUTED).pack(pady=(0, 2))
        row = tk.Frame(left, bg=CARD)
        row.pack(fill='x')
        self.label(row, '使用密钥').pack(side='left', padx=(0, 12))
        combo = ttk.Combobox(row, state='readonly')
        combo.pack(side='left', fill='x', expand=True)
        if decrypting:
            combo.bind('<<ComboboxSelected>>', lambda e: self._clear_result())
        ttk.Button(row, text='管理', command=lambda: self.select_page(2)).pack(side='left', padx=(8, 0))
        self.label(left, '消息图片' if decrypting else '载体图片', 11, bold=True).pack(anchor='w', pady=(16, 7))
        file_row = tk.Frame(left, bg=CARD)
        file_row.pack(fill='x')
        path = tk.StringVar()
        ttk.Entry(file_row, textvariable=path, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(file_row, text='选择图片', command=lambda: self.choose_image(decrypting)).pack(side='left', padx=(8, 0))
        mode = tk.StringVar(value='text')
        secret_path = tk.StringVar()
        mode_controls = []
        secret_frame = None
        if not decrypting:
            mode_row = tk.Frame(left, bg=CARD)
            mode_row.pack(fill='x', pady=(12, 0))
            self.label(mode_row, '消息内容').pack(side='left', padx=(0, 12))
            for title, value in [('文字', 'text'), ('图片', 'image')]:
                radio = ttk.Radiobutton(mode_row, text=title, value=value, variable=mode, command=self._switch_payload)
                radio.pack(side='left', padx=(0, 12)); mode_controls.append(radio)
        if decrypting:
            self.label(left, '解密结果（自动识别文字或图片）', 11, bold=True).pack(anchor='w', pady=(12, 7))
        wrapper, text = self._text(left, height=4, readonly=decrypting)
        bottom = tk.Frame(left, bg=CARD)
        bottom.pack(side='bottom', fill='x')
        wrapper.pack(fill='both', expand=True)
        if not decrypting:
            secret_frame = tk.Frame(left, bg=CARD)
            secret_row = tk.Frame(secret_frame, bg=CARD)
            secret_row.pack(fill='x', pady=(0, 8))
            secret_button = ttk.Button(secret_row, text='选择图片正文', command=self.choose_secret_image)
            secret_button.pack(side='right', padx=(8, 0)); mode_controls.append(secret_button)
            ttk.Entry(secret_row, textvariable=secret_path, state='readonly').pack(side='left', fill='x', expand=True)
            self.label(secret_frame, '支持任意尺寸的常见格式静态图片。\n自动适配至横版1920×1080或竖版1080×1920以内。\n按载体空间压缩为JPG；必要时进一步缩小尺寸。\n透明区域会铺白底。解密后可预览并保存JPG。', 10, MUTED, justify='left', wraplength=430).pack(anchor='w')
        count = self.label(bottom, '等待解密。' if decrypting else '0 / 60,000 字符  ·  0 / 60,000 编码单元', 10, MUTED, anchor='w')
        count.pack(fill='x', pady=(6, 0))
        strength = tk.StringVar(value='均衡冗余')
        strength_combo = None
        if not decrypting:
            controls = tk.Frame(bottom, bg=CARD)
            controls.pack(fill='x', pady=(12, 0))
            self.label(controls, '裁剪冗余').pack(side='left', padx=(0, 12))
            strength_combo = ttk.Combobox(controls, values=['均衡冗余', '增强抗裁剪'], state='readonly', textvariable=strength, width=15)
            strength_combo.pack(side='left')
            strength_combo.bind('<<ComboboxSelected>>', lambda e: self._update_image_info(False))
        action = ttk.Button(bottom, text='解密图片' if decrypting else '加密并保存PNG', style='Accent.TButton', command=lambda: self.run_crypto(decrypting))
        action.pack(fill='x', pady=(14, 0))
        if decrypting:
            actions = tk.Frame(bottom, bg=CARD)
            actions.pack(fill='x', pady=(10, 0))
            copy_button = ttk.Button(actions, text='复制正文', command=self.copy_result)
            copy_button.pack(side='left')
            save_text_button = ttk.Button(actions, text='保存正文', command=self.save_result)
            save_text_button.pack(side='left', padx=8)
            save_image_button = ttk.Button(actions, text='保存图片为JPG', command=self.save_decoded_image, state='disabled')
            save_image_button.pack(side='left')
        self.label(right, '图片预览', 12, bold=True).pack(anchor='w')
        right_bottom = tk.Frame(right, bg=CARD)
        right_bottom.pack(side='bottom', fill='x')
        preview = tk.Label(right, text='选择一张本地图片', bg='#edf2f3', fg=MUTED, width=36, height=15)
        preview.pack(fill='both', expand=True, pady=(12, 14))
        info = self.label(right_bottom, '', 10, MUTED, justify='left', anchor='nw', wraplength=270)
        info.pack(fill='x')
        hint = ('支持原尺寸裁剪和90°倍数旋转。只有保留足够完整数据块时才能恢复；缩放、截图、JPEG转换通常会破坏信息。'
                if decrypting else '最低总像素：\n均衡313,600（方图560×560）\n增强484,416（方图696×696）\n推荐1024×1024及以上。\n长条图另按布局检查，\nJPG、BMP等统一输出PNG。')
        self.label(right_bottom, hint, 10, MUTED, justify='left', wraplength=270).pack(anchor='w', pady=(14, 0))
        widgets = {'page': page, 'path': path, 'combo': combo, 'text': text, 'count': count,
                   'mode': mode, 'secret_path': secret_path, 'mode_controls': mode_controls,
                   'wrapper': wrapper, 'secret_frame': secret_frame, 'bottom': bottom,
                   'preview': preview, 'info': info, 'strength': strength, 'strength_combo': strength_combo, 'action': action, 'size': None}
        if decrypting:
            widgets.update(copy_button=copy_button, save_text_button=save_text_button, save_image_button=save_image_button)
            self.dec = widgets
        else:
            self.enc = widgets
            text.bind('<<Modified>>', self._text_changed)
        return page

    def _key_page(self):
        page = tk.Frame(self.content, bg=CARD, padx=22, pady=20)
        self.label(page, '一个密钥库，管理多把密钥', 17, bold=True).pack(anchor='w')
        self.label(page, '原始密钥和名称加密保存。删除前请先备份；默认密钥仅用于预先选择。', 10, MUTED).pack(anchor='w', pady=(6, 16))
        table = tk.Frame(page, bg=CARD)
        bottom = tk.Frame(page, bg=CARD)
        bottom.pack(side='bottom', fill='x')
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('name', 'fingerprint', 'created', 'default'), show='headings', selectmode='browse')
        for name, label, width in [('name', '名称', 300), ('fingerprint', '指纹', 160), ('created', '创建日期', 200), ('default', '默认', 70)]:
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=60, stretch=name == 'name')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        buttons = tk.Frame(bottom, bg=CARD)
        buttons.pack(fill='x', pady=(16, 0))
        for label, function in [('生成新密钥', self.new_key), ('导入密钥', self.import_key), ('重命名', self.rename_key),
                                ('设为默认', self.default_key), ('显示/复制', self.show_key), ('删除', self.delete_key)]:
            ttk.Button(buttons, text=label, command=function).pack(side='left', padx=(0, 8))
        backups = tk.Frame(bottom, bg=CARD)
        backups.pack(fill='x', pady=(12, 0))
        ttk.Button(backups, text='导出加密备份', command=self.export_backup).pack(side='left', padx=(0, 8))
        ttk.Button(backups, text='导入加密备份', command=self.import_backup).pack(side='left')
        self.label(bottom, '跨设备请传递原始128位密钥或带密码的加密备份；不要直接搬运系统保护的密钥库文件。', 10, MUTED).pack(anchor='w', pady=(14, 0))
        return page

    def _help_page(self):
        page = tk.Frame(self.content, bg=CARD, padx=24, pady=20)
        self.label(page, '发送与恢复', 17, bold=True).pack(anchor='w', pady=(0, 14))
        wrapper, text = self._text(page, readonly=False)
        wrapper.pack(fill='both', expand=True)
        text.insert('1.0', '''1  配置密钥
在“密钥管理”生成或导入128位数字密钥。发送端和接收端必须使用同一把密钥，开头的零不能删除。

2  选择消息内容
在加密页选择“文字”或“图片”，再选择一张载体图片。
文字最多60,000编码单元，中文等扩展字符各占6单元，保留原始换行和尾部空格。
待加密图片不设原始分辨率上限，支持PNG、JPG、BMP、WebP、TIFF等静态格式，自动适配至横版1920×1080或竖版1080×1920以内，再压缩为JPG。程序根据载体空间调整质量，必要时进一步缩小；原始图片不会被改写。较大的载体有助于保留画质。
两种消息都保存为载体PNG。解密时自动识别内容；图片结果可预览并保存为JPG。

3  传递图片
按文件发送输出PNG，避免缩放、截图、滤镜和JPEG转换。图片重新无损压缩但不改变像素时仍可恢复。

4  抗裁剪的范围
每个小块都有三点定位和独立认证。只要留下足够的完整、可读小块，就能恢复全文；界面会显示恢复门限。增强冗余允许丢失更多小块，但需要更多像素。大图边缘留白由4%逐步增至12%，以留出更大的裁剪缓冲。
面积保留比例不等于可读块比例。严重裁剪、切碎后拼接、插值缩放和有损压缩不保证恢复。90度倍数旋转不插值时可以识别。

5  验证与错误
程序先纠错并验证消息，认证通过后才显示文字或图片。两种消息都保留秒级生成时间，解密后按北京时间显示；生成时间取自发送设备的时钟。

6  密钥保护
Windows可用账户保护，Linux可用系统密钥环；也可选择主密码保护。主密码和备份密码至少12字符。密码遗失无法恢复，删除密钥前务必备份。
锁定会停止后续密钥访问，但Python不能承诺彻底擦除进程内存。程序不会把密钥或正文写入日志。

7  隐写不等于不可检测
普通显示中的颜色变化很小，但定位图样和像素奇偶变化仍可能被统计分析识别。程序不承诺规避平台检测，也不保护图片之外的通信元数据。''')
        text.configure(state='disabled')
        return page

    def select_page(self, index):
        for page in self.pages:
            page.pack_forget()
        self.pages[index].pack(fill='both', expand=True)
        self.active_page = index
        for i, button in enumerate(self.nav_buttons):
            button.configure(style='Accent.TButton' if i == index else 'TButton')

    def _text_changed(self, event=None):
        if not self.enc['text'].edit_modified():
            return
        self.enc['text'].edit_modified(False)
        if self._count_after:
            self.after_cancel(self._count_after)
        self._count_after = self.after(150, self._update_count)

    def _update_count(self):
        self._count_after = None
        if self.enc['mode'].get() == 'image':
            self.enc['count'].configure(text='图片将自动压缩；最终尺寸与大小将在保存后显示。', fg=MUTED)
            return
        text = self.enc['text'].get('1.0', 'end-1c')
        try:
            count = len(logical_units(text)) if text else 0
            self.enc['count'].configure(text=f'{len(text):,} / 60,000 字符  ·  {count:,} / 60,000 编码单元', fg=MUTED)
        except PasscodeError as error:
            self.enc['count'].configure(text=str(error), fg=RED)

    def choose_image(self, decrypting):
        if self.busy:
            self.status.configure(text='请先等待或取消当前操作。')
            return
        path = filedialog.askopenfilename(parent=self, title='选择消息图片' if decrypting else '选择载体图片',
                                          filetypes=[('图片文件', '*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff'), ('所有文件', '*.*')])
        if not path:
            return
        self.set_image(decrypting, path)

    def set_image(self, decrypting, path):
        widgets = self.dec if decrypting else self.enc
        try:
            with Image.open(path) as original:
                if original.width * original.height > MAX_PIXELS or max(original.size) > MAX_SIDE:
                    raise PasscodeError('图片最多支持8,000万像素，单边不超过20,000。')
                image = ImageOps.exif_transpose(original)
                size = image.size
                if not decrypting:
                    strength = 'strong' if widgets['strength'].get() == '增强抗裁剪' else 'balanced'
                    plan_layout(*size, strength)
                image.thumbnail((min(410, max(240, widgets['preview'].winfo_width()-16)),
                                 max(80, min(260, widgets['preview'].winfo_height()-12))))
                if 'A' in image.getbands():
                    base = Image.new('RGBA', image.size, 'white')
                    image = Image.alpha_composite(base, image.convert('RGBA'))
                photo = ImageTk.PhotoImage(image.convert('RGB'), master=self)
            self.preview_images[decrypting] = photo
            widgets['size'] = size
            widgets['preview'].configure(image=photo, text='', width=0, height=0)
            widgets['path'].set(str(path))
            if decrypting:
                self._clear_result()
            self._update_image_info(decrypting)
            # Capacity/help text can resize the preview pane; fit after layout settles.
            self.update_idletasks()
            image.thumbnail((max(1, widgets['preview'].winfo_width()-12),
                             max(1, widgets['preview'].winfo_height()-12)))
            photo = ImageTk.PhotoImage(image.convert('RGB'), master=self)
            self.preview_images[decrypting] = photo
            widgets['preview'].configure(image=photo)
        except Exception as error:
            self._error(error)

    def _update_image_info(self, decrypting):
        widgets = self.dec if decrypting else self.enc
        if not widgets['size']:
            return
        w, h = widgets['size']
        if decrypting:
            widgets['info'].configure(text=f'{w:,} × {h:,} 像素\n自动识别裁剪位置和90°旋转。', fg=MUTED)
            return
        try:
            strength = 'strong' if widgets['strength'].get() == '增强抗裁剪' else 'balanced'
            if widgets['mode'].get() == 'image':
                limit = jpeg_capacity(w, h, strength)
                widgets['info'].configure(text=f'{w:,} × {h:,} 像素\n图片正文可用约{limit/1024:.1f} KiB\n将按空间自动压缩JPG。\n较大的载体有助于保留画质。', fg=MUTED)
                return
            plan = plan_layout(w, h, strength)
            widgets['info'].configure(text=f'{w:,} × {h:,} 像素\n最低总像素：{MIN_PIXELS[strength]:,}\n数据块：{plan.n}块，恢复至少{plan.k}块\n拟写入通道比例：{plan.selected_fraction:.1%}\n边缘留白：{plan.margin_fraction:.1%}', fg=MUTED)
        except PasscodeError as error:
            widgets['info'].configure(text=str(error), fg=RED)

    def refresh_keys(self):
        records = [] if self.vault.locked else self.vault.list_keys()
        self.tree.delete(*self.tree.get_children())
        self.key_choices = {}
        default_display = ''
        for item in records:
            display = f"{item['name']}  ·  {item['fingerprint'][:8]}"
            self.key_choices[display] = item['id']
            self.tree.insert('', 'end', iid=item['id'], values=(item['name'], item['fingerprint'], item['created'][:10], '✓' if item['default'] else ''))
            if item['default']:
                default_display = display
        for widgets in (self.enc, self.dec):
            combo = widgets['combo']
            current = combo.get()
            combo.configure(values=list(self.key_choices))
            combo.set(current if current in self.key_choices else default_display)
        self.vault_status.configure(text='密钥库已锁定' if self.vault.locked else f'已解锁 · {len(records)}把密钥')
        self.vault_button.configure(text='解锁密钥库' if self.vault.exists else '建立密钥库')
        if not self.vault.locked:
            self.vault_button.configure(text='锁定密钥库')

    def _available(self):
        if self.busy:
            raise PasscodeError('当前操作尚未结束，请等待或取消。')
        if self.vault.locked:
            raise PasscodeError('请先解锁或建立密钥库。')

    def toggle_vault(self):
        if self.busy:
            self.status.configure(text='请先等待或取消当前操作。')
            return
        if self.vault.locked:
            self.open_vault()
        else:
            self.vault.lock()
            self._clear_result()
            self.refresh_keys()
            self.status.configure(text='密钥库已锁定。')

    def open_vault(self):
        if self.busy:
            return
        if self.vault.exists:
            try:
                if self.vault.mode == 'password':
                    dialog = FormDialog(self, '解锁密钥库', [('主密码', '', True)], on_submit=lambda v: self.vault.unlock(v[0]))
                    self.wait_window(dialog)
                    self.refresh_keys()
                else:
                    self._work(self.vault.unlock, lambda r: (self.refresh_keys(), self.status.configure(text='密钥库已解锁。')))
            except Exception as error:
                self._error(error)
            return
        setup = tk.Toplevel(self)
        setup.title('建立密钥库')
        setup.transient(self)
        setup.configure(bg=CARD)
        setup.resizable(False, False)
        frame = tk.Frame(setup, bg=CARD, padx=24, pady=22)
        frame.pack()
        self.label(frame, '选择本地密钥保护方式', 16, bold=True).pack(anchor='w')
        self.label(frame, '所有密钥和名称均加密保存，不会退回明文文件。', 10, MUTED).pack(anchor='w', pady=(8, 16))
        mode = tk.StringVar(value='system')
        for value, text in [('system', '系统保护：Windows账户 / Linux桌面密钥环'), ('password', '主密码保护：适合无桌面密钥环的Linux环境')]:
            tk.Radiobutton(frame, text=text, variable=mode, value=value, bg=CARD, fg=INK, activebackground=CARD).pack(anchor='w', pady=5)
        self.label(frame, '主密码（选择主密码保护时填写，至少12字符）', 10).pack(anchor='w', pady=(12, 4))
        password = ttk.Entry(frame, show='●', width=52)
        password.pack(fill='x', ipady=4)
        self.label(frame, '再次输入主密码', 10).pack(anchor='w', pady=(8, 4))
        confirm = ttk.Entry(frame, show='●', width=52)
        confirm.pack(fill='x', ipady=4)
        error_label = self.label(frame, '', 10, RED, wraplength=460, justify='left')
        error_label.pack(fill='x', pady=10)
        def create():
            if mode.get() == 'password' and password.get() != confirm.get():
                error_label.configure(text='两次输入的主密码不一致。')
                return
            selected, secret = mode.get(), password.get()
            setup.destroy()
            self._work(lambda: self.vault.create(selected, secret), lambda r: (self.refresh_keys(), self.status.configure(text='密钥库已建立。请生成或导入通信密钥。')))
        ttk.Button(frame, text='建立密钥库', style='Accent.TButton', command=create).pack(fill='x')
        setup.grab_set()

    def _selected_key(self):
        self._available()
        selected = self.tree.selection()
        if not selected:
            raise PasscodeError('请先在列表中选择一把密钥。')
        return selected[0]

    def new_key(self):
        try:
            self._available()
            dialog = FormDialog(self, '生成新密钥', [('密钥名称', '新密钥 ' + datetime.now().strftime('%m-%d %H:%M'), False)],
                                on_submit=lambda v: self.vault.add(v[0]), submit_text='生成并保存')
            self.wait_window(dialog)
            self.refresh_keys()
        except Exception as error:
            self._error(error)

    def import_key(self):
        try:
            self._available()
            dialog = FormDialog(self, '导入通信密钥', [('密钥名称', '', False), ('128位半角数字密钥', '', True)],
                                note='请输入完整的128位半角数字密钥，前导零必须保留。',
                                on_submit=lambda v: self.vault.add(v[0], v[1]), submit_text='导入并保存')
            self.wait_window(dialog)
            self.refresh_keys()
        except Exception as error:
            self._error(error)

    def rename_key(self):
        try:
            identity = self._selected_key()
            old = self.tree.item(identity, 'values')[0]
            dialog = FormDialog(self, '重命名密钥', [('名称', old, False)], on_submit=lambda v: self.vault.rename(identity, v[0]))
            self.wait_window(dialog)
            self.refresh_keys()
        except Exception as error:
            self._error(error)

    def default_key(self):
        try:
            self.vault.set_default(self._selected_key())
            self.enc['combo'].set(''); self.dec['combo'].set('')
            self.refresh_keys()
        except Exception as error:
            self._error(error)

    def show_key(self):
        try:
            identity = self._selected_key()
            secret = self.vault.get(identity)
            dialog = tk.Toplevel(self)
            dialog.title('当前密钥')
            dialog.transient(self)
            dialog.configure(bg=CARD)
            self.label(dialog, '仅向需要通信的人传递此密钥。', 11, MUTED).pack(padx=24, pady=(18, 8))
            text = tk.Text(dialog, width=38, height=5, wrap='char', relief='flat', bg='#f1f5f4', font=('TkFixedFont', 13), padx=12, pady=12)
            text.insert('1.0', secret)
            text.configure(state='disabled')
            text.pack(padx=24, pady=8)
            def copy():
                self.clipboard_clear(); self.clipboard_append(secret); self.update()
                self.status.configure(text='密钥已复制，请妥善传递并及时覆盖剪贴板。')
            ttk.Button(dialog, text='复制密钥', command=copy).pack(pady=(4, 18))
            dialog.grab_set()
        except Exception as error:
            self._error(error)

    def delete_key(self):
        try:
            identity = self._selected_key()
            name = self.tree.item(identity, 'values')[0]
            if messagebox.askyesno('删除密钥', f'确定删除“{name}”？\n没有备份将无法读取使用此密钥的旧消息。', parent=self):
                self.vault.delete(identity)
                self.refresh_keys()
        except Exception as error:
            self._error(error)

    def export_backup(self):
        try:
            self._available()
            def export(values):
                if values[0] != values[1]:
                    raise PasscodeError('两次输入的备份密码不一致。')
                raw = self.vault.export_backup(values[0])
                path = filedialog.asksaveasfilename(parent=self, defaultextension='.bipkeys', initialfile='binary_image_passcode_keys.bipkeys', filetypes=[('加密密钥备份', '*.bipkeys')])
                if path:
                    atomic_write(path, raw)
                return path
            dialog = FormDialog(self, '导出加密备份', [('备份密码（至少12字符）', '', True), ('再次输入备份密码', '', True)],
                                note='此备份可跨Windows和Linux导入。请另外保存密码，遗失后无法恢复。', on_submit=export, submit_text='加密并导出')
            self.wait_window(dialog)
            if dialog.result:
                self.status.configure(text='加密备份已保存。')
        except Exception as error:
            self._error(error)

    def import_backup(self):
        try:
            self._available()
            path = filedialog.askopenfilename(parent=self, filetypes=[('加密密钥备份', '*.bipkeys'), ('所有文件', '*.*')])
            if not path:
                return
            if Path(path).stat().st_size > 2_000_000:
                raise PasscodeError('备份文件过大。')
            raw = Path(path).read_bytes()
            dialog = FormDialog(self, '导入加密备份', [('备份密码', '', True)], on_submit=lambda v: self.vault.import_backup(raw, v[0]),
                                note='相同密钥会跳过；同名的不同密钥会自动重命名，不覆盖现有记录。', submit_text='解密并导入')
            self.wait_window(dialog)
            if dialog.result is not None:
                self.refresh_keys()
                self.status.configure(text=f'已导入{dialog.result}把新密钥。')
        except Exception as error:
            self._error(error)

    def run_crypto(self, decrypting):
        try:
            self._available()
            widgets = self.dec if decrypting else self.enc
            path = widgets['path'].get()
            if not path:
                raise PasscodeError('请先选择图片。')
            identity = self.key_choices.get(widgets['combo'].get())
            key = self.vault.get(identity)
            if decrypting:
                self._clear_result()
                widgets['text'].configure(state='normal'); widgets['text'].delete('1.0', 'end'); widgets['text'].configure(state='disabled')
                widgets['count'].configure(text='正在验证…')
                self._work(lambda: decode_file(path, key, self.cancel, self._progress), self._decoded)
            else:
                image_mode = widgets['mode'].get() == 'image'
                text = widgets['text'].get('1.0', 'end-1c')
                if image_mode:
                    if not widgets['secret_path'].get():
                        raise PasscodeError('请先选择要加密的图片。')
                else:
                    logical_units(text)
                strength = 'strong' if widgets['strength'].get() == '增强抗裁剪' else 'balanced'
                if widgets['size']:
                    plan_layout(*widgets['size'], strength)
                target = filedialog.asksaveasfilename(parent=self, defaultextension='.png', initialfile=Path(path).stem+'_encoded.png',
                                                     filetypes=[('PNG图片', '*.png')])
                if target:
                    if image_mode:
                        secret = widgets['secret_path'].get()
                        self._work(lambda: encode_image_file(path, target, secret, key, strength, overwrite=True, cancel=self.cancel, progress=self._progress), self._encoded_image)
                    else:
                        self._work(lambda: encode_file(path, target, text, key, strength, overwrite=True, cancel=self.cancel, progress=self._progress), self._encoded)
        except Exception as error:
            self._error(error)

    def _switch_payload(self):
        if self.busy:
            return
        image_mode = self.enc['mode'].get() == 'image'
        self.enc['wrapper'].pack_forget()
        self.enc['secret_frame'].pack_forget()
        (self.enc['secret_frame'] if image_mode else self.enc['wrapper']).pack(fill='both', expand=True)
        self._update_count()
        self._update_image_info(False)

    def choose_secret_image(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, title='选择要加密的图片',
                                          filetypes=[('图片文件', '*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.gif *.avif'), ('所有文件', '*.*')])
        if path:
            self.enc['secret_path'].set(path)
            self.enc['count'].configure(text='已选择图片。将按载体空间压缩为JPG，不覆盖原图。', fg=MUTED)

    def _encoded_image(self, result):
        image = result.image
        self.enc['count'].configure(text=f'图片正文：{image.width}×{image.height} · {len(image.data)/1024:.1f} KiB · JPG', fg=ACCENT)
        self.enc['info'].configure(text=f'已保存：{Path(result.output_path).name}\n原图：{image.original_size[0]}×{image.original_size[1]}\n压缩后：{image.width}×{image.height}\nJPG大小：{len(image.data)/1024:.1f} KiB\n压缩质量参数：{image.quality}\n恢复门限：{result.layout.k}/{result.layout.n}块\n请以文件或原图发送载体PNG。', fg=ACCENT)
        self.status.configure(text='图片消息已加密保存为PNG；接收者解密后可保存JPG。')

    def _decoded_image(self, result):
        w, h = result.image_size
        self.dec['text'].configure(state='normal')
        self.dec['text'].delete('1.0', 'end')
        self.dec['text'].insert('1.0', f'图片消息已通过认证。\n\n尺寸：{w} × {h}\n格式：JPG\n大小：{len(result.image_bytes)/1024:.1f} KiB\n\n请点击“保存图片为JPG”选择保存位置。')
        self.dec['text'].configure(state='disabled')
        self.dec['count'].configure(text='生成时间（北京时间）：'+result.generated_at.strftime('%Y-%m-%d %H:%M:%S'), fg=ACCENT)
        self.dec['info'].configure(text=f'图片认证通过\n可读块：{result.recovered_shards}/{result.total_shards}\n恢复门限：{result.required_shards}块\n尺寸：{w}×{h}\n输出：JPG', fg=ACCENT)
        with Image.open(BytesIO(result.image_bytes)) as image:
            self.update_idletasks()
            image.thumbnail((max(1, self.dec['preview'].winfo_width()-12), max(1, self.dec['preview'].winfo_height()-12)))
            photo = ImageTk.PhotoImage(image, master=self)
        self.preview_images[True] = photo
        self.dec['preview'].configure(image=photo, text='', width=0, height=0)
        self.status.configure(text='图片已恢复，可预览并保存JPG。')

    def save_decoded_image(self):
        if self.decoded_image is None or self.busy:
            return
        target = filedialog.asksaveasfilename(parent=self, title='保存解密后的图片',
                                             defaultextension='.jpg', initialfile='decrypted_image.jpg',
                                             filetypes=[('JPG图片', '*.jpg *.jpeg')])
        if target:
            try:
                save_image_result(self.decoded_image, target, overwrite=True,
                                  protected_paths=(self.dec['path'].get(), self.enc['path'].get(), self.enc['secret_path'].get()))
                self.status.configure(text='解密图片已保存为JPG。')
            except Exception as error:
                self._error(error)

    def _encoded(self, result):
        self.status.configure(text=f'已保存PNG：{result.layout.n}块，恢复至少需要{result.layout.k}块。')
        self.enc['info'].configure(text=f'已保存：{Path(result.output_path).name}\n完整块门限：{result.layout.k}/{result.layout.n}\n正文编码：{result.used_units:,}单元\n边缘留白：{result.layout.margin_fraction:.1%}\n请按原文件发送PNG。', fg=ACCENT)

    def _decoded(self, result):
        self.decoded_image = result if result.image_bytes else None
        self.dec['copy_button'].configure(state='disabled' if result.image_bytes else 'normal')
        self.dec['save_text_button'].configure(state='disabled' if result.image_bytes else 'normal')
        self.dec['save_image_button'].configure(state='normal' if result.image_bytes else 'disabled')
        if result.image_bytes:
            self._decoded_image(result)
            return
        self.dec['text'].configure(state='normal')
        self.dec['text'].delete('1.0', 'end'); self.dec['text'].insert('1.0', result.text)
        self.dec['text'].configure(state='disabled')
        stamp = (result.generated_at.strftime('%Y-%m-%d %H:%M')+'（V2.0分钟精度）' if result.message_format == '2.0'
                 else result.generated_at.strftime('%Y-%m-%d %H:%M:%S'))
        self.dec['count'].configure(text='生成时间（北京时间）：'+stamp, fg=ACCENT)
        self.dec['info'].configure(text=f'文字消息认证通过\n可读数据块：{result.recovered_shards}/{result.total_shards}\n恢复门限：{result.required_shards}块\n块内修正：{result.corrected_bytes}字节\n识别旋转：{result.rotation}°', fg=ACCENT)
        self.status.configure(text='已恢复完整正文，消息认证通过。')

    def _clear_result(self):
        if self.decoded_image is not None:
            self.dec['preview'].configure(image='', text='选择消息图片以恢复内容')
            self.preview_images.pop(True, None)
            self.dec['info'].configure(text='')
        self.decoded_image = None
        self.dec['save_image_button'].configure(state='disabled')
        self.dec['copy_button'].configure(state='normal')
        self.dec['save_text_button'].configure(state='normal')
        self.dec['text'].configure(state='normal')
        self.dec['text'].delete('1.0', 'end')
        self.dec['text'].configure(state='disabled')
        self.dec['count'].configure(text='等待解密。', fg=MUTED)

    def copy_result(self):
        if self.decoded_image is not None:
            return
        value = self.dec['text'].get('1.0', 'end-1c')
        if value:
            self.clipboard_clear(); self.clipboard_append(value); self.update()
            self.status.configure(text='正文已复制。')

    def save_result(self):
        if self.decoded_image is not None:
            return
        value = self.dec['text'].get('1.0', 'end-1c')
        if not value:
            return
        path = filedialog.asksaveasfilename(parent=self, initialfile='binary_image_passcode_message.txt', defaultextension='.txt')
        if path:
            try:
                atomic_write(path, value.encode('utf-8'))
                self.status.configure(text='正文已保存。')
            except Exception as error:
                self._error(error)

    def _progress(self, fraction, message):
        self.events.put(('progress', fraction, message))

    def _work(self, function, callback):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.progress['value'] = 0
        self.status.configure(text='正在处理…')
        self.cancel_button.configure(state='normal')
        self.enc['action'].configure(state='disabled'); self.dec['action'].configure(state='disabled')
        self.enc['combo'].configure(state='disabled'); self.dec['combo'].configure(state='disabled')
        self.enc['text'].configure(state='disabled')
        self.enc['strength_combo'].configure(state='disabled')
        for control in self.enc['mode_controls']:
            control.configure(state='disabled')
        def worker():
            try:
                self.events.put(('done', callback, function()))
            except Exception as error:
                self.events.put(('error', error))
        self.executor.submit(worker)

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'progress':
                    self.progress['value'] = event[1]*100
                    self.status.configure(text=event[2])
                else:
                    self.busy = False
                    self.cancel_button.configure(state='disabled')
                    self.enc['action'].configure(state='normal'); self.dec['action'].configure(state='normal')
                    self.enc['combo'].configure(state='readonly'); self.dec['combo'].configure(state='readonly')
                    self.enc['text'].configure(state='normal')
                    self.enc['strength_combo'].configure(state='readonly')
                    for control in self.enc['mode_controls']:
                        control.configure(state='normal')
                    if event[0] == 'done':
                        self.progress['value'] = 100
                        event[1](event[2])
                    else:
                        self.progress['value'] = 0
                        self._error(event[1])
        except queue.Empty:
            pass
        self.after(60, self._poll)

    def _error(self, error):
        message = str(error) if isinstance(error, PasscodeError) else '操作未完成，请检查文件、权限和运行依赖后重试。'
        self.status.configure(text=message)
        if not isinstance(error, Cancelled):
            messagebox.showerror('操作未完成', message, parent=self)

    def close(self):
        if self.busy and not messagebox.askyesno('退出程序', '操作尚未完成，确定取消并退出？', parent=self):
            return
        self.cancel.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.vault.lock()
        self.destroy()

def launch():
    App().mainloop()
