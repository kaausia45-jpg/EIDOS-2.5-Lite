import json
import asyncio
import os
import sympy
import aiohttp 

SCRIPT_DIR_GLOBAL = os.path.dirname(os.path.abspath(__file__))
SAFE_BASE_PATH = os.path.normpath(os.path.join(SCRIPT_DIR_GLOBAL, "eidos_files"))
if not os.path.exists(SAFE_BASE_PATH):
    os.makedirs(SAFE_BASE_PATH)
print(f"🔒 [Exec Module-Lite] 샌드박스 루트: {SAFE_BASE_PATH}")

async def run_search_placeholder(queries: list):
    await asyncio.sleep(0.5)
    query = queries[0] if queries else "unknown query"
    return json.dumps([{"results": [{"snippet": f"{query}에 대한 검색 결과 (시뮬레이션).", "source_title": "Simulated Site 1", "url": "#"}]}])

class _AsyncSearchPlaceholder:
    async def run(self, queries: list): return await run_search_placeholder(queries)

search = _AsyncSearchPlaceholder()
GOOGLE_SEARCH_ENABLED = False

try:
    from google.api.search_tool import GoogleSearchTool 
    search = GoogleSearchTool()
    GOOGLE_SEARCH_ENABLED = True
    print("✅ [Execution Module-Lite] '진짜' Google Search Tool 로드 성공.")
except ImportError:
    print("⚠️ [Execution Module-Lite] Google Search Tool을(를) 찾을 수 없습니다. Fallback 시뮬레이션 모드로 유지됩니다.")

AVAILABLE_TOOLS = {
    "perform_web_search": {
        "description": "최신 정보나 특정 주제에 대해 웹을 검색합니다. (예: '최신 AI 기술 동향')",
        "parameters": {"query": "str", "num_results": "int"}
    },
    "calculate_math": {
        "description": "정확한 수학 표현식(방정식, 미적분 등)을 계산합니다. (예: 'sqrt(16) * 2')",
        "parameters": {"expression": "str"}
    },
    "write_text": {
        "description": "주어진 프롬프트를 바탕으로 긴 글(보고서, 이메일, 코드 등)을 작성합니다. (LLM 호출)",
        "parameters": {"prompt": "str"}
    },
    "read_file": {
        "description": "지정된 경로의 파일 내용을 읽습니다. (경로: './eidos_files/' 내부)",
        "parameters": {"filepath": "str"}
    },
    "write_file": {
        "description": "지정된 경로에 텍스트 내용을 저장합니다. (경로: './eidos_files/' 내부)",
        "parameters": {"filepath": "str", "content": "str"}
    },
    "write_project_files_async": {
        "description": "여러 파일을 프로젝트 구조로 일괄 저장합니다. (경로: './eidos_files/' 내부)",
        "parameters": {"file_structure": "dict"} 
    }
}

async def perform_web_search(query: str, num_results: int = 3) -> str:
    """ [Lite] 웹 검색을 수행하고 '원본 스니펫'을 반환합니다. (LLM 요약 제거) """
    print(f"  🔎 [Exec-Lite] 웹 검색: '{query}'")
    
    try:
        if GOOGLE_SEARCH_ENABLED:
            search_response = await asyncio.to_thread(search.run, queries=[query])
        else:
            search_response = await search.run(queries=[query]) # 비동기 폴백
            
        snippets = []
        results_list = json.loads(search_response)
        if isinstance(results_list, list) and len(results_list) > 0:
             search_results = results_list[0].get('results', [])
             for i, result in enumerate(search_results[:num_results]):
                 snippet = result.get('snippet', '내용 없음').strip()
                 title = result.get('source_title', '출처 없음').strip()
                 snippets.append(f"[{i+1}] 출처: {title}\n내용: {snippet}\n")

        if not snippets:
            return f"'{query}'에 대한 유효한 검색 결과가 없습니다."

        # [Lite] LLM 요약 로직 제거. 원본 스니펫을 바로 반환.
        combined_snippets = "\n".join(snippets)
        return combined_snippets

    except Exception as e:
        return f"'{query}' 검색 중 오류 발생: {e}"

