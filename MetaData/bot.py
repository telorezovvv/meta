import os
import sys
import subprocess
import logging
import sqlite3  # <-- ДОБАВЛЕНО
from pathlib import Path
from typing import Dict, Any

# ========== АВТОМАТИЧЕСКАЯ УСТАНОВКА БИБЛИОТЕК ==========
def install_packages():
    """Автоматическая установка необходимых библиотек"""
    packages = [
        'python-telegram-bot==20.7',
        'Pillow==10.1.0',
        'apscheduler==3.10.4'
    ]
    
    for package in packages:
        try:
            __import__(package.split('==')[0].replace('-', '_'))
        except ImportError:
            print(f"📦 Устанавливаю: {package}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ {package} установлен")

# Устанавливаем библиотеки перед импортом
install_packages()

# ========== ТЕПЕРЬ ИМПОРТИРУЕМ ==========
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import db, DB_PATH  # <-- ДОБАВЛЕНО DB_PATH

# ========== НАСТРОЙКИ (всё здесь) ==========

# Токен бота (обязательно)
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"

# Настройки канала
CHANNEL_ID = "-1001234567890"  # ID канала
CHANNEL_INVITE_LINK = "https://t.me/joinchat/ваша_ссылка"  # Ссылка для подписки

# ID администраторов (кто может выдавать запросы)
ADMIN_IDS = [123456789, 987654321]  # <-- СЮДА ВАШ ID

# ==========================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_БОТА":
    raise ValueError("Укажите BOT_TOKEN в файле bot.py!")

TEMP_DIR = Path("temp_files")
TEMP_DIR.mkdir(exist_ok=True)

# Эмодзи
EMOJIS = {
    'camera': '📷',
    'location': '📍',
    'time': '🕐',
    'settings': '⚙️',
    'file': '📁',
    'info': 'ℹ️',
    'gps': '🌍',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'processing': '⏳',
    'stats': '📊',
    'referral': '🎁',
    'subscribed': '🔓',
    'unsubscribed': '🔒'
}


def extract_photo_metadata(file_path: str) -> Dict[str, Any]:
    """Извлечение метаданных из фото"""
    result = {
        'camera_info': {},
        'photo_settings': {},
        'gps': {},
        'datetime': None,
        'basic': {}
    }
    
    try:
        with Image.open(file_path) as img:
            result['basic'] = {
                'width': img.width,
                'height': img.height,
                'format': img.format
            }
            
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    
                    if tag == 'Make':
                        result['camera_info']['make'] = str(value).strip()
                    elif tag == 'Model':
                        result['camera_info']['model'] = str(value).strip()
                    elif tag == 'Software':
                        result['camera_info']['software'] = str(value).strip()
                    elif tag == 'ISOSpeedRatings':
                        result['photo_settings']['iso'] = int(value) if isinstance(value, int) else str(value)
                    elif tag == 'FNumber':
                        try:
                            if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                                f_number = value.numerator / value.denominator
                            else:
                                f_number = float(value)
                            result['photo_settings']['aperture'] = f"f/{f_number:.1f}"
                        except:
                            result['photo_settings']['aperture'] = str(value)
                    elif tag == 'ExposureTime':
                        try:
                            if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                                exp = value.numerator / value.denominator
                            else:
                                exp = float(value)
                            if exp >= 1:
                                result['photo_settings']['exposure'] = f"{exp:.1f}с"
                            else:
                                result['photo_settings']['exposure'] = f"1/{int(1/exp)}с"
                        except:
                            result['photo_settings']['exposure'] = str(value)
                    elif tag == 'FocalLength':
                        try:
                            if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                                focal = value.numerator / value.denominator
                            else:
                                focal = float(value)
                            result['photo_settings']['focal_length'] = f"{focal:.1f}mm"
                        except:
                            result['photo_settings']['focal_length'] = str(value)
                    elif tag == 'LensModel':
                        result['photo_settings']['lens'] = str(value).strip()
                    elif tag in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                        if value:
                            result['datetime'] = str(value)
                    elif tag == 'GPSInfo':
                        gps_data = {}
                        for gps_tag_id, gps_value in value.items():
                            gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_data[gps_tag] = gps_value
                        
                        if 'GPSLatitude' in gps_data and 'GPSLongitude' in gps_data:
                            lat = convert_to_degrees(gps_data['GPSLatitude'])
                            lon = convert_to_degrees(gps_data['GPSLongitude'])
                            
                            if gps_data.get('GPSLatitudeRef') == 'S':
                                lat = -lat
                            if gps_data.get('GPSLongitudeRef') == 'W':
                                lon = -lon
                            
                            result['gps'] = {
                                'latitude': lat,
                                'longitude': lon,
                                'google_maps': f"https://www.google.com/maps?q={lat},{lon}"
                            }
    except Exception as e:
        result['error'] = str(e)
    
    return result


