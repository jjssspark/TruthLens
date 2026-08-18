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
        // 상태 코드를 반드시 함께 보여준다. 이 문구만으로는 원인을 하나도 알 수
        // 없어서 같은 화면을 놓고 세 번(타임아웃/메모리/업로드 제한) 헤맸다.
        // 413이면 파일이 큰 것, 502·504면 앞단 프록시가 끊은 것이다.
        if (onError) onError({ message: `서버 응답을 해석할 수 없습니다. (HTTP ${xhr.status})` });
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onSuccess) onSuccess(json);
      } else if (onError) {
        // 실패 봉투는 data가 항상 null이고 메시지는 error에 담긴다(backend/api/response.py).
        // data를 읽으면 서버가 무슨 말을 하든 기본 문구로 뭉개져 원인을 알 수 없다.
        const err = json && json.error;
        if (!err) {
          onError({ message: '분석 요청에 실패했습니다.' });
        } else {
          // traceId를 함께 보여줘야 화면에 뜬 오류와 서버 로그를 연결할 수 있다.
          const trace = err.traceId ? ` (코드 ${err.traceId.slice(0, 8)})` : '';
          onError({ ...err, message: `${err.message}${trace}` });
        }
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

  /**
   * 전체 화면 분석 오버레이를 띄운다.
   *
   * 업로드 구간은 XHR이 주는 실제 진행률을 쓴다. 그 뒤 판별 구간은 서버가
   * 진행률을 주지 않으므로 퍼센트를 만들어내지 않는다. 대신 실제 파이프라인
   * 단계명을 순서대로 보여주고, 마지막 단계는 응답이 올 때까지 켜둔 채
   * 실제 경과 시간을 센다. 없는 정보를 있는 척하지 않는다.
   *
   * @param {{title?: string, previewUrl?: string|null, icon?: string, stages: string[]}} options
   * @returns {{setUploadPercent: (n:number)=>void, startAnalysis: ()=>void, close: ()=>void}}
   */
  showAnalysisOverlay({ title = '분석 중', previewUrl = null, icon = 'radar', stages = [] } = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'nx-scan-overlay';
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-live', 'polite');
    overlay.setAttribute('aria-label', title);

    const visual = previewUrl
      ? `<img src="${previewUrl}" alt="">`
      : `<div class="nx-scan-core"><span class="material-symbols-outlined" style="font-size:60px">${icon}</span></div>`;

    overlay.innerHTML = `
      <div class="nx-scan-panel">
        <div class="nx-scan-viewport">
          ${visual}
          <div class="nx-scan-grid"></div>
          <div class="nx-scan-beam"></div>
          <span class="nx-scan-bracket nx-scan-bracket--tl"></span>
          <span class="nx-scan-bracket nx-scan-bracket--tr"></span>
          <span class="nx-scan-bracket nx-scan-bracket--bl"></span>
          <span class="nx-scan-bracket nx-scan-bracket--br"></span>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;gap:6px">
          <p class="nx-scan-title"></p>
          <span class="nx-scan-elapsed">경과 0.0초</span>
        </div>
        <div class="nx-scan-progress"><div class="nx-scan-progress-bar"></div></div>
        <ul class="nx-scan-stages">
          ${stages.map((s) => `<li class="nx-scan-stage"><span class="nx-scan-stage-dot"></span><span>${s}</span></li>`).join('')}
        </ul>
        <p class="nx-scan-note">창을 닫지 마세요. 결과가 준비되면 자동으로 이동합니다.</p>
      </div>`;

    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    requestAnimationFrame(() => overlay.setAttribute('data-open', 'true'));

    const titleEl = overlay.querySelector('.nx-scan-title');
    const elapsedEl = overlay.querySelector('.nx-scan-elapsed');
    const progressEl = overlay.querySelector('.nx-scan-progress');
    const barEl = overlay.querySelector('.nx-scan-progress-bar');
    const stageEls = Array.from(overlay.querySelectorAll('.nx-scan-stage'));

    titleEl.textContent = '업로드 중';

    const startedAt = Date.now();
    const timer = setInterval(() => {
      elapsedEl.textContent = `경과 ${((Date.now() - startedAt) / 1000).toFixed(1)}초`;
    }, 100);

    let stageIndex = -1;
    let stageTimer = null;

    const activate = (index) => {
      stageIndex = index;
      stageEls.forEach((el, i) => {
        el.dataset.state = i < index ? 'done' : i === index ? 'active' : '';
      });
    };

    return {
      setUploadPercent(percent) {
        barEl.style.width = `${Math.min(Math.max(percent, 0), 100)}%`;
      },

      /** 업로드 완료 → 판별 구간. 앞 단계는 실제로 빠르게 끝나므로 순차 점등하고,
       *  마지막(모델 판정) 단계에 머문 채 응답을 기다린다. */
      startAnalysis() {
        titleEl.textContent = title;
        progressEl.hidden = true;
        activate(0);
        stageTimer = setInterval(() => {
          if (stageIndex >= stageEls.length - 1) {
            clearInterval(stageTimer);
            stageTimer = null;
            return;
          }
          activate(stageIndex + 1);
        }, 700);
      },

      close() {
        clearInterval(timer);
        if (stageTimer) clearInterval(stageTimer);
        overlay.removeAttribute('data-open');
        document.body.style.overflow = '';
        setTimeout(() => overlay.remove(), 220);
      },
    };
  },
};

window.TruthLens = TruthLens;
