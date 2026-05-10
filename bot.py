from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import vk_api
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.upload import VkUpload

# ========== КОНФИГУРАЦИЯ ==========
group_token = "vk1.a.QBG637PbpalZlGyTBfrthxc2htux8xoPaII8M5o6Uaxx0RP6U0Fk7O8oMEjxh6ude5smg6ctIE0zI5HUdpfzOxvOaIcZ2JlBGjYOgcZo2ZQuTanBCH_gDCfwJ-ek5YttN_qgfrq9OBHrpMz-mlxojnOpE53QplEXnqhkzKt5WS30-BKeDVfp5OFUeU-H9FW4XxwOJWnIabnIz4JEvu-6Lw"
group_id = 238456927
cd_min = 30
interval_sec = 0.01
admin_ids: list[int] = []
dev_ids: list[int] = [574393629]

# Конфигурация для отправки сообщений
MESSAGE_CONFIG = {
    'text': ".",
    'photo_path': "photos/main_photo.jpg",
    'chat_ids': [
        2000000004, 2000000008, 2000000009, 2000000013, 2000000015, 2000000016,
        2000000017, 2000000018, 2000000020, 2000000021, 2000000022, 2000000023,
        2000000024, 2000000025, 2000000026, 2000000027, 2000000028, 2000000029,
        2000000030, 2000000031, 2000000032, 2000000033, 2000000034, 2000000035,
        2000000036, 2000000037, 2000000038, 2000000039, 2000000040, 2000000041,
        2000000042, 2000000043, 2000000044, 2000000045, 2000000046, 2000000047,
        2000000048, 2000000050, 2000000051, 2000000052, 2000000053, 2000000054,
        2000000055, 2000000056, 2000000057, 2000000058, 2000000059, 2000000060,
        2000000061, 2000000062, 2000000063, 2000000064, 2000000065, 2000000066,
        2000000067, 2000000068, 2000000069, 2000000070, 2000000071, 2000000072,
        2000000073, 2000000074, 2000000075, 2000000076, 2000000077, 2000000078,
        2000000079, 2000000080, 2000000081, 2000000082, 2000000083, 2000000084,
        2000000085, 2000000086, 2000000087, 2000000088, 2000000089, 2000000090,
        2000000091, 2000000092, 2000000093, 2000000094, 2000000095, 2000000096,
        2000000097, 2000000098, 2000000099, 2000000100, 2000000101, 2000000102,
        2000000103, 2000000104, 2000000105, 2000000106, 2000000107, 2000000108,
        2000000109, 2000000110, 2000000111, 2000000112, 2000000113, 2000000114,
        2000000115, 2000000116, 2000000117, 2000000118, 2000000119, 2000000120,
        2000000121, 2000000122, 2000000123, 2000000124, 2000000125, 2000000126,
        2000000127, 2000000128, 2000000129, 2000000130, 2000000131, 2000000132,
        2000000133, 2000000134, 2000000135, 2000000136, 2000000137, 2000000138,
        2000000139, 2000000140, 2000000141, 2000000142, 2000000143, 2000000144,
        2000000145, 2000000146, 2000000147, 2000000148, 2000000149, 2000000150
    ],
    'admin_chat': 2000000001
}

# ========== ЛОГГЕР ==========
def get_logger(name: str = "vk_bot") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_path = Path(__file__).resolve().parent / "bot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger

logger = get_logger()

# ========== РАБОТА С JSON ==========
_LOCKS: dict[str, threading.RLock] = {}

def _get_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    if key not in _LOCKS:
        _LOCKS[key] = threading.RLock()
    return _LOCKS[key]

def read_json(path: Path, default: Any) -> Any:
    lock = _get_lock(path)
    with lock:
        if not path.exists():
            return default.copy() if isinstance(default, dict) else (default[:] if isinstance(default, list) else default)
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default.copy() if isinstance(default, dict) else (default[:] if isinstance(default, list) else default)

def write_json_atomic(path: Path, data: Any) -> None:
    lock = _get_lock(path)
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=4)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

def ensure_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        write_json_atomic(path, default)
    return read_json(path, default)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
