#!/usr/bin/env bash

RSPATH="bench/up"

DMZ="file \
mail \
web \
ldap \
vpn \
dns \
data \
adm"

DEFAULT_TARGETS="internet pgf.uni-potsdam.de clients.wifi.uni-potsdam.de"

DMZ_TARGETS=""
for HOST in $DMZ; do
    DMZ_TARGETS="$DMZ_TARGETS $HOST.uni-potsdam.de"
done

SUBNETS="api.uni-potsdam.de \
asta.uni-potsdam.de \
botanischer-garten-potsdam.de \
chem.uni-potsdam.de \
cs.uni-potsdam.de \
geo.uni-potsdam.de \
geographie.uni-potsdam.de \
hgp-potsdam.de \
hpi.uni-potsdam.de \
hssport.uni-potsdam.de \
intern.uni-potsdam.de \
jura.uni-potsdam.de \
ling.uni-potsdam.de \
math.uni-potsdam.de \
mmz-potsdam.de \
physik.uni-potsdam.de \
pogs.uni-potsdam.de \
psych.uni-potsdam.de \
sq-brandenburg.de \
ub.uni-potsdam.de \
welcome-center-potsdam.de"


SUBHOSTS="web \
voip \
mail \
print \
file"

SUB_TARGETS=""
for SUBNET in $SUBNETS; do
    SUB_TARGETS="$SUB_TARGETS clients.$SUBNET"
    for SUBHOST in $SUBHOSTS; do
        SUB_TARGETS="$SUB_TARGETS $SUBHOST.$SUBNET"
    done
done

TARGETS="$DEFAULT_TARGETS$DMZ_TARGETS$SUB_TARGETS"

END_TO_END=""
for SOURCE in $TARGETS; do
    TMP="$SOURCE:"
    for TARGET in $TARGETS; do
        if [ "$SOURCE" == "$TARGET" ]; then
            continue
        fi
        TMP="$TMP,$TARGET"
    done
    END_TO_END="$END_TO_END;$TMP"
done

TMP_FILE=$(mktemp /dev/shm/end_to_end.XXXXXX)
echo $END_TO_END > $TMP_FILE

RULESETS="\
internet:$RSPATH/simple-host-ruleset,\
pgf.uni-potsdam.de:$RSPATH/pgf.uni-potsdam.de-ruleset,\
clients.wifi.uni-potsdam.de:$RSPATH/wifi.uni-potsdam.de-clients-ruleset,\
dmz.uni-potsdam.de:$RSPATH/simple-switch-ruleset\
"

for HOST in $DMZ; do
    RULESETS="$RULESETS,$HOST.uni-potsdam.de:$RSPATH/dmz-$HOST.uni-potsdam.de-ruleset"
done

for SUBNET in $SUBNETS; do
    RULESETS="$RULESETS,$SUBNET:$RSPATH/simple-switch-ruleset"
    RULESETS="$RULESETS,clients.$SUBNET:$RSPATH/$SUBNET-clients-ruleset"
    for SUBHOST in $SUBHOSTS; do
        RULESETS="$RULESETS,$SUBHOST.$SUBNET:$RSPATH/$SUBNET-$SUBHOST-ruleset"
    done
done

export PYTHONPATH=.
python3 $RSPATH/gen_large.py

ANOMALIES="end_to_end"

usage() { echo "usage: $0 [-h] [-a <anomalies>]" 2>&2; }

while getopts "ha:" o; do
    case "${o}" in
        h)
            usage
            exit 0
            ;;
        a)
            ANOMALIES="${OPTARG}"
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

python3 main.py \
    --no-active-interfaces \
    --network bench/up/large.xml \
    --rulesets $RULESETS \
    --end-to-end $TMP_FILE \
    --anomalies $ANOMALIES

rm $TMP_FILE
