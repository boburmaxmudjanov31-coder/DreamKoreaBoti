import asyncio
import json
import logging
import os
import re
import random
import sqlite3
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = "8966452192:AAHnq4FynE-o7okwsA5meElUljlBeHhvhug"
OPENROUTER_API_KEY = "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"
ADMIN_IDS = {2135267704,1957007666}

AI_PRIMARY_MODEL = "openai/gpt-4o-mini"
AI_FALLBACK_MODELS = [
    "anthropic/claude-3.5-sonnet",
    "google/gemini-2.0-flash-001",
]
AI_COOLDOWN_SECONDS = 3
AI_MAX_CONTEXT = 20
AI_MAX_INPUT = 12000
AI_TIMEOUT = 60

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dreamkorea.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("dreamkorea")

# ============================================================
# DATABASE
# ============================================================
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("PRAGMA foreign_keys = ON")
db.execute("PRAGMA journal_mode = WAL")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def month_now():
    return datetime.now().strftime("%Y-%m")


def db_exec(sql, params=()):
    cur = db.execute(sql, params)
    db.commit()
    return cur.lastrowid


def db_one(sql, params=()):
    return db.execute(sql, params).fetchone()


def db_all(sql, params=()):
    return db.execute(sql, params).fetchall()


def db_init():
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            role TEXT NOT NULL DEFAULT 'USER',
            ai_active INTEGER NOT NULL DEFAULT 0,
            ai_last_request REAL NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins (
            telegram_id INTEGER PRIMARY KEY,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_code TEXT UNIQUE NOT NULL,
            telegram_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            father_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            passport TEXT,
            address TEXT NOT NULL,
            lesson_time TEXT NOT NULL,
            lesson_days TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            group_id INTEGER,
            teacher_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_code TEXT UNIQUE NOT NULL,
            telegram_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            topik_level TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS groups_ (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lesson_time TEXT NOT NULL,
            lesson_days TEXT NOT NULL,
            teacher_id INTEGER,
            telegram_group_id INTEGER,
            monthly_fee INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id)
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_code TEXT UNIQUE NOT NULL,
            telegram_id INTEGER UNIQUE NOT NULL,
            application_id INTEGER,
            group_id INTEGER,
            teacher_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            joined_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id),
            FOREIGN KEY(group_id) REFERENCES groups_(id),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('present','absent')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(student_id,date),
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(group_id) REFERENCES groups_(id),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id)
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            teacher_id INTEGER,
            month TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'paid',
            paid_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(student_id,month),
            FOREIGN KEY(student_id) REFERENCES students(id),
            FOREIGN KEY(group_id) REFERENCES groups_(id),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id)
        );
        CREATE TABLE IF NOT EXISTS content_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            emoji TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            media_type TEXT,
            file_id TEXT,
            external_url TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(category_id) REFERENCES content_categories(id)
        );
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            media_type TEXT,
            file_id TEXT,
            external_url TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(content_id,episode_number),
            FOREIGN KEY(content_id) REFERENCES contents(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS homeworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            text TEXT,
            media_type TEXT,
            file_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id),
            FOREIGN KEY(group_id) REFERENCES groups_(id)
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS advertising_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES ai_conversations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            model TEXT,
            success INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            response_time REAL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS random_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS random_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL,
            korean TEXT NOT NULL,
            uzbek TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(section_id, korean, uzbek),
            FOREIGN KEY(section_id) REFERENCES random_sections(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_students_group ON students(group_id);
        CREATE INDEX IF NOT EXISTS idx_students_teacher ON students(teacher_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);
        CREATE INDEX IF NOT EXISTS idx_payments_month ON payments(month);
        CREATE INDEX IF NOT EXISTS idx_contents_category ON contents(category_id);
        CREATE INDEX IF NOT EXISTS idx_episodes_content ON episodes(content_id);
        CREATE INDEX IF NOT EXISTS idx_homeworks_group ON homeworks(group_id);
        CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation ON ai_messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_random_words_section ON random_words(section_id);
        CREATE INDEX IF NOT EXISTS idx_random_sections_active ON random_sections(active);
        """
    )
    db.commit()
    defaults = [
        ("KOREAN_BOOKS", "KOREYSCHA KITOBLAR", "🇰🇷", 1),
        ("WRITING_BOOKS", "쓰기 KITOBLAR", "✍️", 2),
        ("TOPIK_TESTS", "TOPIK TESTLAR", "🏆", 3),
        ("GRAMMAR_BOOKS", "GRAMMATIK KITOBLAR", "📚", 4),
        ("TOPIK_BOOKS", "TOPIK KITOBLAR", "📘", 5),
        ("KOREAN_DICTIONARY", "KOREYS TILI LUG‘ATLARI", "📕", 6),
        ("EPS_TOPIK", "EPS-TOPIK", "🧰", 7),
        ("MOVIES", "KINOLAR", "🎬", 8),
        ("SERIES", "SERIALLAR", "🎞", 9),
        ("USEFUL_APPS", "FOYDALI DASTURLAR", "📱", 10),
    ]
    for item in defaults:
        db.execute("INSERT OR IGNORE INTO content_categories(key,name,emoji,sort_order) VALUES(?,?,?,?)", item)
    for admin_id in ADMIN_IDS:
        db.execute("INSERT OR IGNORE INTO admins(telegram_id,active,created_at) VALUES(?,?,?)", (admin_id,1,now_str()))
    settings = {
        "welcome": "🇰🇷 DREAM KOREA\n\nAssalomu alaykum!\n\nDREAM KOREA o‘quv markazining rasmiy Telegram botiga xush kelibsiz.",
        "support": "@dreamkorea",
        "default_fee": "0",
        "ai_system_prompt": "Siz DREAM KOREA o‘quv markazining AI yordamchisisiz. Asosan koreys tili, TOPIK, grammatika, tarjima, lug‘at va yozish bo‘yicha aniq va tushunarli yordam bering. Foydalanuvchi qaysi tilda yozsa, asosan shu tilda javob bering.",
    }
    for key, value in settings.items():
        db.execute("INSERT OR IGNORE INTO settings(key,value,updated_at) VALUES(?,?,?)", (key,value,now_str()))
    db.commit()
    log.info("DB ready: %s", DB_PATH)


def get_setting(key, default=""):
    row = db_one("SELECT value FROM settings WHERE key=?", (key,))
    return row[0] if row else default


def set_setting(key, value):
    db_exec("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key,value,now_str()))


def next_code(prefix, table, column):
    row = db_one(f"SELECT {column} FROM {table} ORDER BY id DESC LIMIT 1")
    if not row:
        return f"{prefix}-000001"
    try:
        n = int(str(row[0]).split("-")[-1]) + 1
    except Exception:
        n = 1
    return f"{prefix}-{n:06d}"

# ============================================================
# AUTH / HELPERS
# ============================================================

def is_root_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS


def is_admin(tg_id: int) -> bool:
    if is_root_admin(tg_id):
        return True
    row = db_one("SELECT active FROM admins WHERE telegram_id=?", (tg_id,))
    return bool(row and row[0])


def get_teacher(tg_id: int):
    return db_one("SELECT * FROM teachers WHERE telegram_id=? AND active=1", (tg_id,))


def get_student(tg_id: int):
    return db_one("SELECT * FROM students WHERE telegram_id=? AND active=1", (tg_id,))


def get_user(tg_id: int):
    return db_one("SELECT * FROM users WHERE telegram_id=?", (tg_id,))


def ensure_user(tg_user):
    now = now_str()
    if is_admin(tg_user.id):
        role = "ADMIN"
    elif get_teacher(tg_user.id):
        role = "TEACHER"
    elif get_student(tg_user.id):
        role = "STUDENT"
    else:
        role = "USER"
    db_exec(
        "INSERT INTO users(telegram_id,username,first_name,last_name,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_name=excluded.last_name,role=excluded.role,updated_at=excluded.updated_at",
        (tg_user.id,tg_user.username,tg_user.first_name,tg_user.last_name,role,now,now),
    )
    return get_user(tg_user.id)


def blocked(tg_id: int) -> bool:
    row = db_one("SELECT blocked FROM users WHERE telegram_id=?", (tg_id,))
    return bool(row and row[0])


def money(v):
    try:
        return f"{int(v):,}".replace(",", " ") + " so‘m"
    except Exception:
        return "0 so‘m"


def time_label(v):
    return {"1":"1:30 — 3:30", "2":"3:30 — 5:30"}.get(str(v), "—")


def day_label(v):
    return "Dushanba — Chorshanba — Juma" if v == "MWF" else "Seshanba — Payshanba — Shanba"


def phone_ok(v):
    return bool(re.fullmatch(r"\+?[0-9 ()-]{7,20}", v.strip()))


def msg_media(message: Message):
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.document:
        return "document", message.document.file_id
    if message.audio:
        return "audio", message.audio.file_id
    return None, None


def menu(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back(target="main"):
    return [InlineKeyboardButton(text="⬅️ ORQAGA", callback_data=target)]


def paginate_text(page, pages):
    return f"{page}/{pages}"


def student_display(student_id):
    s = db_one("SELECT * FROM students WHERE id=?", (student_id,))
    if not s:
        return "O‘quvchi"
    if s["application_id"]:
        a = db_one("SELECT first_name,last_name,father_name FROM applications WHERE id=?", (s["application_id"],))
        if a:
            return f"{a['first_name']} {a['last_name']}"
    u = get_user(s["telegram_id"])
    if u:
        return f"{u['first_name'] or ''} {u['last_name'] or ''}".strip() or "O‘quvchi"
    return "O‘quvchi"


def group_matches_today(group):
    wd = datetime.now().weekday()
    return wd in ((0,2,4) if group["lesson_days"] == "MWF" else (1,3,5))


def chunk_text(text, size=4000):
    if not text:
        return [""]
    return [text[i:i+size] for i in range(0,len(text),size)]


async def safe_answer(callback: CallbackQuery, text, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)


async def notify_admins(bot: Bot, text, reply_markup=None):
    ids = set(ADMIN_IDS)
    ids.update(x[0] for x in db_all("SELECT telegram_id FROM admins WHERE active=1"))
    for tg_id in ids:
        try:
            await bot.send_message(tg_id, text, reply_markup=reply_markup)
        except Exception as e:
            log.warning("Cannot notify admin %s: %s", tg_id, e)


# ============================================================
# FSM
# ============================================================
class Admission(StatesGroup):
    first_name=State(); last_name=State(); father_name=State(); phone=State(); passport=State(); address=State(); time=State(); days=State()

class TeacherAdd(StatesGroup):
    tg_id=State(); name=State(); topik=State()

class TeacherEdit(StatesGroup):
    teacher_id=State(); field=State(); value=State()

class ContentEdit(StatesGroup):
    content_id=State(); field=State(); value=State()

class GroupAdd(StatesGroup):
    name=State(); time=State(); days=State(); fee=State(); tg_id=State()

class ContentAdd(StatesGroup):
    category=State(); title=State(); description=State(); media=State(); url=State()

class EpisodeAdd(StatesGroup):
    content_id=State(); number=State(); title=State(); media=State(); url=State()

class Homework(StatesGroup):
    group_id=State(); text=State(); media=State()

class Feedback(StatesGroup):
    text=State()

class Advertising(StatesGroup):
    name=State(); phone=State(); type=State(); description=State()

class Broadcast(StatesGroup):
    target=State(); message=State()

class Setting(StatesGroup):
    key=State(); value=State()

class RandomSectionAdd(StatesGroup):
    name=State(); korean=State(); uzbek=State()

class RandomSectionRename(StatesGroup):
    name=State()

class RandomWordEdit(StatesGroup):
    korean=State(); uzbek=State()

class RandomQuiz(StatesGroup):
    answer=State()


router=Router()

# ============================================================
# COMMANDS
# ============================================================
@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user)
    if blocked(message.from_user.id):
        await message.answer("🚫 Siz bloklangansiz.")
        return
    await message.answer(get_setting("welcome"), reply_markup=main_menu())


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    await state.clear()
    await message.answer("❌ Amal bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    await message.answer(get_setting("welcome"), reply_markup=main_menu())


@router.message(Command("ai"))
async def ai_on(message: Message, state: FSMContext):
    await state.clear(); ensure_user(message.from_user)
    if blocked(message.from_user.id):
        await message.answer("🚫 Siz bloklangansiz."); return
    db_exec("UPDATE users SET ai_active=1,updated_at=? WHERE telegram_id=?", (now_str(),message.from_user.id))
    await message.answer("🤖 DREAM KOREA AI yoqildi.\n\nSavolingizni yozing.\n\nTo‘xtatish: /stop")


@router.message(Command("stop"))
async def ai_off(message: Message, state: FSMContext):
    ensure_user(message.from_user); await state.clear()
    db_exec("UPDATE users SET ai_active=0,updated_at=? WHERE telegram_id=?", (now_str(),message.from_user.id))
    await message.answer("🛑 AI o‘chirildi. Oddiy bot rejimiga qaytdingiz.", reply_markup=main_menu())


@router.message(Command("kabinet"))
async def kabinet_cmd(message: Message):
    ensure_user(message.from_user)
    await send_student_cabinet(message, message.from_user.id)


@router.message(Command("ustoz"))
async def ustoz_cmd(message: Message):
    ensure_user(message.from_user)
    if not get_teacher(message.from_user.id):
        await message.answer("⛔ Siz ustoz sifatida ro‘yxatdan o‘tmagansiz.")
        return
    t=get_teacher(message.from_user.id)
    await message.answer(f"👨‍🏫 DREAM KOREA USTOZ PANELI\n\n{t['full_name']}\nTOPIK: {t['topik_level'] or '—'}", reply_markup=teacher_menu())


@router.message(Command("admin"))
async def admin_cmd(message: Message):
    ensure_user(message.from_user)
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Admin huquqi yo‘q.")
        return
    await message.answer("🇰🇷 DREAM KOREA — ADMIN PANEL", reply_markup=admin_menu())


# ============================================================
# KEYBOARDS
# ============================================================
def main_menu():
    return menu([
        [InlineKeyboardButton(text="🇰🇷 KOREYSCHA KITOBLAR",callback_data="cat:key:KOREAN_BOOKS"),InlineKeyboardButton(text="✍️ 쓰기 KITOB",callback_data="cat:key:WRITING_BOOKS")],
        [InlineKeyboardButton(text="🏆 TOPIK TESTLAR",callback_data="cat:key:TOPIK_TESTS"),InlineKeyboardButton(text="📚 GRAMMATIK KITOBLAR",callback_data="cat:key:GRAMMAR_BOOKS")],
        [InlineKeyboardButton(text="📘 TOPIK KITOBLAR",callback_data="cat:key:TOPIK_BOOKS"),InlineKeyboardButton(text="📕 LUG‘ATLAR",callback_data="cat:key:KOREAN_DICTIONARY")],
        [InlineKeyboardButton(text="🧰 EPS-TOPIK",callback_data="cat:key:EPS_TOPIK"),InlineKeyboardButton(text="🎬 KINOLAR",callback_data="cat:key:MOVIES")],
        [InlineKeyboardButton(text="🎞 SERIALAR",callback_data="cat:key:SERIES"),InlineKeyboardButton(text="📱 FOYDALI DASTURLAR",callback_data="cat:key:USEFUL_APPS")],
        [InlineKeyboardButton(text="🎲 RANDOM SO‘Z",callback_data="random:user"),InlineKeyboardButton(text="📝 QABUL",callback_data="admission:start")],
        [InlineKeyboardButton(text="🔐 SHAXSIY KABINET",callback_data="student:cabinet")],
        [InlineKeyboardButton(text="📢 REKLAMA",callback_data="ads:start"),InlineKeyboardButton(text="✍️ FIKR",callback_data="feedback:start")],
    ])


def student_menu():
    return menu([
        [InlineKeyboardButton(text="📊 DAVOMAT",callback_data="student:attendance"),InlineKeyboardButton(text="💳 TO‘LOVLAR",callback_data="student:payments")],
        [InlineKeyboardButton(text="📚 VAZIFALAR",callback_data="student:homework"),InlineKeyboardButton(text="👨‍🏫 USTOZIM",callback_data="student:teacher")],
        [InlineKeyboardButton(text="👥 GURUHIM",callback_data="student:group")],
        back("main")
    ])


def teacher_menu():
    return menu([
        [InlineKeyboardButton(text="👥 O‘QUVCHILAR",callback_data="teach:select:students"),InlineKeyboardButton(text="✅ DAVOMAT",callback_data="teach:select:attendance")],
        [InlineKeyboardButton(text="📊 TO‘LIQ DAVOMAT",callback_data="teach:select:full"),InlineKeyboardButton(text="💳 TO‘LOVLAR",callback_data="teach:select:payments")],
        [InlineKeyboardButton(text="📚 UYGA VAZIFA",callback_data="teach:select:homework"),InlineKeyboardButton(text="📈 STATISTIKA",callback_data="teach:select:stats")],
        back("main")
    ])


def admin_menu():
    return menu([
        [InlineKeyboardButton(text="📝 QABULLAR",callback_data="admin:apps"),InlineKeyboardButton(text="👨‍🎓 O‘QUVCHILAR",callback_data="admin:students")],
        [InlineKeyboardButton(text="👨‍🏫 USTOZLAR",callback_data="admin:teachers"),InlineKeyboardButton(text="👥 GURUHLAR",callback_data="admin:groups")],
        [InlineKeyboardButton(text="📊 DAVOMAT",callback_data="admin:attendance"),InlineKeyboardButton(text="💳 TO‘LOVLAR",callback_data="admin:payments")],
        [InlineKeyboardButton(text="📚 VAZIFALAR",callback_data="admin:homeworks"),InlineKeyboardButton(text="🎬 KONTENT",callback_data="admin:content")],
        [InlineKeyboardButton(text="🎲 RANDOM SO‘Z",callback_data="admin:random"),InlineKeyboardButton(text="🤖 AI",callback_data="admin:ai")],
        [InlineKeyboardButton(text="📢 BROADCAST",callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📈 STATISTIKA",callback_data="admin:stats"),InlineKeyboardButton(text="⚙️ SOZLAMALAR",callback_data="admin:settings")],
        [InlineKeyboardButton(text="👮 ADMINLAR",callback_data="admin:admins")],
        back("main")
    ])


def content_page_kb(cat_id,page,pages,items,admin=False):
    rows=[]
    for c in items:
        cb=f"ac:view:{c['id']}" if admin else f"content:view:{c['id']}:{page}"
        rows.append([InlineKeyboardButton(text=c['title'][:55],callback_data=cb)])
    nav=[]
    if page>1: nav.append(InlineKeyboardButton(text="⬅️",callback_data=f"acat:{cat_id}:{page-1}" if admin else f"cat:page:{cat_id}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}",callback_data="noop"))
    if page<pages: nav.append(InlineKeyboardButton(text="➡️",callback_data=f"acat:{cat_id}:{page+1}" if admin else f"cat:page:{cat_id}:{page+1}"))
    rows.append(nav)
    rows.append(back("admin:content" if admin else "main"))
    return menu(rows)


# ============================================================
# ADMISSION
# ============================================================
@router.callback_query(F.data=="admission:start")
async def admission_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    ensure_user(callback.from_user)
    existing=db_one("SELECT status FROM applications WHERE telegram_id=? ORDER BY id DESC LIMIT 1",(callback.from_user.id,))
    if existing and existing["status"]=="pending":
        await callback.message.answer("⏳ Sizning arizangiz allaqachon ko‘rib chiqilmoqda."); return
    if get_student(callback.from_user.id):
        await callback.message.answer("✅ Siz allaqachon DREAM KOREA o‘quvchisisiz.",reply_markup=student_menu()); return
    await state.clear(); await state.set_state(Admission.first_name)
    await callback.message.answer("📝 QABUL\n\n1/8. Ismingizni kiriting.")


@router.message(Admission.first_name)
async def ad_first(message:Message,state:FSMContext):
    if not message.text or len(message.text.strip())<2:
        await message.answer("⚠️ Ismni kiriting."); return
    await state.update_data(first_name=message.text.strip()); await state.set_state(Admission.last_name); await message.answer("2/8. Familiyangizni kiriting.")


@router.message(Admission.last_name)
async def ad_last(message:Message,state:FSMContext):
    if not message.text or len(message.text.strip())<2:
        await message.answer("⚠️ Familiyani kiriting."); return
    await state.update_data(last_name=message.text.strip()); await state.set_state(Admission.father_name); await message.answer("3/8. Otangizning ismini kiriting.")


@router.message(Admission.father_name)
async def ad_father(message:Message,state:FSMContext):
    if not message.text or len(message.text.strip())<2:
        await message.answer("⚠️ Otangizning ismini kiriting."); return
    await state.update_data(father_name=message.text.strip()); await state.set_state(Admission.phone)
    await message.answer("4/8. Telefon raqamingizni yuboring.",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Telefonimni yuborish",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True))


@router.message(Admission.phone,F.contact)
async def ad_phone_contact(message:Message,state:FSMContext):
    if message.contact.user_id and message.contact.user_id!=message.from_user.id:
        await message.answer("⚠️ O‘zingizning kontaktingizni yuboring."); return
    await state.update_data(phone=message.contact.phone_number); await state.set_state(Admission.passport)
    await message.answer("5/8. Pasport raqami ixtiyoriy. Kiriting yoki O‘TKAZIB YUBORISHni bosing.",reply_markup=ReplyKeyboardRemove())
    await message.answer("⏭ Pasportni o‘tkazib yuborish",reply_markup=menu([[InlineKeyboardButton(text="⏭ O‘TKAZIB YUBORISH",callback_data="ad:skip_passport")]]))


@router.message(Admission.phone,F.text)
async def ad_phone_text(message:Message,state:FSMContext):
    if not phone_ok(message.text or ""):
        await message.answer("⚠️ Telefon raqam noto‘g‘ri."); return
    await state.update_data(phone=message.text.strip()); await state.set_state(Admission.passport)
    await message.answer("5/8. Pasport raqami ixtiyoriy. Kiriting yoki O‘TKAZIB YUBORISHni bosing.")


@router.callback_query(F.data=="ad:skip_passport")
async def ad_skip_passport(callback:CallbackQuery,state:FSMContext):
    await callback.answer(); await state.update_data(passport=""); await state.set_state(Admission.address); await callback.message.answer("6/8. Yashash manzilingizni kiriting.")


@router.message(Admission.passport)
async def ad_passport(message:Message,state:FSMContext):
    await state.update_data(passport=(message.text or "").strip()); await state.set_state(Admission.address); await message.answer("6/8. Yashash manzilingizni kiriting.")


@router.message(Admission.address)
async def ad_address(message:Message,state:FSMContext):
    if not message.text or len(message.text.strip())<3:
        await message.answer("⚠️ Manzilni kiriting."); return
    await state.update_data(address=message.text.strip()); await state.set_state(Admission.time)
    await message.answer("7/8. Dars vaqtini tanlang.",reply_markup=menu([[InlineKeyboardButton(text="🕐 1:30 — 3:30",callback_data="ad:time:1")],[InlineKeyboardButton(text="🕞 3:30 — 5:30",callback_data="ad:time:2")]]))


@router.callback_query(Admission.time,F.data.startswith("ad:time:"))
async def ad_time(callback:CallbackQuery,state:FSMContext):
    await callback.answer(); await state.update_data(lesson_time=callback.data.split(":")[-1]); await state.set_state(Admission.days)
    await callback.message.answer("8/8. Dars kunlarini tanlang.",reply_markup=menu([[InlineKeyboardButton(text="Dushanba — Chorshanba — Juma",callback_data="ad:days:MWF")],[InlineKeyboardButton(text="Seshanba — Payshanba — Shanba",callback_data="ad:days:TTS")]]))


@router.callback_query(Admission.days,F.data.startswith("ad:days:"))
async def ad_days(callback:CallbackQuery,state:FSMContext):
    await callback.answer(); days=callback.data.split(":")[-1]; await state.update_data(lesson_days=days); data=await state.get_data()
    text=("📝 ANKETA\n\n"
          f"👤 Ism: {data['first_name']}\n👤 Familiya: {data['last_name']}\n👨 Otasining ismi: {data['father_name']}\n"
          f"📱 Telefon: {data['phone']}\n🆔 Telegram ID: {callback.from_user.id}\n🪪 Pasport: {data.get('passport') or '—'}\n"
          f"📍 Manzil: {data['address']}\n🕐 Vaqt: {time_label(data['lesson_time'])}\n📅 Kunlar: {day_label(days)}\n\nTasdiqlaysizmi?")
    await callback.message.answer(text,reply_markup=menu([[InlineKeyboardButton(text="✅ YUBORISH",callback_data="ad:submit")],[InlineKeyboardButton(text="🔄 QAYTA TO‘LDIRISH",callback_data="admission:start")],[InlineKeyboardButton(text="❌ BEKOR QILISH",callback_data="ad:cancel")]]))


@router.callback_query(F.data=="ad:cancel")
async def ad_cancel(callback:CallbackQuery,state:FSMContext):
    await callback.answer(); await state.clear(); await callback.message.answer("❌ Qabul bekor qilindi.",reply_markup=main_menu())


@router.callback_query(F.data=="ad:submit")
async def ad_submit(callback:CallbackQuery,state:FSMContext,bot:Bot):
    await callback.answer(); data=await state.get_data()
    if not data.get("first_name") or not data.get("lesson_days"):
        await callback.message.answer("⚠️ Anketa ma’lumotlari yetarli emas."); return
    app_code=next_code("APP","applications","application_code")
    app_id=db_exec("INSERT INTO applications(application_code,telegram_id,first_name,last_name,father_name,phone,passport,address,lesson_time,lesson_days,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (app_code,callback.from_user.id,data['first_name'],data['last_name'],data['father_name'],data['phone'],data.get('passport',''),data['address'],data['lesson_time'],data['lesson_days'],'pending',now_str(),now_str()))
    await state.clear()
    await callback.message.answer("✅ Arizangiz adminlarga yuborildi. Tasdiqlashni kuting.",reply_markup=main_menu())
    text=(f"📝 YANGI QABUL — {app_code}\n\n👤 F.I.Sh: {data['first_name']} {data['last_name']} {data['father_name']}\n"
          f"📱 Telefon: {data['phone']}\n🆔 Telegram ID: {callback.from_user.id}\n🪪 Pasport: {data.get('passport') or '—'}\n📍 Manzil: {data['address']}\n"
          f"🕐 Vaqt: {time_label(data['lesson_time'])}\n📅 Kunlar: {day_label(data['lesson_days'])}\n🟡 Status: pending")
    await notify_admins(bot,text,menu([[InlineKeyboardButton(text="✅ TASDIQLASH",callback_data=f"app:approve:{app_id}"),InlineKeyboardButton(text="❌ RAD ETISH",callback_data=f"app:reject:{app_id}")],[InlineKeyboardButton(text="👥 GURUH TANLASH",callback_data=f"app:groups:{app_id}")]]))

async def approve_application(bot:Bot,app_id:int,group_id:int):
    a=db_one("SELECT * FROM applications WHERE id=?",(app_id,))
    g=db_one("SELECT * FROM groups_ WHERE id=? AND active=1",(group_id,))
    if not a or not g or a['status']!='pending':
        return False
    teacher_id=g['teacher_id']
    existing=db_one("SELECT * FROM students WHERE telegram_id=?",(a['telegram_id'],))
    if existing:
        student_id=existing['id']
        db_exec("UPDATE students SET application_id=?,group_id=?,teacher_id=?,active=1 WHERE id=?",(app_id,group_id,teacher_id,student_id))
    else:
        code=next_code("DK","students","student_code")
        student_id=db_exec("INSERT INTO students(student_code,telegram_id,application_id,group_id,teacher_id,active,joined_at) VALUES(?,?,?,?,?,?,?)",(code,a['telegram_id'],app_id,group_id,teacher_id,1,now_str()))
    db_exec("UPDATE applications SET status='approved',group_id=?,teacher_id=?,updated_at=? WHERE id=?",(group_id,teacher_id,now_str(),app_id))
    db_exec("INSERT INTO users(telegram_id,role,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET role='STUDENT',updated_at=excluded.updated_at",(a['telegram_id'],'STUDENT',now_str(),now_str()))
    code=db_one("SELECT student_code FROM students WHERE id=?",(student_id,))[0]
    teacher_name='Ustoz hali biriktirilmagan'
    teacher_tg=None
    if teacher_id:
        tr=db_one("SELECT full_name,telegram_id FROM teachers WHERE id=?",(teacher_id,))
        if tr:
            teacher_name=tr['full_name']; teacher_tg=tr['telegram_id']
    user_text=("🎉 TABRIKLAYMIZ!\n\nSiz DREAM KOREA o‘quv markaziga qabul qilindingiz.\n\n"
               f"🆔 Student ID: {code}\n👨‍🏫 Ustoz: {teacher_name}\n👥 Guruh: {g['name']}\n"
               f"🕐 Vaqt: {time_label(g['lesson_time'])}\n📅 Kunlar: {day_label(g['lesson_days'])}\n💳 Oylik: {money(g['monthly_fee'])}")
    try:
        await bot.send_message(a['telegram_id'],user_text,reply_markup=main_menu())
    except Exception as e:
        log.warning("Student approval notification failed: %s",e)
    if teacher_tg:
        try:
            await bot.send_message(teacher_tg,f"👨‍🎓 Yangi o‘quvchi\n\n{a['first_name']} {a['last_name']}\n👥 Guruh: {g['name']}")
        except Exception:
            pass
    return True


@router.callback_query(F.data.startswith("app:approve:"))
async def app_approve(callback:CallbackQuery,bot:Bot):
    await callback.answer()
    if not is_admin(callback.from_user.id): return
    app_id=int(callback.data.split(":")[-1])
    a=db_one("SELECT * FROM applications WHERE id=?",(app_id,))
    if not a or a['status']!='pending':
        await callback.message.answer("⚠️ Ariza allaqachon ko‘rib chiqilgan yoki topilmadi."); return
    groups=db_all("SELECT g.*,t.full_name teacher_name FROM groups_ g LEFT JOIN teachers t ON t.id=g.teacher_id WHERE g.active=1 AND g.lesson_time=? AND g.lesson_days=? ORDER BY g.name",(a['lesson_time'],a['lesson_days']))
    if len(groups)==1:
        if await approve_application(bot,app_id,groups[0]['id']):
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(f"✅ {a['application_code']} tasdiqlandi.")
        return
    all_groups=groups if groups else db_all("SELECT g.*,t.full_name teacher_name FROM groups_ g LEFT JOIN teachers t ON t.id=g.teacher_id WHERE g.active=1 ORDER BY g.name")
    rows=[]
    if not all_groups:
        await callback.message.answer("⚠️ Aktiv guruh yo‘q. Avval guruh yarating."); return
    for g in all_groups:
        rows.append([InlineKeyboardButton(text=f"👥 {g['name']} | {g['teacher_name'] or 'Ustoz yo‘q'}",callback_data=f"app:assign:{app_id}:{g['id']}")])
    await callback.message.answer("👥 Guruhni tanlang:",reply_markup=menu(rows))


@router.callback_query(F.data.startswith("app:groups:"))
async def app_groups(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id): return
    app_id=int(callback.data.split(":")[-1])
    a=db_one("SELECT * FROM applications WHERE id=?",(app_id,))
    if not a or a['status']!='pending': return
    groups=db_all("SELECT g.*,t.full_name teacher_name FROM groups_ g LEFT JOIN teachers t ON t.id=g.teacher_id WHERE g.active=1 ORDER BY g.name")
    rows=[[InlineKeyboardButton(text=f"👥 {g['name']} | {time_label(g['lesson_time'])}",callback_data=f"app:assign:{app_id}:{g['id']}")] for g in groups]
    await callback.message.answer("Guruhni tanlang:",reply_markup=menu(rows or [back(f"admin:apps")]))


@router.callback_query(F.data.startswith("app:assign:"))
async def app_assign(callback:CallbackQuery,bot:Bot):
    await callback.answer()
    if not is_admin(callback.from_user.id): return
    _,_,app_id,group_id=callback.data.split(":")
    ok=await approve_application(bot,int(app_id),int(group_id))
    await callback.message.answer("✅ Ariza tasdiqlandi va guruh biriktirildi." if ok else "⚠️ Amal bajarilmadi.")


@router.callback_query(F.data.startswith("app:reject:"))
async def app_reject(callback:CallbackQuery,bot:Bot):
    await callback.answer()
    if not is_admin(callback.from_user.id): return
    app_id=int(callback.data.split(":")[-1]); a=db_one("SELECT * FROM applications WHERE id=?",(app_id,))
    if not a or a['status']!='pending': return
    db_exec("UPDATE applications SET status='rejected',updated_at=? WHERE id=?",(now_str(),app_id))
    try: await bot.send_message(a['telegram_id'],"❌ Qabul arizangiz tasdiqlanmadi.",reply_markup=main_menu())
    except Exception: pass
    await callback.message.edit_reply_markup(reply_markup=None)

# ============================================================
# STUDENT CABINET
# ============================================================
async def send_student_cabinet(message:Message,tg_id:int):
    s=get_student(tg_id)
    if not s:
        await message.answer("ℹ️ Siz hali DREAM KOREA o‘quvchisi emassiz.",reply_markup=main_menu()); return
    a=db_one("SELECT * FROM applications WHERE id=?",(s['application_id'],)) if s['application_id'] else None
    g=db_one("SELECT * FROM groups_ WHERE id=?",(s['group_id'],)) if s['group_id'] else None
    t=db_one("SELECT * FROM teachers WHERE id=?",(s['teacher_id'],)) if s['teacher_id'] else None
    name=f"{a['first_name']} {a['last_name']}" if a else (get_user(tg_id)['first_name'] or 'O‘quvchi')
    text=("🔐 SHAXSIY KABINET\n\n"
          f"👤 {name}\n🆔 {s['student_code']}\n📱 Telegram ID: {tg_id}\n"
          f"👨‍🏫 Ustoz: {t['full_name'] if t else '—'}\n👥 Guruh: {g['name'] if g else '—'}\n"
          f"🕐 Vaqt: {time_label(g['lesson_time']) if g else '—'}\n📅 Kunlar: {day_label(g['lesson_days']) if g else '—'}")
    await message.answer(text,reply_markup=student_menu())


@router.callback_query(F.data=="student:cabinet")
async def student_cb(callback:CallbackQuery):
    await callback.answer(); await send_student_cabinet(callback.message,callback.from_user.id)

@router.callback_query(F.data=="student:teacher")
async def student_teacher(callback:CallbackQuery):
    await callback.answer(); s=get_student(callback.from_user.id)
    if not s: return
    t=db_one("SELECT * FROM teachers WHERE id=?",(s['teacher_id'],)) if s['teacher_id'] else None
    await callback.message.answer("👨‍🏫 USTOZIM\n\n"+(f"{t['full_name']}\nTOPIK: {t['topik_level'] or '—'}\nTelegram ID: {t['telegram_id']}" if t else "Ustoz biriktirilmagan."),reply_markup=menu([back("student:cabinet")]))

@router.callback_query(F.data=="student:group")
async def student_group(callback:CallbackQuery):
    await callback.answer(); s=get_student(callback.from_user.id)
    if not s or not s['group_id']: return
    g=db_one("SELECT * FROM groups_ WHERE id=?",(s['group_id'],))
    await callback.message.answer(f"👥 GURUH\n\n{g['name']}\n🕐 {time_label(g['lesson_time'])}\n📅 {day_label(g['lesson_days'])}\n💳 {money(g['monthly_fee'])}",reply_markup=menu([back("student:cabinet")]))

@router.callback_query(F.data=="student:attendance")
async def student_att(callback:CallbackQuery):
    await callback.answer(); s=get_student(callback.from_user.id)
    if not s: return
    m=month_now(); total=db_one("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date LIKE ?",(s['id'],m+'%'))[0]; present=db_one("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date LIKE ? AND status='present'",(s['id'],m+'%'))[0]
    absent=total-present; pct=round(present/total*100) if total else 0
    await callback.message.answer(f"📊 DAVOMAT — {m}\n\nJami belgilangan: {total}\n✅ Kelgan: {present}\n❌ Kelmagan: {absent}\n📈 {pct}%",reply_markup=menu([back("student:cabinet")]))

@router.callback_query(F.data=="student:payments")
async def student_pay(callback:CallbackQuery):
    await callback.answer(); s=get_student(callback.from_user.id)
    if not s:return
    rows=db_all("SELECT month,amount,status FROM payments WHERE student_id=? ORDER BY month DESC LIMIT 12",(s['id'],))
    text="💳 TO‘LOVLAR\n\n"+('\n'.join(f"{r['month']} {'✅' if r['status']=='paid' else '❌'} — {money(r['amount'])}" for r in rows) if rows else "To‘lov tarixi yo‘q.")
    await callback.message.answer(text,reply_markup=menu([back("student:cabinet")]))

@router.callback_query(F.data=="student:homework")
async def student_hw(callback:CallbackQuery,bot:Bot):
    await callback.answer(); s=get_student(callback.from_user.id)
    if not s or not s['group_id']:return
    rows=db_all("SELECT h.*,t.full_name teacher_name,g.name group_name FROM homeworks h JOIN teachers t ON t.id=h.teacher_id JOIN groups_ g ON g.id=h.group_id WHERE h.group_id=? ORDER BY h.id DESC LIMIT 10",(s['group_id'],))
    if not rows:
        await callback.message.answer("📚 Hozircha vazifa yo‘q.",reply_markup=menu([back("student:cabinet")])); return
    for h in rows:
        await callback.message.answer(f"📚 UYGA VAZIFA\n\n👨‍🏫 {h['teacher_name']}\n👥 {h['group_name']}\n📅 {h['created_at']}\n\n{h['text'] or ''}")
        if h['file_id']:
            if h['media_type']=='photo': await bot.send_photo(callback.from_user.id,h['file_id'])
            elif h['media_type']=='video': await bot.send_video(callback.from_user.id,h['file_id'])
            elif h['media_type']=='document': await bot.send_document(callback.from_user.id,h['file_id'])
            elif h['media_type']=='audio': await bot.send_audio(callback.from_user.id,h['file_id'])
    await callback.message.answer("⬅️",reply_markup=menu([back("student:cabinet")]))

# ============================================================
# PUBLIC CONTENT CATALOG
# ============================================================
@router.callback_query(F.data.startswith("cat:key:"))
async def public_category(callback:CallbackQuery):
    await callback.answer()
    key=callback.data.split(":")[-1]
    cat=db_one("SELECT * FROM content_categories WHERE key=? AND active=1",(key,))
    if not cat:
        await callback.message.answer("⚠️ Bo‘lim topilmadi."); return
    await show_public_catalog(callback.message,cat['id'],1)


@router.callback_query(F.data.startswith("cat:page:"))
async def public_category_page(callback:CallbackQuery):
    await callback.answer()
    _,_,cat_id,page=callback.data.split(":")
    await show_public_catalog(callback.message,int(cat_id),int(page),edit=True)


async def show_public_catalog(message:Message,cat_id:int,page:int,edit=False):
    cat=db_one("SELECT * FROM content_categories WHERE id=? AND active=1",(cat_id,))
    if not cat:return
    limit=20; offset=(page-1)*limit
    total=db_one("SELECT COUNT(*) FROM contents WHERE category_id=? AND active=1",(cat_id,))[0]
    items=db_all("SELECT * FROM contents WHERE category_id=? AND active=1 ORDER BY id DESC LIMIT ? OFFSET ?",(cat_id,limit,offset))
    text=f"{cat['emoji']} {cat['name']}\n\n"
    if not items:text+="Hozircha ma’lumot yo‘q."
    else:
        for i,item in enumerate(items,start=offset+1):text+=f"{i}. {item['title']}\n"
    pages=max(1,(total+limit-1)//limit)
    rows=[[InlineKeyboardButton(text=item['title'][:55],callback_data=f"content:view:{item['id']}:{page}")] for item in items]
    nav=[]
    if page>1:nav.append(InlineKeyboardButton(text="⬅️ OLDINGI",callback_data=f"cat:page:{cat_id}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}",callback_data="noop"))
    if page<pages:nav.append(InlineKeyboardButton(text="KEYINGI ➡️",callback_data=f"cat:page:{cat_id}:{page+1}"))
    rows.append(nav); rows.append(back("main")); kb=menu(rows)
    if edit:
        try:await message.edit_text(text,reply_markup=kb)
        except Exception:await message.answer(text,reply_markup=kb)
    else:await message.answer(text,reply_markup=kb)


@router.callback_query(F.data.startswith("content:view:"))
async def public_content_view(callback:CallbackQuery,bot:Bot):
    await callback.answer()
    parts=callback.data.split(":"); cid=int(parts[2]); page=int(parts[3]) if len(parts)>3 else 1
    c=db_one("SELECT c.*,cc.name category_name,cc.emoji category_emoji,cc.key category_key FROM contents c JOIN content_categories cc ON cc.id=c.category_id WHERE c.id=? AND c.active=1",(cid,))
    if not c:return
    text=f"{c['category_emoji']} {c['title']}\n\n{c['description'] or 'Tavsif mavjud emas.'}"
    rows=[]
    if c['category_key']=='SERIES':
        eps=db_all("SELECT * FROM episodes WHERE content_id=? ORDER BY episode_number",(cid,))
        for e in eps:rows.append([InlineKeyboardButton(text=f"{e['episode_number']}-QISM — {e['title']}",callback_data=f"episode:view:{e['id']}:{page}")])
        if not eps:text+="\n\nHozircha qismlar qo‘shilmagan."
    else:
        if c['file_id']:rows.append([InlineKeyboardButton(text="📎 FAYLNI OLISH",callback_data=f"content:send:{cid}")])
        if c['external_url']:rows.append([InlineKeyboardButton(text="🔗 OCHISH",url=c['external_url'])])
    rows.append([InlineKeyboardButton(text="⬅️ ORQAGA",callback_data=f"cat:page:{c['category_id']}:{page}")])
    if c['file_id'] and c['media_type']=='photo':
        await bot.send_photo(callback.from_user.id,c['file_id'],caption=text,reply_markup=menu(rows))
    elif c['file_id'] and c['media_type']=='video':
        await bot.send_video(callback.from_user.id,c['file_id'],caption=text,reply_markup=menu(rows))
    else:
        await callback.message.answer(text,reply_markup=menu(rows))


@router.callback_query(F.data.startswith("content:send:"))
async def send_content_file(callback:CallbackQuery,bot:Bot):
    await callback.answer()
    c=db_one("SELECT media_type,file_id FROM contents WHERE id=? AND active=1",(int(callback.data.split(":")[-1]),))
    if not c or not c['file_id']:return
    try:
        if c['media_type']=='photo':await bot.send_photo(callback.from_user.id,c['file_id'])
        elif c['media_type']=='video':await bot.send_video(callback.from_user.id,c['file_id'])
        elif c['media_type']=='document':await bot.send_document(callback.from_user.id,c['file_id'])
        elif c['media_type']=='audio':await bot.send_audio(callback.from_user.id,c['file_id'])
    except Exception as e:log.warning("content send: %s",e)


@router.callback_query(F.data.startswith("episode:view:"))
async def public_episode(callback:CallbackQuery,bot:Bot):
    await callback.answer()
    parts=callback.data.split(":"); eid=int(parts[2]); page=int(parts[3]) if len(parts)>3 else 1
    e=db_one("SELECT e.*,c.title series_title,c.category_id FROM episodes e JOIN contents c ON c.id=e.content_id WHERE e.id=?",(eid,))
    if not e:return
    text=f"🎞 {e['series_title']}\n{e['episode_number']}-QISM — {e['title']}"
    if e['external_url']:
        await callback.message.answer(text,reply_markup=menu([[InlineKeyboardButton(text="🔗 OCHISH",url=e['external_url'])],[InlineKeyboardButton(text="⬅️ ORQAGA",callback_data=f"content:view:{e['content_id']}:{page}")]]))
        return
    if e['file_id']:
        if e['media_type']=='video':await bot.send_video(callback.from_user.id,e['file_id'],caption=text)
        elif e['media_type']=='document':await bot.send_document(callback.from_user.id,e['file_id'],caption=text)
        elif e['media_type']=='audio':await bot.send_audio(callback.from_user.id,e['file_id'],caption=text)
        elif e['media_type']=='photo':await bot.send_photo(callback.from_user.id,e['file_id'],caption=text)

# ============================================================
# TEACHER CORE
# ============================================================
async def teacher_groups(message:Message,action:str):
    tr=get_teacher(message.chat.id)
    if not tr:return
    gs=db_all("SELECT * FROM groups_ WHERE teacher_id=? AND active=1 ORDER BY name",(tr['id'],))
    rows=[[InlineKeyboardButton(text=f"👥 {g['name']} | {time_label(g['lesson_time'])}",callback_data=f"teach:{action}:{g['id']}")] for g in gs]
    rows.append(back("teach:main"))
    await message.answer("👥 Guruhni tanlang:",reply_markup=menu(rows))


@router.callback_query(F.data=="teach:main")
async def teacher_main(callback:CallbackQuery):
    await callback.answer()
    if not get_teacher(callback.from_user.id):return
    t=get_teacher(callback.from_user.id)
    await safe_answer(callback,f"👨‍🏫 {t['full_name']}\n\nDREAM KOREA USTOZ PANELI",teacher_menu())


@router.callback_query(F.data.startswith("teach:select:"))
async def teacher_select(callback:CallbackQuery):
    await callback.answer()
    if not get_teacher(callback.from_user.id):return
    action=callback.data.split(":")[-1]
    await teacher_groups(callback.message,action)


@router.callback_query(F.data.startswith("teach:students:"))
async def teach_students(callback:CallbackQuery):
    await callback.answer()
    tr=get_teacher(callback.from_user.id)
    gid=int(callback.data.split(":")[-1])
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=? AND active=1",(gid,tr['id']))
    if not g:return
    ss=db_all("SELECT id,student_code FROM students WHERE group_id=? AND active=1 ORDER BY id",(gid,))
    text=f"👥 {g['name']} — O‘QUVCHILAR\n\n"+(("\n".join(f"• {student_display(s['id'])} — {s['student_code']}" for s in ss)) if ss else "O‘quvchi yo‘q.")
    await callback.message.answer(text,reply_markup=menu([back("teach:main")]))


@router.callback_query(F.data.startswith("teach:attendance:"))
async def teach_attendance(callback:CallbackQuery):
    await callback.answer()
    tr=get_teacher(callback.from_user.id); gid=int(callback.data.split(":")[-1])
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=? AND active=1",(gid,tr['id']))
    if not g:return
    if not group_matches_today(g):
        await callback.message.answer("⚠️ Bugun bu guruhning dars kuni emas.",reply_markup=menu([back("teach:main")]))
        return
    await render_attendance(callback.message,gid,tr['id'])


async def render_attendance(message,gid,tid):
    date=datetime.now().strftime("%Y-%m-%d")
    g=db_one("SELECT name FROM groups_ WHERE id=? AND teacher_id=?",(gid,tid))
    ss=db_all("SELECT id FROM students WHERE group_id=? AND active=1 ORDER BY id",(gid,))
    text=f"✅ BUGUNGI DAVOMAT\n👥 {g['name']}\n📅 {date}\n\n"; rows=[]
    for s in ss:
        r=db_one("SELECT status FROM attendance WHERE student_id=? AND date=?",(s['id'],date))
        mark="✅" if r and r['status']=='present' else ("❌" if r else "—")
        name=student_display(s['id']); text+=f"{name} {mark}\n"
        rows.append([InlineKeyboardButton(text=f"✅ {name[:25]}",callback_data=f"att:{gid}:{s['id']}:present"),InlineKeyboardButton(text="❌",callback_data=f"att:{gid}:{s['id']}:absent")])
    rows.append(back("teach:main"));
    try:await message.edit_text(text,reply_markup=menu(rows))
    except Exception:await message.answer(text,reply_markup=menu(rows))


@router.callback_query(F.data.startswith("att:"))
async def attendance_set(callback:CallbackQuery):
    await callback.answer("Saqlandi")
    parts=callback.data.split(":"); gid,sid,status=int(parts[1]),int(parts[2]),parts[3]
    tr=get_teacher(callback.from_user.id)
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=? AND active=1",(gid,tr['id']))
    s=db_one("SELECT * FROM students WHERE id=? AND group_id=? AND active=1",(sid,gid))
    if not g or not s:return
    date=datetime.now().strftime("%Y-%m-%d")
    r=db_one("SELECT id FROM attendance WHERE student_id=? AND date=?",(sid,date))
    if r:db_exec("UPDATE attendance SET status=?,teacher_id=?,group_id=?,updated_at=? WHERE id=?",(status,tr['id'],gid,now_str(),r['id']))
    else:db_exec("INSERT INTO attendance(student_id,group_id,teacher_id,date,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(sid,gid,tr['id'],date,status,now_str(),now_str()))
    await render_attendance(callback.message,gid,tr['id'])


@router.callback_query(F.data.startswith("teach:full:"))
async def teach_full(callback:CallbackQuery):
    await callback.answer(); tr=get_teacher(callback.from_user.id); gid=int(callback.data.split(":")[-1])
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=?",(gid,tr['id']))
    if not g:return
    m=month_now(); ss=db_all("SELECT id FROM students WHERE group_id=? AND active=1",(gid,))
    text=f"📊 TO‘LIQ DAVOMAT — {g['name']} / {m}\n\n"
    for s in ss:
        total=db_one("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date LIKE ?",(s['id'],m+'%'))[0]
        p=db_one("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date LIKE ? AND status='present'",(s['id'],m+'%'))[0]
        a=total-p; pct=round(p/total*100) if total else 0
        text+=f"👤 {student_display(s['id'])}\n✅ {p} | ❌ {a} | 📈 {pct}%\n\n"
    await callback.message.answer(text,reply_markup=menu([back("teach:main")]))


@router.callback_query(F.data.startswith("teach:payments:"))
async def teach_payments(callback:CallbackQuery):
    await callback.answer(); tr=get_teacher(callback.from_user.id); gid=int(callback.data.split(":")[-1])
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=?",(gid,tr['id']))
    if not g:return
    m=month_now(); ss=db_all("SELECT id FROM students WHERE group_id=? AND active=1 ORDER BY id",(gid,))
    text=f"💳 TO‘LOVLAR — {g['name']} / {m}\n\n"; rows=[]
    for s in ss:
        p=db_one("SELECT status FROM payments WHERE student_id=? AND month=?",(s['id'],m)); mark="✅" if p and p['status']=='paid' else "❌"; name=student_display(s['id'])
        text+=f"{name} {mark}\n"; rows.append([InlineKeyboardButton(text=f"{mark} {name[:32]}",callback_data=f"pay:{gid}:{s['id']}:{m}")])
    rows.append(back("teach:main")); await callback.message.answer(text,reply_markup=menu(rows))


@router.callback_query(F.data.startswith("pay:"))
async def payment_toggle(callback:CallbackQuery):
    await callback.answer("Yangilandi")
    parts=callback.data.split(":"); gid,sid,month=int(parts[1]),int(parts[2]),parts[3]
    admin=is_admin(callback.from_user.id); tr=get_teacher(callback.from_user.id)
    if not admin and not tr:return
    if admin:g=db_one("SELECT * FROM groups_ WHERE id=?",(gid,)); tid=g['teacher_id'] if g else None
    else:
        g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=?",(gid,tr['id'])); tid=tr['id'] if tr else None
    s=db_one("SELECT * FROM students WHERE id=? AND group_id=? AND active=1",(sid,gid))
    if not g or not s:return
    p=db_one("SELECT * FROM payments WHERE student_id=? AND month=?",(sid,month))
    if p and p['status']=='paid':
        db_exec("UPDATE payments SET status='unpaid',paid_at=NULL WHERE id=?",(p['id'],))
    elif p:
        db_exec("UPDATE payments SET status='paid',amount=?,teacher_id=?,paid_at=? WHERE id=?",(g['monthly_fee'],tid,now_str(),p['id']))
    else:
        db_exec("INSERT INTO payments(student_id,group_id,teacher_id,month,amount,status,paid_at,created_at) VALUES(?,?,?,?,?,?,?,?)",(sid,gid,tid,month,g['monthly_fee'],'paid',now_str(),now_str()))
    try:await callback.message.edit_reply_markup(reply_markup=callback.message.reply_markup)
    except Exception:pass
    try:await callback.bot.send_message(s['telegram_id'],f"💳 {month} uchun to‘lov holatingiz yangilandi.")
    except Exception:pass


@router.callback_query(F.data.startswith("teach:homework:"))
async def teach_homework_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer(); tr=get_teacher(callback.from_user.id); gid=int(callback.data.split(":")[-1])
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=? AND active=1",(gid,tr['id']))
    if not g:return
    await state.clear(); await state.update_data(group_id=gid); await state.set_state(Homework.text)
    await callback.message.answer(f"📚 {g['name']} uchun vazifa matnini yuboring.\nAgar faqat fayl bo‘lsa /skip yozing.")


@router.message(Homework.text)
async def homework_text(message:Message,state:FSMContext):
    if message.text is None:return
    await state.update_data(text="" if message.text=="/skip" else message.text.strip()); await state.set_state(Homework.media)
    await message.answer("📎 Foto/video/document/audio yuboring yoki /skip.")


async def homework_finish(message:Message,state:FSMContext,media_type=None,file_id=None):
    d=await state.get_data(); tr=get_teacher(message.from_user.id); gid=d.get('group_id')
    if not tr or not gid:await state.clear();return
    g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=?",(gid,tr['id']))
    if not g:await state.clear();return
    hw=db_exec("INSERT INTO homeworks(teacher_id,group_id,text,media_type,file_id,created_at) VALUES(?,?,?,?,?,?)",(tr['id'],gid,d.get('text',''),media_type,file_id,now_str()))
    ss=db_all("SELECT telegram_id FROM students WHERE group_id=? AND active=1",(gid,));sent=failed=0
    msgtext=f"📚 DREAM KOREA — UYGA VAZIFA\n\n👨‍🏫 Ustoz: {tr['full_name']}\n👥 Guruh: {g['name']}\n📅 {now_str()}\n\n{d.get('text','')}"
    for tg in ss:
        try:
            await message.bot.send_message(tg['telegram_id'],msgtext)
            if file_id:
                if media_type=='photo':await message.bot.send_photo(tg['telegram_id'],file_id)
                elif media_type=='video':await message.bot.send_video(tg['telegram_id'],file_id)
                elif media_type=='document':await message.bot.send_document(tg['telegram_id'],file_id)
                elif media_type=='audio':await message.bot.send_audio(tg['telegram_id'],file_id)
            sent+=1
        except Exception as e:failed+=1;log.warning("homework delivery %s: %s",tg['telegram_id'],e)
    await state.clear(); await message.answer(f"✅ Vazifa yuborildi.\nYuborildi: {sent}\nXato: {failed}",reply_markup=teacher_menu()); log.info("homework %s",hw)


@router.message(Homework.media,F.photo)
async def hw_photo(message:Message,state:FSMContext):await homework_finish(message,state,'photo',message.photo[-1].file_id)
@router.message(Homework.media,F.video)
async def hw_video(message:Message,state:FSMContext):await homework_finish(message,state,'video',message.video.file_id)
@router.message(Homework.media,F.document)
async def hw_document(message:Message,state:FSMContext):await homework_finish(message,state,'document',message.document.file_id)
@router.message(Homework.media,F.audio)
async def hw_audio(message:Message,state:FSMContext):await homework_finish(message,state,'audio',message.audio.file_id)
@router.message(Homework.media,F.text)
async def hw_skip(message:Message,state:FSMContext):
    if message.text!='/skip':await message.answer("⚠️ Media yuboring yoki /skip.");return
    await homework_finish(message,state)


@router.callback_query(F.data.startswith("teach:stats:"))
async def teach_stats(callback:CallbackQuery):
    await callback.answer();tr=get_teacher(callback.from_user.id);gid=int(callback.data.split(":")[-1]);g=db_one("SELECT * FROM groups_ WHERE id=? AND teacher_id=?",(gid,tr['id']))
    if not g:return
    m=month_now(); students=db_one("SELECT COUNT(*) FROM students WHERE group_id=? AND active=1",(gid,))[0]
    paid=db_one("SELECT COUNT(*) FROM payments WHERE group_id=? AND month=? AND status='paid'",(gid,m))[0]
    p=db_one("SELECT COUNT(*) FROM attendance WHERE group_id=? AND date LIKE ? AND status='present'",(gid,m+'%'))[0]
    total=db_one("SELECT COUNT(*) FROM attendance WHERE group_id=? AND date LIKE ?",(gid,m+'%'))[0]
    pct=round(p/total*100) if total else 0
    await callback.message.answer(f"📈 {g['name']}\n\n👨‍🎓 O‘quvchilar: {students}\n✅ Present: {p}\n📊 Attendance: {pct}%\n💳 To‘lagan: {paid}/{students}",reply_markup=menu([back("teach:main")]))

# ============================================================
# FEEDBACK / ADVERTISING
# ============================================================
@router.callback_query(F.data=="feedback:start")
async def feedback_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer();await state.clear();await state.set_state(Feedback.text);await callback.message.answer("✍️ Fikringizni yozing.")

@router.message(Feedback.text)
async def feedback_save(message:Message,state:FSMContext,bot:Bot):
    if not message.text:return
    db_exec("INSERT INTO feedback(telegram_id,text,status,created_at) VALUES(?,?,?,?)",(message.from_user.id,message.text,'new',now_str()))
    await state.clear();await message.answer("✅ Fikringiz adminlarga yuborildi.",reply_markup=main_menu())
    await notify_admins(bot,f"✍️ YANGI FIKR\n\nID: {message.from_user.id}\n\n{message.text}")

@router.callback_query(F.data=="ads:start")
async def ads_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer();await state.clear();await state.set_state(Advertising.name);await callback.message.answer("📢 REKLAMA\n\nIsmingizni kiriting.")

@router.message(Advertising.name)
async def ads_name(message:Message,state:FSMContext):
    await state.update_data(name=(message.text or '').strip());await state.set_state(Advertising.phone);await message.answer("Telefon raqamingizni kiriting.")

@router.message(Advertising.phone)
async def ads_phone(message:Message,state:FSMContext):
    if not phone_ok(message.text or ''):await message.answer("⚠️ Telefon raqami noto‘g‘ri.");return
    await state.update_data(phone=message.text.strip());await state.set_state(Advertising.type);await message.answer("Reklama turini kiriting.")

@router.message(Advertising.type)
async def ads_type(message:Message,state:FSMContext):
    await state.update_data(type=(message.text or '').strip());await state.set_state(Advertising.description);await message.answer("Reklama haqida yozing.")

@router.message(Advertising.description)
async def ads_desc(message:Message,state:FSMContext,bot:Bot):
    d=await state.get_data()
    db_exec("INSERT INTO advertising_requests(telegram_id,name,phone,type,description,status,created_at) VALUES(?,?,?,?,?,?,?)",(message.from_user.id,d.get('name',''),d.get('phone',''),d.get('type',''),message.text or '','pending',now_str()))
    await state.clear();await message.answer("✅ Reklama so‘rovi yuborildi.",reply_markup=main_menu())
    await notify_admins(bot,f"📢 YANGI REKLAMA\n\nIsm: {d.get('name')}\nTelefon: {d.get('phone')}\nTuri: {d.get('type')}\nID: {message.from_user.id}\n\n{message.text or ''}")

# ============================================================
# ADMIN APPLICATIONS
# ============================================================
@router.callback_query(F.data=="admin:apps")
async def admin_apps(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    apps=db_all("SELECT * FROM applications ORDER BY id DESC LIMIT 50")
    rows=[];text="📝 QABULLAR\n\n"
    for a in apps:
        text+=f"{a['application_code']} | {a['first_name']} {a['last_name']} | {a['status']}\n"
        rows.append([InlineKeyboardButton(text=f"{a['application_code']} — {a['first_name']} {a['last_name']}",callback_data=f"admin:app:{a['id']}")])
    if not apps:text+="Ariza yo‘q."
    rows.append(back("admin:main"));await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("admin:app:"))
async def admin_app_view(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    aid=int(callback.data.split(":")[-1]);a=db_one("SELECT * FROM applications WHERE id=?",(aid,))
    if not a:return
    text=(f"📝 {a['application_code']}\n\n👤 {a['first_name']} {a['last_name']} {a['father_name']}\n"
          f"📱 {a['phone']}\n🆔 {a['telegram_id']}\n🪪 {a['passport'] or '—'}\n📍 {a['address']}\n"
          f"🕐 {time_label(a['lesson_time'])}\n📅 {day_label(a['lesson_days'])}\n📌 {a['status']}")
    rows=[]
    if a['status']=='pending':
        rows.append([InlineKeyboardButton(text="✅ TASDIQLASH",callback_data=f"app:approve:{aid}"),InlineKeyboardButton(text="❌ RAD ETISH",callback_data=f"app:reject:{aid}")])
        rows.append([InlineKeyboardButton(text="👥 GURUH TANLASH",callback_data=f"app:groups:{aid}")])
    rows.append(back("admin:apps"));await callback.message.answer(text,reply_markup=menu(rows))

# ============================================================
# ADMIN TEACHERS
# ============================================================
@router.callback_query(F.data=="admin:teachers")
async def admin_teachers(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    ts=db_all("SELECT * FROM teachers ORDER BY active DESC,full_name")
    rows=[[InlineKeyboardButton(text="➕ USTOZ QO‘SHISH",callback_data="teacher:add")]];text="👨‍🏫 USTOZLAR\n\n"
    for t in ts:
        text+=f"{'✅' if t['active'] else '⛔'} {t['teacher_code']} — {t['full_name']} — TOPIK {t['topik_level'] or '—'}\n"
        rows.append([InlineKeyboardButton(text=t['full_name'][:50],callback_data=f"teacher:view:{t['id']}")])
    rows.append(back("admin:main"));await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data=="teacher:add")
async def teacher_add(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    await state.clear();await state.set_state(TeacherAdd.tg_id);await callback.message.answer("👨‍🏫 USTOZ QO‘SHISH\n\nTelegram IDni kiriting.")

@router.message(TeacherAdd.tg_id)
async def teacher_add_tg(message:Message,state:FSMContext):
    try:tg=int((message.text or '').strip())
    except Exception:await message.answer("⚠️ Telegram ID raqam bo‘lishi kerak.");return
    if db_one("SELECT id FROM teachers WHERE telegram_id=?",(tg,)):await message.answer("⚠️ Bu ID allaqachon mavjud.");return
    await state.update_data(tg_id=tg);await state.set_state(TeacherAdd.name);await message.answer("Ustozning ism familiyasini kiriting.")

@router.message(TeacherAdd.name)
async def teacher_add_name(message:Message,state:FSMContext):
    if len((message.text or '').strip())<3:await message.answer("⚠️ Ism familiya kerak.");return
    await state.update_data(name=message.text.strip());await state.set_state(TeacherAdd.topik);await message.answer("TOPIK darajasini kiriting.")

@router.message(TeacherAdd.topik)
async def teacher_add_topik(message:Message,state:FSMContext):
    d=await state.get_data();code=next_code('TR','teachers','teacher_code');now=now_str()
    tid=db_exec("INSERT INTO teachers(teacher_code,telegram_id,full_name,topik_level,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(code,d['tg_id'],d['name'],message.text.strip(),1,now,now))
    db_exec("INSERT INTO users(telegram_id,role,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET role='TEACHER',updated_at=excluded.updated_at",(d['tg_id'],'TEACHER',now,now))
    await state.clear();await message.answer(f"✅ Ustoz qo‘shildi: {code}",reply_markup=admin_menu());log.info("teacher %s",tid)

@router.callback_query(F.data.startswith("teacher:view:"))
async def teacher_admin_view(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    tid=int(callback.data.split(":")[-1]);t=db_one("SELECT * FROM teachers WHERE id=?",(tid,))
    if not t:return
    gs=db_all("SELECT name FROM groups_ WHERE teacher_id=? AND active=1 ORDER BY name",(tid,));sc=db_one("SELECT COUNT(*) FROM students WHERE teacher_id=? AND active=1",(tid,))[0]
    rows=[[InlineKeyboardButton(text="👥 GURUHLAR",callback_data=f"teacher:groups:{tid}")],[InlineKeyboardButton(text="✏️ O‘ZGARTIRISH",callback_data=f"teacher:edit:{tid}")],[InlineKeyboardButton(text="🗑 DEAKTIVATSIYA" if t['active'] else "♻️ AKTIV QILISH",callback_data=f"teacher:toggle:{tid}")],back("admin:teachers")]
    text=f"👨‍🏫 {t['full_name']}\n\nID: {t['teacher_code']}\nTelegram ID: {t['telegram_id']}\nTOPIK: {t['topik_level'] or '—'}\nGuruhlar: {len(gs)}\nO‘quvchilar: {sc}\nStatus: {'aktiv' if t['active'] else 'noaktiv'}"
    await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("teacher:groups:"))
async def teacher_admin_groups(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    tid=int(callback.data.split(":")[-1]);t=db_one("SELECT full_name FROM teachers WHERE id=?",(tid,));gs=db_all("SELECT * FROM groups_ WHERE teacher_id=? AND active=1 ORDER BY name",(tid,))
    text=f"👥 {t['full_name']} guruhlari\n\n"+('\n'.join(f"• {g['name']} | {time_label(g['lesson_time'])}" for g in gs) if gs else 'Guruh yo‘q.')
    await callback.message.answer(text,reply_markup=menu([back(f"teacher:view:{tid}")]))

@router.callback_query(F.data.startswith("teacher:toggle:"))
async def teacher_toggle(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    tid=int(callback.data.split(":")[-1]);t=db_one("SELECT active FROM teachers WHERE id=?",(tid,))
    if not t:return
    db_exec("UPDATE teachers SET active=?,updated_at=? WHERE id=?",(0 if t['active'] else 1,now_str(),tid));await callback.message.answer("✅ Ustoz statusi o‘zgartirildi.")

@router.callback_query(F.data.startswith("teacher:edit:"))
async def teacher_edit_menu(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    tid=int(callback.data.split(":")[-1])
    await callback.message.answer("Nimani o‘zgartirasiz?",reply_markup=menu([[InlineKeyboardButton(text="👤 ISM",callback_data=f"tedit:{tid}:name")],[InlineKeyboardButton(text="🏆 TOPIK",callback_data=f"tedit:{tid}:topik")],[InlineKeyboardButton(text="⬅️ ORQAGA",callback_data=f"teacher:view:{tid}")]]))

@router.callback_query(F.data.startswith("tedit:"))
async def teacher_edit_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    _,tid,field=callback.data.split(":");await state.clear();await state.update_data(teacher_id=int(tid),field=field);await state.set_state(TeacherEdit.value);await callback.message.answer("Yangi qiymatni yuboring.")

@router.message(TeacherEdit.value)
async def teacher_edit_save(message:Message,state:FSMContext):
    d=await state.get_data();field='full_name' if d['field']=='name' else 'topik_level'
    db_exec(f"UPDATE teachers SET {field}=?,updated_at=? WHERE id=?",(message.text.strip(),now_str(),d['teacher_id']));await state.clear();await message.answer("✅ Ustoz yangilandi.",reply_markup=admin_menu())

# ============================================================
# ADMIN GROUPS
# ============================================================
@router.callback_query(F.data=="admin:groups")
async def admin_groups(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gs=db_all("SELECT g.*,t.full_name teacher_name FROM groups_ g LEFT JOIN teachers t ON t.id=g.teacher_id WHERE g.active=1 ORDER BY g.name")
    rows=[[InlineKeyboardButton(text="➕ GURUH YARATISH",callback_data="group:add")]];text="👥 GURUHLAR\n\n"
    for g in gs:
        text+=f"• {g['name']} | {time_label(g['lesson_time'])} | {g['teacher_name'] or 'Ustoz yo‘q'}\n"
        rows.append([InlineKeyboardButton(text=g['name'][:50],callback_data=f"group:view:{g['id']}")])
    if not gs:text+="Aktiv guruhlar yo‘q."
    rows.append(back("admin:main"));await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data=="group:add")
async def group_add(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    await state.clear();await state.set_state(GroupAdd.name);await callback.message.answer("👥 GURUH YARATISH\n\nGuruh nomini kiriting.")

@router.message(GroupAdd.name)
async def group_add_name(message:Message,state:FSMContext):
    value=(message.text or '').strip()
    if not value:await message.answer("⚠️ Guruh nomini kiriting.");return
    await state.update_data(name=value);await state.set_state(GroupAdd.time);await message.answer("Dars vaqtini tanlang.",reply_markup=menu([[InlineKeyboardButton(text="1:30 — 3:30",callback_data="gadd:time:1")],[InlineKeyboardButton(text="3:30 — 5:30",callback_data="gadd:time:2")]]))

@router.callback_query(GroupAdd.time,F.data.startswith("gadd:time:"))
async def group_add_time(callback:CallbackQuery,state:FSMContext):
    await callback.answer();await state.update_data(lesson_time=callback.data.split(":")[-1]);await state.set_state(GroupAdd.days);await callback.message.answer("Dars kunlarini tanlang.",reply_markup=menu([[InlineKeyboardButton(text="Dushanba — Chorshanba — Juma",callback_data="gadd:days:MWF")],[InlineKeyboardButton(text="Seshanba — Payshanba — Shanba",callback_data="gadd:days:TTS")]]))

@router.callback_query(GroupAdd.days,F.data.startswith("gadd:days:"))
async def group_add_days(callback:CallbackQuery,state:FSMContext):
    await callback.answer();await state.update_data(lesson_days=callback.data.split(":")[-1]);await state.set_state(GroupAdd.fee);await callback.message.answer("Oylik to‘lovni raqamda kiriting.")

@router.message(GroupAdd.fee)
async def group_add_fee(message:Message,state:FSMContext):
    try:fee=int((message.text or '').replace(' ',''));assert fee>=0
    except Exception:await message.answer("⚠️ Raqam kiriting.");return
    await state.update_data(monthly_fee=fee);await state.set_state(GroupAdd.tg_id);await message.answer("Telegram group IDni kiriting yoki /skip.")

@router.message(GroupAdd.tg_id)
async def group_add_save(message:Message,state:FSMContext):
    tg_id=None
    if message.text!='/skip':
        try:tg_id=int(message.text.strip())
        except Exception:await message.answer("⚠️ Group ID raqam bo‘lishi kerak yoki /skip.");return
    d=await state.get_data();gid=db_exec("INSERT INTO groups_(name,lesson_time,lesson_days,teacher_id,telegram_group_id,monthly_fee,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(d['name'],d['lesson_time'],d['lesson_days'],None,tg_id,d['monthly_fee'],1,now_str(),now_str()))
    await state.clear();ts=db_all("SELECT * FROM teachers WHERE active=1 ORDER BY full_name");rows=[[InlineKeyboardButton(text=t['full_name'][:50],callback_data=f"gteacher:{gid}:{t['id']}")] for t in ts];rows.append([InlineKeyboardButton(text="⏭ KEYINROQ",callback_data=f"group:view:{gid}")])
    await message.answer(f"✅ Guruh yaratildi: {d['name']}\n\nUstozni tanlang.",reply_markup=menu(rows))

@router.callback_query(F.data.startswith("gteacher:"))
async def group_teacher_assign(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    _,gid,tid=callback.data.split(":");gid=int(gid);tid=int(tid)
    db_exec("UPDATE groups_ SET teacher_id=?,updated_at=? WHERE id=?",(tid,now_str(),gid));db_exec("UPDATE students SET teacher_id=? WHERE group_id=? AND active=1",(tid,gid));await callback.message.answer("✅ Ustoz biriktirildi.",reply_markup=admin_menu())

@router.callback_query(F.data.startswith("group:view:"))
async def group_view(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gid=int(callback.data.split(":")[-1]);g=db_one("SELECT g.*,t.full_name teacher_name FROM groups_ g LEFT JOIN teachers t ON t.id=g.teacher_id WHERE g.id=?",(gid,))
    if not g:return
    count=db_one("SELECT COUNT(*) FROM students WHERE group_id=? AND active=1",(gid,))[0]
    text=f"👥 {g['name']}\n\n👨‍🏫 {g['teacher_name'] or '—'}\n🕐 {time_label(g['lesson_time'])}\n📅 {day_label(g['lesson_days'])}\n💳 {money(g['monthly_fee'])}\n👨‍🎓 O‘quvchilar: {count}\n📣 Group ID: {g['telegram_group_id'] or '—'}"
    rows=[[InlineKeyboardButton(text="👨‍🎓 O‘QUVCHILAR",callback_data=f"group:students:{gid}")],[InlineKeyboardButton(text="➕ O‘QUVCHI QO‘SHISH",callback_data=f"group:addstudent:{gid}")],[InlineKeyboardButton(text="👨‍🏫 USTOZ",callback_data=f"group:choose_teacher:{gid}")],[InlineKeyboardButton(text="🗑 DEAKTIVATSIYA",callback_data=f"group:delete:{gid}")],back("admin:groups")]
    await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("group:choose_teacher:"))
async def group_choose_teacher(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gid=int(callback.data.split(":")[-1]);ts=db_all("SELECT * FROM teachers WHERE active=1 ORDER BY full_name");rows=[[InlineKeyboardButton(text=t['full_name'],callback_data=f"gteacher:{gid}:{t['id']}")] for t in ts];rows.append(back(f"group:view:{gid}"));await callback.message.answer("👨‍🏫 Ustozni tanlang:",reply_markup=menu(rows))

@router.callback_query(F.data.startswith("group:delete:"))
async def group_delete(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    db_exec("UPDATE groups_ SET active=0,updated_at=? WHERE id=?",(now_str(),int(callback.data.split(":")[-1])));await callback.message.answer("✅ Guruh deaktivatsiya qilindi.")

@router.callback_query(F.data.startswith("group:students:"))
async def group_students(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gid=int(callback.data.split(":")[-1]);ss=db_all("SELECT id,student_code FROM students WHERE group_id=? AND active=1 ORDER BY id",(gid,));text="👨‍🎓 O‘QUVCHILAR\n\n";rows=[]
    for s in ss:text+=f"• {student_display(s['id'])} — {s['student_code']}\n";rows.append([InlineKeyboardButton(text=f"🗑 {student_display(s['id'])[:30]}",callback_data=f"group:remove:{gid}:{s['id']}")])
    if not ss:text+="O‘quvchi yo‘q."
    rows.append([InlineKeyboardButton(text="➕ O‘QUVCHI QO‘SHISH",callback_data=f"group:addstudent:{gid}")]);rows.append(back(f"group:view:{gid}"));await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("group:addstudent:"))
async def group_addstudent(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gid=int(callback.data.split(":")[-1]);ss=db_all("SELECT id FROM students WHERE active=1 AND (group_id IS NULL OR group_id!=?) ORDER BY id LIMIT 50",(gid,));rows=[[InlineKeyboardButton(text=f"➕ {student_display(s['id'])[:40]}",callback_data=f"group:setstudent:{gid}:{s['id']}")] for s in ss];rows.append(back(f"group:view:{gid}"));await callback.message.answer("O‘quvchini tanlang:",reply_markup=menu(rows))

@router.callback_query(F.data.startswith("group:setstudent:"))
async def group_setstudent(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    _,_,gid,sid=callback.data.split(":");gid=int(gid);sid=int(sid);g=db_one("SELECT * FROM groups_ WHERE id=? AND active=1",(gid,))
    if not g:return
    db_exec("UPDATE students SET group_id=?,teacher_id=? WHERE id=?",(gid,g['teacher_id'],sid));st=db_one("SELECT telegram_id FROM students WHERE id=?",(sid,))
    if st:
        try:await callback.bot.send_message(st['telegram_id'],f"📢 Siz {g['name']} guruhiga biriktirildingiz.")
        except Exception:pass
    await callback.message.answer("✅ O‘quvchi biriktirildi.")

@router.callback_query(F.data.startswith("group:remove:"))
async def group_remove_student(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    _,_,gid,sid=callback.data.split(":");db_exec("UPDATE students SET group_id=NULL,teacher_id=NULL WHERE id=? AND group_id=?",(int(sid),int(gid)));await callback.message.answer("✅ O‘quvchi guruhdan chiqarildi.")

# ============================================================
# ADMIN STUDENTS
# ============================================================
@router.callback_query(F.data=="admin:students")
async def admin_students(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    ss=db_all("SELECT id,student_code FROM students WHERE active=1 ORDER BY id DESC LIMIT 50");rows=[];text="👨‍🎓 O‘QUVCHILAR\n\n"
    for s in ss:text+=f"• {student_display(s['id'])} — {s['student_code']}\n";rows.append([InlineKeyboardButton(text=student_display(s['id'])[:45],callback_data=f"student:view:{s['id']}")])
    if not ss:text+="O‘quvchi yo‘q."
    rows.append(back("admin:main"));await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("student:view:"))
async def student_admin_view(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    sid=int(callback.data.split(":")[-1]);s=db_one("SELECT * FROM students WHERE id=?",(sid,));a=db_one("SELECT * FROM applications WHERE id=?",(s['application_id'],)) if s and s['application_id'] else None;g=db_one("SELECT * FROM groups_ WHERE id=?",(s['group_id'],)) if s and s['group_id'] else None;t=db_one("SELECT * FROM teachers WHERE id=?",(s['teacher_id'],)) if s and s['teacher_id'] else None
    if not s:return
    text=(f"👨‍🎓 {student_display(sid)}\n\n🆔 {s['student_code']}\nTelegram ID: {s['telegram_id']}\n📱 {a['phone'] if a else '—'}\n📍 {a['address'] if a else '—'}\n🪪 {a['passport'] if a and a['passport'] else '—'}\n👥 {g['name'] if g else '—'}\n👨‍🏫 {t['full_name'] if t else '—'}")
    await callback.message.answer(text,reply_markup=menu([[InlineKeyboardButton(text="👥 GURUH ALMASHTIRISH",callback_data=f"student:move:{sid}")],[InlineKeyboardButton(text="🔒 BLOCK",callback_data=f"student:block:{s['telegram_id']}")],[InlineKeyboardButton(text="🗑 DEAKTIVATSIYA",callback_data=f"student:deactivate:{sid}")],back("admin:students")]))

@router.callback_query(F.data.startswith("student:move:"))
async def student_move(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    sid=int(callback.data.split(":")[-1]);gs=db_all("SELECT id,name,lesson_time FROM groups_ WHERE active=1 ORDER BY name");rows=[[InlineKeyboardButton(text=f"{g['name']} | {time_label(g['lesson_time'])}",callback_data=f"student:setgroup:{sid}:{g['id']}")] for g in gs];rows.append(back(f"student:view:{sid}"));await callback.message.answer("Yangi guruhni tanlang:",reply_markup=menu(rows))

@router.callback_query(F.data.startswith("student:setgroup:"))
async def student_setgroup(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    _,_,sid,gid=callback.data.split(":");sid=int(sid);gid=int(gid);g=db_one("SELECT * FROM groups_ WHERE id=?",(gid,));
    if not g:return
    db_exec("UPDATE students SET group_id=?,teacher_id=? WHERE id=?",(gid,g['teacher_id'],sid));st=db_one("SELECT telegram_id FROM students WHERE id=?",(sid,))
    if st:
        try:await callback.bot.send_message(st['telegram_id'],f"📢 Guruhingiz o‘zgartirildi.\n👥 {g['name']}\n👨‍🏫 {db_one('SELECT full_name FROM teachers WHERE id=?',(g['teacher_id'],))[0] if g['teacher_id'] and db_one('SELECT full_name FROM teachers WHERE id=?',(g['teacher_id'],)) else '—'}")
        except Exception:pass
    await callback.message.answer("✅ O‘quvchi yangi guruhga o‘tkazildi.")

@router.callback_query(F.data.startswith("student:block:"))
async def student_block(callback:CallbackQuery):
    await callback.answer();
    if not is_admin(callback.from_user.id):return
    tg=int(callback.data.split(":")[-1]);db_exec("UPDATE users SET blocked=1,updated_at=? WHERE telegram_id=?",(now_str(),tg));await callback.message.answer("🔒 Foydalanuvchi bloklandi.")

@router.callback_query(F.data.startswith("student:deactivate:"))
async def student_deactivate(callback:CallbackQuery):
    await callback.answer();
    if not is_admin(callback.from_user.id):return
    db_exec("UPDATE students SET active=0 WHERE id=?",(int(callback.data.split(":")[-1]),));await callback.message.answer("✅ O‘quvchi deaktivatsiya qilindi.")

# ============================================================
# ADMIN ATTENDANCE / PAYMENTS
# ============================================================
@router.callback_query(F.data=="admin:attendance")
async def admin_attendance(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gs=db_all("SELECT id,name FROM groups_ WHERE active=1 ORDER BY name");rows=[[InlineKeyboardButton(text=g['name'],callback_data=f"admin:att:{g['id']}")] for g in gs];rows.append(back("admin:main"));await callback.message.answer("📊 Guruhni tanlang:",reply_markup=menu(rows))

@router.callback_query(F.data.startswith("admin:att:"))
async def admin_att_view(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    gid=int(callback.data.split(":")[-1]);g=db_one("SELECT name FROM groups_ WHERE id=?",(gid,));m=month_now();ss=db_all("SELECT id FROM students WHERE group_id=? AND active=1",(gid,));text=f"📊 DAVOMAT — {g['name']} — {m}\n\n"
    for s in ss:
        total=db_one("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date LIKE ?",(s['id'],m+'%'))[0];p=db_one("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date LIKE ? AND status='present'",(s['id'],m+'%'))[0];a=total-p;pct=round(p/total*100) if total else 0;text+=f"{student_display(s['id'])}: ✅ {p} | ❌ {a} | {pct}%\n"
    await callback.message.answer(text,reply_markup=menu([back("admin:attendance")]))

@router.callback_query(F.data=="admin:payments")
async def admin_payments(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    m=month_now();students=db_one("SELECT COUNT(*) FROM students WHERE active=1")[0];paid=db_one("SELECT COUNT(*) FROM payments WHERE month=? AND status='paid'",(m,))[0];amount=db_one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=? AND status='paid'",(m,))[0]
    await callback.message.answer(f"💳 TO‘LOVLAR — {m}\n\n👨‍🎓 O‘quvchilar: {students}\n✅ To‘lagan: {paid}\n❌ To‘lamagan: {max(0,students-paid)}\n💰 Tushum: {money(amount)}",reply_markup=menu([back("admin:main")]))

# ============================================================
# ADMIN HOMEWORK
# ============================================================
@router.callback_query(F.data=="admin:homeworks")
async def admin_homeworks(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    hs=db_all("SELECT h.created_at,t.full_name teacher_name,g.name group_name FROM homeworks h JOIN teachers t ON t.id=h.teacher_id JOIN groups_ g ON g.id=h.group_id ORDER BY h.id DESC LIMIT 30");text="📚 UYGA VAZIFALAR TARIXI\n\n"+('\n'.join(f"{h['created_at']} | {h['group_name']} | {h['teacher_name']}" for h in hs) if hs else 'Vazifalar yo‘q.')
    await callback.message.answer(text,reply_markup=menu([back("admin:main")]))

# ============================================================
# ADMIN CONTENT CMS
# ============================================================
@router.callback_query(F.data=="admin:content")
async def admin_content(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    cats=db_all("SELECT * FROM content_categories WHERE active=1 ORDER BY sort_order");rows=[[InlineKeyboardButton(text=f"{c['emoji']} {c['name']}",callback_data=f"acat:{c['id']}:1")] for c in cats];rows.append(back("admin:main"));await callback.message.answer("🎬 KONTENT CMS\n\nKategoriya tanlang:",reply_markup=menu(rows))

@router.callback_query(F.data.startswith("acat:"))
async def admin_content_category(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    _,cid,page=callback.data.split(":");cid=int(cid);page=int(page);cat=db_one("SELECT * FROM content_categories WHERE id=? AND active=1",(cid,));
    if not cat:return
    limit=20;offset=(page-1)*limit;total=db_one("SELECT COUNT(*) FROM contents WHERE category_id=? AND active=1",(cid,))[0];items=db_all("SELECT id,title FROM contents WHERE category_id=? AND active=1 ORDER BY id DESC LIMIT ? OFFSET ?",(cid,limit,offset));text=f"{cat['emoji']} {cat['name']}\n\n";rows=[[InlineKeyboardButton(text="➕ QO‘SHISH",callback_data=f"acadd:{cid}")]]
    if items:
        for item in items:rows.append([InlineKeyboardButton(text=item['title'][:55],callback_data=f"acview:{item['id']}")])
    else:text+="Kontent yo‘q."
    pages=max(1,(total+limit-1)//limit);nav=[]
    if page>1:nav.append(InlineKeyboardButton(text="⬅️",callback_data=f"acat:{cid}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}",callback_data="noop"))
    if page<pages:nav.append(InlineKeyboardButton(text="➡️",callback_data=f"acat:{cid}:{page+1}"))
    rows.append(nav);rows.append(back("admin:content"));await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("acadd:"))
async def admin_content_add(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    cid=int(callback.data.split(":")[-1]);await state.clear();await state.update_data(category_id=cid);await state.set_state(ContentAdd.title);await callback.message.answer("➕ KONTENT QO‘SHISH\n\nNomi:")

@router.message(ContentAdd.title)
async def content_title(message:Message,state:FSMContext):
    if not message.text or not message.text.strip():await message.answer("⚠️ Nom kiriting.");return
    await state.update_data(title=message.text.strip());await state.set_state(ContentAdd.description);await message.answer("Tavsif yoki /skip:")

@router.message(ContentAdd.description)
async def content_desc(message:Message,state:FSMContext):
    await state.update_data(description='' if message.text=='/skip' else (message.text or '').strip());await state.set_state(ContentAdd.media);await message.answer("Media yuboring: photo/video/document/audio yoki /skip.")

async def content_media_next(message:Message,state:FSMContext,media_type=None,file_id=None):
    await state.update_data(media_type=media_type,file_id=file_id);await state.set_state(ContentAdd.url);await message.answer("Tashqi URL yoki /skip:")

@router.message(ContentAdd.media,F.photo)
async def c_photo(message:Message,state:FSMContext):await content_media_next(message,state,'photo',message.photo[-1].file_id)
@router.message(ContentAdd.media,F.video)
async def c_video(message:Message,state:FSMContext):await content_media_next(message,state,'video',message.video.file_id)
@router.message(ContentAdd.media,F.document)
async def c_document(message:Message,state:FSMContext):await content_media_next(message,state,'document',message.document.file_id)
@router.message(ContentAdd.media,F.audio)
async def c_audio(message:Message,state:FSMContext):await content_media_next(message,state,'audio',message.audio.file_id)
@router.message(ContentAdd.media,F.text)
async def c_media_skip(message:Message,state:FSMContext):
    if message.text!='/skip':await message.answer("⚠️ Media yoki /skip.");return
    await content_media_next(message,state)

@router.message(ContentAdd.url)
async def content_finish(message:Message,state:FSMContext):
    d=await state.get_data();url=None if message.text=='/skip' else (message.text or '').strip();cid=db_exec("INSERT INTO contents(category_id,title,description,media_type,file_id,external_url,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(d['category_id'],d['title'],d.get('description',''),d.get('media_type'),d.get('file_id'),url,1,now_str(),now_str()));await state.clear();await message.answer(f"✅ Kontent qo‘shildi: {d['title']}",reply_markup=admin_menu());log.info("content %s",cid)

@router.callback_query(F.data.startswith("acview:"))
async def admin_content_view(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    cid=int(callback.data.split(":")[-1]);c=db_one("SELECT c.*,cc.name category_name,cc.key category_key,cc.emoji FROM contents c JOIN content_categories cc ON cc.id=c.category_id WHERE c.id=? AND c.active=1",(cid,));
    if not c:return
    text=f"{c['emoji']} {c['title']}\n\n{c['description'] or 'Tavsif yo‘q.'}\n\nMedia: {c['media_type'] or '—'}\nURL: {c['external_url'] or '—'}"
    rows=[[InlineKeyboardButton(text="✏️ NOMINI O‘ZGARTIRISH",callback_data=f"cedit:{cid}:title")],[InlineKeyboardButton(text="✏️ TAVSIFNI O‘ZGARTIRISH",callback_data=f"cedit:{cid}:description")]]
    if c['category_key']=='SERIES':rows += [[InlineKeyboardButton(text="🎞 QISMLAR",callback_data=f"episodes:{cid}")],[InlineKeyboardButton(text="➕ QISM QO‘SHISH",callback_data=f"episode:add:{cid}")]]
    rows += [[InlineKeyboardButton(text="🗑 O‘CHIRISH",callback_data=f"cdelete:{cid}")],[InlineKeyboardButton(text="⬅️ ORQAGA",callback_data=f"acat:{c['category_id']}:1")]]
    await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("cedit:"))
async def content_edit_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer();
    if not is_admin(callback.from_user.id):return
    _,cid,field=callback.data.split(":");await state.clear();await state.update_data(content_id=int(cid),field=field);await state.set_state(ContentEdit.value);await callback.message.answer("Yangi qiymat:")

@router.message(ContentEdit.value)
async def content_edit_save(message:Message,state:FSMContext):
    d=await state.get_data()
    field=d.get('field')
    if field not in ('title','description'):
        await state.clear()
        return
    db_exec(f"UPDATE contents SET {field}=?,updated_at=? WHERE id=?",(message.text or '',now_str(),d['content_id']))
    await state.clear()
    await message.answer("✅ Kontent yangilandi.",reply_markup=admin_menu())

@router.callback_query(F.data.startswith("cdelete:"))
async def content_delete(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    cid=int(callback.data.split(":")[-1]);db_exec("UPDATE contents SET active=0,updated_at=? WHERE id=?",(now_str(),cid));await callback.message.answer("✅ Kontent o‘chirildi.")

@router.callback_query(F.data.startswith("episodes:"))
async def episode_list_admin(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    cid=int(callback.data.split(":")[-1]);c=db_one("SELECT title FROM contents WHERE id=?",(cid,));eps=db_all("SELECT * FROM episodes WHERE content_id=? ORDER BY episode_number",(cid,));text=f"🎞 {c['title']} — QISMLAR\n\n";rows=[]
    for e in eps:text+=f"{e['episode_number']}-qism — {e['title']}\n";rows.append([InlineKeyboardButton(text=f"🗑 {e['episode_number']}-QISM",callback_data=f"epdelete:{e['id']}")])
    rows.append([InlineKeyboardButton(text="➕ QISM QO‘SHISH",callback_data=f"episode:add:{cid}")]);rows.append([InlineKeyboardButton(text="⬅️ ORQAGA",callback_data=f"acview:{cid}")]);await callback.message.answer(text,reply_markup=menu(rows))

@router.callback_query(F.data.startswith("episode:add:"))
async def episode_add(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    cid=int(callback.data.split(":")[-1]);await state.clear();await state.update_data(content_id=cid);await state.set_state(EpisodeAdd.number);await callback.message.answer("➕ QISM\n\nQism raqami:")

@router.message(EpisodeAdd.number)
async def ep_number(message:Message,state:FSMContext):
    try:n=int((message.text or '').strip());assert n>0
    except Exception:await message.answer("⚠️ Raqam kiriting.");return
    await state.update_data(number=n);await state.set_state(EpisodeAdd.title);await message.answer("Qism nomi:")

@router.message(EpisodeAdd.title)
async def ep_title(message:Message,state:FSMContext):
    if not message.text:return
    await state.update_data(title=message.text.strip());await state.set_state(EpisodeAdd.media);await message.answer("Video/document/audio/photo yuboring yoki /skip:")

async def episode_media_next(message:Message,state:FSMContext,media_type=None,file_id=None):
    await state.update_data(media_type=media_type,file_id=file_id);await state.set_state(EpisodeAdd.url);await message.answer("URL yoki /skip:")

@router.message(EpisodeAdd.media,F.photo)
async def ep_photo(message:Message,state:FSMContext):await episode_media_next(message,state,'photo',message.photo[-1].file_id)
@router.message(EpisodeAdd.media,F.video)
async def ep_video(message:Message,state:FSMContext):await episode_media_next(message,state,'video',message.video.file_id)
@router.message(EpisodeAdd.media,F.document)
async def ep_doc(message:Message,state:FSMContext):await episode_media_next(message,state,'document',message.document.file_id)
@router.message(EpisodeAdd.media,F.audio)
async def ep_audio(message:Message,state:FSMContext):await episode_media_next(message,state,'audio',message.audio.file_id)
@router.message(EpisodeAdd.media,F.text)
async def ep_media_skip(message:Message,state:FSMContext):
    if message.text!='/skip':await message.answer("⚠️ Media yoki /skip.");return
    await episode_media_next(message,state)

@router.message(EpisodeAdd.url)
async def ep_save(message:Message,state:FSMContext):
    d=await state.get_data();url=None if message.text=='/skip' else (message.text or '').strip()
    if not d.get('file_id') and not url:await message.answer("⚠️ Video/file yoki URL kerak.");return
    try:db_exec("INSERT INTO episodes(content_id,episode_number,title,media_type,file_id,external_url,created_at) VALUES(?,?,?,?,?,?,?)",(d['content_id'],d['number'],d['title'],d.get('media_type'),d.get('file_id'),url,now_str()))
    except sqlite3.IntegrityError:await message.answer("⚠️ Bu qism raqami mavjud.");return
    await state.clear();await message.answer("✅ Qism qo‘shildi.",reply_markup=admin_menu())

@router.callback_query(F.data.startswith("epdelete:"))
async def ep_delete(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    db_exec("DELETE FROM episodes WHERE id=?",(int(callback.data.split(":")[-1]),));await callback.message.answer("✅ Qism o‘chirildi.")

# ============================================================
# ADMIN AI / STATS / SETTINGS / ADMINS
# ============================================================
@router.callback_query(F.data=="admin:ai")
async def admin_ai(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    total=db_one("SELECT COUNT(*) FROM ai_usage")[0]
    success=db_one("SELECT COUNT(*) FROM ai_usage WHERE success=1")[0]
    failed=db_one("SELECT COUNT(*) FROM ai_usage WHERE success=0")[0]
    await callback.message.answer(f"🤖 DREAM KOREA AI\n\nPrimary: {AI_PRIMARY_MODEL}\nFallbacklar: {', '.join(AI_FALLBACK_MODELS) or '—'}\n\nJami request: {total}\n✅ Success: {success}\n❌ Xato: {failed}\nCooldown: {AI_COOLDOWN_SECONDS}s\nContext: {AI_MAX_CONTEXT}",reply_markup=menu([back("admin:main")]))


@router.callback_query(F.data=="admin:stats")
async def admin_stats(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    m=month_now()
    users=db_one("SELECT COUNT(*) FROM users")[0]
    students=db_one("SELECT COUNT(*) FROM students WHERE active=1")[0]
    teachers=db_one("SELECT COUNT(*) FROM teachers WHERE active=1")[0]
    groups=db_one("SELECT COUNT(*) FROM groups_ WHERE active=1")[0]
    apps=db_one("SELECT COUNT(*) FROM applications WHERE status='pending'")[0]
    payments=db_one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE month=? AND status='paid'",(m,))[0]
    attendance=db_one("SELECT COUNT(*) FROM attendance WHERE date LIKE ?",(m+'%',))[0]
    content=db_one("SELECT COUNT(*) FROM contents WHERE active=1")[0]
    episodes=db_one("SELECT COUNT(*) FROM episodes")[0]
    homeworks=db_one("SELECT COUNT(*) FROM homeworks")[0]
    await callback.message.answer(f"📈 STATISTIKA — {m}\n\n👤 Users: {users}\n👨‍🎓 Students: {students}\n👨‍🏫 Teachers: {teachers}\n👥 Groups: {groups}\n📝 Pending qabullar: {apps}\n💳 Shu oy tushum: {money(payments)}\n📊 Attendance yozuvlari: {attendance}\n🎬 Content: {content}\n🎞 Episodes: {episodes}\n📚 Homework: {homeworks}",reply_markup=menu([back("admin:main")]))


@router.callback_query(F.data=="admin:settings")
async def admin_settings(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    await callback.message.answer(f"⚙️ SOZLAMALAR\n\nSupport: {get_setting('support','—')}\nDefault fee: {get_setting('default_fee','0')}",reply_markup=menu([[InlineKeyboardButton(text="✏️ WELCOME",callback_data="set:welcome")],[InlineKeyboardButton(text="✏️ SUPPORT",callback_data="set:support")],[InlineKeyboardButton(text="💳 DEFAULT TO‘LOV",callback_data="set:fee")],back("admin:main")]))

@router.callback_query(F.data.startswith("set:"))
async def setting_start(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    key=callback.data.split(":")[-1]; keymap={'welcome':'welcome','support':'support','fee':'default_fee'}
    if key not in keymap:return
    await state.clear();await state.update_data(key=keymap[key]);await state.set_state(Setting.value);await callback.message.answer("Yangi qiymatni yuboring.")

@router.message(Setting.value)
async def setting_save(message:Message,state:FSMContext):
    d=await state.get_data();set_setting(d['key'],message.text or '');await state.clear();await message.answer("✅ Sozlama saqlandi.",reply_markup=admin_menu())

@router.callback_query(F.data=="admin:admins")
async def admin_list(callback:CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    rows_db=db_all("SELECT telegram_id,active FROM admins ORDER BY telegram_id");text="👮 ADMINLAR\n\n"+('\n'.join(f"{'✅' if x['active'] else '⛔'} {x['telegram_id']}{' ROOT' if x['telegram_id'] in ADMIN_IDS else ''}" for x in rows_db) if rows_db else 'Adminlar yo‘q.')
    rows=[[InlineKeyboardButton(text="➕ ADMIN QO‘SHISH",callback_data="admin:add")],[InlineKeyboardButton(text="🗑 ADMIN O‘CHIRISH",callback_data="admin:remove")],back("admin:main")]
    await callback.message.answer(text,reply_markup=menu(rows))

class AdminState(StatesGroup): add=State(); remove=State()

@router.callback_query(F.data=="admin:add")
async def admin_add(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_root_admin(callback.from_user.id):await callback.message.answer("⛔ Faqat ROOT ADMIN.");return
    await state.clear();await state.set_state(AdminState.add);await callback.message.answer("Yangi admin Telegram ID:")

@router.message(AdminState.add)
async def admin_add_save(message:Message,state:FSMContext):
    try:tg=int(message.text.strip())
    except Exception:await message.answer("⚠️ ID raqam bo‘lishi kerak.");return
    db_exec("INSERT INTO admins(telegram_id,active,created_at) VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET active=1",(tg,1,now_str()))
    db_exec("INSERT INTO users(telegram_id,role,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET role='ADMIN',updated_at=excluded.updated_at",(tg,'ADMIN',now_str(),now_str()))
    await state.clear();await message.answer("✅ Admin qo‘shildi.",reply_markup=admin_menu())

@router.callback_query(F.data=="admin:remove")
async def admin_remove(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_root_admin(callback.from_user.id):await callback.message.answer("⛔ Faqat ROOT ADMIN.");return
    await state.clear();await state.set_state(AdminState.remove);await callback.message.answer("O‘chiriladigan admin Telegram ID:")

@router.message(AdminState.remove)
async def admin_remove_save(message:Message,state:FSMContext):
    try:tg=int(message.text.strip())
    except Exception:await message.answer("⚠️ ID raqam bo‘lishi kerak.");return
    if tg in ADMIN_IDS:await message.answer("⛔ Root adminni o‘chirib bo‘lmaydi.");return
    db_exec("DELETE FROM admins WHERE telegram_id=?",(tg,));await state.clear();await message.answer("✅ Admin o‘chirildi.",reply_markup=admin_menu())

# ============================================================
# BROADCAST
# ============================================================
@router.callback_query(F.data=="admin:broadcast")
async def broadcast_menu(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    await state.clear();await state.set_state(Broadcast.target)
    await callback.message.answer("📢 BROADCAST\n\nKimga yuborilsin?",reply_markup=menu([[InlineKeyboardButton(text="👤 BARCHA USERS",callback_data="bc:all")],[InlineKeyboardButton(text="👨‍🎓 STUDENTS",callback_data="bc:students")],[InlineKeyboardButton(text="👨‍🏫 TEACHERS",callback_data="bc:teachers")],[InlineKeyboardButton(text="⬅️ ORQAGA",callback_data="admin:main")]]))

@router.callback_query(F.data.startswith("bc:"))
async def broadcast_target(callback:CallbackQuery,state:FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):return
    await state.update_data(target=callback.data.split(":")[-1]);await state.set_state(Broadcast.message);await callback.message.answer("📢 Broadcast xabarini yuboring. Text/photo/video/document/audio.")

@router.message(Broadcast.message)
async def broadcast_send(message:Message,state:FSMContext,bot:Bot):
    d=await state.get_data();target=d.get('target')
    if target=='all':ids=[x[0] for x in db_all("SELECT telegram_id FROM users WHERE blocked=0")]
    elif target=='students':ids=[x[0] for x in db_all("SELECT telegram_id FROM students WHERE active=1")]
    else:ids=[x[0] for x in db_all("SELECT telegram_id FROM teachers WHERE active=1")]
    sent=failed=0
    for tg in ids:
        try:await bot.copy_message(tg,message.chat.id,message.message_id);sent+=1
        except Exception as e:failed+=1;log.warning("broadcast %s: %s",tg,e)
        await asyncio.sleep(0.04)
    await state.clear();await message.answer(f"✅ Broadcast tugadi.\nYuborildi: {sent}\nXato: {failed}",reply_markup=admin_menu())

# ============================================================
# AI
# ============================================================
async def ai_conversation(tg_id:int):
    row=db_one("SELECT * FROM ai_conversations WHERE telegram_id=? ORDER BY id DESC LIMIT 1",(tg_id,))
    if row:return row
    cid=db_exec("INSERT INTO ai_conversations(telegram_id,title,created_at,updated_at) VALUES(?,?,?,?)",(tg_id,'DREAM KOREA AI',now_str(),now_str()))
    return db_one("SELECT * FROM ai_conversations WHERE id=?",(cid,))


async def ask_openrouter(tg_id:int,prompt:str):
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith('PUT_'):
        return None,'OpenRouter API key sozlanmagan.'
    conv=await ai_conversation(tg_id)
    hist=db_all("SELECT role,content FROM ai_messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",(conv['id'],AI_MAX_CONTEXT));hist=list(reversed(hist))
    messages=[{"role":"system","content":get_setting('ai_system_prompt')}]
    messages += [{"role":x['role'],"content":x['content']} for x in hist]
    messages.append({"role":"user","content":prompt})
    models=[AI_PRIMARY_MODEL]+[x for x in AI_FALLBACK_MODELS if x!=AI_PRIMARY_MODEL]
    start=asyncio.get_running_loop().time();last='unknown'
    headers={'Authorization':f'Bearer {OPENROUTER_API_KEY}','Content-Type':'application/json','X-Title':'DREAM KOREA'}
    for model in models:
        try:
            timeout=aiohttp.ClientTimeout(total=AI_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post('https://openrouter.ai/api/v1/chat/completions',headers=headers,json={'model':model,'messages':messages,'temperature':0.25}) as resp:
                    raw=await resp.text()
                    if resp.status>=400:
                        last=f'HTTP {resp.status}';continue
                    data=json.loads(raw);choices=data.get('choices') or []
                    if not choices: last='empty';continue
                    content=choices[0].get('message',{}).get('content','')
                    if isinstance(content,list):content=''.join(p.get('text','') for p in content if isinstance(p,dict))
                    content=str(content).strip()
                    if not content:last='empty';continue
                    usage=data.get('usage') or {};elapsed=round(asyncio.get_running_loop().time()-start,3)
                    db_exec("INSERT INTO ai_messages(conversation_id,telegram_id,role,content,model,created_at) VALUES(?,?,?,?,?,?)",(conv['id'],tg_id,'user',prompt,model,now_str()))
                    db_exec("INSERT INTO ai_messages(conversation_id,telegram_id,role,content,model,created_at) VALUES(?,?,?,?,?,?)",(conv['id'],tg_id,'assistant',content,model,now_str()))
                    db_exec("UPDATE ai_conversations SET updated_at=? WHERE id=?",(now_str(),conv['id']))
                    db_exec("INSERT INTO ai_usage(telegram_id,model,success,input_tokens,output_tokens,total_tokens,response_time,created_at) VALUES(?,?,?,?,?,?,?,?)",(tg_id,model,1,usage.get('prompt_tokens'),usage.get('completion_tokens'),usage.get('total_tokens'),elapsed,now_str()))
                    return content,None
        except Exception as e:
            last=str(e)[:200];log.warning("OpenRouter %s failed: %s",model,e)
    elapsed=round(asyncio.get_running_loop().time()-start,3)
    db_exec("INSERT INTO ai_usage(telegram_id,model,success,response_time,created_at) VALUES(?,?,?,?,?)",(tg_id,AI_PRIMARY_MODEL,0,elapsed,now_str()))
    return None,last


# ============================================================
# RANDOM SO‘Z — ADMIN + USER
# ============================================================

def random_norm(value: str) -> str:
    """Normalize Uzbek answers for fair exact comparison."""
    if value is None:
        return ""
    value = value.strip().casefold()
    value = value.replace("’", "'").replace("‘", "'").replace("ʻ", "'").replace("ʼ", "'")
    value = re.sub(r"[\u2010-\u2015\-_/\\]+", " ", value)
    value = re.sub(r"[^\w\s']+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def random_sections_keyboard(admin=False):
    sections = db_all("SELECT rs.*, COUNT(rw.id) AS words_count FROM random_sections rs LEFT JOIN random_words rw ON rw.section_id=rs.id WHERE rs.active=1 GROUP BY rs.id ORDER BY rs.id DESC")
    rows = []
    for s in sections:
        text = f"🎲 {s['name']} ({s['words_count']})"
        cb = f"rand:asection:{s['id']}" if admin else f"rand:usection:{s['id']}"
        rows.append([InlineKeyboardButton(text=text[:60], callback_data=cb)])
    if admin:
        rows.append(back("admin:random"))
    else:
        rows.append(back("main"))
    return menu(rows)


async def send_random_question(message: Message, state: FSMContext):
    data = await state.get_data()
    ids = data.get("word_ids") or []
    idx = int(data.get("index", 0))
    if idx >= len(ids):
        await finish_random_quiz(message, state)
        return
    word = db_one("SELECT korean FROM random_words WHERE id=?", (int(ids[idx]),))
    if not word:
        await state.update_data(index=idx + 1)
        await send_random_question(message, state)
        return
    total = int(data.get("total", len(ids)))
    current = idx + 1
    await message.answer(
        f"🎲 RANDOM SO‘Z\n\n"
        f"Savol: {current}/{total}\n\n"
        f"🇰🇷 {word['korean']}\n\n"
        f"🇺🇿 O‘zbekchasini yozing:"
    )


async def finish_random_quiz(message: Message, state: FSMContext):
    data = await state.get_data()
    total = int(data.get("total", 0))
    correct = int(data.get("correct", 0))
    wrong = int(data.get("wrong", 0))
    percent = round(correct * 100 / total) if total else 0
    section_id = data.get("section_id")
    section = db_one("SELECT name FROM random_sections WHERE id=?", (section_id,)) if section_id else None
    name = section["name"] if section else "—"
    await state.clear()
    await message.answer(
        f"🏁 RANDOM SO‘Z YAKUNLANDI\n\n"
        f"🎲 Bo‘lim: {name}\n"
        f"📚 Jami: {total}\n"
        f"✅ To‘g‘ri: {correct}\n"
        f"❌ Xato: {wrong}\n"
        f"📊 Natija: {percent}%",
        reply_markup=menu([[InlineKeyboardButton(text="🎲 YANA BIR TEST", callback_data=f"rand:replay:{section_id}")], [InlineKeyboardButton(text="🏠 BOSH MENYU", callback_data="main")]])
    )


@router.callback_query(F.data=="random:user")
async def random_user_sections(callback: CallbackQuery):
    await callback.answer()
    if blocked(callback.from_user.id):
        await callback.message.answer("🚫 Siz bloklangansiz.")
        return
    sections = db_all("SELECT rs.id, rs.name, COUNT(rw.id) AS words_count FROM random_sections rs LEFT JOIN random_words rw ON rw.section_id=rs.id WHERE rs.active=1 GROUP BY rs.id ORDER BY rs.id DESC")
    if not sections:
        await callback.message.answer("🎲 RANDOM SO‘Z\n\nHozircha bo‘limlar mavjud emas.", reply_markup=menu([back("main")]))
        return
    await callback.message.answer("🎲 RANDOM SO‘Z\n\nTest uchun bo‘limni tanlang:", reply_markup=random_sections_keyboard(admin=False))


@router.callback_query(F.data.startswith("rand:usection:"))
async def random_user_section(callback: CallbackQuery):
    await callback.answer()
    sid = int(callback.data.split(":")[-1])
    section = db_one("SELECT rs.*, COUNT(rw.id) AS words_count FROM random_sections rs LEFT JOIN random_words rw ON rw.section_id=rs.id WHERE rs.id=? AND rs.active=1 GROUP BY rs.id", (sid,))
    if not section:
        await callback.message.answer("⚠️ Bo‘lim topilmadi.", reply_markup=menu([back("random:user")]))
        return
    if section["words_count"] == 0:
        await callback.message.answer(f"🎲 {section['name']}\n\n⚠️ Bu bo‘limda hali so‘zlar yo‘q.", reply_markup=menu([back("random:user")]))
        return
    await callback.message.answer(
        f"🎲 {section['name']}\n\n"
        f"📚 So‘zlar soni: {section['words_count']} ta\n\n"
        f"Boshlash tugmasini bosing. Barcha so‘zlar bir martadan aralashtirib beriladi.",
        reply_markup=menu([
            [InlineKeyboardButton(text="▶️ BOSHLASH", callback_data=f"rand:start:{sid}")],
            [InlineKeyboardButton(text="⬅️ BO‘LIMLAR", callback_data="random:user")]
        ])
    )


@router.callback_query(F.data.startswith("rand:replay:"))
async def random_replay(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sid = int(callback.data.split(":")[-1])
    await start_random_quiz(callback.message, sid, state)


async def start_random_quiz(message: Message, section_id: int, state: FSMContext):
    words = db_all("SELECT id FROM random_words WHERE section_id=? ORDER BY id", (section_id,))
    if not words:
        await message.answer("⚠️ Bu bo‘limda so‘zlar mavjud emas.", reply_markup=menu([back("random:user")]))
        return
    ids = [int(x["id"]) for x in words]
    random.shuffle(ids)
    await state.clear()
    await state.update_data(section_id=section_id, word_ids=ids, index=0, correct=0, wrong=0, total=len(ids))
    await state.set_state(RandomQuiz.answer)
    await send_random_question(message, state)


@router.callback_query(F.data.startswith("rand:start:"))
async def random_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sid = int(callback.data.split(":")[-1])
    await start_random_quiz(callback.message, sid, state)


@router.message(RandomQuiz.answer)
async def random_answer(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("⚠️ Javobni matn ko‘rinishida yozing.")
        return
    data = await state.get_data()
    ids = data.get("word_ids") or []
    idx = int(data.get("index", 0))
    if idx >= len(ids):
        await finish_random_quiz(message, state)
        return
    word = db_one("SELECT korean,uzbek FROM random_words WHERE id=?", (int(ids[idx]),))
    if not word:
        await state.update_data(index=idx + 1)
        await send_random_question(message, state)
        return
    user_answer = random_norm(message.text)
    correct_answer = random_norm(word["uzbek"])
    is_correct = user_answer == correct_answer
    correct = int(data.get("correct", 0)) + (1 if is_correct else 0)
    wrong = int(data.get("wrong", 0)) + (0 if is_correct else 1)
    next_index = idx + 1
    await state.update_data(index=next_index, correct=correct, wrong=wrong)
    if is_correct:
        result_text = "✅ To‘g‘ri!"
    else:
        result_text = f"❌ Xato.\nTo‘g‘ri javob: {word['uzbek']}"
    if next_index >= len(ids):
        await message.answer(result_text)
        await finish_random_quiz(message, state)
        return
    await message.answer(result_text)
    await send_random_question(message, state)


# ---------------- ADMIN RANDOM ----------------

@router.callback_query(F.data=="admin:random")
async def admin_random_menu(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sections_count = db_one("SELECT COUNT(*) FROM random_sections WHERE active=1")[0]
    words_count = db_one("SELECT COUNT(*) FROM random_words rw JOIN random_sections rs ON rs.id=rw.section_id WHERE rs.active=1")[0]
    await callback.message.answer(
        f"🎲 RANDOM SO‘Z BOSHQARUVI\n\n"
        f"📚 Bo‘limlar: {sections_count}\n"
        f"📝 So‘zlar: {words_count}\n\n"
        f"Bu yerda random test bo‘limlari va so‘zlarini boshqarishingiz mumkin.",
        reply_markup=menu([
            [InlineKeyboardButton(text="➕ RANDOM QO‘SHISH", callback_data="rand:add")],
            [InlineKeyboardButton(text="✏️ RANDOM TAHRIRLASH", callback_data="rand:edit")],
            [InlineKeyboardButton(text="⬅️ ADMIN PANEL", callback_data="admin:main")]
        ])
    )


@router.callback_query(F.data=="rand:add")
async def random_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await state.set_state(RandomSectionAdd.name)
    await callback.message.answer("🎲 RANDOM QO‘SHISH\n\n1-qadam. Bo‘lim nomini kiriting:")


@router.message(RandomSectionAdd.name)
async def random_add_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("⚠️ Bo‘lim nomi juda qisqa.")
        return
    exists = db_one("SELECT id FROM random_sections WHERE lower(name)=lower(?)", (name,))
    if exists:
        await message.answer("⚠️ Bunday bo‘lim allaqachon mavjud. Boshqa nom kiriting.")
        return
    sid = db_exec("INSERT INTO random_sections(name,active,created_at,updated_at) VALUES(?,?,?,?)", (name, 1, now_str(), now_str()))
    await state.update_data(section_id=sid, section_name=name)
    await state.set_state(RandomSectionAdd.korean)
    await message.answer(f"✅ {name} bo‘limi yaratildi.\n\n2-qadam. Koreyscha so‘zni kiriting:")


@router.message(RandomSectionAdd.korean)
async def random_add_korean(message: Message, state: FSMContext):
    korean = (message.text or "").strip()
    if len(korean) < 1:
        await message.answer("⚠️ Koreyscha so‘zni kiriting.")
        return
    await state.update_data(korean=korean)
    await state.set_state(RandomSectionAdd.uzbek)
    await message.answer("3-qadam. So‘zning o‘zbekcha tarjimasini kiriting:")


async def random_after_add_word(message: Message, state: FSMContext, section_id: int):
    section = db_one("SELECT name FROM random_sections WHERE id=?", (section_id,))
    name = section["name"] if section else "—"
    count = db_one("SELECT COUNT(*) FROM random_words WHERE section_id=?", (section_id,))[0]
    await state.clear()
    await message.answer(
        f"✅ So‘z qo‘shildi.\n\n"
        f"🎲 Bo‘lim: {name}\n"
        f"📝 Jami so‘zlar: {count} ta\n\n"
        f"Yana so‘z qo‘shasizmi?",
        reply_markup=menu([
            [InlineKeyboardButton(text="➕ YANA SO‘Z QO‘SHISH", callback_data=f"rand:addmore:{section_id}")],
            [InlineKeyboardButton(text="🏠 ADMIN PANEL", callback_data="admin:main")]
        ])
    )


@router.message(RandomSectionAdd.uzbek)
async def random_add_uzbek(message: Message, state: FSMContext):
    uzbek = (message.text or "").strip()
    if len(uzbek) < 1:
        await message.answer("⚠️ O‘zbekcha tarjimani kiriting.")
        return
    data = await state.get_data()
    sid = int(data["section_id"])
    korean = data["korean"]
    try:
        db_exec("INSERT INTO random_words(section_id,korean,uzbek,created_at,updated_at) VALUES(?,?,?,?,?)", (sid, korean, uzbek, now_str(), now_str()))
    except sqlite3.IntegrityError:
        await message.answer("⚠️ Aynan shu koreyscha + o‘zbekcha juftlik bu bo‘limda allaqachon mavjud. Boshqa so‘z kiriting.")
        await state.set_state(RandomSectionAdd.korean)
        await message.answer("Koreyscha yangi so‘zni kiriting:")
        return
    await random_after_add_word(message, state, sid)


@router.callback_query(F.data.startswith("rand:addmore:"))
async def random_add_more(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[-1])
    section = db_one("SELECT name FROM random_sections WHERE id=? AND active=1", (sid,))
    if not section:
        await callback.message.answer("⚠️ Bo‘lim topilmadi.", reply_markup=menu([back("admin:random")]))
        return
    await state.clear()
    await state.update_data(section_id=sid, section_name=section["name"])
    await state.set_state(RandomSectionAdd.korean)
    await callback.message.answer(f"🎲 {section['name']}\n\nKoreyscha yangi so‘zni kiriting:")


@router.callback_query(F.data=="rand:edit")
async def random_edit_list(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sections = db_all("SELECT rs.id,rs.name,COUNT(rw.id) AS words_count FROM random_sections rs LEFT JOIN random_words rw ON rw.section_id=rs.id WHERE rs.active=1 GROUP BY rs.id ORDER BY rs.id DESC")
    if not sections:
        await callback.message.answer("🎲 RANDOM TAHRIRLASH\n\nBo‘limlar yo‘q.", reply_markup=menu([back("admin:random")]))
        return
    await callback.message.answer("🎲 RANDOM TAHRIRLASH\n\nTahrir qilinadigan bo‘limni tanlang:", reply_markup=random_sections_keyboard(admin=True))


@router.callback_query(F.data.startswith("rand:asection:"))
async def random_admin_section(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[-1])
    section = db_one("SELECT rs.*,COUNT(rw.id) AS words_count FROM random_sections rs LEFT JOIN random_words rw ON rw.section_id=rs.id WHERE rs.id=? GROUP BY rs.id", (sid,))
    if not section:
        await callback.message.answer("⚠️ Bo‘lim topilmadi.", reply_markup=menu([back("rand:edit")]))
        return
    await callback.message.answer(
        f"🎲 {section['name']}\n\n"
        f"📝 So‘zlar: {section['words_count']} ta",
        reply_markup=menu([
            [InlineKeyboardButton(text="➕ SO‘Z QO‘SHISH", callback_data=f"rand:addmore:{sid}")],
            [InlineKeyboardButton(text="📝 SO‘ZLARNI BOSHQARISH", callback_data=f"rand:words:{sid}:1")],
            [InlineKeyboardButton(text="✏️ BO‘LIM NOMINI TAHRIRLASH", callback_data=f"rand:rename:{sid}")],
            [InlineKeyboardButton(text="🗑 BO‘LIMNI O‘CHIRISH", callback_data=f"rand:delete_confirm:{sid}")],
            [InlineKeyboardButton(text="⬅️ BO‘LIMLAR", callback_data="rand:edit")]
        ])
    )


@router.callback_query(F.data.startswith("rand:rename:"))
async def random_rename_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[-1])
    section = db_one("SELECT name FROM random_sections WHERE id=?", (sid,))
    if not section:
        await callback.message.answer("⚠️ Bo‘lim topilmadi.")
        return
    await state.clear()
    await state.update_data(section_id=sid)
    await state.set_state(RandomSectionRename.name)
    await callback.message.answer(f"Joriy nom: {section['name']}\n\nYangi bo‘lim nomini kiriting:")


@router.message(RandomSectionRename.name)
async def random_rename_save(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("⚠️ Nom juda qisqa.")
        return
    data = await state.get_data(); sid = int(data["section_id"])
    exists = db_one("SELECT id FROM random_sections WHERE lower(name)=lower(?) AND id!=?", (name, sid))
    if exists:
        await message.answer("⚠️ Bunday bo‘lim allaqachon mavjud.")
        return
    db_exec("UPDATE random_sections SET name=?,updated_at=? WHERE id=?", (name, now_str(), sid))
    await state.clear()
    await message.answer("✅ Bo‘lim nomi yangilandi.", reply_markup=admin_menu())


@router.callback_query(F.data.startswith("rand:delete_confirm:"))
async def random_delete_confirm(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[-1])
    section = db_one("SELECT name FROM random_sections WHERE id=?", (sid,))
    if not section:
        await callback.message.answer("⚠️ Bo‘lim topilmadi.")
        return
    count = db_one("SELECT COUNT(*) FROM random_words WHERE section_id=?", (sid,))[0]
    await callback.message.answer(
        f"⚠️ {section['name']} bo‘limini o‘chirishni tasdiqlaysizmi?\n\n"
        f"Undagi {count} ta so‘z ham o‘chiriladi.",
        reply_markup=menu([
            [InlineKeyboardButton(text="✅ HA, O‘CHIRISH", callback_data=f"rand:delete:{sid}")],
            [InlineKeyboardButton(text="❌ BEKOR", callback_data=f"rand:asection:{sid}")]
        ])
    )


@router.callback_query(F.data.startswith("rand:delete:"))
async def random_delete_section(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[-1])
    section = db_one("SELECT name FROM random_sections WHERE id=?", (sid,))
    if not section:
        return
    db_exec("DELETE FROM random_sections WHERE id=?", (sid,))
    await callback.message.answer(f"✅ {section['name']} bo‘limi va uning so‘zlari o‘chirildi.", reply_markup=admin_menu())


def random_words_kb(section_id: int, page: int = 1):
    limit = 20
    offset = (page - 1) * limit
    total = db_one("SELECT COUNT(*) FROM random_words WHERE section_id=?", (section_id,))[0]
    items = db_all("SELECT * FROM random_words WHERE section_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (section_id, limit, offset))
    pages = max(1, (total + limit - 1) // limit)
    rows = []
    for w in items:
        label = f"{w['korean']} — {w['uzbek']}"
        rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"rand:wordview:{w['id']}:{section_id}:{page}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"rand:words:{section_id}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"rand:words:{section_id}:{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="➕ SO‘Z QO‘SHISH", callback_data=f"rand:addmore:{section_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ BO‘LIM", callback_data=f"rand:asection:{section_id}")])
    return menu(rows)


@router.callback_query(F.data.startswith("rand:words:"))
async def random_words_manage(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    _, _, sid, page = callback.data.split(":")
    sid, page = int(sid), int(page)
    section = db_one("SELECT name FROM random_sections WHERE id=?", (sid,))
    if not section:
        return
    total = db_one("SELECT COUNT(*) FROM random_words WHERE section_id=?", (sid,))[0]
    await callback.message.answer(f"📝 {section['name']} — SO‘ZLAR\n\nJami: {total} ta", reply_markup=random_words_kb(sid, page))


@router.callback_query(F.data.startswith("rand:wordview:"))
async def random_word_view(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    _, _, wid, sid, page = callback.data.split(":")
    word = db_one("SELECT * FROM random_words WHERE id=? AND section_id=?", (int(wid), int(sid)))
    if not word:
        await callback.message.answer("⚠️ So‘z topilmadi.")
        return
    await callback.message.answer(
        f"🎲 SO‘Z\n\n🇰🇷 Koreyscha: {word['korean']}\n🇺🇿 O‘zbekcha: {word['uzbek']}",
        reply_markup=menu([
            [InlineKeyboardButton(text="✏️ TAHRIRLASH", callback_data=f"rand:wordedit:{word['id']}:{sid}")],
            [InlineKeyboardButton(text="🗑 O‘CHIRISH", callback_data=f"rand:worddelete_confirm:{word['id']}:{sid}")],
            [InlineKeyboardButton(text="⬅️ SO‘ZLAR", callback_data=f"rand:words:{sid}:{page}")]
        ])
    )


@router.callback_query(F.data.startswith("rand:wordedit:"))
async def random_word_edit_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    _, _, wid, sid = callback.data.split(":")
    word = db_one("SELECT * FROM random_words WHERE id=? AND section_id=?", (int(wid), int(sid)))
    if not word:
        await callback.message.answer("⚠️ So‘z topilmadi.")
        return
    await state.clear()
    await state.update_data(word_id=int(wid), section_id=int(sid))
    await state.set_state(RandomWordEdit.korean)
    await callback.message.answer(f"Joriy koreyscha: {word['korean']}\n\nYangi koreyscha so‘zni kiriting:")


@router.message(RandomWordEdit.korean)
async def random_word_edit_korean(message: Message, state: FSMContext):
    korean = (message.text or "").strip()
    if not korean:
        await message.answer("⚠️ Koreyscha so‘z kerak.")
        return
    await state.update_data(korean=korean)
    await state.set_state(RandomWordEdit.uzbek)
    await message.answer("Yangi o‘zbekcha tarjimani kiriting:")


@router.message(RandomWordEdit.uzbek)
async def random_word_edit_uzbek(message: Message, state: FSMContext):
    uzbek = (message.text or "").strip()
    if not uzbek:
        await message.answer("⚠️ O‘zbekcha tarjima kerak.")
        return
    data = await state.get_data(); wid=int(data['word_id']); sid=int(data['section_id'])
    try:
        db_exec("UPDATE random_words SET korean=?,uzbek=?,updated_at=? WHERE id=? AND section_id=?", (data['korean'], uzbek, now_str(), wid, sid))
    except sqlite3.IntegrityError:
        await message.answer("⚠️ Bu juftlik bo‘limda allaqachon mavjud. Boshqa tarjima yoki so‘z kiriting.")
        return
    await state.clear()
    await message.answer("✅ So‘z tahrirlandi.", reply_markup=admin_menu())


@router.callback_query(F.data.startswith("rand:worddelete_confirm:"))
async def random_word_delete_confirm(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    _, _, wid, sid = callback.data.split(":")
    word = db_one("SELECT korean,uzbek FROM random_words WHERE id=? AND section_id=?", (int(wid), int(sid)))
    if not word:
        await callback.message.answer("⚠️ So‘z topilmadi.")
        return
    await callback.message.answer(
        f"⚠️ Ushbu so‘zni o‘chirishni tasdiqlaysizmi?\n\n🇰🇷 {word['korean']}\n🇺🇿 {word['uzbek']}",
        reply_markup=menu([
            [InlineKeyboardButton(text="✅ HA, O‘CHIRISH", callback_data=f"rand:worddelete:{wid}:{sid}")],
            [InlineKeyboardButton(text="❌ BEKOR", callback_data=f"rand:asection:{sid}")]
        ])
    )


@router.callback_query(F.data.startswith("rand:worddelete:"))
async def random_word_delete(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    _, _, wid, sid = callback.data.split(":")
    db_exec("DELETE FROM random_words WHERE id=? AND section_id=?", (int(wid), int(sid)))
    await callback.message.answer("✅ So‘z o‘chirildi.", reply_markup=menu([[InlineKeyboardButton(text="⬅️ BO‘LIM", callback_data=f"rand:asection:{sid}")],[InlineKeyboardButton(text="🏠 ADMIN PANEL", callback_data="admin:main")]]))

# ============================================================
# GLOBAL NAVIGATION
# ============================================================
@router.callback_query(F.data=="main")
async def go_main(callback: CallbackQuery):
    await callback.answer()
    ensure_user(callback.from_user)
    await safe_answer(callback, get_setting("welcome"), main_menu())


@router.callback_query(F.data=="admin:main")
async def go_admin_main(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        return
    await safe_answer(callback, "🇰🇷 DREAM KOREA — ADMIN PANEL", admin_menu())


# ============================================================
# GLOBAL CALLBACK / TEXT
# ============================================================
@router.callback_query(F.data=="noop")
async def noop(callback:CallbackQuery):await callback.answer()

@router.message(F.text)
async def final_text_handler(message:Message):
    ensure_user(message.from_user)
    if blocked(message.from_user.id):await message.answer("🚫 Siz bloklangansiz.");return
    if message.text.startswith('/'):return
    user=get_user(message.from_user.id)
    if not user or not user['ai_active']:
        await message.answer("Kerakli bo‘limni menyudan tanlang. AI kerak bo‘lsa /ai yuboring.",reply_markup=main_menu());return
    last=float(user['ai_last_request'] or 0);now_ts=datetime.now().timestamp()
    if now_ts-last<AI_COOLDOWN_SECONDS:await message.answer("⏳ Biroz kuting.");return
    if len(message.text)>AI_MAX_INPUT:await message.answer(f"⚠️ Xabar juda uzun. Maksimum: {AI_MAX_INPUT} belgi.");return
    db_exec("UPDATE users SET ai_last_request=?,updated_at=? WHERE telegram_id=?",(now_ts,now_str(),message.from_user.id))
    await message.bot.send_chat_action(message.chat.id,'typing')
    result,error=await ask_openrouter(message.from_user.id,message.text)
    if not result:
        await message.answer("⚠️ AI ishlamadi. OpenRouter API key/model sozlamasini tekshiring.");return
    for part in chunk_text(result):await message.answer(part)

@router.callback_query()
async def unknown_callback(callback:CallbackQuery):await callback.answer("Bu amal topilmadi.",show_alert=True)


# ============================================================
# STARTUP
# ============================================================
async def main():
    if BOT_TOKEN.startswith('PUT_'):
        raise RuntimeError('BOT_TOKEN ni main.py ichida kiriting.')
    db_init()
    bot=Bot(token=BOT_TOKEN,default=DefaultBotProperties(parse_mode=None))
    dp=Dispatcher(storage=MemoryStorage());dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_my_commands([
            BotCommand(command='start',description='DREAM KOREA bosh menyu'),
            BotCommand(command='ai',description='AI yordamchini yoqish'),
            BotCommand(command='stop',description='AI yordamchini o‘chirish'),
            BotCommand(command='kabinet',description='Shaxsiy kabinet'),
            BotCommand(command='ustoz',description='Ustoz paneli'),
            BotCommand(command='admin',description='Admin panel'),
            BotCommand(command='cancel',description='Amalni bekor qilish'),
        ])
        log.info('DREAM KOREA started')
        await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close();db.close()

if __name__=='__main__':
    try:asyncio.run(main())
    except (KeyboardInterrupt,SystemExit):log.info('Stopped')
