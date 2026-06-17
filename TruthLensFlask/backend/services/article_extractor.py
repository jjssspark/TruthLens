import requests
from bs4 import BeautifulSoup


class ArticleExtractor:
    """
    URL에서 기사 본문만 추출하는 클래스

    지원 언론사
    - 네이버 뉴스
    - 다음 뉴스
    - 연합뉴스
    - 조선일보
    - 중앙일보
    - 동아일보
    - 한국경제
    - 머니투데이
    - SBS
    - KBS
    - MBC
    - YTN

    그 외 사이트는 article/div 기반으로 자동 추출
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/137 Safari/537.36"
        )
    }

    SELECTORS = {

        # 네이버
        "n.news.naver.com": [
            "#dic_area"
        ],

        # 다음
        "v.daum.net": [
            ".article_view"
        ],

        # 연합뉴스
        "yna.co.kr": [
            "#articleWrap",
            ".story-news"
        ],

        # 조선일보
        "chosun.com": [
            ".article-body",
            ".news_body"
        ],

        # 중앙일보
        "joongang.co.kr": [
            ".article_body",
            "#article_body"
        ],

        # 동아일보
        "donga.com": [
            ".article_txt"
        ],

        # 한국경제
        "hankyung.com": [
            "#articletxt",
            ".article-body"
        ],

        # 머니투데이
        "mt.co.kr": [
            "#textBody",
            ".article_body"
        ],

        # SBS
        "sbs.co.kr": [
            ".main_text"
        ],

        # KBS
        "news.kbs.co.kr": [
            "#cont_newstext"
        ],

        # MBC
        "imbc.com": [
            ".news_txt"
        ],

        # YTN
        "ytn.co.kr": [
            "#CmAdContent"
        ]
    }

    @classmethod
    def extract(cls, url):

        response = requests.get(
            url,
            headers=cls.HEADERS,
            timeout=10
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # ----------------------------
        # 언론사별 Selector 적용
        # ----------------------------

        for domain, selectors in cls.SELECTORS.items():

            if domain in url:

                for selector in selectors:

                    article = soup.select_one(selector)

                    if article:

                        text = article.get_text("\n", strip=True)

                        if len(text) > 300:
                            return text

        # ----------------------------
        # article 태그
        # ----------------------------

        article = soup.find("article")

        if article:

            text = article.get_text("\n", strip=True)

            if len(text) > 300:
                return text

        # ----------------------------
        # 가장 긴 div
        # ----------------------------

        longest = ""

        for div in soup.find_all("div"):

            text = div.get_text(" ", strip=True)

            if len(text) > len(longest):
                longest = text

        if len(longest) < 300:
            raise Exception("기사 본문을 추출할 수 없습니다.")

        return longest
