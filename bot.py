# -------------- bot.py (исправленная версия 3.1 - БЕЗ ОШИБОК) --------------
import discord, json, os, asyncio, re
from datetime import datetime, timedelta, timezone
from discord.ext import tasks
from discord import app_commands
from discord.ui import Button, View

# ==================== НАСТРОЙКИ ====================
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1430087806952411230
ADMIN_ROLES = ["dep.YAK", "Owner", "Leader"]
VIEW_ROLES = ["member", "Test", "Famlily", "Yak"]

# ID каналов
STATS_AVG_CHANNEL_ID = 1467543899643052312
STATS_KILLS_CHANNEL_ID = 1467543933209809076
CAPTS_LIST_CHANNEL_ID = 1467544000088117451
LOG_CHANNEL_ID = None  # Укажите ID канала для логов

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DB_STATS = "stats.json"
DB_CAPTS = "capts.json"

# ==================== УТИЛИТЫ ====================
def now():
    """Получить текущее время UTC"""
    return datetime.now(timezone.utc)

def load_stats() -> dict:
    try:
        with open(DB_STATS, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_stats(data: dict):
    with open(DB_STATS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_capts() -> list:
    try:
        with open(DB_CAPTS, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_capts(data: list):
    with open(DB_CAPTS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def has_role(member: discord.Member, roles):
    return any(r.name in roles for r in member.roles)

def progress_bar(percent: int, length: int = 10):
    filled = int(percent / 100 * length)
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)

def medal(pos: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "")

def get_capts_in_period(days: int = None):
    """Получить капты за период"""
    capts = load_capts()
    if days is None:
        return capts
    
    cutoff = now() - timedelta(days=days)
    return [c for c in capts if datetime.fromisoformat(c["date"]).replace(tzinfo=timezone.utc) >= cutoff]

def calculate_stats(capts_list: list) -> dict:
    """Рассчитать статистику из списка каптов"""
    stats = {}
    for capt in capts_list:
        for player in capt["players"]:
            uid = str(player["user_id"])
            if uid not in stats:
                stats[uid] = {"damage": 0, "kills": 0, "games": 0}
            stats[uid]["damage"] += player["damage"]
            stats[uid]["kills"] += player["kills"]
            stats[uid]["games"] += 1
    return stats

async def log_action(guild: discord.Guild, user: discord.Member, action: str, details: str = ""):
    """Логирование действий в лог-канал"""
    if not LOG_CHANNEL_ID:
        return
    
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(
        description=f"**{action}**\n{details}",
        color=0x3498db,
        timestamp=now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    
    try:
        await channel.send(embed=embed)
    except:
        pass

# ==================== VIEW ДЛЯ СПИСКА КАПТОВ ====================
class CaptsListView(View):
    def __init__(self, guild: discord.Guild, period: str = "all"):
        super().__init__(timeout=None)
        self.guild = guild
        self.period = period
        self.current_page = 0
        self.capts_per_page = 10
        self.update_data()

    def update_data(self):
        if self.period == "week":
            self.capts = get_capts_in_period(7)
        elif self.period == "month":
            self.capts = get_capts_in_period(30)
        else:
            self.capts = load_capts()
        
        self.total_pages = max(1, (len(self.capts) + self.capts_per_page - 1) // self.capts_per_page)
        if self.current_page >= self.total_pages:
            self.current_page = max(0, self.total_pages - 1)

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, custom_id="capts_prev")
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.primary, custom_id="capts_page")
    async def page_info(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="capts_next")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="🔄", style=discord.ButtonStyle.success, custom_id="capts_refresh")
    async def refresh(self, interaction: discord.Interaction, button: Button):
        self.update_data()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = await self.create_embed()
        for child in self.children:
            if isinstance(child, Button):
                if child.custom_id == "capts_page":
                    child.label = f"{self.current_page + 1}/{self.total_pages}"
                elif child.custom_id == "capts_prev":
                    child.disabled = self.current_page == 0
                elif child.custom_id == "capts_next":
                    child.disabled = self.current_page >= self.total_pages - 1

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except:
            try:
                await interaction.message.edit(embed=embed, view=self)
            except:
                pass

    async def create_embed(self):
        period_text = {
            "week": "📅 за неделю",
            "month": "📅 за месяц",
            "all": "📜 вся история"
        }.get(self.period, "")
        
        embed = discord.Embed(
            title=f"⚔️ История каптов Семьи {period_text}",
            color=0xe74c3c,
            timestamp=now()
        )

        if not self.capts:
            embed.description = "📭 Нет каптов за этот период"
        else:
            reversed_capts = list(reversed(self.capts))
            start = self.current_page * self.capts_per_page
            end = min(start + self.capts_per_page, len(reversed_capts))

            desc = ""
            for i in range(start, end):
                capt = reversed_capts[i]
                num = len(self.capts) - i
                date = datetime.fromisoformat(capt["date"]).strftime("%d.%m.%Y %H:%M")
                result = "✅" if capt["win"] else "❌"
                players = len(capt["players"])
                damage = sum(p["damage"] for p in capt["players"])
                kills = sum(p["kills"] for p in capt["players"])

                desc += f"**#{num}. Семья vs {capt['vs']}** {result}\n"
                desc += f"🕐 {date} │ 👥 {players} │ 💥 {damage:,} │ ☠️ {kills}\n\n"

            embed.description = desc

            wins = sum(1 for c in self.capts if c["win"])
            total = len(self.capts)
            winrate = (wins/total*100) if total > 0 else 0

            embed.add_field(
                name="📊 Статистика",
                value=f"```Всего:     {total}\nПобед:     {wins}\nПоражений: {total-wins}\nВинрейт:   {winrate:.1f}%```",
                inline=False
            )

        embed.set_footer(text=f"Страница {self.current_page+1}/{self.total_pages}")
        return embed

# ==================== КОМАНДЫ ====================
@tree.command(name="добавить_капт", description="📝 Добавить новый капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    против="Против кого играли",
    результат="win или lose",
    дата="Дата (ДД.ММ.ГГГГ ЧЧ:ММ)"
)
async def add_capt(inter: discord.Interaction, против: str, результат: str, дата: str = None):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    result_text = результат.strip().lower()
    if result_text not in ["win", "lose", "победа", "поражение", "в", "п"]:
        return await inter.response.send_message("❌ Результат: win или lose", ephemeral=True)
    
    win = result_text in ["win", "победа", "в"]
    
    capt_date = now()
    if дата:
        try:
            capt_date = datetime.strptime(дата, "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
        except:
            try:
                capt_date = datetime.strptime(дата, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            except:
                return await inter.response.send_message("❌ Неверный формат даты", ephemeral=True)
    
    new_capt = {
        "vs": против.strip(),
        "date": capt_date.isoformat(),
        "win": win,
        "players": []
    }
    
    capts = load_capts()
    capts.append(new_capt)
    save_capts(capts)
    
    asyncio.create_task(update_capts_list())
    
    await log_action(
        inter.guild, inter.user,
        "➕ Капт создан",
        f"Против: **{против}**\nРезультат: {'✅ Победа' if win else '❌ Поражение'}"
    )
    
    await inter.response.send_message(
        f"✅ Капт против **{против}** создан!\n"
        f"Результат: {'✅ Победа' if win else '❌ Поражение'}",
        ephemeral=True
    )

@tree.command(name="добавить_игрока", description="👤 Добавить игрока в капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    игрок="@упоминание или ID",
    урон="Урон",
    киллы="Киллы",
    номер_капта="Номер капта (1 = последний)"
)
async def add_player(inter: discord.Interaction, игрок: str, урон: int, киллы: int, номер_капта: int = 1):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    mention_text = игрок.strip()
    user_id = None
    
    if mention_text.startswith("<@") and mention_text.endswith(">"):
        user_id = int(mention_text.strip("<@!>"))
    else:
        try:
            user_id = int(mention_text)
        except:
            return await inter.response.send_message("❌ Используйте @упоминание или ID", ephemeral=True)

    try:
        member = await inter.guild.fetch_member(user_id)
    except:
        return await inter.response.send_message("❌ Игрок не найден", ephemeral=True)

    capts = load_capts()
    if номер_капта < 1 or номер_капта > len(capts):
        return await inter.response.send_message("❌ Капт не найден", ephemeral=True)

    capt = capts[-номер_капта]
    
    if any(p["user_id"] == user_id for p in capt["players"]):
        return await inter.response.send_message(f"❌ **{member.display_name}** уже в капте", ephemeral=True)

    capt["players"].append({
        "user_id": user_id,
        "user_name": member.display_name,
        "damage": урон,
        "kills": киллы
    })

    st = load_stats()
    uid = str(user_id)
    if uid not in st:
        st[uid] = {"damage": 0, "kills": 0, "games": 0}
    
    st[uid]["damage"] += урон
    st[uid]["kills"] += киллы
    st[uid]["games"] += 1
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_capts_list())
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    
    await log_action(
        inter.guild, inter.user,
        "👤 Игрок добавлен",
        f"Капт #{len(capts) - номер_капта + 1}\nИгрок: {member.mention}\nУрон: {урон:,}\nКиллы: {киллы}"
    )
    
    await inter.response.send_message(
        f"✅ **{member.display_name}** добавлен\n"
        f"💥 Урон: **{урон:,}** │ ☠️ Киллы: **{киллы}**",
        ephemeral=True
    )

@tree.command(name="загрузить_игроков", description="📤 Загрузить игроков из текста", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    данные="ID урон киллы (каждый с новой строки)",
    номер_капта="Номер капта"
)
async def upload_players(inter: discord.Interaction, данные: str, номер_капта: int = 1):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        capts = load_capts()
        if номер_капта < 1 or номер_капта > len(capts):
            if defer_used:
                await inter.followup.send("❌ Капт не найден", ephemeral=True)
            else:
                await inter.response.send_message("❌ Капт не найден", ephemeral=True)
            return
        
        capt = capts[-номер_капта]
        lines = данные.strip().split('\n')
        added = 0
        errors = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) < 3:
                errors.append(f"❌ Неверный формат: {line}")
                continue
            
            try:
                user_id = int(parts[0])
                damage = int(parts[1].replace('k', '000').replace('K', '000'))
                kills = int(parts[2])
            except:
                errors.append(f"❌ Ошибка парсинга: {line}")
                continue
            
            try:
                member = await inter.guild.fetch_member(user_id)
            except:
                errors.append(f"❌ Игрок {user_id} не найден")
                continue
            
            if any(p["user_id"] == user_id for p in capt["players"]):
                errors.append(f"⚠️ {member.display_name} уже добавлен")
                continue
            
            capt["players"].append({
                "user_id": user_id,
                "user_name": member.display_name,
                "damage": damage,
                "kills": kills
            })
            
            st = load_stats()
            uid = str(user_id)
            if uid not in st:
                st[uid] = {"damage": 0, "kills": 0, "games": 0}
            st[uid]["damage"] += damage
            st[uid]["kills"] += kills
            st[uid]["games"] += 1
            save_stats(st)
            
            added += 1
        
        save_capts(capts)
        
        asyncio.create_task(update_capts_list())
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())
        
        await log_action(
            inter.guild, inter.user,
            "📤 Массовое добавление",
            f"Капт #{len(capts) - номер_капта + 1}\nДобавлено: {added} игроков"
        )
        
        msg = f"✅ Добавлено игроков: **{added}**"
        if errors:
            msg += f"\n\n⚠️ Ошибки:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... и ещё {len(errors)-5}"
        
        if defer_used:
            await inter.followup.send(msg, ephemeral=True)
        else:
            await inter.response.send_message(msg, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в upload_players: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="загрузить_капты", description="📁 Загрузить капты из файла", guild=discord.Object(GUILD_ID))
@app_commands.describe(
    файл="Текстовый файл с каптами",
)
async def upload_capts(inter: discord.Interaction, файл: discord.Attachment, результат: str = "win"):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        if not файл.filename.endswith('.txt'):
            if defer_used:
                await inter.followup.send("❌ Файл должен быть .txt", ephemeral=True)
            else:
                await inter.response.send_message("❌ Файл должен быть .txt", ephemeral=True)
            return
        
        content = await файл.read()
        text = content.decode('utf-8')
        
        capts = load_capts()
        st = load_stats()
        lines = text.strip().split('\n')
        
        current_capt_players = []
        current_capt_info = None
        current_family_name = ""
        current_date_time = None
        current_result = результат
        added_capts = 0
        errors = []
        
        def save_current_capt():
            nonlocal added_capts, current_capt_players, current_family_name, current_date_time, current_result
            
            if current_capt_players:
                try:
                    # Используем дату из файла или текущую
                    if current_date_time:
                        dt = current_date_time
                    
                    new_capt = {
                        "vs": current_family_name if current_family_name else "Противник",
                        "date": dt.isoformat(),
                        "win": current_result.lower() in ["win", "w", "1", "true", "победа", "в"],
                        "players": current_capt_players.copy()
                    }
                    capts.append(new_capt)
                    added_capts += 1
                    
                    # Обновляем статистику для всех игроков
                    for player in current_capt_players:
                        uid = str(player["user_id"])
                        if uid not in st:
                            st[uid] = {"damage": 0, "kills": 0, "games": 0}
                        st[uid]["damage"] += player["damage"]
                        st[uid]["kills"] += player["kills"]
                        st[uid]["games"] += 1
                        
                except Exception as e:
                    errors.append(f"❌ Ошибка сохранения капта - {str(e)}")
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            if not line:
                # Пустая строка - пропускаем
                continue
            
            # Проверяем, является ли строка заголовком капта (начинается с "Семья")
            if line.lower().startswith("семья"):
                # Сохраняем предыдущий капт (если есть)
                save_current_capt()
                
                # Сбрасываем данные для нового капта
                current_capt_players = []
                current_family_name = ""
                current_date_time = None
                current_result = результат
                
                # Парсим заголовок
                try:
                    # Удаляем "Семья" из начала строки
                    header = line[6:].strip()  # "Семья " - 6 символов
                    
                    # Ищем дату и время в формате DD.MM.YYYY HH:MM
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})', header)
                    if date_match:
                        date_time_str = date_match.group(1)
                        # Извлекаем дату и время из заголовка
                        header_without_date = re.sub(r'(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})', '', header).strip()
                        
                        # Парсим дату и время
                        dt = datetime.strptime(date_time_str, "%d.%m.%Y %H:%M")
                        current_date_time = dt
                        
                        # Всё что осталось - название семьи
                        current_family_name = header_without_date
                    else:
                        # Даты нет, всё что после "Семья" - название
                        current_family_name = header
                    
                    # Проверяем результат в заголовке
                    if "win" in line.lower() or "победа" in line.lower():
                        current_result = "win"
                    elif "lose" in line.lower() or "поражение" in line.lower():
                        current_result = "lose"
                    
                except Exception as e:
                    errors.append(f"❌ Строка {line_num}: Ошибка парсинга заголовка - {str(e)}")
                    current_family_name = "Противник"
            
            elif current_family_name or current_capt_players:
                # Это строка с данными игрока
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        user_id = int(parts[0])
                        damage = int(parts[1])
                        kills = int(parts[2])
                        
                        # Проверяем, есть ли уже такой игрок в текущем капте
                        if any(p["user_id"] == user_id for p in current_capt_players):
                            errors.append(f"⚠️ Строка {line_num}: Игрок {user_id} уже в капте")
                            continue
                        
                        # Ищем игрока на сервере
                        try:
                            member = await inter.guild.fetch_member(user_id)
                            user_name = member.display_name
                        except:
                            user_name = f"Игрок {user_id}"
                        
                        current_capt_players.append({
                            "user_id": user_id,
                            "user_name": user_name,
                            "damage": damage,
                            "kills": kills
                        })
                        
                    except Exception as e:
                        errors.append(f"❌ Строка {line_num}: Ошибка обработки игрока - {str(e)}")
                else:
                    errors.append(f"❌ Строка {line_num}: Неверный формат данных игрока")
        
        # Сохраняем последний капт
        save_current_capt()
        
        # Сохраняем изменения в файлы
        if added_capts > 0:
            save_capts(capts)
            save_stats(st)
            
            # Запускаем автообновление
            asyncio.create_task(update_capts_list())
            asyncio.create_task(update_avg_top())
            asyncio.create_task(update_kills_top())
            
            await log_action(
                inter.guild, inter.user,
                "📁 Загрузка каптов",
                f"Загружено каптов: {added_capts}\nОшибок: {len(errors)}"
            )
        
        # Формируем ответ
        if added_capts == 0:
            msg = "❌ Не удалось загрузить ни одного капта"
            if errors:
                msg += f"\n\nОшибки:\n" + "\n".join(errors[:5])
        else:
            msg = f"✅ Загружено каптов: **{added_capts}**"
            if errors:
                msg += f"\n\n⚠️ Ошибки ({len(errors)}):\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... и ещё {len(errors) - 5} ошибок"
        
        if defer_used:
            await inter.followup.send(msg, ephemeral=True)
        else:
            await inter.response.send_message(msg, ephemeral=True)
        
    except Exception as e:
        print(f"❌ Ошибка в upload_capts: {e}")
        try:
            if defer_used:
                await inter.followup.send(f"❌ Ошибка загрузки: {str(e)}", ephemeral=True)
            else:
                await inter.response.send_message(f"❌ Ошибка загрузки: {str(e)}", ephemeral=True)
        except:
            pass

