import os
import csv
import argparse
import tempfile
import time
from paddleocr import PaddleOCR
from pdf2image import convert_from_path
from functools import cmp_to_key

# 初始化OCR
ocr = PaddleOCR(use_angle_cls=True, lang='ch')

def custom_compare(a, b):
    """
    比较函数：
    - 如果 a[0] 比 b[0] 大超过 20，则 a 排在后面（b 在前）
    - 如果 b[0] 比 a[0] 大超过 20，则 b 排在后面（a 在前）
    - 否则认为相等，保持原始顺序
    """
    if a[0] - b[0] > 20:
        return 1   # a > b, 所以 a 排后面
    elif b[0] - a[0] > 20:
        return -1  # a < b, 所以 a 排前面
    else:
        return 0   # 认为相等，保持原顺序（稳定排序保证）

def find_value_after_keyword(lines, keywords):
    """
    在文本行列表中查找包含关键词的行，并返回其后的值。
    支持跨行：如果当前行只有关键词无内容，则取下一行非空文本。
    
    Args:
        lines: 文本行列表（已按 y 坐标排序）
        keywords: 关键词列表，如 ['出租方', '甲方']
    
    Returns:
        提取到的值，字符串
    """
    for i, line in enumerate(lines):
        line = line.strip()
        # 检查当前行是否包含任一关键词
        if any(kw in line for kw in keywords):
            # 提取冒号后的内容
            if '：' in line:
                value = line.split('：', 1)[1].strip()
            elif ':' in line:
                value = line.split(':', 1)[1].strip()
            else:
                value = ''
            
            # 如果冒号后有内容，直接返回
            if value:
                return value
            
            # 否则：关键词在本行但无值 → 查找下一行非空行
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                if next_line and not any(kw in next_line for kw in ['出租方', '承租方', '甲方', '乙方']):
                    return next_line
    
    return ''

