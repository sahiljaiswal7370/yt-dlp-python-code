import json
import urllib.error

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    GeoRestrictedError,
    float_or_none,
    traverse_obj,
    try_call
)


class OnDemandChinaEpisodeIE(InfoExtractor):
    _VALID_URL = r'https?://www\.ondemandchina\.com/\w+/watch/(?P<series_name>[\w-]+)/(?P<id>ep-(?P<episode_num>\d+))'
    _TESTS = [{
        'url': 'https://www.ondemandchina.com/en/watch/together-against-covid-19/ep-1',
        'info_dict': {
            'id': '264394',
            'ext': 'mp4',
            'duration': 3256.88,
            'title': 'EP 1 The Calling',
            'alt_title': '第1集 令出如山',
            'thumbnail': 'https://d2y2efdi5wgkcl.cloudfront.net/fit-in/256x256/media-io/2020/9/11/image.d9816e81.jpg',
            'description': '疫情严峻，党政军民学、东西南北中协同应考',
            'tags': ['Social Humanities', 'Documentary', 'Medical', 'Social'],
        }
    }]

    _QUERY = """query Episode($programSlug: String!, $episodeNumber: Int!, $kind: String!, $part: Int) {
        episode(
            programSlug: $programSlug
            episodeNumber: $episodeNumber
            kind: $kind
            part: $part
        ) {
            ...EpisodeDetail
            __typename
            }
        }

        fragment EpisodeDetail on Episode {
            id
            episodeNumber
            part
            kind
            link
            nextEpisode {
                ...NextEpisodeDetail
                __typename
            }
            title
            titleEn
            titleKo
            titleZhHans
            titleZhHant
            synopsis
            synopsisEn
            synopsisKo
            synopsisZhHans
            synopsisZhHant
            seoSynopsis
            seoSynopsisEn
            seoSynopsisKo
            seoSynopsisZhHans
            seoSynopsisZhHant
            seoKeyword
            seoKeywordEn
            seoKeywordKo
            seoKeywordZhHans
            seoKeywordZhHant
            seoTitle
            seoTitleEn
            seoTitleKo
            seoTitleZhHans
            seoTitleZhHant
            videoCcLanguages
            videoDuration
            releaseDate
            people {
                ...PeopleItem
                __typename
            }
            images {
                thumbnail
                __typename
            }
            ageRating {
                isBlock
                __typename
            }
            __typename
            }

            fragment NextEpisodeDetail on Episode {
                program {
                    slug
                    __typename
                }
                link
                kind
                part
                episodeNumber
                images {
                    thumbnail
                    __typename
                }
                title
                titleEn
                titleKo
                titleZhHans
                titleZhHant
                __typename
            }

            fragment PeopleItem on People {
                role
                slug
                nameEn
                nameZhHans
                nameZhHant
                __typename
            }
            """

    def _get_video_info(self, episode_number, program_slug, display_id):
        video_info = self._download_json(
            'https://odc-graphql.odkmedia.io/graphql', display_id,
            headers={'Content-type': 'application/json'},
            data=json.dumps({
                'operationName': 'Episode',
                'variables': {
                    'programSlug': program_slug,
                    'episodeNumber': int(episode_number),
                    'kind': 'series',
                    'part': None
                },
                'query': self._QUERY}
            ).encode())['data']['episode']
        return video_info

    def _real_extract(self, url):
        program_slug, display_id, ep_number = self._match_valid_url(url).group(
            'series_name', 'id', 'episode_num')
        webpage = self._download_webpage(url, display_id)
        video_info = self._get_video_info(ep_number, program_slug, display_id)
        try:
            source_json = self._download_json(
                f'https://odkmedia.io/odc/api/v2/playback/{video_info["id"]}/', display_id,
                headers={'Authorization': '', 'service-name': 'odc'})
        except ExtractorError as e:
            if (isinstance(e.cause, urllib.error.HTTPError)):
                error_data = self._parse_json(e.cause.read(), display_id)['detail']
                raise GeoRestrictedError(error_data)

        formats, subtitles = [], {}
        for source in traverse_obj(source_json, ('sources', ...)):
            if source.get('type') == 'hls':
                fmts, subs = self._extract_m3u8_formats_and_subtitles(source.get('url'), display_id)
                formats.extend(fmts)
                self._merge_subtitles(subs, target=subtitles)

        return {
            'id': str(video_info['id']),
            'duration': float_or_none(video_info.get('videoDuration'), 1000),
            'thumbnail': (traverse_obj(video_info, ('images', 'thumbnail'))
                          or self._html_search_meta(['og:image', 'twitter:image'], webpage)),
            'title': (video_info.get('title')
                      or self._html_search_meta(['og:title', 'twitter:title'], webpage)
                      or self._html_extract_title(webpage)),
            'alt_title': traverse_obj(video_info, 'titleKo', 'titleZhHans', 'titleZhHant'),
            'description': (traverse_obj(
                video_info, 'synopsisEn', 'synopsisKo', 'synopsisZhHans', 'synopsisZhHant', 'synopisis')
                or self._html_search_meta(['og:description', 'twitter:description', 'description'], webpage)),
            'formats': formats,
            'subtitles': subtitles,
            'tags': try_call(lambda: self._html_search_meta('keywords', webpage).split(", "))
        }
