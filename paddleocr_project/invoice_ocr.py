import os
import cv2
from pathlib import Path
from paddleocr import PaddleOCR
import pandas as pd
from typing import Dict, List, Tuple
import argparse


# 初始化 PaddleOCR
def init_ocr():
    ocr = PaddleOCR(
        use_angle_cls=False,
        lang='ch',
        device='cpu',  # 若无 GPU，请改为 False
    )
    return ocr


# 关键词定义
KEYWORDS = {
    'seller': ['销售方', '销货单位', '销售单位', '销售方名称'],
    'buyer': ['购买方', '购货单位', '购买单位', '购买方名称'],
    'tax_id': ['纳税人识别号', '税号', '统一社会信用代码'],
    'total_amount': ['价税合计', '合计', '总计', '总金额'],
    'amount': ['金额', '不含税金额', '小写金额'],
    'tax': ['税额', '税'],
    'items': ['货物或应税劳务、服务名称', '项目', '品名', '服务名称']
}


def extract_text_lines(result) -> List[Tuple[str, float]]:
    """
    从 predict 返回的 dict 结构中提取文本行和置信度
    输入: result = ocr.predict(...)
    输出: [(text, confidence), ...]
    """
    lines = []
    try:
        # result 是列表，每个元素是一个 dict（多页）
        for res in result:
            if isinstance(res, dict):
                texts = res.get('rec_texts', [])
                scores = res.get('rec_scores', [])
                # 确保长度一致
                if len(texts) == len(scores):
                    for text, score in zip(texts, scores):
                        lines.append((str(text).strip(), float(score)))
                else:
                    print("fallback:", len(texts), len(scores))
                    for text in texts:
                        lines.append((str(text).strip(), 0.9))  # 默认高置信
    except Exception as e:
        print(f"[解析错误] extract_text_lines: {e}")
    return lines