def extract_party_from_contract_pdf(pdf_path: str) -> dict:
    """
    从合同PDF中提取甲方（出租方）和乙方（承租方）
    并先判断第一页标题是否含“合同”
    """
    result = {
        'file': os.path.basename(pdf_path),
        'folder_name': os.path.basename(os.path.dirname(pdf_path)),
        'landlord': '',
        'tenant': '',
        'type': '',
        'status': 'success',
        'error': '',
        'pdf_path': pdf_path
    }

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = os.path.join(temp_dir, "page_0.jpg")
            images = convert_from_path(pdf_path, first_page=0, last_page=1, dpi=200)
            if not images:
                result['status'] = 'failed'
                result['error'] = 'PDF转图片失败'
                return result
            images[0].save(image_path, "JPEG")

            # === 1. OCR识别第一页 ===
            ocr_result = ocr.predict(image_path)
            if not ocr_result or not ocr_result[0]:
                result['status'] = 'failed'
                result['error'] = 'OCR识别无结果'
                return result

            # ocr_result[0] 是一个字典
            res_dict = ocr_result[0]
            
            # 检查是否为字典格式
            if isinstance(res_dict, dict):
                texts = res_dict.get('rec_texts', [])
                polys = res_dict.get('rec_polys', [])  # 或 'boxes'
                scores = res_dict.get('rec_scores', [])
            else:
                # 老版本格式：列表 of (box, (text, score))
                texts = [item[1][0] for item in res_dict]
                polys = [item[0] for item in res_dict]
            
            # 安全检查
            if len(texts) != len(polys):
                print(f"⚠️ 文本数量 {len(texts)} 与框数量 {len(polys)} 不匹配")
                texts = texts[:min(len(texts), len(polys))]
                polys = polys[:min(len(texts), len(polys))]
            
            # 提取文本行并按 y 坐标排序
            lines = []
            for poly, text in zip(polys, texts):
                try:
                    text = str(text).strip()
                    if not text:
                        continue
            
                    # 计算文本框的垂直中心 y 坐标
                    # poly 是 shape=(4,2) 的 numpy array: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    y_coords = [point[1] for point in poly]  # 所有 y 值
                    y_center = sum(y_coords) / len(y_coords)  # 或用 (min + max)/2
            
                    lines.append((y_center, text))
                except Exception as e:
                    print(f"⚠️ 处理文本框时出错: {e}")
                    continue
            
            # 按 y 坐标从上到下排序
            #print(lines)
            #sorted_lines = sorted(lines, key=lambda x: x[0])
            sorted_lines = sorted(lines, key=cmp_to_key(custom_compare))
            #print(sorted_lines)
            all_text_lines = [line[1] for line in sorted_lines]

            # === 2. 提取标题：取最上面的1-10行文本 ===
            title_lines = [line[1].strip() for line in sorted_lines[:10] if line[1].strip()]
            title_text = ' '.join(title_lines)

            # === 3. 判断标题是否含“合同”关键词 ===
            if '补充协议' in title_text:
                result['type'] = '补充协议'
            elif '合同' in title_text:
                result['type'] = '合同'
            else:
                result['type'] = '未知'
                return result


            print(f"📄 标题匹配: \"{title_text}\"")

            # === 4. 提取甲方、乙方 ===
            result['landlord'] = find_value_after_keyword(all_text_lines, ['出租方', '甲方'])
            result['tenant'] = find_value_after_keyword(all_text_lines, ['承租方', '乙方'])

            print(f"  🏢 出租方/甲方: {result['landlord']}")
            print(f"  👤 承租方/乙方: {result['tenant']}")

            # === 第二步：如果 type 正确但双方均为空，尝试读取第二页 ===
            if result['type'] in ['合同', '补充协议'] and not result['landlord'] and not result['tenant']:
                print(f"� 第一页未提取到甲乙双方，尝试读取第二页...")

                image_path_2 = os.path.join(temp_dir, "page_2.jpg")
                images_2 = convert_from_path(pdf_path, first_page=2, last_page=2, dpi=200)

                if not images_2:
                    print("⚠️ 第二页转图片失败或不存在")
                else:
                    images_2[0].save(image_path_2, "JPEG")
                    ocr_result_2 = ocr.predict(image_path_2)
                    if not ocr_result_2 or not ocr_result_2[0]:
                        print("⚠️ 第二页OCR识别无结果")
                    else:
                        res_dict_2 = ocr_result_2[0]
                        texts_2, polys_2 = [], []

                        if isinstance(res_dict_2, dict):
                            texts_2 = res_dict_2.get('rec_texts', [])
                            polys_2 = res_dict_2.get('rec_polys', []) or res_dict_2.get('boxes', [])
                        else:
                            texts_2 = [item[1][0] for item in res_dict_2]
                            polys_2 = [item[0] for item in res_dict_2]

                        if len(texts_2) != len(polys_2):
                            print(f"⚠️ 第二页文本与框数量不匹配：{len(texts_2)} vs {len(polys_2)}")
                            min_len = min(len(texts_2), len(polys_2))
                            texts_2 = texts_2[:min_len]
                            polys_2 = polys_2[:min_len]

                        lines_2 = []
                        for poly, text in zip(polys_2, texts_2):
                            try:
                                text = str(text).strip()
                                if not text:
                                    continue
                                y_coords = [point[1] for point in poly]
                                y_center = sum(y_coords) / len(y_coords)
                                lines_2.append((y_center, text))
                            except Exception as e:
                                print(f"⚠️ 处理第二页文本框时出错: {e}")
                                continue

                        sorted_lines_2 = sorted(lines_2, key=cmp_to_key(custom_compare))
                        all_text_lines_2 = [line[1] for line in sorted_lines_2]

                        # 使用第二页内容重新提取
                        landlord_2 = find_value_after_keyword(all_text_lines_2, ['出租方', '甲方'])
                        tenant_2 = find_value_after_keyword(all_text_lines_2, ['承租方', '乙方'])

                        if landlord_2:
                            result['landlord'] = landlord_2
                            print(f"✅ 成功从第二页提取出租方: {landlord_2}")
                        if tenant_2:
                            result['tenant'] = tenant_2
                            print(f"✅ 成功从第二页提取承租方: {tenant_2}")

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)

    return result

def main(input_folder: str):
    start_time = time.time()

    folder_name = os.path.basename(os.path.abspath(input_folder))
    output_csv = f"{folder_name}_contracts.csv"

    results = []

    for root, dirs, files in os.walk(input_folder):
        for filename in files:
            if filename.lower().endswith('.pdf'):
                pdf_path = os.path.join(root, filename)
                print(f"🔍 检查文件: {filename}")
                result = extract_party_from_contract_pdf(pdf_path)
                results.append(result)

    # 写入CSV
    with open(output_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            '文件名', '所在文件夹', '出租方_甲方', '承租方_乙方', '类型', '文件路径'
        ])
        writer.writeheader()

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

                row = {
                    '文件名': f'=" {os.path.splitext(res["file"])[0]} "',
                    '所在文件夹': res['folder_name'],
                    '出租方_甲方': res['landlord'],
                    '承租方_乙方': res['tenant'],
                    '类型': res['type'],
                    '文件路径': hyperlink
                }
                writer.writerow(row)
                print(f"✅ 已提取: {res['file']}")
            elif res['status'] == 'skipped':
                print(f"🟡 跳过非合同文档: {res['file']} | {res['error']}")
            else:
                print(f"❌ 失败: {res['file']} | {res['error']}")

    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, rem = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(rem, 60)

    print(f"\n� 处理完成！结果已保存至: {output_csv}")
    print(f"� 总耗时: {int(hours):02d}:{int(minutes):02d}:{seconds:05.2f} (时:分:秒)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从合同PDF中提取甲方和乙方信息（基于标题判断）")
    parser.add_argument("input_folder", help="输入文件夹路径（包含PDF）")
    args = parser.parse_args()
    main(args.input_folder)