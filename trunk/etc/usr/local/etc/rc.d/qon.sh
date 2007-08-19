#!/bin/sh

case "$1" in
start)
        [ -x /www/bin/site ] && /www/bin/site start > /dev/null && echo -n ' qon'
        ;;
stop)
        [ -r /www/var/qon-scgi.pid ] && /www/bin/site stop > /dev/null && echo -n ' qon'
        ;;
*)
        echo "Usage: ${0##*/} { start | stop }" >&2
        exit 64
        ;;
esac
