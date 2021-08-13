/**
 * Define a grammar called ip6tables
 */
grammar ip6tables;


entry :         (SPACE? ip6tables? NL)+ EOF;

ip6tables :     IP6TABLES (SPACE command_t)? SPACE command;

command_t :     ARGTYPE_t SPACE table;

command :       command_A | command_P;

command_A :     ARGTYPE_A SPACE identifier SPACE rule_spec;
command_P :     ARGTYPE_P SPACE identifier SPACE target;

jump :          JUMP SPACE target;
target :        TARGET;
table :         TABLE;
rule_spec :     arg (SPACE arg)* SPACE jump;

arg :           negation? DASH (DASH)? identifier SPACE value;

negation :      EXCLAMATION SPACE;

identifier :    WORD | DASHEDWORD;
value :         NUM | WORD | NUM SLASH WORD | DASHEDWORD | ADDRESS;

IP6TABLES :     'ip6tables';

TARGET :        'ACCEPT' | 'DROP';
TABLE :         'filter' | 'nat' | 'mangle' | 'raw' | 'security';

JUMP :          '-j' | '--jump';

ARGTYPE_t :     '-t' | '--table';
ARGTYPE_A :     '-A' | '--append';
ARGTYPE_P :     '-P' | '--policy';

DASHEDWORD :    [a-zA-Z] ([a-zA-Z] | [0-9])* ('-' ([a-zA-Z] | [0-9])+)+;

WORD :          [a-zA-Z] ([a-zA-Z] | [0-9])*;
// XXX: very rudimentary
ADDRESS :       ([0-9a-fA-F]*':')+ (':'[0-9a-fA-F]+)?('/'[0-1]?[0-9]?[0-9])?;
NUM :           [0-9]+;

SLASH :         '/';
NL :            [\r\n];
DASH :          '-';
SPACE :         [ \t]+;
EXCLAMATION :   '!';
OTHER :         .;

