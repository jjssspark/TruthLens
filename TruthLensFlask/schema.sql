-- TruthLens 데이터베이스 스키마 (MariaDB 11.x)
-- 실행 전: CREATE DATABASE truthlens CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ────────────────────────────────────────────
-- 1. users
--    mypage.html 기준 필드, 로그인/회원가입 화면(FR-미정) 대응
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  INT             NOT NULL AUTO_INCREMENT,
    email               VARCHAR(255)    NOT NULL,
    password_hash       VARCHAR(255)    NULL,
    google_sub          VARCHAR(100)    NULL                       COMMENT 'Google OAuth 고유 ID',
    name                VARCHAR(100)    NOT NULL,
    role                VARCHAR(30)     NOT NULL DEFAULT 'free'   COMMENT 'free | pro | enterprise | admin',
    trust_score         FLOAT           NOT NULL DEFAULT 0.0      COMMENT '신뢰 점수 (%)',
    scan_count          INT             NOT NULL DEFAULT 0         COMMENT '총 판별 요청 수',
    accuracy            FLOAT           NOT NULL DEFAULT 0.0      COMMENT '판별 정확도 (%)',
    next_payment_date   DATE            NULL                       COMMENT '구독 다음 결제일',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at       DATETIME        NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ────────────────────────────────────────────
-- 2. detection_requests
--    판별 요청 이력 (DetectionRequest 모델)
--    user_id: auth 구현 전까지 NULL 허용
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS detection_requests (
    id              INT             NOT NULL AUTO_INCREMENT,
    user_id         INT             NULL                       COMMENT 'NULL = 비로그인 요청',
    content_hash    VARCHAR(64)     NOT NULL                   COMMENT 'SHA-256(파일) 또는 MD5(URL/텍스트)',
    type            VARCHAR(20)     NOT NULL                   COMMENT 'video | image | news | paper',
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending' COMMENT 'pending | processing | done | failed',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_detection_requests_content_hash (content_hash),
    KEY idx_detection_requests_user_id (user_id),
    CONSTRAINT fk_dr_user_id
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ────────────────────────────────────────────
-- 3. detection_results
--    판별 결과 (DetectionResult 모델)
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS detection_results (
    id              INT             NOT NULL AUTO_INCREMENT,
    request_id      INT             NOT NULL,
    score           FLOAT           NOT NULL                   COMMENT 'AI 생성 가능성 신뢰 점수 (0~100)',
    detail_json     JSON            NULL                       COMMENT '도메인별 세부 분석 결과',
    cached          TINYINT(1)      NOT NULL DEFAULT 0         COMMENT '1 = Redis 캐시 히트 결과 (FR-05)',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_results_request_id
        FOREIGN KEY (request_id) REFERENCES detection_requests (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ────────────────────────────────────────────
-- 4. paper_citations
--    논문 인용 분석 결과 (PaperCitation 모델, FR-04)
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_citations (
    id              INT             NOT NULL AUTO_INCREMENT,
    request_id      INT             NOT NULL,
    citation_ref    VARCHAR(255)    NOT NULL                   COMMENT '예: [1], (Smith, 2020)',
    status          VARCHAR(20)     NOT NULL DEFAULT 'matched' COMMENT 'matched | missing',
    doi             VARCHAR(100)    NULL,
    title           VARCHAR(500)    NULL,
    PRIMARY KEY (id),
    KEY idx_paper_citations_request_id (request_id),
    CONSTRAINT fk_citations_request_id
        FOREIGN KEY (request_id) REFERENCES detection_requests (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ────────────────────────────────────────────
-- 5. content_stats
--    콘텐츠별 요청 통계 (ContentStats 모델, FR-05)
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_stats (
    content_hash        VARCHAR(64)     NOT NULL,
    request_count       INT             NOT NULL DEFAULT 0,
    last_requested_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ────────────────────────────────────────────
-- 6. cache_metadata
--    캐시 활성화 이력 (CacheMetadata 모델, FR-05)
-- ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cache_metadata (
    content_hash    VARCHAR(64)     NOT NULL,
    ttl             INT             NOT NULL DEFAULT 86400    COMMENT '캐시 TTL(초), 기본 24시간',
    hit_count       INT             NOT NULL DEFAULT 0,
    activated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
