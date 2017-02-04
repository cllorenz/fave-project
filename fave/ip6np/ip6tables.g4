/**
 * Define a grammar called Ip6tables
 */
grammar ip6tables;


entry :			(SPACE? (ip6tables | junk) NL+)* (ip6tables | junk);
ip6tables  :	IP6TABLES (SPACE command_t)? SPACE command;

command_t :		DASH DASH? ARGTYPE_t SPACE table;
command :		command_A | command_C | command_D | command_I | command_R | command_L |
				command_F | command_Z | command_N | command_X | command_P | command_E;
command_A :		DASH DASH? ARGTYPE_A SPACE chain (SPACE rule_spec)+;
command_D :		DASH DASH? ARGTYPE_D SPACE chain (SPACE rule_spec)+ |
				DASH DASH? ARGTYPE_D SPACE chain SPACE rulenum (SPACE rule_spec)*;
command_C :		DASH DASH? ARGTYPE_C SPACE chain (SPACE rule_spec)+;
command_I :		DASH DASH? ARGTYPE_I SPACE chain (SPACE rulenum)? (SPACE rule_spec)+;
command_R :		DASH DASH? ARGTYPE_R SPACE chain SPACE rulenum (SPACE rule_spec)+;
command_S :		DASH DASH? ARGTYPE_S (SPACE chain (SPACE rulenum)?)?;
command_L :		DASH DASH? ARGTYPE_L (SPACE chain (SPACE rulenum)?)? (SPACE rule_spec)*;
command_F :		DASH DASH? ARGTYPE_F (SPACE chain (SPACE rulenum)?)? (SPACE rule_spec)*;
command_Z :		DASH DASH? ARGTYPE_Z (SPACE chain (SPACE rulenum)?)? (SPACE rule_spec)*;
command_N :		DASH DASH? ARGTYPE_N SPACE chain;
command_X :		DASH DASH? ARGTYPE_X (SPACE chain)?;
command_P :		DASH DASH? ARGTYPE_P SPACE chain SPACE target (SPACE rule_spec)*;
command_E : 	DASH DASH? ARGTYPE_E SPACE chain SPACE chain;

target :		TARGET;
table :			TABLE;
chain :			(ALPHA | NUMBER | OTHER | ARGTYPE_t | ARGTYPE_A | ARGTYPE_D | 
				ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | ARGTYPE_L | ARGTYPE_F | 
				ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | ARGTYPE_E | IP6TABLES | 
				TARGET | TABLE
				) 
				(ALPHA | NUMBER | DASH  | OTHER | ARGTYPE_t | ARGTYPE_A | ARGTYPE_D | 
				ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | ARGTYPE_L | ARGTYPE_F |  
				ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | ARGTYPE_E | IP6TABLES | 
				TARGET | TABLE
				)*;
rulenum :		NUMBER+;
rule_spec :		argtype (SPACE arg)*;

junk :			(OTHER | SPACE | ALPHA | NUMBER | DASH | EXCLAMATION | ARGTYPE_t | 
				ARGTYPE_A | ARGTYPE_D | ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | 
				ARGTYPE_L | ARGTYPE_F |  ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | 
				ARGTYPE_E | IP6TABLES | TARGET | TABLE
				)*;
argtype :		(negation)? DASH DASH? 
				(ALPHA | NUMBER  | OTHER | ARGTYPE_t | ARGTYPE_A | ARGTYPE_D | 
				ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | ARGTYPE_L | ARGTYPE_F | 
				ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | ARGTYPE_E | IP6TABLES | 
				TARGET | TABLE
				) 
				(ALPHA | NUMBER | DASH | OTHER | ARGTYPE_t | ARGTYPE_A | ARGTYPE_D | 
				ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | ARGTYPE_L | ARGTYPE_F |
				ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | ARGTYPE_E | IP6TABLES | 
				TARGET | TABLE
				)*;
arg :			(ALPHA | NUMBER | OTHER | ARGTYPE_t | ARGTYPE_A | ARGTYPE_D | 
				ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | ARGTYPE_L | ARGTYPE_F | 
				ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | ARGTYPE_E | IP6TABLES | 
				TARGET | TABLE
				) 
				(ALPHA | NUMBER | OTHER | DASH | ARGTYPE_t | ARGTYPE_A | ARGTYPE_D | 
				ARGTYPE_C | ARGTYPE_I | ARGTYPE_R | ARGTYPE_S | ARGTYPE_L | ARGTYPE_F | 
				ARGTYPE_Z | ARGTYPE_N | ARGTYPE_X | ARGTYPE_P | ARGTYPE_E | IP6TABLES | 
				TARGET | TABLE
				)*;
negation :		EXCLAMATION SPACE;

IP6TABLES :		'ip6tables';

TARGET : 		'ACCEPT' | 'DROP' | 'QUEUE' | 'RETURN';
TABLE :			'filter' | 'nat' | 'mangle' | 'raw' | 'security';

ARGTYPE_t :		't' | 'table';
ARGTYPE_A :		'A' | 'append';
ARGTYPE_D :		'D' | 'delete';
ARGTYPE_C :		'C' | 'check';
ARGTYPE_I :		'I' | 'insert';
ARGTYPE_R :		'R' | 'replace';
ARGTYPE_S :		'S' | 'list-rules';
ARGTYPE_L :		'L' | 'list';
ARGTYPE_F :		'F' | 'flush';
ARGTYPE_Z :		'Z' | 'zero';
ARGTYPE_N :		'N' | 'new-chain';
ARGTYPE_X :		'X' | 'delete-chain';
ARGTYPE_P :		'P' | 'policy';
ARGTYPE_E :		'E' | 'rename-chain';

NL :			[\r\n];
ALPHA :			[a-zA-Z];
NUMBER :		[0-9];
DASH :			'-';
SPACE :			[ \t]+;
EXCLAMATION : 	'!';
OTHER :			.;








