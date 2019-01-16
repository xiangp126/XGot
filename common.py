#!/usr/bin/env python3
import io
import os
import re
import sys
import time
import json
import socket
import locale
import logging
import argparse
from importlib import import_module
from urllib import request, parse, error
import threading

remove_slice = False
dry_run = False
json_output = False
force = False
player = None
extractor_proxy = None
cookies = None
output_filename = None
auto_rename = False
lock = threading.Lock()

class PiecesProgressBar:
    def __init__(self, total_pieces = 1, start = 0):
        self.displayed = False
        self.total_pieces = total_pieces
        self.current_piece = start
        self.received = 0
        self.max_index = start + total_pieces

    def update(self):
        self.displayed = True
        bar = '{0:>5}%[{1:<40}] {2}/{3}'.format(
            '', '=' * 40, self.current_piece, self.max_index
        )
        sys.stdout.write('\r' + bar)
        sys.stdout.flush()

    def update_received(self, n):
        self.received += n
        self.update()

    def update_piece(self, n):
        self.current_piece = n

    def done(self):
        if self.displayed:
            print()
            self.displayed = False

def match1(text, *patterns):
    """Scans through a string for substrings matched some patterns (first-subgroups only).

    Args:
        text: A string to be scanned.
        patterns: Arbitrary number of regex patterns.

    Returns:
        When only one pattern is given, returns a string (None if no match found).
        When more than one pattern are given, returns a list of strings ([] if no match found).
    """

    if len(patterns) == 1:
        pattern = patterns[0]
        match = re.search(pattern, text)
        if match:
            return match.group(1)
        else:
            return None
    else:
        ret = []
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                ret.append(match.group(1))
        return ret

def urlopen_with_retry(*args, **kwargs):
    retry_time = 3
    for i in range(retry_time):
        try:
            return request.urlopen(*args, **kwargs)
        except socket.timeout as e:
            logging.debug('request attempt %s timeout' % str(i + 1))
            if i + 1 == retry_time:
                raise e
        # try to tackle youku CDN fails
        except error.HTTPError as http_error:
            logging.debug('HTTP Error with code{}'.format(http_error.code))
            if i + 1 == retry_time:
                raise http_error

def get_content(url, headers={}, decoded=True):
    """Gets the content of a URL via sending a HTTP GET request.

    Args:
        url: A URL.
        headers: Request headers used by the client.
        decoded: Whether decode the response body using UTF-8 or the charset specified in Content-Type.

    Returns:
        The content as a string.
    """

    logging.debug('get_content: %s' % url)

    req = request.Request(url, headers=headers)
    if cookies:
        cookies.add_cookie_header(req)
        req.headers.update(req.unredirected_hdrs)

    response = urlopen_with_retry(req)
    data = response.read()

    # Handle HTTP compression for gzip and deflate (zlib)
    content_encoding = response.getheader('Content-Encoding')
    if content_encoding == 'gzip':
        data = ungzip(data)
    elif content_encoding == 'deflate':
        data = undeflate(data)

    # Decode the response body
    if decoded:
        charset = match1(
            response.getheader('Content-Type', ''), r'charset=([\w-]+)'
        )
        if charset is not None:
            data = data.decode(charset)
        else:
            data = data.decode('utf-8', 'ignore')

    return data

def general_m3u8_extractor(url, headers={}):
    m3u8_list = get_content(url, headers=headers).split('\n')
    urls = []
    for line in m3u8_list:
        line = line.strip()
        if line and not line.startswith('#'):
            if line.startswith('http'):
                urls.append(line)
            else:
                seg_url = parse.urljoin(url, line)
                urls.append(seg_url)
    return urls

def url_size(url, faker=False, headers={}):
    if faker:
        response = urlopen_with_retry(
            request.Request(url, headers=fake_headers)
        )
    elif headers:
        response = urlopen_with_retry(request.Request(url, headers=headers))
    else:
        response = urlopen_with_retry(url)

    size = response.headers['content-length']
    return int(size) if size is not None else float('inf')

