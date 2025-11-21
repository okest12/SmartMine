#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量从PDF发票中提取结构化信息
支持命令行传入文件夹路径，递归处理所有PDF文件
✅ 从表格中提取合计金额，不再依赖“合计金额”关键词
✅ 自动清洗稀疏表格（None、空字符串、换行符）
✅ 支持结构化输出：供应商、单据关联、费用明细、合计金额
"""

import pdfplumber
import re
import os
import sys
import csv
from typing import Dict, List

def clean_table(raw_table):
    """
    清洗从 pdfplumber 提取的稀疏表格
    - 过滤 None 和空字符串
    - 合并换行符和多余空白
    - 返回干净的二维列表
    """
    cleaned = []
    for row in raw_table:
        cleaned_row = []
        for cell in row:
            if cell is None or cell == '':
                continue
            cell_str = str(cell).strip()
            if cell_str:
                cleaned_cell = re.sub(r'\s+', '', cell_str)  # 合并空白字符（换行、空格）
                cleaned_row.append(cleaned_cell)
        if cleaned_row:  # 非空行才保留
            cleaned.append(cleaned_row)
    return cleaned


def find_value_after_keyword(keyword: str, words) -> str:
    """
    查找关键词右侧紧邻的文本作为值，并尝试合并可能被分行的文本（如供应商名称跨行）
    """
    for word in words:
        if keyword in word['text']:
            # 定义垂直对齐容差
            y_tol = 5
            x_tol = 20  # 水平位置接近即可

            # 当前行：关键词右侧的词
            right_words = [w for w in words 
                         if abs(w['top'] - word['top']) < y_tol and w['x0'] > word['x1']]
            if not right_words:
                return ''

            # 取最左边的一个（紧邻）
            current_line_word = min(right_words, key=lambda w: w['x0'])
            current_text = current_line_word['text'].strip()

            # 尝试查找上一行是否存在延续文本
            # 上一行的 y 坐标应略小（在它上面），且 x 位置接近
            upper_candidates = [
                w for w in words
                if abs(w['top'] - (word['top'] - 12)) < y_tol  # 上一行大约在 -12px 位置
                   and abs(w['x0'] - current_line_word['x0']) < x_tol  # x 起始位置接近
                   and len(w['text'].strip()) > 1
            ]

            if upper_candidates:
                # 按 x0 排序后拼接
                upper_text = ''.join([w['text'] for w in sorted(upper_candidates, key=lambda x: x['x0'])]).strip()
                # 拼接：上一行 + 当前行
                return upper_text + current_text

            # 否则只返回当前行
            return current_text
    return ''

def extract_structured_info_from_pdf(pdf_path: str) -> Dict:
    """
    从单个PDF文件中结构化提取所需信息
    """
    result = {
        'file': os.path.basename(pdf_path),
        'supplier': '',
        'link': '',
        'fee_table': [],
        'total_amount': '',
        'status': 'success',
        'error': '',
        'contract': ''  # 新增：是否有合同
    }

    try:
        # === 新增：检查同目录是否存在文件名包含“合同”的文件 ===
        folder_path = os.path.dirname(pdf_path)
        try:
            all_files = [
                f for f in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, f))
            ]
            # 如果当前文件所在文件夹有超过 1 个文件，则认为“有合同”
            result['contract'] = '有' if len(all_files) > 1 else '没'
        except Exception as e:
            print(f"⚠️  无法读取文件夹 {folder_path}: {e}")
            result['contract'] = '没'  # 出错时默认“没”
        # ===================================================

        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) == 0:
                result['status'] = 'failed'
                result['error'] = 'PDF无页面内容'
                return result

            page = pdf.pages[0]  # 假设信息在第一页
            width = page.width
            height = page.height
            print(f"📄 处理文件: {result['file']} | 页面尺寸: {width:.0f}x{height:.0f}")
            
            text = page.extract_text()
            if "对公借款" not in text:
                result['status'] = 'skipped'
                result['error'] = '文件不包含“对公借款”关键字'
                return result

            # === 1. 提取文字块用于关键词定位（供应商、单据关联）===
            words = page.extract_words(x_tolerance=2, y_tolerance=2)

            result['supplier'] = find_value_after_keyword('供应商名称', words)
            result['link'] = find_value_after_keyword('单据关联', words)
            
            # 调试输出：查看关键字段提取结果
            print(f"  🧾 供应商名称: {result['supplier']}")
            print(f"  🔗 单据关联: {result['link']}")

            # === 2. 提取费用明细表格并提取合计金额 ===
            tables = page.extract_tables()
            if not tables:
                print(f"  ⚠️  未检测到表格")
            else:
                print(f"  📊 检测到 {len(tables)} 个表格")
                target_table = None
                for raw_table in tables:
                    cleaned_table = clean_table(raw_table)
                    if cleaned_table and len(cleaned_table) > 0:
                        header = ''.join(cleaned_table[0])
                        if '费用承担公司' in header or '借款类型' in header:
                            target_table = cleaned_table
                            break

                if target_table:
                    header = target_table[0]
                    print(f"  ✅ 使用表格，表头: {header}")

                    # 遍历表格行，提取明细和合计金额
                    for row_idx, row in enumerate(target_table[1:], start=2):
                        print(f"     行 {row_idx}: {row}")

                        # 情况1: 正常数据行（序号为数字）
                        if len(row) >= 7 and row[0].strip().isdigit():
                            clean_row = [cell.strip() if cell else '' for cell in row]
                            result['fee_table'].append({
                                '序号': clean_row[0],
                                '费用承担公司': clean_row[1],
                                '费用承担部门': clean_row[2],
                                '借款类型': clean_row[3],
                                '借款项目': clean_row[4],
                                '费用日期': clean_row[5],
                                '支付金额': clean_row[6],
                                '归属城市': clean_row[7] if len(row) > 7 else ''
                            })

                        # 情况2: 合计行（第一列为“合计”）
                        elif row[0].strip() == '合计':
                            # 从该行中查找第一个看起来像金额的数字
                            for cell in row:
                                amt_match = re.search(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', cell or '')
                                if amt_match:
                                    result['total_amount'] = amt_match.group()
                                    print(f"  ✅ 从【合计】行提取金额: {result['total_amount']}")
                                    break

                # 如果仍未提取到，尝试最后一行（兜底）
                if not result['total_amount'] and target_table:
                    last_row = target_table[-1]
                    for cell in last_row:
                        amt_match = re.search(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', cell or '')
                        if amt_match:
                            result['total_amount'] = amt_match.group()
                            print(f"  ✅ 从最后一行提取合计金额: {result['total_amount']}")
                            break

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        print(f"  ❌ 处理失败: {e}")

    return result


def process_folder(folder_path: str) -> List[Dict]:
    """
    递归处理文件夹下所有PDF文件
    """
    all_results = []
    pdf_count = 0

    if not os.path.exists(folder_path):
        print(f"❌ 错误：路径不存在: {folder_path}")
        return []

    print(f"🔍 开始扫描文件夹: {folder_path}")

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_count += 1
                pdf_path = os.path.join(root, file)
                print(f"{'-'*60}")
                result = extract_structured_info_from_pdf(pdf_path)
                all_results.append(result)

    print(f"{'='*60}")
    print(f"✅ 扫描完成。共处理 {pdf_count} 个PDF文件。")
    return all_results

def main():
    # 检查命令行参数
    if len(sys.argv) != 2:
        print(f"📌 使用方法: python {sys.argv[0]} <文件夹路径>")
        print(f"📝 示例: python {sys.argv[0]} C:\\invoices")
        sys.exit(1)

    folder_path = sys.argv[1]

    if not os.path.isdir(folder_path):
        print(f"❌ 错误：'{folder_path}' 不是一个有效的文件夹路径")
        sys.exit(1)

    # 开始处理
    results = process_folder(folder_path)

    # 最终汇总
    success_count = sum(1 for r in results if r['status'] == 'success')
    print(f"\n📊 处理汇总: {success_count} / {len(results)} 成功")

    # ========== 🔽 新增：导出到 CSV ==========
    output_csv = "invoice_extracted_results.csv"
    with open(output_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            '文件名', '供应商', '单据关联',
            '序号', '费用承担公司', '费用承担部门', '借款类型', '借款项目', '费用日期', '支付金额', '归属城市',
            '合计金额', '合同'  # 新增列
        ])
        writer.writeheader()

        for res in results:
            if res['status'] == 'success':
                for fee in res['fee_table']:
                    row = {
                        '文件名': f'=" {os.path.splitext(res["file"])[0]} "',
                        '供应商': res['supplier'],
                        '单据关联': res['link'],
                        '序号': fee.get('序号', ''),
                        '费用承担公司': fee.get('费用承担公司', ''),
                        '费用承担部门': fee.get('费用承担部门', ''),
                        '借款类型': fee.get('借款类型', ''),
                        '借款项目': fee.get('借款项目', ''),
                        '费用日期': fee.get('费用日期', ''),
                        '支付金额': fee.get('支付金额', ''),
                        '归属城市': fee.get('归属城市', ''),
                        '合计金额': res['total_amount'],
                        '合同': res['contract']  # ✅ 写入合同列
                    }
                    writer.writerow(row)
                print(f"✅ 已导出 {len(res['fee_table'])} 条明细: {res['file']}")
            elif res['status'] == 'skipped':
                print(f"🟡 跳过非目标文件: {res['file']}")
            else:  # failed
                print(f"❌ 忽略失败文件: {res['file']} - {res['error']}")
                continue

    print(f"✅ 所有结果已保存到: {output_csv}")

if __name__ == "__main__":
    main()