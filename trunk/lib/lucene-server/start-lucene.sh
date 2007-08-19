#!/bin/sh
java -classpath lucene-1.4-rc3.jar:xmlrpc-1.2-b1.jar:.:/www/bin/lucene/lucene-1.4-rc3.jar:/www/bin/lucene/xmlrpc-1.2-b1.jar:/www/bin/lucene Server 3888 /www/var/qon_lucene /www/log/qon/lucene &
