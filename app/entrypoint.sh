#!/bin/sh

cd /usr/app

pip3 install .
uvicorn freshdoc.main:app --host "0.0.0.0" --port 8080 --reload
