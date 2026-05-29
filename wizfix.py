#!/usr/bin/env -S uv run --script

# /// script
# license = "MIT"
# requires-python = ">=3.12"
# dependencies = ["click>=8.3"]
# author = "Jürgen Strobel"
# email = "juergen+wizfix@strobel.info"
# ///
# ruff: noqa: E731

"""
CLI utility to inspect and edit characters in Wizardry 1-3

(C) 2026 Jürgen Strobel
List of offsets and values taken from
https://www.zimlab.com/wizardry/recovered/wizardrygame/pages/w1/cheat.htm

Why? The MSDOS archives version's level up bug completely ruined my stats.
"""

import binascii
import contextlib
import dataclasses
import itertools
import math
import mmap
import operator
import pprint
import struct

import click

VERSION = "0.2"

# --- Game Data ---

RACES = ["HUMAN", "ELF", "DWARF", "GNOME", "HOBBIT"]
CLASSES = ["FIGHTER", "MAGE", "PRIEST", "THIEF", "BISHOP", "SAMURAI", "LORD", "NINJA"]
ALIGNMENTS = ["GOOD", "NEUTRAL", "EVIL"]

# --- Character interface ---

FORMAT = "<"  # built dynamically by packed_field() later
CHAR_LEN = 0  # same
B5_WEIGHTS = (1, 256, 10_000, 2_560_000, 100_000_000)


class hexbytes(bytes):
    def __repr__(self):
        return f"hexbytes({binascii.hexlify(self, sep=' ').decode('ASCII')})"


def packed_field(fmt, default=None):
    global FORMAT
    global CHAR_LEN
    FORMAT += fmt
    CHAR_LEN = struct.calcsize(FORMAT)
    if fmt[-1] == "s" and default is None:
        default = HexBytesDescriptor(fmt)
    # This gives *every* field a default, possibly of None.
    # Necessary because non-defaulted fields cannot follow fields with descriptors,
    # apparently at least not when the default is set through dataclasses.field.
    return dataclasses.field(default=default)


def padding_field(fmt, default=None):
    global FORMAT
    global CHAR_LEN
    FORMAT += fmt
    CHAR_LEN = struct.calcsize(FORMAT)
    if fmt[-1] == "s" and default is None:
        default = HexBytesDescriptor(fmt)
    return dataclasses.field(repr=False, default=default)


def virt_field(default):
    return dataclasses.field(default=default, init=False)


def bits(x, start, end, shiftleft=0):
    """bits of x from start to end *inclusive*; result shifted left

    Numbering goes from left to right, starts at 1, as in reference document!
    """
    n = end - start + 1
    return ((x >> (32 - end)) & ((1 << n) - 1)) << shiftleft


def check_stat(name, x):
    if not 1 <= x <= 18:
        raise ValueError(f"{name} outside range: {x}")


class HexBytesDescriptor:
    def __init__(self, fmt):
        self.size = int(fmt[:-1])

    def __set_name__(self, owner, name):
        self.name = "_" + name

    def __get__(self, obj, objtype=None):
        return getattr(obj, self.name)

    def __set__(self, obj, value):
        if isinstance(value, int):
            value = value.to_bytes(self.size)
        setattr(obj, self.name, hexbytes(value))


class TabledDescriptor:
    def __init__(self, labels):
        values = list(range(1, len(labels) + 1))
        self.table = dict(zip(values, labels))

    def __set_name__(self, owner, name):
        self.name = f"{name}_raw"

    def __get__(self, obj, objtype=None):
        v = getattr(obj, self.name)
        return self.table.get(v, "<unknown>")

    def __set__(self, obj, value):
        if isinstance(value, bytes):
            value = value.decode("ASCII")
        value = value.upper()
        if value in self.table.values():
            value = list(self.table.keys())[list(self.table.values()).index(value)]
        else:
            raise ValueError(str(value))
        setattr(obj, self.name, value)


class StatsDescriptor:
    def __init__(self, start):
        """stats with 5 contiguous bits at start"""
        self.start = start
        self.end = start + 4
        self.sl = 32 - self.end

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        x = int.from_bytes(obj.stats)
        return bits(x, self.start, self.end)

    def __set__(self, obj, value):
        check_stat(self.name, value)
        x = int.from_bytes(obj.stats)
        x ^= bits(x, self.start, self.end, self.sl) ^ (value << self.sl)
        obj.stats = x.to_bytes(4)