def convert_to_degrees(value) -> float:
    """Конвертация GPS координат"""
    if isinstance(value, tuple) and len(value) >= 3:
        try:
            d = float(value[0].numerator) / float(value[0].denominator)
            m = float(value[1].numerator) / float(value[1].denominator)
            s = float(value[2].numerator) / float(value[2].denominator)
            return d + (m / 60.0) + (s / 3600.0)
        except:
            return 0.0
    return 0.0


def format_photo_response(metadata: Dict[str, Any]) -> str:
    """Форматирование метаданных фото"""
    lines = []
    
    lines.append("📸 **РЕЗУЛЬТАТ АНАЛИЗА ФОТО**")
    lines.append("")
    
    camera = metadata.get('camera_info', {})
    if camera:
        lines.append(f"📷 **Устройство:**")
        if camera.get('make') and camera.get('model'):
            lines.append(f"   `{camera['make']} {camera['model']}`")
        elif camera.get('model'):
            lines.append(f"   `{camera['model']}`")
        if camera.get('software'):
            lines.append(f"   🔧 {camera['software']}")
        lines.append("")
    
    settings = metadata.get('photo_settings', {})
    if settings:
        lines.append(f"⚙️ **Настройки съемки:**")
        if settings.get('exposure'):
            lines.append(f"   ⏱ Выдержка: `{settings['exposure']}`")
        if settings.get('aperture'):
            lines.append(f"   🔆 Диафрагма: `{settings['aperture']}`")
        if settings.get('iso'):
            lines.append(f"   📊 ISO: `{settings['iso']}`")
        if settings.get('focal_length'):
            lines.append(f"   🔭 Фокусное: `{settings['focal_length']}`")
        if settings.get('lens'):
            lines.append(f"   📷 Объектив: `{settings['lens']}`")
        lines.append("")
    
    if metadata.get('datetime'):
        lines.append(f"🕐 **Дата и время съемки:**")
        lines.append(f"   `{metadata['datetime']}`")
        lines.append("")
    
    gps = metadata.get('gps', {})
    if gps and 'latitude' in gps and 'longitude' in gps:
        lat = gps['latitude']
        lon = gps['longitude']
        lines.append(f"📍 **МЕСТОПОЛОЖЕНИЕ**")
        lines.append("")
        lines.append(f"   🌐 Координаты:")
        lines.append(f"      Широта: `{lat:.6f}`")
        lines.append(f"      Долгота: `{lon:.6f}`")
        lines.append("")
        lines.append(f"   🗺 **Открыть на картах:**")
        lines.append(f"      • [Google Maps]({gps['google_maps']})")
        lines.append("")
    
    basic = metadata.get('basic', {})
    if basic:
        lines.append(f"ℹ️ **Информация о файле:**")
        if basic.get('width') and basic.get('height'):
            lines.append(f"   📐 Разрешение: `{basic['width']}×{basic['height']}`")
        if basic.get('format'):
            lines.append(f"   📁 Формат: `{basic['format']}`")
        lines.append("")
    
    return '\n'.join(lines)


