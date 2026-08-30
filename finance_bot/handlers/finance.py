from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database import (
    get_user_accounts, 
    add_account, 
    get_debts, 
    get_recent_transactions,
    set_account_balance
)

router = Router()

class AddAccountState(StatesGroup):
    waiting_for_name = State()
    waiting_for_balance = State()

class EditBalanceState(StatesGroup):
    waiting_for_new_balance = State()

def get_account_icon(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ["налич", "нал", "кэш"]): return "💵"
    if any(w in n for w in ["дс", "dc"]): return "📱"
    if any(w in n for w in ["alif", "алиф"]): return "🟢"
    if any(w in n for w in ["eskhata", "эсхата"]): return "🔴"
    if any(w in n for w in ["карт", "card"]): return "💳"
    return "🪙"

@router.message(F.text == "💳 Мои деньги")
@router.callback_query(F.data == "btn_refresh_balance")
async def show_balance_handler(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    accounts = await get_user_accounts(user_id)
    currency = settings.CURRENCY_SYMBOL

    if not accounts:
        text = (
            "💼 **МОИ СЧЕТА И АКТИВЫ**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "▫️ _У вас пока нет добавленных счетов._\n\n"
            "👇 Нажмите кнопку ниже, чтобы создать счет:"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать счет", callback_data="btn_add_account")]
        ])
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
            await event.answer()
        else:
            await event.answer(text, reply_markup=markup, parse_mode="Markdown")
        return

    total_balance = sum(acc["balance"] for acc in accounts)
    lines = [
        "💼 **МОИ СЧЕТА И АКТИВЫ**",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]

    for acc in accounts:
        icon = get_account_icon(acc["name"])
        balance = acc["balance"]
        percent = (balance / total_balance * 100) if total_balance > 0 else 0
        bars = int(percent // 20)
        progress = "▰" * bars + "▱" * (5 - bars)
        lines.append(f"{icon} **{acc['name']}**\n   └ 💰 `{balance:,.2f} {currency}` • _{percent:.0f}%_ `[{progress}]`")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━",
        f"💎 **ИТОГО КАПИТАЛ:**  `{total_balance:,.2f} {currency}`"
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить счет", callback_data="btn_add_account"),
            InlineKeyboardButton(text="⚙️ Изменить баланс", callback_data="btn_choose_edit_acc")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="btn_refresh_balance")
        ]
    ])

    if isinstance(event, CallbackQuery):
        await event.message.edit_text("\n".join(lines), reply_markup=markup, parse_mode="Markdown")
        await event.answer("Баланс обновлен 🔄")
    else:
        await event.answer("\n".join(lines), reply_markup=markup, parse_mode="Markdown")

# Меню выбора счета для изменения баланса
@router.callback_query(F.data == "btn_choose_edit_acc")
async def choose_account_to_edit(callback: CallbackQuery):
    accounts = await get_user_accounts(callback.from_user.id)
    if not accounts:
        await callback.answer("У вас нет счетов для редактирования.", show_alert=True)
        return

    buttons = []
    for acc in accounts:
        icon = get_account_icon(acc["name"])
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {acc['name']} (сейчас: {acc['balance']:,.2f} {settings.CURRENCY_SYMBOL})",
                callback_data=f"edit_bal_id_{acc['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="btn_refresh_balance")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("⚙️ **Выберите счет, баланс которого хотите изменить:**", reply_markup=markup, parse_mode="Markdown")
    await callback.answer()

# Запрос нового баланса для выбранного счета
@router.callback_query(F.data.startswith("edit_bal_id_"))
async def prompt_new_balance(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[3])
    accounts = await get_user_accounts(callback.from_user.id)
    acc = next((a for a in accounts if a["id"] == acc_id), None)
    
    if not acc:
        await callback.answer("Счет не найден.", show_alert=True)
        return

    await state.update_data(edit_account_id=acc_id, edit_account_name=acc["name"])
    await state.set_state(EditBalanceState.waiting_for_new_balance)

    icon = get_account_icon(acc["name"])
    await callback.message.edit_text(
        f"✏️ Выбран счет: {icon} **{acc['name']}**\n"
        f"Текущий баланс: `{acc['balance']:,.2f} {settings.CURRENCY_SYMBOL}`\n\n"
        f"👇 **Отправьте сообщением новый точный баланс** (например: `1250` или `500.50`):",
        parse_mode="Markdown"
    )
    await callback.answer()

