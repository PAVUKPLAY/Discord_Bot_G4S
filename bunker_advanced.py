import discord
from discord import ui, app_commands
import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from config import BUNKER_CATEGORY_ID

logger = logging.getLogger(__name__)

# ==================== КОЛОДЫ КАРТ ====================

PROFESSIONS = [
    "Археолог", "Автомеханик", "Адвокат", "Вирусолог", "Браконьер", "Военный",
    "Видеоинженер", "Биолог", "Гомеопат", "Детектив", "Грабитель", "Дизайнер",
    "Коуч", "Журналист", "Историк", "Лесник", "Домохозяйка", "Знахарь",
    "Маркетолог", "Лётчик-инженер", "Медсестра", "Повар", "Папарацци",
    "Переводчик", "Пожарный", "Модель", "Писатель", "Продавец", "Полицейский",
    "Программист", "Порноактёр", "Стоматолог", "Сексолог", "Спецагент",
    "Робототехник", "Психолог", "Разнорабочий", "Тату-мастер", "Строитель",
    "Судья", "Хакер", "Физик", "Философ", "Хирург", "Фермер", "Химик",
    "Экскурсовод", "Эколог", "Экстрасенс", "Этнограф", "Электрик", "Проститутка"
]

BIOLOGY = [
    "Женщина 19 лет Гомосексуальна", "Андроид", "Женщина 18 лет",
    "Женщина 21 год Бисексуальна", "Женщина 22 года Бисексуальна",
    "Женщина 24 года", "Женщина 31 год", "Женщина 27 лет",
    "Женщина 30 лет", "Женщина 34 года", "Женщина 25 лет Гомосексуальна",
    "Женщина 33 года Гомосексуальна", "Женщина 65 лет", "Женщина 36 лет",
    "Женщина 99 лет", "Мужчина 27 лет Гомосексуален",
    "Мужчина 24 года Бисексуален", "Мужчина 26 лет",
    "Мужчина 23 года Гомосексуален", "Котогендер", "Гном 152 года",
    "Мужчина 18 лет", "Мужчина 32 года Гомосексуален",
    "Мужчина 29 лет", "Мужчина 30 лет", "Мужчина 42 года Гомосексуален",
    "Мужчина 35 лет", "Мужчина 39 лет", "Мужчина 101 год",
    "Мужчина 33 года", "Мужчина 75 лет", "Гуманоид"
]

HEALTH = [
    "Гигантизм отдельных частей тела", "Бесплодие", "Галлюцинации", "Депрессия",
    "Алкоголизм", "Глухой", "Заика", "Зависимость от наркотиков",
    "Игровая зависимость", "Кофейная зависимость", "Карлик", "Клептомания",
    "Лунатизм", "Идеально здоров", "Мания преследования", "Мигрень",
    "Не обследовался", "Нет ноги", "Понос", "Повышенная волосатость",
    "Потеря обоняния", "Раздвоение личности", "Нет руки",
    "Сексуальная озабоченность", "Слепой", "Склероз", "Суицидальные мысли",
    "Хвост", "Тремор рук", "Фригидность/импотенция"
]

HOBBIES = [
    "Холодное оружие", "Черная магия", "Флудить в чатах", "Грибы и гомеопатия",
    "Боевые искусства", "Дачник", "Вуайнеризм", "Алхимия", "Гидропоника",
    "ЗОЖ", "Кино и сериалы", "Компьютерные игры", "Нетворкинг",
    "Любительская радиосвязь", "Настольные игры", "Медитация", "Краеведение",
    "Массаж и акупунктура", "Паркур", "Нетрадиционная медицина",
    "Охота и рыбалка", "Свинг-вечеринки", "Пиротехника", "Разговоры по душам",
    "Современное искусство", "Пивоварение", "Робототехника", "Уфология и мистика",
    "Спортивные танцы", "Стриптиз"
]

