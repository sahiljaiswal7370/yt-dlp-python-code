from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    str_or_none,
    unified_timestamp,
    url_or_none
)
from ..utils.traversal import traverse_obj


class GodResourceIE(InfoExtractor):
    _VALID_URL = r'https?://new\.godresource\.com/video/(?P<id>\w+)'
    _TESTS = [{
        # hls stream
        'url': 'https://new.godresource.com/video/A01mTKjyf6w',
        'info_dict': {
            'id': 'A01mTKjyf6w',
            'ext': 'mp4',
            'view_count': int,
            'timestamp': 1710978666,
            'channel_id': 5,
            'thumbnail': 'https://cdn-02.godresource.com/e42968ac-9e8b-4231-ab86-f4f9d775841f/thumbnail.jpg',
            'channel': 'Stedfast Baptist Church',
            'upload_date': '20240320',
            'title': 'GodResource',
        }
    }, {
        # mp4 link
        'url': 'https://new.godresource.com/video/01DXmBbQv_X',
        'info_dict': {
            'id': '01DXmBbQv_X',
            'ext': 'mp4',
            'channel_id': 12,
            'view_count': int,
            'timestamp': 1687996800,
            'thumbnail': 'https://cdn-02.godresource.com/sodomitedeception/thumbnail.jpg',
            'channel': 'Documentaries',
            'title': 'The Sodomite Deception',
            'upload_date': '20230629',
        }
    }]

    def _real_extract(self, url):
        display_id = self._match_id(url)

        api_data = self._download_json(
            f'https://api.godresource.com/api/Streams/{display_id}', display_id)

        video_url = api_data['streamUrl']
        if (ext := determine_ext(video_url)) == 'm3u8':
            formats, subtitles = self._extract_m3u8_formats_and_subtitles(
                api_data['streamUrl'], display_id)
        elif ext == 'mp4':
            formats, subtitles = [{
                'url': video_url,
                'ext': ext
            }], {}
        else:
            raise ExtractorError(f'Unexpected video format {ext}')

        return {
            'id': display_id,
            'formats': formats,
            'subtitles': subtitles,
            'title': '',
            **traverse_obj(api_data, {
                'title': ('title', {str}),
                'thumbnail': ('thumbnail', {url_or_none}),
                'view_count': ('views', {int}),
                'channel': ('channelName', {str}),
                'channel_id': ('channelId', {str_or_none}),
                'timestamp': ('streamDateCreated', {unified_timestamp}),
                'modified_timestamp': ('streamDataModified', {unified_timestamp})
            })
        }