# Принятие и сохранение нового баланса
@router.message(EditBalanceState.waiting_for_new_balance)
async def save_new_balance(message: Message, state: FSMContext):
    try:
        new_balance = float(message.text.replace(',', '.').strip())
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число (например `500` или `1250.80`).")
        return

    data = await state.get_data()
    acc_id = data["edit_account_id"]
    acc_name = data["edit_account_name"]

    await set_account_balance(acc_id, new_balance)
    await state.clear()

    icon = get_account_icon(acc_name)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💼 Открыть Мои деньги", callback_data="btn_refresh_balance")]
    ])
    await message.answer(
        f"✅ Баланс счета {icon} **{acc_name}** успешно обновлен!\n"
        f"💰 Новый баланс: `{new_balance:,.2f} {settings.CURRENCY_SYMBOL}`",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@router.message(F.text.in_(["👥 Долги", "🤝 Долги"]))
async def show_debts_handler(message: Message):
    debts = await get_debts(message.from_user.id)
    currency = settings.CURRENCY_SYMBOL
    if not debts:
        await message.answer("👥 **У вас нет активных записей о долгах.**", parse_mode="Markdown")
        return

    given_by_person = {}
    received_by_person = {}

    for d in debts:
        name = d["person_name"].strip()
        comment = f" ({d['comment']})" if d.get("comment") else ""
        entry = f"{d['amount']:,.2f} {currency}{comment}"
        
        if d["type"] == "debt_given":
            given_by_person.setdefault(name, []).append((d["amount"], entry))
        else:
            received_by_person.setdefault(name, []).append((d["amount"], entry))

    lines = [
        "👥 **ДОЛГОВОЙ БАЛАНС**",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]

    lent_total = 0.0
    if given_by_person:
        lines.append("🤝 **Вам должны:**")
        for person, items in given_by_person.items():
            subtotal = sum(x[0] for x in items)
            lent_total += subtotal
            details = ", ".join(x[1] for x in items)
            lines.append(f"• **{person}**: `{subtotal:,.2f} {currency}`\n   └ _{details}_")

    borrowed_total = 0.0
    if received_by_person:
        lines.append("\n📥 **Вы должны:**")
        for person, items in received_by_person.items():
            subtotal = sum(x[0] for x in items)
            borrowed_total += subtotal
            details = ", ".join(x[1] for x in items)
            lines.append(f"• **{person}**: `{subtotal:,.2f} {currency}`\n   └ _{details}_")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━",
        f"📈 **Итого вам должны:** `{lent_total:,.2f} {currency}`",
        f"📉 **Итого вы должны:** `{borrowed_total:,.2f} {currency}`"
    ])
    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(F.text == "📋 История")
async def show_history_handler(message: Message):
    txs = await get_recent_transactions(message.from_user.id, limit=10)
    currency = settings.CURRENCY_SYMBOL
    if not txs:
        await message.answer("📋 **История операций пуста.**", parse_mode="Markdown")
        return

    lines = [
        "📋 **ПОСЛЕДНИЕ 10 ОПЕРАЦИЙ**",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]
    for t in txs:
        icon = "💸" if t["type"] == "expense" else "💰"
        acc = f" • _{t['account_name']}_" if t.get("account_name") else ""
        comment = f" — {t['comment']}" if t.get("comment") else ""
        lines.append(f"{icon} `{t['amount']:,.2f} {currency}` | **{t['category']}**{acc}{comment}")

    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(F.text == "➕ Добавить счет")
@router.callback_query(F.data == "btn_add_account")
async def start_add_account(event: Message | CallbackQuery, state: FSMContext):
    msg = event if isinstance(event, Message) else event.message
    await msg.answer("📝 Введите **название счета** (например: `ДС`, `Наличные`, `Alif`):", parse_mode="Markdown")
    await state.set_state(AddAccountState.waiting_for_name)
    if isinstance(event, CallbackQuery):
        await event.answer()

@router.message(AddAccountState.waiting_for_name)
async def process_account_name(message: Message, state: FSMContext):
    account_name = message.text.strip()
    await state.update_data(account_name=account_name)
    await message.answer(f"💰 Введите начальный баланс для **{account_name}** (например `0` или `500`):", parse_mode="Markdown")
    await state.set_state(AddAccountState.waiting_for_balance)

@router.message(AddAccountState.waiting_for_balance)
async def process_account_balance(message: Message, state: FSMContext):
    try:
        balance = float(message.text.replace(',', '.').strip())
    except ValueError:
        await message.answer("⚠️ Введите число (например `0` или `250.50`).")
        return

    data = await state.get_data()
    account_name = data["account_name"]
    await add_account(message.from_user.id, account_name, balance)
    await state.clear()
    
    icon = get_account_icon(account_name)
    await message.answer(f"✅ Счет {icon} **{account_name}** создан с балансом `{balance:,.2f} {settings.CURRENCY_SYMBOL}`!", parse_mode="Markdown")