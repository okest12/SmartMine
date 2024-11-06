Install python from: https://www.python.org/downloads/
Install other components by: pip install opencv-python opencv-contrib-python Pillow numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
To install python virtual environment:
	sudo apt-get update
	sudo apt-get install python3-virtualenv
	virtualenv venv
	source venv/bin/activate
To Run web app at background:
	nohup python app.py &