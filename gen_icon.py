# -*- coding: utf-8 -*-
"""生成 app.ico —— 芯片造型图标(16/32 双尺寸), 纯标准库, 无第三方依赖"""
import os
import struct

BODY = (37, 99, 235, 255)      # 主蓝
HILIGHT = (96, 148, 245, 255)
SHADOW = (28, 72, 180, 255)
PIN = (246, 189, 62, 255)      # 金
WHITE = (255, 255, 255, 255)


def draw(size):
    px = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
    s = size / 32.0

    def rect(x0, y0, x1, y1, color):
        for y in range(max(0, int(round(y0 * s))), min(size, int(round(y1 * s)) + 1)):
            for x in range(max(0, int(round(x0 * s))), min(size, int(round(x1 * s)) + 1)):
                px[y][x] = color

    # 4 边各 3 根引脚
    for t in (11, 15, 19):
        rect(t, 4, t + 1, 8, PIN)
        rect(t, 23, t + 1, 27, PIN)
        rect(4, t, 8, t + 1, PIN)
        rect(23, t, 27, t + 1, PIN)
    # 芯片本体
    rect(8, 8, 23, 23, BODY)
    rect(8, 8, 23, 8, HILIGHT)
    rect(8, 8, 8, 23, HILIGHT)
    rect(8, 23, 23, 23, SHADOW)
    rect(23, 8, 23, 23, SHADOW)
    # 中央标志
    rect(13, 13, 18, 18, WHITE)
    rect(15, 15, 16, 16, BODY)
    return px


def to_bmp(px, size):
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for y in range(size - 1, -1, -1):  # bottom-up
        row = bytearray()
        for x in range(size):
            r, g, b, a = px[y][x]
            row += struct.pack("<BBBB", b, g, r, a)
        rows.append(bytes(row))
    bits = b"".join(rows)
    mask_row = ((size + 31) // 32) * 4
    mask = b"\x00" * (mask_row * size)
    return header + bits + mask


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    images = [(16, draw(16)), (32, draw(32))]
    entries, blobs = b"", b""
    offset = 6 + 16 * len(images)
    for size, px in images:
        blob = to_bmp(px, size)
        entries += struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
                               0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    ico = struct.pack("<HHH", 0, 1, len(images)) + entries + blobs
    out = os.path.join(here, "app.ico")
    with open(out, "wb") as f:
        f.write(ico)
    print(f"已生成 {out} ({len(ico)} bytes, 尺寸: {[s for s, _ in images]})")


if __name__ == "__main__":
    main()
