#!/bin/sh
kill -9 `ps ax | grep lucene | grep -v grep | awk '{print $1}'`