OWNER_ID = 574393629
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data.json"
USERS_DB_PATH = BASE_DIR / "users_db.json"

# Загружаем данные
ensure_json_file(DATA_PATH, MESSAGE_CONFIG)
ensure_json_file(USERS_DB_PATH, {})

runtime_data = read_json(DATA_PATH, MESSAGE_CONFIG)
chat_ids = runtime_data.get("chat_ids", MESSAGE_CONFIG.get("chat_ids", []))
admin_chat = runtime_data.get("admin_chat", MESSAGE_CONFIG.get("admin_chat"))
message_text = runtime_data.get("message_text", MESSAGE_CONFIG.get("text", ""))
message_photo_path = runtime_data.get("photo_path", MESSAGE_CONFIG.get("photo_path"))

# Инициализация VK
vk_session = vk_api.VkApi(token=group_token)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, group_id)
vk_upload = VkUpload(vk_session)

# Потоки
broadcast_thread: threading.Thread | None = None
broadcast_lock = threading.Lock()
auto_broadcast_thread: threading.Thread | None = None
last_broadcast_time = time.time()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def generate_random_id() -> int:
    return int(time.time() * 1000000) % (2**31 - 1)

def load_users() -> dict[str, Any]:
    return read_json(USERS_DB_PATH, {})

def save_users(data: dict[str, Any]) -> None:
    write_json_atomic(USERS_DB_PATH, data)

def get_role(user_id: int) -> str | None:
    if user_id in dev_ids:
        return "dev"
    if user_id in admin_ids:
        return "admin"
    users = load_users()
    return users.get(str(user_id), {}).get("role")

def has_permission(user_id: int, level: str) -> bool:
    role = get_role(user_id)
    if level == "dev":
        return role == "dev"
    if level == "admin":
        return role in {"admin", "dev"}
    return False