@tree.command(name="удалить_капт", description="🗑️ Удалить капт", guild=discord.Object(GUILD_ID))
@app_commands.describe(номер="Номер капта")
async def delete_capt(inter: discord.Interaction, номер: int):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    capts = load_capts()
    if номер < 1 or номер > len(capts):
        return await inter.response.send_message("❌ Капт не найден", ephemeral=True)
    
    removed_capt = capts.pop(-номер)
    
    st = load_stats()
    for player in removed_capt["players"]:
        uid = str(player["user_id"])
        if uid in st:
            st[uid]["damage"] -= player["damage"]
            st[uid]["kills"] -= player["kills"]
            st[uid]["games"] -= 1
            if st[uid]["games"] <= 0:
                del st[uid]
    
    save_stats(st)
    save_capts(capts)
    
    asyncio.create_task(update_capts_list())
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    
    await log_action(
        inter.guild, inter.user,
        "🗑️ Капт удалён",
        f"Против: **{removed_capt['vs']}**"
    )
    
    await inter.response.send_message(
        f"✅ Капт против **{removed_capt['vs']}** удалён",
        ephemeral=True
    )

@tree.command(name="сбросить_статистику", description="🔄 Сбросить всю статистику", guild=discord.Object(GUILD_ID))
async def reset_stats(inter: discord.Interaction):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    capts = load_capts()
    stats_count = len(load_stats())
    
    save_stats({})
    save_capts([])
    
    asyncio.create_task(update_capts_list())
    asyncio.create_task(update_avg_top())
    asyncio.create_task(update_kills_top())
    
    await log_action(
        inter.guild, inter.user,
        "🔄 Сброс статистики",
        f"Удалено каптов: {len(capts)}\nУдалено записей: {stats_count}"
    )
    
    await inter.response.send_message(
        f"✅ Статистика сброшена\n"
        f"Удалено каптов: **{len(capts)}**\n"
        f"Удалено записей: **{stats_count}**",
        ephemeral=True
    )

