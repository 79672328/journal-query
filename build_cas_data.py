# -*- coding: utf-8 -*-
"""
构建 2025 中科院分区（升级版）数据集 cas_data.json.gz
数据源（三份 Excel 交叉合并）：
  1) 中科院分区2025完整版.xlsx   —— 权威主表：Journal / 分区 / Top / Open Access
  2) 2025年期刊中科院分区大类划分.xlsx —— 刊名 / ISSN / EISSN / 数据库 / 大类 / 大类英文 / 出版社
  3) 2025中科院分区表（分类）.xlsx    —— 按大类分 sheet 的分区明细 + 巨型期刊 + IF<20 表
输出：{v, updated, total, cats, journals:[...]}
  单条字段（紧凑数组，字典序见 SCHEMA 注释）：
  [0] 刊名（完整版原始写法）
  [1] 大类（中文）
  [2] 分区（"1"~"4" 或 ""）
  [3] Top（0/1）
  [4] OA（0/1，-1 未知）
  [5] ISSN
  [6] EISSN
  [7] 数据库（SCIE/SSCI/ESCI/AHCI/...）
  [8] 出版社
  [9] 巨型期刊（0/1）
"""
import gzip
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import openpyxl

SRC_DIR = Path(r"G:/写作/期刊分区")
OUT = Path(r"C:/Users/勾陈一/AppData/Local/Temp/jq_repo/cas_data.json.gz")

# 中科院分区表（2025 升级版）全部合法一级大类
KNOWN_CATS = {
    "综合性期刊", "计算机科学", "工程技术", "材料科学", "医学", "化学",
    "环境科学与生态学", "农林科学", "地球科学", "物理与天体物理",
    "生物", "生物学", "数学", "心理学", "管理学", "经济学", "教育学",
    "社会学", "历史学", "文学", "哲学", "艺术学", "综合",
}


# ---------------- 归一化：与前端 normalizeCn 保持同源，另加拉丁重音折叠 ----------------
def norm(s):
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s)
    # 去组合音标（重音），如 á -> a
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("&amp;", "and").replace("&", "and")
    s = re.sub(r"[\s\u3000]+", "", s)
    s = re.sub(r"[（）()\[\]【】〔〕]", "", s)
    s = re.sub(r"[·・•‧.。,]", "", s)
    s = re.sub(r"[—–\-‐－_]", "", s)
    s = re.sub(r"[：:]", "", s)
    s = re.sub(r"[、，,／/]", "", s)
    s = re.sub(r"['\"’‘“”]", "", s)
    return s


def clean(s):
    """单元格取值并清理：去首尾空白、压空格、把异常空白去掉"""
    if s is None:
        return ""
    t = str(s)
    t = t.replace("\u3000", " ").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if t.lower() in ("none", "null", "-", "nan"):
        return ""
    return t


def fmt_issn(s):
    """ISSN 规范化成 1234-5678；异常值返回空"""
    t = clean(s).strip()
    if not t:
        return ""
    t = t.replace(" ", "")
    m = re.fullmatch(r"(\d{4})-?(\d{3}[\dxX])", t)
    if m:
        return f"{m.group(1)}-{m.group(2).upper()}"
    return t if re.fullmatch(r"[\dxX-]{4,12}", t) else ""


# ---------------- 1) 权威主表：完整版 ----------------
def load_master():
    f = SRC_DIR / "中科院分区2025完整版.xlsx"
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    out = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        name = clean(row[0])
        if not name:
            continue
        zone = clean(row[1])
        m = re.search(r"[1-4]", zone)
        zone = m.group(0) if m else ""
        top = 1 if clean(row[2]) in ("是", "Y", "yes", "1", "True") else 0
        oa_raw = clean(row[3])
        oa = 1 if oa_raw in ("是", "Y", "yes", "1", "True") else (0 if oa_raw in ("否", "N", "no", "0", "False") else -1)
        out.append({"name": name, "zone": zone, "top": top, "oa": oa})
    wb.close()
    return out


# ---------------- 2) 大类划分表 ----------------
def load_daqi():
    f = SRC_DIR / "2025年期刊中科院分区大类划分.xlsx"
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    by_norm = {}
    by_issn = {}
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        name = clean(row[0])
        if not name:
            continue
        rec = {
            "name": name,
            "issn": fmt_issn(row[1]),
            "eissn": fmt_issn(row[2]),
            "db": clean(row[3]).strip("; "),
            "cat": clean(row[4]),
            "catEn": clean(row[5]),
            "pub": clean(row[6]),
        }
        rows.append(rec)
        k = norm(name)
        if k and k not in by_norm:
            by_norm[k] = rec
        for iss in (rec["issn"], rec["eissn"]):
            kk = iss.replace("-", "").upper()
            if kk and kk not in by_issn:
                by_issn[kk] = rec
    wb.close()
    return rows, by_norm, by_issn


