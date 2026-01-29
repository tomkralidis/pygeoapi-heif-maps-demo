# =================================================================
#
# Authors: Tom Kralidis <tomkralidis@gmail.com>
#
# Copyright (c) 2026 Tom Kralidis
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================

import logging

import numpy as np
from osgeo import gdal, osr
import pillow_heif
from PIL import Image

from pygeoapi.provider.base import BaseProvider, ProviderQueryError

LOGGER = logging.getLogger(__name__)

IMAGE_FORMATS = {
    'png': 'PNG',
    'jpeg': 'JPEG'
}


class HEIFMapProvider(BaseProvider):
    """
    HEIF map provider

    https://gdal.org/en/stable/drivers/raster/heif.html
    """

    def __init__(self, provider_def):
        """
        Initialize object

        :param provider_def: provider definition

        :returns: pygeoapi.provider.mapscript_.HEIFMapProvider
        """

        BaseProvider.__init__(self, provider_def)

        self.crs = 'EPSG:4326'
        self.crs_list = [self.crs]
        self.styles = []
        self.default_format = 'png'
        LOGGER.debug(f'OPTIONS: {self.options}')

    def query(self, style=None, bbox=[], width=500, height=300, crs='CRS84',
              datetime_=None, format_='png', transparent=True, **kwargs):
        """
        Generate map

        :param style: style name (default is `None`)
        :param bbox: bounding box [minx,miny,maxx,maxy]
        :param width: width of output image (in pixels)
        :param height: height of output image (in pixels)
        :param datetime_: temporal (datestamp or extent)
        :param crs: coordinate reference system identifier
        :param format_: Output format (default is `png`)
        :param transparent: Apply transparency to map (default is `True`)

        :returns: `bytes` of map image
        """

        try:
            _ = IMAGE_FORMATS[format_]
        except KeyError:
            msg = f'Bad output format: {format_}'
            raise ProviderQueryError(user_msg=msg)

        if datetime_ is not None:
            LOGGER.debug('datetime= not yet supported in this provider')

        heif_data = pillow_heif.read_heif(self.data)
        image = Image.frombytes(heif_data.mode, heif_data.size,
                                heif_data.data, 'raw')
        image = image.rotate(-90, expand=True)

        array = np.array(image)
        iheight, iwidth, channels = array.shape

        LOGGER.debug('Creating in memory dataset')
        drv = gdal.GetDriverByName('MEM')
        ds = drv.Create('', iwidth, iheight, channels, gdal.GDT_Byte)

        LOGGER.debug(f'Writing {channels} channels')
        for i in range(channels):
            ds.GetRasterBand(i + 1).WriteArray(array[:, :, i])

        LOGGER.debug(f'Setting CRS to {self.crs}')
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(int(self.crs.split(':')[-1]))
        ds.SetProjection(srs.ExportToWkt())

        LOGGER.debug('Performing affine transformation')
        minx, miny, maxx, maxy = self.options['bbox']
        ds.SetGeoTransform([
            minx,
            (maxx - minx)/iwidth,
            0,
            maxy,
            0,
            -(maxy - miny)/iheight
        ])

        for i in range(1, ds.RasterCount + 1):
            ds.GetRasterBand(i).SetNoDataValue(0)

        LOGGER.debug('clipping dataset to map query')
        ds2 = gdal.Warp(
            '', ds, outputBounds=bbox,
            dstSRS=self.crs, format='MEM',
            width=width,
            height=height
        )

        LOGGER.debug(f'Writing to virtual {IMAGE_FORMATS[format_]}')
        vsipath = '/vsimem/heifout.png'
        gdal.GetDriverByName(IMAGE_FORMATS[format_]).CreateCopy(vsipath, ds2)

        f = gdal.VSIFOpenL(vsipath, 'rb')
        gdal.VSIFSeekL(f, 0, 2)
        size = gdal.VSIFTellL(f)
        gdal.VSIFSeekL(f, 0, 0)
        png_bytes = gdal.VSIFReadL(1, size, f)
        gdal.VSIFCloseL(f)
        gdal.Unlink(vsipath)

        ds = None
        ds2 = None

        return bytes(png_bytes)

    def __repr__(self):
        return f'<HEIFMapProvider> {self.data}'