class StatsDescriptor2:
    """for stats with bits in 2 places"""

    def __init__(self, start1, end1, start2):
        self.start1, self.end1, self.start2 = start1, end1, start2
        self.len1 = end1 - start1 + 1
        self.len2 = 5 - self.len1
        self.end2 = start2 + self.len2 - 1
        self.sl1 = 32 - self.end1
        self.sl2 = 32 - self.end2

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        x = int.from_bytes(obj.stats)
        b1 = bits(x, self.start1, self.end1, self.len2)
        b2 = bits(x, self.start2, self.end2)
        return b1 | b2

    def __set__(self, obj, value):
        check_stat(self.name, value)
        val1 = value >> self.len2
        val2 = value & ((1 << self.len2) - 1)
        x = int.from_bytes(obj.stats)
        x ^= bits(x, self.start1, self.end1, self.sl1) ^ (val1 << self.sl1)
        x ^= bits(x, self.start2, self.end2, self.sl2) ^ (val2 << self.sl2)
        obj.stats = x.to_bytes(4)


class AgeDescriptor:
    def __get__(self, obj, objtype=None):
        return obj.age_raw[0] // 52 + obj.age_raw[1] * 5

    def __set__(self, obj, value):
        b0 = min(255, int(value * 52) % (5 * 52))
        b1 = int(value) // 5
        obj.age_raw = hexbytes([b0, b1])