LUGGAGE = [
    "Звуковая отвертка", "Гитара", "Дефибрилятор", "Инкубатор с набором яиц",
    "3 слитка золота", "Антибиотики и обезболивающее", "Инструменты электрика",
    "Капканы и набор ядов", "Книга Айзека Азимова", "Мешок картошки",
    "Кукла вуду", "Мешок зерна", "Миллион долларов", "Компас и карта окрестностей",
    "Лук и стрелы", "Набор отмычек", "Надувная кукла", "Настольные игры",
    "Саженцы фруктовых деревьев", "Пистолет", "Прибор ночного видения",
    "Переносная электростанция", "Ножи для метания", "Ноутбук и платы ARDUINO",
    "Столярные инструменты", "Снайперская винтовка", "Спиритическая доска",
    "Чемоданчик фельдшера", "Шапочка из фольги", "Энциклопедия грибника"
]

FACTS = [
    "Аблютофоб - боится умываться", "Андрофобия - боится мужчин",
    "Вернулся с СВО", "Безотказный", "Бродяжничал 2 года",
    "Вырос в семье лесника", "Видел инопланетян", "Владеет 5 языками",
    "Гонофобия - боится женщин", "Взломал базу данных ЦРУ",
    "Врёт и преувеличивает", "Держал дома 40 кошек", "Гипнотическая улыбка",
    "Грязно ругается", "Знает наизусть все стихи Пушкина",
    "Знает Азбуку Морзе", "Знает лично президента", "Запустил IT-стартап",
    "Душа компании", "Зануда", "Истеричный", "Извращенец", "Маньяк-убийца",
    "Нытик", "Не пускают в казино", "Нобелевский лауреат по биоинженерии",
    "Остался в живых на необитаемом острове", "Наркодилер",
    "Обладатель уникального сопрано", "Писается по ночам",
    "Отчислен из клуба 'Навыки выживания'", "Пишит с ашипками",
    "Прошёл 2-недельные курсы психолога", "Подходит сзади и дышит",
    "Понимает язык животных", "Психопат", "Победитель параолимпийских игр",
    "Продал почку", "Сделает алкоголь из чего угодно",
    "Работал в экскорт-услугах", "Разговаривает с духами",
    "Только из очага эпидемии", "Сплетник", "Строил подобные бункеры",
    "Тормоз", "Состоял в секте", "Телепат", "Эторофоб - боится секса",
    "Храпит", "Читал все книги Лавкрафта"
]

SPECIAL_CONDITIONS = [
    "Тишина – в этом раунде никто не может говорить (только голосование).",
    "Слепота – каждый игрок видит только профессии остальных, но не имена.",
    "Голосование вслепую – голоса отдаются случайно.",
    "Двойной раунд – исключаются сразу два игрока с наибольшим числом голосов.",
    "Амнистия – исключённый в прошлом раунде возвращается.",
    "Обмен – все игроки меняются багажом по кругу.",
    "Суд – один игрок выбирается судьёй и его голос считается за 3.",
    "Анархия – голосование отменяется, все остаются (переход к следующему раунду).",
    "Эвакуация – двое игроков с наименьшим числом голосов покидают игру.",
    "Карантин – игроки с болезнями не могут голосовать в этом раунде.",
    "Шантаж – вы можете потребовать у любого игрока отдать вам его багаж.",
    "Предатель – вы можете один раз переголосовать, если недовольны результатом.",
    "Сабботаж – вы можете испортить багаж одного игрока (он теряет его навсегда).",
    "Шпионаж – вы узнаёте, за кого голосовал каждый игрок в этом раунде.",
    "Торговец – вы можете обменять свой багаж на защиту от исключения.",
    "Провокатор – вы можете заставить двух игроков поменяться голосами.",
    "Инфекция – вы передаёте свою болезнь другому игроку (меняетесь здоровьем).",
    "Манипулятор – вы можете выбрать, кто будет исключён, если ничья.",
    "Спасатель – вы можете воскресить одного выбывшего игрока (один раз).",
    "Террорист – вы можете отменить голосование и исключить любого игрока по своему выбору."
]

