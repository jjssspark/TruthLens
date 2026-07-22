// TruthLens 공용 클라이언트 스크립트

const TruthLens = {
  /**
   * FormData를 업로드하고 진행률을 콜백으로 전달한다.
   * fetch()는 업로드 진행률 이벤트를 제공하지 않아 XMLHttpRequest를 사용한다.
   */
  uploadWithProgress(url, formData, { onProgress, onSuccess, onError } = {}) {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      let json;
      try {
        json = JSON.parse(xhr.responseText);
      } catch (err) {
        if (onError) onError({ message: '서버 응답을 해석할 수 없습니다.' });
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onSuccess) onSuccess(json);
      } else if (onError) {
        onError((json && json.data) || { message: '분석 요청에 실패했습니다.' });
      }
    });

    xhr.addEventListener('error', () => {
      if (onError) onError({ message: '네트워크 오류가 발생했습니다.' });
    });

    xhr.send(formData);
    return xhr;
  },

  /**
   * 버튼 아래에 진행률 바를 최초 1회 생성하고, 이후 호출부터는 너비만 갱신한다.
   */
  renderProgressBar(container, percent) {
    let wrap = container.querySelector('.tl-progress-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'tl-progress-wrap w-full h-1.5 bg-surface-container-high rounded-full overflow-hidden mt-3';
      const bar = document.createElement('div');
      bar.className = 'tl-progress-bar h-full bg-electric-blue transition-all duration-200';
      bar.style.width = '0%';
      wrap.appendChild(bar);
      container.appendChild(wrap);
    }
    wrap.querySelector('.tl-progress-bar').style.width = Math.min(Math.max(percent, 0), 100) + '%';
  },

  removeProgressBar(container) {
    const wrap = container.querySelector('.tl-progress-wrap');
    if (wrap) wrap.remove();
  },
};

window.TruthLens = TruthLens;
