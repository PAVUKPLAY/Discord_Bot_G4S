import discord
from discord import ui, app_commands
import random
import asyncio
import logging
from typing import Dict, List, Optional, Set
from config import BUNKER_CATEGORY_ID, BUNKER_LOBBY_CHANNEL_ID
from toggle_manager import get_lobby_message_id, set_lobby_message_id

logger = logging.getLogger(__name__)

# ========== КОЛОДЫ КАРТ ==========
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
    "Взял с собой", "Будь другом", "Включил свет", "Громкий голос",
    "Давайте начистоту (Багаж)", "Давайте начистоту (Биология)",
    "Давайте начистоту (Хобби)", "Давайте начистоту (Здоровье)",
    "Давайте начистоту (Факты)", "Защити игрока слева", "Защити игрока справа",
    "Защити смелого", "Защити младшего", "Защити старшего",
    "Диверсия", "Дискредитация", "Обмен карт (Багаж)", "Обмен карт (Биология)",
    "Обмен карт (Хобби)", "Обмен карт (Здоровье)", "Обмен карт (Факты)",
    "Молчание", "Мне нужнее", "Компромат", "Тайная угроза",
    "Просроченные таблетки", "Прямой вопрос", "Хорошие таблетки",
    "План Б", "Фейковый диплом"
]

BUNKER_CARDS = [
    "ВИДЕО СО СПУТНИКА: На стены проецируется расслабляющее видео со спутника.",
    "R2D2: Робот-психолог. Молча слушает, иногда пищит.",
    "АПТЕЧКИ: У входа есть аптечки, резиновые перчатки, маски, лекарства.",
    "ЖЕРТВЕННИК: Спальных мест ровно по числу людей. Одно из них станет жертвенным алтарем.",
    "ГРЕЧКА: Из запасов еды только гречка. Зато очень много.",
    "ДИНАМО-МАШИНА: Резервный электрогенератор с велоприводом и куча металлолома.",
    "ГОЛОСОВОЕ УПРАВЛЕНИЕ: Бункер управляется ИИ с голосовым интерфейсом.",
    "ВМЕСТЕ НА 10 ЛЕТ: Бункер откроется через 10 лет. В финале откройте дополнительную угрозу.",
    "ГИПНОМОДУЛЬ: Модуль гипно-телепатической коммуникации и детектор паранормальных полей.",
    "ЗАГАДОЧНЫЙ ЖУРНАЛ: Странный журнал с именами всей команды, датами и описанием.",
    "ЗАПИСИ КОНТРАБАНДИСТА: Библиотека контрабандиста. Описаны ценные предметы и маршруты.",
    "ИНСТРУКЦИЯ К МИКРОВОЛНОВКЕ: Нет бумаги для туалета! Зато есть инструкция на 7174 языках.",
    "МАСТЕРСКАЯ: Мастерская с инструментами.",
    "КОФЕ: Кофемашина и запас ароматного обжаренного зернового кофе.",
    "КРЫСЫ: Похоже, что в бункере обитают полчища крыс.",
    "КНИГА О ЕДЕ: Книга о вкусной и здоровой пище. Советы как добывать и готовить еду.",
    "КАТАКОМБЫ: Из подвала есть выход в естественный грот с подземной рекой.",
    "КЕРОСИНОВЫЕ ЛАМПЫ: Электрическое освещение работает с перебоями. Есть керосиновые лампы.",
    "МЕД. ЛАБОРАТОРИЯ: Медицинская лаборатория с операционной.",
    "МЕДИАТЕКА: Есть автономная медиатека. Подбор фильмов — в основном кинематограф.",
    "МУСОР: Дырявые матрасы и тряпки, брошенный строительный мусор, старые газеты.",
    "СИЛОВОЕ ПОЛЕ: Переносной генератор защитного силового поля.",
    "ПОДВАЛ: Бункер строили заключенные. Нашли инструменты и оружие охранников.",
    "РАДИО: По внутреннему радио крутят классическую музыку и Киркорова.",
    "УКЛОН 45°: В результате тектонических сдвигов бункер наклонило на 45 градусов.",
    "НЕКРОНОМИКОН: Огромный древний фолиант на неизвестном языке с мистическими иллюстрациями.",
    "РОБОТ-ПОЛИГРАФ: Автономный робот-переводчик с функцией полиграфа (детектора лжи).",
    "ШКАФ С НАСТОЛКАМИ: Шкаф с настольными играми! Монополия и прочие развлечения.",
    "УЧЕБНИК: Учебное пособие «Как убивать зомби не жрать ваш мозг».",
    "ХИМ. ЛАБОРАТОРИЯ: Хим. лаборатория и реактивы. Можно устроить напалмовую ферму."
]

# ========== КЛАССЫ КАРТ И ИГРОКОВ ==========

class Card:
    def __init__(self, name: str, card_type: str):
        self.name = name
        self.type = card_type

