FROM ghcr.io/girder/large_image:latest

RUN apt-get update && \
    apt-get install -y \
    curl \
    optipng \
    plantuml \
    && \
    curl -LJ https://github.com/plantuml/plantuml/releases/download/v1.2022.4/plantuml-1.2022.4.jar -o /usr/share/plantuml/plantuml.jar

COPY . $PWD

ENTRYPOINT ["python", "-u", "./cli_list.py"]
