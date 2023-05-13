FROM python:3.9.16-alpine

WORKDIR /usr/app

COPY ./requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY ./entrypoint.sh /entrypoint.sh
ENTRYPOINT [ "/bin/sh", "/entrypoint.sh" ]
