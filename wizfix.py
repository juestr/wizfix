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
import functools
import itertools
import json
import math
import mmap
import operator
import pprint
import struct

import click

VERSION = "0.3"


# --- Game Data ---


def _table(labels, start=0):
    return {k: v for k, v in enumerate(labels, start) if v is not None}


RACES = _table(["HUMAN", "ELF", "DWARF", "GNOME", "HOBBIT"], start=1)
CLASSES = _table(
    ["FIGHTER", "MAGE", "PRIEST", "THIEF", "BISHOP", "SAMURAI", "LORD", "NINJA"]
)
ALIGNMENTS = _table(["GOOD", "NEUTRAL", "EVIL"], start=1)
MAGE_SPELLS = _table(
    [
        "HALITO",
        "MOGREF",
        "KATINO",
        "DUMAPIC",
        "DILTO",
        "SOPIC",
        "MAHALITO",
        "MOLITO",
        "MORLIS",
        "DALTO",
        "LAHALITO",
        "MAMORLIS",
        "MAKANITO",
        "MADALTO",
        "LAKANITO",
        "ZILWAN",
        "MASOPIC",
        "HAMAN",
        "MALOR",
        "MAHAMAN",
        "TILTOWAIT",
    ],
    start=1,
)
PRIEST_SPELLS = _table(
    [
        "KALKI",
        "DIOS",
        "BADIOS",
        "MILWA",
        "PORFIC",
        "MATU",
        "CALFO",
        "MANIFO",
        "MONTINO",
        "LOMILWA",
        None,
        "DIALKO",
        "LATUMAPIC",
        "BAMATU",
        "DIAL",
        "BADIAL",
        "LATUMOFIS",
        "MAPORFIC",
        "DIALMA",
        "BADIALMA",
        "LITOKAN",
        "KANDI",
        "DI",
        "BADI",
        "LORTO",
        "MADI",
        "MABADI",
        "LOKTOFEIT",
        "MALIKTO",
        "KADORTO",
    ],
    start=22,
)
ITEMS_W1 = _table(
    [
        "LONG SWORD",
        "SHORT SWORD",
        "ANOINTED MACE",
        "ANOINTED FLAIL",
        "STAFF",
        "DAGGER",
        "SMALL SHIELD",
        "LARGE SHIELD",
        "ROBES",
        "LEATHER ARMOR",
        "CHAIN MAIL",
        "BREAST PLATE",
        "PLATE MAIL",
        "HELM",
        "DIOS POTION",
        "LATUMOFIS POTION",
        "LONG SWORD + 1",
        "SHORT SWORD + 1",
        "MACE + 1",
        "STAFF OF MOGREF",
        "SCROLL/KATINO",
        "LEATHER ARMOR + 1",
        "CHAIN MAIL + 1",
        "PLATE MAIL + 1",
        "SHIELD + 1",
        "BREAST PLATE + 1",
        "SCROLL/BADIOS",
        "SCROLL/HALITO",
        "LONG SWORD - 1",
        "SHORT SWORD - 1",
        "MACE - 1",
        "STAFF + 2",
        "DRAGON SLAYER",
        "HELM + 1",
        "LEATHER ARMOR - 1",
        "CHAIN MAIL - 1",
        "BREAST PLATE - 1",
        "SHIELD - 1",
        "JEWELD AMULET",
        "SCROLL/BADIOS",
        "POTOIN OF SOPIC",
        "LONG SWORD + 2",
        "SHORT SWORD + 2",
        "MACE + 2",
        "SCROLL/LOMILWA",
        "SCROLL/DILTO",
        "COPPER GLOVES",
        "LEATHER ARMOR + 2",
        "CHAIN MAIL + 2",
        "PLATE MAIL + 2",
        "SHIELD + 2",
        "HELM + 2 (EVIL)",
        "POTION OF DIAL",
        "RING OF PORFIC",
        "WERE SLAYER",
        "MAGE MASHER",
        "MACE PRO POISON",
        "STAFF/MONTINO",
        "BLADE CUSINART'",
        "AMULET/MANIFO",
        "ROD OF FLAME",
        "EVIL CHAIN + 2",
        "NEURTAL PLATE MAIL + 2",
        "EVIL SHIELD + 2",
        "AMULET MAKANITO",
        "DIADEM OF MALOR",
        "SCROLL/BADIAL",
        "SHORT  SWORD - 2",
        "DAGGER + 2",
        "MACE - 2",
        "STAFF - 2",
        "DAGGER OF SPEED",
        "CURSED ROBE",
        "LEATHER ARMOR - 2",
        "CHAIN MAIL - 2",
        "BREAST PLATE - 2",
        "SHIELD - 2",
        "CURSED HELMET",
        "BREAST PLATE + 2",
        "SILVER GLOVES",
        "EVIL SWORD + 3",
        "EVIL SHORT SWORD + 3",
        "THIEVES DAGGER",
        "BREAST PLATE + 3",
        "LORDS GARB",
        "MURASAMA BLADE",
        "SURIKEN",
        "CHAIN PRO FIRE",
        "EVIL PLATE MAIL + 3",
        "SHIELD + 3",
        "RING OF HEALING",
        "RING PRO UNDEAD",
        "DEADLY RING",
        "WERDNA'S AMULET",
        "STATUETTE/BEAR",
        "STATUETTE/FROG",
        "BRONZE KEY",
        "SILVER KEY",
        "GOLD KEY",
        "BLUE RIBBON",
    ],
    start=1,
)

