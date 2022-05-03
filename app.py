import os
from pathlib import Path

import large_image
import streamlit as st
from appdirs import user_data_dir

import tiff_to_uml

st.set_page_config(page_title="Tiff to UML")

"""
# Tiff to UML

[![Kitware](https://img.shields.io/badge/Made%20by-Kitware-blue)](https://www.kitware.com/)

Depict the internal structure of a Tiff image as an UML diagram by grpahing
the internal Image File Directories (IFDs).
"""



def upload_file_to_path(uploaded_file):
    path = Path(user_data_dir("tifftools"), uploaded_file.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return str(path.absolute())


uploaded_file = st.file_uploader("Upload a Tiff")

if uploaded_file:
    path = upload_file_to_path(uploaded_file)
    source = large_image.open(path, encoding="PNG")

    with st.sidebar:
        thumb_data, _ = source.getThumbnail(encoding="PNG", width=256, height=256)
        st.image(thumb_data)
        st.write("Metadata")
        st.json(source.getMetadata())

    uml_path = Path(user_data_dir("tifftools"), f"{os.path.basename(path)}-diagram.svg")
    uml_path.parent.mkdir(parents=True, exist_ok=True)

    arguments = ["--dest", str(uml_path), str(path)]
    tiff_to_uml.generate_uml(tiff_to_uml.parse_args(arguments))

    with open(uml_path, 'rb') as f:
        st.download_button('Download Graph', f.read(), file_name='uml.svg', mime='image/svg+xml')

    st.image(str(uml_path), use_column_width=True, width=None)
