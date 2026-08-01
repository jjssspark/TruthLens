import os
import uuid

from werkzeug.utils import secure_filename


class UnsupportedFileType(ValueError):
    """확장자 allowlist에 없는 파일이 업로드된 경우"""


def save_upload(file, allowed_ext, upload_folder):
    """업로드 파일을 안전한 경로에 저장하고 저장 경로를 반환한다.

    확장자를 allowlist로 먼저 검증하므로 경로에 들어가는 확장자는
    allowlist에 있는 문자열로만 한정된다. 이름 부분은 secure_filename으로
    경로 구분자와 상위 참조를 제거하고, uuid 접두어로 동시 업로드 충돌을 막는다.
    """
    original = file.filename or ''
    stem, dot_ext = os.path.splitext(original)
    ext = dot_ext.lower().lstrip('.')

    if ext not in allowed_ext:
        raise UnsupportedFileType(
            f"지원하지 않는 파일 형식입니다: {dot_ext or '(확장자 없음)'}"
        )

    # 한글 등 비ASCII 이름은 secure_filename이 전부 제거할 수 있어 대체 이름을 둔다
    safe_stem = secure_filename(stem) or 'upload'
    save_path = os.path.join(upload_folder, f"{uuid.uuid4().hex}_{safe_stem}.{ext}")

    file.save(save_path)
    return save_path
