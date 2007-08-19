#!/www/python/bin/python
"""
$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/bin/make_tab_edge_images.py $
$Id: make_tab_edge_images.py,v 1.1 2004/04/13 03:31:40 pierre Exp $

Supports generating tab-edge png files in any color.

Example:
make_tab_edge_images.py unselected 9 40 102 56 88 160
make_tab_edge_images.py selected 183 200 226 56 88 160

Note: tab.ptl currently uses gifs made from these by
using pngcrush, opening the tiny pngs in xv, changing to 8-bit mode,
and then saving (normal size) as gif files.
The biggest of the resulting gif files is 232 bytes.
"""

import sys
from PIL import Image
import cStringIO
_MASK = Image.open(cStringIO.StringIO('\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00)\x00\x00\x00)\x08\x06\x00\x00\x00\xa8`\x00\xf6\x00\x00\x00\x04gAMA\x00\x00\xb1\x8f\x0b\xfca\x05\x00\x00\x01\x0eIDATx\x9c\xcd\x98\xc9\x11\x830\x10\x04\xdb.\x7f\x1d\x82\xb3PF\xc4C,$B\x14\x84\xc0\x97\x07~\xd8\xf8\xc0\xe6\x90\x98\x95v\xaa\xf6\t\xd5\xcc\xee\xe8\x00|\xab\x01\xfa\xd2\x10K\xaa\x80\x01\x18\x9f\xe5J\x01\xe8x\xc3\xb9\x83\xac\xf9\x85s\x05\xf9\xcf=7\x90\x81\xef\xd9s\x07\xb9\x17\xb0\x18\xe4\xda\xfc\xb9\x80\x8c\x05\xcc\x0e\x19\xd3\xe2"\x90\xa9\x80\xe3)#\xe4\x00\\R\x1e<\x8bA\x96\xd4\x91\x08\x98K)A\xc9:\x93\xc9s\x98\x13rk\xbb+\x0eY\x89\x00M\xd3\x9d\x9c\xe6\xb9\xac\xd2\xdd L\xb3\x95\x932\x17\xc1\xc6\xc9\x1a\xf1\x9ah\xe1d\x0f\\\x95/T;Y!\x06\xb4P\x8bh\xd9\x99\x95L\xc1\x08P\ni\xe5\xa2\x0c\xd2\xd2E\xd9\x8e#O\xf4\xa7\x14\xe9\xaeq\x9eh\xd5Q\xcc\xb4\xdd\xa6m\x9et\xa4\xdd-\xce\xdb\xac\xb8\x12\x98.A\xb9\x01\xa3!K\x00FA\x96\x02\xdc\x9d\xee\x0e\xb8\xc5|\x91R[\xe9\x9e\xfe]\x17\x03\\S\xc0\xf6\xc0ph&\xbd\xc1\xbd \x03\x8fP\xa8.\xf2\xf2\xba\x03Y\xb3\x071\x1b\xb2\xb9\xaa\x00\x00\x00\x00IEND\xaeB`\x82'))

def get_tab_image(foreground, background, flip):
    fg_image = Image.new('RGB', _MASK.size, foreground)
    bg_image = Image.new('RGB', _MASK.size, background)
    image = Image.composite(fg_image, bg_image, _MASK)
    if flip:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    output = cStringIO.StringIO()
    image.save(output, "PNG")
    return output.getvalue()

def get_left_tab_image(foreground, background):
    return get_tab_image(foreground, background, False)

def get_right_tab_image(foreground, background):
    return get_tab_image(foreground, background, True)

if __name__ == '__main__':
    try:
        base = sys.argv[1]
        numbers = map(int, sys.argv[2:])
        foreground = tuple(numbers[:3])
        background = tuple(numbers[3:6])
    except:
        print """
Usage:
  make_tab_edge_images.py <basename> <fgred> <fggreen> <fgblue> <bgred> <bggreen> <bgblue>
  (writes to <basename>_left.png and <basename>_right.png)
"""
    open(base+'_left.png', 'wb').write(
        get_left_tab_image(foreground, background))
    open(base+'_right.png', 'wb').write(
        get_right_tab_image(foreground, background))
        
        

