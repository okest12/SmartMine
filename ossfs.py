import oss2
import os
import configparser
import argparse
import datetime
import json

def create_oss_bucket():
    # 读取配置文件
    with open('oss-config.json', 'r') as config_file:
        config = json.load(config_file)

    # 获取配置信息
    access_key_id = config['OSS']['access_key_id']
    access_key_secret = config['OSS']['access_key_secret']
    bucket_name = config['OSS']['bucket_name']
    endpoint = config['OSS']['endpoint']

    # 创建 Bucket 对象
    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)

def ensure_directory_exists(bucket, directory):
    """确保目录存在，如果不存在则创建"""
    if not bucket.object_exists(directory):
        bucket.put_object(directory, '')

def upload_image(bucket, file_path):
    """上传图片到指定目录"""
    # 获取当前日期
    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    directory = f'{current_date}/'
    
    # 确保目录存在
    ensure_directory_exists(bucket, directory)
    
    # 构建文件名
    filename = os.path.basename(file_path)
    object_key = f'{directory}{filename}'
    
    # 上传文件
    with open(file_path, 'rb') as file:
        bucket.put_object(object_key, file)
    
    print(f'File {file_path} uploaded successfully to {object_key}')


def upload_jpg_files_to_oss(bucket, path):
    # 获取当前日期
    date_dir = datetime.datetime.now().strftime('%Y-%m-%d')

    if os.path.isfile(path):
        upload_image(bucket, path)
    elif os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file_name in files:
                if file_name.endswith('.jpg'):
                    file_path = os.path.join(root, file_name)
                    upload_image(bucket, file_path)
    else:
        print(f"Invalid path: {path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload JPG files to OSS.')
    parser.add_argument('path', type=str, help='Path to the file or directory to upload')
    args = parser.parse_args()
    bucket = create_oss_bucket()
    upload_jpg_files_to_oss(bucket, args.path)