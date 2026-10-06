"""Read one bill from a ZIP using Python and Ubuntu's fcrackzip/unzip."""

import re
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path


def unpack(path, suffix, password=None):
    with zipfile.ZipFile(path) as archive:
        entries = [i for i in archive.infolist() if not i.is_dir()]
        if (
            len(entries) != 1
            or Path(entries[0].filename).suffix.lower() != "." + suffix
        ):
            raise ValueError("expected one bill file")
        entry = entries[0]
        if not 0 < entry.file_size <= 50 * 1024 * 1024:
            raise ValueError("invalid bill size")
        if entry.flag_bits & 1 and not password:
            # Streaming ZIP writers put sizes in the central directory only.
            # fcrackzip needs those sizes in the local header. Keep the encryption
            # flag and encrypted bytes intact; decrypt the original ZIP afterward.
            raw = bytearray(Path(path).read_bytes())
            struct.pack_into(
                "<III",
                raw,
                entry.header_offset + 14,
                entry.CRC,
                entry.compress_size,
                entry.file_size,
            )
            with tempfile.NamedTemporaryFile(suffix=".zip") as copy:
                copy.write(raw)
                copy.flush()
                result = subprocess.run(
                    ["fcrackzip", "-b", "-c", "1", "-l", "6-6", "-u", copy.name],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            match = re.search(r"pw == (\d{6})", result.stdout)
            if not match:
                raise ValueError("six-digit password could not be recovered")
            password = match[1]
        return archive.read(entry, pwd=password.encode() if password else None)
