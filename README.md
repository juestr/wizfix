# wizfix.py

Simple Wizardry 1-3 CLI character editor. No warranties, make a backup first.

# Installation

It's a self contained Python [uv](https://docs.astral.sh/uv/) script.
Just make wizfix.py executable and move it somewhere convenient,
no further installation is needed as long as you have uv. E.g.:

    cp wizfix.py ~/.local/bin
    chmod 755 ~/.local/bin/wizfix.py

It's only external dependency is
[Click](https://click.palletsprojects.com/en/stable/)
if for some reason you don't have uv.

# Features

Run wizfix.py --help

It's a rather minimal CLI editor. Exp, gold, stats, character names and passwords
are easy to fix. Items and spells require a bit more knowledge. The binary layout
description was taken from
[here](https://www.zimlab.com/wizardry/recovered/wizardrygame/pages/w1/cheat.htm
).

# Example

    > wizfix.py show SAVE1.DSK fang
    Character(name=b'FANG',
              password=b'',
              out=0,
              race=1,
              cls=2,
              age_raw=hexbytes(af 04),
              life=0,
              alignment=1,
              stats=hexbytes(e9 3c 52 36),
              gold_raw=hexbytes(8d 13 0c 00 00),
              n_items=6,
              item1_raw=hexbytes(01 00 00 00 01 00 19 00),
              item2_raw=hexbytes(01 00 00 00 01 00 41 00),
              item3_raw=hexbytes(01 00 00 00 01 00 39 00),
              item4_raw=hexbytes(00 00 00 00 01 00 3c 00),
              item5_raw=hexbytes(00 00 00 00 01 00 58 00),
              item6_raw=hexbytes(01 00 00 00 01 00 32 00),
              item7_raw=hexbytes(00 00 00 00 01 00 58 00),
              item8_raw=hexbytes(00 00 00 00 01 00 58 00),
              experience_raw=hexbytes(18 21 1f 00 00),
              last_level=14,
              cur_level=12,
              hitpoints=132,
              max_hitpoints=132,
              spells_raw=hexbytes(00 00 c0 ff ff 7f 01),
              mage1_spells=0,
              mage2_spells=0,
              mage3_spells=0,
              mage4_spells=0,
              mage5_spells=0,
              mage6_spells=0,
              mage7_spells=0,
              priest1_spells=9,
              priest2_spells=9,
              priest3_spells=8,
              priest4_spells=6,
              priest5_spells=6,
              priest6_spells=3,
              priest7_spells=0,
              last_ac=9,
              cur_ac=65535,
              items_effects_raw=hexbytes(02 00 01 00 08 00 00 00 00 10),
              honors_raw=hexbytes(00 00),
              age=23,
              gold=125005,
              experience=318472,
              strength=9,
              iq=7,
              piety=15,
              vitality=18,
              agility=18,
              luck=13,
              item1='0x1900',
              item2='0x4100',
              item3='0x3900',
              item4='0x3c00',
              item5='0x5800',
              item6='0x3200',
              item7='<empty>',
              item8='<empty>')
    > wizfix.py edit SAVE1.DSK fang iq=12 gold+=10000
