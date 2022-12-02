FROM python:3.9

ADD . /pretty-cool-events
COPY entry.sh /usr/bin/entry.sh
WORKDIR /pretty-cool-events

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt


ENTRYPOINT [ "/bin/bash" , "/usr/bin/entry.sh", "/config/config.yaml" ]
