FROM python:3.9.16-alpine

WORKDIR /usr/app

RUN apk update && apk add git

COPY ./requirements.txt /usr/app/requirements.txt
RUN pip3 install -r requirements.txt

COPY ./app /usr/app
RUN pip3 install /usr/app

ENTRYPOINT [ "uvicorn", "freshdoc.main:app", "--host", "0.0.0.0", "--port", "8080" ]
