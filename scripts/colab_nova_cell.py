# Run this cell after setup, or in an already running notebook after replacing the backend ZIP.
import os
from pathlib import Path
import subprocess
import sys
from IPython.display import Image, display
from zipfile import ZipFile

root = Path('/content/spherex-colab')
bundle = Path('/content/spherex-colab-backend.zip')
with ZipFile(bundle) as archive:
    name = 'scripts/preview_v572_vel.py'
    if name not in archive.namelist():
        raise RuntimeError('Replace /content/spherex-colab-backend.zip with the updated ZIP.')
    archive.extract(name, root)
output = root / 'v572-vel-timeline.png'
subprocess.run([
    sys.executable, '-m', 'uv', 'run', '--no-project', '--python', '3.13',
    '--with-requirements', str(root / 'backend/requirements.txt'),
    'python', '-m', 'scripts.preview_v572_vel', str(output),
], cwd=root, env={**os.environ, 'SPHEREX_DATA_DIR': str(root / 'data')}, check=True)
display(Image(filename=str(output), width=1000))
