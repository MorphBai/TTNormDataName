#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量重命名工具 - 最终格式："组别-序号_手机型号_第N个点"
  - 自动识别文件名中的手机型号和点位序号（支持错误输入大写中文/阿拉伯数字）
  - 清理文件名中的非法字符
  - 支持递归处理子文件夹
  - 提供预览模式和直接执行模式
  - 支持手机型号分组并在文件名前添加组别和序号
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

# Windows 非法字符正则
INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*]')

# 手机型号分组映射
# 请根据实际情况修改以下映射，格式为：组号-序号: [手机型号列表]
PHONE_GROUPS = {
    '1-1': ['小米15', 'xiaomi15'],
    '1-2': ['一加13', 'oneplus13'],
    '1-3': ['oppo find x8', 'oppofindx8pro', 'findx8pro'],
    '1-4': ['vivo iqoo13', 'vivoiqoo13', 'iqoo13'],
    '1-5': ['三星s24', 'samsungs24'],
    
    '2-1': ['vivo x200 pro', 'vivox200pro', 'x200pro'],
    '2-2': ['苹果15', 'iphone15'],
    '2-3': ['荣耀magic7', 'honormagic7', 'magic7'],
    '2-4': ['红米k80pro', 'redmik80pro', 'k80pro'],
    '2-5': ['华为p40proplus', 'huaweip40proplus', 'p40proplus'],
    
    '3-1': ['华为mate60', 'huaweimate60', 'mate60'],
    '3-2': ['一加ace3', 'oneplusace3', 'ace3'],
    '3-3': ['小米14', 'xiaomi14'],
    '3-4': ['荣耀magic6', 'honormagic6', 'magic6'],
    '3-5': ['荣耀magicvs3', 'honormagicvs3', 'magicvs3'],

    '4-1': ['华为p60', 'huaweip60', 'p60'],
    '4-2': ['华为nova13', 'huaweinova13', 'nova13'],
    '4-3': ['华为mate50pro', 'huaweimate50pro', 'mate50pro'],
    '4-4': ['华为nova14pro', 'huaweinova14pro', 'nova14pro'],
    '4-5': ['华为nova14ultra', 'huaweinova14ultra', 'nova14ultra'],

    '5-1': ['华为p70pro', 'huaweip70pro', 'p70pro'],
    '5-2': ['华为matex5', 'huaweimatex5', 'matex5'],
    '5-3': ['vivo s19 pro', 'vivos19pro', 's19pro'],
    '5-4': ['vivo x100 pro', 'vivox100pro', 'x100pro'],
    '5-5': ['oppo find x7', 'oppofindx7', 'findx7'],
    '5-6': ['oppo find n3', 'oppofindn3', 'findn3'],
}

# 反向映射：手机型号 -> 组别-序号
MODEL_TO_GROUP: dict[str, str] = {}
# 规范化映射：规范化后的手机型号 -> (组别-序号, 原始别名)
NORMALIZED_MODEL_TO_GROUP: dict[str, tuple[str, str]] = {}
# 新增：组别-序号 -> 该组“第一个型号”（作为最终输出的规范型号）
GROUP_TO_CANONICAL_MODEL: dict[str, str] = {}

def normalize_model_key(s: str) -> str:
    """规范化型号用于匹配：小写、去空白和常见连接符"""
    s = s.lower().strip()
    # 去掉空白、下划线、连字符、破折号等
    return re.sub(r'[\s_\-—–]+', '', s)

def init_group_index():
    """根据 PHONE_GROUPS 构建反向映射和规范化映射"""
    MODEL_TO_GROUP.clear()
    NORMALIZED_MODEL_TO_GROUP.clear()
    GROUP_TO_CANONICAL_MODEL.clear()  # 新增
    for group, aliases in PHONE_GROUPS.items():
        if aliases:
            # 记录该组第一个型号作为规范输出型号（此处仅strip，真正落盘前仍会sanitize）
            GROUP_TO_CANONICAL_MODEL[group] = aliases[0].strip()
        for alias in aliases:
            a = alias.strip()
            if not a:
                continue
            MODEL_TO_GROUP[a] = group
            NORMALIZED_MODEL_TO_GROUP[normalize_model_key(a)] = (group, a)

