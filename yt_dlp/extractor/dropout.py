import functools

from .common import InfoExtractor
from .vimeo import VHXEmbedIE
from ..utils import (
    ExtractorError,
    OnDemandPagedList,
    clean_html,
    extract_attributes,
    get_element_by_class,
    get_element_by_id,
    get_elements_html_by_class,
    int_or_none,
    traverse_obj,
    unified_strdate,
    urlencode_postdata,
)


class DropoutBaseIE(InfoExtractor):
    """Subclasses must define _HOST"""

    def _get_authenticity_token(self, display_id):
        signin_page = self._download_webpage(
            f'{self._HOST}/login', display_id, note='Getting authenticity token')
        return self._html_search_regex(
            r'name=["\']authenticity_token["\'] value=["\'](.+?)["\']',
            signin_page, 'authenticity_token')

    def _login(self, display_id):
        username, password = self._get_login_info()
        if not username:
            return True

        response = self._download_webpage(
            f'{self._HOST}/login', display_id, note='Logging in', fatal=False,
            data=urlencode_postdata({
                'email': username,
                'password': password,
                'authenticity_token': self._get_authenticity_token(display_id),
                'utf8': True,
            }))

        user_has_subscription = self._search_regex(
            r'user_has_subscription:\s*["\'](.+?)["\']', response, 'subscription status', default='none')
        if user_has_subscription.lower() == 'true':
            return
        elif user_has_subscription.lower() == 'false':
            return 'Account is not subscribed'
        else:
            return 'Incorrect username/password'

    def _real_extract(self, url):
        display_id = self._match_id(url)

        webpage = None
        if self._get_cookies(self._HOST).get('_session'):
            webpage = self._download_webpage(url, display_id)
        if not webpage or '<div id="watch-unauthorized"' in webpage:
            login_err = self._login(display_id)
            webpage = self._download_webpage(url, display_id)
            if login_err and '<div id="watch-unauthorized"' in webpage:
                if login_err is True:
                    self.raise_login_required(method='any')
                raise ExtractorError(login_err, expected=True)

        embed_url = self._search_regex(r'embed_url:\s*["\'](.+?)["\']', webpage, 'embed url')
        thumbnail = self._og_search_thumbnail(webpage)
        watch_info = get_element_by_id('watch-info', webpage) or ''

        title = clean_html(get_element_by_class('video-title', watch_info))
        season_episode = get_element_by_class(
            'site-font-secondary-color', get_element_by_class('text', watch_info))
        episode_number = int_or_none(self._search_regex(
            r'Episode (\d+)', season_episode or '', 'episode', default=None))

        return {
            '_type': 'url_transparent',
            'ie_key': VHXEmbedIE.ie_key(),
            'url': VHXEmbedIE._smuggle_referrer(embed_url, self._HOST),
            'id': self._search_regex(r'embed\.vhx\.tv/videos/(.+?)\?', embed_url, 'id'),
            'display_id': display_id,
            'title': title,
            'description': self._html_search_meta('description', webpage, fatal=False),
            'thumbnail': thumbnail.split('?')[0] if thumbnail else None,  # Ignore crop/downscale
            'series': clean_html(get_element_by_class('series-title', watch_info)),
            'episode_number': episode_number,
            'episode': title if episode_number else None,
            'season_number': int_or_none(self._search_regex(
                r'Season (\d+),', season_episode or '', 'season', default=None)),
            'release_date': unified_strdate(self._search_regex(
                r'data-meta-field-name=["\']release_dates["\'] data-meta-field-value=["\'](.+?)["\']',
                watch_info, 'release date', default=None)),
        }


