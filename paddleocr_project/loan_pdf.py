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


def find_tax_rate_after_zhuanpiao(words, zhuanpiao_word):
    """
    在 '专票' 文本块右侧查找税率（如 3%, 6%, 13%, 也支持 1.5%, 0.5% 等）
    :param words: 所有文本块列表，每个元素为 dict，包含 'text', 'x0', 'x1', 'top'
    :param zhuanpiao_word: 包含 '专票' 的 word 对象
    :return: 税率字符串，如 '3%'、'1.5%'，未找到返回 ''
    """
    y_tol = 5          # 垂直对齐容差
    min_x_gap = 10     # 最小水平间距
    max_x_gap = 100    # 最大水平间距

    # 更新正则：支持整数或一位小数，如 3%、3.5%、1.5%、0.5%、13% 等
    pattern = r'^(\d{1,2}(\.\d)?|免税)%$'

    candidates = []
    for w in words:
        text = w['text'].strip()
        # 检查是否在同一行附近，且在右侧
        if (
            abs(w['top'] - zhuanpiao_word['top']) < y_tol
            and w['x0'] > zhuanpiao_word['x1'] + min_x_gap
            and w['x0'] < zhuanpiao_word['x1'] + max_x_gap
        ):
            # 使用更灵活的正则匹配税率（支持小数）
            if re.fullmatch(pattern, text):
                candidates.append(w)

    # 返回最左边的匹配项
    if candidates:
        leftmost = min(candidates, key=lambda x: x['x0'])
        return leftmost['text'].strip()

    return ''


