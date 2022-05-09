from pathlib import Path

import large_image
import streamlit as st
import tifftools
from appdirs import user_data_dir

import tiff_to_uml

st.set_page_config(page_title="Tiff Internals")

"""
# Tiff Internals

[![Kitware](https://img.shields.io/badge/Made%20by-Kitware-blue)](https://www.kitware.com/)

Extract information from the internal Image File Directories (IFDs) of a Tiff.
"""


def upload_file_to_path(uploaded_file):
    path = Path(user_data_dir("tifftools"), uploaded_file.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(uploaded_file.getvalue())
    return str(path.absolute())


uploaded_file = st.file_uploader("Upload a Tiff")

if uploaded_file:
    with st.spinner("Gathering internal data..."):
        path = upload_file_to_path(uploaded_file)
        source = large_image.open(path, encoding="PNG")

        yaml = tiff_to_uml.generate_yaml(tiff_to_uml.parse_args([str(path)]))

        raw = tifftools.read_tiff(str(path))

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
            with st.expander("Internal Metadata"):
                st.json(source.getInternalMetadata())
            with st.expander("Full tifftools dump (formatted)"):
                st.json(yaml)
            with st.expander("Full tifftools dump (raw)"):
                st.json(raw)

        # Body
        ifds = yaml[str(path)]["ifds"]
        # st.json(ifds)
        n = len(ifds)

        # with st.center():
        st.metric("N Directories", n)

        metrics = [
            "ImageWidth",
            "ImageLength",
        ]  # "TileWidth", "TileLength"]

        keys = list(ifds.keys())
        for j in range(n // 3):
            level = keys[j * 3:][:3]
            cols = st.columns(3)
            for i, key in enumerate(level):
                key = f"Directory {j*3 + i}"
                with cols[i]:
                    st.subheader(key)
                    thumb_data = tiff_to_uml.get_thumbnail(raw["ifds"][j * 3 + i], 1)
                    st.image(thumb_data, width=200)
                    st.download_button(
                        "Download IFD as PNG",
                        thumb_data,
                        file_name=f"{key}.png",
                        mime="image/png",
                    )
                    for m in metrics:
                        st.metric(m, ifds[key][m])
                    with st.expander("JSON"):
                        st.json(ifds[key])
