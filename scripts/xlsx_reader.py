# -*- coding: utf-8 -*-
"""
xlsx 底层读取工具
=================
直接解析 .xlsx（本质是 zip + XML），不依赖 openpyxl / pandas。

为什么要这么做：源文件《创发第一轮面试打分表.xlsx》由 WPS/Excel 生成，
其 styles.xml 里有一个不带 patternType 的 fill 节点，会导致 openpyxl 在
解析样式时抛 `Fill() takes no arguments` 错误。绕开样式层、只读数据即可。

返回结构：
  load_xlsx(path) -> { sheet_name: { row_index(int): { col_index(int): str } } }
其中所有单元格值都以字符串返回（数字、共享字符串、内联字符串均已解析）。
"""
import zipfile
import re
from xml.etree import ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def col_to_idx(col):
    """列字母 -> 数字索引（A=1, B=2, ...）。"""
    i = 0
    for c in col:
        i = i * 26 + (ord(c) - 64)
    return i


def load_xlsx(path):
    z = zipfile.ZipFile(path)

    # 共享字符串表
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in root.findall(NS + 'si'):
            shared.append(''.join(t.text or '' for t in si.iter(NS + 't')))

    # workbook.xml -> sheet 名称与 r:id
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    names = [s.get('name') for s in wb.find(NS + 'sheets')]
    rids = [s.get(RNS) for s in wb.find(NS + 'sheets')]

    # workbook.xml.rels -> r:id -> 目标 sheet 文件
    rel = {}
    if 'xl/_rels/workbook.xml.rels' in z.namelist():
        for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
            rel[r.get('Id')] = r.get('Target')

    result = {}
    for i, name in enumerate(names):
        target = rel[rids[i]].lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target

        root = ET.fromstring(z.read(target))
        rows = {}
        for row in root.iter(NS + 'row'):
            r = int(row.get('r'))
            cells = {}
            for c in row.findall(NS + 'c'):
                ref = c.get('r')
                col, _ = re.match(r'([A-Z]+)([0-9]+)', ref).groups()
                t = c.get('t')
                v = c.find(NS + 'v')
                isv = c.find(NS + 'is')
                val = None
                if t == 's' and v is not None:
                    val = shared[int(v.text)]          # 共享字符串
                elif t == 'inlineStr' and isv is not None:
                    val = ''.join(x.text or '' for x in isv.iter(NS + 't'))
                elif v is not None:
                    val = v.text                        # 数字 / 布尔 / 普通字符串
                if val is not None:
                    cells[col_to_idx(col)] = val
            if cells:
                rows[r] = cells
        result[name] = rows
    return result
