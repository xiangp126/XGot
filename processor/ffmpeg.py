#!/usr/bin/env python3

import logging
import os
import subprocess
import sys

try:
    from subprocess import DEVNULL
except ImportError:
    # Python 3.2 or below
    import os
    import atexit
    DEVNULL = os.open(os.devnull, os.O_RDWR)
    atexit.register(lambda fd: os.close(fd), DEVNULL)

def get_usable_ffmpeg(cmd):
    try:
        p = subprocess.Popen([cmd, '-version'], stdin=DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        vers = str(out, 'utf-8').split('\n')[0].split()
        assert (vers[0] == 'ffmpeg' and vers[2][0] > '0') or (vers[0] == 'avconv')
        try:
            v = vers[2][1:] if vers[2][0] == 'n' else vers[2]
            version = [int(i) for i in v.split('.')]
        except:
            version = [1, 0]
        return cmd, 'ffprobe', version
    except:
        return None

FFMPEG, FFPROBE, FFMPEG_VERSION = get_usable_ffmpeg('ffmpeg') or get_usable_ffmpeg('avconv') or (None, None, None)

if logging.getLogger().isEnabledFor(logging.DEBUG):
    LOGLEVEL = ['-loglevel', 'info']
    STDIN = None
else:
    LOGLEVEL = ['-loglevel', 'quiet']
    STDIN = DEVNULL

def has_ffmpeg_installed():
    return FFMPEG is not None

def ffmpeg_concat_ts_to_mp4(files, output='output.mp4'):
    print('\nStart to Merge Video Parts ...', flush = True)
    # params = [FFMPEG] + LOGLEVEL + ['-isync', '-y', '-i']
    params = [FFMPEG] + ['-y', '-i']
    params.append('concat:')
    for file in files:
        if os.path.isfile(file):
            params[-1] += file + '|'
    params += ['-c', 'copy', output]

    try:
        if subprocess.call(params, stdin=STDIN) == 0:
            return True
        else:
            return False
    except:
        return False