@tree.command(name="список_каптов", description="📜 История каптов", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def list_capts(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        view = CaptsListView(inter.guild, period)
        embed = await view.create_embed()
        
        if defer_used:
            await inter.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, view=view, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в list_capts: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="топ_средний", description="🏆 Топ по среднему урону", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_avg(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            capts = load_capts()
            period_text = "за всё время"
        
        st = calculate_stats(capts)
        filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
        
        if not filtered:
            if defer_used:
                await inter.followup.send("📭 Нет игроков с 3+ играми", ephemeral=True)
            else:
                await inter.response.send_message("📭 Нет игроков с 3+ играми", ephemeral=True)
            return

        users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]
        
        embed = discord.Embed(
            title=f"🏆 ТОП-10 СРЕДНЕГО УРОНА",
            description=f"*Статистика {period_text}*",
            color=0x9b59b6,
            timestamp=now()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            avg = data["damage"] // data["games"]
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            desc += f"```Средний урон: {avg:,}\nИгр:         {data['games']}\nВсего урона: {data['damage']:,}```\n"
        
        embed.description = f"*Статистика {period_text}*\n\n" + desc
        embed.set_footer(text="Минимум 3 игры для участия")
        
        if defer_used:
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в top_avg: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="топ_киллы", description="☠️ Топ по киллам", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def top_kills(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            capts = load_capts()
            period_text = "за всё время"
        
        st = calculate_stats(capts)
        
        if not st:
            if defer_used:
                await inter.followup.send("📭 Статистика пуста", ephemeral=True)
            else:
                await inter.response.send_message("📭 Статистика пуста", ephemeral=True)
            return

        users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]

        embed = discord.Embed(
            title=f"☠️ ТОП-10 ПО КИЛЛАМ",
            description=f"*Статистика {period_text}*",
            color=0xe74c3c,
            timestamp=now()
        )
        
        desc = ""
        for i, (uid, data) in enumerate(users, 1):
            try:
                member = await inter.guild.fetch_member(int(uid))
                name = member.display_name
            except:
                name = f"Игрок {uid}"
            
            if i <= 3:
                desc += f"{medal(i)} **{name}**\n"
            else:
                desc += f"`{i}.` **{name}**\n"
            
            desc += f"```Киллов:      {data['kills']}\nИгр:         {data['games']}\nСредний урон: {data['damage']//data['games']:,}```\n"
        
        embed.description = f"*Статистика {period_text}*\n\n" + desc
        
        if defer_used:
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в top_kills: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="моя_статистика", description="📊 Ваша статистика", guild=discord.Object(GUILD_ID))
@app_commands.describe(period="Период")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За неделю", value="week"),
    app_commands.Choice(name="За месяц", value="month")
])
async def my_stats(inter: discord.Interaction, period: str = "all"):
    if not has_role(inter.user, VIEW_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        await inter.response.defer(ephemeral=True)
        defer_used = True
    except:
        defer_used = False
    
    try:
        if period == "week":
            capts = get_capts_in_period(7)
            period_text = "за неделю"
        elif period == "month":
            capts = get_capts_in_period(30)
            period_text = "за месяц"
        else:
            capts = load_capts()
            period_text = "за всё время"
        
        st = calculate_stats(capts)
        uid = str(inter.user.id)
        
        if uid not in st:
            if defer_used:
                await inter.followup.send(f"📭 Нет статистики {period_text}", ephemeral=True)
            else:
                await inter.response.send_message(f"📭 Нет статистики {period_text}", ephemeral=True)
            return
        
        data = st[uid]
        avg = data["damage"] // data["games"] if data["games"] > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Статистика {inter.user.display_name}",
            description=f"*{period_text.capitalize()}*",
            color=0x3498db,
            timestamp=now()
        )
        embed.set_thumbnail(url=inter.user.display_avatar.url)
        
        embed.add_field(
            name="📈 Основная статистика",
            value=f"```Игр:         {data['games']}\nСредний урон: {avg:,}\nВсего урона:  {data['damage']:,}\nВсего киллов: {data['kills']}```",
            inline=False
        )
        
        avg_users = sorted(st.items(), key=lambda x: x[1]["damage"]/x[1]["games"] if x[1]["games"] >= 3 else 0, reverse=True)
        kills_users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)
        
        avg_pos = next((i+1 for i, (u, _) in enumerate(avg_users) if u == uid and data["games"] >= 3), None)
        kills_pos = next((i+1 for i, (u, _) in enumerate(kills_users) if u == uid), None)
        
        positions = ""
        if avg_pos:
            positions += f"🏅 Место по среднему: **#{avg_pos}**\n"
        if kills_pos:
            positions += f"☠️ Место по киллам: **#{kills_pos}**"
        
        if positions:
            embed.add_field(name="🎯 Позиции в рейтинге", value=positions, inline=False)
        
        if defer_used:
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        print(f"❌ Ошибка в my_stats: {e}")
        try:
            if defer_used:
                await inter.followup.send("❌ Произошла ошибка при выполнении команды", ephemeral=True)
            else:
                await inter.response.send_message("❌ Произошла ошибка при выполнении команды", ephemeral=True)
        except:
            pass

