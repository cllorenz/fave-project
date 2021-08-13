/**
 * Define a grammar called ip6tables
 */
grammar ip6tables;


entry :         (SPACE? ip6tables? NL)+ EOF;

ip6tables :     IP6TABLES (SPACE command_t)? SPACE command;
//junk :          (command_t | command | command_A | command_P |
//                jump | target | table | rule_spec | arg | negation | identifier
//                value | TARGET | TABLE | JUMP | ARGTYPE_t | ARGTYPE_A |
//                ARGTYPE_P | DASHEDWORD | WORD | NUM | SLASH | DASH |
//                SPACE | EXCLAMATION | OTHER)*;


command_t :     ARGTYPE_t SPACE table;

command :       command_A | command_P; //| command_I | command_FLZ | command_X;

command_A :     ARGTYPE_A SPACE identifier SPACE rule_spec;
//command_I :        ARGTYPE_I (SPACE NUM)? SPACE rule_spec;
//command_FLZ :    (ARGTYPE_F | ARGTYPE_L | ARGTYPE_Z)
//                (SPACE identifier (SPACE NUM)?)? (SPACE rule_spec)?;
//command_X :        ARGTYPE_X (SPACE identifier)?;
command_P :     ARGTYPE_P SPACE identifier SPACE target;

jump :          JUMP SPACE target;
target :        TARGET;
table :         TABLE;
rule_spec :     arg (SPACE arg)* SPACE jump;

arg :           negation? DASH (DASH)? identifier SPACE value;

negation :      EXCLAMATION SPACE;

identifier :    WORD | DASHEDWORD;
value :         NUM | WORD | NUM SLASH WORD | DASHEDWORD;

IP6TABLES :     'ip6tables';

TARGET :        'ACCEPT' | 'DROP';
TABLE :         'filter' | 'nat' | 'mangle' | 'raw' | 'security';

JUMP :          '-j' | '--jump';

ARGTYPE_t :     '-t' | '--table';
ARGTYPE_A :     '-A' | '--append';
//ARGTYPE_D :     '-D' | '--delete';
//ARGTYPE_C :     '-C' | '--check';
//ARGTYPE_I :     '-I' | '--insert';
//ARGTYPE_R :     '-R' | '--replace';
//ARGTYPE_S :     '-S' | '--list-rules';
//ARGTYPE_L :     '-L' | '--list';
//ARGTYPE_F :     '-F' | '--flush';
//ARGTYPE_Z :     '-Z' | '--zero';
//ARGTYPE_N :     '-N' | '--new-chain';
//ARGTYPE_X :     '-X' | '--delete-chain';
ARGTYPE_P :     '-P' | '--policy';
//ARGTYPE_E :     '-E' | '--rename-chain';

DASHEDWORD :    [a-zA-Z] ([a-zA-Z] | [0-9])* ('-' ([a-zA-Z] | [0-9])+)+;
WORD :          [a-zA-Z] ([a-zA-Z] | [0-9])*;
NUM :           [0-9]+;

SLASH :         '/';
NL :            [\r\n];
DASH :          '-';
SPACE :         [ \t]+;
EXCLAMATION :   '!';
OTHER :         .;