class Player:
    def __init__(self, member: discord.Member):
        self.member = member
        self.id = member.id
        self.name = member.display_name
        self.profession = None
        self.biology = None
        self.health = None
        self.hobby = None
        self.luggage = None
        self.fact = None
        self.special = None
        self.cards_open = {k: False for k in ["profession", "biology", "health", "hobby", "luggage", "fact", "special"]}
        self.is_exiled = False
        self.vote_weight = 1
        self.is_spectator = False

    def open_card(self, card_type: str) -> bool:
        if card_type in self.cards_open and not self.cards_open[card_type]:
            self.cards_open[card_type] = True
            return True
        return False

    def get_open_list(self) -> List[str]:
        result = []
        if self.cards_open["profession"] and self.profession:
            result.append(f"Профессия: {self.profession.name}")
        if self.cards_open["biology"] and self.biology:
            result.append(f"Биология: {self.biology.name}")
        if self.cards_open["health"] and self.health:
            result.append(f"Здоровье: {self.health.name}")
        if self.cards_open["hobby"] and self.hobby:
            result.append(f"Хобби: {self.hobby.name}")
        if self.cards_open["luggage"] and self.luggage:
            result.append(f"Багаж: {self.luggage.name}")
        if self.cards_open["fact"] and self.fact:
            result.append(f"Факт: {self.fact.name}")
        if self.cards_open["special"] and self.special:
            result.append(f"Особое условие: {self.special.name}")
        return result

# ========== КАРТЫ ОСОБЫХ УСЛОВИЙ (РЕГИСТР) ==========

class SpecialCardEffect:
    def __init__(self, name: str, description: str, can_use_after_exile: bool = False):
        self.name = name
        self.description = description
        self.can_use_after_exile = can_use_after_exile

    async def apply(self, game: 'Game', player: Player, target: Optional[Player] = None, extra=None):
        raise NotImplementedError

SPECIAL_CARD_REGISTRY = {}

def register_special_card(cls):
    instance = cls()
    SPECIAL_CARD_REGISTRY[instance.name] = instance
    return cls

# ---------- Реализация карт ----------