TABLES = {
    "race": RACES,
    "class": CLASSES,
    "alignment": ALIGNMENTS,
    "mage_spells": MAGE_SPELLS,
    "priest_spells": PRIEST_SPELLS,
    "items_w1": ITEMS_W1,
}

# --- Character interface ---

FORMAT = "<"  # built dynamically by packed_field() later
CHAR_LEN = 0  # same


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


class hexbytes(bytes):
    def __repr__(self):
        return f"hexbytes({binascii.hexlify(self, sep=' ').decode('ASCII')})"


class HexBytesDescriptor:
    def __init__(self, fmt):
        self.size = int(fmt[:-1])

    def __set_name__(self, owner, name):
        self._name = "_" + name

    def __get__(self, obj, objtype=None):
        return getattr(obj, self._name)

    def __set__(self, obj, value):
        if isinstance(value, int):
            value = value.to_bytes(self.size)
        setattr(obj, self._name, hexbytes(value))


def _get_bits(x, positions):
    r = 0
    for p in positions:
        r = (r << 1) | ((x >> p) & 0x1)
    return r


class StatsDescriptor:
    def __init__(self, positions):
        self.positions = positions

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        x = int.from_bytes(obj.stats_raw)
        return _get_bits(x, self.positions)

    def __set__(self, obj, value):
        if not 1 <= value <= 18:
            raise ValueError(f"{value} outside range for {self.name}")
        x = int.from_bytes(obj.stats_raw)
        for i, p in enumerate(reversed(self.positions)):
            x ^= (_get_bits(x, (p,)) ^ _get_bits(value, (i,))) << p
        obj.stats_raw = x.to_bytes(4)


class AgeDescriptor:
    def __get__(self, obj, objtype=None):
        return obj.age_raw[0] // 52 + obj.age_raw[1] * 5

    def __set__(self, obj, value):
        b0 = min(255, int(value * 52) % (5 * 52))
        b1 = int(value) // 5
        obj.age_raw = hexbytes([b0, b1])


