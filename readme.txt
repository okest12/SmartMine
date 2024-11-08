Install python from: https://www.python.org/downloads/

At Edge server:
	Environment:
		pip install opencv-python opencv-contrib-python Pillow numpy oss2 -i https://pypi.tuna.tsinghua.edu.cn/simple
	Config:
		camera-config.json
		oss-config.json
	To Run the camera app:
		python camera_app.py

At ECS server:
	Environment:
		sudo apt-get update
		sudo apt-get install python3-virtualenv
		virtualenv venv
		source venv/bin/activate
		pip install oss2
	Config:
		oss-config.json
	To Run web app at background:
		nohup python app.py &