@tree.command(name="справка", description="📚 Помощь по командам", guild=discord.Object(GUILD_ID))
async def help_cmd(inter: discord.Interaction):
    is_admin = has_role(inter.user, ADMIN_ROLES)
    
    embed = discord.Embed(
        title="📚 СПРАВКА ПО КОМАНДАМ",
        description="*Статистика Семьи YAK*",
        color=0xe74c3c,
        timestamp=now()
    )
    
    embed.add_field(
        name="👥 Для всех",
        value=(
            "`/список_каптов` - История каптов\n"
            "`/топ_средний` - Топ по урону\n"
            "`/топ_киллы` - Топ по киллам\n"
            "`/моя_статистика` - Ваша стата\n"
            "`/справка` - Эта справка"
        ),
        inline=False
    )
    
    if is_admin:
        embed.add_field(
            name="👑 Для админов",
            value=(
                "`/добавить_капт` - Создать капт\n"
                "`/добавить_игрока` - Добавить игрока\n"
                "`/загрузить_игроков` - Массовое добавление\n"
                "`/загрузить_каптов` - Загрузить из файла\n"
                "`/удалить_капт` - Удалить капт\n"
                "`/сбросить_статистику` - Сброс всего\n"
                "`/sync` - Синхронизация команд"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📝 Форматы загрузки",
            value=(
                "**Текст (игроки):**\n"
                "```ID урон киллы```\n"
                "**Файл (капты):**\n"
                "```ID урон киллы win\n\nID урон киллы lose```"
            ),
            inline=False
        )
    
    embed.set_footer(text="YAK Clan Stats Bot v3.1")
    
    await inter.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="sync", description="🔄 Синхронизировать команды", guild=discord.Object(GUILD_ID))