def extract_invoice_fields_from_lines(lines: List[Tuple[str, float]]) -> Dict[str, str]:
    """
    根据发票文本行提取关键字段
    输入: lines = [(text, confidence), ...] 按 OCR 检测顺序排列
    输出: 包含关键字段的字典
    """
    # 提取纯文本列表，便于搜索
    texts = [line[0] for line in lines]

    fields = {
        'seller': '',           # 销售方名称
        'buyer': '',            # 购买方名称
        'tax_id': '',           # 销售方纳税人识别号（按你要求：销售方税号）
        'service_items': '',    # 服务名称
        'amount': '',           # 金额（不含税）
        'tax': '',              # 税额
        'total_amount': '',     # 价税合计（小写）
    }

    # ==================== 1. 提取购买方名称 ====================
    try:
        buyer_idx = texts.index('购买方')
        # 购买方名称通常在 '购买方' 之后几行内
        for i in range(buyer_idx + 1, min(buyer_idx + 5, len(texts))):
            text = texts[i]
            if '纳税人识别号' in text:
                break
            if len(text) >= 4 and '：' not in text and '@' not in text and '(' not in text:
                fields['buyer'] = text.strip()
                break
    except ValueError:
        pass  # 未找到 '购买方'

    # ==================== 2. 提取销售方纳税人识别号（销售方税号）====================
    try:
        seller_tax_start = texts.index('纳税人识别号：')
        # 销售方税号在 '纳税人识别号：' 之后，但可能被 '备'、'注' 干扰
        for i in range(seller_tax_start + 1, min(seller_tax_start + 5, len(texts))):
            text = texts[i]
            if len(text) >= 10 and text.isalnum() and text.startswith('91') and 'MA' in text:
                fields['tax_id'] = text.strip()
                break
    except ValueError:
        pass  # 未找到 '纳税人识别号：'

    # ==================== 3. 提取服务名称 ====================
    # 服务名称出现在 '货物或应税劳务、服务名称' 之后，金额之前
    try:
        items_header_idx = texts.index('货物或应税劳务、服务名称')
        for i in range(items_header_idx + 1, len(texts)):
            text = texts[i]
            if '规格型号' in text or '单位' in text or '数量' in text:
                continue
            if '合计' in text or '金额' in text or '税额' in text:
                break
            if len(text) >= 4 and '￥' not in text and '%' not in text:
                fields['service_items'] = text.strip()
                break
    except ValueError:
        pass  # 未找到表头

    # ==================== 4. 提取金额（￥3595.75）====================
    try:
        amount_header_idx = texts.index('金额')
        for i in range(amount_header_idx + 1, len(texts)):
            text = texts[i]
            if '￥' in text and any(c.isdigit() for c in text):
                # 提取含 ¥ 的金额
                fields['amount'] = text.replace('￥', '').strip()
                break
    except ValueError:
        pass

    # ==================== 5. 提取税额（￥215.75）====================
    try:
        tax_header_idx = texts.index('税额')
        for i in range(tax_header_idx + 1, len(texts)):
            text = texts[i]
            if '￥' in text and any(c.isdigit() for c in text):
                fields['tax'] = text.replace('￥', '').strip()
                break
    except ValueError:
        pass

    # ==================== 6. 提取价税合计（￥3811.50）====================
    try:
        # 方法1：找“（小写）”后的金额
        if '（小写）' in texts:
            small_idx = texts.index('（小写）')
            if small_idx + 1 < len(texts):
                text = texts[small_idx + 1]
                if '￥' in text:
                    fields['total_amount'] = text.replace('￥', '').strip()

        # 方法2：找“合计”附近的金额
        if not fields['total_amount']:
            if '合计' in texts:
                total_idx = texts.index('合计')
                for i in range(total_idx + 1, min(total_idx + 3, len(texts))):
                    text = texts[i]
                    if '￥' in text:
                        # 可能有两列：金额和税额，取最后一个 ¥
                        parts = text.split('￥')
                        if len(parts) > 1:
                            fields['total_amount'] = parts[-1].strip()
                        else:
                            fields['total_amount'] = text.replace('￥', '').strip()
                        break
    except Exception:
        pass

    return fields

def batch_process_folder(folder_path: str):
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"不是有效文件夹: {folder_path}")

    # 获取文件夹名称作为 CSV 文件名
    csv_filename = f"{folder.name}.csv"
    output_csv = folder.parent / csv_filename  # 保存在上一级目录，避免污染原图文件夹
    # 也可改为：output_csv = folder / csv_filename  保存在原文件夹内

    # 支持的图片格式
    image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
    image_files = [f for f in folder.iterdir() if f.suffix.lower() in image_extensions]

    if not image_files:
        print(f"⚠️ 在 {folder_path} 中未找到图片文件")
        return

    print(f"🔍 发现 {len(image_files)} 张图片，开始处理...")

    # 初始化 OCR
    ocr = init_ocr()

    # 存储结果
    results = []

    for img_file in image_files:
        print(f"📄 正在处理: {img_file.name}")
        try:
            result = ocr.predict(str(img_file))
            lines = extract_text_lines(result)
            fields = extract_invoice_fields_from_lines(lines)
            fields['filename'] = img_file.name  # 添加文件名
            results.append(fields)
        except Exception as e:
            print(f"❌ 处理失败 {img_file.name}: {str(e)}")
            results.append({
                'filename': img_file.name,
                'seller': '', 'buyer': '', 'tax_id': '',
                'service_items': '', 'amount': '', 'tax': '', 'total_amount': '',
                'error': str(e)
            })

    # 保存为 CSV
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False, encoding='utf_8_sig')
    print(f"✅ 批量处理完成！结果已保存至：{output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量处理发票图片，提取信息并保存为 CSV（文件夹名作为 CSV 名）")
    parser.add_argument("--input", type=str, required=True, help="发票图片文件夹路径")

    args = parser.parse_args()

    batch_process_folder(args.input)