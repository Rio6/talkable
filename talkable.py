#!/usr/bin/env python
import os, sys, math
import ffmpeg, audioop
from operator import itemgetter

BLEN = 8 * 1024
PIX_FMT = 'rgb24'
IMG_EXTS = ['png', 'jpg', 'jpeg', 'gif']

def read_image(path):
    width, height = itemgetter('width', 'height')(ffmpeg.probe(path).get('streams')[0])
    proc = (ffmpeg
            .input(path)
        .output('pipe:', format='rawvideo', pix_fmt=PIX_FMT, **{'frames:v': 1})
        .run_async(pipe_stdout=True, quiet=True))
    data = proc.stdout.read()
    proc.wait()
    return (width, height, data)

verbose = False
images = []
width, height = (-1, -1)
in_file, out_file = (None, None)
in_opt, out_opt = ({}, {})
scale = 0

sys.argv.pop(0)
img_dir = sys.argv.pop(0)
while len(sys.argv) > 0:
    arg = sys.argv.pop(0)
    if arg == '-v':
        verbose = True
    elif arg == '-scale':
        scale = int(sys.argv.pop(0))
    elif len(arg) > 1 and arg.startswith('-'):
        if in_file == None:
            in_opt[arg.strip('-')] = sys.argv.pop(0)
        else:
            out_opt[arg.strip('-')] = sys.argv.pop(0)
    else:
        if in_file == None:
            in_file = arg
        else:
            out_file = arg

for path in sorted(path for path in os.listdir(img_dir) if path.split('.')[-1].lower() in IMG_EXTS):
    _width, _height, data = read_image(img_dir + '/' + path)
    if width < 0 or height < 0:
        width = _width
        height = _height
    elif width != _width or height != _height:
        print('inconsistent image size', file=sys.stderr)
        exit(1)
    images.append(data)

proc_in = (ffmpeg
    .input(in_file, re=None, **in_opt)
    .output('pipe:', format='s16le')
    .global_args('-nostdin')
    .run_async(pipe_stdout=True, pipe_stderr=not verbose))

proc_out = (ffmpeg
    .input('pipe:', re=None, format='rawvideo', pix_fmt=PIX_FMT, video_size=(width, height))
    .output(out_file, **out_opt)
    .overwrite_output()
    .run_async(pipe_stdin=True, pipe_stderr=not verbose))

try:
    while True:
        buff = proc_in.stdout.read(BLEN)
        if len(buff) == 0: break
        volume = min(audioop.rms(buff, 2) * scale, 8191)
        proc_out.stdin.write(images[math.floor(volume / 8192 * len(images))])

except (KeyboardInterrupt, BrokenPipeError):
    pass

print('exiting', file=sys.stderr)

proc_in.stdout.close()
proc_in.terminate()

proc_out.stdin.close()
proc_out.terminate()

proc_in.wait()
proc_out.wait()
