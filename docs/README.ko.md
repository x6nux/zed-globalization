# Zed Globalization

[![GitHub stars][stars-image]][stars-url]
[![Github Downloads][download-image]][download-url]
[![license][license-image]][license-url]

[简体中文](../README.md)|[English](README.en.md)|[日本語](README.ja.md)|**한국어**

[Zed 편집기](https://github.com/zed-industries/zed) 다국어 현지화 도구 체인. AI 기반의 완전 자동 번역 및 빌드 파이프라인.

## 다운로드

[Releases](https://github.com/x6nux/zed-globalization/releases/latest)에서 빌드된 바이너리를 다운로드:

| 플랫폼 | 파일 | 설치 방법 |
|--------|------|----------|
| macOS (Apple Silicon) | `zed-globalization-zh-cn-macos-aarch64.dmg` | DMG 열고 Applications로 드래그 |
| Windows (x64) | `zed-globalization-zh-cn-windows-x86_64.zip` | 압축 해제 후 `zed.exe` 실행 |
| Linux (x64) | `zed-globalization-zh-cn-linux-x86_64.tar.gz` | `/usr/local`에 압축 해제 |
| Linux (x64 deb) | `zed-globalization-zh-cn-linux-x86_64.deb` | `sudo dpkg -i *.deb` |

**Windows Scoop:**

```bash
scoop bucket add zed-globalization https://github.com/x6nux/zed-globalization -b scoop
scoop install zed-globalization
```

## 특징

- AI 자동 스캔으로 번역 대상 Rust 소스 파일 식별
- 정규식 기반 문자열 추출 + 코드 컨텍스트 수집
- AI 동시 번역, 3단계 폴백 전략 (JSON -> XML CDATA -> 번호 형식)
- 소스 치환 3계층 보호 (필터링 + 구문 수정 + 보호 영역 건너뛰기)
- JSON <-> Excel 양방향 변환, 수동 검토 지원
- 크로스 플랫폼 빌드 (Windows / Linux / macOS), 앱 아이콘 포함
- GitHub Actions 완전 자동 파이프라인: 스캔 -> 번역 -> 빌드 -> 릴리스

## 자동화 파이프라인

```
03-scan (매일 정시)      Zed 신규 버전 감지, 번역 대상 문자열 추출
       |
04-translate             AI 동시 번역, i18n 브랜치에 푸시
       |
01-build                 3개 플랫폼 컴파일, Release 생성
       |
02-update-scoop          Scoop Manifest 업데이트
```

## 로컬 사용

### 설치

```bash
# 기본 (치환 기능만)
pip install .

# AI 번역 기능 포함
pip install ".[ai]"

# 전체 기능
pip install ".[all]"
```

### 단계별 실행

```bash
# 1. AI 스캔: 번역이 필요한 .rs 파일 식별
zedl10n scan --source-root zed

# 2. 문자열 추출
zedl10n extract --source-root zed --output string.json

# 3. AI 번역
zedl10n translate --input string.json --output i18n/zh-CN.json --mode full

# 4. 소스 치환
zedl10n replace --input i18n/zh-CN.json --source-root zed
```

### 원클릭 파이프라인

```bash
zedl10n pipeline --source-root zed --lang zh-CN --mode full
```

### 로컬 빌드

```bash
git clone https://github.com/zed-industries/zed.git
zedl10n replace --input i18n/zh-CN.json --source-root zed
cd zed && cargo build --release
```

## AI 설정

| 환경 변수 | CLI 옵션 | 설명 | 기본값 |
|----------|----------|------|-------|
| `AI_BASE_URL` | `--base-url` | API 엔드포인트 | `https://api.openai.com/v1` |
| `AI_API_KEY` | `--api-key` | API 키 | 필수 |
| `AI_MODEL` | `--model` | 모델 이름 | `gpt-4o-mini` |
| `AI_CONCURRENCY` | `--concurrency` | 동시성 | `5` |

OpenAI 호환 API 지원. 우선순위: CLI 옵션 > 환경 변수 > 기본값.

## 프로젝트 구조

```
zed-globalization/
├── .github/workflows/
│   ├── 01-build.yml        # 멀티 플랫폼 빌드 + 릴리스
│   ├── 02-update-scoop.yml # Scoop Manifest 업데이트
│   ├── 03-scan.yml         # 정시 스캔 + 문자열 추출
│   └── 04-translate.yml    # AI 번역
├── config/
│   └── glossary.yaml       # 번역 용어집
├── i18n/                   # 번역 파일 (zh-CN, ja, ko 등)
├── src/zedl10n/
│   ├── cli.py              # CLI 엔트리 (scan/extract/translate/replace/convert/pipeline)
│   ├── scan.py             # AI 스캔
│   ├── extract.py          # 정규식 추출 + 컨텍스트
│   ├── translate.py        # AI 동시 번역 (3단계 폴백)
│   ├── replace.py          # 소스 치환 (3계층 보호)
│   ├── convert.py          # JSON <-> Excel 변환
│   └── utils.py            # 공유 유틸리티 및 설정
└── pyproject.toml
```

## 치환 보호 메커니즘

소스 치환 시 Rust 컴파일 안전성을 보장하는 다층 메커니즘:

1. **번역 필터링**: 순수 ASCII 구두점 문자열을 건너뛰어 배열 구문 파괴 방지
2. **보호 영역**: 바이트 문자열(`b""`/`br#""#`)과 속성 매크로(`#[action(...)]`) 내 치환 건너뛰기
3. **따옴표 이스케이프**: 번역문의 쌍따옴표를 자동으로 `\"`로 이스케이프
4. **구문 수정**: 문자열 사이의 중국어 구두점을 ASCII 구두점으로 자동 복원

## 감사의 말

- [Zed](https://github.com/zed-industries/zed)
- [deevus/zed-windows-builds](https://github.com/deevus/zed-windows-builds)
- [Nriver/zed-translation](https://github.com/Nriver/zed-translation)

## 라이선스

[MIT](../LICENSE)

[stars-url]: https://github.com/x6nux/zed-globalization/stargazers
[stars-image]: https://img.shields.io/github/stars/x6nux/zed-globalization?style=flat-square&logo=github
[download-url]: https://github.com/x6nux/zed-globalization/releases/latest
[download-image]: https://img.shields.io/github/downloads/x6nux/zed-globalization/total?style=flat-square&logo=github
[license-url]: https://github.com/x6nux/zed-globalization/blob/main/LICENSE
[license-image]: https://img.shields.io/github/license/x6nux/zed-globalization?style=flat-square
