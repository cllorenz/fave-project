#!/usr/bin/env sh

PID=$1
MODE=$2


case $MODE in
	"pre" )
	FILE="pre.mem.log"
	;;
	"in" )
	FILE="in.mem.log"
	;;
	"post" )
	FILE="post.mem.log"
	;;
esac

ps -o rssize -p $PID | sed 1d >> $FILE
