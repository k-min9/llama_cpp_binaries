# llama_cpp_binaries

[ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) **원본에서 직접** 빌드한 `llama-server` 바이너리 휠 (Windows 전용).
[oobabooga/llama-cpp-binaries](https://github.com/oobabooga/llama-cpp-binaries) 의존을 끊기 위한 자체 저장소 — oobabooga 코드는 한 줄도 쓰지 않는다(클린룸, 원본 llama.cpp는 MIT). 패키지명이 동일해 **드롭인 교체**(소비 측 import 무수정).

새 모델 아키텍처("unknown model architecture")가 나오면 남을 기다리지 않고 즉시 새 휠을 만들 수 있다.

## 배포 (기본 경로 — GitHub Actions, 로컬 PC 불필요)

Actions 탭 → `build-llama-wheel` → **Run workflow** → llama.cpp b태그 입력 (예: `b10423`).

- 러너가 CUDA 툴킷 설치 → 크로스 컴파일 → 휠 검증(설치+import+`--version` 기동) → 같은 b태그로 Release 생성+휠 첨부까지 완결
- 서브모듈도 커밋도 불필요 — 태그 입력이 곧 릴리스. GPU 아키텍처는 감지 없이 고정 리스트(`61;70;75;80;86;89;120` = Pascal~RTX50)로 컴파일
- 소요 1.5~3시간, 사람 조작은 태그 입력 ~1분 (무료 조건 = Public 저장소)

설치(소비 측):

```
pip install https://github.com/<계정>/llama_cpp_binaries/releases/download/b10423/llama_cpp_binaries-10423+cu128-py3-none-win_amd64.whl
```

## 버전 정책 — llama.cpp 상류 버전 정렬

휠 버전 = b태그의 빌드 번호 그대로 (`b10423` → `10423`, 단조 증가라 pip 버전 비교도 자연스럽다). b#### 형식이 아닌 ref면 날짜 버전(YYYY.M.D) 폴백. CUDA 변형은 로컬 태그(`+cu128` — nvcc에서 자동 감지 / `+cpu`)로 기록 — **휠 파일명만으로 "어느 llama.cpp + 어느 CUDA"인지 식별된다.**

## 로컬 빌드 (선택 — MSVC + CUDA Toolkit, "x64 Native Tools Command Prompt for VS 2022"에서)

CMake/Ninja는 pip 빌드 격리환경에 자동 조달되므로 시스템 설치 불요 — 필요한 것은 MSVC(cl)와 CUDA Toolkit(nvcc)뿐. 제너레이터는 Ninja 고정(VS 제너레이터는 CUDA VS 통합 요구로 CI에서 실패).

```
python build_llama_wheel.py                    # 기본 태그, CUDA, 고정 아키텍처 리스트
python build_llama_wheel.py --tag b10423       # 태그 지정
python build_llama_wheel.py --cuda-archs "86"  # 아키텍처 축소 (빌드 시간 단축)
python build_llama_wheel.py --cpu              # CPU 전용 휠 (nvcc 불필요)
```

산출: `dist/llama_cpp_binaries-10423+cu128-py3-none-win_amd64.whl`

## 구조

| 파일 | 역할 |
|---|---|
| `build_llama_wheel.py` | 오케스트레이터 — llama.cpp 태그 고정 클론(`work/`) → `pip wheel` → 산출 휠 검증 |
| `setup.py` | 핵심 빌드 로직 — build_ext를 가로채 CMake 실행, 산출물+CUDA 런타임 DLL을 `bin/`에 복사, `py3-none` 태그 강제 |
| `pyproject.toml` | 패키지 메타데이터 — 빌드 격리환경에 cmake 자동 조달 |
| `llama_cpp_binaries/__init__.py` | `get_binary_path()` 1개 — 파이썬 인터페이스 전부 |
| `.github/workflows/build_wheel.yml` | 태그 입력 → 빌드 → Release 업로드 |

## 포인트

- **파이썬 버전 무관** (`py3-none-win_amd64`) — 휠 내용물이 llama-server.exe + DLL + 경로 함수 1개뿐이라 libpython 링크가 없다. 휠 1개가 3.10 venv에도 3.12에도 그대로 설치된다.
- **CUDA 런타임 DLL 3종**(cudart/cublas/cublasLt) 동봉 — CUDA 툴킷 없는 사용자 PC에서 기동하기 위한 필수 조건. 빌드 스크립트가 휠 내용을 검증한다.
- **CPU-only PC에서도 동작** — `GGML_BACKEND_DL` + CPU 변형 DLL 동봉으로 GPU/드라이버가 없으면 CPU 백엔드로 폴백한다.
- 참고: llama.cpp 공식 Releases에도 Windows CUDA zip(+cudart zip)이 태그마다 올라온다. 컴파일 없이 그 zip을 휠로 재포장하는 고속 경로도 가능하나(수 분), CUDA 버전·아키텍처·빌드 옵션이 공식 빌드 설정에 묶인다 — 필요해지면 이 저장소에 재포장 워크플로우를 추가한다.

## oobabooga 대비 — 장점 흡수 체크리스트 (2026-08-14, 그들의 build-wheels-cuda.yml 실사 기준)

| oobabooga의 장점 | 우리 빌드 |
|---|---|
| pip 휠 + `get_binary_path()` 드롭인 | ✅ 동일 (패키지명까지 동일) |
| CUDA 런타임 동봉 (자급자족 휠) | ✅ 동일 (cudart/cublas/cublasLt) |
| `GGML_NATIVE=off` (빌드머신 과최적화 방지) | ✅ 채택 |
| `GGML_BACKEND_DL=on` + `GGML_CPU_ALL_VARIANTS=on` (CPU 세대별 최적 커널 + CUDA 불가 시 완전 폴백) | ✅ 채택 |
| 넓은 GPU 커버리지 (구형 포함) | ✅ 채택 — `61;70;75;80;86;89;120` (Pascal~RTX50) |
| 버전 식별 | ✅ 우리가 우위 — 자체 카운터(v0.138.0) 대신 상류 b태그 번호 그대로 |
| 공급망 | ✅ 우리가 우위 — 그들은 자기 fork(빌드 인프라 패치) 빌드, 우리는 upstream 직빌드 |
| ik_llama.cpp 엔진 (별도 fork, 특수 양자화) | ❌ 의도적 제외 — 본체 미사용 |
| Vulkan/ROCm/macOS/Linux 변형 | ❌ 의도적 제외 — Windows+NVIDIA/CPU가 대상. AMD GPU 지원이 필요해지면 Vulkan 워크플로우 1개 추가로 흡수 가능 |
| `GGML_RPC` / BoringSSL | ❌ 의도적 제외 — 본체는 로컬 HTTP만 사용 |
| 구형 CUDA 라인(cu124) 병행 | ❌ 단일 cu128 — 구형 드라이버 대응이 필요하면 워크플로우의 Jimver `cuda:` 값만 바꿔 재실행 |

## 검증 체크리스트

- [x] 오케스트레이터 문법 / prereq 가드 / PEP 517 배선 (2026-08-14, CUDA 없는 PC에서 확인)
- [ ] Actions 첫 실빌드 (워크플로우가 설치+import+`--version` 기동까지 자동 확인)
- [ ] 본 프로젝트(MY-Little-Jarvis-Plus) 소비 URL 교체 — requirements.txt / requirements_fix.txt / README의 oobabooga URL 3곳
