import oss2
import os
import json

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
bucket = oss2.Bucket(auth, endpoint, bucket_name)

def list_and_upload_jpg_files():
    # 获取当前目录下的所有 .jpg 文件
    current_directory = os.getcwd()
    jpg_files = [f for f in os.listdir(current_directory) if f.endswith('.jpg')]

    # 上传文件到 OSS
    for file_name in jpg_files:
        file_path = os.path.join(current_directory, file_name)
        with open(file_path, 'rb') as file:
            bucket.put_object(file_name, file)
        print(f"Uploaded {file_name} to OSS")

    return jpg_files

if __name__ == '__main__':
    uploaded_files = list_and_upload_jpg_files()
    print("Uploaded files:")
    for file_name in uploaded_files:
        print(file_name)