class B5_Descriptor:
    """A number encoded in 5 bytes using B5_WEIGTHS"""

    def __set_name__(self, owner, name):
        self.name_raw = name + "_raw"

    def __get__(self, obj, objtype=None):
        xs = getattr(obj, self.name_raw)
        return math.sumprod(xs, B5_WEIGHTS)

    def __set__(self, obj, value):
        xs = []
        for w in reversed(B5_WEIGHTS):
            xs.append(value // w)
            value %= w
        setattr(obj, self.name_raw, bytes(reversed(xs)))


class ItemDescriptor:
    """Item by 2-byte number

    Can use Python hex literals directly from table, concatenate byte #7 and #8.
    Set items will become unequipped and identified.
    The number of valid items is given by n_items, and the user is reponsible to
    carefully manage this and inventory. The last non empty item can be removed
    by assigning 0.
    """

    def __set_name__(self, owner, name):
        self.n = int(name[-1])
        self.name_raw = name + "_raw"

    def __get__(self, obj, objtype=None):
        """Convert item bytes 7 and 8 to a hex string"""
        if self.n <= obj.n_items:
            xs = getattr(obj, self.name_raw)
            itemid = (xs[6] << 8) + xs[7]
            return f"0x{itemid:04x}"
        else:
            return "<empty>"

    def __set__(self, obj, value):
        """Accept int or str containing hex value"""
        if isinstance(value, str):
            value = int(value, 16)
        if self.n > obj.n_items + 1:
            raise ValueError("can only assign to first empty item")
        if value == 0 and self.n != obj.n_items:
            raise ValueError("can only remove last non empty item")
        b7, b8 = divmod(value, 256)
        xs = [0, 0, 0, 0, value > 0, 0, b7, b8]
        setattr(obj, self.name_raw, bytes(xs))
        obj.n_items = max(obj.n_items, self.n) - (value == 0)


@dataclasses.dataclass
class Character:
    """Character class making the binary data accessible

    Makes most fields directly accesible, and provides some
    "virtual" fields to help with the more exotic encodings.
    Does round trip padding exactly.
    Has some safeguards, but buyer beware.
    """

    # fields

    name: str = packed_field("16p")
    password: str = packed_field("16p")
    out: int = packed_field("B")
    _padding0: hexbytes = padding_field("1s")

    race_raw: int = packed_field("B")
    race: TabledDescriptor = virt_field(TabledDescriptor(RACES))
    _padding1: hexbytes = padding_field("1s")
    cls_raw: int = packed_field("B")
    cls: TabledDescriptor = virt_field(TabledDescriptor(CLASSES))
    _padding2: hexbytes = padding_field("1s")
    age_raw: hexbytes = packed_field("2s")
    age: AgeDescriptor = virt_field(AgeDescriptor())
    life: int = packed_field("B")
    _padding3: hexbytes = padding_field("1s")
    alignment_raw: int = packed_field("B")
    alignment: TabledDescriptor = virt_field(TabledDescriptor(ALIGNMENTS))
    _padding4: hexbytes = padding_field("1s")
    stats: hexbytes = packed_field("4s")
    strength: StatsDescriptor = virt_field(StatsDescriptor(4))
    iq: StatsDescriptor2 = virt_field(StatsDescriptor2(15, 16, 1))
    piety: StatsDescriptor = virt_field(StatsDescriptor(10))
    vitality: StatsDescriptor = virt_field(StatsDescriptor(20))
    agility: StatsDescriptor2 = virt_field(StatsDescriptor2(31, 32, 17))
    luck: StatsDescriptor = virt_field(StatsDescriptor(26))
    _padding5: hexbytes = padding_field("4s")

    gold_raw: hexbytes = packed_field("5s")
    gold: B5_Descriptor = virt_field(B5_Descriptor())
    _padding6: hexbytes = padding_field("1s")
    n_items: int = packed_field("B")
    _padding7: hexbytes = padding_field("1s")
    item1_raw: hexbytes = packed_field("8s")
    item1: ItemDescriptor = virt_field(ItemDescriptor())
    item2_raw: hexbytes = packed_field("8s")
    item2: ItemDescriptor = virt_field(ItemDescriptor())
    item3_raw: hexbytes = packed_field("8s")
    item3: ItemDescriptor = virt_field(ItemDescriptor())
    item4_raw: hexbytes = packed_field("8s")
    item4: ItemDescriptor = virt_field(ItemDescriptor())
    item5_raw: hexbytes = packed_field("8s")
    item5: ItemDescriptor = virt_field(ItemDescriptor())
    item6_raw: hexbytes = packed_field("8s")
    item6: ItemDescriptor = virt_field(ItemDescriptor())
    item7_raw: hexbytes = packed_field("8s")
    item7: ItemDescriptor = virt_field(ItemDescriptor())
    item8_raw: hexbytes = packed_field("8s")
    item8: ItemDescriptor = virt_field(ItemDescriptor())

    experience_raw: hexbytes = packed_field("5s")
    experience: B5_Descriptor = virt_field(B5_Descriptor())
    _padding8: hexbytes = padding_field("1s")
    last_level: int = packed_field("B")
    _padding9: hexbytes = padding_field("1s")
    cur_level: int = packed_field("B")
    _padding10: hexbytes = padding_field("1s")
    hitpoints: int = packed_field("H")
    max_hitpoints: int = packed_field("H")

    spells_raw: hexbytes = packed_field("7s")
    _padding11: hexbytes = padding_field("1s")
    mage1_spells: int = packed_field("B")
    _padding12: hexbytes = padding_field("1s")
    mage2_spells: int = packed_field("B")
    _padding13: hexbytes = padding_field("1s")
    mage3_spells: int = packed_field("B")
    _padding14: hexbytes = padding_field("1s")
    mage4_spells: int = packed_field("B")
    _padding15: hexbytes = padding_field("1s")
    mage5_spells: int = packed_field("B")
    _padding16: hexbytes = padding_field("1s")
    mage6_spells: int = packed_field("B")
    _padding17: hexbytes = padding_field("1s")
    mage7_spells: int = packed_field("B")
    _padding18: hexbytes = padding_field("1s")
    priest1_spells: int = packed_field("B")
    _padding19: hexbytes = padding_field("1s")
    priest2_spells: int = packed_field("B")
    _padding20: hexbytes = padding_field("1s")
    priest3_spells: int = packed_field("B")
    _padding21: hexbytes = padding_field("1s")
    priest4_spells: int = packed_field("B")
    _padding22: hexbytes = padding_field("1s")
    priest5_spells: int = packed_field("B")
    _padding23: hexbytes = padding_field("1s")
    priest6_spells: int = packed_field("B")
    _padding24: hexbytes = padding_field("1s")
    priest7_spells: int = packed_field("B")
    _padding25: hexbytes = padding_field("1s")

    last_ac: int = packed_field("H")
    cur_ac: int = packed_field("H")
    _padding26: hexbytes = padding_field("4s")
    items_effects_raw: hexbytes = packed_field("10s")
    _padding27: hexbytes = padding_field("14s")
    honors_raw: hexbytes = packed_field("2s")

    # binary packing

    @staticmethod
    def unpack(data):
        return Character(*struct.unpack(FORMAT, data))

    def pack(self):
        packed_mask = [f.init for f in dataclasses.fields(self)]
        packed_fields = itertools.compress(dataclasses.astuple(self), packed_mask)
        return struct.pack(FORMAT, *packed_fields)


# --- Save file handling ---


def find_base(data, name):
    tag = struct.pack(f"{len(name) + 1}p", bytes(name.upper(), "ASCII"))
    base = data.find(tag)
    if base == -1:
        raise ValueError(f"character {name.upper()} not found")
    else:
        return base


def get_character(data, name):
    base = find_base(data, name)
    return data[base : base + CHAR_LEN]


def put_character(data, name, char):
    base = find_base(data, name)
    data[base : base + CHAR_LEN] = char


# --- Click CLI ---

wrap_exceptions = True
"""Wrap everything in user friendly ClickExceptions"""


@contextlib.contextmanager
def handle_exceptions():
    if wrap_exceptions:
        try:
            yield
        except click.ClickException:
            raise
        except ValueError as ex:
            raise click.BadParameter(str(ex)) from ex
        except Exception as ex:
            raise click.ClickException(str(ex)) from ex
    else:
        yield


@click.group()
@click.version_option(version=VERSION)
@click.option("--debug", is_flag=True, help="Show technical details.", envvar="DEBUG")
def main(debug=False):
    global wrap_exceptions
    if debug:
        wrap_exceptions = False
        for f in dataclasses.fields(Character):
            f.repr = True


@main.command()
@click.argument("file", type=click.File("rb"))
@click.argument("name")
@handle_exceptions()
def show(file, name):
    """Show attributes of character NAME in FILE

    Example (CLI):

    wizfix show SAVE1.dsk jeanne
    """
    with mmap.mmap(file.fileno(), 0, prot=mmap.PROT_READ) as mm:
        char = Character.unpack(get_character(mm, name))
        click.echo(pprint.pprint(char))


@main.command()
@click.argument("file", type=click.File("r+b"))
@click.argument("name")
@click.argument("tasks", nargs=-1)
@handle_exceptions()
def edit(file, name, tasks):
    """Edit attributes of character NAME in FILE

    Multiple tasks can be given.
    Each task must be of the form ATTRIBUTE=VALUE, where VALUE has to be a valid
    Python expression fitting a character attribute seen with the "show" command.
    Access to the Character object is possible via "self" for complex expressions,
    and you can increase or decrease numbers by using += or -= instead
    of plain assignment with =.

    In most cases assigning simple numbers are fine,
    but strings need to be quoted, probably with shell escapes or quotes too.
    Binary ASCII encoding of Python strings is done automaticly.

    The fields of type "hexbytes" can be set through ordinary bytes literals (b"..."),
    other bytes constructions, or little endian integer literals in decimal or hex
    base (0x....).

    Note that in several cases character attributes can be accessed
    (both read and written) through either *_raw or cooked attribute names.

    Examples (CLI):

    wizfix edit SAVE1.dsk.bak3 jeanne gold=10000 iq=10 luck+=1

    wizfix edit SAVE1.dsk.bak3 jeanne 'password="secret"' 'alignment="evil"'

    wizfix edit SAVE1.dsk.bak3 jeanne 'spells_raw=b"\\xfe\\xff\\xff\\xff\\xff\\xff\\x07"'
    wizfix edit SAVE1.dsk.bak3 jeanne spells_raw=0xfeffffffffff07
    """

    def handle_task(char, task):
        if "=" not in task:
            raise ValueError(f"task {repr(task)}")
        attr, valstr = task.split("=", 1)
        match attr[-1]:
            case "+":
                op = operator.add
                attr = attr[:-1]
            case "-":
                op = operator.sub
                attr = attr[:-1]
            case _:
                op = lambda v, x: x
        if not hasattr(char, attr):
            raise ValueError(f"character attribute {attr}")
        try:
            val = eval(valstr, globals={"self": char})
            if isinstance(val, str):
                val = bytes(val, "ASCII")
            val = op(getattr(char, attr), val)
            setattr(char, attr, val)
        except ValueError:
            raise
        except Exception as ex:
            raise ValueError(f"{repr(task)} ({ex.args[0]})") from ex

    with mmap.mmap(file.fileno(), 0) as mm:
        char = Character.unpack(get_character(mm, name))
        for task in tasks:
            handle_task(char, task)
        put_character(mm, name, char.pack())


if __name__ == "__main__":
    main()
