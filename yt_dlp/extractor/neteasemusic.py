import itertools
import json
import re
import time
from base64 import b64encode
from binascii import hexlify
from hashlib import md5
from random import randint

from .common import InfoExtractor
from ..aes import aes_ecb_encrypt, pkcs7_padding
from ..compat import compat_urllib_parse_urlencode
from ..networking import Request
from ..utils import (
    ExtractorError,
    bytes_to_intlist,
    error_to_compat_str,
    strftime_or_none,
    float_or_none,
    int_or_none,
    str_or_none,
    traverse_obj,
    intlist_to_bytes,
    urljoin,
    try_get,
)


class NetEaseMusicBaseIE(InfoExtractor):
    _FORMATS = ['bMusic', 'mMusic', 'hMusic']
    _NETEASE_SALT = '3go8&$8*3*3h0k(2)2'
    _API_BASE = 'http://music.163.com/api/'

    @classmethod
    def _encrypt(cls, dfsid):
        salt_bytes = bytearray(cls._NETEASE_SALT.encode('utf-8'))
        string_bytes = bytearray(str(dfsid).encode('ascii'))
        salt_len = len(salt_bytes)
        for i in range(len(string_bytes)):
            string_bytes[i] = string_bytes[i] ^ salt_bytes[i % salt_len]
        m = md5()
        m.update(bytes(string_bytes))
        result = b64encode(m.digest()).decode('ascii')
        return result.replace('/', '_').replace('+', '-')

    def _create_eapi_cipher(self, api_path, query, cookies):
        KEY = b'e82ckenh8dichen8'
        request_text = json.dumps({**query, 'header': cookies}, separators=(',', ':'))

        message = f'nobody{api_path}use{request_text}md5forencrypt'.encode('latin1')
        msg_digest = md5(message).hexdigest()

        data = pkcs7_padding(bytes_to_intlist(
            f'{api_path}-36cd479b6b5-{request_text}-36cd479b6b5-{msg_digest}'))
        encrypted = intlist_to_bytes(aes_ecb_encrypt(data, bytes_to_intlist(KEY)))
        return b'params=' + hexlify(encrypted).upper()

    def _download_eapi_json(self, path, song_id, query, headers={}, **kwargs):
        cookies = {
            'osver': None,
            'deviceId': None,
            'appver': '8.0.0',
            'versioncode': '140',
            'mobilename': None,
            'buildver': '1623435496',
            'resolution': '1920x1080',
            '__csrf': '',
            'os': 'pc',
            'channel': None,
            'requestId': f'{int(time.time() * 1000)}_{randint(0, 1000):04}',
        }
        headers = {
            'User-Agent': self.get_param('http_headers', {}).get('User-Agent'),
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://music.163.com',
            'Cookie': '; '.join([f'{k}={v if v is not None else "undefined"}' for [k, v] in cookies.items()]),
            **headers,
        }
        url = urljoin('https://interface3.music.163.com/', f'/eapi{path}')
        data = self._create_eapi_cipher(f'/api{path}', query, cookies)
        return self._download_json(url, song_id, data=data, headers=headers, **kwargs)

    def _call_player_api(self, song_id, bitrate):
        return self._download_eapi_json(
            '/song/enhance/player/url', song_id,
            {'ids': f'[{song_id}]', 'br': bitrate},
            note=f'Downloading song URL info: bitrate {bitrate}')

    def make_player_api_request_data_and_headers(self, song_id, bitrate):
        KEY = b'e82ckenh8dichen8'
        URL = '/api/song/enhance/player/url'
        now = int(time.time() * 1000)
        rand = randint(0, 1000)
        cookie = {
            'osver': None,
            'deviceId': None,
            'appver': '8.0.0',
            'versioncode': '140',
            'mobilename': None,
            'buildver': '1623435496',
            'resolution': '1920x1080',
            '__csrf': '',
            'os': 'pc',
            'channel': None,
            'requestId': '{0}_{1:04}'.format(now, rand),
        }
        request_text = json.dumps(
            {'ids': '[{0}]'.format(song_id), 'br': bitrate, 'header': cookie},
            separators=(',', ':'))
        message = 'nobody{0}use{1}md5forencrypt'.format(
            URL, request_text).encode('latin1')
        msg_digest = md5(message).hexdigest()

        data = '{0}-36cd479b6b5-{1}-36cd479b6b5-{2}'.format(
            URL, request_text, msg_digest)
        data = pkcs7_padding(bytes_to_intlist(data))
        encrypted = intlist_to_bytes(aes_ecb_encrypt(data, bytes_to_intlist(KEY)))
        encrypted_params = hexlify(encrypted).decode('ascii').upper()

        cookie = '; '.join(
            ['{0}={1}'.format(k, v if v is not None else 'undefined')
             for [k, v] in cookie.items()])

        headers = {
            'User-Agent': self.get_param('http_headers', {}).get('User-Agent'),
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://music.163.com',
            'Cookie': cookie,
        }
        return ('params={0}'.format(encrypted_params), headers)

    def _call_player_api_old(self, song_id, bitrate):
        url = 'https://interface3.music.163.com/eapi/song/enhance/player/url'
        data, headers = self.make_player_api_request_data_and_headers(song_id, bitrate)
        try:
            msg = 'empty result'
            result = self._download_json(
                url, song_id, data=data.encode('ascii'), headers=headers)
            if result:
                return result
        except ExtractorError as e:
            if type(e.cause) in (ValueError, TypeError):
                # JSON load failure
                raise
        except Exception as e:
            msg = error_to_compat_str(e)
            self.report_warning('%s API call (%s) failed: %s' % (
                song_id, bitrate, msg))
        return {}

    def extract_formats(self, info):
        err = 0
        formats = []
        song_id = info['id']
        for song_format in self._FORMATS:
            details = info.get(song_format)
            if not details:
                continue

            bitrate = int_or_none(details.get('bitrate')) or 999000
            data = self._call_player_api(song_id, bitrate)
            for song in try_get(data, lambda x: x['data'], list) or []:
                song_url = try_get(song, lambda x: x['url'])
                if not song_url:
                    continue
                if self._is_valid_url(song_url, info['id'], 'song'):
                    formats.append({
                        'url': song_url,
                        'ext': details.get('extension'),
                        'abr': float_or_none(song.get('br'), scale=1000),
                        'format_id': song_format,
                        'filesize': int_or_none(song.get('size')),
                        'asr': int_or_none(details.get('sr')),
                    })
                elif err == 0:
                    err = try_get(song, lambda x: x['code'], int)

        if not formats:
            msg = 'No media links found'
            if err != 0 and (err < 200 or err >= 400):
                raise ExtractorError(
                    '%s (site code %d)' % (msg, err, ), expected=True)
            else:
                self.raise_geo_restricted(
                    msg + ': probably this video is not available from your location due to geo restriction.',
                    countries=['CN'])

        return formats

    @classmethod
    def convert_milliseconds(cls, ms):
        return int(round(ms / 1000.0))

    def query_api(self, endpoint, video_id, note):
        req = Request('%s%s' % (self._API_BASE, endpoint))
        req.headers['Referer'] = self._API_BASE
        result = self._download_json(req, video_id, note)
        if result['code'] == -462:
            self.raise_login_required(f'Login required to download: {result["message"]}')
        elif result['code'] != 200:
            raise ExtractorError(f'Failed to get meta info: {result["code"]} {result}')
        return result


class NetEaseMusicIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:song'
    IE_DESC = '网易云音乐'
    _VALID_URL = r'https?://(y\.)?music\.163\.com/(?:[#m]/)?song\?.*?\bid=(?P<id>[0-9]+)'
    _TESTS = [{
        'url': 'http://music.163.com/#/song?id=32102397',
        'md5': '3e909614ce09b1ccef4a3eb205441190',
        'info_dict': {
            'id': '32102397',
            'ext': 'mp3',
            'title': 'Bad Blood',
            'creator': 'Taylor Swift / Kendrick Lamar',
            'upload_date': '20150516',
            'timestamp': 1431792000,
            'description': 'md5:25fc5f27e47aad975aa6d36382c7833c',
            'duration': 199,
            'thumbnail': r're:^http.*\.jpg',
        },
    }, {
        'note': 'No lyrics.',
        'url': 'http://music.163.com/song?id=17241424',
        'info_dict': {
            'id': '17241424',
            'ext': 'mp3',
            'title': 'Opus 28',
            'creator': 'Dustin O\'Halloran',
            'upload_date': '20080211',
            'description': 'md5:f12945b0f6e0365e3b73c5032e1b0ff4',
            'timestamp': 1202745600,
        },
    }, {
        'note': 'Has translated name.',
        'url': 'http://music.163.com/#/song?id=22735043',
        'info_dict': {
            'id': '22735043',
            'ext': 'mp3',
            'title': '소원을 말해봐 (Genie)',
            'creator': '少女时代',
            'description': 'md5:79d99cc560e4ca97e0c4d86800ee4184',
            'upload_date': '20100127',
            'timestamp': 1264608000,
            'alt_title': '说出愿望吧(Genie)',
        },
    }, {
        'url': 'https://y.music.163.com/m/song?app_version=8.8.45&id=95670&uct2=sKnvS4+0YStsWkqsPhFijw%3D%3D&dlt=0846',
        'md5': '95826c73ea50b1c288b22180ec9e754d',
        'info_dict': {
            'id': '95670',
            'ext': 'mp3',
            'title': '国际歌',
            'creator': '马备',
            'upload_date': '19911130',
            'timestamp': 691516800,
            'description': 'md5:1ba2f911a2b0aa398479f595224f2141',
        },
    }]

    def _process_lyrics(self, lyrics_info):
        original = lyrics_info.get('lrc', {}).get('lyric')
        translated = lyrics_info.get('tlyric', {}).get('lyric')

        if not translated:
            return original

        lyrics_expr = r'(\[[0-9]{2}:[0-9]{2}\.[0-9]{2,}\])([^\n]+)'
        original_ts_texts = re.findall(lyrics_expr, original)
        translation_ts_dict = dict(
            (time_stamp, text) for time_stamp, text in re.findall(lyrics_expr, translated)
        )
        lyrics = '\n'.join([
            '%s%s / %s' % (time_stamp, text, translation_ts_dict.get(time_stamp, ''))
            for time_stamp, text in original_ts_texts
        ])
        return lyrics

    def _real_extract(self, url):
        song_id = self._match_id(url)

        params = {
            'id': song_id,
            'ids': '[%s]' % song_id
        }
        info = self.query_api(
            'song/detail?' + compat_urllib_parse_urlencode(params),
            song_id, 'Downloading song info')['songs'][0]

        formats = self.extract_formats(info)

        lyrics_info = self.query_api(
            'song/lyric?id=%s&lv=-1&tv=-1' % song_id,
            song_id, 'Downloading lyrics data')
        lyrics = self._process_lyrics(lyrics_info)

        alt_title = None
        if info.get('transNames'):
            alt_title = '/'.join(info.get('transNames'))

        return {
            'id': song_id,
            'title': info['name'],
            'alt_title': alt_title,
            'creator': ' / '.join([artist['name'] for artist in info.get('artists', [])]),
            'timestamp': self.convert_milliseconds(info.get('album', {}).get('publishTime')),
            'thumbnail': info.get('album', {}).get('picUrl'),
            'duration': self.convert_milliseconds(info.get('duration', 0)),
            'description': lyrics,
            'formats': formats,
        }


class NetEaseMusicAlbumIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:album'
    IE_DESC = '网易云音乐 - 专辑'
    _VALID_URL = r'https?://music\.163\.com/(#/)?album\?id=(?P<id>[0-9]+)'
    _TEST = {
        'url': 'http://music.163.com/#/album?id=220780',
        'info_dict': {
            'id': '220780',
            'title': 'B\'Day',
        },
        'playlist_count': 23,
        'skip': 'Blocked outside Mainland China',
    }

    def _real_extract(self, url):
        album_id = self._match_id(url)

        info = self.query_api(
            'album/%s?id=%s' % (album_id, album_id),
            album_id, 'Downloading album data')['album']

        name = info['name']
        desc = info.get('description') or None
        entries = [
            self.url_result('http://music.163.com/#/song?id=%s' % song['id'],
                            'NetEaseMusic', song['id'])
            for song in info['songs']
        ]
        return self.playlist_result(entries, album_id, name, desc)


class NetEaseMusicSingerIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:singer'
    IE_DESC = '网易云音乐 - 歌手'
    _VALID_URL = r'https?://music\.163\.com/(#/)?artist\?id=(?P<id>[0-9]+)'
    _TESTS = [{
        'note': 'Singer has aliases.',
        'url': 'http://music.163.com/#/artist?id=10559',
        'info_dict': {
            'id': '10559',
            'title': '张惠妹 - aMEI;阿妹;阿密特',
        },
        'playlist_count': 50,
        'skip': 'Blocked outside Mainland China',
    }, {
        'note': 'Singer has translated name.',
        'url': 'http://music.163.com/#/artist?id=124098',
        'info_dict': {
            'id': '124098',
            'title': '李昇基 - 이승기',
        },
        'playlist_count': 50,
        'skip': 'Blocked outside Mainland China',
    }]

    def _real_extract(self, url):
        singer_id = self._match_id(url)

        info = self.query_api(
            'artist/%s?id=%s' % (singer_id, singer_id),
            singer_id, 'Downloading singer data')

        name = info['artist']['name']
        if info['artist']['trans']:
            name = '%s - %s' % (name, info['artist']['trans'])
        if info['artist']['alias']:
            name = '%s - %s' % (name, ';'.join(info['artist']['alias']))

        entries = [
            self.url_result('http://music.163.com/#/song?id=%s' % song['id'],
                            'NetEaseMusic', song['id'])
            for song in info['hotSongs']
        ]
        return self.playlist_result(entries, singer_id, name)


class NetEaseMusicListIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:playlist'
    IE_DESC = '网易云音乐 - 歌单'
    _VALID_URL = r'https?://music\.163\.com/(#/)?(playlist|discover/toplist)\?id=(?P<id>[0-9]+)'
    _TESTS = [{
        'url': 'http://music.163.com/#/playlist?id=79177352',
        'info_dict': {
            'id': '79177352',
            'title': 'Billboard 2007 Top 100',
            'description': 'md5:12fd0819cab2965b9583ace0f8b7b022',
            'tags': ['欧美'],
            'uploader': '浑然破灭',
            'uploader_id': '67549805',
        },
        'playlist_mincount': 95,
        'skip': 'Blocked outside Mainland China',
    }, {
        'note': 'Toplist/Charts sample',
        'url': 'http://music.163.com/#/discover/toplist?id=3733003',
        'info_dict': {
            'id': '3733003',
            'title': 're:韩国Melon排行榜周榜 [0-9]{4}-[0-9]{2}-[0-9]{2}',
            'description': 'md5:73ec782a612711cadc7872d9c1e134fc',
        },
        'playlist_count': 50,
        'skip': 'Blocked outside Mainland China',
    }]

    def _real_extract(self, url):
        list_id = self._match_id(url)

        info = self._download_eapi_json(
            '/v3/playlist/detail', list_id,
            {'id': list_id, 't': '-1', 'n': '500', 's': '0'},
            note="Downloading playlist info")

        meta = traverse_obj(info, ('playlist', {
            'title': ('name', {str_or_none}),
            'description': ('description', {str_or_none}),
            'tags': ('tags', ..., {str_or_none}),
            'uploader': ('creator', 'nickname', {str_or_none}),
            'uploader_id': ('creator', 'userId', {str_or_none}),
            'timestamp': ('creator', 'updateTime', {lambda i: int_or_none(i, scale=1000)}),
        }))
        if traverse_obj(info, ('playlist', 'specialType')) == 10:
            meta['title'] = f'{meta.get("title")} {strftime_or_none(meta.get("timestamp"), "%Y-%m-%d")}'

        entries = [
            self.url_result(f'http://music.163.com/#/song?id={song_id}',
                            NetEaseMusicIE, song_id)
            for song_id in traverse_obj(info, ('playlist', 'tracks', ..., 'id'))]
        return self.playlist_result(entries, list_id, **meta)


class NetEaseMusicMvIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:mv'
    IE_DESC = '网易云音乐 - MV'
    _VALID_URL = r'https?://music\.163\.com/(#/)?mv\?id=(?P<id>[0-9]+)'
    _TEST = {
        'url': 'http://music.163.com/#/mv?id=415350',
        'info_dict': {
            'id': '415350',
            'ext': 'mp4',
            'title': '이럴거면 그러지말지',
            'description': '白雅言自作曲唱甜蜜爱情',
            'creator': '白娥娟',
            'upload_date': '20150520',
            'thumbnail': r're:http.*\.jpg',
            'duration': 217,
        },
        'skip': 'Blocked outside Mainland China',
    }

    def _real_extract(self, url):
        mv_id = self._match_id(url)

        info = self.query_api(
            'mv/detail?id=%s&type=mp4' % mv_id,
            mv_id, 'Downloading mv info')['data']

        formats = [
            {'url': mv_url, 'ext': 'mp4', 'format_id': '%sp' % brs, 'height': int(brs)}
            for brs, mv_url in info['brs'].items()
        ]

        return {
            'id': mv_id,
            'title': info['name'],
            'description': info.get('desc') or info.get('briefDesc'),
            'creator': info['artistName'],
            'upload_date': info['publishTime'].replace('-', ''),
            'formats': formats,
            'thumbnail': info.get('cover'),
            'duration': self.convert_milliseconds(info.get('duration', 0)),
        }


class NetEaseMusicProgramIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:program'
    IE_DESC = '网易云音乐 - 电台节目'
    _VALID_URL = r'https?://music\.163\.com/(#/?)program\?id=(?P<id>[0-9]+)'
    _TESTS = [{
        'url': 'http://music.163.com/#/program?id=10109055',
        'info_dict': {
            'id': '32593346',
            'ext': 'mp3',
            'title': '不丹足球背后的故事',
            'description': '喜马拉雅人的足球梦 ...',
            'creator': '大话西藏',
            'timestamp': 1434179287,
            'upload_date': '20150613',
            'thumbnail': r're:http.*\.jpg',
            'duration': 900,
        },
    }, {
        'note': 'This program has accompanying songs.',
        'url': 'http://music.163.com/#/program?id=10141022',
        'info_dict': {
            'id': '10141022',
            'title': '滚滚电台的有声节目',
            'description': 'md5:8d594db46cc3e6509107ede70a4aaa3b',
        },
        'playlist_count': 4,
    }, {
        'note': 'This program has accompanying songs.',
        'url': 'http://music.163.com/#/program?id=10141022',
        'info_dict': {
            'id': '32647209',
            'ext': 'mp3',
            'title': '滚滚电台的有声节目',
            'description': 'md5:8d594db46cc3e6509107ede70a4aaa3b',
            'creator': '滚滚电台ORZ',
            'timestamp': 1434450733,
            'upload_date': '20150616',
            'thumbnail': r're:http.*\.jpg',
            'duration': 1104,
        },
        'params': {
            'noplaylist': True
        },
    }]

    def _real_extract(self, url):
        program_id = self._match_id(url)

        info = self.query_api(
            'dj/program/detail?id=%s' % program_id,
            program_id, 'Downloading program info')['program']

        name = info['name']
        description = info['description']

        if not self._yes_playlist(info['songs'] and program_id, info['mainSong']['id']):
            formats = self.extract_formats(info['mainSong'])

            return {
                'id': str(info['mainSong']['id']),
                'title': name,
                'description': description,
                'creator': info['dj']['brand'],
                'timestamp': self.convert_milliseconds(info['createTime']),
                'thumbnail': info['coverUrl'],
                'duration': self.convert_milliseconds(info.get('duration', 0)),
                'formats': formats,
            }

        song_ids = [info['mainSong']['id']]
        song_ids.extend([song['id'] for song in info['songs']])
        entries = [
            self.url_result('http://music.163.com/#/song?id=%s' % song_id,
                            'NetEaseMusic', song_id)
            for song_id in song_ids
        ]
        return self.playlist_result(entries, program_id, name, description)


class NetEaseMusicDjRadioIE(NetEaseMusicBaseIE):
    IE_NAME = 'netease:djradio'
    IE_DESC = '网易云音乐 - 电台'
    _VALID_URL = r'https?://music\.163\.com/(#/)?djradio\?id=(?P<id>[0-9]+)'
    _TEST = {
        'url': 'http://music.163.com/#/djradio?id=42',
        'info_dict': {
            'id': '42',
            'title': '声音蔓延',
            'description': 'md5:c7381ebd7989f9f367668a5aee7d5f08'
        },
        'playlist_mincount': 40,
    }
    _PAGE_SIZE = 1000

    def _real_extract(self, url):
        dj_id = self._match_id(url)

        name = None
        desc = None
        entries = []
        for offset in itertools.count(start=0, step=self._PAGE_SIZE):
            info = self.query_api(
                'dj/program/byradio?asc=false&limit=%d&radioId=%s&offset=%d'
                % (self._PAGE_SIZE, dj_id, offset),
                dj_id, 'Downloading dj programs - %d' % offset)

            entries.extend([
                self.url_result(
                    'http://music.163.com/#/program?id=%s' % program['id'],
                    'NetEaseMusicProgram', program['id'])
                for program in info['programs']
            ])

            if name is None:
                radio = info['programs'][0]['radio']
                name = radio['name']
                desc = radio['desc']

            if not info['more']:
                break

        return self.playlist_result(entries, dj_id, name, desc)