def find_group_for_model(model_text: str) -> tuple[str | None, str | None]:
    """
    根据提取到的型号文本查找组别：
    - 先做规范化精确匹配
    - 再做包含/被包含的模糊匹配（取最长别名命中）
    返回：(组别-序号, 命中的别名) 或 (None, None)
    """
    key = normalize_model_key(model_text)
    if key in NORMALIZED_MODEL_TO_GROUP:
        group, alias = NORMALIZED_MODEL_TO_GROUP[key]
        return group, alias

    best = None  # (group, alias, alias_key_len)
    for alias_key, (grp, alias) in NORMALIZED_MODEL_TO_GROUP.items():
        if alias_key in key or key in alias_key:
            cand = (grp, alias, len(alias_key))
            if best is None or cand[2] > best[2]:
                best = cand
    if best:
        return best[0], best[1]
    return None, None

# 初始化组别索引
init_group_index()

# 数字映射（含常见中文/大写中文）
NUM_MAP = {
    '零': 0, '〇': 0,
    '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '壹': 1, '贰': 2, '貳': 2, '叁': 3, '肆': 4, '伍': 5, '陆': 6, '陸': 6, '柒': 7, '捌': 8, '玖': 9,
}
UNIT_MAP = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}

INT_TO_CN = {0: '零', 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九'}

# 捕获：可选前缀(乱码/分隔符) + 手机型号 + 第N(个)?点(位)?
PATTERN = re.compile(
    r'''(?x)
    ^(?:.*?(?:[-—]{2,}|—|---)\s*)?           # 可选前缀和分隔符
    (?P<model>.+?)                           # 手机型号（懒惰匹配，直到“第”）
    \s*第\s*
    (?P<num>(\d+|[零〇两一二三四五六七八九壹贰貳叁肆伍陆陸柒捌玖十拾百佰千仟]+))
    \s*(?:个)?\s*点(?:位)?                   # “个”为可选；支持“点/点位”
    (?:\s*.*)?$                              # 忽略尾部
    '''
)

def cn2int(s: str) -> int | None:
    """
    中文/大写中文/阿拉伯数字 -> 整数
    """
    s = s.strip()   # 去首尾空白
    if not s:
        return None
    if s.isdigit(): # 纯数字直接转换
        return int(s)
    total = 0
    current = 0
    for ch in s:
        if ch in NUM_MAP:
            current = NUM_MAP[ch]
        elif ch in UNIT_MAP:
            unit = UNIT_MAP[ch]
            if current == 0:
                current = 1  # 处理“十、百、千”前省略“一”的情况
            total += current * unit
            current = 0
        elif ch.isspace():
            continue
        else:
            return None
    total += current
    return total

def int2cn(n: int) -> str:
    """整数 -> 中文数字（0-999，超出范围原样返回字符串）"""
    if n == 0:
        return '零'
    if 0 < n < 10:
        return INT_TO_CN[n]
    if 10 <= n < 100:
        tens, units = divmod(n, 10)
        result = '十' if tens == 1 else f'{INT_TO_CN[tens]}十'
        if units:
            result += INT_TO_CN[units]
        return result
    if 100 <= n < 1000:
        hundreds, remainder = divmod(n, 100)
        result = f'{INT_TO_CN[hundreds]}百'
        if remainder:
            if remainder < 10:
                result += '零'
            result += int2cn(remainder)
        return result
    return str(n)

def sanitize_component(text: str) -> str:
    """清理文件名组件：去非法字符、归一化空白、清理边界连接符/空白/点"""
    text = INVALID_CHARS_RE.sub('-', text)
    text = re.sub(r'\s+', ' ', text)  # 合并连续空白
    text = re.sub(r'^[\s_\-—–]+|[\s_\-—–]+$', '', text)  # 去首尾连接符/空白
    return text.rstrip(' .')

def build_new_name(basename: str) -> str | None:
    """由原始无扩展名构建新名：命中则为 组别-序号_规范型号_第中文数字个点，否则 型号_第中文数字个点"""
    m = PATTERN.search(basename)
    if not m:
        return None

    # 提取手机型号（保持原样的大小写，仅清洗）
    model = sanitize_component(m.group('model').strip())
    if not model:
        return None

    # 数字解析为中文
    num_raw = m.group('num').strip()
    n = cn2int(num_raw)
    if n is None:
        return None
    num_cn = int2cn(n)

    # 组别匹配（精确/模糊）
    group_id, _alias = find_group_for_model(model)
    prefix = f'{group_id}_' if group_id else ''

    # 若命中组别，最终型号使用该组的“第一个型号”作为规范输出
    final_model = model
    if group_id:
        canonical = GROUP_TO_CANONICAL_MODEL.get(group_id)
        if canonical:
            # 仍进行一次清洗，避免映射里出现尾空格或非法字符
            cleaned = sanitize_component(canonical)
            if cleaned:
                final_model = cleaned

    return f'{prefix}{final_model}_第{num_cn}个点'

def ensure_unique(target: Path) -> Path:
    """若目标已存在，追加 (k) 后缀以保证唯一"""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 2
    while True:
        cand = target.with_name(f'{stem} ({i}){suffix}')
        if not cand.exists():
            return cand
        i += 1

def iter_files(root: Path, recursive: bool):
    """遍历文件：支持递归或非递归"""
    return (p for p in (root.rglob('*') if recursive else root.iterdir()) if p.is_file())

def plan_changes(root: Path, recursive: bool):
    """生成重命名计划"""
    files = root.rglob('*') if recursive else root.iterdir()    # 获取所有文件路径
    plans: list[tuple[Path, Path]] = []
    for p in files:
        if not p.is_file():
            continue
        new_base = build_new_name(p.stem)
        if not new_base:
            continue
        if new_base == p.stem:
            continue
        new_path = ensure_unique(p.with_name(new_base + p.suffix))
        # Windows 大小写不敏感：仅大小写变化则跳过
        if new_path.name.casefold() == p.name.casefold():
            continue
        if new_path != p:
            plans.append((p, new_path))
    return plans

def main():
    parser = argparse.ArgumentParser(description='批量重命名为：组别-序号_手机型号_第N个点（N为中文数字）')
    parser.add_argument('-d', '--dir', default=str(Path(__file__).resolve().parent),
                        help='目标文件夹路径（默认：脚本所在目录）')
    parser.add_argument('-r', '--recursive', action='store_true', help='递归处理子文件夹')
    parser.add_argument('--apply', '-y', action='store_true', help='直接执行重命名（无此参数则仅预览并询问）')
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.exists() or not root.is_dir():
        print(f'目录不存在：{root}')
        return

    plans = plan_changes(root, args.recursive)
    if not plans:
        print('未找到可重命名的文件。')
        return

    print('将进行如下重命名：')
    for src, dst in plans:
        try:
            rel = src.relative_to(root)
        except Exception:
            rel = src.name
        print(f'- {rel}  ->  {dst.name}')

    if not args.apply:
        ans = input('是否执行重命名？(y/N) ').strip().lower()
        if ans not in ('y', 'yes'):
            print('已取消。')
            return

    count = 0
    for src, dst in plans:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(dst)
            count += 1
        except Exception as e:
            print(f'[失败] {src.name} -> {dst.name}: {e}')
    print(f'完成：成功重命名 {count} 个文件。')

if __name__ == '__main__':
    main()