import io
import os

import pytest
from werkzeug.datastructures import FileStorage

from backend.services.upload_service import UnsupportedFileType, save_upload

IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}


def _file(filename, content=b"data"):
    return FileStorage(stream=io.BytesIO(content), filename=filename)


def test_saves_inside_upload_folder(tmp_path):
    """정상 업로드는 지정한 폴더 안에 저장된다"""
    path = save_upload(_file("photo.jpg"), IMAGE_EXT, str(tmp_path))

    assert os.path.dirname(os.path.abspath(path)) == str(tmp_path)
    assert os.path.exists(path)


def test_traversal_filename_cannot_escape_upload_folder(tmp_path):
    """../ 가 포함된 파일명도 업로드 폴더를 벗어나지 못한다"""
    path = save_upload(_file("../../evil.jpg"), IMAGE_EXT, str(tmp_path))

    assert os.path.dirname(os.path.abspath(path)) == str(tmp_path)
    assert ".." not in os.path.basename(path)


def test_rejects_extension_outside_allowlist(tmp_path):
    """allowlist에 없는 확장자는 UnsupportedFileType을 던진다"""
    with pytest.raises(UnsupportedFileType):
        save_upload(_file("payload.php"), IMAGE_EXT, str(tmp_path))


def test_rejects_file_without_extension(tmp_path):
    """확장자가 없는 파일도 거부한다"""
    with pytest.raises(UnsupportedFileType):
        save_upload(_file("noext"), IMAGE_EXT, str(tmp_path))


def test_extension_check_is_case_insensitive(tmp_path):
    """대문자 확장자도 허용하고 소문자로 저장한다"""
    path = save_upload(_file("photo.JPG"), IMAGE_EXT, str(tmp_path))

    assert path.endswith(".jpg")


def test_same_filename_twice_does_not_overwrite(tmp_path):
    """같은 이름을 두 번 올려도 서로 덮어쓰지 않는다"""
    first = save_upload(_file("photo.jpg", b"first"), IMAGE_EXT, str(tmp_path))
    second = save_upload(_file("photo.jpg", b"second"), IMAGE_EXT, str(tmp_path))

    assert first != second
    assert os.path.exists(first) and os.path.exists(second)


def test_non_ascii_filename_keeps_extension(tmp_path):
    """한글 파일명이어도 확장자가 보존된다"""
    path = save_upload(_file("사진.png"), {"png"}, str(tmp_path))

    assert path.endswith(".png")
    assert os.path.exists(path)