async def sync_commands(inter: discord.Interaction):
    if not has_role(inter.user, ADMIN_ROLES):
        return await inter.response.send_message("❌ Нет доступа", ephemeral=True)
    
    try:
        synced = await tree.sync(guild=discord.Object(GUILD_ID))
        
        embed = discord.Embed(
            title="✅ Команды синхронизированы",
            description=f"Синхронизировано команд: **{len(synced)}**",
            color=0x2ecc71,
            timestamp=now()
        )
        
        commands_list = "\n".join([f"• `/{cmd.name}`" for cmd in synced[:15]])
        if len(synced) > 15:
            commands_list += f"\n*...и ещё {len(synced) - 15}*"
        
        embed.add_field(
            name="📋 Синхронизированные команды",
            value=commands_list,
            inline=False
        )
        
        embed.set_footer(text="Команды обновлены")
        
        await log_action(
            inter.guild, inter.user,
            "🔄 Синхронизация команд",
            f"Синхронизировано: {len(synced)} команд"
        )
        
        await inter.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Ошибка синхронизации",
            description=f"```{str(e)}```",
            color=0xe74c3c,
            timestamp=now()
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

# ==================== АВТООБНОВЛЕНИЕ ====================
async def update_avg_top():
    channel = client.get_channel(STATS_AVG_CHANNEL_ID)
    if not channel:
        return

    st = load_stats()
    filtered = {uid: d for uid, d in st.items() if d["games"] >= 3}
    if not filtered:
        return

    users = sorted(filtered.items(), key=lambda x: x[1]["damage"]/x[1]["games"], reverse=True)[:10]

    embed = discord.Embed(
        title="🏆 ТОП-10 СРЕДНЕГО УРОНА",
        color=0x9b59b6,
        timestamp=now()
    )

    desc = ""
    for i, (uid, data) in enumerate(users, 1):
        try:
            member = await channel.guild.fetch_member(int(uid))
            name = member.display_name
        except:
            name = f"Игрок {uid}"

        avg = data["damage"] // data["games"]
        leader_avg = users[0][1]["damage"] // users[0][1]["games"]
        percent = (avg / leader_avg * 100) if leader_avg > 0 else 0
        bar = progress_bar(percent)

        desc += f"{medal(i)} **{i}. {name}**\n{bar} **{avg:,}** урона ({data['games']} игр)\n\n"

    embed.description = desc
    embed.set_footer(text="Обновляется каждый час • Минимум 3 игры")

    async for msg in channel.history(limit=50):
        if msg.author.id == client.user.id and msg.embeds:
            if "ТОП-10 СРЕДНЕГО УРОНА" in msg.embeds[0].title:
                try:
                    await msg.edit(embed=embed)
                    return
                except:
                    pass

    try:
        await channel.send(embed=embed)
    except:
        pass

async def update_kills_top():
    channel = client.get_channel(STATS_KILLS_CHANNEL_ID)
    if not channel:
        return

    st = load_stats()
    if not st:
        return

    users = sorted(st.items(), key=lambda x: x[1]["kills"], reverse=True)[:10]

    embed = discord.Embed(
        title="☠️ ТОП-10 ПО КИЛЛАМ",
        color=0xe74c3c,
        timestamp=now()
    )

    desc = ""
    for i, (uid, data) in enumerate(users, 1):
        try:
            member = await channel.guild.fetch_member(int(uid))
            name = member.display_name
        except:
            name = f"Игрок {uid}"

        leader_kills = users[0][1]["kills"]
        percent = (data["kills"] / leader_kills * 100) if leader_kills > 0 else 0
        bar = progress_bar(percent)

        desc += f"{medal(i)} **{i}. {name}**\n{bar} **{data['kills']}** киллов ({data['games']} игр)\n\n"

    embed.description = desc
    embed.set_footer(text="Обновляется каждый час")

    async for msg in channel.history(limit=50):
        if msg.author.id == client.user.id and msg.embeds:
            if "ТОП-10 ПО КИЛЛАМ" in msg.embeds[0].title:
                try:
                    await msg.edit(embed=embed)
                    return
                except:
                    pass

    try:
        await channel.send(embed=embed)
    except:
        pass

