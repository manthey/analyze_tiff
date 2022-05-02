import argparse
import base64
import io
import json
import math
import os
import subprocess
import sys
import tempfile

import large_image
import large_image_source_tiff
import numpy
import PIL.Image
import PIL.ImageColor
import PIL.ImageDraw
import tifftools
import yaml


def get_thumbnail(ifd, factor):
    maxwh = max(
        ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0],
        ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0])
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = os.path.join(tmpdir, 'oneifd.tiff')
        tifftools.write_tiff(ifd, dest, allowExisting=True)
        try:
            ts = large_image_source_tiff.open(dest)
            return ts.getThumbnail(width=int(maxwh * factor), height=int(maxwh * factor))[0]
        except Exception:
            pass
        try:
            ts = large_image.open(dest)
            return ts.getThumbnail(width=int(maxwh * factor), height=int(maxwh * factor))[0]
        except Exception:
            pass
        img = PIL.Image.open(dest)
        img.thumbnail((int(maxwh * factor), int(maxwh * factor)))
        output = io.BytesIO()
        img.save(output, 'PNG')
        img = output.getvalue()
        return img


def add_structure_grid(img, w, h, horz, vert, factor, rescale):
    if horz and horz < h and horz >= 2:
        lastsy = None
        for y in range(horz - 1, h, horz):
            sy = int(round(y * factor * rescale))
            if sy != lastsy and sy < img.shape[0]:
                img[sy, :] = numpy.bitwise_xor(img[sy, :], [128, 128, 128])
            lastsy = sy
    if vert and vert < w and vert >= 2:
        lastsx = None
        for x in range(vert - 1, w, vert):
            sx = int(round(x * factor * rescale))
            if sx != lastsx and sx < img.shape[1]:
                img[:, sx] = numpy.bitwise_xor(img[:, sx], [128, 128, 128])
            lastsx = sx


def add_structure_order(img, w, h, horz, vert, factor, rescale, order):
    sorder = sorted([(val, idx) for idx, val in enumerate(order)])
    skipped = 0
    order = [0] * len(order)
    for idx, (val, oidx) in enumerate(sorder):
        if not val and skipped == idx:
            skipped += 1
        order[oidx] = (val, idx)
    idx = 0
    for y in range(0, h, horz or h):
        for x in range(0, w, vert or w):
            val = int(order[idx][1] / ((len(order) - skipped) or 1) * 256)
            sx1 = min(int(round(x * factor * rescale)), img.shape[1] - 1)
            sx2 = min(int(round((x + (vert or w)) * factor * rescale)), img.shape[1] - 1)
            sy1 = min(int(round(y * factor * rescale)), img.shape[0] - 1)
            sy2 = min(int(round((y + (horz or h)) * factor * rescale)), img.shape[0] - 1)
            if sx2 > sx1 and sy2 > sy1:
                if order[idx][0]:
                    img[sy1:sy2, sx1:sx2] = [val, val, val]
                else:
                    img[sy1:sy2, sx1:sx2] = [255, 255, 0]
            idx += 1


def add_structure(img, ifd, factor, order=False):
    w = ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0]
    h = ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0]
    vert = horz = None
    if tifftools.Tag.TileWidth.value in ifd['tags']:
        vert = ifd['tags'][tifftools.Tag.TileWidth.value]['data'][0]
        horz = ifd['tags'][tifftools.Tag.TileLength.value]['data'][0]
        orderset = ifd['tags'][tifftools.Tag.TileOffsets.value]['data']
    elif tifftools.Tag.NDPI_MCU_STARTS.value in ifd['tags']:
        count = len(ifd['tags'][tifftools.Tag.NDPI_MCU_STARTS.value]['data'])
        horz = 8 * (ifd['tags'][tifftools.Tag.YCbCrSubsampling.value]['data'][1]
                    if tifftools.Tag.YCbCrSubsampling.value in ifd['tags'] else 1)
        vert = w * h // horz // count
        orderset = ifd['tags'][tifftools.Tag.NDPI_MCU_STARTS.value]['data']
    elif tifftools.Tag.RowsPerStrip.value in ifd['tags']:
        horz = ifd['tags'][tifftools.Tag.RowsPerStrip.value]['data'][0]
        orderset = ifd['tags'][tifftools.Tag.StripOffsets.value]['data']
    if not order and (not horz or horz >= h or horz < 2) and (not vert or vert >= w or vert < 2):
        return img
    # rescale makes lines thinner (1 / rescale in conceptual size) and
    # antialiased
    rescale = 2
    img = PIL.Image.open(io.BytesIO(img))
    if rescale != 1:
        origwh = img.width, img.height
        img = img.resize((img.width * rescale, img.height * rescale))
    img = numpy.asarray(img.convert('RGB'))

    if not order:
        add_structure_grid(img, w, h, horz, vert, factor, rescale)
    else:
        add_structure_order(img, w, h, horz, vert, factor, rescale, orderset)

    img = PIL.Image.fromarray(img, 'RGB')
    if rescale != 1:
        img = img.resize(origwh)
    output = io.BytesIO()
    img.save(output, 'PNG')
    img = output.getvalue()
    return img


def optimize_image(img, args):
    if img[:4] != b'\x89PNG':
        return img
    with tempfile.TemporaryDirectory() as tmpdir:
        file = os.path.join(tmpdir, 'img.png')
        open(file, 'wb').write(img)
        cmd = ['optipng', '-quiet', file]
        if args.verbose:
            sys.stdout.write('optipng command: %r\n' % cmd)
        try:
            subprocess.check_call(cmd)
        except Exception:
            return img
        img = open(file, 'rb').read()
    return img


