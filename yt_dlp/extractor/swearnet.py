from .vidyard import VidyardBaseIE
from ..utils import ExtractorError, int_or_none, make_archive_id


class SwearnetEpisodeIE(VidyardBaseIE):
    _VALID_URL = r'https?://www\.swearnet\.com/shows/(?P<id>[\w-]+)/seasons/(?P<season_num>\d+)/episodes/(?P<episode_num>\d+)'
    _TESTS = [{
        'url': 'https://www.swearnet.com/shows/gettin-learnt-with-ricky/seasons/1/episodes/1',
        'info_dict': {
            'id': 'wicK2EOzjOdxkUXGDIgcPw',
            'display_id': '232819',
            'ext': 'mp4',
            'episode_number': 1,
            'episode': 'Episode 1',
            'duration': 719,
            'description': 'md5:c48ef71440ce466284c07085cd7bd761',
            'season': 'Season 1',
            'title': 'Episode 1 - Grilled Cheese Sammich',
            'season_number': 1,
            'thumbnail': 'https://cdn.vidyard.com/thumbnails/custom/0dd74f9b-388a-452e-b570-b407fb64435b_small.jpg',
            '_old_archive_ids': ['swearnetepisode 232819'],
        },
    }]

    def _real_extract(self, url):
        display_id, season_number, episode_number = self._match_valid_url(url).group('id', 'season_num', 'episode_num')
        webpage = self._download_webpage(url, display_id)

        try:
            external_id = self._search_regex(r'externalid\s*=\s*"([^"]+)', webpage, 'externalid')
        except ExtractorError:
            if 'Upgrade Now' in webpage:
                self.raise_login_required()
            raise

        info = self._process_video_json(
            self._fetch_video_json(external_id, display_id)['chapters'][0], display_id)
        if info.get('display_id'):
            info['_old_archive_ids'] = [make_archive_id(self, info['display_id'])]

        return {
            **info,
            'season_number': int_or_none(season_number),
            'episode_number': int_or_none(episode_number),
        }
