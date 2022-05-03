import argparse
import os
import sys
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


def parse_args(args):
    parser = argparse.ArgumentParser("Data Diagnostics")
    parser.add_argument("-f", "--filename", help="Local path or URL", required=False)
    return parser.parse_args(args)


def upload_file_to_path(uploaded_file):
    path = Path(user_data_dir("tifftools"), uploaded_file.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return str(path.absolute())


uploaded_file = st.file_uploader("Upload a Tiff")
args = parse_args(sys.argv[1:])
arg_path = args.filename


if arg_path:
    if not os.path.exists(arg_path):
        st.error(f"Path does not exist: {arg_path}")
    arg_path = None


if uploaded_file or arg_path:
    with st.spinner("Generating graph..."):
        if uploaded_file:
            path = upload_file_to_path(uploaded_file)
        else:
            path = arg_path
        source = large_image.open(path, encoding="PNG")

        uml_path = Path(
            user_data_dir("tifftools"), f"{os.path.basename(path)}-diagram.svg"
        )
        uml_path.parent.mkdir(parents=True, exist_ok=True)

        arguments = ["--dest", str(uml_path), str(path)]
        args = tiff_to_uml.parse_args(arguments)
        tiff_to_uml.generate_uml(args)
        yaml = tiff_to_uml.generate_yaml(args)

    with st.sidebar:
        thumb_data, _ = source.getThumbnail(encoding="PNG", width=512, height=512)
        st.image(thumb_data)
        st.download_button(
            "Download Thumbnail",
            thumb_data,
            file_name="thumbnail.png",
            mime="image/png",
        )

        with st.expander("Metadata"):
            st.json(source.getMetadata())
        with st.expander("Tifftools Dump"):
            st.json(yaml)

    with open(uml_path, "rb") as f:
        st.download_button(
            "Download Graph", f.read(), file_name="uml.svg", mime="image/svg+xml"
        )

    st.image(str(uml_path), use_column_width=True, width=None)
