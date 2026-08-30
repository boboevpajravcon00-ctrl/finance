import json
import logging
import asyncio
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from google.genai.errors import ClientError, APIError
from config import settings

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GEMINI_API_KEY)

# Пул моделей с приоритетом на Pro для глубокого анализа и Flash для скорости
MODELS_POOL = [
    "gemini-2.5-pro",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash"
]

class OperationItem(BaseModel):
    action: str = Field(default="transaction")
    type: str = Field(default="expense")
    amount: float = Field(default=0.0)
    category: str = Field(default="Разное")
    account_name: Optional[str] = None
    comment: Optional[str] = None
    person_name: Optional[str] = None

class GeminiFinanceResponse(BaseModel):
    is_finance_entry: bool = False
    conversational_reply: Optional[str] = None
    operations: List[OperationItem] = Field(default_factory=list)

SYSTEM_PROMPT = """
Ты — личный финансовый консультант и ассистент по учету бюджета.
Определи намерение пользователя:

1. ФИНАНСОВАЯ ОПЕРАЦИЯ (трата, доход, долг, пополнение):
- is_finance_entry = true
- conversational_reply = null
- operations: заполнить список операций:
  * "40 такси" -> action: "transaction", type: "expense", amount: 40.0, category: "Транспорт", comment: "такси"
  * "дал 100 Али в долг" -> action: "debt", type: "debt_given", amount: 100.0, person_name: "Али", category: "Долг"
  * "взял 50 у Вали" -> action: "debt", type: "debt_received", amount: 50.0, person_name: "Вали", category: "Долг"
  * "пополнил ДС на 300" -> action: "transaction", type: "income", amount: 300.0, category: "Пополнение", account_name: "ДС"

2. ВОПРОС / РАЗГОВОР / СОВЕТ (например: "как накопить на BMW M5?", "привет"):
- is_finance_entry = false
- operations = []
- conversational_reply: подробный финансовый совет, расчеты и правила бюджета.

Верни СТРОГО чистый JSON:
{
  "is_finance_entry": false,
  "conversational_reply": "Текст ответа",
  "operations": []
}
"""

def fallback_local_parse(text: str, accounts_names: Optional[List[str]] = None) -> Optional[GeminiFinanceResponse]:
    clean_text = text.lower().strip()
    num_match = re.search(r'\b\d+(?:[.,]\d+)?\b', text)
    if not num_match:
        return None

    amount = float(num_match.group().replace(',', '.'))
    matched_acc = None
    if accounts_names:
        for acc in accounts_names:
            if acc.lower() in clean_text:
                matched_acc = acc
                break

    is_income = any(w in clean_text for w in ["пополнил", "доход", "зарплата", "пришло", "+"])
    is_debt = any(w in clean_text for w in ["долг", "в долг", "занял", "одолжил", "вернул долг"])

    if is_debt:
        words = [w for w in text.split() if not re.match(r'^\d', w) and w.lower() not in ["долг", "в", "дал", "взял", "отдал", "вернул"]]
        person = words[0] if words else "Знакомый"
        debt_type = "debt_received" if any(w in clean_text for w in ["взял", "занял"]) else "debt_given"
        return GeminiFinanceResponse(
            is_finance_entry=True,
            operations=[OperationItem(
                action="debt",
                type=debt_type,
                amount=amount,
                category="Долг",
                person_name=person,
                comment=text
            )]
        )

    category = "Разное"
    if any(w in clean_text for w in ["такси", "дорог", "проезд", "бензин"]):
        category = "Транспорт"
    elif any(w in clean_text for w in ["еда", "магазин", "обед", "ужин", "кафе", "ресторан", "продукты", "кофе"]):
        category = "Продукты и еда"
    elif any(w in clean_text for w in ["аптека", "лекарств", "врач"]):
        category = "Здоровье"

    op_type = "income" if is_income else "expense"
    category = "Пополнение" if is_income else category

    return GeminiFinanceResponse(
        is_finance_entry=True,
        operations=[OperationItem(
            action="transaction",
            type=op_type,
            amount=amount,
            category=category,
            account_name=matched_acc,
            comment=text
        )]
    )

async def parse_text_with_gemini(text: str, accounts_names: Optional[List[str]] = None) -> GeminiFinanceResponse:
    acc_info = f"Доступные счета: {', '.join(accounts_names)}\n" if accounts_names else ""
    prompt = f"{acc_info}Сообщение: {text}"

    for model_name in MODELS_POOL:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)

            if "operations" not in data or data["operations"] is None:
                data["operations"] = []
            if "is_finance_entry" not in data:
                data["is_finance_entry"] = bool(data["operations"])

            return GeminiFinanceResponse.model_validate(data)

        except ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.warning(f"Модель {model_name} занята. Переключаемся на следующую...")
                await asyncio.sleep(0.5)
                continue
            logger.error(f"Ошибка модели {model_name}: {e}")
        except Exception as e:
            logger.error(f"Ошибка {model_name}: {e}")

    local_result = fallback_local_parse(text, accounts_names)
    if local_result:
        return local_result

    return GeminiFinanceResponse(
        is_finance_entry=False,
        conversational_reply="⏳ Квота запросов временно исчерпана. Попробуйте снова через 10-15 секунд.",
        operations=[]
    )

async def parse_audio_with_gemini(audio_bytes: bytes, accounts_names: Optional[List[str]] = None, mime_type: str = "audio/ogg") -> GeminiFinanceResponse:
    acc_info = f" Доступные счета: {', '.join(accounts_names)}." if accounts_names else ""
    instruction = f"Распознай аудиозапись и извлеки финансовую операцию в формате JSON.{acc_info}"

    for model_name in MODELS_POOL:
        try:
            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[audio_part, instruction],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
            if "operations" not in data or data["operations"] is None:
                data["operations"] = []
            return GeminiFinanceResponse.model_validate(data)
        except Exception:
            continue

    return GeminiFinanceResponse(
        is_finance_entry=False,
        conversational_reply="⚠️ Голосовое сообщение не удалось распознать.",
        operations=[]
    )