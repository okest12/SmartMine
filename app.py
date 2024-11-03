from flask import Flask, render_template_string, request, jsonify, send_file
import oss2
import json

app = Flask(__name__)

# 读取配置文件
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# 获取配置信息
access_key_id = config['OSS']['access_key_id']
access_key_secret = config['OSS']['access_key_secret']
bucket_name = config['OSS']['bucket_name']
endpoint = config['OSS']['endpoint']

# 创建 Bucket 对象
auth = oss2.Auth(access_key_id, access_key_secret)
bucket = oss2.Bucket(auth, endpoint, bucket_name)

@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>OSS File List</title>
        </head>
        <body>
            <h1>OSS File List</h1>
            <button id="list-files-btn">查看</button>
            <div id="file-list"></div>

            <script>
                document.getElementById('list-files-btn').addEventListener('click', function() {
                    fetch('/list_files')
                        .then(response => response.json())
                        .then(data => {
                            const fileListDiv = document.getElementById('file-list');
                            fileListDiv.innerHTML = '';
                            const ul = document.createElement('ul');
                            data.files.forEach(file => {
                                const li = document.createElement('li');
                                const a = document.createElement('a');
                                a.href = `/view_file?file=${encodeURIComponent(file)}`;
                                a.textContent = file;
                                li.appendChild(a);
                                ul.appendChild(li);
                            });
                            fileListDiv.appendChild(ul);
                        });
                });
            </script>
        </body>
        </html>
    ''')

@app.route('/list_files')
def list_files():
    files = []
    for obj in oss2.ObjectIterator(bucket):
        files.append(obj.key)
    return jsonify(files=files)

@app.route('/view_file')
def view_file():
    file_name = request.args.get('file')
    if not file_name:
        return "No file specified", 400

    # 获取文件内容
    file_obj = bucket.get_object(file_name)
    file_content = file_obj.read()

    # 设置响应头
    response = app.response_class(
        response=file_content,
        status=200,
        mimetype='image/jpeg'  # 根据文件类型调整 MIME 类型
    )
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=80)