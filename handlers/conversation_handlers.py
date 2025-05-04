from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from typing import Optional, Dict
import uuid
from datetime import datetime
from config.constants import *
from services.mindee_service import MindeePassportAPI, MindeeVehicleAPI
from services.groq_service import GroqService
from utils.file_utils import ensure_directories_exist, save_mindee_response, generate_policy_filename
from utils.logging_utils import logger
import os

# Ініціалізація сервісів
mindee_passport_api = MindeePassportAPI()
mindee_vehicle_api = MindeeVehicleAPI()
groq_service = GroqService()

# Головні функції бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Початок розмови - запит фото паспорта"""
    message = update.message or update.callback_query.message
    await message.reply_text(
        "Привіт! Я бот для створення страховки на ваше авто. "
        "Надішліть фото вашого паспорта для розпізнавання даних.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]
        ])
    )
    return AWAITING_PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка фото паспорта"""
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_path = f"downloads/passport_{uuid.uuid4().hex}.jpg"
        await photo_file.download_to_drive(img_path)
        await update.message.reply_text("🔍 Розпізнаю дані з фото...")

        # Відправка на обробку до Mindee
        job_id = mindee_passport_api.upload_document(img_path)
        if not job_id:
            await update.message.reply_text("❌ Не вдалося обробити документ. Спробуйте ще раз.")
            return await suggest_manual_input(update.message)

        mindee_response = mindee_passport_api.get_result(job_id)
        if not mindee_response:
            await update.message.reply_text("⏳ Час очікування вичерпано або виникла помилка.")
            return await suggest_manual_input(update.message)

        save_mindee_response(job_id, mindee_response)
        passport_data = mindee_passport_api.extract_passport_data(mindee_response)
        
        if not passport_data:
            await update.message.reply_text("⚠ Не вдалося розпізнати дані з документу.")
            return await suggest_manual_input(update.message)

        context.user_data['passport_data'] = passport_data
        return await show_data_for_confirmation(update.message, passport_data)

    except Exception as e:
        logger.error(f"Error in handle_photo: {e}", exc_info=True)
        await update.message.reply_text("❌ Сталася несподівана помилка. Спробуйте ще раз.")
        return AWAITING_PHOTO

async def suggest_manual_input(message) -> int:
    """Запит на ручне введення даних паспорта"""
    instructions = (
        "📝 Введіть дані паспорта у такому форматі:\n\n"
        "Прізвище\n"
        "Ім'я\n"
        "Номер паспорта\n"
        "Громадянство\n"
        "Дата народження (РРРР-ММ-ДД)\n\n"
        "Приклад:\n"
        "Іванов\n"
        "Іван\n"
        "КМ123456\n"
        "Україна\n"
        "1990-05-15"
    )
    keyboard = [
        [InlineKeyboardButton("↩ Назад", callback_data="back_to_photo")],
        [InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]
    ]
    await message.reply_text(instructions, reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_MANUAL_DATA

async def show_data_for_confirmation(message, data: dict) -> int:
    """Підтвердження даних паспорта"""
    msg = (
        "📋 Виявлені дані:\n"
        f"▪ Прізвище: {data['surname']}\n"
        f"▪ Ім'я: {data['given_name']}\n"
        f"▪ Номер паспорта: {data['document_number']}\n"
        f"▪ Громадянство: {data['nationality']}\n"
        f"▪ Дата народження: {data['birth_date']}\n\n"
        "Ці дані вірні?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Так, все вірно", callback_data="confirm"),
            InlineKeyboardButton("✏ Виправити вручну", callback_data="edit")
        ],
        [
            InlineKeyboardButton("↩ Назад", callback_data="back_to_photo"),
            InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")
        ]
    ]
    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_CONFIRM

async def confirm_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Підтвердження даних паспорта"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("↩ Назад", callback_data="back_to_passport_confirm")],
        [InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]
    ]
    
    await query.edit_message_text(
        "✅ Дані паспорта підтверджено!\n\n"
        "Тепер будь ласка, надішліть фото першої сторінки техпаспорта (де вказаний номер реєстрації):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AWAITING_TECH_PASSPORT_1

async def edit_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Редагування даних паспорта"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏ Будь ласка, введіть дані паспорта вручну:")
    return await suggest_manual_input(query.message)

async def handle_manual_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка ручного введення даних паспорта"""
    try:
        parts = [line.strip() for line in update.message.text.split('\n') if line.strip()]
        if len(parts) != 5:
            raise ValueError("Потрібно ввести рівно 5 рядків з даними паспорта")
            
        context.user_data['passport_data'] = {
            'surname': parts[0],
            'given_name': parts[1],
            'passport_number': parts[2],
            'nationality': parts[3],
            'birth_date': parts[4],
            'tech_passport': None
        }
        
        keyboard = [
            [InlineKeyboardButton("↩ Назад", callback_data="back_to_passport_confirm")],
            [InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]
        ]
        
        await update.message.reply_text(
            "✅ Дані паспорта збережено!\n\n"
            "Тепер будь ласка, надішліть фото першої сторінки техпаспорта (де вказаний номер реєстрації):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AWAITING_TECH_PASSPORT_1
        
    except Exception as e:
        logger.error(f"Error in handle_manual_data: {e}")
        await update.message.reply_text("❌ Невірний формат даних. Будь ласка, введіть дані у вказаному форматі.")
        return AWAITING_MANUAL_DATA

async def handle_tech_passport_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка першої сторінки техпаспорта"""
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_path = f"downloads/tech_passport_1_{uuid.uuid4().hex}.jpg"
        await photo_file.download_to_drive(img_path)
        
        await update.message.reply_text("🔍 Обробляю першу сторінку техпаспорта...")
        
        job_id = mindee_vehicle_api.upload_document(img_path)
        if not job_id:
            await update.message.reply_text("❌ Не вдалося обробити техпаспорт. Спробуйте ще раз.")
            return AWAITING_TECH_PASSPORT_1

        mindee_response = mindee_vehicle_api.get_result(job_id)
        if not mindee_response:
            await update.message.reply_text("⏳ Час очікування вичерпано або виникла помилка.")
            return await suggest_manual_vehicle_input(update.message)

        vehicle_data = mindee_vehicle_api.extract_vehicle_data(mindee_response)
        
        if not vehicle_data:
            await update.message.reply_text("⚠ Не вдалося розпізнати дані з техпаспорта.")
            return await suggest_manual_vehicle_input(update.message)

        context.user_data['vehicle_data'] = vehicle_data
        
        keyboard = [
            [InlineKeyboardButton("↩ Назад", callback_data="back_to_passport_data")],
            [InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]
        ]
        
        await update.message.reply_text(
            "✅ Перша сторінка оброблена!\n\n"
            "Тепер будь ласка, надішліть фото другої сторінки техпаспорта (де вказані марка та VIN):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AWAITING_TECH_PASSPORT_2
        
    except Exception as e:
        logger.error(f"Error in handle_tech_passport_1: {e}")
        await update.message.reply_text("❌ Помилка при обробці техпаспорта. Спробуйте ще раз.")
        return AWAITING_TECH_PASSPORT_1

async def handle_tech_passport_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка другої сторінки техпаспорта"""
    try:
        photo_file = await update.message.photo[-1].get_file()
        img_path = f"downloads/tech_passport_2_{uuid.uuid4().hex}.jpg"
        await photo_file.download_to_drive(img_path)
        
        await update.message.reply_text("🔍 Обробляю другу сторінку техпаспорта...")
        
        job_id = mindee_vehicle_api.upload_document(img_path)
        if not job_id:
            await update.message.reply_text("❌ Не вдалося обробити техпаспорт. Спробуйте ще раз.")
            return AWAITING_TECH_PASSPORT_2

        mindee_response = mindee_vehicle_api.get_result(job_id)
        if not mindee_response:
            await update.message.reply_text("⏳ Час очікування вичерпано або виникла помилка.")
            return await suggest_manual_vehicle_input(update.message)

        additional_data = mindee_vehicle_api.extract_vehicle_data(mindee_response)
        
        if not additional_data:
            await update.message.reply_text("⚠ Не вдалося розпізнати дані з техпаспорта.")
            return await suggest_manual_vehicle_input(update.message)

        vehicle_data = context.user_data.get('vehicle_data', {})
        vehicle_data.update(additional_data)
        context.user_data['vehicle_data'] = vehicle_data
        
        if not vehicle_data.get('owner_name'):
            passport_data = context.user_data.get('passport_data', {})
            owner_name = f"{passport_data.get('given_name', '')} {passport_data.get('surname', '')}".strip()
            if owner_name:
                vehicle_data['owner_name'] = owner_name
        
        return await show_vehicle_data_for_confirmation(update.message, vehicle_data)
        
    except Exception as e:
        logger.error(f"Error in handle_tech_passport_2: {e}")
        await update.message.reply_text("❌ Помилка при обробці техпаспорта. Спробуйте ще раз.")
        return AWAITING_TECH_PASSPORT_2

async def suggest_manual_vehicle_input(message) -> int:
    """Запит на ручне введення даних техпаспорта"""
    instructions = (
        "📝 Введіть дані техпаспорта у такому форматі:\n\n"
        "Номер реєстрації\n"
        "Дата реєстрації (РРРР-ММ-ДД)\n"
        "VIN номер\n"
        "Марка автомобіля\n\n"
        "Приклад:\n"
        "АА1234ВВ\n"
        "2020-01-15\n"
        "JT2BF22K3W0123456\n"
        "Toyota Camry"
    )
    keyboard = [
        [InlineKeyboardButton("↩ Назад", callback_data="back_to_tech_passport_1")],
        [InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]
    ]
    await message.reply_text(instructions, reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_MANUAL_VEHICLE_DATA

async def handle_manual_vehicle_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка ручного введення даних техпаспорта"""
    try:
        parts = [line.strip() for line in update.message.text.split('\n') if line.strip()]
        if len(parts) != 4:
            raise ValueError("Потрібно ввести рівно 4 рядки з даними техпаспорта")
            
        context.user_data['vehicle_data'] = {
            'vehicle_registration_number': parts[0],
            'registration_date': parts[1],
            'vehicle_identification_number': parts[2],
            'make': parts[3],
            'owner_name': context.user_data['passport_data'].get('given_name', '') + ' ' + 
                         context.user_data['passport_data'].get('surname', ''),
            'insurance_details': []
        }
        
        return await show_vehicle_data_for_confirmation(update.message, context.user_data['vehicle_data'])
        
    except Exception as e:
        logger.error(f"Error in handle_manual_vehicle_data: {e}")
        await update.message.reply_text("❌ Невірний формат даних. Будь ласка, введіть дані у вказаному форматі.")
        return AWAITING_MANUAL_VEHICLE_DATA

async def show_vehicle_data_for_confirmation(message, data: dict) -> int:
    """Підтвердження даних техпаспорта"""
    data.setdefault('vehicle_registration_number', 'Не вказано')
    data.setdefault('registration_date', 'Не вказано')
    data.setdefault('owner_name', 'Не вказано')
    data.setdefault('vehicle_identification_number', 'Не вказано')
    data.setdefault('make', 'Не вказано')
    
    msg = (
        "📋 Виявлені дані техпаспорта:\n"
        f"▪ Номер реєстрації: {data['vehicle_registration_number']}\n"
        f"▪ Дата реєстрації: {data['registration_date']}\n"
        f"▪ Власник: {data['owner_name']}\n"
        f"▪ VIN: {data['vehicle_identification_number']}\n"
        f"▪ Марка: {data['make']}\n\n"
        "Ці дані вірні?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Так, все вірно", callback_data="confirm_vehicle"),
            InlineKeyboardButton("✏ Виправити вручну", callback_data="edit_vehicle")
        ],
        [
            InlineKeyboardButton("↩ Назад", callback_data="back_to_tech_passport_2"),
            InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")
        ]
    ]
    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_VEHICLE_CONFIRM

async def confirm_vehicle_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Підтвердження даних техпаспорта"""
    query = update.callback_query
    await query.answer()
    
    vehicle_data = context.user_data.get('vehicle_data', {})
    context.user_data['passport_data']['tech_passport'] = vehicle_data.get('vehicle_registration_number', '')
    
    return await show_agreement(query.message, context.user_data)

async def edit_vehicle_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Редагування даних техпаспорта"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏ Будь ласка, введіть дані техпаспорта вручну:")
    return AWAITING_MANUAL_VEHICLE_DATA

async def show_agreement(message, data: dict) -> int:
    """Відображення умов страхування"""
    vehicle_data = data.get('vehicle_data', {})
    
    msg = (
        "📝 Умови страхування:\n\n"
        f"🚗 Дані автомобіля:\n"
        f"- Номер: {vehicle_data.get('vehicle_registration_number', 'Невідомо')}\n"
        f"- Марка: {vehicle_data.get('make', 'Невідомо')}\n"
        f"- VIN: {vehicle_data.get('vehicle_identification_number', 'Невідомо')}\n\n"
        "💳 Умови страхування:\n"
        "1. Вартість: 100 USD на рік\n"
        "2. Термін дії: 1 рік\n"
        "3. Покриття: базове\n\n"
        "Ви погоджуєтесь з умовами?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Так, погоджуюсь", callback_data="agree"),
            InlineKeyboardButton("❌ Відхилити", callback_data="decline")
        ],
        [
            InlineKeyboardButton("↩ Назад", callback_data="back_to_vehicle_confirm"),
            InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")
        ]
    ]
    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAITING_AGREEMENT