class FiveBytesDescriptor:
    WEIGHTS = (1, 256, 10_000, 2_560_000, 100_000_000)

    def __set_name__(self, owner, name):
        self.name_raw = name + "_raw"

    def __get__(self, obj, objtype=None):
        xs = getattr(obj, self.name_raw)
        return math.sumprod(xs, self.WEIGHTS)

    def __set__(self, obj, value):
        xs = []
        for w in reversed(self.WEIGHTS):
            xs.append(value // w)
            value %= w
        setattr(obj, self.name_raw, bytes(reversed(xs)))


class TabledDescriptor:
    def __init__(self, table):
        self.table = table

    def __set_name__(self, owner, name):
        self.name_raw = f"{name}_raw"

    def __get__(self, obj, objtype=None):
        v = getattr(obj, self.name_raw)
        return self.table.get(v, "<unknown>")

    def __set__(self, obj, value):
        if isinstance(value, bytes):
            value = value.decode("ASCII")
        value = value.upper()
        if value in self.table.values():
            value = list(self.table.keys())[list(self.table.values()).index(value)]
        else:
            raise ValueError(str(value))
        setattr(obj, self.name_raw, value)


class ItemDescriptor(TabledDescriptor):
    def __init__(self):
        super().__init__(ITEMS_W1)

    def __set_name__(self, owner, name):
        super().__set_name__(owner, name)
        self.n = int(name[-1])
        self.name_equipped = name + "_equipped"
        self.name_identified = name + "_identified"

    def __get__(self, obj, objtype=None):
        if self.n <= obj.n_items:
            return super().__get__(obj, objtype)
        else:
            return None

    def __set__(self, obj, value):
        if value in (0, None, "", b""):
            if self.n < obj.n_items:
                raise ValueError("can only zero out last non empty item slot")
            obj.n_items = min(obj.n_items, self.n - 1)
        else:
            if self.n > obj.n_items + 1:
                raise ValueError("can only assign to first empty item slot")
            super().__set__(obj, value)
            setattr(obj, self.name_equipped, False)
            setattr(obj, self.name_identified, True)
            obj.n_items = max(obj.n_items, self.n)


class SpellsDescriptor:
    def __init__(self, table):
        self.table = table
        self.spell_bits = {spell: 1 << bit for bit, spell in table.items()}
        self.all = sum(self.spell_bits.values())
        self.inv_mask = 0xFFFFFFFFFFFFFF ^ self.all

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        raw_bits = int.from_bytes(obj.spells_raw, byteorder="little")
        return ",".join(
            [spell for bit, spell in self.table.items() if raw_bits & (1 << bit)]
        )

    def __set__(self, obj, value):
        def get_bit(spell_name):
            spell_name = spell_name.strip()
            try:
                return self.spell_bits[spell_name]
            except KeyError as ex:
                raise ValueError(f"invalid {spell_name} in {self.name}") from ex

        if isinstance(value, bytes):
            value = value.decode("ASCII")
        value = value.upper().strip()
        match value:
            case "" | "NONE":
                combined_bits = 0
            case "ALL":
                combined_bits = self.all
            case _:
                combined_bits = functools.reduce(
                    operator.or_, map(get_bit, value.split(","))
                )
        raw_bits = int.from_bytes(obj.spells_raw, byteorder="little")
        raw_bits &= self.inv_mask
        raw_bits |= combined_bits
        obj.spells_raw = raw_bits.to_bytes(7, byteorder="little")


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
    out: bool = packed_field("?")
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
    stats_raw: hexbytes = packed_field("4s")
    strength: StatsDescriptor = virt_field(StatsDescriptor([28, 27, 26, 25, 24]))
    iq: StatsDescriptor = virt_field(StatsDescriptor((17, 16, 31, 30, 29)))
    piety: StatsDescriptor = virt_field(StatsDescriptor((22, 21, 20, 19, 18)))
    vitality: StatsDescriptor = virt_field(StatsDescriptor((12, 11, 10, 9, 8)))
    agility: StatsDescriptor = virt_field(StatsDescriptor((1, 0, 15, 14, 13)))
    luck: StatsDescriptor = virt_field(StatsDescriptor((6, 5, 4, 3, 2)))
    _padding5: hexbytes = padding_field("4s")

    gold_raw: hexbytes = packed_field("5s")
    gold: FiveBytesDescriptor = virt_field(FiveBytesDescriptor())
    _padding6: hexbytes = padding_field("1s")
    n_items: int = packed_field("B")
    _padding7: hexbytes = padding_field("1s")
    item1_equipped: bool = packed_field("?")
    _item1_padding1: hexbytes = padding_field("3s")
    item1_identified: bool = packed_field("?")
    _item1_padding2: hexbytes = padding_field("1s")
    item1_raw: int = packed_field("H")
    item1: TabledDescriptor = virt_field(ItemDescriptor())
    item2_equipped: bool = packed_field("?")
    _item2_padding1: hexbytes = padding_field("3s")
    item2_identified: bool = packed_field("?")
    _item2_padding2: hexbytes = padding_field("1s")
    item2_raw: int = packed_field("H")
    item2: TabledDescriptor = virt_field(ItemDescriptor())
    item3_equipped: bool = packed_field("?")
    _item3_padding1: hexbytes = padding_field("3s")
    item3_identified: bool = packed_field("?")
    _item3_padding2: hexbytes = padding_field("1s")
    item3_raw: int = packed_field("H")
    item3: TabledDescriptor = virt_field(ItemDescriptor())
    item4_equipped: bool = packed_field("?")
    _item4_padding1: hexbytes = padding_field("3s")
    item4_identified: bool = packed_field("?")
    _item4_padding2: hexbytes = padding_field("1s")
    item4_raw: int = packed_field("H")
    item4: TabledDescriptor = virt_field(ItemDescriptor())
    item5_equipped: bool = packed_field("?")
    _item5_padding1: hexbytes = padding_field("3s")
    item5_identified: bool = packed_field("?")
    _item5_padding2: hexbytes = padding_field("1s")
    item5_raw: int = packed_field("H")
    item5: TabledDescriptor = virt_field(ItemDescriptor())
    item6_equipped: bool = packed_field("?")
    _item6_padding1: hexbytes = padding_field("3s")
    item6_identified: bool = packed_field("?")
    _item6_padding2: hexbytes = padding_field("1s")
    item6_raw: int = packed_field("H")
    item6: TabledDescriptor = virt_field(ItemDescriptor())
    item7_equipped: bool = packed_field("?")
    _item7_padding1: hexbytes = padding_field("3s")
    item7_identified: bool = packed_field("?")
    _item7_padding2: hexbytes = padding_field("1s")
    item7_raw: int = packed_field("H")
    item7: TabledDescriptor = virt_field(ItemDescriptor())
    item8_equipped: bool = packed_field("?")
    _item8_padding1: hexbytes = padding_field("3s")
    item8_identified: bool = packed_field("?")
    _item8_padding2: hexbytes = padding_field("1s")
    item8_raw: int = packed_field("H")
    item8: TabledDescriptor = virt_field(ItemDescriptor())

    experience_raw: hexbytes = packed_field("5s")
    experience: FiveBytesDescriptor = virt_field(FiveBytesDescriptor())
    _padding8: hexbytes = padding_field("1s")
    last_level: int = packed_field("B")
    _padding9: hexbytes = padding_field("1s")
    cur_level: int = packed_field("B")
    _padding10: hexbytes = padding_field("1s")
    hitpoints: int = packed_field("H")
    max_hitpoints: int = packed_field("H")

    spells_raw: hexbytes = packed_field("7s")
    mage_spells: SpellsDescriptor = virt_field(SpellsDescriptor(MAGE_SPELLS))
    priest_spells: SpellsDescriptor = virt_field(SpellsDescriptor(PRIEST_SPELLS))
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

    def to_json(self, with_padding=False, indent=2, **flags):
        def conv(obj):
            if isinstance(obj, hexbytes):
                return repr(obj)
            elif isinstance(obj, bytes):
                return obj.decode("ASCII")
            else:
                assert False

        xs = [
            (f.name, v)
            for f, v in zip(dataclasses.fields(self), dataclasses.astuple(self))
            if not f.name.startswith("_") or with_padding
        ]
        return json.dumps(dict(xs), default=conv, indent=indent, **flags)


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

debug_mode = False
output_json = False
show_padding = False


@contextlib.contextmanager
def handle_exceptions():
    if debug_mode:
        yield
    else:
        try:
            yield
        except click.ClickException:
            raise
        except click.Abort:
            raise
        except ValueError as ex:
            raise click.BadParameter(str(ex)) from ex
        except Exception as ex:
            raise click.ClickException(str(ex)) from ex


def show_character(char):
    if output_json:
        click.echo(char.to_json(with_padding=show_padding))
    else:
        click.echo(pprint.pp(char))


def handle_edit_task(char, task):
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


handle_edit_task_wrapped = handle_exceptions()(handle_edit_task)


@click.group()
@click.version_option(version=VERSION)
@click.option(
    "--debug", is_flag=True, help="Show technical details (exceptions).", envvar="DEBUG"
)
@click.option(
    "--json", is_flag=True, help="Format output in json (default: Python pprint)."
)
@click.option("--padding", is_flag=True, help="Show padding bytes.")
def main(debug=False, json=False, padding=False):
    global debug_mode, output_json, show_padding
    debug_mode = debug
    output_json = json
    show_padding = padding
    if show_padding:
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
        show_character(char)


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
    but strings need to be quoted, probably with shell escapes or quotes in
    addition to the Python quotes. See example below.
    Binary ASCII encoding and upper casing of strings is done automatically.

    The fields of type "hexbytes" can be set through ordinary bytes literals (b"..."),
    other bytes constructions, or little endian integer literals in decimal or hex
    base (0x....).

    Note that in several cases character attributes can be accessed
    (both read and written) through either *_raw or cooked attribute names.

    Examples (CLI):

    wizfix edit SAVE1.dsk.bak3 jeanne gold=10000 iq=10 luck+=1

    wizfix edit SAVE1.dsk.bak3 jeanne 'password="secret"' 'alignment="evil"'
    wizfix edit SAVE1.dsk.bak3 jeanne 'item3="long sword + 2"'

    wizfix edit SAVE1.dsk.bak3 jeanne 'spells_raw=b"\\xfe\\xff\\xff\\xff\\xff\\xff\\x07"'
    wizfix edit SAVE1.dsk.bak3 jeanne spells_raw=0xfeffffffffff07
    """

    with mmap.mmap(file.fileno(), 0) as mm:
        char = Character.unpack(get_character(mm, name))
        for task in tasks:
            handle_edit_task(char, task)
        put_character(mm, name, char.pack())


@main.command()
@click.argument("file", type=click.File("r+b"))
@click.argument("name")
@handle_exceptions()
def shell(file, name):
    """Edit attributes of character NAME in FILE in a REPL

    The prompt accepts tasks as the edit command does, one per line.
    """
    with mmap.mmap(file.fileno(), 0) as mm:
        char = Character.unpack(get_character(mm, name))
        show_character(char)
        while ...:
            match click.prompt(
                "<property>=<expression> or (S)ave, (Q)uit",
                default="_",
                show_default=False,
            ):
                case "_":
                    show_character(char)
                case "s" | "S" | "save" | "Save":
                    put_character(mm, name, char.pack())
                    return
                case "q" | "Q" | "quit" | "Quit":
                    raise click.Abort()
                case task:
                    try:
                        handle_edit_task_wrapped(char, task)
                        show_character(char)
                    except click.ClickException as ex:
                        ex.show()


@main.command()
@click.argument("name", type=click.Choice(TABLES.keys()))
@handle_exceptions()
def table(name):
    """Show one of the built in identifier tables"""
    name = name.lower()
    if output_json:
        click.echo(json.dumps(TABLES[name], indent=2))
    else:
        width = 80 if name.startswith("item") else 1
        click.echo(pprint.pp(TABLES[name], width=width))


if __name__ == "__main__":
    main()