# ---------------- 3) 分类表（按大类 sheet） ----------------
ZONE_SHEETS = ["计算机科学", "工程技术", "材料科学", "医学", "化学",
               "环境科学与生态学", "农林科学", "地球科学", "物理与天体物理",
               "生物", "管理", "综合"]


def load_fenlei():
    """返回 (刊名->分区 的补充映射, 刊名->大类 的补充映射, 巨型期刊集合)"""
    f = SRC_DIR / "2025中科院分区表（分类）.xlsx"
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    zone_sup, cat_sup, giant = {}, {}, set()

    for sh in ZONE_SHEETS:
        if sh not in wb.sheetnames:
            continue
        ws = wb[sh]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            name = clean(row[0])
            if not name:
                continue
            z = clean(row[2])
            m = re.search(r"[1-4]", z)
            if m:
                zone_sup.setdefault(norm(name), m.group(0))
                cat_sup.setdefault(norm(name), sh)

    # 巨型期刊表：序号/期刊名称/ISSN/大类/2025大类分区/2023大类分区/出版社
    if "巨型期刊" in wb.sheetnames:
        ws = wb["巨型期刊"]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i <= 1:
                continue
            name = clean(row[1])
            if not name:
                continue
            k = norm(name)
            giant.add(k)
            z = clean(row[4])
            m = re.search(r"[1-4]", z)
            if m:
                zone_sup.setdefault(k, m.group(0))
            c = clean(row[3])
            if c:
                cat_sup.setdefault(k, c)

    wb.close()
    return zone_sup, cat_sup, giant


