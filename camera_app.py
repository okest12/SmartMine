import tkinter as tk
from tkinter import Label, StringVar, Menu, simpledialog
import cv2
from PIL import Image, ImageTk
import datetime
import os
import numpy as np
from pathlib import Path
import json

class CameraApp:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        
        self.video_source = 0
        self.vid = None
        
        self.canvas = tk.Canvas(window, width=640, height=480)
        self.canvas.pack()
        
        self.progress_var = StringVar()
        self.progress_label = Label(window, textvariable=self.progress_var, width=50)
        self.progress_label.pack(anchor=tk.CENTER, expand=True)
        
        # 创建菜单
        self.menu = Menu(window)
        window.config(menu=self.menu)
        
        # 添加文件菜单
        self.file_menu = Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="文件", menu=self.file_menu)
        self.file_menu.add_command(label="打开摄像头", command=self.open_camera)
        self.file_menu.add_command(label="信息录入", command=self.prompt_for_name)
        self.file_menu.add_command(label="训练数据", command=self.train_data)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="退出", command=window.quit)
        
        self.center_window(800, 600)
        
        self.window.mainloop()

    def center_window(self, width, height):
        # 获取屏幕宽度和高度
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # 计算窗口左上角坐标
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        # 设置窗口大小和位置
        self.window.geometry(f'{width}x{height}+{x}+{y}')

    def open_camera(self):
        # id_to_name.json文件并建立id到name的映射关系
        if os.path.exists("trainer/id_to_name.json"):
            with open("trainer/id_to_name.json", "r") as f:
                names = json.load(f)
        else:
            names = []
        
        self.vid = cv2.VideoCapture(self.video_source)
        self.update_camera(names)

    def update_camera(self, names):
        ret, frame = self.vid.read()
        if ret:
            # 加载训练好的模型
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.read("trainer/trainer.yml")
            
            # 加载人脸检测器
            face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            
            # 将图像转换为灰度图
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 检测人脸
            faces = face_detector.detectMultiScale(gray)
            
            for (x, y, w, h) in faces:
                # 预测人脸
                id, confidence = recognizer.predict(gray[y:y+h, x:x+w])
                
                # 如果置信度低于100，则认为是已知人脸
                if confidence < 100:
                    name = names[id]
                    confidence_text = f"  {round(100 - confidence)}%"
                else:
                    name = "unknown"
                    confidence_text = f"  {round(100 - confidence)}%"
                
                # 绘制矩形框和标签
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                cv2.putText(frame, str(name), (x+5, y-5), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(frame, str(confidence_text), (x+5, y+h-5), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 1)
            
            self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        
        self.window.after(10, self.update_camera, names)

    def prompt_for_name(self):
        # 弹出对话框让用户输入姓名
        name = simpledialog.askstring("输入姓名", "请输入姓名：")
        if name:
            self.start_snapshot(name)

    def start_snapshot(self, name):
        self.vid = cv2.VideoCapture(self.video_source)
        self.snapshot_count = 0
        self.max_snapshots = 20
        self.snapshot_interval = 200  # 0.2 second
        self.update_snapshot(name)

    def update_snapshot(self, name):
        if self.snapshot_count < self.max_snapshots:
            ret, frame = self.vid.read()
            if ret:
                self.photo = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

                # 使用当前时间和姓名作为文件名
                filename = f"{name}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
                # 确保data目录存在
                if not os.path.exists("data"):
                    os.makedirs("data")
                # 保存照片到data目录
                filepath = os.path.join("data", filename)
                cv2.imwrite(filepath, frame)
                print(f"照片已保存: {filepath}")
                
                self.snapshot_count += 1
                self.window.after(self.snapshot_interval, self.update_snapshot, name)
        else:
            self.vid.release()
            print("拍照完成，摄像头已关闭")
            self.train_data()

    def train_data(self):
        self.progress_var.set("开始训练数据...")
        self.window.update()
        
        # 确保trainer目录存在
        if not os.path.exists("trainer"):
            os.makedirs("trainer")
        
        # 获取data目录下的所有图像文件
        image_paths = list(Path("data").glob("*.jpg"))
        face_samples = []
        ids = []
        names = []
        
        # 创建人脸识别分类器
        face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        
        for idx, image_path in enumerate(image_paths):
            name = image_path.stem.split('_')[0]
            if name in names:
                # 如果name在names中，返回其索引
                index = names.index(name)
            else:
                # 如果name不在names中，添加到最后
                names.append(name)
                index = len(names) - 1

            # 将图像转换为灰度图
            img = cv2.imread(str(image_path))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 检测人脸
            faces = face_detector.detectMultiScale(gray)
            
            for (x, y, w, h) in faces:
                face_samples.append(gray[y:y+h, x:x+w])
                ids.append(index)
            
            # 更新进度
            progress = (idx + 1) / len(image_paths) * 100
            self.progress_var.set(f"训练进度: {progress:.2f}%")
            self.window.update()
        
        # 训练人脸识别模型
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(face_samples, np.array(ids))
        
        # 保存训练结果
        recognizer.save("trainer/trainer.yml")
        
        # 保存ID和姓名的关联关系
        with open("trainer/id_to_name.json", "w") as f:
            json.dump(names, f)
        
        self.progress_var.set("训练完成，结果已保存到 trainer/trainer.yml")
        print("训练完成，结果已保存到 trainer/trainer.yml")

    def __del__(self):
        if self.vid and self.vid.isOpened():
            self.vid.release()

if __name__ == "__main__":
    root = tk.Tk()
    app = CameraApp(root, "摄像头应用")