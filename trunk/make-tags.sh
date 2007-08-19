#!/bin/sh
TAGS=exctags
LIBS=/opt/local/lib/python2.3/site-packages

$TAGS --exclude=build --langmap=python:+.ptl -R
$TAGS --append --exclude=qon -R $LIBS
