import functools
import pickle
import sys
import datetime
from abc import ABC, abstractmethod
from collections import UserDict
from typing import Callable, Any


def input_error(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(self: "Command", *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except TypeError as e:
            self.bot.interface.show_message(f"Invalid arguments. Usage:\n{self.help}")
        except ValueError as e:
            self.bot.interface.show_message(f"{e}")

    return wrapper


class Field:
    value: str

    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return str(self.value)


class Name(Field):
    pass


class Phone(Field):
    def __init__(self, value: str):
        if len(value) != 10 or not value.isdigit():
            raise ValueError("Phone number must be 10 digits.")

        super().__init__(value)


class Birthday(Field):
    __date: datetime.datetime

    def __init__(self, value: str):
        try:
            self.__date = datetime.datetime.strptime(value, "%d.%m.%Y")
            super().__init__(value)
        except ValueError:
            raise ValueError("Accepted date format: 'DD.MM.YYYY'.")

    @property
    def date(self) -> datetime.date:
        return self.__date.date()

    @staticmethod
    def find_next_weekday(date: datetime.date, weekday: int) -> datetime.date:
        days_ahead = weekday - date.weekday()

        if days_ahead <= 0:
            days_ahead += 7

        return date + datetime.timedelta(days=days_ahead)

    @staticmethod
    def adjust_for_weekend(date: datetime.date) -> datetime.date:
        if date.weekday() >= 5:
            return Birthday.find_next_weekday(date, 0)

        return date


class Record:
    name: Name
    phones: list[Phone]
    birthday: Birthday | None

    def __init__(self, name: str):
        self.name = Name(name)
        self.phones = []
        self.birthday = None

    def add_birthday(self, birthday: str):
        self.birthday = Birthday(birthday)

    def add_phone(self, number: str):
        self.phones.append(Phone(number))

    def remove_phone(self, number: str):
        for p in self.phones:
            if p.value == number:
                self.phones.remove(p)
                return

        raise ValueError(f"Phone number '{number}' not found.")

    def edit_phone(self, old_number: str, new_number: str):
        for i, p in enumerate(self.phones):
            if p.value == old_number:
                self.phones[i] = Phone(new_number)
                return

        raise ValueError(f"Phone number '{old_number}' not found.")

    def find_phone(self, number: str) -> Phone | None:
        for p in self.phones:
            if p.value == number:
                return p

        return None

    def __str__(self) -> str:
        return f"{self.name.value}\n{'\n'.join(f'  {p.value}' for p in self.phones)}"


class AddressBook(UserDict[str, Record]):
    def add_record(self, record: Record):
        self.data[record.name.value] = record

    def find(self, name: str) -> Record | None:
        return self.data.get(name, None)

    def delete(self, name: str):
        if not self.data.pop(name, None):
            raise ValueError("Contact '{name}' not found.")

    def get_upcoming_birthdays(self, days=7) -> list[dict[str, str]]:
        upcoming_birthdays = []
        today = datetime.date.today()

        for record in self.values():
            if not record.birthday:
                continue

            birthday_this_year = record.birthday.date.replace(year=today.year)

            if birthday_this_year < today:
                birthday_this_year = birthday_this_year.replace(year=birthday_this_year.year + 1)

            if 0 <= (birthday_this_year - today).days <= days:
                birthday_this_year = Birthday.adjust_for_weekend(birthday_this_year)
                congratulation_date_str = birthday_this_year.strftime("%d.%m.%Y")
                upcoming_birthdays.append({"name": record.name, "birthday": congratulation_date_str})

        return upcoming_birthdays

    def __str__(self) -> str:
        return "\n".join(str(r) for r in self.data.values())


class Command:
    __names: list[str]
    __func: Callable
    __help: str
    bot: "Bot"

    def __init__(self, bot: "Bot", names: str | list[str], func: Callable, help_str: str):
        self.names = names
        self.__func = func
        self.__help = help_str
        self.bot = bot

    @property
    def names(self) -> list[str]:
        return self.__names

    @names.setter
    def names(self, names: str | list[str]):
        self.__names = [names] if isinstance(names, str) else names

    @input_error
    def execute(self, *args, **kwargs):
        self.__func(*args, **kwargs)

    @property
    def help(self) -> str:
        return f"{', '.join(self.__names)}{': ' + self.__help if self.__help else ''}"


class BotInterface(ABC):
    @abstractmethod
    def get_input(self, prompt: str) -> str:
        pass

    @abstractmethod
    def show_message(self, message: str):
        pass

    @abstractmethod
    def show_help(self, help_str: str):
        pass


class ConsoleInterface(BotInterface):
    def get_input(self, prompt: str) -> str:
        return input(prompt)

    def show_message(self, message: str):
        print(message)

    def show_help(self, help_str: str):
        print(help_str)


class Bot:
    __book: AddressBook
    __commands: list[Command]
    interface: BotInterface

    def __init__(self):
        self.interface = ConsoleInterface()
        self.__book = self.__load_data()
        self.__commands = []

    def add_command(self, name: str | list[str], cmd: Callable, help_str: str = ""):
        self.__commands.append(Command(self, name, cmd, help_str))

    def __parse_input(self, user_input: str) -> tuple[None, list[Any]] | tuple[str, list[str]]:
        parts = user_input.strip().split()

        if not parts:
            return None, []

        cmd = parts[0].lower()
        args = parts[1:]

        return cmd, args

    def __get_help(self, title: str = "Available commands:") -> str:
        help_str = f"{title}\n"
        help_str += "\n".join([cmd.help for cmd in self.__commands])
        return help_str

    def get_help_for_cmd(self, name: str) -> str:
        for cmd in self.__commands:
            if name in cmd.names:
                return cmd.help

        raise ValueError("No such command.")

    def save_data(self, filename: str = "addressbook.pkl"):
        try:
            with open(filename, "wb") as f:
                pickle.dump(self.__book, f)
        except Exception as e:
            self.interface.show_message(f"An unexpected error occurred: {e}")

    def __load_data(self, filename: str = "addressbook.pkl"):
        try:
            with open(filename, "rb") as f:
                return pickle.load(f)
        except FileNotFoundError:
            return AddressBook()
        except Exception as e:
            self.interface.show_message(f"An unexpected error occurred: {e}")
            return AddressBook()

    def run(self):
        self.add_command("hello", self.hello)
        self.add_command(["exit", "close"], self.exit)
        self.add_command("add", self.add_number, "[name] [number]")
        self.add_command("change", self.change_number, "[name] [old number] [new number]")
        self.add_command("phone", self.show_phone, "[name]")
        self.add_command("all", self.show_all)
        self.add_command("add-birthday", self.add_birthday, "[name] [birthday]")
        self.add_command("show-birthday", self.show_birthday, "[name]")
        self.add_command("birthdays", self.get_birthdays)

        self.interface.show_help(self.__get_help("Welcome to the assistant bot!"))

        while True:
            user_input = self.interface.get_input("Enter a command: ")
            cmd_str, args = self.__parse_input(user_input)
            cmd = next((c for c in self.__commands if cmd_str in c.names), None)

            if cmd:
                cmd.execute(*args)
            else:
                self.interface.show_help(self.__get_help("Invalid command."))

    def hello(self, *_):
        self.interface.show_message("Hello, how can I help you?")

    def exit(self, *_):
        self.interface.show_message("Goodbye!")
        sys.exit()

    def add_number(self, name: str, number: str):
        record = self.__book.find(name)
        if record:
            if record.find_phone(number):
                raise ValueError("Phone number already exists.")

            record.add_phone(number)
            self.interface.show_message(f"Added number '{number}' to contact '{name}'.")
            return

        record = Record(name)
        record.add_phone(number)

        self.__book.add_record(record)

        self.interface.show_message(f"Contact '{name}' with number '{number}' added.")

    def change_number(self, name: str, old_num: str, new_num: str):
        record = self.__book.find(name)
        if record:
            if record.find_phone(new_num):
                raise ValueError(f"Number '{new_num}' already exists.")

            record.edit_phone(old_num, new_num)
            self.interface.show_message(f"Number changed from '{old_num}' to '{new_num}' for contact '{name}'.")
        else:
            raise ValueError(f"Contact '{name}' not found.")

    def show_phone(self, name: str):
        record = self.__book.find(name)
        if record:
            self.interface.show_message(str(record))
        else:
            raise ValueError(f"Contact '{name}' not found.")

    def show_all(self, *_):
        if not len(self.__book):
            self.interface.show_message("No contacts stored.")
        else:
            self.interface.show_message(str(self.__book))

    def add_birthday(self, name: str, birthday: str):
        record = self.__book.find(name)
        if record:
            record.add_birthday(birthday)
            self.interface.show_message(f"{name}'s birthday is {birthday}.")
        else:
            raise ValueError(f"Contact '{name}' not found.")

    def show_birthday(self, name: str):
        record = self.__book.find(name)
        if record:
            self.interface.show_message(f"{name}'s birthday is {record.birthday}.")
        else:
            raise ValueError(f"Contact '{name}' not found.")

    def get_birthdays(self, *_):
        birthdays = self.__book.get_upcoming_birthdays()

        if len(birthdays):
            birthdays_str = "Upcoming birthdays:\n"
            birthdays_str += "\n  ".join([f"{b['name']} - {b['birthday']}" for b in birthdays])
            self.interface.show_message(birthdays_str)
        else:
            self.interface.show_message("No upcoming birthdays.")


def main():
    bot = Bot()

    try:
        bot.run()
    except KeyboardInterrupt:
        bot.exit()
    finally:
        bot.save_data()


if __name__ == "__main__":
    main()