def extract_structured_info_from_pdf(pdf_path: str) -> Dict:
    result = {
        'file': os.path.basename(pdf_path),
        'link': '',  # 单据关联
        'fee_table': [],
        'status': 'success',
        'error': '',
        'pdf_path': pdf_path  # 新增：记录原始路径
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) == 0:
                result['status'] = 'failed'
                result['error'] = 'PDF无页面内容'
                return result

            page = pdf.pages[0]  # 假设信息在第一页
            width = page.width
            height = page.height
            print(f" 处理文件: {result['file']} | 页面尺寸: {width:.0f}x{height:.0f}")

            text = page.extract_text()

            # === 新增：筛选必须包含“借款核销审批流程”字段 ===
            if "借款核销审批流程" not in text:
                result['status'] = 'skipped'
                result['error'] = '文件不包含“借款核销审批流程”关键字'
                print(f"  ⚠️  跳过非目标文件: {result['file']}")
                return result

            # 提取文字块用于关键词定位（单据关联）
            words = page.extract_words(x_tolerance=2, y_tolerance=2)

            # 提取单据关联
            result['link'] = find_value_after_keyword('单据关联', words)
            print(f"  � 单据关联: {result['link']}")

            # 提取表格数据（使用带坐标的表格提取）
            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            }
            tables = page.find_tables(table_settings)
            
            if not tables:
                print(f"  ⚠️  未检测到表格")
            else:
                print(f"   检测到 {len(tables)} 个表格")
                target_table = None
                target_table_data = None
                table_rows = None

                for table in tables:
                    # 裁剪表格区域提取文本
                    table_page = page.crop(table.bbox)
                    table_data = table_page.extract_table()
                    
                    if not table_data or len(table_data) == 0:
                        continue
                        
                    header = ''.join(table_data[0])
                    if '发票项⽬' in header or '核销⾦额' in header:
                        target_table = table
                        target_table_data = table_data
                        table_rows = table.rows  # 保存每行的 bbox
                        break

                if target_table_data:
                    cleaned_table = clean_table(target_table_data)
                    header = cleaned_table[0]
                    print(f"  ✅ 使用表格，表头: {header}")

                    # 遍历表格行，提取明细
                    for row_idx, row in enumerate(cleaned_table[1:], start=1):
                        print(f"     行 {row_idx+1}: {row}")

                        if len(row) >= 7 and row[0].strip().isdigit():
                            clean_row = [cell.strip() if cell else '' for cell in row]
                            invoice_type = clean_row[6]
                            tax_rate = ''

                            # 只有“专票”才提取税率
                            if '专票' in invoice_type:
                                # 获取当前行的 y 范围
                                table_row = table_rows[row_idx]  # 注意：table_rows[0] 是表头
                                row_top = table_row.bbox[1]
                                row_bottom = table_row.bbox[3]

                                # 在 words 中找同一行的 '专票'
                                for word in words:
                                    if (
                                        word['text'] == '专票'
                                        and row_top - 10 < word['top'] < row_bottom + 10
                                    ):
                                        tax_rate = find_tax_rate_after_zhuanpiao(words, word)
                                        if tax_rate:
                                            break

                            result['fee_table'].append({
                                '借款单号': f'=" {clean_row[0]} "',
                                '费用承担公司': clean_row[1],
                                '费用承担部门': clean_row[2],
                                '费用日期': clean_row[3],
                                '发票项目': clean_row[4],
                                '核销金额': clean_row[5],
                                '发票类型': invoice_type,
                                '发票税率': tax_rate  # 新增字段
                            })

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

    print(f" 开始扫描文件夹: {folder_path}")

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
    if len(sys.argv) != 2:
        print(f" 使用方法: python {sys.argv[0]} <文件夹路径>")
        print(f" 示例: python {sys.argv[0]} C:\\invoices")
        sys.exit(1)

    folder_path = sys.argv[1]

    if not os.path.isdir(folder_path):
        print(f"❌ 错误：'{folder_path}' 不是一个有效的文件夹路径")
        sys.exit(1)

    # 开始处理
    results = process_folder(folder_path)

    # 汇总
    success_count = sum(1 for r in results if r['status'] == 'success')
    print(f"\n 处理汇总: {success_count} / {len(results)} 成功")

    # ========== 导出到 CSV ==========
    output_csv = "loan_extracted_results.csv"
    with open(output_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            '文件名', '单据关联', '借款单号', '费用承担公司', '费用承担部门', '费用日期', 
            '发票项目', '核销金额', '发票类型', '发票税率', '文件路径'  # ← 新增
        ])
        writer.writeheader()

        csv_dir = os.path.dirname(os.path.abspath(output_csv))  # CSV 所在目录

        for res in results:
            if res['status'] == 'success':
                # 计算相对路径
                csv_dir = os.path.dirname(os.path.abspath(output_csv))
                pdf_abs_path = res['pdf_path']
                try:
                    rel_path = os.path.relpath(pdf_abs_path, csv_dir)
                except ValueError:
                    rel_path = pdf_abs_path  # 跨盘符时用绝对路径

                # 统一显示用反斜杠（Windows 风格），便于阅读
                path_display = rel_path.replace('/', '\\')  # 如 input\发票2025.pdf

                # 但 HYPERLINK 函数内部推荐使用正斜杠（更兼容 Excel）
                path_for_hyperlink = rel_path.replace('\\', '/')  # 如 input/发票2025.pdf

                # 构造公式：=HYPERLINK("input/发票2025.pdf", "input\发票2025.pdf")
                hyperlink = f'=HYPERLINK("{path_for_hyperlink}", "{path_display}")'

                for fee in res['fee_table']:
                    row = {
                        '文件名': f'=" {os.path.splitext(res["file"])[0]} "',
                        '单据关联': res['link'],
                        '借款单号': fee.get('借款单号', ''),
                        '费用承担公司': fee.get('费用承担公司', ''),
                        '费用承担部门': fee.get('费用承担部门', ''),
                        '费用日期': fee.get('费用日期', ''),
                        '发票项目': fee.get('发票项目', ''),
                        '核销金额': fee.get('核销金额', ''),
                        '发票类型': fee.get('发票类型', ''),
                        '发票税率': fee.get('发票税率', ''),
                        '文件路径': hyperlink
                    }
                    writer.writerow(row)
                print(f"✅ 已导出 {len(res['fee_table'])} 条明细: {res['file']}")
            elif res['status'] == 'skipped':
                print(f"🟡 跳过非目标文件: {res['file']}")
            else:
                print(f"❌ 忽略失败文件: {res['file']} - {res['error']}")

    print(f"✅ 所有结果已保存到: {output_csv}")

if __name__ == "__main__":
    main()