async def write_text(prompt: str) -> str:
    """
    [Lite] 이 함수는 Core에 의해 가로채어질 것입니다.
    Core는 이 prompt를 lite_llm_module.get_llm_response_async로 전달합니다.
    """
    print(f"  ✍️ [Exec-Lite] 글 작성 요청 (Core가 처리해야 함): '{prompt[:50]}...'")
    # 이 함수는 Core의 _execute_task에서 직접 호출되지 않고,
    # Core가 'write_text' 도구 이름을 감지하고 LLM을 대신 호출합니다.
    # 만약 이 함수가 직접 호출된다면(잘못된 설계), LLM 모듈을 임포트해야 합니다.
    # 여기서는 Core가 중개한다고 가정하고, 프롬프트 자체를 반환합니다. (Core가 처리하도록)
    return f"[TOOL_PASSTHROUGH] {prompt}"

def _get_safe_path(filepath: str) -> str:
    """ (HELPER) 경로를 검증하고 샌드박스 내부의 절대 경로를 반환합니다. """
    if os.path.isabs(filepath):
        target_path = os.path.normpath(filepath)
    else:
        target_path = os.path.normpath(os.path.join(SAFE_BASE_PATH, filepath))

    real_target = os.path.realpath(target_path)
    real_base = os.path.realpath(SAFE_BASE_PATH)
    
    if not real_target.startswith(real_base):
        raise PermissionError(f"Security Error: '{real_target}'이(가) 샌드박스 '{real_base}' 외부에 있습니다.")
    return target_path

async def read_file(**kwargs) -> str:
    filepath = kwargs.get('filepath', kwargs.get('path'))
    if filepath is None:
        return "파일 읽기 실패: 'filepath' 인수가 필요합니다."
    
    print(f"  📄 [Exec-Lite] 파일 읽기: '{filepath}'")
    try:
        target_path = _get_safe_path(filepath)

        def sync_read():
            if not os.path.exists(target_path):
                 raise FileNotFoundError(f"File not found: '{filepath}'")
            with open(target_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content

        content = await asyncio.to_thread(sync_read)
        return f"파일 '{filepath}' 내용:\n{content}"
    except Exception as e:
        return f"파일 '{filepath}' 읽기 실패: {e}"

async def write_file(**kwargs) -> str:
    filepath = kwargs.get('filepath', kwargs.get('path'))
    content = kwargs.get('content')
    if filepath is None or content is None:
        return "파일 쓰기 실패: 'filepath'와 'content' 인수가 필요합니다."

    print(f"  💾 [Exec-Lite] 파일 쓰기: '{filepath}'")
    try:
        target_path = _get_safe_path(filepath)

        def sync_write():
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content)

        await asyncio.to_thread(sync_write)
        return f"파일 '{filepath}'에 내용 저장을 완료했습니다."
    except Exception as e:
        return f"파일 '{filepath}' 쓰기 실패: {e}"

async def write_project_files_async(**kwargs) -> str:
    print(f"  💾 [Exec-Lite] 프로젝트 일괄 쓰기...")
    try:
        file_dict = kwargs.get('file_structure')
        if not isinstance(file_dict, dict):
            raise ValueError("'file_structure'가 딕셔너리가 아닙니다.")

        written_files = []

        def sync_write_all():
            for relative_path, content in file_dict.items():
                if not isinstance(content, str): continue
                
                # [Lite] Pro Lock 제거, _get_safe_path 헬퍼 사용
                target_path = _get_safe_path(relative_path)
                
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                written_files.append(relative_path)

        await asyncio.to_thread(sync_write_all)
        
        return json.dumps({
            "status": "success",
            "file_count": len(written_files),
            "files_written": written_files,
        })
    except Exception as e:
        return f"프로젝트 쓰기 실패: {e}"

async def calculate_math(expression: str) -> str:
    print(f"  🧮 [Exec-Lite] 수학 계산: '{expression}'")
    def sync_calculate():
        try:
            result_obj = sympy.sympify(expression)
            if hasattr(result_obj, 'doit'): result_obj = result_obj.doit()
            if hasattr(result_obj, 'evalf'): result_obj = result_obj.evalf()
            return f"계산 결과: {expression} = {str(result_obj)}"
        except Exception as e:
            return f"오류: '{expression}' 계산 중 오류 발생: {e}"

    return await asyncio.to_thread(sync_calculate)
