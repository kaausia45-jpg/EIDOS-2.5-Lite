import google.generativeai as genai
import asyncio
import json
from config import GEMINI_API_KEY
from typing import Optional, Dict, List

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro')
except Exception as e:
    print(f"❌ Gemini API 설정 중 오류 발생: {e}")
    model = None

async def get_llm_response_async(prompt: str, response_mime_type: Optional[str] = None) -> str:
    """ [Lite] Gemini API를 호출하는 기본 래퍼 함수 """
    if not model:
        return "[LLM 설정 오류: API 키 또는 모델 초기화 실패]"
    
    try:
        generation_config = None
        if response_mime_type == "application/json":
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=32768
            )
        
        response = await asyncio.to_thread(
            model.generate_content, 
            prompt, 
            generation_config=generation_config
        )

        if hasattr(response, 'text'):
            return response.text
        else:
             if response.prompt_feedback.block_reason:
                 reason = response.prompt_feedback.block_reason
                 return f"[LLM 응답 차단됨: {reason}]"
             return "[LLM 응답 오류: 알 수 없는 형식]"

    except Exception as e:
        print(f"❌ [LLM Async] API 호출 중 예외 발생: {e}")
        return f"LLM API 호출 실패: {type(e).__name__} - {e}"

async def generate_tool_use_plan_async(
    user_input: str, 
    chat_history: List[str], 
    available_tools_str: str
) -> str:
    """
    [EIDOS-Lite의 두뇌] 사용자 입력과 도구 목록을 받아 '도구 사용 계획(JSON)'을 생성합니다.
    """
    history_str = "\n".join(chat_history[-10:])

    prompt = f"""
    당신은 사용자 요청을 '도구 사용 계획'으로 변환하는 AI 플래너입니다.
    사용자 요청이 단순 대화('안녕', '고마워')라면 "CHAT"라고만 응답하세요.
    그렇지 않다면, 사용 가능한 도구를 활용하여 JSON 계획을 생성하세요.

    [사용 가능한 도구]
    {available_tools_str}

    [최근 대화]
    {history_str}

    [사용자 요청]
    "{user_input}"

    [규칙]
    1.  사용자 요청이 단순 대화(인사, 감정표현)면, 다른 텍스트 없이 "CHAT"라고만 응답합니다.
    2.  파일 경로는 항상 './eidos_files/'로 시작해야 합니다.
    3.  `write_project_files_async`의 코드 내용은 `\\n`과 `\\"`로 이스케이프해야 합니다.
    4.  'Plan'은 JSON 리스트 형식이어야 합니다.

    [JSON 계획 (또는 "CHAT")]
    """
    return await get_llm_response_async(prompt, response_mime_type="application/json")

async def generate_modification_suggestion_async(current_code: str, chat_history: List[str]) -> str:
    """ (Lite) 코드 편집기용 AI 추천 생성기 (기존과 동일) """
    if not model: return "LLM 오류"
    history_str = "\n".join(chat_history[-10:])
    prompt = f"""
    AI 코드 리뷰어입니다. 사용자가 다음에 수행할 만한 '가장 논리적인 작업 1가지'를 '매우 짧게' 추천하세요.
    (10단어 이내 한국어, "..."으로 끝, 다른 설명 금지)
    [최근 대화]
    {history_str}
    [현재 코드]
    {current_code[:2000]}...
    [추천 작업]
    """
    try:
        response_text = await get_llm_response_async(prompt)
        return response_text.strip().replace('"', '')
    except Exception as e:
        return f"추천 생성 실패: {e}"

async def modify_code_async(current_code: str, 
                            user_request: str, 
                            new_file_name: Optional[str] = None,
                            relevant_chunks: Optional[str] = None) -> str:
    """ (Lite) 코드 편집기용 AI 코드 수정기 (기존과 동일, RAG/Fallback 로직 포함) """
    if not model:
        return json.dumps({"filepath": "CURRENT", "code": "[LLM 오류]"})

    target_file_instruction = ""
    if new_file_name and new_file_name.strip():
        new_file_name = new_file_name.strip().replace(" ", "_")
        target_file_instruction = f"[지시] [현재 코드]에서 '{user_request}'에 해당하는 부분을 분리하여, 새 파일 '{new_file_name}'에 들어갈 '새로운 코드'만 생성합니다."
        target_filepath_for_json = new_file_name
    else:
        target_file_instruction = "[지시] [현재 코드]를 [사용자 요청]에 맞게 '수정'하고, '수정된 전체 코드'를 반환합니다."
        target_filepath_for_json = "CURRENT"

    MAX_CODE_LENGTH = 8000
    prompt_code_label = "[현재 코드]"
    code_context = current_code
    reconstruction_instruction = ""

    if relevant_chunks and relevant_chunks.strip():
        prompt_code_label = "[관련 코드 조각 (RAG)]"
        code_context = relevant_chunks
        reconstruction_instruction = "[RAG 지시] [관련 코드 조각]은 원본 코드의 일부입니다. 이 조각들을 참고하여 [현재 코드]의 '전체'를 수정/복원해야 합니다."
    elif len(current_code) > MAX_CODE_LENGTH:
        print(f"❌ [LLM CodeModify] RAG 실패 및 코드가 너무 깁니다 ({len(current_code)}자). LLM 호출을 중단합니다.")
        return json.dumps({
            "filepath": "CURRENT",
            "code": f"[LLM 오류: 코드 손상 방지]\n파일이 너무 커서({len(current_code)}자) RAG 검색 없이는 안전하게 수정할 수 없습니다.\n{current_code}"
        })
    
    prompt = f"""
    AI 코드 어시스턴트입니다. '반드시' [JSON 스키마]에 맞춰 응답하세요.
    {target_file_instruction}
    {reconstruction_instruction}

    {prompt_code_label}
    {code_context}

    [사용자 요청]
    "{user_request}"

    [JSON 스키마 (필수)]
    {{
      "filepath": "{target_filepath_for_json}",
      "code": "[여기에 '수정된 전체 코드' 또는 '새 코드'를 작성]"
    }}

    [JSON 응답]
    """
    try:
        response_text = await get_llm_response_async(prompt, response_mime_type="application/json")
        try:
            parsed_dict = json.loads(response_text)
            return json.dumps(parsed_dict)
        except json.JSONDecodeError:
            return json.dumps({"filepath": "CURRENT", "code": response_text.strip()})
    except Exception as e:
        return json.dumps({"filepath": "CURRENT", "code": f"[LLM 오류: {e}]\n\n{current_code}"})
