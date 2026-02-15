import logging
import re
import config
import asyncio
import time

from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import BadRequest
from datetime import datetime, time  # noqa: F811
import pytz
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

muted_users = {}
is_night_mode = False  # Флаг режима тишины
TIMEZONE = pytz.timezone("Europe/Moscow")  # Замените на ваш часовой пояс

bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Словарь для хранения предупреждений пользователей
user_warnings = {}
# Словарь для хранения выговоров пользователей
user_strikes = {}

WELCOME_MESSAGE = """
Привет, {new_user}! Добро пожаловать в нашу беседу!

Пожалуйста, ознакомьтесь с правилами:

1.  Уважайте всех участников чата.
2.  Не спамьте и не флудите.
3.  Не используйте нецензурную лексику.
4.  Обсуждайте только темы, относящиеся к тематике беседы.

Приятного общения!
"""


async def is_admin(user_id: int, chat_id: int):
    """Проверяет, является ли пользователь администратором чата."""
    member = await bot.get_chat_member(chat_id, user_id)
    logging.info(
        f"User ID: {user_id}, Chat ID: {chat_id}, is admin: {member.is_chat_admin()}"
    )
    return member.is_chat_admin()


# Команда БАН
@dp.message_handler(content_types=["text"], commands=["ban"], commands_prefix="!/")
async def cmd_ban(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Команда /ban <reply>")
        return

    username = message.reply_to_message.from_user.username
    if username:
        await message.reply_to_message.reply(f"Ничего личного, @{username}")
    else:
        await message.reply_to_message.reply("Ничего личного")

    await message.bot.delete_message(
        chat_id=config.GROUP_ID, message_id=message.message_id
    )
    await message.bot.kick_chat_member(
        chat_id=config.GROUP_ID, user_id=message.reply_to_message.from_user.id
    )


# Команда Mute
async def get_user_id_by_username(chat_id, username):
    """Получает ID пользователя по его имени."""
    try:
        chat = await bot.get_chat(chat_id)
        for member in await bot.get_chat_administrators(chat.id):
            if member.user.username == username:
                return member.user.id
    except Exception as e:
        logging.error(f"Error getting user by username: {e}")
    return None


@dp.message_handler(commands=["mute"], commands_prefix="!/")
async def mute_user(message: types.Message):
    if not await is_admin(message.from_user.id, message.chat.id):
        await message.reply("У вас нет прав для использования этой команды!")
        return

    if not message.reply_to_message and not message.text.split(" ")[1:]:
        await message.reply(
            "Используйте команду как ответ на сообщение пользователя, которого хотите замутить или укажите имя пользователя"
        )
        return

    try:
        user_id_to_mute = None
        args = message.text.split()

        if message.reply_to_message:
            user_id_to_mute = message.reply_to_message.from_user.id
            if len(args) < 2:
                await message.reply("Укажите время мута!")
                return
            time_str = args[1]
        else:
            if len(args) < 3:
                await message.reply(
                    "Неверный формат команды. Используйте /mute <@username> <время>"
                )
                return
            try:
                user_id_to_mute = int(args[1].replace("@", ""))
                user_id_to_mute = (
                    await bot.get_chat_member(message.chat.id, user_id_to_mute)
                ).user.id
            except (ValueError, BadRequest):
                await message.reply("Неверный формат пользователя. Укажите @username")
                return
            time_str = args[2]

        time_multiplier = 1
        if time_str[-1].lower() == "m":
            time_multiplier = 60
            time_str = time_str[:-1]
        elif time_str[-1].lower() == "h":
            time_multiplier = 60 * 60
            time_str = time_str[:-1]
        elif time_str[-1].lower() == "d":
            time_multiplier = 60 * 60 * 24
            time_str = time_str[:-1]
        try:
            mute_time = int(time_str)
        except ValueError:
            await message.reply("Неверный формат времени")
            return
        mute_duration = mute_time * time_multiplier
        until_date = int(time.time()) + mute_duration

        user_info = await bot.get_chat_member(message.chat.id, user_id_to_mute)

        if await is_admin(user_id_to_mute, message.chat.id):
            await message.reply("Нельзя замутить администратора!")
            return

        await bot.restrict_chat_member(
            message.chat.id,
            user_id_to_mute,
            types.ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        await message.reply(f"Пользователь {user_info.user.full_name} был замучен!")

    except BadRequest as e:
        logging.error(f"Ошибка при муте пользователя: {e}")
        await message.reply("Не удалось замутить пользователя. Проверьте права бота.")


# Команда UnMute
@dp.message_handler(commands=["unmute"], commands_prefix="!/")
async def unmute_user(message: types.Message):
    if not await is_admin(message.from_user.id, message.chat.id):
        await message.reply("У вас нет прав для использования этой команды!")
        return

    if not message.reply_to_message and not message.text.split(" ")[1:]:
        await message.reply(
            "Используйте команду как ответ на сообщение пользователя, которого хотите размутить или укажите имя пользователя или его ID"
        )
        return

    try:
        if message.reply_to_message:
            user_id_to_unmute = message.reply_to_message.from_user.id
        else:
            user_id_to_unmute = message.text.split(" ")[1]
            try:
                user_id_to_unmute = int(user_id_to_unmute)
            except ValueError:
                user_id_to_unmute = int(user_id_to_unmute.replace("@", ""))
                try:
                    user_id_to_unmute = (
                        await bot.get_chat_member(message.chat.id, user_id_to_unmute)
                    ).user.id
                except BadRequest:
                    await message.reply("Пользователь не найден")
                    return

        user_info = await bot.get_chat_member(message.chat.id, user_id_to_unmute)
        await bot.restrict_chat_member(
            message.chat.id,
            user_id_to_unmute,
            types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await message.reply(f"Пользователь {user_info.user.full_name} был размучен.")

    except BadRequest as e:
        logging.error(f"Ошибка при размуте пользователя: {e}")
        await message.reply("Не удалось размутить пользователя. Проверьте права бота.")


# Команда предупреждения и выговоров
@dp.message_handler(commands=["warn"], commands_prefix="!/")
async def warn_user(message: types.Message):
    if not await is_admin(message.from_user.id, message.chat.id):
        await message.reply("У вас нет прав для использования этой команды!")
        return

    if not message.reply_to_message:
        await message.reply(
            "Используйте команду /warn как ответ на сообщение пользователя."
        )
        return

    warned_user_id = message.reply_to_message.from_user.id
    warned_user_name = message.reply_to_message.from_user.username
    if warned_user_name:
        warn_message = f"Пользователь @{warned_user_name} получил предупреждение!"
    else:
        warn_message = f"Пользователь {message.reply_to_message.from_user.full_name} получил предупреждение!"

    if warned_user_id not in user_warnings:
        user_warnings[warned_user_id] = 0

    user_warnings[warned_user_id] += 1

    if user_warnings[warned_user_id] >= 3:
        if warned_user_id not in user_strikes:
            user_strikes[warned_user_id] = 0
        user_strikes[warned_user_id] += 1
        user_warnings[warned_user_id] = 0
        if user_strikes[warned_user_id] >= 3:
            await message.bot.kick_chat_member(
                chat_id=config.GROUP_ID, user_id=warned_user_id
            )
            if warned_user_name:
                await message.reply(
                    f"Пользователь @{warned_user_name} получил 3 выговора и заблокирован!"
                )
            else:
                await message.reply(
                    f"Пользователь {message.reply_to_message.from_user.full_name} получил 3 выговора и заблокирован!"
                )

            user_strikes[warned_user_id] = 0
            return
        else:
            if warned_user_name:
                warn_message = f"Пользователь @{warned_user_name} получил выговор. Осталось {3 - user_strikes[warned_user_id]} выговора до бана!"
            else:
                warn_message = f"Пользователь {message.reply_to_message.from_user.full_name} получил выговор. Осталось {3 - user_strikes[warned_user_id]} выговора до бана!"
    else:
        if warned_user_name:
            warn_message = f"У пользователя @{warned_user_name} {user_warnings[warned_user_id]}/3 предупреждений."
        else:
            warn_message = f"У пользователя {message.reply_to_message.from_user.full_name} {user_warnings[warned_user_id]}/3 предупреждений."

    # Создаем Inline кнопку для снятия предупреждения
    markup = InlineKeyboardMarkup()
    remove_button = InlineKeyboardButton(
        "Снять предупреждение", callback_data=f"remove_warn_{warned_user_id}"
    )
    markup.add(remove_button)

    await message.reply(warn_message, reply_markup=markup)


# Обработчик нажатия на кнопку снятия предупреждения
@dp.callback_query_handler(lambda query: query.data.startswith("remove_warn_"))
async def remove_warning_callback(query: types.CallbackQuery):
    user_id = int(query.data.split("_")[-1])
    if not await is_admin(query.from_user.id, query.message.chat.id):
        await query.answer("У вас нет прав для снятия предупреждений!", show_alert=True)
        return
    if user_id in user_warnings and user_warnings[user_id] > 0:
        user_warnings[user_id] -= 1
        await query.answer("Предупреждение снято!", show_alert=True)

        warned_user_info = await bot.get_chat_member(query.message.chat.id, user_id)
        if warned_user_info.user.username:
            warn_message = f"У пользователя @{warned_user_info.user.username} {user_warnings[user_id]}/3 предупреждений."
        else:
            warn_message = f"У пользователя {warned_user_info.user.full_name} {user_warnings[user_id]}/3 предупреждений."

        # Обновляем сообщение, меняя текст и убирая кнопки
        await bot.edit_message_text(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=warn_message,
            reply_markup=None,
        )
    else:
        await query.answer(
            "У пользователя нет предупреждений, которые можно снять.", show_alert=True
        )


# Команда для снятия выговора
@dp.message_handler(commands=["remove_warn"], commands_prefix="!/")
async def remove_strike(message: types.Message):
    if not await is_admin(message.from_user.id, message.chat.id):
        await message.reply("У вас нет прав для использования этой команды!")
        return

    if not message.reply_to_message:
        await message.reply(
            "Используйте команду /remove_strike как ответ на сообщение пользователя."
        )
        return

    user_id_to_remove_strike = message.reply_to_message.from_user.id
    user_name = message.reply_to_message.from_user.username
    if (
        user_id_to_remove_strike in user_strikes
        and user_strikes[user_id_to_remove_strike] > 0
    ):
        user_strikes[user_id_to_remove_strike] -= 1
        if user_name:
            await message.reply(
                f"Выговор пользователя @{user_name} снят. Осталось {user_strikes[user_id_to_remove_strike]} выговоров."
            )
        else:
            await message.reply(
                f"Выговор пользователя {message.reply_to_message.from_user.full_name} снят. Осталось {user_strikes[user_id_to_remove_strike]} выговоров."
            )

    else:
        if user_name:
            await message.reply(
                f"У пользователя @{user_name} нет выговоров или они уже сняты."
            )
        else:
            await message.reply(
                f"У пользователя {message.reply_to_message.from_user.full_name} нет выговоров или они уже сняты."
            )


# АнтиМат
def load_mat_words(file_path):
    mat = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                mat.append(line.strip().lower())
    except FileNotFoundError:
        print(f"Файл не найден: {file_path}")
    return mat


def contains_stop_words(text, mat):
    if not text:
        return "*"
    text = text.lower()
    for word in mat:
        text = re.sub(r"\b" + re.escape(word) + r"\b", "", text)
    return text


@dp.message_handler(content_types=["text"])
async def check_message(message: types.Message):
    global is_night_mode
    file_path = "MAT.txt"
    mat = load_mat_words(file_path)

    user_id = message.from_user.id
    chat_id = message.chat.id
    logging.info(
        f"Message received from {user_id}, text: {message.text}, is_night_mode: {is_night_mode}"
    )
    is_user_admin = await is_admin(user_id, chat_id)
    logging.info(f"Is User Admin: {is_user_admin}")
    if is_night_mode and not is_user_admin:
        logging.info(
            f"Deleting message from user {message.from_user.id} during night mode."
        )
        try:
            await message.delete()
            logging.info("Message deleted.")
            return
        except Exception as e:
            logging.error(f"Error deleting message: {e}")
            return

    if message.text:
        cleaned_text = contains_stop_words(message.text, mat)
        if cleaned_text and cleaned_text != message.text.lower():
            try:
                await message.answer(cleaned_text)  # посылаем новое сообщение
                await bot.delete_message(message.chat.id, message.message_id)
                print(
                    f"Сообщение с ID {message.message_id} изменено. Стоп-слова удалены."
                )
            except Exception as e:
                print(f"Ошибка: {e}")
        elif (
            not cleaned_text and cleaned_text != message.text.lower()
        ):  # Проверяем если cleaned_text пустой, но был текст.
            try:
                await bot.delete_message(
                    message.chat.id, message.message_id
                )  # удаляем оригинальное сообщение
                print(
                    f"Сообщение с ID {message.message_id} удалено. Так как содержит только стоп слова"
                )
            except Exception as e:
                print(f"Ошибка: {e}")
        else:
            print(f"Сообщение с ID {message.message_id} не содержит матов.")
    else:
        print(f"Сообщение с ID {message.message_id} не содержит текста.")


# Приветствие новых пользователей
@dp.message_handler(content_types=types.ContentTypes.NEW_CHAT_MEMBERS)
async def new_member_handler(message: types.Message):
    for new_member in message.new_chat_members:
        if new_member.id != bot.id:
            if new_member.username:
                welcome_text = WELCOME_MESSAGE.format(
                    new_user=f"@{new_member.username}"
                )
            else:
                welcome_text = WELCOME_MESSAGE.format(new_user=new_member.full_name)
            await message.reply(welcome_text, parse_mode="HTML")


# Night | Day
async def check_time_for_night_mode():
    global is_night_mode
    while True:
        now = datetime.now(TIMEZONE).time()
        logging.info(f"Current time: {now}, is_night_mode: {is_night_mode}")
        if time(22, 0) <= now or now < time(8, 0) and not is_night_mode:
            is_night_mode = True
            logging.info("Night mode activated.")
        elif not (time(23, 0) <= now or now < time(8, 0)) and is_night_mode:
            is_night_mode = False
            logging.info("Night mode deactivated.")
        await asyncio.sleep(60)


async def on_startup(dp):
    asyncio.create_task(check_time_for_night_mode())
    print("Бот запущен...")
    print(f"Текущее время на сервере: {datetime.now(TIMEZONE)}")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