async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка подписки пользователя на канал"""
    if not CHANNEL_ID:
        return True
    
    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id
        )
        is_subscribed = chat_member.status in ['member', 'administrator', 'creator']
        db.update_subscription(user_id, is_subscribed)
        return is_subscribed
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False


async def show_subscription_required(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает экран с требованием подписки"""
    text = f"""
🔐 **ТРЕБУЕТСЯ ПОДПИСКА**

Для использования бота необходимо подписаться на наш канал.

⚠️ **Без подписки вы НЕ сможете пользоваться ботом!**

После подписки нажмите кнопку **"Проверить подписку"** ✅
"""
    
    keyboard = []
    if CHANNEL_INVITE_LINK:
        keyboard.append([InlineKeyboardButton("📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_INVITE_LINK)])
    keyboard.append([InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")])
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Проверяем реферальный код
    args = context.args
    if args and len(args) > 0:
        referral_code = args[0].upper()
        referrer_id = db.get_user_by_referral_code(referral_code)
        
        if referrer_id and referrer_id != user_id:
            existing_user = db.get_user(user_id)
            if not existing_user:
                db.create_user(
                    user_id=user_id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    referrer_id=referrer_id
                )
                db.process_referral(referrer_id, user_id)
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 **Новый реферал!**\nПользователь @{user.username or user.first_name} присоединился!\nВы получили **+1 запрос**!",
                        parse_mode='Markdown'
                    )
                except:
                    pass
    
    # Создаем пользователя если его нет
    if not db.get_user(user_id):
        db.create_user(
            user_id=user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    
    # Проверяем подписку
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await show_subscription_required(update.effective_chat.id, context)
        return
    
    # Показываем главное меню
    await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню"""
    user = update.effective_user
    user_id = user.id
    
    stats = db.get_user_stats(user_id)
    
    text = f"""
👋 **Добро пожаловать, {user.first_name}!** ✨

Я бот для анализа метаданных ваших файлов.

📤 **Отправьте мне файл**, и я покажу:
• 📷 Модель камеры или телефона
• 📍 Местоположение (GPS координаты)
• ⚙️ Настройки съемки
• 🕐 Дату и время создания

📊 **Ваша статистика:**
• Всего запросов: `{stats.get('total_requests', 0)}`
• Доступно сегодня: `{stats.get('remaining', 0)}` из `{stats.get('total_available', 5)}`
• Бонусных запросов: `{stats.get('bonus_requests', 0)}`
• Приглашено друзей: `{stats.get('referrals', {}).get('total', 0)}`
• Получено бонусов: `{stats.get('referrals', {}).get('bonus_given', 0)}`

💡 **Пополнить лимит:** /referral
"""
    
    keyboard = [
        [InlineKeyboardButton("🎁 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")]
    ]
    
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.message.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия кнопки проверки подписки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        await query.message.edit_text(
            f"{EMOJIS['success']} ✅ **Подписка подтверждена!**\n\n🎉 Отлично! Теперь вы можете пользоваться ботом.",
            parse_mode='Markdown'
        )
        class FakeUpdate:
            def __init__(self, user, query):
                self.effective_user = user
                self.callback_query = query
                self.message = None
        await show_main_menu(FakeUpdate(query.from_user, query), context)
    else:
        text = f"""
🔐 **ТРЕБУЕТСЯ ПОДПИСКА**

Вы **НЕ** подписаны на наш канал.

⚠️ **Без подписки вы НЕ сможете пользоваться ботом!**

После подписки нажмите кнопку **"Проверить подписку"** ✅
"""
        keyboard = []
        if CHANNEL_INVITE_LINK:
            keyboard.append([InlineKeyboardButton("📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_INVITE_LINK)])
        keyboard.append([InlineKeyboardButton("✅ ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")])
        
        await query.message.edit_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка файлов"""
    user_id = update.effective_user.id
    
    # Проверяем подписку
    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        await show_subscription_required(update.effective_chat.id, context)
        return
    
    # Проверяем лимиты
    can_request, message = db.can_make_request(user_id)
    if not can_request:
        await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    try:
        # Проверяем, что это документ
        if not update.message.document:
            await update.message.reply_text(
                f"{EMOJIS['warning']} **⚠️ ВНИМАНИЕ!**\n\n"
                "Вы отправили фото как изображение.\n\n"
                "📸 **Отправьте фото как ФАЙЛ (документ):**\n"
                "1. Нажмите на скрепку 📎\n"
                "2. Выберите **'Файл'**\n"
                "3. Выберите фото\n"
                "4. Отправьте",
                parse_mode='Markdown'
            )
            return
        
        file = update.message.document
        file_name = file.file_name or f"document_{file.file_id}"
        ext = Path(file_name).suffix.lower()
        
        # Проверяем формат
        supported = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
        if ext not in supported:
            await update.message.reply_text(
                f"⚠️ Неподдерживаемый формат.\nПоддерживаются: JPG, PNG, GIF, BMP, TIFF, WEBP"
            )
            return
        
        # Скачиваем файл
        remaining = db.get_remaining_requests(user_id)
        processing_msg = await update.message.reply_text(
            f"{EMOJIS['processing']} **Анализирую ваш файл...**\n"
            f"📁 `{file_name}`\n\n"
            f"📊 Осталось запросов: `{remaining - 1}`",
            parse_mode='Markdown'
        )
        
        file_obj = await file.get_file()
        file_path = TEMP_DIR / file_name
        await file_obj.download_to_drive(file_path)
        
        # Анализируем
        metadata = extract_photo_metadata(str(file_path))
        response = format_photo_response(metadata)
        
        # Добавляем информацию о лимитах
        footer = "\n" + "─" * 30 + "\n"
        footer += f"{EMOJIS['success']} Анализ завершен!\n"
        footer += f"📊 Осталось запросов: `{remaining - 1}`"
        if remaining - 1 == 0:
            footer += "\n\n💡 Пригласите друга и получите **+1 запрос**!\nИспользуйте /referral"
        response += footer
        
        # Регистрируем запрос
        db.add_request(user_id)
        
        await processing_msg.edit_text(
            response,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        try:
            file_path.unlink()
        except:
            pass
    
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Произошла ошибка при обработке файла.\nПопробуйте еще раз."
        )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Если отправили фото как изображение"""
    await update.message.reply_text(
        f"{EMOJIS['warning']} **⚠️ ВНИМАНИЕ!**\n\n"
        "Вы отправили фото как изображение.\n\n"
        "📸 **Отправьте фото как ФАЙЛ (документ):**\n"
        "1. Нажмите на скрепку 📎\n"
        "2. Выберите **'Файл'**\n"
        "3. Выберите фото\n"
        "4. Отправьте",
        parse_mode='Markdown'
    )


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /referral"""
    user_id = update.effective_user.id
    
    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        await show_subscription_required(update.effective_chat.id, context)
        return
    
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка")
        return
    
    referral_code = user.get('referral_code')
    stats = db.get_user_stats(user_id)
    referral_stats = stats.get('referrals', {})
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    text = f"""
🎁 **Реферальная система**

👤 **Ваш реферальный код:**
`{referral_code}`

🔗 **Ваша ссылка:**
{referral_link}

📊 **Статистика:**
• Приглашено: `{referral_stats.get('total', 0)}` человек
• Активных: `{referral_stats.get('active', 0)}` человек
• Получено бонусов: `{referral_stats.get('bonus_given', 0)}` запросов

💡 **Как работает:**
1. Отправьте ссылку другу
2. Он переходит и подписывается на канал
3. Вы получаете **+1 запрос** (навсегда)!
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Скопировать код", callback_data=f"copy_{referral_code}")],
        [InlineKeyboardButton("📤 Поделиться ссылкой", callback_data=f"share_{referral_code}")]
    ]
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /stats"""
    user_id = update.effective_user.id
    
    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        await show_subscription_required(update.effective_chat.id, context)
        return
    
    stats = db.get_user_stats(user_id)
    
    text = f"""
📊 **Ваша статистика**

👤 **Пользователь:** {update.effective_user.first_name}

📅 **Сегодня:**
• Использовано: `{stats.get('daily_used', 0)}` из `{stats.get('total_available', 5)}`
• Осталось: `{stats.get('remaining', 0)}`
• Бонусных запросов: `{stats.get('bonus_requests', 0)}`

📈 **Всего:**
• Запросов: `{stats.get('total_requests', 0)}`
• Приглашено: `{stats.get('referrals', {}).get('total', 0)}` человек
• Активных рефералов: `{stats.get('referrals', {}).get('active', 0)}`
• Получено бонусов: `{stats.get('referrals', {}).get('bonus_given', 0)}`

🎁 **Бонусы:**
• За рефералов: `+{stats.get('referrals', {}).get('bonus_given', 0)}` запросов навсегда
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')


# ========== КОМАНДА ДЛЯ ВЫДАЧИ ЗАПРОСОВ (ТОЛЬКО ДЛЯ АДМИНА) ==========
async def add_requests_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /add_requests - выдача запросов пользователю (только для админов)"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь админом
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды!")
        return
    
    # Проверяем аргументы
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование: `/add_requests @username количество`\n"
            "Пример: `/add_requests @user123 5`\n\n"
            "Или по ID: `/add_requests 123456789 5`",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Определяем пользователя и количество
        target = args[0]
        amount = int(args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Количество должно быть больше 0!")
            return
        
        # Ищем пользователя
        target_user_id = None
        target_username = None
        
        # Если передан ID
        if target.isdigit():
            target_user_id = int(target)
            user_data = db.get_user(target_user_id)
            if user_data:
                target_username = user_data.get('username')
        else:
            # Если передан @username
            username = target.replace('@', '')
            # Ищем пользователя в базе
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_id, username FROM users WHERE username = ?', (username,))
                row = cursor.fetchone()
                if row:
                    target_user_id = row[0]
                    target_username = row[1]
        
        if not target_user_id:
            await update.message.reply_text(f"❌ Пользователь {target} не найден в базе данных!")
            return
        
        # Добавляем бонусные запросы
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET bonus_requests = bonus_requests + ?
                WHERE user_id = ?
            ''', (amount, target_user_id))
            conn.commit()
        
        # Отправляем уведомление пользователю
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎁 **Вам начислено {amount} бонусных запросов!**\n\n"
                     f"📊 Теперь у вас доступно больше запросов!\n"
                     f"Используйте /stats для проверки.",
                parse_mode='Markdown'
            )
        except:
            pass
        
        # Отправляем подтверждение админу
        await update.message.reply_text(
            f"✅ **Запросы выданы!**\n\n"
            f"👤 Пользователь: @{target_username or target_user_id}\n"
            f"📊 Добавлено: `{amount}` запросов\n"
            f"💬 Уведомление отправлено!",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Количество должно быть числом!\nПример: `/add_requests @user 5`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    if query.data == "check_sub":
        await check_subscription_callback(update, context)
    
    elif query.data == "referral":
        is_subscribed = await check_subscription(user_id, context)
        if not is_subscribed:
            await show_subscription_required(update.effective_chat.id, context)
            return
        
        user = db.get_user(user_id)
        if not user:
            await query.message.reply_text("❌ Ошибка")
            return
        
        referral_code = user.get('referral_code')
        bot_username = context.bot.username
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"
        
        text = f"🎁 **Реферальная система**\n\n👤 **Ваш код:** `{referral_code}`\n🔗 **Ссылка:** {referral_link}"
        keyboard = [
            [InlineKeyboardButton("📋 Скопировать код", callback_data=f"copy_{referral_code}")],
            [InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{referral_code}")]
        ]
        await query.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data == "stats":
        is_subscribed = await check_subscription(user_id, context)
        if not is_subscribed:
            await show_subscription_required(update.effective_chat.id, context)
            return
        
        stats = db.get_user_stats(user_id)
        text = f"""
📊 **Ваша статистика**

👤 **Пользователь:** {query.from_user.first_name}

📅 **Сегодня:**
• Использовано: `{stats.get('daily_used', 0)}` из `{stats.get('total_available', 5)}`
• Осталось: `{stats.get('remaining', 0)}`
• Бонусных запросов: `{stats.get('bonus_requests', 0)}`

📈 **Всего:**
• Запросов: `{stats.get('total_requests', 0)}`
• Приглашено: `{stats.get('referrals', {}).get('total', 0)}` человек
• Получено бонусов: `{stats.get('referrals', {}).get('bonus_given', 0)}`
"""
        await query.message.reply_text(text, parse_mode='Markdown')
    
    elif query.data.startswith("copy_"):
        code = query.data.replace("copy_", "")
        await query.message.reply_text(
            f"📋 **Ваш реферальный код:**\n`{code}`\n\n🔗 **Ссылка:** https://t.me/{context.bot.username}?start={code}",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("share_"):
        code = query.data.replace("share_", "")
        referral_link = f"https://t.me/{context.bot.username}?start={code}"
        share_text = f"🎁 **Приглашаю в бота для анализа метаданных!**\n\n📸 Отправляй фото - я покажу все скрытые данные!\n\n👉 Переходи: {referral_link}"
        await query.message.reply_text(share_text, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    user_id = update.effective_user.id
    
    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        await show_subscription_required(update.effective_chat.id, context)
        return
    
    text = """
❓ **Помощь**

📸 **Что я умею:**
• Анализировать метаданные фото
• Показывать модель камеры
• Определять GPS координаты

📊 **Лимиты:**
• 5 запросов в день
• +1 запрос навсегда за приглашенного друга

⚙️ **Команды:**
/start - Главное меню
/help - Помощь
/stats - Статистика
/referral - Реферальная система

⚠️ **Важно!**
Отправляйте фото как **ФАЙЛ** (документ)!
"""
    await update.message.reply_text(text, parse_mode='Markdown')


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /about"""
    user_id = update.effective_user.id
    
    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        await show_subscription_required(update.effective_chat.id, context)
        return
    
    text = """
🤖 **Metadata Bot v4.0**

Анализ метаданных с системой подписки.

**Особенности:**
• 📸 Анализ EXIF и GPS
• 🔒 Подписка на канал
• 📊 5 запросов в день
• 🎁 Реферальная система (+1 запрос навсегда)

**Разработчик:** @haman
"""
    await update.message.reply_text(text, parse_mode='Markdown')


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.message:
            await update.message.reply_text(f"{EMOJIS['error']} Произошла ошибка. Попробуйте еще раз.")
    except:
        pass


def reset_daily_requests():
    """Сброс лимитов в 00:00"""
    db.reset_daily_requests()
    logger.info("🔄 Дневные лимиты сброшены")


async def post_init(application: Application):
    """Инициализация после запуска"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reset_daily_requests, CronTrigger(hour=0, minute=0), id="reset_daily_requests")
    scheduler.start()
    logger.info("🔄 Планировщик запущен, сброс лимитов в 00:00")


def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("add_requests", add_requests_command))  # <-- ДОБАВЛЕНО
    
    # Кнопки
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Файлы
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    
    # Ошибки
    application.add_error_handler(error_handler)
    
    print("🤖 Бот запущен с подпиской и рефералами!")
    print("=" * 50)
    print(f"📢 ID канала: {CHANNEL_ID or 'Не настроен'}")
    print(f"📊 Лимит: 5 запросов в день")
    print(f"🔄 Сброс в 00:00")
    print(f"👑 Админы: {ADMIN_IDS}")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
