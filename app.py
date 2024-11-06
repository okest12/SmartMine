from flask import Flask, render_template_string, request, jsonify
import oss2
import json
import re
from datetime import datetime

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

app = Flask(__name__)

def get_date_folders():
    folders = set()
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}/$')
    for obj in oss2.ObjectIterator(bucket, delimiter='/'):
        if obj.is_prefix():  # 检查是否为前缀（即文件夹）
            folder = obj.key
            if date_pattern.match(folder):
                folders.add(folder)
    return sorted(list(folders))

def get_images_in_folder(folder):
    images = []
    for obj in oss2.ObjectIterator(bucket, prefix=folder):
        if obj.key.endswith('.jpg'):
            images.append(obj.key)
    return images

@app.route('/')
def index():
    folders = get_date_folders()
    today_folder = datetime.now().strftime('%Y-%m-%d') + '/'
    if today_folder in folders:
        selected_folder = today_folder
    else:
        selected_folder = folders[0] if folders else ''
    
    images = get_images_in_folder(selected_folder)
    current_image = images[0] if images else None

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>智慧矿山</title>
            <style>
                .folder {
                    cursor: pointer;
                    margin: 5px;
                }
                .selected {
                    font-weight: bold;
                }
                .image-container {
                    margin-top: 20px;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <h1>智慧矿山</h1>
            <div id="folder-list">
                {% for folder in folders %}
                    <span class="folder {{ 'selected' if folder == selected_folder else '' }}" onclick="selectFolder('{{ folder }}')">{{ folder }}</span>
                {% endfor %}
            </div>
            <div id="image-container" class="image-container">
                {% if current_image %}
                    <img id="current-image" src="{{ url_for('get_image', image=current_image) }}" alt="Image">
                {% else %}
                    <p>No images found.</p>
                {% endif %}
            </div>
            <div>
                <button id="prev-btn" onclick="changeImage(-1)">Previous</button>
                <button id="next-btn" onclick="changeImage(1)">Next</button>
            </div>

            <script>
                let currentFolder = "{{ selected_folder }}";
                let images = {{ images|tojson }};
                let currentIndex = 0;

                function selectFolder(folder) {
                    currentFolder = folder;
                    fetch(`/get_images_list?folder=${encodeURIComponent(folder)}`)
                        .then(response => response.json())
                        .then(data => {
                            images = data.images;
                            currentIndex = 0;
                            updateImage();
                        });
                }

                function changeImage(direction) {
                    currentIndex += direction;
                    if (currentIndex < 0) {
                        currentIndex = images.length - 1;
                    } else if (currentIndex >= images.length) {
                        currentIndex = 0;
                    }
                    updateImage();
                }

                function updateImage() {
                    const imgElement = document.getElementById('current-image');
                    const prevBtn = document.getElementById('prev-btn');
                    const nextBtn = document.getElementById('next-btn');

                    if (images.length === 0) {
                        imgElement.src = '';
                        imgElement.alt = 'No images found.';
                        prevBtn.disabled = true;
                        nextBtn.disabled = true;
                    } else {
                        imgElement.src = `/get_image?image=${encodeURIComponent(images[currentIndex])}`;
                        imgElement.alt = 'Image';
                        prevBtn.disabled = false;
                        nextBtn.disabled = false;
                    }
                }
            </script>
        </body>
        </html>
    ''', folders=folders, selected_folder=selected_folder, images=images, current_image=current_image)

@app.route('/get_images_list')
def get_images_list():
    folder = request.args.get('folder', '')
    images = get_images_in_folder(folder)
    return jsonify(images=images)

@app.route('/get_image')
def get_image():
    image = request.args.get('image', '')
    if not image:
        return "No image specified", 400

    # 获取文件内容
    file_obj = bucket.get_object(image)
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