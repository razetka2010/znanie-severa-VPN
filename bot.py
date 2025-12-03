import asyncio
import logging
import sys
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_IDS
from database import Database

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# Состояния для FSM
class UserStates(StatesGroup):
    waiting_for_payment_proof = State()

class AdminStates(StatesGroup):
    waiting_for_key_input = State()
    waiting_for_reply = State()

# Команда /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Без имени"
    
    # Регистрация пользователя в базе
    db.add_user(user_id, username)
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="💰 Купить ключ", callback_data="buy_key"),
        types.InlineKeyboardButton(text="🌐 Мои ключи", callback_data="my_keys"),
        types.InlineKeyboardButton(text="⚠️ Помощь", callback_data="help"),
        types.InlineKeyboardButton(text="👨‍💻 Поддержка", url="t.me/razetkaartem")
    )
    builder.adjust(2, 2)
    
    await message.answer(
        f"Добро пожаловать в VPN бот ^_^\n" 
        " \n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

# Кнопка "Купить ключ"
@dp.callback_query(F.data == "buy_key")
async def process_buy_key(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="1 месяц - 100 руб", callback_data="buy_1_month"),
        types.InlineKeyboardButton(text="3 месяца - 250 руб", callback_data="buy_3_months"),
        types.InlineKeyboardButton(text="6 месяцев - 450 руб", callback_data="buy_6_months"),
        types.InlineKeyboardButton(text="1 год - 800 руб", callback_data="buy_1_year"),
        types.InlineKeyboardButton(text="Назад", callback_data="main_menu")
    )
    builder.adjust(2, 2, 1)
    
    await callback.message.edit_text(
        "💰 Выберите тариф:\n\n"
        "• 1 месяц - 100 руб\n"
        "• 3 месяца - 250 руб (экономия 50 руб)\n"
        "• 6 месяцев - 450 руб (экономия 150 руб)\n"
        "• 1 год - 800 руб (экономия 400 руб)\n\n"
        "После оплаты пришлите скриншот чека для получения ключа.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обработка выбора тарифа
@dp.callback_query(F.data.startswith('buy_'))
async def process_tariff_selection(callback: CallbackQuery, state: FSMContext):
    tariff_map = {
        'buy_1_month': {'duration': 30, 'price': 100, 'name': '1 месяц'},
        'buy_3_months': {'duration': 90, 'price': 250, 'name': '3 месяца'},
        'buy_6_months': {'duration': 180, 'price': 450, 'name': '6 месяцев'},
        'buy_1_year': {'duration': 365, 'price': 800, 'name': '1 год'}
    }
    
    tariff = callback.data
    if tariff in tariff_map:
        await state.update_data(tariff=tariff_map[tariff])
        
        payment_info = (
            f"💳 Оплатите {tariff_map[tariff]['price']} руб\n\n"
            "📱 Реквизиты для оплаты:\n"
            "• Сбербанк: 2202 2082 6210 7460\n\n"
            "После оплаты пришлите скриншот чека.\n"
            f"В комментарии к платежу укажите: @dapogkakto"
        )
        
        # Создаем клавиатуру с кнопкой "Назад"
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="Назад", callback_data="buy_key")
        )
        
        await callback.message.edit_text(
            payment_info,
            reply_markup=builder.as_markup()
        )
        await state.set_state(UserStates.waiting_for_payment_proof)
    await callback.answer()

