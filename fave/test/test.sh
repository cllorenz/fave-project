#!/usr/bin/env sh

export CLASSPATH=".:/usr/local/lib/antlr-4.7-complete.jar:$CLASSPATH"

java -Xmx500M -cp "/usr/local/lib/antlr-4.7-complexe.jar:$CLASSPATH" org.antlr.v4.Tool -atn -Dlanguage=Python2 ip6tables.g4

sed s/ip6tablesLexer/IP6TablesLexer/g ip6tablesLexer.py > ip6tables_lexer.py
sed s/ip6tablesListener/IP6TablesListener/g ip6tablesListener.py > ip6tables_listener.py
sed s/ip6tablesParser/IP6TablesParser/g ip6tablesParser.py > ip6tables_parser.py

rm ip6tablesLexer.tokens
rm ip6tablesLexer.py ip6tablesListener.py ip6tablesParser.py

ATN=atn
mkdir -p $ATN
for f in `ls *.dot`; do
    dot -Tpdf $f -o $ATN/$f.pdf
done
mv *.dot $ATN

python2 test.py
#PYTHONPATH=/usr/local/lib/python2.7/dist-packages pypy test.py
