"""Optional local build; requires PyInstaller. Source also runs directly on Linux."""
from pathlib import Path
import argparse
import os
import subprocess
import sys

root=Path(__file__).resolve().parent
if os.name != 'nt':
    raise SystemExit('This build script targets Windows. Run the Python source directly on Linux.')
build=root/'.build'
parser=argparse.ArgumentParser()
parser.add_argument('--dist-dir',type=Path,default=root)
args=parser.parse_args()
command=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed',
         '--name','binary_image_passcode','--paths',str(root),
         '--add-data',str(root/'assets')+';assets',
         '--icon',str(root/'assets/binary_image_passcode.ico'),
         '--version-file',str(root/'assets/version_info.txt'),
         '--distpath',str(args.dist_dir.resolve()),'--workpath',str(build/'work'),'--specpath',str(build),
         str(root/'binary_image_passcode.py')]
subprocess.run(command,check=True,cwd=root)
