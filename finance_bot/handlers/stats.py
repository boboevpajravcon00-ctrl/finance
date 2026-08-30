from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import settings
from database import get_expense_stats, get_expenses_by_period

router = Router()

def get_stats_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="exp_period_today"),
            InlineKeyboardButton(text="🗓 7 дней", callback_data="exp_period_week"),
            InlineKeyboardButton(text="📊 30 дней", callback_data="exp_period_month")
        ],
        [
            InlineKeyboardButton(text="📝 Список покупок детально", callback_data="exp_details_week")
        ]
    ])

@router.message(F.text.in_(["📊 Статистика", "/stats"]))
async def stats_handler(message: Message):
    await render_period_stats(message, user_id=message.from_user.id, period="month", is_callback=False)

@router.callback_query(F.data.startswith("exp_period_"))
async def change_period_callback(callback: CallbackQuery):
    period = callback.data.split("_")[2]
    await render_period_stats(callback, user_id=callback.from_user.id, period=period, is_callback=True)

async def render_period_stats(event: Message | CallbackQuery, user_id: int, period: str, is_callback: bool):
    days_map = {"today": 1, "week": 7, "month": 30}
    title_map = {"today": "ЗА СЕГОДНЯ", "week": "ЗА 7 ДНЕЙ", "month": "ЗА 30 ДНЕЙ"}
    
    days = days_map.get(period, 30)
    stats = await get_expense_stats(user_id, days=days)
    currency = settings.CURRENCY_SYMBOL

    if not stats:
        text = (
            f"📊 **АНАЛИТИКА РАСХОДОВ ({title_map.get(period)})**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "▫️ _За выбранный период расходов нет._"
        )
    else:
        total_expense = sum(s["total"] for s in stats)
        lines = [
            f"📊 **АНАЛИТИКА РАСХОДОВ ({title_map.get(period)})**",
            "━━━━━━━━━━━━━━━━━━━━━"
        ]
        for item in stats:
            pct = (item["total"] / total_expense * 100) if total_expense > 0 else 0
            bars = int(pct // 20)
            progress = "▰" * bars + "▱" * (5 - bars)
            lines.append(f"• **{item['category']}**: `{item['total']:,.2f} {currency}` ({pct:.0f}%) `[{progress}]`")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━",
            f"💸 **ВСЕГО:** `{total_expense:,.2f} {currency}`"
        ])
        text = "\n".join(lines)

    if is_callback:
        await event.message.edit_text(text, reply_markup=get_stats_period_kb(), parse_mode="Markdown")
        await event.answer()
    else:
        await event.answer(text, reply_markup=get_stats_period_kb(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("exp_details_"))
async def show_detailed_expenses_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    expenses = await get_expenses_by_period(user_id, period="week")
    currency = settings.CURRENCY_SYMBOL

    if not expenses:
        await callback.answer("Расходов за последнюю неделю не найдено.", show_alert=True)
        return

    lines = [
        "📝 **ДЕТАЛЬНЫЙ СПИСОК РАСХОДОВ (7 ДНЕЙ)**",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]
    for ex in expenses[:15]:
        acc = f" • _{ex['account_name']}_" if ex.get("account_name") else ""
        comm = f" ({ex['comment']})" if ex.get("comment") and ex['comment'] != "Расход" else ""
        date_str = ex["created_at"][:16]
        lines.append(f"• `{ex['amount']:,.2f} {currency}` | **{ex['category']}**{comm}{acc}\n   └ 🕒 _{date_str}_")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="exp_period_month")]
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=markup, parse_mode="Markdown")
    await callback.answer()