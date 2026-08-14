# llama_cpp_binaries

[ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)의 `llama-server`를 빌드해 파이썬 휠로 배포하는 저장소 (Windows x64).

## 설치

```
pip install https://github.com/k-min9/llama_cpp_binaries/releases/download/b10423/llama_cpp_binaries-10423+cu128-py3-none-win_amd64.whl
```

## 사용

```python
import llama_cpp_binaries

exe = llama_cpp_binaries.get_binary_path()  # llama-server.exe 절대경로
```

exe를 subprocess로 기동하고 HTTP(`/completion`, `/health` 등 llama-server 표준 API)로 통신한다.

## 휠 사양

- 휠 태그 `py3-none-win_amd64` — 내용물이 exe+DLL뿐(libpython 링크 없음)이라 파이썬 3.9+ 어디에나 설치된다
- 휠 버전 = llama.cpp 릴리스 태그의 빌드 번호 (`b10423` → `10423`). CUDA 변형은 로컬 태그(`+cu128` / `+cpu`)
- CUDA 런타임 DLL(cudart/cublas/cublasLt) 동봉 — 사용자 PC에 CUDA Toolkit 설치 불필요
- GPU/드라이버가 없으면 CPU 백엔드로 폴백 — CPU 세대별 커널 DLL 동봉
- CUDA 아키텍처: `61;70;75;80;86;89;120` (Pascal~RTX50)

## 릴리스

GitHub Actions(workflow_dispatch)로 빌드부터 Release 업로드까지 수행한다. 새 모델 아키텍처 에러(`unknown model architecture`)가 나오면 새로 릴리스한다.

1. Actions 탭 → `build-llama-wheel` 선택
2. **Run workflow** 클릭 — 입력칸은 기본값 그대로 둔다
   - tag를 비워두면 llama.cpp 최신 릴리스 태그가 자동 조회된다. 과거 버전 재현 시에만 `b####` 입력
   - 소요 1.5~3시간 (멀티 아키텍처 컴파일)
