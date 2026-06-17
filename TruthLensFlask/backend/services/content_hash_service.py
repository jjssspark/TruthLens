import hashlib
from urllib.parse import urlparse, urlunparse


def hash_file(file_path):
    """파일 내용을 SHA-256으로 해시한다 (영상/이미지, FR-05)"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def hash_text_or_url(value):
    """텍스트 또는 정규화된 URL을 MD5로 해시한다 (FR-05)"""
    normalized = _normalize_url(value) if _looks_like_url(value) else value
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


def _looks_like_url(value):
    return value.startswith('http://') or value.startswith('https://')


def _normalize_url(url):
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=''))
