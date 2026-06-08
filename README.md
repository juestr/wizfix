# wizfix.py

Simple Wizardry 1-3 CLI character editor for SAVE<X>.DSK files.
No warranties, make a backup first.

# Installation

It's a self contained Python [uv](https://docs.astral.sh/uv/) script.
Just make wizfix.py executable and move it somewhere convenient,
no further installation is needed as long as you have uv installed. E.g.:

    cp wizfix.py ~/.local/bin
    chmod 755 ~/.local/bin/wizfix.py

It's only external dependency is
[Click](https://click.palletsprojects.com/en/stable/)
if for some reason you don't have uv.

# Features

    $ wizfix --help
    Usage: wizfix.py [OPTIONS] COMMAND [ARGS]...

    Options:
    --version           Show the version and exit.
    --debug             Show technical details (exceptions).
    --json              Format output in json.
    --raw               Show *_raw fields.
    --padding           Show padding fields.
    --wizardry [1|2|3]  Wizardry number (for items DB).
    --help              Show this message and exit.

    Commands:
    edit   Edit attributes of character NAME in FILE
    shell  Edit attributes of character NAME in FILE in a REPL
    show   Show attributes of character NAME in FILE
    table  Show one of the built in identifier tables

    Options can also be set by WIZFIX_* environment variables.


It's a rather minimal CLI editor. Exp, gold, stats, character names and passwords
are easy to fix. Items and spells require a bit more knowledge of the binary layout,
which was taken from
[here](https://www.zimlab.com/wizardry/recovered/wizardrygame/pages/w1/cheat.htm
).

# Example

    $ wizfix.py show SAVE1.DSK pots
                   name: 'POTS'
               password: ''
                    out: False
                   race: 'DWARF'
                    cls: 'LORD'
                    age: 25
                   life: 0
              alignment: 'GOOD'
               strength: 18
                     iq: 7
                  piety: 14
               vitality: 18
                agility: 18
                   luck: 9
                   gold: 169935
                n_items: 6
         item1_equipped: True
       item1_identified: True
                  item1: 'JEWELD AMULET'
         item2_equipped: True
       item2_identified: True
                  item2: 'SHIELD + 1'
         item3_equipped: True
       item3_identified: True
                  item3: 'LORDS GARB'
         item4_equipped: True
       item4_identified: True
                  item4: 'COPPER GLOVES'
         item5_equipped: True
       item5_identified: True
                  item5: "BLADE CUSINART'"
         item6_equipped: True
       item6_identified: True
                  item6: 'HELM + 1'
         item7_equipped: False
       item7_identified: False
                  item7: None
         item8_equipped: False
       item8_identified: False
                  item8: None
             experience: 1147528
             last_level: 14
              cur_level: 13
              hitpoints: 124
          max_hitpoints: 124
            mage_spells: ''
          priest_spells: 'KALKI,DIOS,BADIOS,MILWA,PORFIC,MATU,CALFO,MANIFO,MONTINO,LOMILWA,DIALKO,LATUMAPIC,BAMATU,DIAL,BADIAL,LATUMOFIS,MAPORFIC,DIALMA,BADIALMA,LITOKAN,KANDI,DI,BADI,LORTO,MADI,MABADI,LOKTOFEIT,MALIKTO'
           mage1_spells: 0
           mage2_spells: 0
           mage3_spells: 0
           mage4_spells: 0
           mage5_spells: 0
           mage6_spells: 0
           mage7_spells: 0
         priest1_spells: 7
         priest2_spells: 8
         priest3_spells: 4
         priest4_spells: 3
         priest5_spells: 6
         priest6_spells: 4
         priest7_spells: 2
                last_ac: 15
                 cur_ac: 65529