# Прием скриншота оплаты
@dp.message(UserStates.waiting_for_payment_proof, F.photo)
async def process_payment_proof(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    tariff = user_data['tariff']
    user_id = message.from_user.id
    username = message.from_user.username or "Без имени"
    
    # Сохраняем информацию о платеже
    payment_id = db.add_payment(
        user_id=user_id,
        amount=tariff['price'],
        duration=tariff['duration'],
        proof_photo_id=message.photo[-1].file_id
    )
    
    # Уведомляем администраторов
    for admin_id in ADMIN_IDS:
        try:
            builder = InlineKeyboardBuilder()
            builder.row(
                types.InlineKeyboardButton(
                    text="🔑 Выдать ключ", 
                    callback_data=f"approve_{payment_id}"
                )
            )
            builder.row(
                types.InlineKeyboardButton(
                    text="💬 Ответить",
                    callback_data=f"reply_{payment_id}"
                ),
                types.InlineKeyboardButton(
                    text="🗑️ Удалить",
                    callback_data=f"delete_{payment_id}"
                )
            )
            
            await bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=(
                    f"🔄 <b>Новый платеж!</b>\n\n"
                    f"👤 <b>Пользователь:</b> @{username}\n"
                    f"💰 <b>Сумма:</b> {tariff['price']} руб\n"
                    f"⏱ <b>Срок:</b> {tariff['name']}\n"
                    f"🆔 <b>ID:</b> {user_id}\n"
                    f"📝 <b>ID платежа:</b> {payment_id}"
                ),
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            logger.error(f"Error sending to admin {admin_id}: {e}")
    
    # Создаем клавиатуру с кнопкой "Назад" для пользователя
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")
    )
    
    await message.answer(
        "✅ Скриншот получен! Ожидайте проверки платежа администратором. "
        "Обычно это занимает до 15 минут.\n\n"
        "Вы получите ключ сразу после проверки.",
        reply_markup=builder.as_markup()
    )
    await state.clear()