def url_save(url, filepath, bar, refer=None, is_part=False, faker=False,
             headers=None, timeout=None, **kwargs):
    tmp_headers = headers.copy() if headers is not None else {}
    # When a referer specified with param refer,
    # the key must be 'Referer' for the hack here
    if refer is not None:
        tmp_headers['Referer'] = refer
    if type(url) is list:
        file_size = urls_size(url, faker=faker, headers=tmp_headers)
        is_chunked, urls = True, url
    else:
        file_size = url_size(url, faker=faker, headers=tmp_headers)
        is_chunked, urls = False, [url]

    continue_renameing = True
    while continue_renameing:
        continue_renameing = False
        if os.path.exists(filepath):
            if not force and file_size == os.path.getsize(filepath):
                if not is_part:
                    if bar:
                        bar.done()
                    log.w(
                        'Skipping {}: file already exists'.format(
                            tr(os.path.basename(filepath))
                        )
                    )
                else:
                    if bar:
                        bar.update_received(file_size)
                return
            else:
                if not is_part:
                    if bar:
                        bar.done()
                    if not force and auto_rename:
                        path, suffix = os.path.basename(filepath).rsplit('.', 1)
                        finder = re.compile(' \([1-9]\d*?\)$')
                        if (finder.search(path) is None):
                            thisfile = path + ' (1).' + suffix
                        else:
                            def numreturn(a):
                                return ' (' + str(int(a.group()[2:-1]) + 1) + ').'
                            thisfile = finder.sub(numreturn, path) + suffix
                        filepath = os.path.join(os.path.dirname(filepath), thisfile)
                        print('Changing name to %s' % tr(os.path.basename(filepath)), '...')
                        continue_renameing = True
                        continue
                    if log.yes_or_no('File with this name already exists. Overwrite?'):
                        log.w('Overwriting %s ...' % tr(os.path.basename(filepath)))
                    else:
                        return
        elif not os.path.exists(os.path.dirname(filepath)):
            os.mkdir(os.path.dirname(filepath))

    temp_filepath = filepath + '.download' if file_size != float('inf') \
        else filepath
    received = 0
    if not force:
        open_mode = 'ab'

        if os.path.exists(temp_filepath):
            received += os.path.getsize(temp_filepath)
            if bar:
                bar.update_received(os.path.getsize(temp_filepath))
    else:
        open_mode = 'wb'

    for url in urls:
        received_chunk = 0
        if received < file_size:
            if faker:
                tmp_headers = fake_headers
            '''
            if parameter headers passed in, we have it copied as tmp_header
            elif headers:
                headers = headers
            else:
                headers = {}
            '''
            if received and not is_chunked:  # only request a range when not chunked
                tmp_headers['Range'] = 'bytes=' + str(received) + '-'
            if refer:
                tmp_headers['Referer'] = refer

            if timeout:
                response = urlopen_with_retry(
                    request.Request(url, headers=tmp_headers), timeout=timeout
                )
            else:
                response = urlopen_with_retry(
                    request.Request(url, headers=tmp_headers)
                )
            try:
                range_start = int(
                    response.headers[
                        'content-range'
                    ][6:].split('/')[0].split('-')[0]
                )
                end_length = int(
                    response.headers['content-range'][6:].split('/')[1]
                )
                range_length = end_length - range_start
            except:
                content_length = response.headers['content-length']
                range_length = int(content_length) if content_length is not None \
                    else float('inf')

            if is_chunked:  # always append if chunked
                open_mode = 'ab'
            elif file_size != received + range_length:  # is it ever necessary?
                received = 0
                if bar:
                    bar.received = 0
                open_mode = 'wb'

            with open(temp_filepath, open_mode) as output:
                while True:
                    buffer = None
                    try:
                        buffer = response.read(1024 * 256)
                    except socket.timeout:
                        pass
                    if not buffer:
                        if is_chunked and received_chunk == range_length:
                            break
                        elif not is_chunked and received == file_size:  # Download finished
                            break
                        # Unexpected termination. Retry request
                        if not is_chunked:  # when
                            tmp_headers['Range'] = 'bytes=' + str(received) + '-'
                        response = urlopen_with_retry(
                            request.Request(url, headers=tmp_headers)
                        )
                        continue
                    output.write(buffer)
                    received += len(buffer)
                    received_chunk += len(buffer)
                    if bar:
                        bar.update_received(len(buffer))

    assert received == os.path.getsize(temp_filepath), '%s == %s == %s' % (
        received, os.path.getsize(temp_filepath), temp_filepath
    )

    if os.access(filepath, os.W_OK):
        # on Windows rename could fail if destination filepath exists
        os.remove(filepath)
    os.rename(temp_filepath, filepath)

def get_output_filename(urls, title, suffix, output_dir, merge):
    # lame hack for the --output-filename option
    global output_filename
    if output_filename:
        if suffix:
            return output_filename + '.' + suffix
        return output_filename

    merged_suffix = suffix
    if (len(urls) > 1) and merge:
        from processor.ffmpeg import has_ffmpeg_installed
        # only support suffix: ts now
        if has_ffmpeg_installed():
            merged_suffix = 'mp4'
    return '%s.%s' % (title, merged_suffix)

def download_urls(urls, title, suffix, total_size, parts, output_dir = '.',
                  refer = None, merge = True, faker = False, headers = {},
                  base = 0, **kwargs):
    assert urls

    bar = PiecesProgressBar(len(urls), base)
    slice_parts = []

    bar.update()
    for i, url in enumerate(urls):
        filename = '%s_%02d.%s' % (title, base + i, suffix)
        filepath = os.path.join(output_dir, filename)
        slice_parts.append(filepath)
        bar.update_piece(base + i + 1)

        url_save(url, filepath, bar, refer=refer, is_part=True, faker=faker,
                 headers=headers, **kwargs)

    #  bar.done()

def tackle_slice_of_ts(parts, output_filepath, suffix, merge):
    if not merge:
        print()
        return

    # only support mpeg2-ts now
    if suffix == 'ts':
        try:
            from processor.ffmpeg import has_ffmpeg_installed
            if has_ffmpeg_installed():
                from processor.ffmpeg import ffmpeg_concat_ts_to_mp4
                ffmpeg_concat_ts_to_mp4(parts, output_filepath)
            else:
                from processor.join_ts import concat_ts
                concat_ts(parts, output_filepath)
            print('\nMerged into %s' %output_filepath)
        except:
            raise
        else:
            for part in parts:
                if remove_slice:
                    os.remove(part)
    else:
        print("Can't merge %s files" % suffix)

    print()
