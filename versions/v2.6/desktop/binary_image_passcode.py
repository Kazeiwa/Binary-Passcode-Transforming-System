#!/usr/bin/env python3
"""GUI entry point and optional CLI. Keys are never accepted as command-line values."""
import argparse
from getpass import getpass
from pathlib import Path
import sys

def main(argv=None):
    parser = argparse.ArgumentParser(prog='binary_image_passcode', description='二进制密码图片终端')
    parser.add_argument('--version', action='store_true')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('gui', help='打开图形界面')
    capacity = sub.add_parser('capacity', help='检查载体容量')
    capacity.add_argument('image')
    capacity.add_argument('--strength', choices=['balanced', 'strong'], default='balanced')
    for name in ['encode', 'decode', 'encode-image']:
        command = sub.add_parser(name)
        command.add_argument('image')
        command.add_argument('--key', help='密钥库中的名称或ID，省略时使用默认密钥')
        command.add_argument('--vault', type=Path)
        command.add_argument('--output', type=Path, required=name in ('encode', 'encode-image'))
        command.add_argument('--force', action='store_true', help='允许覆盖已有输出文件')
        if name in ('encode', 'encode-image'):
            if name == 'encode':
                command.add_argument('--text-file', required=True, type=Path, help='UTF-8正文文件')
            else:
                command.add_argument('--image-file', required=True, type=Path, help='要隐藏的静态图片，自动适配至1080P')
                command.add_argument('--lossless',action='store_true',help='使用PNG无损图片正文，需要完整载体文件')
            command.add_argument('--strength', choices=['balanced', 'strong'], default='balanced')
    args = parser.parse_args(argv)
    from bip import __version__
    if args.version:
        print('binary_image_passcode ' + __version__)
        return 0
    try:
        if args.command in (None, 'gui'):
            from bip.gui import launch
            launch()
            return 0
        from bip.errors import PasscodeError
        from bip.image_transport import load_rgb, plan_layout, encode_file, decode_file
        from bip.vault import KeyVault, atomic_write
        if args.command == 'capacity':
            rgb = load_rgb(args.image)
            plan = plan_layout(rgb.shape[1], rgb.shape[0], args.strength)
            print(f'{plan.width}×{plan.height}: {plan.n}块，至少保留{plan.k}块可恢复；写入通道约{plan.selected_fraction:.1%}，边缘留白{plan.margin_fraction:.1%}。')
            return 0
        vault = KeyVault(args.vault)
        if not vault.exists:
            raise PasscodeError('尚未建立密钥库，请先运行图形界面。')
        vault.unlock(getpass('主密码：') if vault.mode == 'password' else None)
        records = vault.list_keys()
        identity = vault.default_id
        if args.key:
            identity = next((r['id'] for r in records if r['id'] == args.key or r['name'] == args.key), None)
        key = vault.get(identity)
        try:
            if args.command == 'encode-image':
                from bip.image_payload import encode_image_file
                result = encode_image_file(args.image, args.output, args.image_file, key, args.strength, overwrite=args.force,lossless=args.lossless)
                print(f'已保存PNG：{result.output_path}；图片正文{result.image.width}×{result.image.height}，{len(result.image.data):,}字节。')
            elif args.command == 'encode':
                if args.text_file.stat().st_size > 200_000:
                    raise PasscodeError('正文文件过大。')
                with args.text_file.open('r', encoding='utf-8-sig', newline='') as file:
                    text = file.read()
                result = encode_file(args.image, args.output, text, key, args.strength, overwrite=args.force)
                print(f'已保存：{result.output_path}；恢复门限{result.layout.k}/{result.layout.n}块。')
            else:
                result = decode_file(args.image, key)
                if result.image_bytes:
                    from bip.image_payload import save_image_result
                    if not args.output:
                        raise PasscodeError('这是图片消息，请用--output 指定对应的.jpg或.png输出文件。')
                    save_image_result(result, args.output, overwrite=args.force, protected_paths=(args.image,))
                elif args.output:
                    if args.output.exists() and not args.force:
                        raise PasscodeError('输出文件已存在，使用--force才会覆盖。')
                    if args.output.resolve() == Path(args.image).resolve():
                        raise PasscodeError('正文输出不能覆盖输入图片。')
                    atomic_write(args.output, result.text.encode('utf-8'))
                else:
                    sys.stdout.write(result.text)
                print('\n生成时间（北京时间）：' + result.generated_at.strftime('%Y-%m-%d %H:%M:%S'), file=sys.stderr)
            return 0
        finally:
            vault.lock()
    except ModuleNotFoundError as error:
        message = '运行依赖未安装。请运行启动脚本，或执行：python -m pip install -r requirements.txt'
        print(message, file=sys.stderr)
        if args.command in (None, 'gui'):
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk(); root.withdraw()
                messagebox.showerror('binary_image_passcode', message)
                root.destroy()
            except ImportError:
                pass
        return 2
    except Exception as error:
        from bip.errors import PasscodeError
        print('错误：' + (str(error) if isinstance(error, PasscodeError) else '操作未完成，请检查文件及运行环境。'), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