# Админ: обработка кнопки "Выдать ключ"
@dp.callback_query(F.data.startswith('approve_'))
async def process_approve_payment(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split('_')[1])
        
        # Получаем информацию о платеже
        payment = db.get_payment_by_id(payment_id)
        
        if not payment:
            await callback.answer("❌ Платеж не найден!", show_alert=True)
            return
        
        if payment['status'] == 'approved':
            await callback.answer("⚠️ Этот платеж уже обработан!", show_alert=True)
            return
        
        # Сохраняем данные платежа в состоянии
        await state.update_data(
            payment_id=payment_id,
            user_id=payment['user_id'],
            username=payment.get('username', 'Без имени'),
            amount=payment['amount'],
            duration=payment['duration']
        )
        await state.set_state(AdminStates.waiting_for_key_input)
        
        duration_name = {
            30: "1 месяц",
            90: "3 месяца",
            180: "6 месяцев",
            365: "1 год"
        }.get(payment['duration'], f"{payment['duration']} дней")
        
        # Отправляем новое сообщение с инструкцией
        await callback.message.answer(
            f"🔑 <b>Введите ключ VPN</b>\n\n"
            f"👤 <b>Пользователь:</b> @{payment.get('username', 'Без имени')}\n"
            f"🆔 <b>ID пользователя:</b> {payment['user_id']}\n"
            f"💰 <b>Сумма:</b> {payment['amount']} руб\n"
            f"⏱ <b>Срок:</b> {duration_name}\n"
            f"📝 <b>ID платежа:</b> {payment_id}\n\n"
            f"<i>Просто отправьте текстовое сообщение с ключом...</i>\n\n"
            f"<code>/cancel</code> - отменить"
        )
        
        await callback.answer("⏳ Ожидаю ввод ключа...")
        
    except Exception as e:
        logger.error(f"Error in process_approve_payment: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# Админ: удаление платежа
@dp.callback_query(F.data.startswith('delete_'))
async def process_delete_payment(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split('_')[1])
        
        # Удаляем платеж из базы
        deleted = db.delete_payment(payment_id)
        
        if deleted:
            await callback.answer("✅ Платеж удален", show_alert=True)
            
            # Отправляем отдельное подтверждение
            await callback.message.answer(f"🗑️ Платеж ID {payment_id} успешно удален")
        else:
            await callback.answer("❌ Платеж не найден", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in process_delete_payment: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# Админ: ответ пользователю
@dp.callback_query(F.data.startswith('reply_'))
async def process_reply_to_payment(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split('_')[1])
        
        # Получаем информацию о платеже
        payment = db.get_payment_by_id(payment_id)
        
        if not payment:
            await callback.answer("❌ Платеж не найден!", show_alert=True)
            return
        
        # Сохраняем данные для ответа
        await state.update_data(
            reply_payment_id=payment_id,
            reply_user_id=payment['user_id'],
            reply_username=payment.get('username', 'Без имени')
        )
        await state.set_state(AdminStates.waiting_for_reply)
        
        # Запрашиваем текст ответа
        await callback.message.answer(
            f"💬 <b>Ответ пользователю</b>\n\n"
            f"👤 <b>Кому:</b> @{payment.get('username', 'Без имени')}\n"
            f"🆔 <b>ID:</b> {payment['user_id']}\n"
            f"📝 <b>ID платежа:</b> {payment_id}\n\n"
            f"<i>Введите текст ответа...</i>\n\n"
            f"<code>/cancel</code> - отменить"
        )
        
        await callback.answer("⏳ Ожидаю текст ответа...")
        
    except Exception as e:
        logger.error(f"Error in process_reply_to_payment: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# Админ: прием ответа пользователю
@dp.message(AdminStates.waiting_for_reply)
async def process_admin_reply(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    # Проверяем отмену
    if message.text.strip() == "/cancel":
        await message.answer("❌ Ответ отменен")
        await state.clear()
        return
    
    try:
        user_data = await state.get_data()
        payment_id = user_data['reply_payment_id']
        user_id = user_data['reply_user_id']
        username = user_data['reply_username']
        
        reply_text = message.text.strip()
        
        if not reply_text:
            await message.answer("❌ Текст ответа не может быть пустым!")
            return
        
        # Отправляем ответ пользователю
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"💬 <b>Ответ от администратора:</b>\n\n{reply_text}"
            )
            
            # Уведомляем администратора об успехе
            await message.answer(
                f"✅ <b>Ответ отправлен!</b>\n\n"
                f"👤 <b>Пользователю:</b> @{username}\n"
                f"🆔 <b>ID:</b> {user_id}\n"
                f"📝 <b>ID платежа:</b> {payment_id}\n\n"
                f"<b>Текст:</b>\n{reply_text}"
            )
            
        except Exception as e:
            logger.error(f"Error sending reply to user {user_id}: {e}")
            await message.answer(
                f"❌ <b>Не удалось отправить ответ</b>\n\n"
                f"<b>Причина:</b> {str(e)}\n\n"
                f"<b>Текст ответа:</b>\n{reply_text}\n\n"
                f"<i>Пользователь мог заблокировать бота</i>"
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in process_admin_reply: {e}")
        await message.answer(f"❌ <b>Ошибка:</b> {str(e)}")
        await state.clear()

# Админ: прием ключа от администратора
@dp.message(AdminStates.waiting_for_key_input)
async def process_admin_key_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        return
    
    # Проверяем отмену
    if message.text.strip() == "/cancel":
        await message.answer("❌ Выдача ключа отменена")
        await state.clear()
        return
    
    try:
        user_data = await state.get_data()
        payment_id = user_data['payment_id']
        user_id = user_data['user_id']
        
        vpn_key = message.text.strip()
        
        if not vpn_key:
            await message.answer("❌ Ключ не может быть пустым! Попробуйте снова.")
            return
        
        if len(vpn_key) < 5:
            await message.answer("❌ Ключ слишком короткий! Минимум 5 символов.")
            return
        
        # Обновляем платеж с ключом
        db.update_payment_with_key(payment_id, vpn_key)
        
        # Добавляем ключ пользователю
        db.add_key(user_id, vpn_key, user_data['duration'])
        
        # Формируем сообщение для пользователя
        duration_name = {
            30: "1 месяц",
            90: "3 месяца",
            180: "6 месяцев",
            365: "1 год"
        }.get(user_data['duration'], f"{user_data['duration']} дней")
        
        user_message = (
            f"🎉 <b>Ваш платеж подтвержден!</b>\n\n"
            f"🔑 <b>Ваш ключ VPN:</b> <code>{vpn_key}</code>\n"
            f"⏱ <b>Срок действия:</b> {duration_name}\n\n"
            f"<b>Как использовать:</b>\n"
            f"1. Установите приложение WireGuard\n"
            f"2. Добавьте новый туннель\n"
            f"3. Введите ключ: <code>{vpn_key}</code>\n"
            f"4. Настройте сервер по инструкции\n\n"
            f"<i>При проблемах обращайтесь: @razetkaartem</i>"
        )
        
        # Отправляем ключ пользователю
        try:
            await bot.send_message(
                chat_id=user_id,
                text=user_message
            )
            
            # Уведомляем администратора об успехе
            await message.answer(
                f"✅ <b>Ключ успешно выдан!</b>\n\n"
                f"👤 <b>Пользователь:</b> {user_data['username']}\n"
                f"🆔 <b>ID:</b> {user_id}\n"
                f"🔑 <b>Ключ:</b> <code>{vpn_key}</code>\n"
                f"⏱ <b>Срок:</b> {duration_name}\n"
                f"💰 <b>Сумма:</b> {user_data['amount']} руб"
            )
            
        except Exception as e:
            logger.error(f"Error sending key to user {user_id}: {e}")
            await message.answer(
                f"⚠️ <b>Ключ сохранен, но не отправлен пользователю</b>\n\n"
                f"<b>Причина:</b> {str(e)}\n\n"
                f"<b>Ключ:</b> <code>{vpn_key}</code>\n"
                f"<b>ID пользователя:</b> {user_id}\n\n"
                f"<i>Отправьте ключ пользователю вручную</i>"
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in process_admin_key_input: {e}")
        await message.answer(f"❌ <b>Ошибка:</b> {str(e)}")
        await state.clear()

# Показать мои ключи
@dp.callback_query(F.data == "my_keys")
async def process_my_keys(callback: CallbackQuery):
    user_id = callback.from_user.id
    keys = db.get_user_keys(user_id)
    
    if not keys:
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="💰 Купить ключ", callback_data="buy_key"),
            types.InlineKeyboardButton(text="Назад", callback_data="main_menu")
        )
        builder.adjust(2)
        
        await callback.message.edit_text(
            "У вас нет активных ключей.\n"
            "Приобретите ключ в разделе '💰 Купить ключ'",
            reply_markup=builder.as_markup()
        )
        return
    
    message_text = "🔑 Ваши активные ключи:\n\n"
    for key in keys:
        status = "✅ Активен" if key['is_active'] else "❌ Истек"
        duration_name = {
            30: "1 месяц",
            90: "3 месяца",
            180: "6 месяцев",
            365: "1 год"
        }.get(key['duration'], f"{key['duration']} дней")
        
        message_text += (
            f"<b>Ключ:</b> <code>{key['key']}</code>\n"
            f"<b>Срок:</b> {duration_name}\n"
            f"<b>Статус:</b> {status}\n"
            f"<b>Действителен до:</b> {key['expires_at']}\n\n"
        )
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="Назад", callback_data="main_menu")
    )
    
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Помощь
@dp.callback_query(F.data == "help")
async def process_help(callback: CallbackQuery):
    help_text = (
        "⚠️ <b>Часто задаваемые вопросы:</b>\n\n"
        "1. <b>Как подключить VPN?</b>\n"
        "   • Установите WireGuard с официального сайта\n"
        "   • Получите ключ после оплаты\n"
        "   • Добавьте ключ в приложение\n"
        "   • Настройте сервер (инструкция в поддержке)\n\n"
        "2. <b>На сколько выдается ключ?</b>\n"
        "   • 1 месяц - 100 руб\n"
        "   • 3 месяца - 250 руб\n"
        "   • 6 месяцев - 450 руб\n"
        "   • 1 год - 800 руб\n\n"
        "3. <b>Как оплатить?</b>\n"
        "   • Выберите тариф\n"
        "   • Оплатите на карту Сбербанк\n"
        "   • Пришлите скриншот чека\n"
        "   • В комментарии укажите @dapogkakto\n\n"
        "4. <b>Сколько ждать выдачи ключа?</b>\n"
        "   • Ключ выдается в течение 15 минут после проверки платежа.\n\n"
        "5. <b>Проблемы с подключением?</b>\n"
        "   • Обратитесь в поддержку: @razetkaartem"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="Назад", callback_data="main_menu"))
    
    await callback.message.edit_text(
        help_text,
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Возврат в главное меню
@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "Без имени"
    
    db.add_user(user_id, username)
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="💰 Купить ключ", callback_data="buy_key"),
        types.InlineKeyboardButton(text="🌐 Мои ключи", callback_data="my_keys"),
        types.InlineKeyboardButton(text="⚠️ Помощь", callback_data="help"),
        types.InlineKeyboardButton(text="👨‍💻 Поддержка", url="t.me/razetkaartem")
    )
    builder.adjust(2, 2)
    
    await callback.message.edit_text(
        f"Добро пожаловать в VPN бот ^_^\n" 
        " \n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Админ-панель
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    
    # Получаем статистику
    user_count = db.get_user_count()
    pending_payments = db.get_pending_payments()
    
    stats_text = (
        f"👨‍💻 <b>Админ-панель</b>\n\n"
        f"📊 Статистика:\n"
        f"• Пользователей: {user_count}\n"
        f"• Ожидающих платежей: {len(pending_payments)}\n\n"
        f"<i>Для выдачи ключа нажмите кнопку в уведомлении о платеже</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="📋 Все платежи", callback_data="admin_all_payments"),
        types.InlineKeyboardButton(text="Назад", callback_data="main_menu")
    )
    builder.adjust(2)
    
    await message.answer(
        stats_text,
        reply_markup=builder.as_markup()
    )

# Просмотр всех платежей
@dp.callback_query(F.data == "admin_all_payments")
async def admin_all_payments(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    try:
        payments = db.get_all_payments()
        
        if not payments:
            text = "📋 <b>Все платежи:</b>\n\n📭 Нет платежей"
        else:
            text = "📋 <b>Все платежи:</b>\n\n"
            for payment in payments:
                status_emoji = "✅" if payment.get('status') == 'approved' else "⏳"
                duration = payment.get('duration', 0)
                duration_name = {
                    30: "1 месяц",
                    90: "3 месяца",
                    180: "6 месяцев",
                    365: "1 год"
                }.get(duration, f"{duration} дней")
                
                text += (
                    f"{status_emoji} <b>ID:</b> {payment.get('id', '?')}\n"
                    f"👤 <b>Пользователь:</b> @{payment.get('username', 'Без имени')}\n"
                    f"💰 <b>Сумма:</b> {payment.get('amount', 0)} руб\n"
                    f"⏱ <b>Срок:</b> {duration_name}\n"
                    f"📅 <b>Дата:</b> {payment.get('created_at', 'неизвестно')}\n"
                    f"🔑 <b>Ключ:</b> {payment.get('admin_key', 'не выдан')[:20] + '...' if payment.get('admin_key') and len(payment.get('admin_key', '')) > 20 else payment.get('admin_key', 'не выдан')}\n"
                    f"────────────────\n"
                )
        
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_all_payments"),
            types.InlineKeyboardButton(text="Назад в админку", callback_data="admin_back"),
            types.InlineKeyboardButton(text="Главное меню", callback_data="main_menu")
        )
        builder.adjust(1, 2)
        
        await callback.message.answer(
            text,
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in admin_all_payments: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# Назад в админку
@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав!", show_alert=True)
        return
    
    await cmd_admin(callback.message)
    await callback.answer()

# Команда для получения своего ID
@dp.message(Command("myid"))
async def cmd_myid(message: types.Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")
    
    # Проверка админских прав
    if message.from_user.id in ADMIN_IDS:
        await message.answer("✅ Вы являетесь администратором!")
    else:
        await message.answer("❌ Вы не администратор.")

# Обработка текстовых сообщений
@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith('/'):
        if message.text == '/admin' and message.from_user.id in ADMIN_IDS:
            await cmd_admin(message)
        elif message.text == '/start':
            await cmd_start(message)
        else:
            await message.answer("Неизвестная команда. Используйте /start")
    else:
        await message.answer("Используйте кнопки меню для навигации.")

# Обработка неизвестных callback-ов
@dp.callback_query()
async def handle_unknown_callback(callback: CallbackQuery):
    await callback.answer("⚠️ Эта кнопка больше не активна. Используйте /start", show_alert=True)

async def main():
    # Удаляем вебхук (если был)
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("🤖 VPN Бот запускается...")
    print(f"Админские ID: {ADMIN_IDS}")
    print("Для остановки нажмите Ctrl+C")
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")