async def handle_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка відповіді на умови страхування"""
    query = update.callback_query
    await query.answer()

    if query.data == "decline":
        await query.edit_message_text("Добре, якщо передумаєте — я тут! Просто напишіть /start.")
        keyboard = [[InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]]
        return ConversationHandler.END

    elif query.data == "agree":
        await query.edit_message_text("🔄 Генерую страховий поліс...")
        
        policy_text = await groq_service.generate_insurance_policy(context.user_data)
        passport_data = context.user_data.get('passport_data', {})
        txt_path = generate_policy_filename(passport_data)
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(policy_text)

        await query.edit_message_text("✅ Ваш страховий поліс сформовано:")
        
        with open(txt_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=f"Страховий_поліс_{passport_data.get('given_name', '')}_{passport_data.get('surname', '')}.txt",
                caption="Ваш страховий поліс у форматі TXT"
            )
        
        os.remove(txt_path)
        
        return ConversationHandler.END

async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробка кнопок 'Назад'"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_photo":
        await query.edit_message_text("Надішліть фото вашого паспорта для розпізнавання даних.")
        return AWAITING_PHOTO
        
    elif query.data == "back_to_passport_confirm":
        return await show_data_for_confirmation(query.message, context.user_data.get('passport_data', {}))
        
    elif query.data == "back_to_tech_passport_1":
        await query.edit_message_text(
            "Будь ласка, надішліть фото першої сторінки техпаспорта (де вказаний номер реєстрації):"
        )
        return AWAITING_TECH_PASSPORT_1
        
    elif query.data == "back_to_tech_passport_2":
        await query.edit_message_text(
            "Будь ласка, надішліть фото другої сторінки техпаспорта (де вказані марка та VIN):"
        )
        return AWAITING_TECH_PASSPORT_2
        
    elif query.data == "back_to_vehicle_confirm":
        return await show_vehicle_data_for_confirmation(query.message, context.user_data.get('vehicle_data', {}))
        
    elif query.data == "back_to_passport_data":
        return await show_data_for_confirmation(query.message, context.user_data.get('passport_data', {}))
        
    elif query.data == "restart":
        context.user_data.clear()
        await query.edit_message_text("Починаємо з початку...")
        return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Скасування розмови"""
    keyboard = [[InlineKeyboardButton("🔄 Почати з початку", callback_data="restart")]]
    await update.message.reply_text(
        "❌ Операцію скасовано.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

def get_conversation_handler():
    """Створення обробника розмови"""
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AWAITING_PHOTO: [
                MessageHandler(filters.PHOTO, handle_photo),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_CONFIRM: [
                CallbackQueryHandler(confirm_data, pattern='^confirm$'),
                CallbackQueryHandler(edit_data, pattern='^edit$'),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_MANUAL_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_data),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_TECH_PASSPORT_1: [
                MessageHandler(filters.PHOTO, handle_tech_passport_1),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_TECH_PASSPORT_2: [
                MessageHandler(filters.PHOTO, handle_tech_passport_2),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_MANUAL_VEHICLE_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_vehicle_data),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_VEHICLE_CONFIRM: [
                CallbackQueryHandler(confirm_vehicle_data, pattern='^confirm_vehicle$'),
                CallbackQueryHandler(edit_vehicle_data, pattern='^edit_vehicle$'),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
            AWAITING_AGREEMENT: [
                CallbackQueryHandler(handle_agreement, pattern='^(agree|decline)$'),
                CallbackQueryHandler(handle_back_button, pattern="^(restart|back_to_)"),
                CommandHandler('cancel', cancel)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )