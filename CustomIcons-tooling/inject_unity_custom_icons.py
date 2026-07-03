import argparse
import base64
import io
import zipfile
from pathlib import Path

from PIL import Image


DEFAULT_ICONS_DIR = Path(__file__).resolve().with_name("icons")


ICON_FILES = {
    "adapter": "adapter.png",
    "world": "world.png",
    "relatives": "relatives.png",
    "system": "system.png",
    "pool": "pool.png",
    "filesystem": "filesystem.png",
    "storage_resource": "storage_resource.png",
    "host_lun": "host_lun.png",
    "dae": "dae.png",
    "dpe": "dpe.png",
    "disk": "disk.png",
    "host": "host.png",
    "storage_processor": "storage_processor.png",
    "ethernet_port": "ethernet_port.png",
    "fc_port": "fc_port.png",
    "file_interface": "file_interface.png",
    "nas_server": "nas_server.png",
    "replication_session": "replication_session.png",
}


TARGET_SUFFIX_MAP = {
    "_management_pack.png": ("adapter", "png"),
    "_management_pack_world.png": ("world", "png"),
    "_management_pack_relatives.png": ("relatives", "png"),
    "_unity_system.png": ("system", "png"),
    "_unity_system.svg": ("system", "svg"),
    "_unity_pool.png": ("pool", "png"),
    "_unity_filesystem.png": ("filesystem", "png"),
    "_unity_storage_resource.png": ("storage_resource", "png"),
    "_unity_host_lun.png": ("host_lun", "png"),
    "_unity_dae.png": ("dae", "png"),
    "_unity_dpe.png": ("dpe", "png"),
    "_unity_dpe.svg": ("dpe", "svg"),
    "_unity_disk.png": ("disk", "png"),
    "_unity_host.png": ("host", "png"),
    "_unity_storage_processor.png": ("storage_processor", "png"),
    "_unity_ethernet_port.png": ("ethernet_port", "png"),
    "_unity_fc_port.png": ("fc_port", "png"),
    "_unity_file_interface.png": ("file_interface", "png"),
    "_unity_nas_server.png": ("nas_server", "png"),
    "_unity_replication_session.png": ("replication_session", "png"),
}


def png_as_svg(png_bytes):
    with Image.open(io.BytesIO(png_bytes)) as img:
        width, height = img.size
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<image href="data:image/png;base64,{encoded}" width="{width}" height="{height}"/>'
        "</svg>"
    ).encode("utf-8")


def default_output_path(pak_path):
    stem = pak_path.stem
    if stem.endswith("_icons"):
        stem = stem[:-6]
    return pak_path.with_name(f"{stem}_icons{pak_path.suffix}")


def load_icon_assets(icons_dir):
    missing = [filename for filename in ICON_FILES.values() if not (icons_dir / filename).exists()]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise FileNotFoundError(f"Missing icon files in {icons_dir}: {missing_list}")

    return {
        key: (icons_dir / filename).read_bytes()
        for key, filename in ICON_FILES.items()
    }


def replace_inner_adapter_images(inner_zip_bytes, icon_assets):
    source = zipfile.ZipFile(io.BytesIO(inner_zip_bytes))
    output_buffer = io.BytesIO()
    replacements = []

    with zipfile.ZipFile(output_buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)

            if "/conf/images/AdapterKind/" in info.filename and info.filename.endswith(".png"):
                data = icon_assets["adapter"]
                replacements.append(info.filename)
            elif "/conf/images/ResourceKind/" in info.filename:
                for suffix, (asset_key, target_type) in TARGET_SUFFIX_MAP.items():
                    if info.filename.endswith(suffix):
                        raw_png = icon_assets[asset_key]
                        data = raw_png if target_type == "png" else png_as_svg(raw_png)
                        replacements.append(info.filename)
                        break

            new_info = zipfile.ZipInfo(info.filename)
            new_info.date_time = info.date_time
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.comment = info.comment
            new_info.extra = info.extra
            new_info.create_system = info.create_system
            new_info.external_attr = info.external_attr
            target.writestr(new_info, data)

    source.close()
    return output_buffer.getvalue(), replacements


def patch_pak(pak_path, output_path, icons_dir):
    icon_assets = load_icon_assets(icons_dir)
    replacements = []

    with zipfile.ZipFile(pak_path) as pak:
        adapter_entry = next((name for name in pak.namelist() if name.endswith("adapters.zip")), None)
        if not adapter_entry:
            raise RuntimeError(f"No adapters.zip found in {pak_path}")

        patched_inner_zip, inner_replacements = replace_inner_adapter_images(
            pak.read(adapter_entry),
            icon_assets,
        )
        replacements.extend(inner_replacements)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as out_pak:
            for info in pak.infolist():
                data = pak.read(info.filename)
                if info.filename == adapter_entry:
                    data = patched_inner_zip

                new_info = zipfile.ZipInfo(info.filename)
                new_info.date_time = info.date_time
                new_info.compress_type = zipfile.ZIP_DEFLATED
                new_info.comment = info.comment
                new_info.extra = info.extra
                new_info.create_system = info.create_system
                new_info.external_attr = info.external_attr
                out_pak.writestr(new_info, data)

    return replacements


def main():
    parser = argparse.ArgumentParser(
        description="Patch a Unity MP Builder PAK with local custom resource images without changing MP Builder metadata."
    )
    parser.add_argument("pak", help="Path to the MP Builder-generated PAK file.")
    parser.add_argument(
        "--icons-dir",
        default=str(DEFAULT_ICONS_DIR),
        help="Directory that contains the icon PNG files. Defaults to ./icons beside this script.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output path. Defaults to '<input>_icons.pak'.",
    )
    args = parser.parse_args()

    pak_path = Path(args.pak)
    if not pak_path.exists():
        raise FileNotFoundError(f"PAK not found: {pak_path}")

    icons_dir = Path(args.icons_dir)
    if not icons_dir.exists():
        raise FileNotFoundError(f"Icons directory not found: {icons_dir}")

    output_path = Path(args.output) if args.output else default_output_path(pak_path)
    replacements = patch_pak(pak_path, output_path, icons_dir)

    print(f"Wrote {output_path}")
    print(f"Loaded icons from {icons_dir}")
    print("Preserved original MP Builder metadata and package version")
    print(f"Replaced {len(replacements)} image entries")
    for name in replacements:
        print(f"  {name}")


if __name__ == "__main__":
    main()