# ==================== КЛАСС ИГРОКА ====================

class AdvancedPlayer:
    def __init__(self, member: discord.Member):
        self.member = member
        self.id = member.id
        self.name = member.display_name

        self.profession = random.choice(PROFESSIONS)
        self.biology = random.choice(BIOLOGY)
        self.health = random.choice(HEALTH)
        self.hobby = random.choice(HOBBIES)
        self.luggage = random.choice(LUGGAGE)
        self.fact = random.choice(FACTS)
        self.special = random.choice(SPECIAL_CONDITIONS)

        self.cards_open = {k: False for k in ["profession", "biology", "health", "hobby", "luggage", "fact", "special"]}
        self.is_exiled = False
        self.vote_weight = 1
        self.protected = False

    def open_card(self, card_type: str) -> bool:
        if card_type in self.cards_open and not self.cards_open[card_type]:
            self.cards_open[card_type] = True
            return True
        return False

    def get_open_list(self) -> List[str]:
        return [f"{t.capitalize()}: {getattr(self, t)}" for t in self.cards_open if self.cards_open[t]]

    def get_private_cards(self) -> Dict[str, str]:
        return {
            "profession": self.profession,
            "biology": self.biology,
            "health": self.health,
            "hobby": self.hobby,
            "luggage": self.luggage,
            "fact": self.fact,
            "special": self.special
        }

# ==================== КЛАСС ИГРЫ ====================

