FROM ghcr.io/girder/large_image:latest

RUN apt-get update && \
    apt-get install -y \
    curl \
    optipng \
    plantuml \
    && \
    curl -LJ https://github.com/plantuml/plantuml/releases/download/v1.2022.4/plantuml-1.2022.4.jar -o /usr/share/plantuml/plantuml.jar

COPY requirements.txt /opt/analyze_tiff/requirements.txt
RUN pip install -r  /opt/analyze_tiff/requirements.txt

COPY app.py /opt/analyze_tiff/
COPY tiff_to_uml.py /opt/analyze_tiff/

EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "/opt/analyze_tiff/app.py"]