async def update_capts_list():
    channel = client.get_channel(CAPTS_LIST_CHANNEL_ID)
    if not channel:
        return

    view = CaptsListView(channel.guild, "all")
    embed = await view.create_embed()

    async for msg in channel.history(limit=50):
        if msg.author.id == client.user.id and msg.embeds:
            if "История каптов" in msg.embeds[0].title:
                try:
                    await msg.edit(embed=embed, view=view)
                    print("✅ Список каптов обновлён")
                    return
                except:
                    pass

    try:
        await channel.send(embed=embed, view=view)
        print("✅ Список каптов отправлен")
    except:
        pass

@tasks.loop(hours=1)
async def auto_update():
    await update_avg_top()
    await update_kills_top()
    await update_capts_list()
    print(f"✅ Автообновление выполнено: {datetime.now().strftime('%H:%M:%S')}")

# ==================== СОБЫТИЯ ====================
@client.event
async def on_ready():
    print(f"✅ Бот запущен: {client.user}")
    
    try:
        await tree.sync(guild=discord.Object(GUILD_ID))
        print("✅ Команды синхронизированы")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    if not auto_update.is_running():
        auto_update.start()
        print("✅ Автообновление запущено")

@client.event
async def on_member_remove(member: discord.Member):
    st = load_stats()
    uid = str(member.id)
    
    if uid in st:
        del st[uid]
        save_stats(st)
        
        await log_action(
            member.guild, client.user,
            "👋 Игрок покинул сервер",
            f"{member.mention} ({member.display_name})\nСтатистика удалена"
        )
        
        asyncio.create_task(update_avg_top())
        asyncio.create_task(update_kills_top())

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    for db in [DB_STATS, DB_CAPTS]:
        if not os.path.exists(db):
            with open(db, "w", encoding="utf-8") as f:
                json.dump({} if db == DB_STATS else [], f)
            print(f"📁 Создан {db}")

    client.run(TOKEN)