class AdvancedGame:
    def __init__(self, guild: discord.Guild, channel: discord.TextChannel, max_players: int = 6):
        self.guild = guild
        self.start_channel = channel
        self.max_players = max_players
        self.players: Dict[int, AdvancedPlayer] = {}
        self.round = 0
        self.status = "waiting"  # waiting, setup, playing, finished

        self.category = None
        self.text_channel = None
        self.voice_channel = None
        self.spectator_role = None

        self.current_phase = None
        self.reveal_order: List[int] = []
        self.reveal_index = 0
        self.reveal_timer_task = None

        self.votes: Dict[int, int] = {}
        self.voters: Set[int] = set()
        self.exiled: List[int] = []

        self.board_message = None
        self.private_messages: Dict[int, discord.Message] = {}

    # ========== УПРАВЛЕНИЕ КАНАЛАМИ ==========
    async def create_channels(self):
        if BUNKER_CATEGORY_ID:
            category = self.guild.get_channel(BUNKER_CATEGORY_ID)
        else:
            category = await self.guild.create_category("🎮 Игра Бункер")
        self.category = category

        self.text_channel = await self.guild.create_text_channel(
            "🛡️-табло-бункера",
            category=category,
            topic="Здесь будет отображаться текущее состояние игры"
        )

        self.voice_channel = await self.guild.create_voice_channel(
            "🎙️-вход-в-бункер",
            category=category,
            user_limit=self.max_players + 2
        )

        self.spectator_role = await self.guild.create_role(
            name="Зритель Бункера",
            permissions=discord.Permissions(connect=True, speak=False)
        )

        await self.voice_channel.set_permissions(self.guild.default_role, connect=True, speak=False)
        await self.voice_channel.set_permissions(self.spectator_role, connect=True, speak=False)

    # ========== УПРАВЛЕНИЕ ИГРОКАМИ ==========
    async def add_player(self, member: discord.Member) -> bool:
        if member.id in self.players or len(self.players) >= self.max_players:
            return False
        self.players[member.id] = AdvancedPlayer(member)
        return True

    # ========== ЗАПУСК ИГРЫ ==========
    async def start_game(self):
        self.status = "playing"
        self.round = 1

        for p in self.players.values():
            embed = self._create_card_embed(p, "profession")
            view = CardNavigationView(p.id, self)
            msg = await p.member.send(embed=embed, view=view)
            self.private_messages[p.id] = msg

        await self.start_channel.send("🕒 У вас есть **2 минуты**, чтобы изучить свои карты в личных сообщениях. Используйте кнопки 'Вперёд' и 'Назад'.")
        await asyncio.sleep(120)
        await self.start_channel.send("⏰ Время вышло! Начинаем игру.")

        for msg in self.private_messages.values():
            await msg.edit(view=None)

        await self.start_round()

    def _create_card_embed(self, player: AdvancedPlayer, current_card: str) -> discord.Embed:
        cards = player.get_private_cards()
        desc = cards.get(current_card, "Неизвестно")
        embed = discord.Embed(
            title=f"🧑‍🚀 Ваши карты – {current_card.capitalize()}",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Карта {current_card} • Используйте кнопки для навигации")
        return embed

    # ========== НАВИГАЦИЯ ПО КАРТАМ ==========
    class CardNavigationView(ui.View):
        def __init__(self, player_id: int, game: 'AdvancedGame'):
            super().__init__(timeout=120)
            self.player_id = player_id
            self.game = game
            self.card_list = ["profession", "biology", "health", "hobby", "luggage", "fact", "special"]
            self.current_index = 0

        @ui.button(label="◀ Назад", style=discord.ButtonStyle.secondary, custom_id="card_prev")
        async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.player_id:
                await interaction.response.send_message("Это не ваши карты!", ephemeral=True)
                return
            self.current_index = (self.current_index - 1) % len(self.card_list)
            current = self.card_list[self.current_index]
            embed = self.game._create_card_embed(self.game.players[self.player_id], current)
            await interaction.response.edit_message(embed=embed, view=self)

        @ui.button(label="Вперёд ▶", style=discord.ButtonStyle.primary, custom_id="card_next")
        async def next_button(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.player_id:
                await interaction.response.send_message("Это не ваши карты!", ephemeral=True)
                return
            self.current_index = (self.current_index + 1) % len(self.card_list)
            current = self.card_list[self.current_index]
            embed = self.game._create_card_embed(self.game.players[self.player_id], current)
            await interaction.response.edit_message(embed=embed, view=self)

    # ========== ОСНОВНОЙ ИГРОВОЙ ЦИКЛ ==========
    async def start_round(self):
        if self.status != "playing" or self.round > 5:
            await self.finish_game()
            return

        alive = [p for p in self.players.values() if p.id not in self.exiled]
        self.reveal_order = [p.id for p in alive]
        self.reveal_index = 0

        await self.text_channel.send(f"🏚️ **Раунд {self.round}** начинается!")
        await self.update_board()
        await self.start_reveal_phase()

    async def start_reveal_phase(self):
        if self.reveal_index >= len(self.reveal_order):
            await self.after_reveal()
            return

        player_id = self.reveal_order[self.reveal_index]
        player = self.players[player_id]

        closed = [k for k, v in player.cards_open.items() if not v and k != "special"]
        if closed:
            chosen = random.choice(closed)
        else:
            chosen = "profession"

        player.open_card(chosen)
        await self.text_channel.send(f"📖 **{player.name}** раскрыл(а) **{chosen.capitalize()}**: {getattr(player, chosen)}")
        await self.update_board()

        self.reveal_index += 1
        await asyncio.sleep(2)
        await self.start_reveal_phase()

    async def after_reveal(self):
        if self.round >= 2 and self.round <= 5:
            await self.start_voting()
        else:
            self.round += 1
            await self.start_round()

    async def start_voting(self):
        alive = [p for p in self.players.values() if p.id not in self.exiled]
        if len(alive) <= 1:
            await self.after_voting()
            return

        embed = discord.Embed(
            title=f"🗳️ Голосование – Раунд {self.round}",
            description="Выберите игрока, которого хотите исключить.",
            color=discord.Color.blue()
        )
        view = VotingView(self, alive, self.text_channel)
        await self.text_channel.send(embed=embed, view=view)

    async def after_voting(self):
        if self.votes:
            max_votes = max(self.votes.values())
            candidates = [uid for uid, v in self.votes.items() if v == max_votes]
            if len(candidates) == 1:
                exiled_id = candidates[0]
                self.exiled.append(exiled_id)
                await self.text_channel.send(f"❌ {self.players[exiled_id].name} исключён!")
                for k in self.players[exiled_id].cards_open:
                    self.players[exiled_id].cards_open[k] = True
                await self.update_board()
            else:
                await self.text_channel.send("⚖️ Ничья! Никто не исключается.")
        else:
            await self.text_channel.send("❌ Никто не проголосовал.")

        self.round += 1
        await self.start_round()

    async def update_board(self):
        embed = discord.Embed(
            title="📋 Табло Бункера",
            description="Открытые карты игроков",
            color=discord.Color.blue()
        )
        for p in self.players.values():
            if p.id in self.exiled:
                continue
            open_cards = p.get_open_list()
            text = "\n".join(open_cards) if open_cards else "Ничего не открыто"
            embed.add_field(name=p.name, value=text, inline=False)

        if self.board_message:
            await self.board_message.edit(embed=embed)
        else:
            self.board_message = await self.text_channel.send(embed=embed)

    async def finish_game(self):
        winners = [p for p in self.players.values() if p.id not in self.exiled]
        win_mentions = " ".join([p.member.mention for p in winners])
        embed = discord.Embed(
            title="🏆 Игра завершена!",
            description=f"Победители: {win_mentions}\nВсего выжило: {len(winners)} человек.",
            color=discord.Color.gold()
        )
        await self.start_channel.send(embed=embed)
        self.status = "finished"
        await self.voice_channel.delete()
        await self.spectator_role.delete()

# ==================== КНОПКИ ГОЛОСОВАНИЯ ====================

class VotingView(ui.View):
    def __init__(self, game: AdvancedGame, alive_players: List[AdvancedPlayer], channel):
        super().__init__(timeout=60)
        self.game = game
        self.alive = alive_players
        self.channel = channel
        for p in alive_players:
            btn = ui.Button(label=p.name, style=discord.ButtonStyle.primary, custom_id=f"vote_{p.id}")
            btn.callback = self.make_callback(p.id)
            self.add_item(btn)

    def make_callback(self, target_id):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id == target_id:
                await interaction.response.send_message("❌ Нельзя голосовать за себя.", ephemeral=True)
                return
            if interaction.user.id in self.game.voters:
                await interaction.response.send_message("❌ Вы уже проголосовали.", ephemeral=True)
                return
            self.game.voters.add(interaction.user.id)
            self.game.votes[target_id] = self.game.votes.get(target_id, 0) + 1
            await interaction.response.send_message(f"✅ Вы проголосовали за {self.game.players[target_id].name}.", ephemeral=True)
            alive = self.game.get_alive_players()
            if len(self.game.voters) >= len(alive):
                self.stop()
                await self.game.after_voting()
        return callback

    async def on_timeout(self):
        await self.game.after_voting()

# ==================== КНОПКИ ЛОББИ ====================

class LobbyView(ui.View):
    def __init__(self, game: AdvancedGame):
        super().__init__(timeout=None)
        self.game = game

    @ui.button(label="🎙️ Присоединиться к игре", style=discord.ButtonStyle.primary, custom_id="join_game")
    async def join_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id in self.game.players:
            await interaction.response.send_message("Вы уже в игре!", ephemeral=True)
            return
        success = await self.game.add_player(interaction.user)
        if not success:
            await interaction.response.send_message("❌ Места закончились или вы уже в игре.", ephemeral=True)
            return
        await interaction.user.move_to(self.game.voice_channel)
        await interaction.response.send_message(f"✅ {interaction.user.display_name} присоединился!", ephemeral=True)

    @ui.button(label="🚀 Начать игру", style=discord.ButtonStyle.success, custom_id="start_game")
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        if len(self.game.players) < 2:
            await interaction.response.send_message("❌ Нужно минимум 2 игрока.", ephemeral=True)
            return
        await interaction.response.send_message("🔄 Игра начинается...")
        await self.game.start_game()