def update_user_stats(user_id: int, action: str) -> None:
    users = load_users()
    user = users.setdefault(
        str(user_id),
        {
            "role": "user",
            "osn_photo_count": 0,
            "osn_text_count": 0,
            "total_messages": 0,
            "last_message": "",
            "stats": {},
        },
    )
    stats = user.setdefault("stats", {})
    stats[action] = int(stats.get(action, 0) or 0) + 1
    stats["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if action == "osn_photo":
        user["osn_photo_count"] = int(user.get("osn_photo_count", 0) or 0) + 1
    elif action == "osn_text":
        user["osn_text_count"] = int(user.get("osn_text_count", 0) or 0) + 1
    elif action == "command":
        user["total_messages"] = int(user.get("total_messages", 0) or 0) + 1
    user["last_message"] = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {action}"
    save_users(users)

def save_runtime_data() -> None:
    runtime_data["chat_ids"] = chat_ids
    runtime_data["admin_chat"] = admin_chat
    runtime_data["message_text"] = message_text
    runtime_data["photo_path"] = message_photo_path
    write_json_atomic(DATA_PATH, runtime_data)

def remove_chat_from_broadcast_list(chat_id: int, reason: str) -> None:
    if chat_id == admin_chat:
        return
    if chat_id in chat_ids:
        chat_ids.remove(chat_id)
        save_runtime_data()
        logger.info(f"Chat {chat_id}: удалён из списка рассылки ({reason})")

def build_join_keyboard() -> str:
    keyboard = VkKeyboard(inline=True)
    keyboard.add_openlink_button(
        label="🔗 Присоединиться к нам!",
        link="https://vk.me/join/Bp/rS5GCao5gcWOOKtuX/qA7Uc4x0acv78g=",
    )
    return keyboard.get_keyboard()

def get_help_text(role: str | None) -> str:
    user_commands = (
        "📋 ОСНОВНЫЕ КОМАНДЫ:\n"
        "🔹 .пинг — проверить, работает ли бот\n"
        "🔹 .стата — посмотреть свою статистику\n"
        "🔹 .хелп — показать это сообщение\n\n"
    )
    admin_commands = (
        "👑 АДМИН КОМАНДЫ:\n"
        "🔹 .рассылка — запустить рассылку\n"
        "🔹 .список — показать количество чатов\n"
        "🔹 .ид — узнать ID текущего чата\n"
        "🔹 .инфо — показать текущие настройки\n"
        "🔹 .тест — отправить тестовое сообщение\n"
        "🔹 .уст — добавить текущий чат в рассылку\n"
        "🔹 .инфочат — получить информацию о чате\n"
        "🔹 .добид [число] — добавить ID в список\n"
        "🔹 .делид [число] — удалить ID с конца списка\n\n"
    )
    dev_commands = (
        "🔧 DEV КОМАНДЫ:\n"
        "🔹 .админ [@] — выдать/снять права админа\n"
        "🔹 .разраб [@] — выдать/снять права разработчика\n"
        "🔹 .редоснтекст [текст] — изменить текст рассылки\n"
        "🔹 .редоснфото — изменить фото рассылки\n"
        "🔹 .gzov — разослать сообщение во все чаты\n"
        "🔹 .стафф — показать персонал\n"
        "🔹 .админчат — установить админ-чат\n"
    )
    full_text = user_commands
    if role in {"admin", "dev"}:
        full_text += admin_commands
    if role == "dev":
        full_text += dev_commands
    return full_text

def get_user_display_name(user_id: int) -> str:
    try:
        user_info = vk.users.get(user_ids=user_id)[0]
        return f"{user_info['first_name']} {user_info['last_name']}"
    except Exception:
        return f"Пользователь {user_id}"

def render_user_stats_detailed(user_id: int) -> str:
    users = load_users()
    user = users.get(str(user_id), {})
    stats = user.get("stats", {})
    total_commands = int(user.get("total_messages", stats.get("command", 0)) or 0)
    role_names = {"user": "Пользователь", "admin": "Администратор", "dev": "Разработчик"}
    role_display = role_names.get(user.get("role", "user"), "Пользователь")
    return (
        f"👤 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:\n\n"
        f"🔹 Имя: {get_user_display_name(user_id)}\n"
        f"🔹 Роль: {role_display}\n"
        f"🔹 Изменений текста/фото: {int(user.get('osn_text_count', 0) or 0) + int(user.get('osn_photo_count', 0) or 0)}\n"
        f"🔹 Всего команд: {total_commands}\n"
        f"🔹 Последнее действие: {user.get('last_message', 'Неизвестно')}"
    )

def render_staff_detailed() -> str:
    users = load_users()
    devs = []
    admins = []
    try:
        owner_info = vk.users.get(user_ids=OWNER_ID)[0]
        owner_name = f"{owner_info['first_name']} {owner_info['last_name']}"
        devs.append(f"• [id{OWNER_ID}|{owner_name}]")
    except Exception:
        devs.append(f"• [id{OWNER_ID}|Разработчик]")
    for uid, data in users.items():
        if data.get("role") == "admin":
            try:
                info = vk.users.get(user_ids=int(uid))[0]
                name = f"{info['first_name']} {info['last_name']}"
                admins.append(f"• [id{uid}|{name}]")
            except Exception:
                admins.append(f"• [id{uid}|Администратор]")
    return "🔧 ПЕРСОНАЛ БОТА:\n\nРАЗРАБОТЧИК:\n" + "\n".join(devs) + "\n\nАДМИНИСТРАТОРЫ:\n" + ("\n".join(admins) if admins else "Нет назначенных администраторов")

def render_runtime_info() -> str:
    return (
        "📊 НАСТРОЙКИ БОТА\n\n"
        f"⏱️ Интервал рассылки: {cd_min} минут\n"
        f"⚡ Пауза между сообщениями: {interval_sec} сек\n"
        f"📝 Текст рассылки:\n{message_text if message_text else '<пусто>'}"
    )

def save_config_value(name: str, value_repr: str) -> None:
    """Сохраняет настройки в config.py (для совместимости)"""
    config_path = BASE_DIR / "config.py"
    if not config_path.exists():
        return
    lines = config_path.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(f"{name} ="):
            new_lines.append(f"{name} = {value_repr}")
            updated = True
        else:
            new_lines.append(line)
    if updated:
        config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def send_message(chat_id: int, text: str, attachment: str | None = None, keyboard: str | None = None) -> Any:
    params = {"peer_id": chat_id, "message": text or " ", "random_id": generate_random_id()}
    if attachment:
        params["attachment"] = attachment
    if keyboard:
        params["keyboard"] = keyboard
    try:
        return vk.messages.send(**params)
    except Exception as exc:
        error_text = str(exc)
        error_lower = error_text.lower()
        if "the user was kicked out of the conversation" in error_lower:
            remove_chat_from_broadcast_list(chat_id, "участник исключён из беседы")
            return None
        if "you are restricted to write to a chat" in error_lower or "code 983" in error_lower:
            remove_chat_from_broadcast_list(chat_id, "ограничение на запись")
            return None
        if "ошибка доступа" in error_lower or "access denied" in error_lower:
            logger.warning(f"Chat {chat_id}: ошибка доступа")
            return "access_error"
        logger.error(f"Ошибка отправки в чат {chat_id}: {exc}")
        return None

def upload_message_photo() -> str | None:
    if not message_photo_path:
        logger.warning("message_photo_path пуст")
        return None
    
    if isinstance(message_photo_path, str) and message_photo_path.startswith(("photo", "doc", "video")):
        return message_photo_path
    
    photo_path = Path(message_photo_path)
    if not photo_path.is_absolute():
        photo_path = BASE_DIR / photo_path
    
    if not photo_path.exists():
        logger.error(f"Файл не существует: {photo_path}")
        return None
    
    try:
        photo = vk_upload.photo_messages(str(photo_path))[0]
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        logger.info(f"Фото загружено: {attachment}")
        return attachment
    except Exception as e:
        logger.error(f"Ошибка загрузки фото: {e}")
        return None

def save_main_photo_from_message(message: dict[str, Any]) -> tuple[bool, str]:
    global message_photo_path
    attachments = message.get("attachments") or []
    if not attachments:
        return False, "Прикрепите фото к сообщению с командой .редоснфото"
    
    photo_attachment = None
    for item in attachments:
        if item.get("type") == "photo":
            photo_attachment = item["photo"]
            break
    
    if not photo_attachment:
        return False, "Поддерживается только фото."

    sizes = photo_attachment.get("sizes") or []
    if not sizes:
        return False, "Не удалось получить размеры фото."
    
    best = max(sizes, key=lambda x: x.get("width", 0) * x.get("height", 0))
    url = best.get("url")
    if not url:
        return False, "Не удалось получить ссылку на фото."

    photos_dir = BASE_DIR / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = photos_dir / "main_photo.jpg"
    
    try:
        with urlopen(url) as response:
            target.write_bytes(response.read())
    except Exception as exc:
        return False, f"Не удалось сохранить фото: {exc}"

    message_photo_path = "photos/main_photo.jpg"
    save_runtime_data()
    return True, "✅ Основное фото бота успешно обновлено."

def send_broadcast_to_chat(chat_id: int) -> str | None:
    logger.info(f"Рассылка: отправка в чат {chat_id}")
    if message_text:
        result = send_message(
            chat_id,
            message_text,
            attachment=upload_message_photo(),
            keyboard=build_join_keyboard(),
        )
        if result == "access_error":
            return "access_error"
        time.sleep(interval_sec)
    return None

def broadcast_message(notify_chat_id: int | None = None) -> None:
    target_chats = [cid for cid in chat_ids if admin_chat is not None and cid != admin_chat and len(str(cid)) == 10 and str(cid).startswith("2")]
    logger.info(f"Рассылка запущена. Чатов: {len(target_chats)}")
    
    if not target_chats:
        if notify_chat_id:
            send_message(notify_chat_id, "⚠️ Список чатов пуст.")
        return
    
    sent_count = 0
    try:
        for chat_id in target_chats:
            result = send_broadcast_to_chat(chat_id)
            if result == "access_error":
                break
            sent_count += 1
        
        if notify_chat_id:
            send_message(notify_chat_id, f"✅ Рассылка завершена. Отправлено: {sent_count}")
    except Exception as exc:
        logger.exception(f"Ошибка рассылки: {exc}")
        if notify_chat_id:
            send_message(notify_chat_id, f"❌ Ошибка: {exc}")

def start_broadcast(notify_chat_id: int | None = None) -> None:
    global broadcast_thread
    with broadcast_lock:
        if broadcast_thread and broadcast_thread.is_alive():
            logger.info("Рассылка уже активна")
            return
        broadcast_thread = threading.Thread(target=broadcast_message, kwargs={"notify_chat_id": notify_chat_id}, daemon=True)
        broadcast_thread.start()

def send_gzov_to_chat(chat_id: int) -> Any:
    logger.info(f"GZOV: отправка в чат {chat_id}")
    return send_message(
        chat_id,
        message_text,
        attachment=upload_message_photo(),
        keyboard=build_join_keyboard(),
    )

def broadcast_gzov(notify_chat_id: int | None = None) -> None:
    target_chats = [cid for cid in chat_ids if admin_chat is not None and cid != admin_chat and len(str(cid)) == 10 and str(cid).startswith("2")]
    logger.info(f"GZOV запущен. Чатов: {len(target_chats)}")
    
    if not target_chats:
        if notify_chat_id:
            send_message(notify_chat_id, "⚠️ Список чатов пуст.")
        return
    
    sent_count = 0
    try:
        for chat_id in target_chats:
            result = send_gzov_to_chat(chat_id)
            if result == "access_error":
                break
            sent_count += 1
            time.sleep(interval_sec)
        
        if notify_chat_id:
            send_message(notify_chat_id, f"✅ GZOV завершён. Отправлено: {sent_count}")
    except Exception as exc:
        logger.exception(f"Ошибка GZOV: {exc}")
        if notify_chat_id:
            send_message(notify_chat_id, f"❌ Ошибка: {exc}")

def start_gzov(notify_chat_id: int | None = None) -> None:
    thread = threading.Thread(target=broadcast_gzov, kwargs={"notify_chat_id": notify_chat_id}, daemon=True)
    thread.start()

def auto_broadcast_loop() -> None:
    global last_broadcast_time
    while True:
        try:
            if time.time() - last_broadcast_time >= cd_min * 60:
                logger.info("Автоматическая рассылка по таймеру")
                start_broadcast()
                last_broadcast_time = time.time()
        except Exception as exc:
            logger.error(f"Ошибка авторассылки: {exc}")
        time.sleep(5)

def resolve_user_id(token: str) -> int | None:
    token = token.strip()
    mention_match = re.match(r"\[id(\d+)\|", token)
    if mention_match:
        return int(mention_match.group(1))
    direct_id = re.match(r"id(\d+)$", token, re.IGNORECASE)
    if direct_id:
        return int(direct_id.group(1))
    if token.startswith("@"):
        token = token[1:]
    try:
        user = vk.users.get(user_ids=token)
        if user:
            return int(user[0]["id"])
    except Exception as exc:
        logger.warning(f"Не удалось разрешить пользователя {token}: {exc}")
    return None

def extract_target_user(message: dict[str, Any], text: str) -> int | None:
    reply_message = message.get("reply_message")
    if isinstance(reply_message, dict) and reply_message.get("from_id"):
        return int(reply_message["from_id"])
    for raw_part in (text or "").replace("\n", " ").split():
        part = raw_part.strip(",")
        mention_match = re.match(r"\[id(\d+)\|", part)
        if mention_match:
            return int(mention_match.group(1))
        if part.startswith("@"):
            resolved = resolve_user_id(part[1:])
            if resolved:
                return resolved
        direct_id = re.match(r"id(\d+)$", part, re.IGNORECASE)
        if direct_id:
            return int(direct_id.group(1))
        if "vk.com/" in part or "vk.ru/" in part:
            tail = part.rstrip("/").split("/")[-1]
            resolved = resolve_user_id(tail)
            if resolved:
                return resolved
    return None

# ========== ОСНОВНОЙ ЦИКЛ ==========
def main() -> None:
    global admin_chat, message_text, cd_min, interval_sec, auto_broadcast_thread, last_broadcast_time
    
    logger.info("=" * 50)
    logger.info("БОТ ЗАПУЩЕН (режим: рассылка с кнопкой)")
    logger.info("=" * 50)
    
    # Проверка подключения
    try:
        vk_session.get_api()
        logger.info("✅ Успешное подключение к VK API")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        return
    
    last_broadcast_time = time.time()
    
    if auto_broadcast_thread is None or not auto_broadcast_thread.is_alive():
        auto_broadcast_thread = threading.Thread(target=auto_broadcast_loop, daemon=True)
        auto_broadcast_thread.start()
        logger.info("✅ Поток авторассылки запущен")

    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue
        
        message = event.obj.message
        chat_id = message.get("peer_id")
        user_id = message.get("from_id")
        text = (message.get("text") or "").strip().lower()

        # Игнорируем ЛС
        if chat_id == user_id:
            continue

        # Проверка прав (только админ-чат)
        if chat_id != admin_chat and not has_permission(user_id, "admin"):
            continue

        # ========== КОМАНДЫ ==========
        
        if text == ".пинг":
            start_time = time.time()
            send_message(chat_id, "🏓 Понг!")
            end_time = time.time()
            ping_ms = int((end_time - start_time) * 1000)
            send_message(chat_id, f"⏱️ Пинг: {ping_ms} мс")
            update_user_stats(user_id, "command")
            continue

        if text == ".хелп":
            role = get_role(user_id)
            send_message(chat_id, get_help_text(role))
            update_user_stats(user_id, "command")
            continue

        if text.startswith(".стата"):
            target = extract_target_user(message, text) or user_id
            send_message(chat_id, render_user_stats_detailed(target))
            update_user_stats(user_id, "command")
            continue

        if text == ".список":
            total = len(chat_ids)
            preview = "\n".join(str(cid) for cid in chat_ids[:10] if cid != admin_chat)
            msg = f"📊 Чатов в рассылке: {total}\n\nПервые 10:\n{preview}"
            if total > 10:
                msg += f"\n... и ещё {total - 10}"
            send_message(chat_id, msg)
            update_user_stats(user_id, "command")
            continue

        if text == ".ид":
            send_message(chat_id, f"🆔 ID этой беседы: {chat_id}")
            update_user_stats(user_id, "command")
            continue

        if text == ".инфо":
            send_message(chat_id, render_runtime_info())
            update_user_stats(user_id, "command")
            continue

        if text == ".уст":
            if len(str(chat_id)) == 10 and str(chat_id).startswith("2"):
                if chat_id not in chat_ids:
                    chat_ids.append(chat_id)
                    save_runtime_data()
                    send_message(chat_id, "✅ Чат добавлен в рассылку")
                else:
                    send_message(chat_id, "❌ Чат уже в списке")
            else:
                send_message(chat_id, "❌ Это не беседа")
            update_user_stats(user_id, "command")
            continue

        if text == ".инфочат":
            send_message(chat_id, f"📋 О чате:\nID: {chat_id}\nАдмин-чат: {admin_chat}")
            update_user_stats(user_id, "command")
            continue

        if text.startswith(".добид"):
            parts = text.split()
            if len(parts) < 2:
                send_message(chat_id, "❌ .добид [число]")
                continue
            try:
                count = int(parts[1])
                if count <= 0:
                    raise ValueError
            except ValueError:
                send_message(chat_id, "❌ Нужно положительное число")
                continue
            
            bot_chats = [cid for cid in chat_ids if str(cid).startswith("2") and len(str(cid)) == 10]
            next_id = max(bot_chats, default=2000000000) + 1
            for _ in range(count):
                chat_ids.append(next_id)
                next_id += 1
            save_runtime_data()
            send_message(chat_id, f"✅ Добавлено {count} чатов")
            update_user_stats(user_id, "command")
            continue

        if text.startswith(".делид"):
            parts = text.split()
            if len(parts) < 2:
                send_message(chat_id, "❌ .делид [число]")
                continue
            try:
                count = int(parts[1])
                if count <= 0:
                    raise ValueError
            except ValueError:
                send_message(chat_id, "❌ Нужно положительное число")
                continue
            
            bot_chats = [cid for cid in chat_ids if str(cid).startswith("2") and len(str(cid)) == 10]
            removed = 0
            for _ in range(min(count, len(bot_chats))):
                if bot_chats:
                    to_remove = bot_chats.pop()
                    if to_remove in chat_ids:
                        chat_ids.remove(to_remove)
                        removed += 1
            if removed:
                save_runtime_data()
            send_message(chat_id, f"✅ Удалено {removed} чатов")
            update_user_stats(user_id, "command")
            continue

        if text == ".тест":
            send_broadcast_to_chat(chat_id)
            update_user_stats(user_id, "command")
            continue

        if text == ".рассылка" and has_permission(user_id, "admin"):
            start_broadcast(notify_chat_id=chat_id)
            last_broadcast_time = time.time()
            send_message(chat_id, "✅ Рассылка запущена")
            update_user_stats(user_id, "command")
            continue

        if text == ".gzov" and has_permission(user_id, "dev"):
            start_gzov(notify_chat_id=chat_id)
            send_message(chat_id, "✅ GZOV запущен")
            update_user_stats(user_id, "command")
            continue

        if text == ".стафф" and user_id == OWNER_ID:
            send_message(chat_id, render_staff_detailed())
            update_user_stats(user_id, "command")
            continue

        if text == ".админчат" and has_permission(user_id, "dev"):
            admin_chat = chat_id
            save_runtime_data()
            send_message(chat_id, "✅ Админ-чат установлен")
            update_user_stats(user_id, "command")
            continue

        if text.startswith(".редоснтекст") and has_permission(user_id, "dev"):
            if chat_id != admin_chat:
                send_message(chat_id, "❌ Команда только в админ-чате")
                continue
            parts = text.split(" ", 1)
            if len(parts) < 2 or not parts[1].strip():
                send_message(chat_id, "❌ .редоснтекст [текст]")
                continue
            message_text = parts[1].strip()
            save_runtime_data()
            send_message(chat_id, "✅ Текст обновлён")
            update_user_stats(user_id, "osn_text")
            continue

        if text == ".редоснфото" and has_permission(user_id, "dev"):
            if chat_id != admin_chat:
                send_message(chat_id, "❌ Команда только в админ-чате")
                continue
            ok, result = save_main_photo_from_message(message)
            send_message(chat_id, result)
            if ok:
                update_user_stats(user_id, "osn_photo")
            continue

        if text.startswith(".админ") and has_permission(user_id, "dev"):
            target = extract_target_user(message, text)
            if not target:
                send_message(chat_id, "❌ Укажите пользователя (ответом или @)")
                continue
            if user_id == target:
                send_message(chat_id, "❌ Нельзя изменить свою роль")
                continue
            
            users = load_users()
            user_key = str(target)
            if user_key not in users:
                users[user_key] = {"role": "user", "osn_photo_count": 0, "osn_text_count": 0, "total_messages": 0, "last_message": ""}
            
            if users[user_key].get("role") == "admin":
                users[user_key]["role"] = "user"
                save_users(users)
                send_message(chat_id, f"❌ Права админа сняты с {target}")
            else:
                users[user_key]["role"] = "admin"
                save_users(users)
                send_message(chat_id, f"✅ Пользователь {target} назначен админом")
            update_user_stats(user_id, "command")
            continue

        if text.startswith(".разраб") and user_id == OWNER_ID:
            target = extract_target_user(message, text)
            if not target:
                send_message(chat_id, "❌ Укажите пользователя")
                continue
            
            users = load_users()
            user_key = str(target)
            if user_key not in users:
                users[user_key] = {"role": "user", "osn_photo_count": 0, "osn_text_count": 0, "total_messages": 0, "last_message": ""}
            
            if users[user_key].get("role") == "dev":
                users[user_key]["role"] = "user"
                save_users(users)
                send_message(chat_id, f"❌ Права разработчика сняты с {target}")
            else:
                users[user_key]["role"] = "dev"
                save_users(users)
                send_message(chat_id, f"✅ Пользователь {target} назначен разработчиком")
            update_user_stats(user_id, "command")
            continue

if __name__ == "__main__":
    main()