def add_thumbnails(rawyaml, args):
    info = tifftools.read_tiff(args.source)
    # Get the range of dimensions of the images
    maxdim = 0
    minmaxdim = None
    for ifd in tifftools.commands._iterate_ifds(info['ifds'], subifds=True):
        maxwh = max(
            ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0],
            ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0])
        maxdim = max(maxdim, maxwh)
        if minmaxdim is None or maxwh < minmaxdim:
            minmaxdim = maxwh
    if minmaxdim == maxdim:
        minmaxdim /= 2
    minout = min(minmaxdim, args.minthumb)
    maxout = min(maxdim, args.maxthumb)
    ref = 0
    for ifd in tifftools.commands._iterate_ifds(info['ifds'], subifds=True):
        maxwh = max(
            ifd['tags'][tifftools.Tag.ImageWidth.value]['data'][0],
            ifd['tags'][tifftools.Tag.ImageLength.value]['data'][0])
        factor = (math.log(maxwh / maxdim) - math.log(minmaxdim / maxdim)) / (
            -math.log(minmaxdim / maxdim))
        factor = (math.exp(factor * -math.log(minout / maxout) + math.log(
            minout / maxout)) * maxout) / maxwh

        if args.verbose >= 2:
            sys.stderr.write(
                'Getting thumbnail from image with maximum dimension %d at scale %5.3f\n' % (
                    maxwh, factor))
        img = get_thumbnail(ifd, factor)

        if not img:
            imgtitle = 'Image'
            imgstr = 'Could not decode image'
        else:
            imglist = []
            if args.thumb:
                imglist.append(('Image', optimize_image(img, args)))
            if args.structure:
                try:
                    imglist.append(('Structure', optimize_image(
                        add_structure(img, ifd, factor), args)))
                except Exception:
                    pass
            if args.order:
                try:
                    imglist.append(('Order', optimize_image(
                        add_structure(img, ifd, factor, order=True), args)))
                except Exception:
                    raise
                    pass
            imgtitle = ' | '.join([entry[0] for entry in imglist])
            imgstr = ' '.join([
                '<img:data:image/png;base64,' + base64.encodebytes(
                    entry[1]).decode().replace('\n', '') + '>'
                for entry in imglist])
        # Change the yaml.  This is an ugly way to inject the results
        ref = rawyaml.index('\n', rawyaml.index('    ImageLength: ', ref)) + 1
        spaces = rawyaml.rindex('ImageLength: ', 0, ref - 1) - (
            rawyaml.rindex('\n', 0, ref - 1) + 1)
        rawyaml = (
            rawyaml[:ref] +
            ' ' * spaces + '"Image Thumbnail":\n' +
            ' ' * spaces + '  "%s": %s\n' % (imgtitle, json.dumps(imgstr)) +
            rawyaml[ref:])
    return rawyaml


def generate_uml(args):
    cmd = ['tifftools', 'dump', '--yaml'] + args.tifftools_args + [args.source]
    if args.verbose:
        sys.stdout.write('tifftools command: %r\n' % cmd)
    rawyaml = subprocess.check_output(cmd).decode()
    if args.thumb or args.structure or args.order:
        rawyaml = add_thumbnails(rawyaml, args)

    yamldata = yaml.safe_load(rawyaml)
    if len(yamldata) == 1:
        yamldata = yamldata[list(yamldata.keys())[0]]
    jsonuml = '@startjson\n%s\n@endjson\n' % (json.dumps(
        yamldata, indent=1 if args.uml else None))

    if args.uml:
        open(args.uml, 'w').write(jsonuml)

    cmd = ['plantuml', '-pipe'] + args.plantuml_args
    if args.verbose:
        sys.stdout.write('plantuml command: %r\n' % cmd)
    with subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as proc:
        result = proc.communicate(input=jsonuml.encode())[0]
    if args.dest and args.dest != '-':
        open(args.dest, 'wb').write(result)
    else:
        sys.stdout.write(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="""
Read tiff files and emit svg UML diagrams of their internal details.

Any unknown arguments are passed to either tifftools or plantuml.  If at least
one argument is specified, the default arguments are not used.  Unknown
arguments before "--" are sent to "tifftools dump --yaml".  Those after -- are
sent to plantuml.    The default arguments for tifftools dump are "--max 6
--max-text 40".  For plantuml, they are "-tsvg".
""")
    parser.add_argument(
        'source', help='Path to source image')
    parser.add_argument(
        '--out', '--dest', dest='dest',
        help='The destination file.  If not specified or "-", the results are sent to stdout.')
    parser.add_argument(
        '--uml', help='Output the intermediate uml file.')
    parser.add_argument(
        '--thumb', '--thumbnails', '--images', action='store_true',
        help='Add image thumbnails to the output.')
    parser.add_argument(
        '--minthumb', type=int, default=64,
        help='The minimum thumbnail size for the lowest resolution image layer.')
    parser.add_argument(
        '--maxthumb', type=int, default=512,
        help='The maximum thumbnail size for the highest resolution image layer.')
    parser.add_argument(
        '--structure', action='store_true',
        help='Draw the tile or strip structure on top of the thumbnail.')
    parser.add_argument(
        '--order', action='store_true',
        help='Draw the tile or strip order on top of the thumbnail.')
    parser.add_argument(
        '--verbose', '-v', action='count', default=0, help='Increase verbosity')

    args, unknown = parser.parse_known_args()
    args.tifftools_args = unknown[:unknown.index('--') if '--' in unknown else len(unknown)] or \
        ['--max', '6', '--max-text', '40']
    args.plantuml_args = unknown[unknown.index('--') + 1 if '--' in unknown else len(unknown):] or \
        ['-tsvg']
    if args.verbose >= 2:
        sys.stderr.write('args: %r\n' % args)
    generate_uml(args)