# ---------------- 合并 ----------------
def main():
    master = load_master()
    daqi_rows, daqi_by_norm, daqi_by_issn = load_daqi()
    zone_sup, cat_sup, giant = load_fenlei()

    # 大类划分表里存在、但完整版主表没有的刊（例：仅 ESCI 收录）也纳入
    master_keys = {norm(r["name"]) for r in master}
    # 完整版主表以刊名归一化为键建索引
    master_by_norm = {}
    for r in master:
        k = norm(r["name"])
        if k:
            master_by_norm.setdefault(k, r)

    merged = {}

    def slot(name):
        k = norm(name)
        if not k:
            return None
        if k not in merged:
            merged[k] = {
                "name": name, "cat": "", "zone": "", "top": 0, "oa": -1,
                "issn": "", "eissn": "", "db": "", "pub": "", "giant": 0,
            }
        return merged[k]

    # 基线：完整版主表
    for r in master:
        s = slot(r["name"])
        if not s:
            continue
        s["zone"] = r["zone"]
        s["top"] = r["top"]
        s["oa"] = r["oa"]

    # 补充：大类划分表（大类/ISSN/数据库/出版社）
    for r in daqi_rows:
        s = slot(r["name"])
        if not s:
            continue
        if not s["name"]:
            s["name"] = r["name"]
        s["cat"] = s["cat"] or r["cat"]
        s["db"] = s["db"] or r["db"]
        s["pub"] = s["pub"] or r["pub"]
        s["issn"] = s["issn"] or r["issn"]
        s["eissn"] = s["eissn"] or r["eissn"]
        # 完整版没有分区时，用分类表补
        if not s["zone"] and r["name"]:
            z = zone_sup.get(norm(r["name"]), "")
            if z:
                s["zone"] = z

    # 补充：分类表 sheet 的分区与大类（兜底）
    for k, s in merged.items():
        if not s["zone"] and k in zone_sup:
            s["zone"] = zone_sup[k]
        if not s["cat"] and k in cat_sup:
            s["cat"] = cat_sup[k]
        if k in giant:
            s["giant"] = 1

    # ---- ISSN 回填：zone 或 cat 缺失时，用 ISSN 到大类表查（补全已有条目，不新增） ----
    fill_by_issn = 0
    iss_index = {}
    for r in daqi_rows:
        for iss in (r["issn"], r["eissn"]):
            kk = iss.replace("-", "").upper()
            if kk:
                iss_index.setdefault(kk, r)
    for k, s in merged.items():
        if s["zone"] and s["cat"]:
            continue
        for iss in (s["issn"], s["eissn"]):
            kk = iss.replace("-", "").upper()
            if kk and kk in iss_index:
                r = iss_index[kk]
                if not s["cat"]:
                    s["cat"] = r["cat"]
                if not s["pub"]:
                    s["pub"] = r["pub"]
                if not s["db"]:
                    s["db"] = r["db"]
                if not s["zone"]:
                    z = zone_sup.get(norm(r["name"]), "")
                    if z:
                        s["zone"] = z
                fill_by_issn += 1
                break

    # ---- 组装 ----
    def tidy_cat(c):
        """清洗大类字段：合并表尾部偶见的错位残留（列偏移导致刊名落到大类列）"""
        c = (c or "").strip()
        if not c:
            return ""
        if c not in KNOWN_CATS:
            # 形如「Information Processing in Agriculture」的错位值：非合法大类，丢弃
            return ""
        return c
    # 大类别名统一：分类表 sheet 用「综合」，大类表用「综合性期刊」，统一到后者
    CAT_ALIAS = {"综合": "综合性期刊"}

    journals = []
    dropped_nozone = 0
    for k, s in merged.items():
        if not s["name"]:
            continue
        # 只保留真正进入 2025 分区表的期刊（有 1-4 区分区）。
        # 大类划分表含 242 条仅列了库别/大类、未参与分区的刊（ESCI/AHCI 为主），
        # 保留会导致「查到该刊却显示无分区」的事实性误报，故剔除。
        if not s["zone"]:
            dropped_nozone += 1
            continue
        cat = CAT_ALIAS.get(tidy_cat(s["cat"]), tidy_cat(s["cat"]))
        journals.append([
            s["name"], cat, s["zone"], s["top"], s["oa"],
            s["issn"], s["eissn"], s["db"], s["pub"], s["giant"],
        ])

    cats = Counter(j[1] for j in journals if j[1])
    cat_order = ["综合性期刊", "计算机科学", "工程技术", "材料科学", "医学", "化学",
                 "环境科学与生态学", "农林科学", "地球科学", "物理与天体物理",
                 "生物", "生物学", "数学", "心理学", "管理学", "经济学", "教育学",
                 "社会学", "历史学", "文学", "哲学", "艺术学"]
    cat_list = [c for c in cat_order if c in cats] + \
               [c for c in sorted(cats) if c not in cat_order]

    out = {
        "v": "2025",
        "updated": "2025年中科院分区表（升级版）",
        "total": len(journals),
        "cats": cat_list,
        "journals": journals,
    }
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    # ---- 统计报告 ----
    print("=" * 66)
    print("完整版主表条数        :", len(master))
    print("大类划分表条数        :", len(daqi_rows))
    print("合并后唯一条目        :", len(journals))
    print("其中有分区(1-4)        :", sum(1 for j in journals if j[2]))
    print("其中 Top 期刊          :", sum(1 for j in journals if j[3]))
    print("其中 Open Access       :", sum(1 for j in journals if j[4] == 1))
    print("其中巨型期刊           :", sum(1 for j in journals if j[9]))
    print("有 ISSN               :", sum(1 for j in journals if j[5] or j[6]))
    print("有大类                :", sum(1 for j in journals if j[1]))
    print("剔除（无分区）         :", dropped_nozone)
    print("ISSN 回填命中          :", fill_by_issn)
    print("---- 大类分布 ----")
    for c in cat_list:
        print(f"  {c:<12} {cats[c]}")
    print("---- 分区分布 ----")
    zc = Counter(j[2] or "(无分区)" for j in journals)
    for z in sorted(zc, key=lambda x: (x == "(无分区)", x)):
        print(f"  {z:<10} {zc[z]}")
    # 关键刊抽查
    print("---- 关键刊抽查 ----")
    probe = ["Nature", "Science", "Cement and Concrete Research",
             "Construction and Building Materials", "Journal of Cleaner Production",
             "Safety Science", "Materials", "Applied Sciences-Basel"]
    idx = {norm(j[0]): j for j in journals}
    for p in probe:
        j = idx.get(norm(p))
        print(f"  {p:<38} -> " + (f"分区{j[2]} | {j[1]} | Top{j[3]} | OA{j[4]} | {j[5] or j[6]}" if j else "未命中"))
    size = OUT.stat().st_size
    print("=" * 66)
    print("输出:", OUT, f"({size/1024:.0f} KB gzip)")


if __name__ == "__main__":
    main()