class DropoutIE(DropoutBaseIE):
    _HOST = 'https://www.dropout.tv'
    _NETRC_MACHINE = 'dropout'

    _VALID_URL = r'https?://(?:www\.)?dropout\.tv/(?:[^/]+/)*videos/(?P<id>[^/]+)/?$'
    _TESTS = [
        {
            'url': 'https://www.dropout.tv/game-changer/season:2/videos/yes-or-no',
            'note': 'Episode in a series',
            'md5': 'fc55805bac60b1ce2ffdc35fb9c51195',
            'info_dict': {
                'id': '738153',
                'display_id': 'yes-or-no',
                'ext': 'mp4',
                'title': 'Yes or No',
                'description': 'Ally, Brennan, and Zac are asked a simple question, but is there a correct answer?',
                'release_date': '20200508',
                'thumbnail': 'https://vhx.imgix.net/chuncensoredstaging/assets/351e3f24-c4a3-459a-8b79-dc80f1e5b7fd.jpg',
                'series': 'Game Changer',
                'season_number': 2,
                'season': 'Season 2',
                'episode_number': 6,
                'episode': 'Yes or No',
                'duration': 1180,
                'uploader_id': 'user80538407',
                'uploader_url': 'https://vimeo.com/user80538407',
                'uploader': 'OTT Videos'
            },
            'expected_warnings': ['Ignoring subtitle tracks found in the HLS manifest'],
        },
        {
            'url': 'https://www.dropout.tv/ch-shorts/season:1/videos/post-apocalyptic-dane-cook',
            'note': 'Episode in a series (missing release_date)',
            'md5': 'f260b8d7d0fdbaceae713c9196dac07f',
            'info_dict': {
                'id': '449042',
                'display_id': 'post-apocalyptic-dane-cook',
                'ext': 'mp4',
                'title': 'Post-Apocalyptic Dane Cook',
                'description': 'Dane Cook is back with his all new special. Don\'t worry, it\'s not the end of the world.',
                'thumbnail': 'https://vhx.imgix.net/chuncensoredstaging/assets/5b0678df-d9c3-4864-b811-24db03072f4a.jpg',
                'series': 'CH Shorts',
                'season_number': 1,
                'season': 'Season 1',
                'episode_number': 1,
                'episode': 'Post-Apocalyptic Dane Cook',
                'duration': 135,
                'uploader_id': 'user80538407',
                'uploader_url': 'https://vimeo.com/user80538407',
                'uploader': 'OTT Videos'
            },
            'expected_warnings': ['Ignoring subtitle tracks found in the HLS manifest'],
        },
        {
            'url': 'https://www.dropout.tv/videos/misfits-magic-holiday-special',
            'note': 'Episode not in a series',
            'md5': '147e0607bd877a791665c0b7219b512c',
            'info_dict': {
                'id': '1915774',
                'display_id': 'misfits-magic-holiday-special',
                'ext': 'mp4',
                'title': 'Misfits & Magic Holiday Special',
                'description': 'The magical misfits spend Christmas break at Gowpenny, with an unwelcome visitor.',
                'release_date': '20211215',
                'thumbnail': 'https://vhx.imgix.net/chuncensoredstaging/assets/d91ea8a6-b250-42ed-907e-b30fb1c65176-8e24b8e5.jpg',
                'duration': 11698,
                'uploader_id': 'user80538407',
                'uploader_url': 'https://vimeo.com/user80538407',
                'uploader': 'OTT Videos'
            },
            'expected_warnings': ['Ignoring subtitle tracks found in the HLS manifest'],
        },
    ]


class DropoutSeasonBaseIE(InfoExtractor):
    """Subclasses must define _VIDEO_IE"""
    _PAGE_SIZE = 24

    def _fetch_page(self, url, season_id, page):
        page += 1
        webpage = self._download_webpage(
            f'{url}?page={page}', season_id, note=f'Downloading page {page}', expected_status={400})
        yield from [self.url_result(item_url, self._VIDEO_IE) for item_url in traverse_obj(
            get_elements_html_by_class('browse-item-link', webpage), (..., {extract_attributes}, 'href'))]

    def _real_extract(self, url):
        season_id = self._match_id(url)
        season_num = self._match_valid_url(url).group('season') or 1
        season_title = season_id.replace('-', ' ').title()

        return self.playlist_result(
            OnDemandPagedList(functools.partial(self._fetch_page, url, season_id), self._PAGE_SIZE),
            f'{season_id}-season-{season_num}', f'{season_title} - Season {season_num}')


class DropoutSeasonIE(DropoutSeasonBaseIE):
    _VALID_URL = r'https?://(?:www\.)?dropout\.tv/(?P<id>[^\/$&?#]+)(?:/?$|/season:(?P<season>[0-9]+)/?$)'
    _VIDEO_IE = DropoutIE
    _TESTS = [
        {
            'url': 'https://www.dropout.tv/dimension-20-fantasy-high/season:1',
            'note': 'Multi-season series with the season in the url',
            'playlist_count': 24,
            'info_dict': {
                'id': 'dimension-20-fantasy-high-season-1',
                'title': 'Dimension 20 Fantasy High - Season 1',
            },
        },
        {
            'url': 'https://www.dropout.tv/dimension-20-fantasy-high',
            'note': 'Multi-season series with the season not in the url',
            'playlist_count': 24,
            'info_dict': {
                'id': 'dimension-20-fantasy-high-season-1',
                'title': 'Dimension 20 Fantasy High - Season 1',
            },
        },
        {
            'url': 'https://www.dropout.tv/dimension-20-shriek-week',
            'note': 'Single-season series',
            'playlist_count': 4,
            'info_dict': {
                'id': 'dimension-20-shriek-week-season-1',
                'title': 'Dimension 20 Shriek Week - Season 1',
            },
        },
        {
            'url': 'https://www.dropout.tv/breaking-news-no-laugh-newsroom/season:3',
            'note': 'Multi-season series with season in the url that requires pagination',
            'playlist_count': 25,
            'info_dict': {
                'id': 'breaking-news-no-laugh-newsroom-season-3',
                'title': 'Breaking News No Laugh Newsroom - Season 3',
            },
        },
    ]