@register_special_card
class VzyalSSoboi(SpecialCardEffect):
    def __init__(self):
        super().__init__("Взял с собой", "Забери любую открытую карту бункера, теперь она у изгнанных.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        await game.text_channel.send(f"🔄 {player.name} использует «Взял с собой»! Карта бункера переходит к изгнанным.")

@register_special_card
class BudDrugom(SpecialCardEffect):
    def __init__(self):
        super().__init__("Будь другом", "Выбранный игрок до конца игры не голосует против тебя.")
    async def apply(self, game, player, target=None, extra=None):
        if target:
            game.friend_protection = getattr(game, 'friend_protection', {})
            game.friend_protection[target.id] = player.id
            await game.text_channel.send(f"🤝 {player.name} и {target.name} теперь друзья! {target.name} не будет голосовать против {player.name}.")

@register_special_card
class VkluchilSvet(SpecialCardEffect):
    def __init__(self):
        super().__init__("Включил свет", "Замени любую открытую карту бункера на случайную из колоды.")
    async def apply(self, game, player, target=None, extra=None):
        await game.text_channel.send(f"💡 {player.name} включает свет! Карта бункера заменена.")

@register_special_card
class GromkiyGolos(SpecialCardEffect):
    def __init__(self):
        super().__init__("Громкий голос", "Твой голос считается за два в этом голосовании.")
    async def apply(self, game, player, target=None, extra=None):
        game.vote_weights[player.id] = 2
        await game.text_channel.send(f"🗣️ {player.name} использует «Громкий голос»! Его голос будет считаться за два.")

@register_special_card
class DavayteNachistotuBagazh(SpecialCardEffect):
    def __init__(self):
        super().__init__("Давайте начистоту (Багаж)", "Собери все открытые карты багажа у неизгнанных, перемешай и перераздай.")
    async def apply(self, game, player, target=None, extra=None):
        luggages = []
        for p in game.players.values():
            if not p.is_exiled and p.cards_open["luggage"] and p.luggage:
                luggages.append((p, p.luggage))
        if luggages:
            random.shuffle(luggages)
            for i, (p, _) in enumerate(luggages):
                p.luggage = luggages[i][1]
            await game.text_channel.send(f"🔄 {player.name} перераздал багаж!")
        else:
            await game.text_channel.send("Нет открытых карт багажа для перераздачи.")

@register_special_card
class DavayteNachistotuBiologiya(SpecialCardEffect):
    def __init__(self):
        super().__init__("Давайте начистоту (Биология)", "Собери все открытые карты биологии у неизгнанных, перемешай и перераздай.")
    async def apply(self, game, player, target=None, extra=None):
        items = []
        for p in game.players.values():
            if not p.is_exiled and p.cards_open["biology"] and p.biology:
                items.append((p, p.biology))
        if items:
            random.shuffle(items)
            for i, (p, _) in enumerate(items):
                p.biology = items[i][1]
            await game.text_channel.send(f"🔄 {player.name} перераздал биологию!")
        else:
            await game.text_channel.send("Нет открытых карт биологии для перераздачи.")

@register_special_card
class DavayteNachistotuHobbi(SpecialCardEffect):
    def __init__(self):
        super().__init__("Давайте начистоту (Хобби)", "Собери все открытые карты хобби у неизгнанных, перемешай и перераздай.")
    async def apply(self, game, player, target=None, extra=None):
        items = []
        for p in game.players.values():
            if not p.is_exiled and p.cards_open["hobby"] and p.hobby:
                items.append((p, p.hobby))
        if items:
            random.shuffle(items)
            for i, (p, _) in enumerate(items):
                p.hobby = items[i][1]
            await game.text_channel.send(f"🔄 {player.name} перераздал хобби!")
        else:
            await game.text_channel.send("Нет открытых карт хобби для перераздачи.")

@register_special_card
class DavayteNachistotuZdorovie(SpecialCardEffect):
    def __init__(self):
        super().__init__("Давайте начистоту (Здоровье)", "Собери все открытые карты здоровья у неизгнанных, перемешай и перераздай.")
    async def apply(self, game, player, target=None, extra=None):
        items = []
        for p in game.players.values():
            if not p.is_exiled and p.cards_open["health"] and p.health:
                items.append((p, p.health))
        if items:
            random.shuffle(items)
            for i, (p, _) in enumerate(items):
                p.health = items[i][1]
            await game.text_channel.send(f"🔄 {player.name} перераздал здоровье!")
        else:
            await game.text_channel.send("Нет открытых карт здоровья для перераздачи.")

@register_special_card
class DavayteNachistotuFakty(SpecialCardEffect):
    def __init__(self):
        super().__init__("Давайте начистоту (Факты)", "Собери все открытые карты фактов у неизгнанных, перемешай и перераздай.")
    async def apply(self, game, player, target=None, extra=None):
        items = []
        for p in game.players.values():
            if not p.is_exiled and p.cards_open["fact"] and p.fact:
                items.append((p, p.fact))
        if items:
            random.shuffle(items)
            for i, (p, _) in enumerate(items):
                p.fact = items[i][1]
            await game.text_channel.send(f"🔄 {player.name} перераздал факты!")
        else:
            await game.text_channel.send("Нет открытых карт фактов для перераздачи.")

@register_special_card
class ZashchitiIgrokaSleva(SpecialCardEffect):
    def __init__(self):
        super().__init__("Защити игрока слева", "Если изгнан игрок слева, в следующий раз ты обязан голосовать против себя.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        if extra:
            left_player_id = extra
            game.player_vows = getattr(game, 'player_vows', {})
            game.player_vows[player.id] = left_player_id
            await game.text_channel.send(f"🛡️ {player.name} защищает игрока слева. Если он будет изгнан, {player.name} будет голосовать против себя.")

@register_special_card
class ZashchitiIgrokaSprava(SpecialCardEffect):
    def __init__(self):
        super().__init__("Защити игрока справа", "Если изгнан игрок справа, в следующий раз ты обязан голосовать против себя.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        if extra:
            right_player_id = extra
            game.player_vows = getattr(game, 'player_vows', {})
            game.player_vows[player.id] = right_player_id
            await game.text_channel.send(f"🛡️ {player.name} защищает игрока справа. Если он будет изгнан, {player.name} будет голосовать против себя.")

@register_special_card
class Zashchitismelogo(SpecialCardEffect):
    def __init__(self):
        super().__init__("Защити смелого", "Если изгнан первый открывший здоровье, ты обязан голосовать против себя.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        game.player_vows = getattr(game, 'player_vows', {})
        game.player_vows[player.id] = "first_health"
        await game.text_channel.send(f"🛡️ {player.name} защищает смелого. Если он будет изгнан, {player.name} будет голосовать против себя.")

@register_special_card
class Zashchitimladshego(SpecialCardEffect):
    def __init__(self):
        super().__init__("Защити младшего", "Если изгнан самый младший по возрасту, ты обязан голосовать против себя.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        game.player_vows = getattr(game, 'player_vows', {})
        game.player_vows[player.id] = "youngest"
        await game.text_channel.send(f"🛡️ {player.name} защищает младшего. Если он будет изгнан, {player.name} будет голосовать против себя.")

@register_special_card
class Zashchitistarshego(SpecialCardEffect):
    def __init__(self):
        super().__init__("Защити старшего", "Если изгнан самый старший по возрасту, ты обязан голосовать против себя.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        game.player_vows = getattr(game, 'player_vows', {})
        game.player_vows[player.id] = "oldest"
        await game.text_channel.send(f"🛡️ {player.name} защищает старшего. Если он будет изгнан, {player.name} будет голосовать против себя.")

@register_special_card
class Diversiya(SpecialCardEffect):
    def __init__(self):
        super().__init__("Диверсия", "Сбрось любую открытую карту бункера.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        await game.text_channel.send(f"💣 {player.name} устраивает диверсию! Карта бункера сброшена.")

@register_special_card
class Diskreditatsiya(SpecialCardEffect):
    def __init__(self):
        super().__init__("Дискредитация", "Голос выбранного игрока не учитывается в этом голосовании.")
    async def apply(self, game, player, target=None, extra=None):
        if target:
            game.discredited_target = target.id
            await game.text_channel.send(f"⛔ {player.name} дискредитировал {target.name}! Его голос не будет учтён.")

@register_special_card
class ObmenKartBagazh(SpecialCardEffect):
    def __init__(self):
        super().__init__("Обмен карт (Багаж)", "Поменяйся открытыми картами багажа с игроком справа или слева.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.luggage and player.luggage:
            player.luggage, target.luggage = target.luggage, player.luggage
            await game.text_channel.send(f"🔄 {player.name} и {target.name} обменялись багажом!")

@register_special_card
class ObmenKartBiologiya(SpecialCardEffect):
    def __init__(self):
        super().__init__("Обмен карт (Биология)", "Поменяйся открытыми картами биологии с игроком справа или слева.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.biology and player.biology:
            player.biology, target.biology = target.biology, player.biology
            await game.text_channel.send(f"🔄 {player.name} и {target.name} обменялись биологией!")

@register_special_card
class ObmenKartHobbi(SpecialCardEffect):
    def __init__(self):
        super().__init__("Обмен карт (Хобби)", "Поменяйся открытыми картами хобби с игроком справа или слева.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.hobby and player.hobby:
            player.hobby, target.hobby = target.hobby, player.hobby
            await game.text_channel.send(f"🔄 {player.name} и {target.name} обменялись хобби!")

@register_special_card
class ObmenKartZdorovie(SpecialCardEffect):
    def __init__(self):
        super().__init__("Обмен карт (Здоровье)", "Поменяйся открытыми картами здоровья с игроком справа или слева.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.health and player.health:
            player.health, target.health = target.health, player.health
            await game.text_channel.send(f"🔄 {player.name} и {target.name} обменялись здоровьем!")

@register_special_card
class ObmenKartFakty(SpecialCardEffect):
    def __init__(self):
        super().__init__("Обмен карт (Факты)", "Поменяйся открытыми картами фактов с игроком справа или слева.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.fact and player.fact:
            player.fact, target.fact = target.fact, player.fact
            await game.text_channel.send(f"🔄 {player.name} и {target.name} обменялись фактами!")

@register_special_card
class Molchanie(SpecialCardEffect):
    def __init__(self):
        super().__init__("Молчание", "Больше никто не говорит в этом раунде до голосования.")
    async def apply(self, game, player, target=None, extra=None):
        game.silence_active = True
        await game.text_channel.send(f"🤫 {player.name} активировал «Молчание»! В этом раунде никто не говорит до голосования.")

@register_special_card
class MneNuzhnee(SpecialCardEffect):
    def __init__(self):
        super().__init__("Мне нужнее", "Забери себе карту багажа у любого игрока. Пострадавший берёт из колоды ещё 1 карту особых условий.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.luggage:
            player.luggage = target.luggage
            target.luggage = None
            new_special = random.choice(SPECIAL_CONDITIONS)
            target.special = Card(new_special, "special")
            target.cards_open["special"] = False
            await game.text_channel.send(f"🔄 {player.name} забирает багаж у {target.name}! {target.name} получает новое особое условие.")
        else:
            await game.text_channel.send(f"⚠️ У {target.name if target else 'цели'} нет багажа.")

@register_special_card
class Kompromat(SpecialCardEffect):
    def __init__(self):
        super().__init__("Компромат", "Голоса против выбранного игрока удваиваются в этом раунде, но сам ты не голосуешь.")
    async def apply(self, game, player, target=None, extra=None):
        if target:
            game.compromat_target = target.id
            game.compromat_owner = player.id
            await game.text_channel.send(f"📄 {player.name} использует компромат против {target.name}! Голоса против него удваиваются, но {player.name} не голосует.")
        else:
            await game.text_channel.send("Не выбрана цель.")

@register_special_card
class TainayaUgroza(SpecialCardEffect):
    def __init__(self):
        super().__init__("Тайная угроза", "Банда мародеров узнала о бункере, в финале это дополнительная угроза.", can_use_after_exile=True)
    async def apply(self, game, player, target=None, extra=None):
        await game.text_channel.send(f"⚠️ {player.name} активирует «Тайную угрозу»! В финале будет дополнительная угроза.")

@register_special_card
class ProsrochennyeTabletki(SpecialCardEffect):
    def __init__(self):
        super().__init__("Просроченные таблетки", "Замени открытую карту здоровья любого игрока на случайную из колоды.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.cards_open["health"]:
            new_health = random.choice(HEALTH)
            target.health = Card(new_health, "health")
            await game.text_channel.send(f"💊 {player.name} заменил здоровье {target.name} на '{new_health}'.")

@register_special_card
class PryamoyVopros(SpecialCardEffect):
    def __init__(self):
        super().__init__("Прямой вопрос", "Выбери тип карт, до конца раунда в свой ход все должны открывать карту этого типа.")
    async def apply(self, game, player, target=None, extra=None):
        if extra:
            card_type = extra
            game.must_reveal_type = card_type
            await game.text_channel.send(f"❓ {player.name} задаёт прямой вопрос! В этом раунде все открывают карты типа **{card_type.capitalize()}**.")

@register_special_card
class KhoroshieTabletki(SpecialCardEffect):
    def __init__(self):
        super().__init__("Хорошие таблетки", "Сбрось открытую карту здоровья у любого игрока.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.cards_open["health"]:
            target.health = None
            target.cards_open["health"] = False
            await game.text_channel.send(f"💊 {player.name} сбросил здоровье {target.name}.")

@register_special_card
class PlanB(SpecialCardEffect):
    def __init__(self):
        super().__init__("План Б", "Все должны переголосовать заново, выбирая другого кандидата.")
    async def apply(self, game, player, target=None, extra=None):
        game.forced_voting_retry = True
        await game.text_channel.send(f"🔄 {player.name} активирует План Б! Начинается переголосование.")

@register_special_card
class FeykovyDiplom(SpecialCardEffect):
    def __init__(self):
        super().__init__("Фейковый диплом", "Смени открытую карту профессии любого игрока на случайную из колоды.")
    async def apply(self, game, player, target=None, extra=None):
        if target and target.cards_open["profession"]:
            new_prof = random.choice(PROFESSIONS)
            target.profession = Card(new_prof, "profession")
            await game.text_channel.send(f"🎓 {player.name} заменяет профессию {target.name} на '{new_prof}'.")

# ========== КЛАСС ИГРЫ ==========

class Game:
    def __init__(self, guild: discord.Guild, lobby_manager: 'LobbyManager'):
        self.guild = guild
        self.lobby_manager = lobby_manager
        self.players: Dict[int, Player] = {}
        self.round = 0
        self.status = "waiting"

        self.category = None
        self.text_channel = None
        self.voice_channel = None
        self.spectator_role = None

        self.exiled: List[int] = []
        self.votes: Dict[int, int] = {}
        self.voters: Set[int] = set()
        self.board_message = None

        self.reveal_order: List[int] = []
        self.reveal_index = 0

        # Флаги особых условий
        self.silence_active = False
        self.discredited_target = None
        self.compromat_target = None
        self.compromat_owner = None
        self.vote_weights: Dict[int, int] = {}
        self.must_reveal_type: Optional[str] = None
        self.forced_voting_retry = False
        self.friend_protection: Dict[int, int] = {}
        self.player_vows: Dict[int, any] = {}

    async def create_channels(self):
        if BUNKER_CATEGORY_ID:
            category = self.guild.get_channel(BUNKER_CATEGORY_ID)
        else:
            category = await self.guild.create_category("🎮 Игра Бункер")
        self.category = category
        self.text_channel = await self.guild.create_text_channel("🛡️-табло-бункера", category=category)
        self.voice_channel = await self.guild.create_voice_channel("🎙️-вход-в-бункер", category=category, user_limit=10)
        self.spectator_role = await self.guild.create_role(name="Зритель Бункера", permissions=discord.Permissions(connect=True, speak=False))
        await self.voice_channel.set_permissions(self.guild.default_role, connect=True, speak=False)
        await self.voice_channel.set_permissions(self.spectator_role, connect=True, speak=False)

    async def add_player(self, member: discord.Member) -> bool:
        if member.id in self.players:
            return False
        self.players[member.id] = Player(member)
        return True

    async def distribute_cards(self):
        for player in self.players.values():
            player.profession = Card(random.choice(PROFESSIONS), "profession")
            player.biology = Card(random.choice(BIOLOGY), "biology")
            player.health = Card(random.choice(HEALTH), "health")
            player.hobby = Card(random.choice(HOBBIES), "hobby")
            player.luggage = Card(random.choice(LUGGAGE), "luggage")
            player.fact = Card(random.choice(FACTS), "fact")
            player.special = Card(random.choice(SPECIAL_CONDITIONS), "special")

            embed = self._create_private_embed(player)
            view = SpecialCardView(player, self)
            await player.member.send(embed=embed, view=view)

    def _create_private_embed(self, player: Player) -> discord.Embed:
        embed = discord.Embed(
            title="🧑‍🚀 Ваш персонаж",
            description=(
                f"**Профессия:** {player.profession.name}\n"
                f"**Биология:** {player.biology.name}\n"
                f"**Здоровье:** {player.health.name}\n"
                f"**Хобби:** {player.hobby.name}\n"
                f"**Багаж:** {player.luggage.name}\n"
                f"**Факт:** {player.fact.name}\n"
                f"**Особое условие:** {player.special.name}"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Используйте особое условие через кнопку ниже.")
        return embed

    async def move_players_to_voice(self):
        for member_id in self.lobby_manager.players:
            member = self.guild.get_member(member_id)
            if member:
                await member.move_to(self.voice_channel)
        for member_id in self.lobby_manager.spectators:
            member = self.guild.get_member(member_id)
            if member:
                await member.move_to(self.voice_channel)
                await member.add_roles(self.spectator_role)

    async def start_game(self):
        self.status = "playing"
        self.round = 1
        await self.create_channels()
        await self.distribute_cards()
        await self.move_players_to_voice()
        await self.update_board()
        await self.start_round()

    async def start_round(self):
        if self.round > 5 or self.status != "playing":
            await self.finish_game()
            return

        bunker_card = random.choice(BUNKER_CARDS)
        await self.text_channel.send(f"🏚️ **Исследование бункера – Раунд {self.round}**\n📦 **Карта Бункера:** {bunker_card}")

        self.silence_active = False
        self.discredited_target = None
        self.compromat_target = None
        self.compromat_owner = None
        self.vote_weights = {}
        self.must_reveal_type = None
        self.forced_voting_retry = False

        alive = [p for p in self.players.values() if not p.is_exiled]
        self.reveal_order = [p.id for p in alive]
        self.reveal_index = 0

        await self.text_channel.send(f"🏚️ **Раунд {self.round}** начинается!")
        await self.update_board()
        await self.reveal_phase()

    async def reveal_phase(self):
        if self.reveal_index >= len(self.reveal_order):
            await self.after_reveal()
            return

        player_id = self.reveal_order[self.reveal_index]
        player = self.players[player_id]

        closed = [k for k in player.cards_open if not player.cards_open[k] and k != "special"]
        if self.must_reveal_type and self.must_reveal_type in closed:
            chosen = self.must_reveal_type
            player.open_card(chosen)
            await self.text_channel.send(f"📖 **{player.name}** по требованию открывает **{chosen.capitalize()}**: {getattr(player, chosen).name}")
            await self.update_board()
            self.reveal_index += 1
            await asyncio.sleep(2)
            await self.reveal_phase()
            return

        if not closed:
            await self.text_channel.send(f"⚠️ {player.name} уже открыл все карты. Пропускаем ход.")
            self.reveal_index += 1
            await asyncio.sleep(1)
            await self.reveal_phase()
            return

        view = RevealView(self, player, timeout=15)
        try:
            msg = await player.member.send("Выберите карту для раскрытия:", view=view)
            await view.wait()
            await msg.delete()
        except:
            chosen = random.choice(closed)
            await self.after_reveal_choice(player, chosen)
            return

    async def after_reveal_choice(self, player: Player, chosen_card_type: str):
        if not player.cards_open[chosen_card_type]:
            player.open_card(chosen_card_type)
            await self.text_channel.send(f"📖 **{player.name}** раскрыл(а) **{chosen_card_type.capitalize()}**: {getattr(player, chosen_card_type).name}")
            await self.update_board()
        else:
            await self.text_channel.send(f"⚠️ {player.name} не смог выбрать новую карту. Пропускаем ход.")

        self.reveal_index += 1
        await asyncio.sleep(2)
        await self.reveal_phase()

    async def after_reveal(self):
        if self.round >= 2:
            await self.voting_phase()
        else:
            self.round += 1
            await self.start_round()

    async def voting_phase(self):
        alive = [p for p in self.players.values() if not p.is_exiled]
        if len(alive) <= 1:
            await self.after_voting()
            return

        embed = discord.Embed(
            title=f"🗳️ Голосование – Раунд {self.round}",
            description="Выберите игрока, которого хотите исключить. У вас 15 секунд.",
            color=discord.Color.blue()
        )
        view = VotingView(self, alive, self.text_channel)
        await self.text_channel.send(embed=embed, view=view)

    async def after_voting(self):
        if self.forced_voting_retry:
            self.forced_voting_retry = False
            await self.voting_phase()
            return

        if self.votes:
            max_votes = max(self.votes.values())
            candidates = [uid for uid, v in self.votes.items() if v == max_votes]
            if len(candidates) == 1:
                exiled_id = candidates[0]
                self.exiled.append(exiled_id)
                player = self.players[exiled_id]
                player.is_exiled = True
                for k in player.cards_open:
                    player.cards_open[k] = True
                await self.text_channel.send(f"❌ {player.name} исключён!")
                await self.text_channel.send(f"💬 {player.name}, у вас есть 60 секунд для прощальных слов.")
                await asyncio.sleep(60)
                await self.update_board()
            else:
                await self.text_channel.send("⚖️ Ничья! Проводим защиту-баттл.")
                for uid in candidates:
                    p = self.players[uid]
                    await self.text_channel.send(f"🗣️ {p.name}, у вас есть 2 минуты, чтобы оправдаться.")
                    await asyncio.sleep(120)
                await self.text_channel.send("🔄 Защита-баттл завершён. Переходим к следующему раунду.")
        else:
            await self.text_channel.send("❌ Никто не проголосовал.")

        self.votes = {}
        self.voters = set()
        self.vote_weights = {}
        self.silence_active = False
        self.discredited_target = None
        self.compromat_target = None
        self.compromat_owner = None

        self.round += 1
        await self.start_round()

    async def update_board(self):
        embed = discord.Embed(
            title="📋 Табло Бункера",
            description="Открытые карты игроков",
            color=discord.Color.blue()
        )
        for p in self.players.values():
            if p.is_exiled:
                continue
            open_cards = p.get_open_list()
            text = "\n".join(open_cards) if open_cards else "Ничего не открыто"
            embed.add_field(name=p.name, value=text, inline=False)

        if self.board_message:
            await self.board_message.edit(embed=embed)
        else:
            self.board_message = await self.text_channel.send(embed=embed)

    async def finish_game(self):
        winners = [p for p in self.players.values() if not p.is_exiled]
        win_mentions = " ".join([p.member.mention for p in winners])
        embed = discord.Embed(
            title="🏆 Игра завершена!",
            description=f"Победители: {win_mentions}\nВсего выжило: {len(winners)} человек.",
            color=discord.Color.gold()
        )
        await self.text_channel.send(embed=embed)
        self.status = "finished"
        await self.voice_channel.delete()
        await self.spectator_role.delete()
        self.lobby_manager.voice_channel = None
        await self.lobby_manager.channel.send("🎮 Игра завершена. Вы можете создать новое лобби.")

# ========== КНОПКИ И ИНТЕРФЕЙС ==========

class RevealView(ui.View):
    def __init__(self, game: Game, player: Player, timeout: int = 15):
        super().__init__(timeout=timeout)
        self.game = game
        self.player = player
        self.chosen = None

        closed = [k for k in player.cards_open if not player.cards_open[k] and k != "special"]
        if not closed:
            self.chosen = "profession"
            return
        for card_type in closed:
            card_name = getattr(player, card_type).name if hasattr(player, card_type) else card_type
            btn = ui.Button(label=f"{card_type.capitalize()}: {card_name}", style=discord.ButtonStyle.secondary, custom_id=f"reveal_{card_type}")
            btn.callback = self.make_callback(card_type)
            self.add_item(btn)

    def make_callback(self, card_type):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player.id:
                await interaction.response.send_message("❌ Это не ваш ход.", ephemeral=True)
                return
            self.chosen = card_type
            self.stop()
            await interaction.response.send_message(f"✅ Вы выбрали карту **{card_type.capitalize()}**", ephemeral=True)
            await self.game.after_reveal_choice(self.player, card_type)
        return callback

    async def on_timeout(self):
        if self.chosen is None:
            closed = [k for k in self.player.cards_open if not self.player.cards_open[k] and k != "special"]
            if closed:
                self.chosen = random.choice(closed)
            else:
                self.chosen = "profession"
            await self.game.after_reveal_choice(self.player, self.chosen)

class SpecialCardView(ui.View):
    def __init__(self, player: Player, game: Game):
        super().__init__(timeout=None)
        self.player = player
        self.game = game

    @ui.button(label="🃏 Использовать особое условие", style=discord.ButtonStyle.primary, custom_id="use_special")
    async def use_special(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("❌ Это не ваша карта.", ephemeral=True)
            return
        await interaction.response.send_message("Используйте команду `/использовать_условие` и укажите цель.", ephemeral=True)

class VotingView(ui.View):
    def __init__(self, game: Game, alive_players: List[Player], channel):
        super().__init__(timeout=15)
        self.game = game
        self.alive_players = alive_players
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
            if self.game.discredited_target == interaction.user.id:
                await interaction.response.send_message("❌ Вы дискредитированы и не можете голосовать в этом раунде.", ephemeral=True)
                return
            if self.game.friend_protection.get(interaction.user.id) == target_id:
                await interaction.response.send_message("❌ Вы не можете голосовать против друга.", ephemeral=True)
                return
            weight = self.game.vote_weights.get(interaction.user.id, 1)
            self.game.voters.add(interaction.user.id)
            self.game.votes[target_id] = self.game.votes.get(target_id, 0) + weight
            if self.game.compromat_target == target_id:
                self.game.votes[target_id] += 1
            await interaction.response.send_message(f"✅ Вы проголосовали за {self.game.players[target_id].name} (вес: {weight}).", ephemeral=True)
            alive = self.game.get_alive_players()
            if len(self.game.voters) >= len(alive):
                self.stop()
                await self.game.after_voting()
        return callback

    async def on_timeout(self):
        await self.game.after_voting()

# ========== ЛОББИ И АВТОМАТИЧЕСКОЕ СОЗДАНИЕ СООБЩЕНИЯ ==========

class LobbyManager:
    def __init__(self, guild: discord.Guild, channel: discord.TextChannel, host: discord.Member):
        self.guild = guild
        self.channel = channel
        self.host = host
        self.voice_channel = None
        self.players: Set[int] = set()
        self.spectators: Set[int] = set()
        self.game = None

    async def create_voice_channel(self):
        category = self.guild.get_channel(BUNKER_CATEGORY_ID)
        if not category:
            category = await self.guild.create_category("🎮 Игра Бункер")
        self.voice_channel = await self.guild.create_voice_channel(
            f"🎙️ Лобби {self.host.display_name}",
            category=category,
            user_limit=10
        )
        return self.voice_channel

    def add_player(self, member: discord.Member):
        self.players.add(member.id)

    def remove_player(self, member: discord.Member):
        self.players.discard(member.id)

    def add_spectator(self, member: discord.Member):
        self.spectators.add(member.id)

    def remove_spectator(self, member: discord.Member):
        self.spectators.discard(member.id)

    def is_full(self) -> bool:
        return len(self.players) >= 6

class LobbyView(ui.View):
    def __init__(self, manager: Optional[LobbyManager] = None):
        super().__init__(timeout=None)
        self.manager = manager
        if manager:
            self.add_item(JoinButton(manager))
            self.add_item(SpectatorButton(manager))
        else:
            self.add_item(CreateLobbyButton())

class CreateLobbyButton(ui.Button):
    def __init__(self):
        super().__init__(label="➕ Создать лобби", style=discord.ButtonStyle.primary, custom_id="create_lobby")

    async def callback(self, interaction: discord.Interaction):
        manager = LobbyManager(interaction.guild, interaction.channel, interaction.user)
        vc = await manager.create_voice_channel()
        await interaction.response.send_message(f"✅ Голосовой канал `{vc.name}` создан! Заходите в него.", ephemeral=True)
        embed = discord.Embed(
            title="🎮 Лобби создано!",
            description=f"Создатель: {manager.host.mention}\nГолосовой канал: {manager.voice_channel.mention}\nНажмите **«Присоединиться»**, чтобы стать участником игры.\nНажмите **«Стать зрителем»**, чтобы наблюдать (без микрофона).\nВсе участники и зрители должны зайти в голосовой канал!",
            color=discord.Color.green()
        )
        view = LobbyView(manager)
        await interaction.message.edit(embed=embed, view=view)
        start_view = StartGameView(manager)
        await manager.host.send("🚀 Вы готовы начать игру? Нажмите кнопку ниже, когда все соберутся.", view=start_view)

class JoinButton(ui.Button):
    def __init__(self, manager: LobbyManager):
        super().__init__(label="🎙️ Присоединиться", style=discord.ButtonStyle.success, custom_id="join_lobby")
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if self.manager.is_full():
            await interaction.response.send_message("❌ Мест больше нет.", ephemeral=True)
            return
        if interaction.user.id in self.manager.players:
            await interaction.response.send_message("❌ Вы уже участник.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel != self.manager.voice_channel:
            await interaction.response.send_message("❌ Вы должны зайти в голосовой канал Лобби.", ephemeral=True)
            return
        self.manager.add_player(interaction.user)
        self.manager.spectators.discard(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.display_name} стал участником!", ephemeral=True)

class SpectatorButton(ui.Button):
    def __init__(self, manager: LobbyManager):
        super().__init__(label="👁️ Стать зрителем", style=discord.ButtonStyle.secondary, custom_id="spectate_lobby")
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id in self.manager.players:
            await interaction.response.send_message("❌ Вы уже участник. Нельзя быть одновременно зрителем.", ephemeral=True)
            return
        if not interaction.user.voice or interaction.user.voice.channel != self.manager.voice_channel:
            await interaction.response.send_message("❌ Вы должны зайти в голосовой канал Лобби.", ephemeral=True)
            return
        self.manager.add_spectator(interaction.user)
        await interaction.response.send_message(f"👁️ {interaction.user.display_name} стал зрителем.", ephemeral=True)

class StartGameView(ui.View):
    def __init__(self, manager: LobbyManager):
        super().__init__(timeout=None)
        self.manager = manager

    @ui.button(label="🚀 Начать игру", style=discord.ButtonStyle.success, custom_id="start_game")
    async def start_game(self, interaction: discord.Interaction, button: ui.Button):
        if len(self.manager.players) < 2:
            await interaction.response.send_message("❌ Нужно минимум 2 игрока.", ephemeral=True)
            return
        game = Game(interaction.guild, self.manager)
        self.manager.game = game
        for pid in self.manager.players:
            member = interaction.guild.get_member(pid)
            if member:
                await game.add_player(member)
        await interaction.response.send_message("✅ Игра начинается!", ephemeral=True)
        await game.start_game()

# ========== АВТОМАТИЧЕСКОЕ СОЗДАНИЕ СООБЩЕНИЯ ==========

async def ensure_lobby_message(bot):
    if not BUNKER_LOBBY_CHANNEL_ID:
        logger.warning("BUNKER_LOBBY_CHANNEL_ID не задан.")
        return
    channel = bot.get_channel(BUNKER_LOBBY_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(BUNKER_LOBBY_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Не удалось найти канал: {e}")
            return
    saved_msg_id = get_lobby_message_id()
    if saved_msg_id:
        try:
            msg = await channel.fetch_message(saved_msg_id)
            if msg.author == bot.user and msg.embeds and msg.components:
                return
        except:
            pass
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.embeds and msg.components:
            for embed in msg.embeds:
                if embed.title and "Игра Бункер" in embed.title:
                    set_lobby_message_id(msg.id)
                    return
    embed = discord.Embed(
        title="🎮 Игра Бункер",
        description="Нажмите **«Создать лобби»**, чтобы начать новую игру.",
        color=discord.Color.blue()
    )
    view = LobbyView()
    msg = await channel.send(embed=embed, view=view)
    set_lobby_message_id(msg.id)
    logger.info(f"Создано новое сообщение лобби (ID: {msg.id})")
